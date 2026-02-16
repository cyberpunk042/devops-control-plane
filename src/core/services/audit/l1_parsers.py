"""
L1 — Dependency manifest parsers.

Pure functions that extract dependency names + versions from
manifest files across ecosystems (Python, Node, Go, Rust, Ruby, Elixir).

Extracted from l1_classification.py.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


# ══════════════════════════════════════════════════════════════════
#  Manifest parsers — extract dependency names + versions
# ══════════════════════════════════════════════════════════════════


def _parse_requirements_txt(path: Path) -> list[dict]:
    """Parse requirements.txt → list of {name, version, dev}."""
    deps: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            # Handle: package==1.0, package>=1.0, package~=1.0, package
            match = re.match(r"^([a-zA-Z0-9_.-]+)\s*([<>=!~]+\s*\S+)?", line)
            if match:
                name = match.group(1).strip()
                version = (match.group(2) or "").strip()
                deps.append({"name": name, "version": version, "dev": False})
    except (OSError, UnicodeDecodeError):
        pass
    return deps


def _parse_pyproject_toml(path: Path) -> list[dict]:
    """Parse pyproject.toml → list of {name, version, dev}."""
    deps: list[dict] = []
    try:
        import tomllib  # Python 3.11+
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError:
            # Fallback: regex-based extraction
            return _parse_pyproject_toml_regex(path)

    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _parse_pyproject_toml_regex(path)

    # [project.dependencies]
    for dep_str in data.get("project", {}).get("dependencies", []):
        match = re.match(r"^([a-zA-Z0-9_.-]+)", dep_str)
        if match:
            name = match.group(1)
            version = dep_str[len(name):].strip()
            deps.append({"name": name, "version": version, "dev": False})

    # [project.optional-dependencies] — treat as dev
    for group_deps in data.get("project", {}).get("optional-dependencies", {}).values():
        for dep_str in group_deps:
            match = re.match(r"^([a-zA-Z0-9_.-]+)", dep_str)
            if match:
                name = match.group(1)
                version = dep_str[len(name):].strip()
                deps.append({"name": name, "version": version, "dev": True})

    # [tool.poetry.dependencies] and [tool.poetry.dev-dependencies]
    poetry = data.get("tool", {}).get("poetry", {})
    for name, spec in poetry.get("dependencies", {}).items():
        if name.lower() == "python":
            continue
        version = spec if isinstance(spec, str) else str(spec)
        deps.append({"name": name, "version": version, "dev": False})
    for name, spec in poetry.get("dev-dependencies", {}).items():
        version = spec if isinstance(spec, str) else str(spec)
        deps.append({"name": name, "version": version, "dev": True})

    return deps


def _parse_pyproject_toml_regex(path: Path) -> list[dict]:
    """Fallback: regex-based pyproject.toml parsing."""
    deps: list[dict] = []
    try:
        content = path.read_text(encoding="utf-8")
        # Find lines like "  flask >= 3.0,"  within dependency arrays
        in_deps = False
        for line in content.splitlines():
            stripped = line.strip()
            if "dependencies" in stripped and ("=" in stripped or "[" in stripped):
                in_deps = True
                continue
            if in_deps:
                if stripped.startswith("]"):
                    in_deps = False
                    continue
                # Extract quoted dep string
                match = re.match(r'^\s*"([a-zA-Z0-9_.-]+)', stripped)
                if match:
                    deps.append({"name": match.group(1), "version": "", "dev": False})
    except (OSError, UnicodeDecodeError):
        pass
    return deps


def _parse_package_json(path: Path) -> list[dict]:
    """Parse package.json → list of {name, version, dev}."""
    deps: list[dict] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return deps

    for name, version in data.get("dependencies", {}).items():
        deps.append({"name": name, "version": version, "dev": False})
    for name, version in data.get("devDependencies", {}).items():
        deps.append({"name": name, "version": version, "dev": True})
    for name, version in data.get("peerDependencies", {}).items():
        deps.append({"name": name, "version": version, "dev": False})

    return deps


def _parse_go_mod(path: Path) -> list[dict]:
    """Parse go.mod → list of {name, version, dev}."""
    deps: list[dict] = []
    try:
        content = path.read_text(encoding="utf-8")
        in_require = False
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("require ("):
                in_require = True
                continue
            if stripped == ")":
                in_require = False
                continue
            if in_require or stripped.startswith("require "):
                # "github.com/foo/bar v1.2.3"
                parts = stripped.replace("require ", "").strip().split()
                if len(parts) >= 2:
                    deps.append({"name": parts[0], "version": parts[1], "dev": False})
    except (OSError, UnicodeDecodeError):
        pass
    return deps


def _parse_cargo_toml(path: Path) -> list[dict]:
    """Parse Cargo.toml → list of {name, version, dev}."""
    deps: list[dict] = []
    try:
        content = path.read_text(encoding="utf-8")
        section = ""
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("["):
                section = stripped.strip("[]").strip()
                continue
            if section in ("dependencies", "dev-dependencies", "build-dependencies"):
                dev = section != "dependencies"
                # name = "version" or name = { version = "...", ... }
                match = re.match(r'^([a-zA-Z0-9_-]+)\s*=\s*"([^"]*)"', stripped)
                if match:
                    deps.append({"name": match.group(1), "version": match.group(2), "dev": dev})
                elif "=" in stripped:
                    name = stripped.split("=")[0].strip()
                    if name and not name.startswith("#"):
                        # Complex spec — extract version if present
                        ver_match = re.search(r'version\s*=\s*"([^"]*)"', stripped)
                        version = ver_match.group(1) if ver_match else ""
                        deps.append({"name": name, "version": version, "dev": dev})
    except (OSError, UnicodeDecodeError):
        pass
    return deps


def _parse_gemfile(path: Path) -> list[dict]:
    """Parse Gemfile → list of {name, version, dev}."""
    deps: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or not stripped:
                continue
            # gem 'name', '~> 1.0'
            match = re.match(r"""gem\s+['"]([^'"]+)['"](?:\s*,\s*['"]([^'"]+))?""", stripped)
            if match:
                deps.append({
                    "name": match.group(1),
                    "version": match.group(2) or "",
                    "dev": ":development" in stripped or ":test" in stripped,
                })
    except (OSError, UnicodeDecodeError):
        pass
    return deps


def _parse_mix_exs(path: Path) -> list[dict]:
    """Parse mix.exs → list of {name, version, dev}."""
    deps: list[dict] = []
    try:
        content = path.read_text(encoding="utf-8")
        # {:name, "~> 1.0"} or {:name, "~> 1.0", only: :test}
        for match in re.finditer(r'\{:(\w+),\s*\"([^\"]*?)\"', content):
            deps.append({
                "name": match.group(1),
                "version": match.group(2),
                "dev": "only:" in content[match.end():match.end() + 30],
            })
    except (OSError, UnicodeDecodeError):
        pass
    return deps


# Routing table: file → parser
PARSERS: dict[str, callable] = {
    "requirements.txt": _parse_requirements_txt,
    "requirements-dev.txt": lambda p: [
        {**d, "dev": True} for d in _parse_requirements_txt(p)
    ],
    "pyproject.toml": _parse_pyproject_toml,
    "package.json": _parse_package_json,
    "go.mod": _parse_go_mod,
    "Cargo.toml": _parse_cargo_toml,
    "Gemfile": _parse_gemfile,
    "mix.exs": _parse_mix_exs,
}
