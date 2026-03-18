"""
Per-language dependency file parsers.

Each function reads the module's dependency file and returns a list of
package names. These are the packages the module actually depends on —
the input to registry queries.

Parsers:
  - Node: package.json (dependencies + devDependencies)
  - Go: go.mod (require blocks)
  - Rust: Cargo.toml ([dependencies] + [dev-dependencies])
  - Ruby: Gemfile (gem entries)
  - PHP: composer.json (require)
  - Elixir: mix.exs (deps function)
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════
# NODE.JS — package.json
# ══════════════════════════════════════════════════════════════════


def scan_npm_deps(module_dir: Path) -> list[str]:
    """Parse package.json for dependency names.

    Reads both dependencies and devDependencies.
    Returns normalized package names (including scoped @scope/pkg).
    """
    pkg_json = module_dir / "package.json"
    if not pkg_json.is_file():
        return []

    try:
        data = json.loads(pkg_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.debug("Failed to parse package.json: %s", exc)
        return []

    deps: list[str] = []
    for key in ("dependencies", "devDependencies", "peerDependencies"):
        section = data.get(key, {})
        if isinstance(section, dict):
            deps.extend(section.keys())

    return sorted(set(deps))


# ══════════════════════════════════════════════════════════════════
# GO — go.mod
# ══════════════════════════════════════════════════════════════════


def scan_go_deps(module_dir: Path) -> list[str]:
    """Parse go.mod for required module paths.

    Returns module paths (e.g. "github.com/gin-gonic/gin").
    Extracts the last path segment as the package name for display.
    """
    go_mod = module_dir / "go.mod"
    if not go_mod.is_file():
        return []

    try:
        content = go_mod.read_text(encoding="utf-8")
    except OSError as exc:
        logger.debug("Failed to read go.mod: %s", exc)
        return []

    deps: list[str] = []

    # Match require blocks: require ( ... )
    block_re = re.compile(r"require\s*\((.*?)\)", re.DOTALL)
    for block_match in block_re.finditer(content):
        block = block_match.group(1)
        for line in block.splitlines():
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            # Each line: module/path v1.2.3
            parts = line.split()
            if parts:
                deps.append(parts[0])

    # Match single-line require: require module/path v1.2.3
    single_re = re.compile(r"^require\s+(\S+)\s+", re.MULTILINE)
    for m in single_re.finditer(content):
        deps.append(m.group(1))

    # Filter out stdlib / indirect
    deps = [d for d in deps if "/" in d]  # Go modules always have a path

    return sorted(set(deps))


# ══════════════════════════════════════════════════════════════════
# RUST — Cargo.toml
# ══════════════════════════════════════════════════════════════════


def scan_rust_deps(module_dir: Path) -> list[str]:
    """Parse Cargo.toml for crate dependency names.

    Reads [dependencies], [dev-dependencies], and [build-dependencies].
    Simple TOML parsing — handles inline tables and key-only entries.
    """
    cargo_toml = module_dir / "Cargo.toml"
    if not cargo_toml.is_file():
        return []

    try:
        content = cargo_toml.read_text(encoding="utf-8")
    except OSError as exc:
        logger.debug("Failed to read Cargo.toml: %s", exc)
        return []

    deps: list[str] = []
    in_deps_section = False
    deps_sections = {"[dependencies]", "[dev-dependencies]", "[build-dependencies]"}

    for line in content.splitlines():
        stripped = line.strip()

        # Track section headers
        if stripped.startswith("["):
            section = stripped.split("]")[0] + "]" if "]" in stripped else ""
            # Check if it's a deps section (including [dependencies.foo] for inline tables)
            in_deps_section = any(
                section == s or section.startswith(s.rstrip("]") + ".")
                for s in deps_sections
            )
            # If it's [dependencies.cratename], extract the crate name
            for prefix in deps_sections:
                dotprefix = prefix.rstrip("]") + "."
                if section.startswith(dotprefix):
                    crate = section[len(dotprefix):].rstrip("]")
                    if crate:
                        deps.append(crate)
            continue

        if not in_deps_section:
            continue

        # Skip comments and empty lines
        if not stripped or stripped.startswith("#"):
            continue

        # Parse: crate_name = "version" or crate_name = { version = "..." }
        if "=" in stripped:
            key = stripped.split("=")[0].strip()
            if key and not key.startswith("["):
                deps.append(key)

    return sorted(set(deps))


# ══════════════════════════════════════════════════════════════════
# RUBY — Gemfile
# ══════════════════════════════════════════════════════════════════


def scan_ruby_deps(module_dir: Path) -> list[str]:
    """Parse Gemfile for gem dependency names.

    Extracts gem names from `gem 'name'` declarations.
    Skips source, group, and platform directives.
    """
    gemfile = module_dir / "Gemfile"
    if not gemfile.is_file():
        return []

    try:
        content = gemfile.read_text(encoding="utf-8")
    except OSError as exc:
        logger.debug("Failed to read Gemfile: %s", exc)
        return []

    deps: list[str] = []
    gem_re = re.compile(r"""^\s*gem\s+['"]([^'"]+)['"]""", re.MULTILINE)

    for m in gem_re.finditer(content):
        deps.append(m.group(1))

    return sorted(set(deps))


# ══════════════════════════════════════════════════════════════════
# PHP — composer.json
# ══════════════════════════════════════════════════════════════════


def scan_php_deps(module_dir: Path) -> list[str]:
    """Parse composer.json for package dependency names.

    Reads the require section. Filters out php, ext-*, and lib-* entries.
    Returns vendor/package names (e.g. "laravel/framework").
    """
    composer_json = module_dir / "composer.json"
    if not composer_json.is_file():
        return []

    try:
        data = json.loads(composer_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.debug("Failed to parse composer.json: %s", exc)
        return []

    deps: list[str] = []
    for key in ("require", "require-dev"):
        section = data.get(key, {})
        if isinstance(section, dict):
            for pkg in section:
                # Filter out PHP itself, extensions, and lib constraints
                if pkg == "php" or pkg.startswith("ext-") or pkg.startswith("lib-"):
                    continue
                deps.append(pkg)

    return sorted(set(deps))


# ══════════════════════════════════════════════════════════════════
# ELIXIR — mix.exs
# ══════════════════════════════════════════════════════════════════


def scan_elixir_deps(module_dir: Path) -> list[str]:
    """Parse mix.exs for dependency names.

    Extracts atom names from the deps function.
    Pattern: {:dep_name, "~> X.Y"} or {:dep_name, ">= X.Y"}
    """
    mix_exs = module_dir / "mix.exs"
    if not mix_exs.is_file():
        return []

    try:
        content = mix_exs.read_text(encoding="utf-8")
    except OSError as exc:
        logger.debug("Failed to read mix.exs: %s", exc)
        return []

    deps: list[str] = []
    # Match {:name, ...} patterns in deps-like contexts
    dep_re = re.compile(r"\{:(\w+),\s*[\"~><=]")

    for m in dep_re.finditer(content):
        deps.append(m.group(1))

    return sorted(set(deps))
