"""
Tool Remediation Coverage — Automated Validation

Run:  .venv/bin/python -m tests.test_remediation_coverage
      .venv/bin/python -m tests.test_remediation_coverage --verbose
      .venv/bin/python -m tests.test_remediation_coverage --suggest

Per-tool mode (fast, targeted — preferred during audits):
      .venv/bin/python -m tests.test_remediation_coverage --tool npm
      .venv/bin/python -m tests.test_remediation_coverage --tool curl

Validates the entire remediation layer:
  1. Recipe completeness (cli, label, install methods per system)
  2. Dep coverage (every dep referenced in handlers is resolvable)
  3. Handler option validity (switch_method targets exist, packages cover families)
  4. Scenario availability (no false impossibles across all system presets)
  5. Missing tool detection (common tools that should have recipes but don't)

Per-tool mode validates:
  A. Recipe schema for the specific tool
  B. Handler schema for the tool's method family
  C. Full scenario sweep: every handler × every preset using the REAL recipe

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
from src.core.services.tool_install.data.tool_failure_handlers import (
    TOOL_FAILURE_HANDLERS,
)
from src.core.services.tool_install.resolver.dynamic_dep_resolver import (
    PACKAGE_GROUPS,
    resolve_package_group,
)
from src.core.services.tool_install.domain.remediation_planning import (
    _check_dep_availability,
    _compute_availability,
    build_remediation_response,
)
from src.core.services.tool_install.data.recipe_schema import (
    _validate_handler_list,
    validate_all_recipes,
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

        # Check if tool has at least one valid install path
        has_universal = "_default" in install
        has_any_pkg_mgr = any(
            m in install for m in ("apt", "dnf", "apk", "zypper", "brew", "pacman")
        )
        has_lang_method = any(
            m in install for m in ("pip", "npm", "cargo", "go")
        )
        has_source = "source" in install
        if not has_universal and not has_any_pkg_mgr and not has_lang_method and not has_source:
            issues.append(
                f"recipe/{tool_id}: no _default, no system pkg manager, "
                f"no language method, and no source method"
            )

        # Validate source method structure (must be dict, not command list)
        if has_source:
            source_spec = install["source"]
            if not isinstance(source_spec, dict):
                issues.append(
                    f"recipe/{tool_id}: 'source' method must be a dict "
                    f"(got {type(source_spec).__name__})"
                )
            elif not source_spec.get("build_system") and not source_spec.get("command"):
                issues.append(
                    f"recipe/{tool_id}: 'source' method missing "
                    f"'build_system' or 'command'"
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
                # Resolve string group references
                if isinstance(packages, str):
                    if packages not in PACKAGE_GROUPS:
                        issues.append(
                            f"handler/{layer}/{fid}/{oid}: "
                            f"unknown package group '{packages}'"
                        )
                        continue
                    packages = resolve_package_group(packages)
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
    "No 'source' install method in recipe",
    "ARM architecture is not supported",
    "This method has been permanently removed upstream",
    # A2 version-aware gates
    "snap requires systemd (not available)",
    "Cannot install packages: read-only root filesystem",
}

# Patterns that are reason-correct but dynamic (contain tool names)
SYSTEM_CORRECT_REASON_PATTERNS = (
    "Package manager '",            # native PM not available
    "not installed",                 # locked deps (language PMs, build tools)
    "No packages defined for distro family",
)


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

                    # Skip dynamic system-correct patterns
                    if any(reason.startswith(p) for p in SYSTEM_CORRECT_REASON_PATTERNS):
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
# Check 7: Arch-hardcoded _default commands
# ═══════════════════════════════════════════════════════════════════

_X86_PATTERNS = ("x86_64", "x86-64", "amd64", "64bit", "linux-amd64")


def check_default_arch_awareness(verbose: bool = False) -> list[str]:
    """Warn about _default commands with hardcoded x86 arch strings.

    If a recipe uses {arch} or {os} placeholders, it'll work everywhere.
    If it has a hardcoded arch string AND no arch_exclude, ARM systems
    will download the wrong binary.
    """
    issues: list[str] = []

    for tool_id, recipe in sorted(TOOL_RECIPES.items()):
        if recipe.get("_not_installable"):
            continue

        install = recipe.get("install", {})
        default_cmd = install.get("_default")
        if not default_cmd:
            continue

        # Flatten command to a single string for pattern matching
        cmd_str = " ".join(str(c) for c in default_cmd).lower()

        # Skip if using {arch} template — already arch-aware
        if "{arch}" in cmd_str:
            continue

        # Check for hardcoded x86 arch strings
        has_hardcoded_arch = any(pat in cmd_str for pat in _X86_PATTERNS)
        if not has_hardcoded_arch:
            continue

        # Check if there's an arch_exclude or on_failure that handles this
        has_arch_handling = bool(recipe.get("arch_exclude"))
        if has_arch_handling:
            continue

        issues.append(
            f"arch/{tool_id}: _default command contains hardcoded x86 arch "
            f"but no {{arch}} template and no arch_exclude"
        )

    return issues


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

    # ── Check 7 ──
    if suggest:
        print("\n🏗️  Check 7: Arch-hardcoded _default commands...")
        suggestions = check_default_arch_awareness(verbose=True)
        print(f"   {len(suggestions)} arch-hardcoded _default commands")
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


# ═══════════════════════════════════════════════════════════════════
# Per-tool testing (--tool <tool_id>)
# ═══════════════════════════════════════════════════════════════════

def _detect_method_family(tool_id: str, recipe: dict) -> str | None:
    """Determine which method family a tool belongs to.

    Checks the tool's install methods against known method families.
    Returns the family name or None.
    """
    install = recipe.get("install", {})
    for method in install:
        if method in METHOD_FAMILY_HANDLERS:
            return method
    # Check if the tool IS a method family (npm installs npm packages)
    if tool_id in METHOD_FAMILY_HANDLERS:
        return tool_id
    return None


def _get_all_families_for_tool(recipe: dict, tool_id: str = "") -> list[str]:
    """Return all method families that apply to a tool's install methods.

    Also includes the tool's own family if the tool IS a method family
    (e.g. npm, pip, cargo — they are both tools AND install methods for
    downstream packages).
    """
    install = recipe.get("install", {})
    families = []
    for method in install:
        if method in METHOD_FAMILY_HANDLERS:
            families.append(method)
    # If the tool itself IS a method family, include it
    # (npm the tool has its own npm-specific failure handlers)
    if tool_id and tool_id in METHOD_FAMILY_HANDLERS:
        if tool_id not in families:
            families.append(tool_id)
    # Also check the recipe's category — tools in the "node" category
    # should be tested against npm handlers, etc.
    category = recipe.get("category", "")
    category_to_family = {
        "node": "npm",
        "python": "pip",
        "rust": "cargo",
        "go": "go",
        "ruby": "gem",
    }
    mapped_family = category_to_family.get(category)
    if mapped_family and mapped_family in METHOD_FAMILY_HANDLERS:
        if mapped_family not in families:
            families.append(mapped_family)
    return families


def check_single_tool(tool_id: str) -> int:
    """Run targeted validation for a single tool.

    Returns 0 on success, 1 on failure.
    """
    print("=" * 70)
    print(f"  Per-Tool Audit: {tool_id}")
    print("=" * 70)

    issues: list[str] = []

    # ── A. Recipe schema ──────────────────────────────────────────
    print("\n📋 A. Recipe schema validation...")
    if tool_id not in TOOL_RECIPES:
        print(f"   ❌ {tool_id}: NOT FOUND in TOOL_RECIPES")
        return 1

    recipe = TOOL_RECIPES[tool_id]
    errs = validate_all_recipes({tool_id: recipe})
    tool_errs = errs.get(tool_id, [])
    if tool_errs:
        for e in tool_errs:
            print(f"   ❌ {e}")
            issues.append(f"recipe: {e}")
    else:
        print(f"   ✅ {tool_id} recipe: VALID")

    # ── B. Handler schema ─────────────────────────────────────────
    print("\n🔧 B. Handler schema validation...")
    families = _get_all_families_for_tool(recipe, tool_id=tool_id)
    # Also check _default if present
    if "_default" in recipe.get("install", {}):
        if "_default" not in families:
            families.append("_default")

    if not families:
        print("   ⚠️  No method families found — tool uses only native PM")
    else:
        for fam in families:
            if fam not in METHOD_FAMILY_HANDLERS:
                print(f"   ℹ️  {fam}: no method family handlers (OK for PM methods)")
                continue
            handler_errs = _validate_handler_list(
                METHOD_FAMILY_HANDLERS[fam], fam
            )
            if handler_errs:
                for e in handler_errs:
                    print(f"   ❌ {fam}: {e}")
                    issues.append(f"handler/{fam}: {e}")
            else:
                count = len(METHOD_FAMILY_HANDLERS[fam])
                print(f"   ✅ {fam} handlers: VALID ({count} handlers)")

    # Validate on_failure (Layer 3) handlers from TOOL_FAILURE_HANDLERS
    on_failure_raw = TOOL_FAILURE_HANDLERS.get(tool_id, [])
    if on_failure_raw:
        handler_errs = _validate_handler_list(
            on_failure_raw, f"{tool_id}/on_failure",
        )
        if handler_errs:
            for e in handler_errs:
                print(f"   ❌ on_failure: {e}")
                issues.append(f"handler/on_failure: {e}")
        else:
            count = len(on_failure_raw)
            print(f"   ✅ on_failure handlers: VALID ({count} handlers)")

    # ── C. Scenario sweep ─────────────────────────────────────────
    print("\n🎯 C. Scenario sweep (handlers × presets)...")
    print()

    all_presets = sorted(SYSTEM_PRESETS.keys())

    # Collect all handlers that apply to this tool
    test_scenarios: list[tuple[str, str, int, str, str]] = []
    # (label, method, exit_code, stderr, handler_id)

    # Method family handlers
    for fam in families:
        if fam not in METHOD_FAMILY_HANDLERS:
            continue
        for handler in METHOD_FAMILY_HANDLERS[fam]:
            stderr = handler.get("example_stderr", handler.get("pattern", "error"))
            exit_code = handler.get("example_exit_code", 1)
            test_scenarios.append((
                handler["label"],
                fam,
                exit_code,
                stderr,
                handler["failure_id"],
            ))

    # INFRA handlers (always apply)
    for handler in INFRA_HANDLERS:
        stderr = handler.get("example_stderr", handler.get("pattern", "error"))
        exit_code = handler.get("example_exit_code", 1)
        # Use the tool's primary install method for INFRA tests
        primary_method = recipe.get("install", {})
        first_method = next(iter(primary_method), "_default")
        test_scenarios.append((
            f"[INFRA] {handler['label']}",
            first_method,
            exit_code,
            stderr,
            handler["failure_id"],
        ))

    # Layer 3: Tool-specific on_failure handlers (from TOOL_FAILURE_HANDLERS)
    on_failure = TOOL_FAILURE_HANDLERS.get(tool_id, [])
    if on_failure:
        primary_method = recipe.get("install", {})
        first_method = next(iter(primary_method), "_default")
        for handler in on_failure:
            stderr = handler.get(
                "example_stderr", handler.get("pattern", "error"),
            )
            exit_code = handler.get("example_exit_code", 1)
            test_scenarios.append((
                f"[TOOL] {handler['label']}",
                first_method,
                exit_code,
                stderr,
                handler["failure_id"],
            ))

    total = 0
    covered = 0
    gaps: list[str] = []

    for label, method, exit_code, stderr, handler_id in test_scenarios:
        missed: list[str] = []
        for pn in all_presets:
            total += 1
            r = build_remediation_response(
                tool_id=tool_id,
                step_idx=0,
                step_label=f"Install {tool_id}",
                exit_code=exit_code,
                stderr=stderr,
                method=method,
                system_profile=SYSTEM_PRESETS[pn],
            )
            if r:
                covered += 1
            else:
                missed.append(pn)

        if missed:
            status = f"❌ {len(all_presets) - len(missed)}/{len(all_presets)} — GAPS: {', '.join(missed[:5])}"
            gaps.append(f"{label} ({handler_id}): {', '.join(missed)}")
        else:
            status = f"✅ {len(all_presets)}/{len(all_presets)}"

        print(f"  {label:45s} {status}")

    # ── Summary ───────────────────────────────────────────────────
    print()
    print("─" * 70)
    n_scenarios = len(test_scenarios)
    n_presets = len(all_presets)

    pct = (100 * covered // total) if total > 0 else 0
    print(f"\n  SCENARIOS: {n_scenarios}")
    print(f"  PRESETS:   {n_presets}")
    print(f"  MATRIX:    {n_scenarios} × {n_presets} = {total}")
    print(f"  COVERED:   {covered}/{total} ({pct}%)")

    if gaps:
        print(f"\n  ❌ {len(gaps)} GAP(S):")
        for g in gaps:
            print(f"    • {g}")
            issues.append(f"gap: {g}")
    else:
        print(f"\n  ✅ FULL COVERAGE — {n_scenarios} scenarios, {n_presets} presets")

    # Handler inventory
    print("\n  Handler inventory:")
    for fam in families:
        if fam in METHOD_FAMILY_HANDLERS:
            for h in METHOD_FAMILY_HANDLERS[fam]:
                print(f"    • {h['failure_id']:35s} [{h['category']}]")
    if on_failure:
        for h in on_failure:
            print(f"    ▸ {h['failure_id']:35s} [{h['category']}]  (on_failure)")
    print(f"    + {len(INFRA_HANDLERS)} INFRA handlers (cross-tool)")

    print()
    return 1 if issues else 0


if __name__ == "__main__":
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    suggest = "--suggest" in sys.argv or "-s" in sys.argv

    # Per-tool mode
    if "--tool" in sys.argv:
        idx = sys.argv.index("--tool")
        if idx + 1 >= len(sys.argv):
            print("❌ --tool requires a tool_id argument", file=sys.stderr)
            print("   Example: python -m tests.test_remediation_coverage --tool npm")
            sys.exit(1)
        tool_id = sys.argv[idx + 1]
        sys.exit(check_single_tool(tool_id))

    sys.exit(run_all_checks(verbose=verbose, suggest=suggest))
