"""
Dependency compatibility checker — queries package registries for version constraints.

Supports all languages with public registry APIs:
  - Python: PyPI (Requires-Python)
  - Node.js: npm (engines.node)
  - Rust: crates.io (rust_version / MSRV)
  - Ruby: RubyGems (required_ruby_version)
  - PHP: Packagist (require.php)
  - Elixir: Hex.pm (elixir requirements)

Each handler: scan deps → query registry → compare against target → report.
Read-only — nothing is modified. Both preview and execute return the same data.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.request
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..context import UpgradeContext

logger = logging.getLogger(__name__)

_PYPI_TIMEOUT = 10  # seconds per package query


def _build_host_import_mapping() -> dict[str, str]:
    """Build import-name → package-name mapping from the HOST Python.

    Uses importlib.metadata to inspect all installed distributions and
    their top-level import names. This covers every installed package
    accurately — no hardcoded list needed.
    """
    mapping: dict[str, str] = {}
    try:
        from importlib.metadata import distributions

        for dist in distributions():
            dist_name = dist.metadata["Name"]
            # top_level.txt lists the importable package names
            top_level = dist.read_text("top_level.txt")
            if top_level:
                for line in top_level.strip().split("\n"):
                    name = line.strip()
                    if name and not name.startswith("#"):
                        mapping[name] = dist_name
            else:
                # Fallback: use the distribution name itself as import name
                mapping[dist_name.replace("-", "_").lower()] = dist_name
    except Exception:
        pass
    return mapping


# Cached at module load — built once from the host environment
_HOST_IMPORT_TO_PKG: dict[str, str] | None = None


def _get_import_to_pkg() -> dict[str, str]:
    """Get the cached host import→package mapping."""
    global _HOST_IMPORT_TO_PKG
    if _HOST_IMPORT_TO_PKG is None:
        _HOST_IMPORT_TO_PKG = _build_host_import_mapping()
    return _HOST_IMPORT_TO_PKG


def handle_check_dep_compat_pypi(ctx: UpgradeContext, mode: str) -> dict:
    """Check if the module's dependencies support the target Python version.

    Both preview and execute do the same thing: scan imports, query PyPI,
    return a compatibility report. This is read-only.
    """
    if ctx.language != "python":
        return {
            "ok": True,
            "can_apply": False,
            "preview_type": "info",
            "summary": "Dependency checking only available for Python",
        }

    # ── Scan module imports ──────────────────────────────────────
    try:
        from src.core.services.system_posture.bridges.module_intel import (
            _build_import_mapping,
            _find_site_packages,
            _scan_module_imports,
        )

        module_dir = ctx.project_root / ctx.module_path
        if not module_dir.is_dir():
            return {"ok": False, "error": f"Module directory not found: {ctx.module_path}"}

        module_imports = _scan_module_imports(module_dir)
        if not module_imports:
            return {
                "ok": True,
                "can_apply": False,
                "preview_type": "findings",
                "summary": "No third-party imports found",
                "findings": [],
            }

        # Map import names to pip package names using the host environment
        host_mapping = _get_import_to_pkg()

        # Also try site-packages mapping as fallback
        try:
            site_packages = _find_site_packages(ctx.project_root)
            if site_packages:
                sp_mapping = _build_import_mapping(site_packages)
                # Host mapping takes precedence, site-packages fills gaps
                combined = {**sp_mapping, **host_mapping}
            else:
                combined = host_mapping
        except Exception:
            combined = host_mapping

        # Map imports to package names
        packages: set[str] = set()
        for imp in module_imports:
            if imp in combined:
                packages.add(combined[imp])
            else:
                packages.add(imp)

    except Exception as exc:
        return {"ok": False, "error": f"Failed to scan imports: {exc}"}

    # ── Query PyPI for each package ──────────────────────────────
    target_parts = _parse_version(ctx.target_floor)
    if not target_parts:
        return {"ok": False, "error": f"Cannot parse target version: {ctx.target_floor}"}

    # Read pinned versions from requirements.txt (if exists)
    pinned_versions: dict[str, str] = {}
    req_file = ctx.project_root / ctx.module_path / "requirements.txt"
    if req_file.is_file():
        try:
            import re as _re
            for line in req_file.read_text(encoding="utf-8").split("\n"):
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("-"):
                    continue
                # Match: package==version or package>=version
                m = _re.match(r"^([a-zA-Z0-9_-]+)\s*[=<>~!]+\s*([\d.]+)", line)
                if m:
                    pinned_versions[m.group(1).lower().replace("_", "-")] = m.group(2)
        except Exception:
            pass

    findings = []
    errors = []

    for pkg_name in sorted(packages):
        pkg_normalized = pkg_name.lower().replace("_", "-")

        # If already pinned to a compatible version, skip PyPI query
        pinned = pinned_versions.get(pkg_normalized)
        if pinned:
            result = _check_package_compat(
                pkg_normalized, target_parts, ctx.target_floor, pinned_version=pinned,
            )
        else:
            result = _check_package_compat(pkg_normalized, target_parts, ctx.target_floor)
        if result:
            findings.append(result)
        # Errors are logged but don't stop the process

    compatible_count = sum(1 for f in findings if f["compatible"])
    incompatible_count = sum(1 for f in findings if not f["compatible"])
    unknown_count = sum(1 for f in findings if f.get("unknown"))

    all_ok = incompatible_count == 0

    return {
        "ok": True,
        "can_apply": False,  # read-only operation
        "preview_type": "findings",
        "summary": (
            f"All {compatible_count} checked dependencies support Python {ctx.target_floor}"
            if all_ok
            else f"{incompatible_count} of {len(findings)} dependencies may not support Python {ctx.target_floor}"
        ),
        "findings": findings,
        "compatible_count": compatible_count,
        "incompatible_count": incompatible_count,
        "unknown_count": unknown_count,
        "all_compatible": all_ok,
    }


def _check_package_compat(
    package: str,
    target_parts: list[int],
    target_str: str,
    pinned_version: str | None = None,
) -> dict | None:
    """Check a single package's Python version compatibility via PyPI.

    If pinned_version is provided, checks THAT version instead of latest.
    Returns a finding dict, or None if the package can't be checked.
    """
    try:
        if pinned_version:
            url = f"https://pypi.org/pypi/{package}/{pinned_version}/json"
        else:
            url = f"https://pypi.org/pypi/{package}/json"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=_PYPI_TIMEOUT) as resp:
            data = json.loads(resp.read().decode())
    except Exception as exc:
        logger.debug("PyPI query failed for %s: %s", package, exc)
        return {
            "package": package,
            "compatible": False,
            "unknown": True,
            "requires_python": "?",
            "note": "Could not query PyPI — verify manually",
        }

    info = data.get("info", {})
    current_version = info.get("version", "")
    requires_python = info.get("requires_python") or ""

    if not requires_python:
        return {
            "package": package,
            "version": current_version,
            "compatible": True,
            "unknown": True,
            "requires_python": "(none specified)",
            "note": "No Requires-Python metadata",
        }

    # Parse the floor from requires_python (e.g., ">=3.8" → [3, 8])
    floor_match = re.search(r">=\s*(\d+(?:\.\d+)*)", requires_python)
    if not floor_match:
        return {
            "package": package,
            "version": current_version,
            "compatible": True,
            "unknown": True,
            "requires_python": requires_python,
            "note": "Cannot parse constraint",
        }

    req_parts = _parse_version(floor_match.group(1))
    if not req_parts:
        return None

    # Check: does the package SUPPORT our target?
    # If requires-python is ">=3.8", it supports 3.12 (target >= floor)
    compatible = target_parts >= req_parts

    # Also check for upper bounds like "<4" or "<=3.11"
    upper_match = re.search(r"<\s*(\d+(?:\.\d+)*)", requires_python)
    if upper_match and compatible:
        upper_parts = _parse_version(upper_match.group(1))
        if upper_parts and target_parts >= upper_parts:
            compatible = False

    return {
        "package": package,
        "version": current_version,
        "compatible": compatible,
        "requires_python": requires_python,
    }


def handle_update_deps_interactive(ctx: UpgradeContext, mode: str) -> dict:
    """Find alternative versions of incompatible deps.

    For each dependency that doesn't support the target Python version,
    queries PyPI for older versions that DO support it and presents
    them as alternatives the user can choose.

    Both preview and execute return the same data — this is a read-only
    analysis. The user applies changes manually (editing requirements files).
    """
    if ctx.language != "python":
        return {
            "ok": True,
            "can_apply": False,
            "preview_type": "info",
            "summary": "Dependency alternatives only available for Python",
        }

    # First, run the compatibility check to find incompatible deps
    compat_result = handle_check_dep_compat_pypi(ctx, mode)
    if not compat_result.get("ok"):
        return compat_result

    findings = compat_result.get("findings", [])
    incompatible = [f for f in findings if not f.get("compatible") and not f.get("unknown")]

    if not incompatible:
        return {
            "ok": True,
            "can_apply": False,
            "preview_type": "info",
            "summary": "All dependencies are compatible — no alternatives needed",
        }

    target_parts = _parse_version(ctx.target_floor)
    if not target_parts:
        return {"ok": False, "error": f"Cannot parse target version: {ctx.target_floor}"}

    # For each incompatible dep, find compatible versions
    alternatives = []
    for dep in incompatible:
        pkg = dep.get("package", "")
        if not pkg:
            continue

        alt_versions = _find_compatible_versions(pkg, target_parts, ctx.target_floor)
        alternatives.append({
            "package": pkg,
            "current_version": dep.get("version", ""),
            "requires_python": dep.get("requires_python", ""),
            "compatible_versions": alt_versions[:5],  # top 5 alternatives
        })

    return {
        "ok": True,
        "can_apply": False,  # user picks versions manually
        "preview_type": "findings",
        "summary": f"Found alternatives for {len(alternatives)} incompatible package(s)",
        "detail": (
            "These packages don't support Python {target} in their latest version. "
            "Below are older versions that do. Update your requirements accordingly."
        ).format(target=ctx.target_floor),
        "findings": [
            {
                "package": a["package"],
                "note": (
                    f"Current {a['current_version']} ({a['requires_python']}) → "
                    + (
                        ", ".join(
                            f"{v['version']} ({v['requires_python']})"
                            for v in a["compatible_versions"]
                        )
                        if a["compatible_versions"]
                        else "no compatible version found"
                    )
                ),
                "compatible": False,
            }
            for a in alternatives
        ],
    }


def _find_compatible_versions(
    package: str,
    target_parts: list[int],
    target_str: str,
) -> list[dict]:
    """Query PyPI for versions of a package that support the target Python.

    Returns a list of {version, requires_python} sorted newest-first.
    """
    try:
        url = f"https://pypi.org/pypi/{package}/json"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=_PYPI_TIMEOUT) as resp:
            data = json.loads(resp.read().decode())
    except Exception:
        return []

    releases = data.get("releases", {})
    compatible = []

    for ver, files in releases.items():
        if not files:
            continue
        # Skip pre-releases
        if any(c in ver for c in ("a", "b", "rc", "dev", "post")):
            continue

        # Find requires_python from file metadata
        requires_python = None
        for f in files:
            rp = f.get("requires_python")
            if rp:
                requires_python = rp
                break

        if not requires_python:
            continue

        # Check if target satisfies requires_python
        floor_match = re.search(r">=\s*(\d+(?:\.\d+)*)", requires_python)
        if not floor_match:
            continue

        req_parts = _parse_version(floor_match.group(1))
        if not req_parts:
            continue

        if target_parts >= req_parts:
            # Also check upper bound
            upper_match = re.search(r"<\s*(\d+(?:\.\d+)*)", requires_python)
            if upper_match:
                upper_parts = _parse_version(upper_match.group(1))
                if upper_parts and target_parts >= upper_parts:
                    continue

            compatible.append({
                "version": ver,
                "requires_python": requires_python,
            })

    # Sort by version descending
    compatible.sort(
        key=lambda a: [int(x) for x in a["version"].split(".")[:3] if x.isdigit()],
        reverse=True,
    )

    return compatible



# ══════════════════════════════════════════════════════════════════
# GENERIC MULTI-LANGUAGE DEP CHECKER
# ══════════════════════════════════════════════════════════════════


def _generic_dep_check(
    ctx,
    language_label: str,
    scan_fn,
    query_fn,
    extract_constraint_fn,
    version_label: str,
) -> dict:
    """Generic dep compatibility checker for any language.

    Args:
        ctx: UpgradeContext
        language_label: Human-readable name (e.g. "Node.js")
        scan_fn: (module_dir) → list[str] of package names
        query_fn: (package_name) → dict with version info or None
        extract_constraint_fn: (query_result) → constraint string or ""
        version_label: Name of the constraint field for display (e.g. "engines.node")
    """
    module_dir = ctx.project_root / ctx.module_path
    if not module_dir.is_dir():
        return {"ok": False, "error": f"Module directory not found: {ctx.module_path}"}

    packages = scan_fn(module_dir)
    if not packages:
        return {
            "ok": True, "can_apply": False, "preview_type": "findings",
            "summary": f"No {language_label} dependencies found",
            "findings": [],
        }

    target_parts = _parse_version(ctx.target_floor)
    if not target_parts:
        return {"ok": False, "error": f"Cannot parse target version: {ctx.target_floor}"}

    findings = []
    for pkg in sorted(packages):
        result = query_fn(pkg)
        if not result:
            findings.append({
                "package": pkg, "compatible": False, "unknown": True,
                "requires_python": "?", "note": "Could not query registry — verify manually",
            })
            continue

        constraint = extract_constraint_fn(result)
        version = result.get("version", "")

        if not constraint:
            findings.append({
                "package": pkg, "version": version, "compatible": True,
                "unknown": True, "requires_python": f"(no {version_label})",
                "note": f"No {version_label} specified",
            })
            continue

        compatible = _check_constraint_compat(constraint, target_parts)
        findings.append({
            "package": pkg, "version": version, "compatible": compatible,
            "requires_python": constraint,
        })

    compat_count = sum(1 for f in findings if f["compatible"])
    incompat_count = sum(1 for f in findings if not f["compatible"])

    return {
        "ok": True, "can_apply": False, "preview_type": "findings",
        "summary": (
            f"All {compat_count} checked dependencies support {language_label} {ctx.target_floor}"
            if incompat_count == 0
            else f"{incompat_count} of {len(findings)} dependencies may not support {language_label} {ctx.target_floor}"
        ),
        "findings": findings,
        "compatible_count": compat_count,
        "incompatible_count": incompat_count,
        "all_compatible": incompat_count == 0,
    }


def _check_constraint_compat(constraint: str, target_parts: list[int]) -> bool:
    """Check if a version constraint is compatible with the target.

    Handles: >=X.Y, ~>X.Y, >=X.Y <Z, ^X.Y, and bare X.Y
    """
    # Try >= constraint
    floor_match = re.search(r">=\s*(\d+(?:\.\d+)*)", constraint)
    if floor_match:
        req_parts = _parse_version(floor_match.group(1))
        if req_parts and target_parts < req_parts:
            return False

    # Try ~> constraint (Ruby/Elixir pessimistic)
    if not floor_match:
        tilde_match = re.search(r"~>\s*(\d+(?:\.\d+)*)", constraint)
        if tilde_match:
            req_parts = _parse_version(tilde_match.group(1))
            if req_parts and target_parts < req_parts:
                return False

    # Check upper bound
    upper_match = re.search(r"<\s*(\d+(?:\.\d+)*)", constraint)
    if upper_match:
        upper_parts = _parse_version(upper_match.group(1))
        if upper_parts and target_parts >= upper_parts:
            return False

    return True


# ── Dependency discovery — detect missing deps ──────────────────


def handle_discover_missing_deps(ctx: UpgradeContext, mode: str) -> dict:
    """Discover imports that aren't listed in requirements.txt.

    Scans module code for import statements, maps import names to pip
    package names using the host Python's importlib.metadata, and reports
    any that are missing from requirements.txt.

    Preview: shows what's missing.
    Execute: adds missing packages to requirements.txt.
    """
    if ctx.language != "python":
        return {"ok": True, "can_apply": False, "preview_type": "info",
                "summary": "Dependency discovery only available for Python"}

    try:
        from src.core.services.system_posture.bridges.module_intel import (
            _scan_module_imports,
        )

        module_dir = ctx.project_root / ctx.module_path
        if not module_dir.is_dir():
            return {"ok": False, "error": f"Module directory not found: {ctx.module_path}"}

        module_imports = _scan_module_imports(module_dir)
        if not module_imports:
            return {"ok": True, "can_apply": False, "preview_type": "info",
                    "summary": "No third-party imports found", "findings": []}

        # Map imports to package names
        host_mapping = _get_import_to_pkg()
        packages: dict[str, str] = {}  # import_name → package_name
        for imp in module_imports:
            pkg = host_mapping.get(imp, imp)
            packages[imp] = pkg

        # Read current requirements.txt
        req_file = module_dir / "requirements.txt"
        existing_pkgs: set[str] = set()
        if req_file.is_file():
            for line in req_file.read_text(encoding="utf-8").split("\n"):
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("-"):
                    continue
                # Extract package name (before any version specifier)
                pkg_match = re.match(r"^([a-zA-Z0-9_.-]+)", line)
                if pkg_match:
                    existing_pkgs.add(pkg_match.group(1).lower().replace("_", "-"))

        # Find missing
        missing: list[dict] = []
        for imp, pkg in sorted(packages.items()):
            pkg_normalized = pkg.lower().replace("_", "-")
            if pkg_normalized not in existing_pkgs:
                # Get installed version from host for pinning
                version = ""
                try:
                    from importlib.metadata import version as _get_ver
                    version = _get_ver(pkg)
                except Exception:
                    pass

                missing.append({
                    "import_name": imp,
                    "package": pkg,
                    "version": version,
                    "line": f"{pkg}>={version}" if version else pkg,
                })

        if not missing:
            return {"ok": True, "can_apply": False, "preview_type": "info",
                    "summary": "All imports are covered by requirements.txt",
                    "findings": []}

        # Build BEFORE/AFTER diff of requirements.txt
        current_content = req_file.read_text(encoding="utf-8").rstrip("\n") if req_file.is_file() else ""
        new_lines = "\n".join(m["line"] for m in missing)
        new_content = (current_content + "\n" + new_lines).strip()

        # Also build per-package findings for detail
        findings = []
        for m in missing:
            findings.append({
                "feature": f"{m['import_name']} → {m['package']}",
                "file": f"requirements.txt",
                "version": m["version"] or "latest",
            })

        if mode == "preview":
            return {
                "ok": True,
                "can_apply": True,
                "preview_type": "diff",
                "summary": f"{len(missing)} package(s) imported but not in requirements.txt",
                "file": str(req_file.relative_to(ctx.project_root)),
                "old_value": current_content,
                "new_value": new_content,
                "findings": findings,
                "detail": "Code imports these packages but they're not in requirements.txt. Apply to add them.",
            }

        # Execute — append missing packages to requirements.txt
        if not req_file.is_file():
            req_file.write_text("", encoding="utf-8")

        lines = req_file.read_text(encoding="utf-8").rstrip("\n")
        added = []
        for m in missing:
            lines += "\n" + m["line"]
            added.append(m["line"])

        req_file.write_text(lines + "\n", encoding="utf-8")

        return {
            "ok": True,
            "summary": f"Added {len(added)} package(s) to requirements.txt: {', '.join(added)}",
            "added": added,
        }

    except Exception as exc:
        return {"ok": False, "error": f"Dependency discovery failed: {exc}"}


# ── Node.js ──────────────────────────────────────────────────────


def handle_check_dep_compat_npm(ctx, mode: str) -> dict:
    """Check npm dependency compatibility with target Node.js version."""
    from .dep_scanner import scan_npm_deps
    from .registry_clients import query_npm

    return _generic_dep_check(
        ctx, "Node.js", scan_npm_deps, query_npm,
        lambda r: r.get("engines_node", ""),
        "engines.node",
    )


def handle_update_deps_npm(ctx, mode: str) -> dict:
    """Find alternative npm versions for incompatible deps."""
    return _generic_update_deps(ctx, mode, "Node.js", handle_check_dep_compat_npm,
                                _find_npm_alternatives)


def _find_npm_alternatives(pkg, target_parts, target_str):
    from .registry_clients import query_npm_versions
    versions = query_npm_versions(pkg)
    compatible = []
    for v in versions:
        constraint = v.get("engines_node", "")
        if constraint and _check_constraint_compat(constraint, target_parts):
            compatible.append({"version": v["version"], "requires_python": constraint})
    return compatible[:5]


# ── Rust ─────────────────────────────────────────────────────────


def handle_check_dep_compat_crates(ctx, mode: str) -> dict:
    """Check crate MSRV compatibility with target Rust version."""
    from .dep_scanner import scan_rust_deps
    from .registry_clients import query_crates

    return _generic_dep_check(
        ctx, "Rust", scan_rust_deps, query_crates,
        lambda r: ">=" + r["rust_version"] if r.get("rust_version") else "",
        "rust-version (MSRV)",
    )


def handle_update_deps_crates(ctx, mode: str) -> dict:
    """Find alternative crate versions for incompatible deps."""
    return _generic_update_deps(ctx, mode, "Rust", handle_check_dep_compat_crates,
                                _find_crates_alternatives)


def _find_crates_alternatives(pkg, target_parts, target_str):
    from .registry_clients import query_crates_versions
    versions = query_crates_versions(pkg)
    compatible = []
    for v in versions:
        rv = v.get("rust_version", "")
        if rv:
            constraint = f">={rv}"
            if _check_constraint_compat(constraint, target_parts):
                compatible.append({"version": v["version"], "requires_python": constraint})
    return compatible[:5]


# ── Ruby ─────────────────────────────────────────────────────────


def handle_check_dep_compat_rubygems(ctx, mode: str) -> dict:
    """Check gem compatibility with target Ruby version."""
    from .dep_scanner import scan_ruby_deps
    from .registry_clients import query_rubygems

    return _generic_dep_check(
        ctx, "Ruby", scan_ruby_deps, query_rubygems,
        lambda r: r.get("required_ruby_version", ""),
        "required_ruby_version",
    )


def handle_update_deps_rubygems(ctx, mode: str) -> dict:
    """Find alternative gem versions for incompatible deps."""
    return _generic_update_deps(ctx, mode, "Ruby", handle_check_dep_compat_rubygems,
                                lambda pkg, tp, ts: [])  # rubygems versions API lacks per-version ruby info


# ── PHP ──────────────────────────────────────────────────────────


def handle_check_dep_compat_packagist(ctx, mode: str) -> dict:
    """Check Composer package compatibility with target PHP version."""
    from .dep_scanner import scan_php_deps
    from .registry_clients import query_packagist

    return _generic_dep_check(
        ctx, "PHP", scan_php_deps, query_packagist,
        lambda r: r.get("require_php", ""),
        "require.php",
    )


def handle_update_deps_packagist(ctx, mode: str) -> dict:
    """Find alternative Packagist versions for incompatible deps."""
    return _generic_update_deps(ctx, mode, "PHP", handle_check_dep_compat_packagist,
                                _find_packagist_alternatives)


def _find_packagist_alternatives(pkg, target_parts, target_str):
    from .registry_clients import query_packagist_versions
    versions = query_packagist_versions(pkg)
    compatible = []
    for v in versions:
        constraint = v.get("require_php", "")
        if constraint and _check_constraint_compat(constraint, target_parts):
            compatible.append({"version": v["version"], "requires_python": constraint})
    return compatible[:5]


# ── Elixir ───────────────────────────────────────────────────────


def handle_check_dep_compat_hex(ctx, mode: str) -> dict:
    """Check Hex package compatibility with target Elixir version."""
    from .dep_scanner import scan_elixir_deps
    from .registry_clients import query_hex

    return _generic_dep_check(
        ctx, "Elixir", scan_elixir_deps, query_hex,
        lambda r: r.get("elixir_requirement", ""),
        "elixir requirement",
    )


def handle_update_deps_hex(ctx, mode: str) -> dict:
    """Find alternative Hex versions for incompatible deps."""
    return _generic_update_deps(ctx, mode, "Elixir", handle_check_dep_compat_hex,
                                lambda pkg, tp, ts: [])  # hex versions API would need per-release queries


# ══════════════════════════════════════════════════════════════════
# GENERIC UPDATE DEPS (alternatives finder)
# ══════════════════════════════════════════════════════════════════


def _generic_update_deps(ctx, mode, language_label, check_fn, find_alt_fn) -> dict:
    """Generic handler for finding alternative dep versions.

    Runs the compat check first, then for each incompatible dep
    queries for older compatible versions.
    """
    compat_result = check_fn(ctx, mode)
    if not compat_result.get("ok"):
        return compat_result

    findings = compat_result.get("findings", [])
    incompatible = [f for f in findings if not f.get("compatible") and not f.get("unknown")]

    if not incompatible:
        return {
            "ok": True, "can_apply": False, "preview_type": "info",
            "summary": f"All {language_label} dependencies are compatible — no alternatives needed",
        }

    target_parts = _parse_version(ctx.target_floor)
    if not target_parts:
        return {"ok": False, "error": f"Cannot parse target version: {ctx.target_floor}"}

    alt_findings = []
    for dep in incompatible:
        pkg = dep.get("package", "")
        if not pkg:
            continue

        alt_versions = find_alt_fn(pkg, target_parts, ctx.target_floor)
        alt_findings.append({
            "package": pkg,
            "compatible": False,
            "note": (
                f"Current {dep.get('version', '?')} ({dep.get('requires_python', '?')}) → "
                + (
                    ", ".join(f"{v['version']} ({v['requires_python']})" for v in alt_versions)
                    if alt_versions
                    else "no compatible version found"
                )
            ),
        })

    return {
        "ok": True, "can_apply": False, "preview_type": "findings",
        "summary": f"Found alternatives for {len(alt_findings)} incompatible {language_label} package(s)",
        "detail": f"These packages don't support {language_label} {ctx.target_floor} in their latest version.",
        "findings": alt_findings,
    }


def _parse_version(v: str) -> list[int] | None:
    """Parse version string to integer list."""
    try:
        return [int(x) for x in v.split(".")]
    except (ValueError, AttributeError):
        return None
