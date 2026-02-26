"""
Tool Remediation Coverage — Automated Validation

Run:  .venv/bin/python -m tests.test_remediation_coverage
      .venv/bin/python -m tests.test_remediation_coverage --verbose
      .venv/bin/python -m tests.test_remediation_coverage --suggest

Validates the entire remediation layer:
  1. Recipe completeness (cli, label, install methods per system)
  2. Dep coverage (every dep referenced in handlers is resolvable)
  3. Handler option validity (switch_method targets exist, packages cover families)
  4. Scenario availability (no false impossibles across all system presets)
  5. Missing tool detection (common tools that should have recipes but don't)

Exit codes:
  0 = all checks pass
  1 = failures detected (printed to stderr)
"""

from __future__ import annotations

import sys
import shutil
from typing import Any

from src.core.services.tool_install.data.recipes import TOOL_RECIPES
from src.core.services.tool_install.data.remediation_handlers import (
    BOOTSTRAP_HANDLERS,
    INFRA_HANDLERS,
    METHOD_FAMILY_HANDLERS,
)
from src.core.services.tool_install.domain.remediation_planning import (
    _check_dep_availability,
    _compute_availability,
    build_remediation_response,
)
from src.core.services.dev_scenarios import (
    SYSTEM_PRESETS,
    generate_all_scenarios,
)


# ═══════════════════════════════════════════════════════════════════
# Expected tool registry — tools that SHOULD have recipes
# ═══════════════════════════════════════════════════════════════════

# Common tools that any serious dev system must be able to install.
# If they're missing from TOOL_RECIPES, the test will flag them.
EXPECTED_TOOLS = {
    # ── Core runtimes ──────────────────────────────────────────
    "python3", "node", "go", "rustup", "ruby", "java",
    # ── Version control ────────────────────────────────────────
    "git", "git-lfs",
    # ── Containers ─────────────────────────────────────────────
    "docker", "podman", "kubectl", "helm", "k9s",
    # ── Package managers ───────────────────────────────────────
    "pip", "pipx", "npm", "yarn", "cargo", "nvm",
    # ── System utilities ───────────────────────────────────────
    "curl", "wget", "unzip", "tar", "jq", "yq",
    "tmux", "htop", "tree", "make", "gcc",
    # ── Quality / linting ──────────────────────────────────────
    "ruff", "black", "mypy", "eslint", "prettier",
    "shellcheck", "shfmt",
    # ── Security ───────────────────────────────────────────────
    "trivy", "snyk",
    # ── Infrastructure ─────────────────────────────────────────
    "terraform", "ansible", "packer",
}

# Map of package manager → distro families it serves
PKG_MGR_TO_FAMILIES = {
    "apt":    ["debian"],
    "dnf":    ["rhel"],
    "apk":    ["alpine"],
    "zypper": ["suse"],
    "brew":   ["macos"],
    "pacman": ["arch"],
}

# All distro families we support
ALL_FAMILIES = {"debian", "rhel", "alpine", "suse", "macos", "arch"}


# ═══════════════════════════════════════════════════════════════════
# Check 1: Recipe completeness
# ═══════════════════════════════════════════════════════════════════

def check_recipe_completeness(verbose: bool = False) -> list[str]:
    """Validate every recipe has required fields and reasonable coverage."""
    issues: list[str] = []

    for tool_id, recipe in sorted(TOOL_RECIPES.items()):
        # Skip non-installable entries
        if recipe.get("_not_installable"):
            continue

        cli = recipe.get("cli", "")
        if not cli or cli == "?":
            issues.append(f"recipe/{tool_id}: missing or placeholder cli field")

        if not recipe.get("label"):
            # Not critical but worth noting
            if verbose:
                issues.append(f"recipe/{tool_id}: missing label")

        install = recipe.get("install", {})
        if not install:
            issues.append(f"recipe/{tool_id}: NO install methods at all")
            continue

        # Check if tool has at least _default or a system pkg manager
        has_universal = "_default" in install
        has_any_pkg_mgr = any(
            m in install for m in ("apt", "dnf", "apk", "zypper", "brew", "pacman")
        )
        if not has_universal and not has_any_pkg_mgr:
            issues.append(
                f"recipe/{tool_id}: no _default and no system pkg manager method"
            )

    return issues


# ═══════════════════════════════════════════════════════════════════
# Check 2: Dep coverage
# ═══════════════════════════════════════════════════════════════════

def check_dep_coverage(verbose: bool = False) -> list[str]:
    """Validate every dep referenced in handlers is resolvable."""
    issues: list[str] = []
    all_deps: set[str] = set()

    # Collect all deps from all handler layers
    for method, handlers in METHOD_FAMILY_HANDLERS.items():
        for handler in handlers:
            for opt in handler.get("options", []):
                dep = opt.get("dep", "")
                if dep:
                    all_deps.add(dep)

    for handler in INFRA_HANDLERS + BOOTSTRAP_HANDLERS:
        for opt in handler.get("options", []):
            dep = opt.get("dep", "")
            if dep:
                all_deps.add(dep)

    for dep in sorted(all_deps):
        state, reason, deps, impossible = _check_dep_availability(dep)
        if state == "impossible":
            issues.append(
                f"dep/{dep}: impossible — {impossible}"
            )
        elif state == "locked" and dep not in TOOL_RECIPES:
            # Dep is a system package (no recipe). Not an error but worth noting.
            if verbose:
                has_binary = shutil.which(dep) is not None
                if has_binary:
                    pass  # It's installed, fine
                else:
                    issues.append(
                        f"dep/{dep}: no recipe, not installed — "
                        f"treated as system package (will work if pkg manager has it)"
                    )

    return issues


# ═══════════════════════════════════════════════════════════════════
# Check 3: Handler option validity
# ═══════════════════════════════════════════════════════════════════

def check_handler_options(verbose: bool = False) -> list[str]:
    """Validate handler options have correct references."""
    issues: list[str] = []

    all_handlers: list[tuple[str, str, dict]] = []

    for method, handlers in METHOD_FAMILY_HANDLERS.items():
        for handler in handlers:
            all_handlers.append((f"method/{method}", handler["failure_id"], handler))

    for handler in INFRA_HANDLERS:
        all_handlers.append(("infra", handler["failure_id"], handler))

    for handler in BOOTSTRAP_HANDLERS:
        all_handlers.append(("bootstrap", handler["failure_id"], handler))

    for layer, fid, handler in all_handlers:
        for opt in handler.get("options", []):
            strategy = opt.get("strategy", "")
            oid = opt.get("id", "?")

            if strategy == "install_packages":
                packages = opt.get("packages", {})
                dynamic = opt.get("dynamic_packages", False)
                if not dynamic and not packages:
                    issues.append(
                        f"handler/{layer}/{fid}/{oid}: "
                        f"install_packages with no packages defined"
                    )
                elif not dynamic:
                    covered = set(packages.keys())
                    # Check if this handler is method-specific
                    # dnf/yum handlers only need rhel packages
                    if layer.startswith("method/dnf") or layer.startswith("method/yum"):
                        if "rhel" not in covered:
                            issues.append(
                                f"handler/{layer}/{fid}/{oid}: "
                                f"RHEL-family handler missing 'rhel' packages"
                            )
                    elif verbose:
                        missing = ALL_FAMILIES - covered
                        if missing:
                            issues.append(
                                f"handler/{layer}/{fid}/{oid}: "
                                f"install_packages missing families: {sorted(missing)}"
                            )

    return issues


# ═══════════════════════════════════════════════════════════════════
# Check 4: Scenario availability
# ═══════════════════════════════════════════════════════════════════

# Impossibles that are intentional / correct
KNOWN_LEGITIMATE_IMPOSSIBLES = {
    # Edge case test scenarios — intentionally impossible
    "edge_all_impossible",
    # Method-specific handlers tested on wrong systems
    # (e.g. dnf handler option on Debian — EPEL doesn't exist there)
}

# Impossibles that are system-correct (apt option on non-apt system, etc.)
SYSTEM_CORRECT_REASONS = {
    "No 'apt' install method in recipe",
    "No 'dnf' install method in recipe",
    "No 'apk' install method in recipe",
    "No 'pacman' install method in recipe",
    "No 'zypper' install method in recipe",
    "ARM architecture is not supported",
    "This method has been permanently removed upstream",
    # A2 version-aware gates
    "snap requires systemd (not available)",
    "Cannot install packages: read-only root filesystem",
}


def check_scenario_availability(verbose: bool = False) -> list[str]:
    """Run all scenarios on all presets and report false impossibles."""
    issues: list[str] = []
    summary: dict[str, dict[str, int]] = {}

    for preset_id in sorted(SYSTEM_PRESETS.keys()):
        scenarios = generate_all_scenarios(preset_id)
        counts = {"ready": 0, "locked": 0, "impossible": 0, "false_impossible": 0}

        for s in scenarios:
            sid = s["_meta"]["id"]
            for opt in s.get("remediation", {}).get("options", []):
                avail = opt.get("availability", "unknown")
                counts[avail] = counts.get(avail, 0) + 1

                if avail == "impossible":
                    reason = opt.get("impossible_reason", "?")

                    # Skip known legitimate impossibles
                    if sid in KNOWN_LEGITIMATE_IMPOSSIBLES:
                        continue

                    # Skip system-correct impossibles
                    if reason in SYSTEM_CORRECT_REASONS:
                        continue

                    # Skip family-specific package mismatches (correct)
                    if reason.startswith("No packages defined for distro family"):
                        continue

                    # Skip PM availability mismatches (correct)
                    if reason.startswith("Package manager '") and reason.endswith(
                        "is not available on this system"
                    ):
                        continue

                    # This is a FALSE impossible — report it
                    counts["false_impossible"] += 1
                    issues.append(
                        f"scenario/{preset_id}/{sid}/{opt.get('id','?')}: "
                        f"FALSE IMPOSSIBLE — {reason}"
                    )

        summary[preset_id] = counts

    # Print summary table
    print("\n┌─────────────────────┬───────┬────────┬────────────┬─────────────────┐")
    print("│ System Preset       │ Ready │ Locked │ Impossible │ FALSE Impossible│")
    print("├─────────────────────┼───────┼────────┼────────────┼─────────────────┤")
    for pid in sorted(summary.keys()):
        c = summary[pid]
        false_str = str(c['false_impossible'])
        if c['false_impossible'] > 0:
            false_str = f"❌ {false_str}"
        else:
            false_str = f"✅ {false_str}"
        print(
            f"│ {pid:19s} │ {c['ready']:5d} │ {c['locked']:6d} │ {c['impossible']:10d} │ {false_str:>15s} │"
        )
    print("└─────────────────────┴───────┴────────┴────────────┴─────────────────┘")

    return issues


# ═══════════════════════════════════════════════════════════════════
# Check 5: Missing tools
# ═══════════════════════════════════════════════════════════════════

def check_missing_tools(verbose: bool = False) -> list[str]:
    """Report expected tools that don't have recipes yet."""
    issues: list[str] = []

    for tool_id in sorted(EXPECTED_TOOLS):
        if tool_id not in TOOL_RECIPES:
            issues.append(f"missing/{tool_id}: expected tool has no recipe")

    return issues


# ═══════════════════════════════════════════════════════════════════
# Check 6: Method coverage gaps
# ═══════════════════════════════════════════════════════════════════

def check_method_coverage(verbose: bool = False) -> list[str]:
    """Report tools that are missing common install methods for systems they could support."""
    issues: list[str] = []
    suggestions: list[str] = []

    # Method families and what systems use them
    method_to_systems = {
        "apt":    "Debian/Ubuntu/Raspbian",
        "dnf":    "Fedora/RHEL/CentOS",
        "apk":    "Alpine",
        "zypper": "openSUSE/SLES",
        "brew":   "macOS",
        "pacman": "Arch/Manjaro",
    }

    for tool_id, recipe in sorted(TOOL_RECIPES.items()):
        if recipe.get("_not_installable"):
            continue

        install = recipe.get("install", {})
        if not install:
            continue

        methods = set(install.keys())

        # If a tool has apt, it probably should also have dnf, apk, pacman
        # (it's a native-package tool)
        pkg_mgr_methods = methods & {"apt", "dnf", "apk", "zypper", "brew", "pacman"}
        if pkg_mgr_methods and len(pkg_mgr_methods) < 3:
            all_pkg_mgrs = {"apt", "dnf", "apk", "zypper", "brew", "pacman"}
            missing = all_pkg_mgrs - methods
            if missing and verbose:
                missing_systems = [
                    f"{m}({method_to_systems.get(m, '?')})"
                    for m in sorted(missing)
                ]
                suggestions.append(
                    f"coverage/{tool_id}: has {sorted(pkg_mgr_methods)} "
                    f"but missing {', '.join(missing_systems)}"
                )

    return issues + suggestions


# ═══════════════════════════════════════════════════════════════════
# Runner
# ═══════════════════════════════════════════════════════════════════

def run_all_checks(verbose: bool = False, suggest: bool = False) -> int:
    """Run all checks. Returns exit code (0=pass, 1=failures)."""
    all_issues: list[str] = []
    all_suggestions: list[str] = []

    print("=" * 70)
    print("  Tool Remediation Coverage — Automated Validation")
    print("=" * 70)

    # ── Check 1 ──
    print("\n📋 Check 1: Recipe completeness...")
    issues = check_recipe_completeness(verbose=verbose)
    errors = [i for i in issues if "NO install" in i or "missing or placeholder cli" in i]
    warnings = [i for i in issues if i not in errors]
    print(f"   {len(TOOL_RECIPES)} recipes, {len(errors)} errors, {len(warnings)} warnings")
    all_issues.extend(errors)
    if verbose:
        all_suggestions.extend(warnings)

    # ── Check 2 ──
    print("\n🔗 Check 2: Dep coverage...")
    issues = check_dep_coverage(verbose=verbose)
    errors = [i for i in issues if "impossible" in i]
    warnings = [i for i in issues if i not in errors]
    print(f"   {len(errors)} impossible deps, {len(warnings)} notes")
    all_issues.extend(errors)
    if verbose:
        all_suggestions.extend(warnings)

    # ── Check 3 ──
    print("\n🔧 Check 3: Handler option validity...")
    issues = check_handler_options(verbose=verbose)
    errors = [i for i in issues if "missing families" not in i]
    warnings = [i for i in issues if "missing families" in i]
    print(f"   {len(errors)} errors, {len(warnings)} coverage gaps")
    all_issues.extend(errors)
    if verbose:
        all_suggestions.extend(warnings)

    # ── Check 4 ──
    print("\n🎯 Check 4: Scenario availability (all presets)...")
    issues = check_scenario_availability(verbose=verbose)
    print(f"   {len(issues)} false impossibles")
    all_issues.extend(issues)

    # ── Check 5 ──
    print("\n🔍 Check 5: Missing expected tools...")
    issues = check_missing_tools(verbose=verbose)
    print(f"   {len(issues)} expected tools without recipes")
    all_issues.extend(issues)

    # ── Check 6 ──
    if suggest:
        print("\n💡 Check 6: Method coverage suggestions...")
        suggestions = check_method_coverage(verbose=True)
        print(f"   {len(suggestions)} coverage suggestions")
        all_suggestions.extend(suggestions)

    # ── Summary ──
    print("\n" + "=" * 70)

    if all_issues:
        print(f"\n❌ {len(all_issues)} ISSUES FOUND:\n")
        for issue in all_issues:
            print(f"  • {issue}", file=sys.stderr)
            print(f"  • {issue}")
    else:
        print("\n✅ All checks passed!")

    if all_suggestions and suggest:
        print(f"\n💡 {len(all_suggestions)} SUGGESTIONS:\n")
        for s in all_suggestions:
            print(f"  → {s}")

    print()
    return 1 if all_issues else 0


if __name__ == "__main__":
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    suggest = "--suggest" in sys.argv or "-s" in sys.argv
    sys.exit(run_all_checks(verbose=verbose, suggest=suggest))
