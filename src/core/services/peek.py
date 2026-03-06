"""
Peek — file and symbol reference scanner and resolver for documentation.

Scans markdown content for file/path/symbol references and resolves them
against the project filesystem and AST index. Each resolved reference
becomes a peekable element that can be linked to the source location.

Pattern types:
    T1  Backticked filename with known extension:  `l0_detection.py`
    T2  Path with slashes:  src/core/services/audit/
    T3  Filename with line number:  helpers.py:48
    T4  Filename in heading (handled by T1/T6)
    T5  Backticked function/class:  `l0_system_profile()`  `DocusaurusBuilder`
    T6  Bare filename in prose:  scoring.py

Public API:
    scan_and_resolve(content, doc_path, project_root, symbol_index=None)
        → list[PeekReference]
    build_symbol_index(project_root)
        → dict[str, list[SymbolEntry]]
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ── Known extensions (mirrors crypto.py sets) ────────────────────────

_CODE_EXTS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".c", ".cpp", ".h", ".hpp",
    ".cs", ".go", ".rs", ".rb", ".php", ".swift", ".kt", ".scala", ".r",
    ".lua", ".dart", ".vue", ".svelte", ".zig", ".nim", ".ex", ".exs",
    ".clj", ".erl", ".hs", ".ml", ".fs", ".v", ".vhdl",
    ".html", ".htm", ".css", ".scss", ".less", ".sass", ".wasm",
}
_SCRIPT_EXTS = {
    ".sh", ".bash", ".zsh", ".fish", ".bat", ".cmd", ".ps1", ".psm1",
    ".pl", ".awk", ".sed",
}
_CONFIG_EXTS = {
    ".yaml", ".yml", ".json", ".toml", ".ini", ".cfg", ".conf",
    ".env", ".properties", ".xml", ".plist",
}
_DOC_EXTS = {".md", ".rst", ".txt", ".mdx"}
_DATA_EXTS = {
    ".csv", ".tsv", ".sql", ".sqlite", ".db",
    ".jsonl", ".ndjson",
}

KNOWN_EXTS = _CODE_EXTS | _SCRIPT_EXTS | _CONFIG_EXTS | _DOC_EXTS | _DATA_EXTS

# Special filenames that are recognisable without extension check
_KNOWN_FILENAMES = {
    "Makefile", "Dockerfile", "Vagrantfile", "Procfile",
    ".gitignore", ".gitattributes", ".editorconfig",
    ".dockerignore", "docker-compose.yml", "docker-compose.yaml",
    "pyproject.toml", "setup.cfg", "package.json", "tsconfig.json",
    "Cargo.toml", "go.mod", "Gemfile", "mix.exs",
    "README.md", "CHANGELOG.md", "LICENSE",
}


# ── Data classes ─────────────────────────────────────────────────────

@dataclass
class PeekCandidate:
    """A potential file reference found in text, before validation."""
    text: str              # Matched text as it appears
    type: str              # "T1", "T2", "T3", "T5", "T6"
    candidate_path: str    # Best-guess relative path (or symbol name for T5)
    line_number: int | None  # For T3
    in_code_fence: bool    # Inside ``` block


@dataclass
class PeekReference:
    """A validated file reference that resolves to a real path."""
    text: str              # Matched text as it appears
    type: str              # "T1", "T2", "T3", "T5", "T6"
    resolved_path: str     # Validated path relative to project root
    line_number: int | None
    is_directory: bool


@dataclass
class SymbolEntry:
    """A single symbol location in the project."""
    name: str
    file: str              # Relative path from project root
    line: int              # Start line
    kind: str              # "function", "class", "async_function", etc.


# ── Helpers ──────────────────────────────────────────────────────────

def _has_known_ext(name: str) -> bool:
    """Check if a filename has a known source/config/script extension."""
    dot = name.rfind(".")
    if dot < 1:
        return False
    return name[dot:].lower() in KNOWN_EXTS


def _is_known_filename(name: str) -> bool:
    """Check if a bare name is a recognised config/project file."""
    return name in _KNOWN_FILENAMES


# ── Pattern scanner ──────────────────────────────────────────────────

# T1: backticked filename with known extension
# Matches: `name.ext`  (must have a dot and known extension)
_RE_T1 = re.compile(r"`([A-Za-z0-9_][A-Za-z0-9_./-]*\.[a-z]{1,5})`")

# T2: path with slashes (optionally backticked)
# Matches: `path/to/thing`  or  path/to/thing  (must contain at least one /)
_RE_T2_BACKTICK = re.compile(r"`([A-Za-z0-9_.][A-Za-z0-9_./-]*/[A-Za-z0-9_./-]*)`")
_RE_T2_BARE = re.compile(
    r"(?<![(\\\"'`/])([A-Za-z0-9_.][A-Za-z0-9_./-]*/[A-Za-z0-9_./-]*)(?![)\"'`])"
)
# Strip markdown link targets before T2 bare matching:
# [text](target) → [text]  — keeps link text, removes URL target.
_RE_MD_LINK_TARGET = re.compile(r"\]\([^)]+\)")

# T3: filename:line_number
# Matches: name.ext:42
_RE_T3 = re.compile(r"`?([A-Za-z0-9_][A-Za-z0-9_./-]*\.[a-z]{1,5}):(\d+)`?")

# Bare filename (no backticks) — used inside code fences for file maps
# Matches: l0_detection.py  (word-boundary delimited, known extension)
_RE_BARE_FILENAME = re.compile(
    r"(?<![A-Za-z0-9_./])([A-Za-z_][A-Za-z0-9_.]*\.[a-z]{1,5})(?![A-Za-z0-9_./])"
)

# T5: backticked function call or class name
# Matches: `func_name()` or `func_name(args)` or `func_name`
# Must look like a Python identifier (starts with letter/underscore)
_RE_T5_FUNC = re.compile(
    r"`([a-z_][a-z0-9_]*)\(`[^`]*`?\)`?"
    r"|"  # or just `func_name()` with parens inside backticks
    r"`([a-z_][a-z0-9_]*)\([^)]*\)`"
)
# Matches: `ClassName` (PascalCase identifier)
_RE_T5_CLASS = re.compile(
    r"`([A-Z][a-zA-Z0-9]*)`"
)


def scan_peek_candidates(
    content: str,
    doc_path: str,
) -> list[PeekCandidate]:
    """Scan markdown content for potential file/path references.

    Args:
        content: Raw markdown text.
        doc_path: Relative path of the document being scanned
                  (e.g. "src/core/services/audit/README.md").

    Returns:
        List of candidates (not yet validated against filesystem).
    """
    candidates: list[PeekCandidate] = []
    seen_texts: set[str] = set()  # deduplicate

    lines = content.split("\n")
    in_fence = False

    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("```"):
            in_fence = not in_fence

        # Skip lines that are already markdown links: [text](url)
        # We don't want to peek inside existing link targets
        # (but we DO want to peek inside link text — the scanner
        #  does not need to worry about that here, the DOM annotator
        #  will skip elements already inside <a> tags)

        # ── T3: file:line (check before T1 to avoid partial match) ──
        for m in _RE_T3.finditer(line):
            filename = m.group(1)
            lineno = int(m.group(2))
            if not _has_known_ext(filename):
                continue
            full = f"{filename}:{lineno}"
            if full in seen_texts:
                continue
            seen_texts.add(full)
            candidates.append(PeekCandidate(
                text=full,
                type="T3",
                candidate_path=filename,
                line_number=lineno,
                in_code_fence=in_fence,
            ))

        # ── T2: path with slashes (backticked) ──
        for m in _RE_T2_BACKTICK.finditer(line):
            path_text = m.group(1)
            # Skip if it looks like a URL
            if path_text.startswith(("http://", "https://", "//")):
                continue
            if path_text in seen_texts:
                continue
            seen_texts.add(path_text)
            candidates.append(PeekCandidate(
                text=path_text,
                type="T2",
                candidate_path=path_text,
                line_number=None,
                in_code_fence=in_fence,
            ))

        # ── T2: path with slashes (bare) ──
        # Strip markdown link targets so [dir/](dir/README.md) only
        # yields "dir/" (from the link text), not "dir/README.md".
        bare_line = _RE_MD_LINK_TARGET.sub("]", line)

        for m in _RE_T2_BARE.finditer(bare_line):
            path_text = m.group(1)
            if path_text.startswith(("http://", "https://", "//", "#")):
                continue
            # Skip if already captured by backtick variant
            if path_text in seen_texts:
                continue
            # Skip if inside a markdown link target (parenthesized)
            start = m.start(1)
            if start > 0 and bare_line[start - 1] == "(":
                continue
            # Skip URL fragments: if :// appears shortly before the match,
            # this is part of a URL, not a project path reference.
            before = bare_line[max(0, start - 20):start]
            if "://" in before:
                continue
            seen_texts.add(path_text)
            candidates.append(PeekCandidate(
                text=path_text,
                type="T2",
                candidate_path=path_text,
                line_number=None,
                in_code_fence=in_fence,
            ))

        # ── T1: backticked filename ──
        for m in _RE_T1.finditer(line):
            filename = m.group(1)
            if not _has_known_ext(filename):
                continue
            # Skip if already captured by T3 (file:line) or T2 (path/with/slash)
            if filename in seen_texts:
                continue
            # Skip filenames that contain / (those are T2 paths)
            if "/" in filename:
                continue
            seen_texts.add(filename)
            candidates.append(PeekCandidate(
                text=filename,
                type="T1",
                candidate_path=filename,
                line_number=None,
                in_code_fence=in_fence,
            ))

        # ── Bare filename detection ──
        # Inside code fences (file maps, dependency graphs): high-confidence → T1
        # Outside code fences (prose): lower confidence → T6
        # Filesystem validation in the resolver eliminates false positives.
        for m in _RE_BARE_FILENAME.finditer(line):
            filename = m.group(1)
            if not _has_known_ext(filename):
                continue
            if filename in seen_texts:
                continue
            if "/" in filename:
                continue

            # Skip if this line looks like a URL or markdown link target
            if not in_fence:
                start = m.start(1)
                # Inside a markdown link target: [text](file.py)
                if start > 0 and line[start - 1] == "(":
                    continue
                # Inside a URL
                if "://" in line[:start]:
                    continue
                # Inside an HTML attribute (href="...", src="...")
                if '"' in line[max(0, start - 10):start]:
                    continue

            seen_texts.add(filename)
            candidates.append(PeekCandidate(
                text=filename,
                type="T1" if in_fence else "T6",
                candidate_path=filename,
                line_number=None,
                in_code_fence=in_fence,
            ))

        # ── T5: backticked function/class name ──
        # Only outside code fences (inside fences, these are code, not refs)
        if not in_fence:
            # Function calls: `func_name()` or `func_name(args)`
            for m in _RE_T5_FUNC.finditer(line):
                sym_name = m.group(1) or m.group(2)
                if not sym_name:
                    continue
                if sym_name in seen_texts:
                    continue
                # Skip common language keywords
                if sym_name in _COMMON_KEYWORDS:
                    continue
                seen_texts.add(sym_name)
                candidates.append(PeekCandidate(
                    text=sym_name,
                    type="T5",
                    candidate_path=sym_name,  # symbol name, not a path
                    line_number=None,
                    in_code_fence=False,
                ))

            # Class names: `ClassName` (PascalCase)
            for m in _RE_T5_CLASS.finditer(line):
                class_name = m.group(1)
                if class_name in seen_texts:
                    continue
                # Skip if it looks like a filename (has known extension)
                if _has_known_ext(class_name):
                    continue
                # Skip single-char or too-short names
                if len(class_name) < 3:
                    continue
                # Skip common non-class words
                if class_name in _COMMON_PASCAL:
                    continue
                seen_texts.add(class_name)
                candidates.append(PeekCandidate(
                    text=class_name,
                    type="T5",
                    candidate_path=class_name,
                    line_number=None,
                    in_code_fence=False,
                ))

    return candidates


# Common keywords to skip for T5 function detection
_COMMON_KEYWORDS = {
    "if", "for", "while", "return", "yield", "print", "len", "str",
    "int", "float", "bool", "list", "dict", "set", "tuple", "type",
    "range", "enumerate", "zip", "map", "filter", "sorted", "reversed",
    "any", "all", "sum", "min", "max", "abs", "round", "hash",
    "open", "close", "read", "write", "append", "extend", "insert",
    "super", "self", "cls", "isinstance", "issubclass", "hasattr",
    "getattr", "setattr", "delattr", "property", "staticmethod",
    "classmethod", "true", "false", "none", "null",
}

# Common PascalCase words that aren't class references
_COMMON_PASCAL = {
    "True", "False", "None", "Error", "Type", "String", "Integer",
    "Boolean", "Float", "Number", "Object", "Array", "Map", "Set",
    "Promise", "Optional", "Required", "Default", "Example",
    "Note", "Warning", "Important", "Todo", "Fixme", "Hack",
    "Yes", "No", "See", "Returns", "Args", "Raises", "Yields",
    "Phase", "Step", "Stage", "Level", "Status", "Table",
}


# ── Filename index ───────────────────────────────────────────────────

def _build_filename_index(
    project_root: Path,
    doc_dir: str,
) -> dict[str, list[str]]:
    """Build filename → list[relative_path] index for the doc's subtree.

    Scans the directory tree rooted at the document's directory (or project
    root if doc_dir is empty) and maps each filename to all relative paths
    where it appears. This enables efficient subdirectory lookup.

    Args:
        project_root: Absolute path to the project root.
        doc_dir: Relative path of the document's directory (may be "").

    Returns:
        { "action.py": ["src/core/models/action.py"], ... }
    """
    index: dict[str, list[str]] = {}
    base = project_root / doc_dir if doc_dir else project_root

    if not base.is_dir():
        return index

    for f in base.rglob("*"):
        try:
            rel = str(f.relative_to(project_root))
        except ValueError:
            continue
        index.setdefault(f.name, []).append(rel)
        # Also index directory names with trailing /
        if f.is_dir():
            index.setdefault(f.name + "/", []).append(rel)

    return index


# ── Resolver ─────────────────────────────────────────────────────────

def resolve_peek_candidates(
    candidates: list[PeekCandidate],
    doc_path: str,
    project_root: Path,
    symbol_index: dict[str, list[SymbolEntry]] | None = None,
) -> list[PeekReference]:
    """Validate candidates against the filesystem and symbol index.

    Resolution order for file references (T1, T2, T3, T6):
        1. Same directory as the document
        2. Subdirectory search via filename index (closest match wins)
        3. Project root (for paths containing /)
        4. One level up from the document

    T5 symbol references are resolved via the symbol index
    with proximity-based disambiguation.

    Uses the passive ProjectIndex when available (zero I/O). Falls back
    to on-demand _build_filename_index() if the index isn't ready.

    Args:
        candidates: Unvalidated peek candidates.
        doc_path: Relative path of the document.
        project_root: Absolute path to the project root.
        symbol_index: Optional symbol name → locations index for T5.

    Returns:
        List of validated references (only those that exist on disk).
    """
    # Determine the document's directory
    doc_dir = str(Path(doc_path).parent)
    if doc_dir == ".":
        doc_dir = ""

    # Use project index if available (zero I/O), else build on-demand.
    fn_index: dict[str, list[str]] | None = None
    all_paths: set[str] | None = None

    dir_paths: set[str] | None = None

    try:
        from src.core.services.project_index import get_index
        idx = get_index()
        if idx.ready:
            # Merge file_map + dir_map so the resolver can find BOTH
            # files and directories via the subdirectory search path.
            fn_index = {**idx.file_map, **idx.dir_map}
            all_paths = idx.all_paths
            # Build set of full directory paths for is_directory detection
            dir_paths = set()
            for paths in idx.dir_map.values():
                dir_paths.update(paths)
    except ImportError:
        pass

    resolved: list[PeekReference] = []
    seen_keys: set[str] = set()  # deduplicate resolved references

    for cand in candidates:
        if cand.type == "T5":
            ref = _resolve_symbol(cand, doc_dir, symbol_index)
        else:
            # Build filename index on first file-reference candidate (fallback)
            if fn_index is None:
                fn_index = _build_filename_index(project_root, doc_dir)
            ref = _resolve_one(cand, doc_dir, project_root, fn_index, all_paths, dir_paths)
        if ref is None:
            continue

        # Dedup key: use text + resolved_path together.
        # Different text forms of the same file need separate entries
        # because the DOM annotator searches by text string.
        # e.g. "project.py" and "models/project.py" both resolve to
        # "src/core/models/project.py" but the annotator needs both
        # to find all occurrences in the document.
        dedup_key = f"{ref.text}:{ref.resolved_path}"

        if dedup_key not in seen_keys:
            seen_keys.add(dedup_key)
            resolved.append(ref)

    return resolved


def _resolve_one(
    cand: PeekCandidate,
    doc_dir: str,
    project_root: Path,
    fn_index: dict[str, list[str]],
    all_paths: set[str] | None = None,
    dir_paths: set[str] | None = None,
) -> PeekReference | None:
    """Try to resolve a single candidate against the filesystem.

    If ``all_paths`` is provided (from the passive ProjectIndex), uses
    set lookups instead of filesystem stat calls for existence checks.
    Falls back to ``abs_path.exists()`` if ``all_paths`` is None.

    ``dir_paths`` is an optional set of full directory relative paths
    (e.g. {"src/core/services/tool_install", ...}) for accurate
    is_directory detection in the index fast path.
    """
    path_str = cand.candidate_path.rstrip("/")
    is_dir_ref = cand.candidate_path.endswith("/")

    # Strip leading ./ if present
    if path_str.startswith("./"):
        path_str = path_str[2:]

    # Try resolution strategies in order
    for try_path in _resolution_candidates(path_str, doc_dir, fn_index, is_dir_ref):
        # Fast path: use index set lookup if available
        if all_paths is not None:
            if try_path in all_paths:
                # Determine if it's a directory from the dir_paths set
                is_dir = (dir_paths is not None and try_path in dir_paths) or try_path.endswith("/")
                return PeekReference(
                    text=cand.text,
                    type=cand.type,
                    resolved_path=try_path,
                    line_number=cand.line_number,
                    is_directory=is_dir,
                )
            continue

        # Fallback: filesystem check
        abs_path = project_root / try_path
        if abs_path.exists():
            # Safety: don't link outside project root
            try:
                abs_path.resolve().relative_to(project_root.resolve())
            except ValueError:
                continue

            return PeekReference(
                text=cand.text,
                type=cand.type,
                resolved_path=try_path,
                line_number=cand.line_number,
                is_directory=abs_path.is_dir(),
            )

    return None


def _resolution_candidates(
    path_str: str,
    doc_dir: str,
    fn_index: dict[str, list[str]],
    is_dir_ref: bool = False,
) -> list[str]:
    """Generate candidate resolved paths to try, in priority order.

    Resolution order:
        1. Same directory as the document
        2. Subdirectory search (filename index, ranked by depth proximity)
        3. Project root
        4. One level up
    """
    candidates: list[str] = []

    if "/" in path_str:
        # Path with slashes — try as project-root-relative first
        candidates.append(path_str)
        # Also try relative to doc directory
        if doc_dir:
            candidates.append(f"{doc_dir}/{path_str}")
        # Try each ancestor of doc_dir as a prefix
        # e.g. doc_dir="src/core", path="core/engine/executor.py"
        #   → try "src/core/engine/executor.py" (prefix "src/")
        # e.g. doc_dir="src/core", path="adapters/containers/docker.py"
        #   → try "src/adapters/containers/docker.py" (prefix "src/")
        if doc_dir:
            parts = Path(doc_dir).parts
            for i in range(len(parts)):
                ancestor = str(Path(*parts[:i + 1])) if i > 0 else parts[0]
                candidate = f"{ancestor}/{path_str}"
                if candidate not in candidates:
                    candidates.append(candidate)
    else:
        # Bare filename — try same directory first
        if doc_dir:
            candidates.append(f"{doc_dir}/{path_str}")

        # Then project root
        candidates.append(path_str)

        # Then one level up
        parent = str(Path(doc_dir).parent) if doc_dir else ""
        if parent and parent != "." and parent != doc_dir:
            candidates.append(f"{parent}/{path_str}")

        # Subdirectory search via filename index
        # Look up the filename (or dirname/) in the index
        lookup_key = path_str + "/" if is_dir_ref else path_str
        index_hits = fn_index.get(lookup_key, [])
        if not index_hits and is_dir_ref:
            # Also try without trailing /
            index_hits = fn_index.get(path_str, [])

        if index_hits:
            # Rank by depth proximity to doc_dir (fewest intermediate dirs wins)
            def _depth_from_doc(p: str) -> int:
                """Count how many path segments separate p from doc_dir."""
                p_dir = str(Path(p).parent) if not p.endswith("/") else p.rstrip("/")
                if doc_dir and p_dir.startswith(doc_dir):
                    remainder = p_dir[len(doc_dir):].lstrip("/")
                    return remainder.count("/") + (1 if remainder else 0)
                return 999  # outside doc subtree

            ranked = sorted(index_hits, key=_depth_from_doc)
            for hit in ranked:
                if hit not in candidates:
                    candidates.append(hit)

    return candidates



# ── Symbol resolver ──────────────────────────────────────────────────

def _resolve_symbol(
    cand: PeekCandidate,
    doc_dir: str,
    symbol_index: dict[str, list[SymbolEntry]] | None,
) -> PeekReference | None:
    """Try to resolve a T5 symbol candidate via the symbol index."""
    if not symbol_index:
        return None

    sym_name = cand.candidate_path
    entries = symbol_index.get(sym_name)
    if not entries:
        return None

    # Single match — no disambiguation needed
    if len(entries) == 1:
        e = entries[0]
        return PeekReference(
            text=cand.text,
            type="T5",
            resolved_path=e.file,
            line_number=e.line,
            is_directory=False,
        )

    # Multiple matches — score by proximity to doc_dir
    best = _disambiguate(entries, doc_dir)
    if best is None:
        return None

    return PeekReference(
        text=cand.text,
        type="T5",
        resolved_path=best.file,
        line_number=best.line,
        is_directory=False,
    )


def _disambiguate(
    entries: list[SymbolEntry],
    doc_dir: str,
) -> SymbolEntry | None:
    """Pick the best symbol match by directory proximity.

    Scoring:
        3  Same directory as the document
        2  Same parent package
        1  Any other location
        0  Skip (ambiguous with no proximity signal)
    """
    if not doc_dir:
        # No context — ambiguous, skip
        return entries[0] if len(entries) == 1 else None

    scored: list[tuple[int, SymbolEntry]] = []
    for e in entries:
        e_dir = str(Path(e.file).parent)
        if e_dir == doc_dir:
            scored.append((3, e))
        elif e_dir.startswith(doc_dir + "/") or doc_dir.startswith(e_dir + "/"):
            scored.append((2, e))
        else:
            parent = str(Path(doc_dir).parent)
            if parent != "." and (e_dir == parent or e_dir.startswith(parent + "/")):
                scored.append((2, e))
            else:
                scored.append((1, e))

    scored.sort(key=lambda x: x[0], reverse=True)

    # Only link if there's a clear winner (top score is unique)
    if len(scored) >= 2 and scored[0][0] == scored[1][0]:
        # Tied top scores — ambiguous, don't link
        return None

    return scored[0][1]


# ── Symbol index builder ─────────────────────────────────────────────

# Module-level cache for the symbol index
_symbol_index_cache: dict[str, list[SymbolEntry]] | None = None
_symbol_index_root: str | None = None


def build_symbol_index(
    project_root: Path,
    *,
    use_cache: bool = True,
    block: bool = True,
) -> dict[str, list[SymbolEntry]]:
    """Build a symbol-name → locations index from AST parser data.

    Uses the passive ProjectIndex when available (zero I/O). Falls
    back to on-demand AST parsing only if ``block=True``.

    Args:
        project_root: Absolute path to the project root.
        use_cache: If True, return the cached index if available.
        block: If False, return {} immediately when no cached data
               is available rather than spending ~23s parsing ASTs.
               HTTP request handlers should ALWAYS pass block=False.

    Returns:
        { "l0_system_profile": [SymbolEntry(...)], ... }
    """
    global _symbol_index_cache, _symbol_index_root

    root_str = str(project_root.resolve())

    # Check in-memory cache first
    if use_cache and _symbol_index_cache is not None and _symbol_index_root == root_str:
        return _symbol_index_cache

    # Check passive project index (background-built, zero I/O)
    if use_cache:
        try:
            from src.core.services.project_index import get_index, IndexSymbolEntry
            idx = get_index()
            if idx.symbols_ready and idx.symbol_map:
                # Convert IndexSymbolEntry → SymbolEntry
                converted: dict[str, list[SymbolEntry]] = {}
                for name, entries in idx.symbol_map.items():
                    converted[name] = [
                        SymbolEntry(name=e.name, file=e.file, line=e.line, kind=e.kind)
                        for e in entries
                    ]
                _symbol_index_cache = converted
                _symbol_index_root = root_str
                log.debug(
                    "[Peek] Symbol index from ProjectIndex: %d unique names",
                    len(converted),
                )
                return converted
        except ImportError:
            pass

    # Non-blocking mode: return empty rather than spending 23s parsing
    if not block:
        log.debug("[Peek] Symbol index not ready, skipping (non-blocking)")
        return {}

    # Fallback: build on-demand from AST parsers (BLOCKING — ~23s)
    try:
        from src.core.services.audit.parsers import registry
    except ImportError:
        log.warning("[Peek] AST parser not available, T5 symbols disabled")
        return {}

    index: dict[str, list[SymbolEntry]] = {}

    try:
        analyses = registry.parse_tree(project_root)
    except Exception as e:
        log.warning("[Peek] Failed to build symbol index: %s", e)
        return {}

    for rel_path, analysis in analyses.items():
        for sym in analysis.symbols:
            entry = SymbolEntry(
                name=sym.name,
                file=rel_path,
                line=sym.lineno,
                kind=sym.kind,
            )
            index.setdefault(sym.name, []).append(entry)

    _symbol_index_cache = index
    _symbol_index_root = root_str

    log.debug(
        "[Peek] Symbol index: %d unique names, %d total entries",
        len(index), sum(len(v) for v in index.values()),
    )

    return index


# ── Index-driven scanner ─────────────────────────────────────────────
#
# The regex scanner (T1-T6) is a best-effort first pass. It misses
# references inside markdown link text `[dir/](...)`, certain table
# cell formats, and edge cases the lookbehind/lookahead can't handle.
#
# The index-driven scanner flips the approach: the project index
# KNOWS every file and directory that exists. We search the content
# for any occurrence of those known names. This catches everything
# the regex misses — because the index IS the truth.

def _index_driven_scan(
    content: str,
    doc_path: str,
    project_root: Path,
    already_found: set[str],
) -> list[PeekCandidate]:
    """Scan content for known file/directory names using the project index.

    This is a second-pass scanner that finds references the regex
    scanner missed. It uses the ProjectIndex's file_map and dir_map
    to know what exists, then searches the content for those names.

    Args:
        content: Raw markdown text.
        doc_path: Relative path of the document being scanned.
        project_root: Absolute path to the project root.
        already_found: Set of text strings already found by the regex scanner.
                       Used to avoid duplicates.

    Returns:
        Additional candidates not found by the regex scanner.
    """
    try:
        from src.core.services.project_index import get_index
        idx = get_index()
        if not idx.ready:
            return []
    except ImportError:
        return []

    doc_dir = str(Path(doc_path).parent)
    if doc_dir == ".":
        doc_dir = ""

    extra: list[PeekCandidate] = []
    seen: set[str] = set(already_found)

    # ── Directory references: search for "name/" ──
    # Only check directory names that actually exist as children
    # of the document's directory (or project root).
    for dir_name, dir_paths in idx.dir_map.items():
        # dir_map stores with and without trailing /; only use the
        # trailing-/ variant to avoid double-processing.
        if not dir_name.endswith("/"):
            continue

        search_text = dir_name  # e.g. "k8s/"

        if search_text in seen:
            continue

        # Match if this directory exists anywhere within the doc's subtree
        # (the resolver handles proximity-based disambiguation)
        has_local = False
        for dp in dir_paths:
            if doc_dir and dp.startswith(doc_dir + "/"):
                has_local = True
                break
            elif not doc_dir:
                has_local = True
                break

        if not has_local:
            continue

        # Search for this directory name in the content
        if search_text in content:
            seen.add(search_text)
            extra.append(PeekCandidate(
                text=search_text,
                type="T2",
                candidate_path=search_text,
                line_number=None,
                in_code_fence=False,
            ))

    # ── File references: search for known filenames ──
    # Only check files in the same directory as the document.
    for filename, file_paths in idx.file_map.items():
        if filename in seen:
            continue

        # Must have a known extension
        if not _has_known_ext(filename):
            continue

        # Must exist in the same directory subtree
        has_local = False
        for fp in file_paths:
            if doc_dir and fp.startswith(doc_dir):
                has_local = True
                break
            elif not doc_dir:
                has_local = True
                break

        if not has_local:
            continue

        # Search in content — check for word-boundary-ish match
        # (preceded by space, backtick, pipe, bracket, or start of line)
        if filename in content:
            seen.add(filename)
            extra.append(PeekCandidate(
                text=filename,
                type="T6",
                candidate_path=filename,
                line_number=None,
                in_code_fence=False,
            ))

    return extra


# ── Public API ───────────────────────────────────────────────────────

def scan_and_resolve(
    content: str,
    doc_path: str,
    project_root: Path,
    symbol_index: dict[str, list[SymbolEntry]] | None = None,
) -> list[PeekReference]:
    """Scan markdown content for file and symbol references and resolve them.

    This is the main entry point. Combines scanning and resolution
    into a single call.

    Args:
        content: Raw markdown text.
        doc_path: Relative path of the document being scanned.
        project_root: Absolute path to the project root.
        symbol_index: Optional symbol index for T5 resolution.
                      If None and T5 candidates exist, they are skipped.
                      Use build_symbol_index() to create one.

    Returns:
        List of validated references pointing to real files/directories.
    """
    candidates = scan_peek_candidates(content, doc_path)

    # Second pass: index-driven scan catches what regex missed
    already_found = {c.text for c in candidates}
    extra = _index_driven_scan(content, doc_path, project_root, already_found)
    candidates.extend(extra)

    return resolve_peek_candidates(candidates, doc_path, project_root, symbol_index)


def scan_and_resolve_all(
    content: str,
    doc_path: str,
    project_root: Path,
    symbol_index: dict[str, list[SymbolEntry]] | None = None,
) -> tuple[list[PeekReference], list[PeekReference], list[PeekReference]]:
    """Scan and resolve, returning resolved, unresolved, AND pending references.

    Uses both regex-based scanner (T1-T6) and index-driven scanner
    for comprehensive reference detection.

    Args:
        content: Raw markdown text.
        doc_path: Relative path of the document being scanned.
        project_root: Absolute path to the project root.
        symbol_index: Optional symbol index for T5 resolution.

    Returns:
        Tuple of (resolved, unresolved, pending).
        - resolved: refs with valid resolved_path
        - unresolved: refs that were looked up and NOT found
        - pending: T5 refs that couldn't be checked because
          the symbol index isn't ready yet
    """
    candidates = scan_peek_candidates(content, doc_path)

    # Second pass: index-driven scan catches what regex missed
    already_found = {c.text for c in candidates}
    extra = _index_driven_scan(content, doc_path, project_root, already_found)
    candidates.extend(extra)

    resolved = resolve_peek_candidates(candidates, doc_path, project_root, symbol_index)

    # Find unresolved: candidates whose text has no corresponding resolved ref
    resolved_texts = {r.text for r in resolved}
    unresolved: list[PeekReference] = []
    pending: list[PeekReference] = []
    seen_unresolved: set[str] = set()

    for cand in candidates:
        if cand.text in resolved_texts:
            continue
        if cand.text in seen_unresolved:
            continue
        if cand.type == "T5":
            if symbol_index is None:
                # Symbol index not ready — mark as pending (will resolve later)
                seen_unresolved.add(cand.text)
                pending.append(PeekReference(
                    text=cand.text,
                    type=cand.type,
                    resolved_path="",
                    line_number=cand.line_number,
                    is_directory=False,
                ))
            # When symbol_index exists but symbol not found → drop silently
            # (it's genuinely not a project symbol, not peekable)
            continue
        seen_unresolved.add(cand.text)
        unresolved.append(PeekReference(
            text=cand.text,
            type=cand.type,
            resolved_path="",
            line_number=cand.line_number,
            is_directory=False,
        ))

    return resolved, unresolved, pending
