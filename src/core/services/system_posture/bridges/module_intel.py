"""
Module stack intelligence — deep analysis of module runtime compatibility.

Provides:
  - Dependency floor: highest runtime constraint among a module's dependencies
  - Code floor: highest language feature version used in module source files
  - Consistency verdict: compares declared, deps, code floors

These complement the declared floor from detection.py to give the full
picture of a module's real compatibility.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════
# DEPENDENCY FLOOR — what do the module's dependencies require?
# ══════════════════════════════════════════════════════════════════


def compute_dependency_floor(
    project_root: Path,
    module_path: str,
    language: str | None,
) -> tuple[str | None, list[dict]]:
    """Compute the effective runtime floor from a module's actual dependencies.

    Two steps:
    1. Scan the module's .py files for import statements to find which
       packages the module actually uses (not the whole venv).
    2. For each used package, read its Requires-Python from .dist-info/METADATA.
    3. Return the highest minimum — that's the real floor imposed by deps.

    Args:
        project_root: Project root path.
        module_path: Relative path to the module.
        language: Module language (python, javascript, etc.)

    Returns:
        (floor_version, details):
        - floor_version: highest min among module's actual deps (e.g. "3.9")
        - details: list of {package, requires_python, floor} for deps with constraints
    """
    if language != "python":
        return None, []

    module_dir = project_root / module_path
    if not module_dir.is_dir():
        return None, []

    # Find the venv's site-packages
    site_packages = _find_site_packages(project_root)
    if not site_packages:
        return None, []

    # Step 1: Find which packages this module actually imports
    module_imports = _scan_module_imports(module_dir)
    if not module_imports:
        return None, []

    # Step 2: Build import-name → package-name mapping from dist-info
    import_to_pkg = _build_import_mapping(site_packages)

    # Step 3: Map module's imports to package names
    module_packages: set[str] = set()
    for imp in module_imports:
        # Try direct mapping first
        if imp in import_to_pkg:
            module_packages.add(import_to_pkg[imp])
        else:
            # Fall back: import name = package name (common case)
            module_packages.add(imp)

    # Step 4: Look up Requires-Python for each package
    all_constraints = _scan_dist_info_requires_python(site_packages)

    highest_floor: str | None = None
    highest_parts: list[int] = []
    details: list[dict] = []

    for pkg_name in module_packages:
        # Normalize for lookup
        pkg_normalized = pkg_name.lower().replace("_", "-")
        requires_python = all_constraints.get(pkg_normalized)
        if not requires_python:
            continue

        floor = _parse_requires_python_floor(requires_python)
        if not floor:
            continue

        details.append({
            "package": pkg_normalized,
            "requires_python": requires_python,
            "floor": floor,
        })

        try:
            parts = [int(x) for x in floor.split(".")]
        except ValueError:
            continue

        if not highest_parts or parts > highest_parts:
            highest_parts = parts
            highest_floor = floor

    return highest_floor, details


def _scan_module_imports(module_dir: Path) -> set[str]:
    """Scan .py files in a module directory for import statements.

    Returns the set of top-level import names (e.g. {"flask", "click", "yaml"}).
    Only returns third-party imports — filters out stdlib and relative imports.
    """
    imports: set[str] = set()

    # Common stdlib modules to exclude (not exhaustive, but covers the big ones)
    _STDLIB = {
        "os", "sys", "re", "json", "pathlib", "typing", "dataclasses",
        "collections", "functools", "itertools", "operator", "abc",
        "datetime", "time", "math", "random", "hashlib", "hmac",
        "base64", "uuid", "enum", "copy", "io", "string", "textwrap",
        "logging", "warnings", "traceback", "inspect", "importlib",
        "contextlib", "concurrent", "threading", "multiprocessing",
        "subprocess", "shutil", "tempfile", "glob", "fnmatch",
        "socket", "http", "urllib", "email", "html", "xml",
        "csv", "configparser", "argparse", "getpass", "platform",
        "struct", "ctypes", "unittest", "doctest", "pdb",
        "ast", "dis", "code", "codeop", "compileall",
        "sqlite3", "dbm", "shelve", "marshal", "pickle",
        "gzip", "bz2", "lzma", "zipfile", "tarfile",
        "signal", "mmap", "select", "selectors", "stat",
        "posixpath", "ntpath", "genericpath", "linecache",
        "tokenize", "token", "keyword", "pprint", "difflib",
        "secrets", "webbrowser", "types", "weakref", "array",
        "queue", "heapq", "bisect", "decimal", "fractions",
        "statistics", "numbers", "sysconfig", "site",
        "__future__", "builtins", "_thread", "atexit",
        "mimetypes", "shlex", "locale", "gettext", "codecs",
        "unicodedata", "textwrap", "html", "xml", "http",
        "urllib", "email", "mailbox", "mmap", "fileinput",
        "rlcompleter", "readline", "curses", "resource",
        "grp", "pwd", "crypt", "tty", "pty", "pipes",
        "formatter", "chunk", "colorsys", "imghdr", "sndhdr",
    }

    import_re = re.compile(
        r"^(?:import\s+(\w+)|from\s+(\w+)(?:\.\w+)*\s+import)",
        re.MULTILINE,
    )

    for py_file in module_dir.rglob("*.py"):
        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        for match in import_re.finditer(content):
            name = match.group(1) or match.group(2)
            if not name:
                continue
            # Skip stdlib, relative imports (start with .), and src-internal
            if name in _STDLIB:
                continue
            if name.startswith("_"):
                continue
            if name == "src":
                continue
            imports.add(name)

    return imports


def _build_import_mapping(site_packages: Path) -> dict[str, str]:
    """Build mapping from import name → package name using dist-info.

    Reads top_level.txt first (lists import names). If that doesn't exist
    (modern packages may not have it), falls back to the package directory
    name itself.

    Returns: {"yaml": "pyyaml", "PIL": "pillow", "flask": "flask", ...}
    """
    mapping: dict[str, str] = {}

    for dist_info in site_packages.glob("*.dist-info"):
        pkg_name = _dist_info_to_pkg_name(dist_info.name)
        found_top_level = False

        # Try top_level.txt first — most reliable
        top_level = dist_info / "top_level.txt"
        if top_level.is_file():
            try:
                for line in top_level.read_text(encoding="utf-8").splitlines():
                    import_name = line.strip()
                    if import_name:
                        mapping[import_name] = pkg_name
                        found_top_level = True
            except OSError:
                pass

        if not found_top_level:
            # Fall back: check if a directory with the package name exists
            # in site-packages (the actual importable package)
            # For most packages: flask → flask/, click → click/, pydantic → pydantic/
            simple = pkg_name.replace("-", "_")
            if (site_packages / simple).is_dir() or (site_packages / (simple + ".py")).is_file():
                mapping[simple] = pkg_name
            # Also try the raw package name
            if (site_packages / pkg_name.replace("-", "_")).is_dir():
                mapping[pkg_name.replace("-", "_")] = pkg_name

    return mapping


def _find_site_packages(project_root: Path) -> Path | None:
    """Find the active venv's site-packages directory."""
    # Check common venv locations
    candidates = [
        project_root / ".venv" / "lib",
        project_root / ".venv-ft" / "lib",
        project_root / "venv" / "lib",
    ]

    for venv_lib in candidates:
        if not venv_lib.is_dir():
            continue
        # Find python3.X directory inside lib/
        for child in venv_lib.iterdir():
            if child.name.startswith("python3") and child.is_dir():
                sp = child / "site-packages"
                if sp.is_dir():
                    return sp
    return None


def _scan_dist_info_requires_python(site_packages: Path) -> dict[str, str]:
    """Scan all .dist-info directories for Requires-Python headers.

    Returns: {package_name: requires_python_constraint}
    """
    results: dict[str, str] = {}

    for dist_info in site_packages.glob("*.dist-info"):
        metadata_file = dist_info / "METADATA"
        if not metadata_file.is_file():
            continue

        pkg_name = _dist_info_to_pkg_name(dist_info.name)

        try:
            # Read only headers (before first blank line)
            text = metadata_file.read_text(encoding="utf-8", errors="replace")
            for line in text.splitlines():
                if not line.strip():
                    break  # end of headers
                if line.lower().startswith("requires-python:"):
                    value = line.split(":", 1)[1].strip()
                    if value:
                        results[pkg_name] = value
                    break
        except OSError:
            continue

    return results


def _dist_info_to_pkg_name(dirname: str) -> str:
    """Extract normalized package name from a .dist-info directory name.

    'flask-3.1.3.dist-info' → 'flask'
    'pydantic_core-2.12.5.dist-info' → 'pydantic-core'
    'PyYAML-6.0.3.dist-info' → 'pyyaml'
    """
    # Strip .dist-info suffix
    name = dirname
    if name.endswith(".dist-info"):
        name = name[: -len(".dist-info")]

    # Split on '-' but version starts with a digit
    # Find the first '-' followed by a digit
    parts = name.split("-")
    pkg_parts = []
    for i, part in enumerate(parts):
        if i > 0 and part and part[0].isdigit():
            break
        pkg_parts.append(part)

    return "-".join(pkg_parts).replace("_", "-").lower()


def _parse_requires_python_floor(constraint: str) -> str | None:
    """Extract floor version from a Requires-Python constraint.

    Handles: ">=3.8", ">=3.8,<4", ">=3.9.0", "~=3.8", etc.
    """
    match = re.search(r">=\s*(\d+(?:\.\d+)*)", constraint)
    if match:
        return match.group(1)
    match = re.search(r"~=\s*(\d+(?:\.\d+)*)", constraint)
    if match:
        return match.group(1)
    return None


# ══════════════════════════════════════════════════════════════════
# CODE FLOOR — what language features does the module's code use?
# ══════════════════════════════════════════════════════════════════

# Python version features, split into two categories:
#
# RUNTIME features: always count regardless of __future__ annotations.
# These are syntax constructs that execute at runtime.
#
# ANNOTATION features: only count if __future__ annotations is NOT present.
# With the import, these are deferred strings and work on 3.7+.
# Without the import, they require their version at runtime.

_RUNTIME_FEATURES: list[tuple[str, str, str]] = [
    # (version, feature_name, regex_pattern)
    # These always require their version — can't be deferred by __future__
    ("3.12", "type statement", r"^\s*type\s+\w+\s*[\[=]"),
    ("3.11", "except* (exception groups)", r"\bexcept\s*\*"),
    ("3.10", "match/case", r"^\s*match\s+\w+.*:\s*$"),
    ("3.8", "walrus operator :=", r"(?<!['\"])\b\w+\s*:=\s"),
    ("3.8", "positional-only /", r"def\s+\w+\([^)]*,\s*/\s*[,)]"),
    ("3.6", "f-strings", r"""f['\"]"""),
]

_ANNOTATION_FEATURES: list[tuple[str, str, str]] = [
    # These only count WITHOUT __future__ annotations.
    # With __future__, annotations are strings → work on 3.7+.
    ("3.10", "union type X | Y (runtime)", r":\s*\w+\s*\|\s*\w+"),
    ("3.9", "builtin generics (runtime)", r"\b(?:list|dict|set|tuple|frozenset)\["),
]

_FUTURE_IMPORT_RE = re.compile(
    r"^from\s+__future__\s+import\s+annotations", re.MULTILINE,
)


def compute_code_floor(
    project_root: Path,
    module_path: str,
    language: str | None,
) -> tuple[str | None, list[dict]]:
    """Detect the minimum Python version required by the module's code.

    Scans .py files for version-specific language features, accounting
    for `from __future__ import annotations` which defers annotation
    evaluation and allows 3.9/3.10 type hint syntax on 3.7+.

    Features are split into:
    - RUNTIME: always count (match/case, walrus, except*, etc.)
    - ANNOTATION: only count WITHOUT __future__ annotations

    Args:
        project_root: Project root path.
        module_path: Relative path to module.
        language: Module language.

    Returns:
        (floor_version, features):
        - floor_version: highest feature version (e.g. "3.10")
        - features: list of {version, feature, file, line} for each detection
    """
    if language != "python":
        return None, []

    module_dir = project_root / module_path
    if not module_dir.is_dir():
        return None, []

    features_found: list[dict] = []
    highest_version: str | None = None
    highest_parts: list[int] = []

    # Compile patterns once
    runtime_compiled = [
        (ver, name, re.compile(pattern, re.MULTILINE))
        for ver, name, pattern in _RUNTIME_FEATURES
    ]
    annotation_compiled = [
        (ver, name, re.compile(pattern, re.MULTILINE))
        for ver, name, pattern in _ANNOTATION_FEATURES
    ]

    py_files = list(module_dir.rglob("*.py"))

    def _update_highest(ver: str) -> None:
        nonlocal highest_version, highest_parts
        try:
            parts = [int(x) for x in ver.split(".")]
        except ValueError:
            return
        if not highest_parts or parts > highest_parts:
            highest_parts = parts
            highest_version = ver

    for py_file in py_files[:500]:
        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        rel_path = str(py_file.relative_to(project_root))
        has_future = bool(_FUTURE_IMPORT_RE.search(content))

        # Always check runtime features
        for ver, name, pattern in runtime_compiled:
            matches = list(pattern.finditer(content))
            if matches:
                line_no = content[:matches[0].start()].count("\n") + 1
                features_found.append({
                    "version": ver,
                    "feature": name,
                    "file": rel_path,
                    "line": line_no,
                })
                _update_highest(ver)
                break  # one runtime feature per file is enough

        # Check annotation features ONLY if __future__ is NOT present
        if not has_future:
            for ver, name, pattern in annotation_compiled:
                matches = list(pattern.finditer(content))
                if matches:
                    line_no = content[:matches[0].start()].count("\n") + 1
                    features_found.append({
                        "version": ver,
                        "feature": name,
                        "file": rel_path,
                        "line": line_no,
                    })
                    _update_highest(ver)
                    break

        # If file HAS __future__, record it as 3.7+ baseline
        if has_future and not highest_parts:
            _update_highest("3.7")

    # Deduplicate: keep one example per feature
    seen_features: set[str] = set()
    unique_features: list[dict] = []
    for f in features_found:
        key = f"{f['version']}:{f['feature']}"
        if key not in seen_features:
            seen_features.add(key)
            unique_features.append(f)

    # Sort by version descending
    unique_features.sort(key=lambda f: f["version"], reverse=True)

    return highest_version, unique_features


# ══════════════════════════════════════════════════════════════════
# CONSISTENCY VERDICT — compare all three floors
# ══════════════════════════════════════════════════════════════════


def compute_verdict(
    declared_floor: str | None,
    deps_floor: str | None,
    code_floor: str | None,
    floor_source: str | None = None,
) -> tuple[str, str]:
    """Compare declared, dependency, and code floors.

    Args:
        declared_floor: from 3-tier detection
        deps_floor: from dependency analysis
        code_floor: from code feature analysis
        floor_source: "module" | "stack" | "project" — affects wording

    Returns (verdict, explanation):
      verdict: "consistent" | "gap" | "could_lower" | "unknown"
      explanation: human-readable detail
    """
    if not declared_floor:
        return "unknown", "No declared floor"

    declared = _ver_tuple(declared_floor)
    if not declared:
        return "unknown", "Cannot parse declared floor"

    # Label for the declared source in explanations
    source_label = {
        "stack": "stack baseline",
        "project": "project config",
        "module": "module config",
    }.get(floor_source or "", "declared")

    # Collect all floors
    floors = [("declared", declared_floor, declared)]
    if deps_floor:
        deps = _ver_tuple(deps_floor)
        if deps:
            floors.append(("deps", deps_floor, deps))
    if code_floor:
        code = _ver_tuple(code_floor)
        if code:
            floors.append(("code", code_floor, code))

    # Check for gaps — deps higher than declared
    if deps_floor:
        deps = _ver_tuple(deps_floor)
        if deps and declared < deps:
            return (
                "gap",
                f"{source_label} is {declared_floor} but deps need ≥{deps_floor}",
            )

    # Check for gaps — code higher than declared
    if code_floor:
        code = _ver_tuple(code_floor)
        if code and declared < code:
            return (
                "gap",
                f"{source_label} is {declared_floor} but code uses {code_floor}+ features",
            )

    # Check if declared is higher than needed
    if len(floors) > 1:
        other_max = max(
            (f for f in floors if f[0] != "declared"),
            key=lambda x: x[2],
        )
        if declared > other_max[2]:
            return (
                "could_lower",
                f"{source_label} is {declared_floor} but nothing needs more than {other_max[1]}",
            )

    return "consistent", "all layers aligned"


def compute_effective_floor(
    declared_floor: str | None,
    deps_floor: str | None,
    code_floor: str | None,
) -> str | None:
    """Return the highest of all three floors — the real minimum."""
    floors: list[tuple[list[int], str]] = []

    for f in [declared_floor, deps_floor, code_floor]:
        if f:
            parts = _ver_tuple(f)
            if parts:
                floors.append((parts, f))

    if not floors:
        return None

    return max(floors, key=lambda x: x[0])[1]


def _ver_tuple(v: str) -> list[int] | None:
    """Parse version string to comparable tuple."""
    try:
        return [int(x) for x in v.split(".")]
    except (ValueError, AttributeError):
        return None


# ══════════════════════════════════════════════════════════════════
# DATE UTILITIES — for deferrals and version plans
# ══════════════════════════════════════════════════════════════════


def _parse_decision_date(date_str: str) -> "date | None":
    """Parse a decision date string into a date object.

    Handles:
      "2026-09-01"  → date(2026, 9, 1)
      "2026-09"     → date(2026, 9, 30)  (end of month)
      "Q1 2026"     → date(2026, 3, 31)  (end of Q1)
      "Q2 2026"     → date(2026, 6, 30)
      "Q3 2026"     → date(2026, 9, 30)
      "Q4 2026"     → date(2026, 12, 31)
    """
    from datetime import date as _date

    if not date_str:
        return None

    s = date_str.strip()

    # Quarter format: "Q3 2026"
    quarter_match = re.match(r"Q(\d)\s+(\d{4})", s, re.IGNORECASE)
    if quarter_match:
        q = int(quarter_match.group(1))
        year = int(quarter_match.group(2))
        quarter_ends = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}
        if q in quarter_ends:
            month, day = quarter_ends[q]
            return _date(year, month, day)
        return None

    # ISO date: "2026-09-01"
    try:
        parts = s.split("-")
        if len(parts) == 3:
            return _date(int(parts[0]), int(parts[1]), int(parts[2]))
        if len(parts) == 2:
            # "2026-09" → end of month
            year, month = int(parts[0]), int(parts[1])
            if month == 12:
                return _date(year, 12, 31)
            return _date(year, month + 1, 1) - __import__("datetime").timedelta(days=1)
    except (ValueError, IndexError):
        pass

    return None


def is_deferral_expired(until_str: str) -> bool:
    """Check if a deferral date has passed."""
    from datetime import date as _date

    target = _parse_decision_date(until_str)
    if target is None:
        return False  # can't parse → treat as not expired
    return _date.today() > target


def is_plan_overdue(date_str: str) -> bool:
    """Check if a plan target date has passed."""
    from datetime import date as _date

    target = _parse_decision_date(date_str)
    if target is None:
        return False
    return _date.today() > target


def is_plan_met(target_floor: str, effective_floor: str) -> bool:
    """Check if the effective floor meets or exceeds the plan target."""
    if not target_floor or not effective_floor:
        return False
    target = _ver_tuple(target_floor)
    effective = _ver_tuple(effective_floor)
    if not target or not effective:
        return False
    return effective >= target
