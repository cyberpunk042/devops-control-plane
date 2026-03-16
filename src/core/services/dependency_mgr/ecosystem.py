"""
Ecosystem adapter — the protocol contract for package ecosystems.

Every ecosystem-specific detail lives behind this interface.
The rest of the system (scanner, pipeline, tree builder) talks to
adapters through the registry, never through ecosystem-specific code.

Same shape as ``src/adapters/base.py`` (ABC + abstract methods +
``__repr__``) but serves a different role: ecosystem knowledge
rather than action execution.

To add a new ecosystem:
    1. Subclass EcosystemAdapter
    2. Implement all abstract methods
    3. Add one line to ``_register_adapters()`` in ``__init__.py``
    Zero changes to scanner, pipeline, tree builder, or routes.
"""

from __future__ import annotations

import logging
import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .models import DeclaredDep, ManifestInfo, ParsedManifest

if TYPE_CHECKING:
    from .parsers.base import OutputParser

logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════════
#  Adapter protocol
# ═════════════════════════════════════════════════════════════════


class EcosystemAdapter(ABC):
    """Abstract base class for all ecosystem adapters.

    One subclass per package ecosystem (pip, npm, go, cargo, etc.).
    All ecosystem-specific logic — manifest detection, parsing,
    command building, output parsing, version queries — lives here.

    Contract:
    - Detection and parsing methods NEVER raise. Return empty on failure.
    - Command methods return argument lists, never execute them.
    - ``is_available()`` should be fast and never raise.
    """

    # ── Identity ──────────────────────────────────────────────

    @property
    @abstractmethod
    def id(self) -> str:
        """Ecosystem identifier: ``'pip'``, ``'npm'``, ``'go'``, etc."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable label: ``'Python (pip)'``, ``'Node (npm)'``."""

    @property
    @abstractmethod
    def cli(self) -> str:
        """Primary CLI tool name: ``'pip'``, ``'npm'``, ``'go'``."""

    # ── Detection (Phase 1 — fast, no file reads) ────────────

    @abstractmethod
    def detect(self, directory: Path) -> list[ManifestInfo]:
        """Check if this ecosystem has manifests in the given directory.

        Fast: only checks file existence and ``stat()``.  No parsing.
        Returns empty list if ecosystem not present.

        Args:
            directory: Absolute path to scan.

        Returns:
            List of ``ManifestInfo`` — one per manifest file found.
        """

    def is_available(self) -> bool:
        """Check if the CLI tool is installed and accessible.

        Default implementation uses ``shutil.which()``.
        Override for ecosystems that need special checks (e.g. pip
        uses ``sys.executable -m pip``).
        """
        return shutil.which(self.cli) is not None

    # ── Parsing (Phase 2 — reads file contents) ──────────────

    @abstractmethod
    def parse_manifest(
        self, manifest: Path, lock_file: Path | None,
    ) -> ParsedManifest:
        """Parse a manifest file into declared dependencies.

        Reads file contents.  Uses lock file for pinned versions
        if available.

        Args:
            manifest: Absolute path to the manifest file.
            lock_file: Absolute path to lock file, or None.

        Returns:
            ``ParsedManifest`` with dependencies and dev_dependencies.
        """

    # ── Commands (return args, never execute) ─────────────────

    @abstractmethod
    def install_cmd(
        self, directory: Path, *, dev: bool = False, frozen: bool = True,
    ) -> list[str]:
        """Command to install all dependencies in this directory.

        Args:
            directory: Working directory for the command.
            dev: Include dev dependencies.
            frozen: Use lock file (``npm ci``, ``pip install -r``).
                If False, resolve fresh (``npm install``).

        Returns:
            Command argument list (for ``subprocess.Popen``).
        """

    @abstractmethod
    def update_cmd(
        self, directory: Path, packages: list[str] | None = None,
    ) -> list[str]:
        """Command to update dependencies.

        Args:
            directory: Working directory.
            packages: Specific packages to update.  ``None`` = all.

        Returns:
            Command argument list.
        """

    @abstractmethod
    def update_single_cmd(
        self, directory: Path, package: str, version: str | None = None,
    ) -> list[str]:
        """Command to update one specific package.

        Args:
            directory: Working directory.
            package: Package name.
            version: Target version.  ``None`` = latest.

        Returns:
            Command argument list.
        """

    # ── Rollback ──────────────────────────────────────────────

    @abstractmethod
    def snapshot_files(self, directory: Path) -> list[Path]:
        """Files to backup before an operation.

        Returns absolute paths to manifest and lock files that should
        be snapshotted.  Empty list if nothing to snapshot.
        """

    @abstractmethod
    def restore_cmd(self, directory: Path) -> list[str]:
        """Command to run after restoring snapshot files.

        Syncs the installed state with the restored lock/manifest.
        E.g. ``pip install -r requirements.txt`` or ``npm ci``.
        """

    # ── Output parsing ────────────────────────────────────────

    @abstractmethod
    def create_output_parser(self, scope: str) -> OutputParser:
        """Create a fresh output parser for this ecosystem.

        Each operation gets its own parser instance (stateful).

        Args:
            scope: The TreeNode.id for this operation (passed to events).
        """

    # ── Version intelligence ──────────────────────────────────

    @abstractmethod
    def fetch_latest_version(self, package: str) -> str | None:
        """Query the ecosystem registry for the latest version.

        Network call.  Returns ``None`` on failure or timeout.
        Caller handles caching.
        """

    @abstractmethod
    def check_deprecated(
        self, package: str, version: str,
    ) -> tuple[bool, str]:
        """Check if a specific package version is deprecated/yanked.

        Returns:
            ``(is_deprecated, detail_message)``.
            ``(False, "")`` if not deprecated or on lookup failure.
        """

    # ── Repr ──────────────────────────────────────────────────

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self.id!r}>"


# ═════════════════════════════════════════════════════════════════
#  Registry
# ═════════════════════════════════════════════════════════════════


class EcosystemRegistry:
    """Central lookup for ecosystem adapters.

    Same pattern as ``src/adapters/registry.py`` but simpler:
    no circuit breakers, no mock mode, no execution dispatch.
    Registration, lookup, and availability queries only.

    The pipeline (``pipeline.py``) handles execution — the registry
    just resolves which adapter to use.
    """

    def __init__(self) -> None:
        self._adapters: dict[str, EcosystemAdapter] = {}

    def register(self, adapter: EcosystemAdapter) -> None:
        """Register an ecosystem adapter by its ``id``."""
        aid = adapter.id
        if aid in self._adapters:
            logger.warning("Overwriting ecosystem adapter: %s", aid)
        self._adapters[aid] = adapter
        logger.debug("Registered ecosystem adapter: %s", aid)

    def unregister(self, ecosystem_id: str) -> None:
        """Remove an adapter from the registry."""
        self._adapters.pop(ecosystem_id, None)

    def get(self, ecosystem_id: str) -> EcosystemAdapter | None:
        """Look up an adapter by ecosystem ID."""
        return self._adapters.get(ecosystem_id)

    def all(self) -> list[EcosystemAdapter]:
        """All registered adapters (regardless of availability)."""
        return list(self._adapters.values())

    def available(self) -> list[EcosystemAdapter]:
        """Only adapters whose CLI tool is installed."""
        result = []
        for adapter in self._adapters.values():
            try:
                if adapter.is_available():
                    result.append(adapter)
            except Exception:
                pass
        return result

    def ids(self) -> list[str]:
        """List all registered ecosystem IDs."""
        return list(self._adapters.keys())

    def status(self) -> dict[str, dict[str, Any]]:
        """Availability status of all registered adapters."""
        result: dict[str, dict[str, Any]] = {}
        for adapter in self._adapters.values():
            try:
                avail = adapter.is_available()
            except Exception:
                avail = False
            result[adapter.id] = {
                "name": adapter.name,
                "cli": adapter.cli,
                "available": avail,
                "type": adapter.__class__.__name__,
            }
        return result
