"""Verifier — prove a fix actually worked before accepting it.

Runs checks in order, stops on first failure:
1. Syntax check — file parses without errors
2. Re-detection — feature no longer detected in the AST
3. Import check — file can still be imported/compiled
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..analysis.engine import DetectionEngine
    from ..backends.base import LanguageBackend

logger = logging.getLogger(__name__)


@dataclass
class VerificationCheck:
    """Result of a single verification check."""
    check_type: str              # "syntax", "re_detection", "import"
    passed: bool
    message: str
    duration_ms: int = 0


@dataclass
class VerificationResult:
    """Complete verification result for a fix."""
    file_path: str
    feature_id: str
    checks: list[VerificationCheck] = field(default_factory=list)
    duration_ms: int = 0

    @property
    def all_passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def failed_checks(self) -> list[VerificationCheck]:
        return [c for c in self.checks if not c.passed]

    @property
    def errors(self) -> list[str]:
        return [c.message for c in self.checks if not c.passed]


class Verifier:
    """Run verification checks on fixed files."""

    def __init__(
        self,
        detection_engine: DetectionEngine,
        backend: LanguageBackend,
    ):
        self._detection = detection_engine
        self._backend = backend

    def verify_fix(
        self,
        file_path: Path,
        feature_id: str,
        project_root: Path,
        run_import_check: bool = True,
    ) -> VerificationResult:
        """Run all verification checks for a single fix.

        Order: syntax → re-detection → import (stop on first failure).
        """
        t0 = time.time()
        result = VerificationResult(
            file_path=str(file_path),
            feature_id=feature_id,
        )

        # 1. Syntax check
        t1 = time.time()
        passed, msg = self._backend.check_syntax(file_path)
        result.checks.append(VerificationCheck(
            check_type="syntax",
            passed=passed,
            message=msg if not passed else "File parses without errors",
            duration_ms=int((time.time() - t1) * 1000),
        ))
        if not passed:
            result.duration_ms = int((time.time() - t0) * 1000)
            return result

        # 2. Re-detection
        t2 = time.time()
        self._detection.invalidate_cache(file_path)
        still_found = not self._detection.verify_fix(file_path, feature_id, project_root)
        result.checks.append(VerificationCheck(
            check_type="re_detection",
            passed=not still_found,
            message=(
                f"Feature '{feature_id}' still detected after fix"
                if still_found
                else "Feature no longer detected"
            ),
            duration_ms=int((time.time() - t2) * 1000),
        ))
        if still_found:
            result.duration_ms = int((time.time() - t0) * 1000)
            return result

        # 3. Import check
        if run_import_check:
            t3 = time.time()
            passed, msg = self._backend.check_importable(file_path, project_root)
            result.checks.append(VerificationCheck(
                check_type="import",
                passed=passed,
                message=msg if not passed else "File imports successfully",
                duration_ms=int((time.time() - t3) * 1000),
            ))

        result.duration_ms = int((time.time() - t0) * 1000)
        return result

    def verify_file(
        self,
        file_path: Path,
        feature_ids: list[str],
        project_root: Path,
        run_import_check: bool = True,
    ) -> list[VerificationResult]:
        """Verify all fixes in a single file.

        Syntax check runs once. Re-detection runs per feature.
        Import check runs once at the end.
        """
        results: list[VerificationResult] = []

        # 1. Syntax check (once for the file)
        passed, msg = self._backend.check_syntax(file_path)
        if not passed:
            for fid in feature_ids:
                results.append(VerificationResult(
                    file_path=str(file_path),
                    feature_id=fid,
                    checks=[VerificationCheck(
                        check_type="syntax",
                        passed=False,
                        message=msg,
                    )],
                ))
            return results

        # 2. Re-detection (per feature)
        self._detection.invalidate_cache(file_path)
        all_re_detect_passed = True

        for fid in feature_ids:
            still_found = not self._detection.verify_fix(file_path, fid, project_root)
            vr = VerificationResult(
                file_path=str(file_path),
                feature_id=fid,
                checks=[
                    VerificationCheck(
                        check_type="syntax",
                        passed=True,
                        message="File parses without errors",
                    ),
                    VerificationCheck(
                        check_type="re_detection",
                        passed=not still_found,
                        message=(
                            f"Feature '{fid}' still detected after fix"
                            if still_found
                            else "Feature no longer detected"
                        ),
                    ),
                ],
            )
            if still_found:
                all_re_detect_passed = False
            results.append(vr)

        # 3. Import check (once, only if all re-detections passed)
        if run_import_check and all_re_detect_passed:
            passed, msg = self._backend.check_importable(file_path, project_root)
            import_check = VerificationCheck(
                check_type="import",
                passed=passed,
                message=msg if not passed else "File imports successfully",
            )
            for vr in results:
                vr.checks.append(import_check)

        return results
