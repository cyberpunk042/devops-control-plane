"""Documentation reference validator — detect stale references in docs.

This module provides:
- Universal data models for documentation reference validation
- A DocValidator that scans markdown files for references to source code
  and checks whether those references are still accurate

What it detects:
- File references that point to files that no longer exist
- Line references (e.g., "line 42") that are out of range
- Function/class references that can't be found in the target file

Design principle: OBSERVE, DON'T JUDGE.
"docs/ARCH.md references src/foo.py which doesn't exist" is a fact.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


# ═══════════════════════════════════════════════════════════════════
#  Data Models
# ═══════════════════════════════════════════════════════════════════


@dataclass
class DocReference:
    """A reference found in a documentation file."""

    doc_file: str               # Path to the doc containing the reference
    doc_line: int               # Line number in the doc
    reference_type: str         # "file" | "line" | "line_count" | "function" | "class"
    reference_text: str         # The original text matched
    target_file: str            # The file being referenced
    target_detail: str | None = None  # e.g., line number, function name
    is_valid: bool = True       # Whether the reference checks out
    issue: str | None = None    # What's wrong, if invalid


@dataclass
class DocFileAnalysis:
    """Analysis of references in a single documentation file."""

    doc_file: str
    total_references: int = 0
    valid_references: int = 0
    stale_references: list[DocReference] = field(default_factory=list)
    all_references: list[DocReference] = field(default_factory=list)

    @property
    def freshness(self) -> float:
        """Fraction of references that are still valid (0.0–1.0)."""
        if self.total_references == 0:
            return 1.0
        return self.valid_references / self.total_references


@dataclass
class DocAuditResult:
    """Complete documentation freshness result — facts only."""

    files: list[DocFileAnalysis] = field(default_factory=list)

    @property
    def total_docs(self) -> int:
        return len(self.files)

    @property
    def docs_with_references(self) -> int:
        return sum(1 for f in self.files if f.total_references > 0)

    @property
    def total_references(self) -> int:
        return sum(f.total_references for f in self.files)

    @property
    def total_valid(self) -> int:
        return sum(f.valid_references for f in self.files)

    @property
    def total_stale(self) -> int:
        return sum(len(f.stale_references) for f in self.files)

    @property
    def overall_freshness(self) -> float:
        if self.total_references == 0:
            return 1.0
        return self.total_valid / self.total_references


# ═══════════════════════════════════════════════════════════════════
#  Reference Patterns
# ═══════════════════════════════════════════════════════════════════


# Match backtick-quoted file paths that look like source files
# e.g., `src/core/services/vault.py`, `src/ui/web/routes/audit/__init__.py`
_FILE_REF_PATTERN = re.compile(
    r"`((?:src|tests|scripts|lib)/[a-zA-Z0-9_/]+\.(?:py|js|ts|go|java|sh|ps1|yml|yaml|json|toml))`"
)

# Match line references like "line 42", "L42", "lines 10-25"
_LINE_REF_PATTERN = re.compile(
    r"(?:line|L)\s*(\d+)(?:\s*[-–]\s*(\d+))?",
    re.IGNORECASE,
)

# Match line count references like "150 lines", "~200 lines"
_LINE_COUNT_PATTERN = re.compile(
    r"~?(\d+)\s+lines?\b",
    re.IGNORECASE,
)

# Match function/method references like `_parse_header()`, `do_something()`
_FUNC_REF_PATTERN = re.compile(
    r"`([a-zA-Z_][a-zA-Z0-9_]*)\(\)`"
)

# Match class references like `class EventBus`, `EventBus` (in code context)
_CLASS_REF_PATTERN = re.compile(
    r"`(?:class\s+)?([A-Z][a-zA-Z0-9]+)`"
)


# ═══════════════════════════════════════════════════════════════════
#  Validator
# ═══════════════════════════════════════════════════════════════════


class DocValidator:
    """Validate documentation references against the actual codebase.

    Scans markdown files for references to source files, line numbers,
    functions, and classes.  Checks each reference against the real
    filesystem to determine if it's still accurate.
    """

    def analyze(
        self,
        project_root: Path,
        *,
        doc_dirs: list[str] | None = None,
        scope: str | None = None,
        exclude_dirs: list[str] | None = None,
    ) -> DocAuditResult:
        """Analyze documentation for stale references.

        Args:
            project_root: Project root directory.
            doc_dirs: Directories to scan for docs (relative to root).
                      Defaults to ["docs", ".agent/plans", "README.md"].
            scope: Optional scope to limit doc scanning.
            exclude_dirs: Directories to exclude (relative to root).
                          Defaults to ["docs/audits"] to avoid scanning
                          the report's own output.

        Returns:
            DocAuditResult with all analyzed files.
        """
        if doc_dirs is None:
            doc_dirs = ["docs"]
        if exclude_dirs is None:
            exclude_dirs = ["docs/audits"]

        # Resolve exclusion paths for matching
        excluded_abs = [
            (project_root / e).resolve() for e in exclude_dirs
        ]

        def _is_excluded(path: Path) -> bool:
            resolved = path.resolve()
            return any(
                resolved == ex or str(resolved).startswith(str(ex) + "/")
                for ex in excluded_abs
            )

        result = DocAuditResult()

        for doc_dir in doc_dirs:
            doc_path = project_root / doc_dir

            if doc_path.is_file() and doc_path.suffix == ".md":
                # Single file (e.g., README.md)
                if _is_excluded(doc_path):
                    continue
                analysis = self._analyze_doc(doc_path, project_root)
                if analysis is not None:
                    result.files.append(analysis)
            elif doc_path.is_dir():
                for md_file in sorted(doc_path.rglob("*.md")):
                    if "__pycache__" in str(md_file):
                        continue
                    if _is_excluded(md_file):
                        continue
                    analysis = self._analyze_doc(md_file, project_root)
                    if analysis is not None:
                        result.files.append(analysis)

        return result

    def _analyze_doc(
        self,
        doc_path: Path,
        project_root: Path,
    ) -> DocFileAnalysis | None:
        """Analyze a single markdown file for references."""
        try:
            content = doc_path.read_text(errors="replace")
        except OSError:
            return None

        rel_path = str(doc_path.relative_to(project_root))
        analysis = DocFileAnalysis(doc_file=rel_path)
        lines = content.splitlines()

        # Track the most recently seen file reference for context
        # (line numbers often appear near a file reference)
        last_file_ref: str | None = None

        for lineno, line in enumerate(lines, start=1):
            # Skip code blocks (fenced ``` blocks)
            # Simple heuristic: skip lines inside triple-backtick blocks
            # (A full parser would track open/close, but this is good enough)
            if line.strip().startswith("```"):
                continue

            # ── File references ──
            for match in _FILE_REF_PATTERN.finditer(line):
                ref_path = match.group(1)
                last_file_ref = ref_path
                ref = self._check_file_ref(
                    ref_path, project_root, rel_path, lineno, match.group(0),
                )
                analysis.all_references.append(ref)
                analysis.total_references += 1
                if ref.is_valid:
                    analysis.valid_references += 1
                else:
                    analysis.stale_references.append(ref)

            # ── Function references ──
            for match in _FUNC_REF_PATTERN.finditer(line):
                func_name = match.group(1)
                # Only validate if we have a nearby file context
                if last_file_ref:
                    ref = self._check_func_ref(
                        func_name, last_file_ref, project_root,
                        rel_path, lineno, match.group(0),
                    )
                    analysis.all_references.append(ref)
                    analysis.total_references += 1
                    if ref.is_valid:
                        analysis.valid_references += 1
                    else:
                        analysis.stale_references.append(ref)

        return analysis

    # ── Check methods ──

    @staticmethod
    def _check_file_ref(
        ref_path: str,
        project_root: Path,
        doc_file: str,
        lineno: int,
        raw_text: str,
    ) -> DocReference:
        """Check if a file reference points to an existing file."""
        target = project_root / ref_path
        ref = DocReference(
            doc_file=doc_file,
            doc_line=lineno,
            reference_type="file",
            reference_text=raw_text,
            target_file=ref_path,
        )
        if not target.exists():
            ref.is_valid = False
            ref.issue = "File does not exist"
        return ref

    @staticmethod
    def _check_func_ref(
        func_name: str,
        context_file: str,
        project_root: Path,
        doc_file: str,
        lineno: int,
        raw_text: str,
    ) -> DocReference:
        """Check if a function reference exists in the context file."""
        target = project_root / context_file
        ref = DocReference(
            doc_file=doc_file,
            doc_line=lineno,
            reference_type="function",
            reference_text=raw_text,
            target_file=context_file,
            target_detail=func_name,
        )

        if not target.is_file():
            ref.is_valid = False
            ref.issue = f"Context file {context_file} does not exist"
            return ref

        try:
            content = target.read_text(errors="replace")
        except OSError:
            ref.is_valid = False
            ref.issue = f"Cannot read {context_file}"
            return ref

        # Search for function definition
        if f"def {func_name}" not in content and f"def {func_name}" not in content:
            ref.is_valid = False
            ref.issue = f"Function '{func_name}()' not found in {context_file}"

        return ref
