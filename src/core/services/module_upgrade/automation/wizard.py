"""
Wizard orchestrator — multi-step automation flows with SSE streaming.

Provides generator functions that yield SSE event dicts for:
  - Dependency compatibility scanning (scan phase)
  - Dependency update with alternatives (apply phase)
  - Subprocess execution with streaming output

Two-phase design:
  Phase 1 (scan): analyze state, query registries, return results
  Phase 2 (apply): take user choices, apply changes, stream output

Each generator yields dicts like:
  {"type": "step_start", "step": 0, "label": "Scanning dependencies"}
  {"type": "log", "step": 0, "line": "Checking express..."}
  {"type": "step_done", "step": 0, "elapsed_ms": 234}
  {"type": "done", "ok": True, "scan_result": {...}}
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING, Generator

if TYPE_CHECKING:
    from ..context import UpgradeContext

logger = logging.getLogger(__name__)


def wizard_dep_scan(ctx: UpgradeContext) -> Generator[dict, None, None]:
    """Phase 1: Scan dependencies and check compatibility.

    Yields SSE events as it scans. Final event includes full results
    with compatible/incompatible lists and alternatives for each
    incompatible dep.
    """
    language = ctx.language
    target = ctx.target_floor
    module_dir = ctx.project_root / ctx.module_path

    yield {"type": "wizard_start", "title": f"Checking dependency compatibility", "total_steps": 3}

    # ── Step 1: Scan dependencies ────────────────────────────────
    yield {"type": "step_start", "step": 0, "label": "Scanning dependencies"}
    t0 = time.time()

    scanner, querier, extractor, version_label = _get_lang_tools(language)
    if not scanner:
        yield {"type": "log", "step": 0, "line": f"No dependency scanner for {language}"}
        yield {"type": "done", "ok": True, "scan_result": {"packages": [], "compatible": [], "incompatible": []}}
        return

    try:
        packages = scanner(module_dir)
    except Exception as exc:
        yield {"type": "step_failed", "step": 0, "error": f"Failed to scan dependencies: {exc}"}
        yield {"type": "done", "ok": False, "error": f"Dependency scan failed: {exc}"}
        return
    elapsed = int((time.time() - t0) * 1000)
    yield {"type": "log", "step": 0, "line": f"Found {len(packages)} dependencies"}
    yield {"type": "step_done", "step": 0, "elapsed_ms": elapsed}

    if not packages:
        yield {"type": "done", "ok": True, "scan_result": {"packages": [], "compatible": [], "incompatible": []}}
        return

    # ── Step 2: Query registry ───────────────────────────────────
    yield {"type": "step_start", "step": 1, "label": "Querying package registry"}
    t0 = time.time()

    from .dep_checker import _check_constraint_compat, _parse_version
    target_parts = _parse_version(target)

    compatible = []
    incompatible = []
    unknown = []

    for i, pkg in enumerate(packages):
        yield {"type": "log", "step": 1, "line": f"Checking {pkg}..."}
        if len(packages) > 1:
            yield {"type": "progress", "step": 1, "percent": int((i + 1) / len(packages) * 100)}

        try:
            result = querier(pkg)
        except Exception as exc:
            unknown.append({"package": pkg, "note": f"Query error: {exc}"})
            yield {"type": "log", "step": 1, "line": f"  {pkg}: ❓ query failed ({exc})"}
            continue

        if not result:
            unknown.append({"package": pkg, "note": "Could not query registry"})
            yield {"type": "log", "step": 1, "line": f"  {pkg}: ❓ registry unreachable"}
            continue

        try:
            constraint = extractor(result)
            version = result.get("version", "")
        except Exception as exc:
            unknown.append({"package": pkg, "note": f"Parse error: {exc}"})
            yield {"type": "log", "step": 1, "line": f"  {pkg}: ❓ failed to parse metadata ({exc})"}
            continue

        if not constraint:
            unknown.append({"package": pkg, "version": version, "note": f"No {version_label}"})
            yield {"type": "log", "step": 1, "line": f"  {pkg} {version}: ❓ no {version_label}"}
            continue

        if target_parts and _check_constraint_compat(constraint, target_parts):
            compatible.append({"package": pkg, "version": version, "constraint": constraint})
            yield {"type": "log", "step": 1, "line": f"  {pkg} {version}: ✅ compatible ({constraint})"}
        else:
            incompatible.append({"package": pkg, "version": version, "constraint": constraint})
            yield {"type": "log", "step": 1, "line": f"  {pkg} {version}: ❌ incompatible ({constraint})"}

    elapsed = int((time.time() - t0) * 1000)
    yield {"type": "step_done", "step": 1, "elapsed_ms": elapsed}

    # ── Step 3: Find alternatives for incompatible deps ──────────
    alternatives = {}
    if incompatible:
        yield {"type": "step_start", "step": 2, "label": f"Finding alternatives for {len(incompatible)} package(s)"}
        t0 = time.time()

        alt_finder = _get_alt_finder(language)
        for dep in incompatible:
            pkg = dep["package"]
            yield {"type": "log", "step": 2, "line": f"Searching alternatives for {pkg}..."}
            try:
                alts = alt_finder(pkg, target_parts, target) if alt_finder else []
            except Exception as exc:
                alts = []
                yield {"type": "log", "step": 2, "line": f"  ❓ Failed to query alternatives: {exc}"}
            alternatives[pkg] = alts[:5]
            if alts:
                yield {"type": "log", "step": 2, "line": f"  Found {len(alts)} compatible version(s)"}
            elif alt_finder:
                yield {"type": "log", "step": 2, "line": f"  No compatible versions found"}

        elapsed = int((time.time() - t0) * 1000)
        yield {"type": "step_done", "step": 2, "elapsed_ms": elapsed}
    else:
        yield {"type": "step_start", "step": 2, "label": "No incompatible dependencies"}
        yield {"type": "step_done", "step": 2, "elapsed_ms": 0}

    # ── Done ─────────────────────────────────────────────────────
    yield {
        "type": "done",
        "ok": True,
        "scan_result": {
            "compatible": compatible,
            "incompatible": incompatible,
            "unknown": unknown,
            "alternatives": alternatives,
            "compatible_count": len(compatible),
            "incompatible_count": len(incompatible),
            "all_compatible": len(incompatible) == 0,
        },
    }


def wizard_subprocess(ctx: UpgradeContext, cmd: list[str], label: str) -> Generator[dict, None, None]:
    """Run a subprocess with streaming output.

    Yields SSE events for each line of output.
    """
    import shutil

    module_dir = ctx.project_root / ctx.module_path
    binary = cmd[0] if cmd else ""

    yield {"type": "wizard_start", "title": f"Running {label}", "total_steps": 1}
    yield {"type": "step_start", "step": 0, "label": label}

    if not shutil.which(binary):
        yield {"type": "step_failed", "step": 0, "error": f"`{binary}` not found on PATH"}
        yield {"type": "done", "ok": False, "error": f"`{binary}` not found"}
        return

    if not module_dir.is_dir():
        yield {"type": "step_failed", "step": 0, "error": f"Directory not found: {ctx.module_path}"}
        yield {"type": "done", "ok": False, "error": "Module directory not found"}
        return

    yield {"type": "log", "step": 0, "line": f"$ cd {ctx.module_path}"}
    yield {"type": "log", "step": 0, "line": f"$ {' '.join(cmd)}"}

    t0 = time.time()

    try:
        from src.core.services.tool_install.execution.subprocess_runner import (
            _run_subprocess_streaming,
        )

        for chunk in _run_subprocess_streaming(cmd, cwd=str(module_dir)):
            if "line" in chunk:
                yield {"type": "log", "step": 0, "line": chunk["line"]}
            elif chunk.get("done"):
                elapsed = int((time.time() - t0) * 1000)
                if chunk.get("ok"):
                    yield {"type": "step_done", "step": 0, "elapsed_ms": elapsed}
                    yield {"type": "done", "ok": True, "summary": f"{label} completed in {elapsed}ms"}
                else:
                    error = chunk.get("stderr", "") or f"Exit code {chunk.get('exit_code', '?')}"
                    yield {"type": "step_failed", "step": 0, "error": error}
                    yield {"type": "done", "ok": False, "error": error}
                return

    except Exception as exc:
        elapsed = int((time.time() - t0) * 1000)
        yield {"type": "step_failed", "step": 0, "error": str(exc)}
        yield {"type": "done", "ok": False, "error": str(exc)}


# ── Language tool mapping ────────────────────────────────────────


def _get_lang_tools(language: str):
    """Get scanner + querier + extractor for a language.

    Returns (scan_fn, query_fn, extract_fn, version_label) or (None, None, None, None).
    """
    from .dep_scanner import (
        scan_elixir_deps,
        scan_npm_deps,
        scan_php_deps,
        scan_ruby_deps,
        scan_rust_deps,
    )
    from .registry_clients import (
        query_crates,
        query_hex,
        query_npm,
        query_packagist,
        query_rubygems,
    )

    mapping = {
        "python": None,  # Python uses its own path (module_intel imports)
        "javascript": (scan_npm_deps, query_npm, lambda r: r.get("engines_node", ""), "engines.node"),
        "typescript": (scan_npm_deps, query_npm, lambda r: r.get("engines_node", ""), "engines.node"),
        "rust": (scan_rust_deps, query_crates, lambda r: ">=" + r["rust_version"] if r.get("rust_version") else "", "rust-version"),
        "ruby": (scan_ruby_deps, query_rubygems, lambda r: r.get("required_ruby_version", ""), "required_ruby_version"),
        "php": (scan_php_deps, query_packagist, lambda r: r.get("require_php", ""), "require.php"),
        "elixir": (scan_elixir_deps, query_hex, lambda r: r.get("elixir_requirement", ""), "elixir requirement"),
    }

    tools = mapping.get(language)
    if tools is None:
        return None, None, None, None
    return tools


def _get_alt_finder(language: str):
    """Get the alternative version finder for a language."""
    from .dep_checker import (
        _find_compatible_versions,
        _find_crates_alternatives,
        _find_npm_alternatives,
        _find_packagist_alternatives,
    )

    finders = {
        "python": _find_compatible_versions,
        "javascript": _find_npm_alternatives,
        "typescript": _find_npm_alternatives,
        "rust": _find_crates_alternatives,
        "php": _find_packagist_alternatives,
        # Ruby and Elixir don't have per-version queries (API limitation)
        "ruby": None,
        "elixir": None,
    }
    return finders.get(language)


# ── Subprocess command mapping ───────────────────────────────────


SUBPROCESS_COMMANDS = {
    # Package manager operations
    "run_go_mod_tidy": (["go", "mod", "tidy"], "go mod tidy"),
    "run_bundle_update": (["bundle", "update"], "bundle update"),
    "run_composer_update": (["composer", "update", "--no-interaction"], "composer update"),
    "run_dotnet_restore": (["dotnet", "restore"], "dotnet restore"),
    "run_mix_deps_get": (["mix", "deps.get"], "mix deps.get"),
    "run_cargo_check": (["cargo", "check"], "cargo check"),
    "run_npm_install": (["npm", "install"], "npm install"),
    # Test suite runners
    "run_pytest": (["pytest", "--tb=short", "-q"], "pytest"),
    "run_npm_test": (["npm", "test"], "npm test"),
    "run_go_test": (["go", "test", "./..."], "go test ./..."),
    "run_cargo_test": (["cargo", "test"], "cargo test"),
    "run_bundle_exec_rspec": (["bundle", "exec", "rspec"], "bundle exec rspec"),
    "run_mvn_test": (["mvn", "test", "-q"], "mvn test"),
    "run_dotnet_test": (["dotnet", "test"], "dotnet test"),
    "run_composer_test": (["composer", "test", "--no-interaction"], "composer test"),
    "run_mix_test": (["mix", "test"], "mix test"),
    # Package install (for after pinning versions)
    "run_pip_install": (["pip", "install", "-r", "requirements.txt"], "pip install -r requirements.txt"),
}


def wizard_batch(
    ctx: UpgradeContext,
    step_ids: list[str],
    step_labels: list[str],
    project_root: Path,
    auto_fix: bool = False,
) -> Generator[dict, None, None]:
    """Run multiple automation steps sequentially with SSE streaming.

    Each step runs through the executor. Progress, logs, and errors
    are streamed live. Stops on first failure.

    auto_fix: When True, fix handlers modify source files. When False, they preview only.
    """
    total = len(step_ids)
    yield {"type": "wizard_start", "title": f"Running {total} automation steps", "total_steps": total}

    from . import get_handler_registry
    from .executor import _get_plan_target, _mark_step_done

    registry = get_handler_registry()
    completed = 0
    failed_step = None

    # Set auto_fix on context so fix handlers know whether to modify files
    ctx.auto_fix = auto_fix

    for idx, (step_id, label) in enumerate(zip(step_ids, step_labels)):
        automation_id = step_id.split(":")[0] if ":" in step_id else ""

        yield {"type": "step_start", "step": idx, "label": label, "total": total}
        yield {"type": "log", "step": idx, "line": f"Running: {label}"}
        t0 = time.time()

        handler_id = automation_id.split("__")[0] if "__" in automation_id else automation_id
        handler = registry.get(handler_id)
        if not handler:
            yield {"type": "log", "step": idx, "line": f"No handler for '{handler_id}'"}
            yield {"type": "step_failed", "step": idx, "error": f"No handler: {handler_id}"}
            failed_step = idx
            break

        # Determine mode: fix steps use preview when auto_fix is OFF
        _FIX_PREFIXES = ("fix_compat_auto", "add_future_annotations")
        base_aid = automation_id.split("__")[0] if "__" in automation_id else automation_id
        is_fix_step = base_aid in _FIX_PREFIXES
        mode = "execute"
        if is_fix_step and not auto_fix:
            mode = "preview"

        # Pass feature hash to context for per-feature filtering
        if "__" in automation_id:
            ctx._feature_hash = automation_id.split("__")[1]
        else:
            ctx._feature_hash = None

        try:
            result = handler(ctx, mode)
        except Exception as exc:
            elapsed = int((time.time() - t0) * 1000)
            yield {"type": "log", "step": idx, "line": f"❌ Error: {exc}"}
            yield {"type": "step_failed", "step": idx, "error": str(exc), "elapsed_ms": elapsed}
            failed_step = idx
            break

        elapsed = int((time.time() - t0) * 1000)
        ok = result.get("ok", False)

        # Fix step in preview mode — show what would change, needs user confirmation
        if is_fix_step and not auto_fix and ok:
            summary = result.get("summary", "")
            yield {"type": "log", "step": idx,
                   "line": f"👁️ Preview: {summary} — click Automate individually to apply"}
            yield {"type": "step_done", "step": idx, "elapsed_ms": elapsed,
                   "step_id": step_id, "needs_attention": True}
            completed += 1
            continue  # Continue to next step (non-fix steps still run)

        # Log result details
        if result.get("summary"):
            yield {"type": "log", "step": idx, "line": result["summary"]}
        if result.get("file"):
            yield {"type": "log", "step": idx, "line": f"  File: {result['file']}"}
        if result.get("old_value") and result.get("new_value"):
            yield {"type": "log", "step": idx, "line": f"  Changed: {result['old_value']} → {result['new_value']}"}
        if result.get("output"):
            for line in result["output"].split("\n")[:10]:
                yield {"type": "log", "step": idx, "line": f"  {line}"}

        # Report findings — different handling for dep checks vs code scans
        findings = result.get("findings", [])
        is_dep_check = automation_id.startswith("check_dep_compat_")

        if findings and is_dep_check:
            # Dep checker: findings have {package, compatible, version}
            compat = sum(1 for f in findings if f.get("compatible"))
            incompat = sum(1 for f in findings if not f.get("compatible") and not f.get("unknown"))
            yield {"type": "log", "step": idx, "line": f"  {compat} compatible, {incompat} incompatible"}
            for f in findings[:5]:
                icon = "✅" if f.get("compatible") else ("❓" if f.get("unknown") else "❌")
                yield {"type": "log", "step": idx, "line": f"  {icon} {f.get('package', '?')} {f.get('version', '')}"}
            if len(findings) > 5:
                yield {"type": "log", "step": idx, "line": f"  ...and {len(findings) - 5} more"}

            if incompat > 0:
                # Dep check with incompatible results → remediation
                pass  # falls through to remediation block below
            else:
                incompat = 0  # all clear

        elif findings:
            # Code scanner: findings have {file, line, feature, version}
            # Classify: annotation features (fixable with __future__) vs runtime (unfixable)
            # BUT: annotation features in files that already have __future__ are FALSE POSITIVES
            # (compute_code_floor should not return them, but filter here as safety net)
            _ANNOTATION_FEATURE_NAMES = {"builtin generics (runtime)", "union type X | Y (runtime)"}
            _future_re = re.compile(r"^from\s+__future__\s+import\s+annotations", re.MULTILINE)

            def _file_has_future(file_path):
                try:
                    content = (ctx.project_root / file_path).read_text(encoding="utf-8", errors="ignore")
                    return bool(_future_re.search(content))
                except OSError:
                    return False

            # Filter out annotation findings in files that already have __future__
            real_findings = []
            for f in findings:
                if f.get("feature") in _ANNOTATION_FEATURE_NAMES and _file_has_future(f.get("file", "")):
                    continue  # false positive — file already has __future__
                real_findings.append(f)

            if not real_findings:
                yield {"type": "log", "step": idx, "line": f"  {len(findings)} finding(s) — all in files with __future__ (no action needed)"}
                findings = []
                annotation_findings = []
                runtime_findings = []
                incompat = 0
            else:
                findings = real_findings
                annotation_findings = [f for f in findings if f.get("feature") in _ANNOTATION_FEATURE_NAMES]
                runtime_findings = [f for f in findings if f.get("feature") not in _ANNOTATION_FEATURE_NAMES]

                yield {"type": "log", "step": idx, "line": f"  {len(findings)} finding(s)"}
                for f in findings[:8]:
                    file_ref = f.get("file", "")
                    if f.get("line"):
                        file_ref += f":{f['line']}"
                    fixable = "🔧" if f.get("feature") in _ANNOTATION_FEATURE_NAMES else "⚠️"
                    yield {"type": "log", "step": idx, "line": f"  {fixable} {file_ref} — {f.get('feature', '')} ({f.get('version', '')}+)"}
                if len(findings) > 8:
                    yield {"type": "log", "step": idx, "line": f"  ...and {len(findings) - 8} more"}

            # Check if any findings are above the target version
            from .dep_checker import _parse_version
            target_parts = _parse_version(ctx.target_floor)
            above_target = [
                f for f in findings
                if target_parts and _parse_version(f.get("version", "")) and
                _parse_version(f["version"]) > target_parts
            ]

            if above_target and annotation_findings:
                # There are fixable annotation issues — offer remediation
                annotation_above = [f for f in annotation_findings
                                    if target_parts and _parse_version(f.get("version", ""))
                                    and _parse_version(f["version"]) > target_parts]
                runtime_above = [f for f in runtime_findings
                                 if target_parts and _parse_version(f.get("version", ""))
                                 and _parse_version(f["version"]) > target_parts]

                if annotation_above:
                    # Collect unique files that need __future__
                    files_needing_future = list(set(f.get("file", "") for f in annotation_above))
                    yield {"type": "log", "step": idx,
                           "line": f"  🔧 {len(files_needing_future)} file(s) can be fixed with __future__ annotations"}

                if runtime_above:
                    highest_runtime = max(f.get("version", "") for f in runtime_above)
                    yield {"type": "log", "step": idx,
                           "line": f"  ⚠️ {len(runtime_above)} runtime feature(s) require Python {highest_runtime}+ — cannot be fixed with __future__"}

                yield {"type": "step_failed", "step": idx,
                       "error": f"{len(above_target)} code feature(s) above target Python {ctx.target_floor}",
                       "elapsed_ms": elapsed}

                # Build remediation options
                rem_options = []
                if annotation_above and not runtime_above:
                    rem_options.append({
                        "id": "add_future", "label": f"Add __future__ annotations to {len(files_needing_future)} file(s)",
                        "description": "Adds `from __future__ import annotations` to make annotation syntax compatible"})
                elif annotation_above and runtime_above:
                    rem_options.append({
                        "id": "add_future", "label": f"Fix {len(annotation_above)} annotation issue(s) with __future__",
                        "description": "Fixes annotation features but runtime features will still require a higher Python"})
                if runtime_above:
                    highest_runtime = max(f.get("version", "") for f in runtime_above)
                    rem_options.append({
                        "id": "raise_target", "label": f"Raise target to {highest_runtime}",
                        "description": f"Runtime features require Python {highest_runtime}+"})
                rem_options.append({
                    "id": "skip", "label": "Skip — handle manually",
                    "description": "Review the findings and fix the code yourself"})

                yield {"type": "done", "ok": False,
                       "summary": f"{len(above_target)} code feature(s) incompatible with Python {ctx.target_floor}",
                       "completed": completed, "total": total,
                       "failed_step_id": step_id, "failed_step_idx": idx,
                       "remediation": {
                           "packages": [{"package": f.get("file", ""), "constraint": f.get("feature", ""),
                                         "current_version": f.get("version", "")+"+ required",
                                         "alternatives": []} for f in above_target[:10]],
                           "options": rem_options,
                           "code_files": files_needing_future if annotation_above else [],
                       }}
                return

            incompat = 0  # findings exist but none above target — step passes

        else:
            incompat = 0

        if is_dep_check and incompat > 0:
                incompat_pkgs = [f for f in findings if not f.get("compatible") and not f.get("unknown")]
                yield {"type": "log", "step": idx, "line": f"⚠️ {incompat} incompatible — searching alternatives..."}

                # Query alternatives for each incompatible package
                from .dep_checker import _parse_version
                target_parts = _parse_version(ctx.target_floor)
                alt_finder = _get_alt_finder(ctx.language) if ctx.language else None

                remediation_packages = []
                for dep in incompat_pkgs:
                    pkg = dep.get("package", "")
                    alts = []
                    if alt_finder and target_parts:
                        try:
                            alts = alt_finder(pkg, target_parts, ctx.target_floor)[:5]
                        except Exception:
                            pass
                    if alts:
                        yield {"type": "log", "step": idx, "line": f"  📦 {pkg}: {len(alts)} compatible version(s) available"}
                    else:
                        yield {"type": "log", "step": idx, "line": f"  📦 {pkg}: no compatible versions found"}

                    remediation_packages.append({
                        "package": pkg,
                        "current_version": dep.get("version", ""),
                        "constraint": dep.get("requires_python", ""),
                        "alternatives": [
                            {"version": a.get("version", ""), "constraint": a.get("requires_python", "")}
                            for a in alts
                        ],
                    })

                yield {"type": "step_failed", "step": idx,
                       "error": f"{incompat} incompatible dependencies found",
                       "elapsed_ms": elapsed}

                failed_step = idx
                # Don't break yet — emit done with remediation data
                yield {"type": "done", "ok": False,
                       "summary": f"{incompat} incompatible dependencies found",
                       "completed": completed, "total": total,
                       "failed_step_id": step_id, "failed_step_idx": idx,
                       "remediation": {
                           "packages": remediation_packages,
                           "options": [
                               {"id": "downgrade", "label": "Use compatible versions",
                                "description": "Update dependency constraints to use older versions that support your target"},
                               {"id": "raise_target", "label": "Raise target version",
                                "description": "Change your plan target to match what your dependencies require"},
                               {"id": "skip", "label": "Skip — handle manually",
                                "description": "Continue with the remaining steps and resolve dependencies later"},
                           ],
                       }}
                return  # done event already emitted

        if result.get("error"):
            yield {"type": "log", "step": idx, "line": f"❌ {result['error']}"}
            detail = result.get("detail", "")
            if detail:
                for detail_line in detail.split("\n"):
                    if detail_line.strip():
                        yield {"type": "log", "step": idx, "line": f"  {detail_line}"}

        # Determine if step should be marked done
        # Uses shared function from executor.py — ONE logic, no divergence
        from .executor import should_mark_done

        if ok and should_mark_done(result):
            _mark_step_done(ctx.module_name, step_id)
            yield {"type": "step_done", "step": idx, "elapsed_ms": elapsed,
                   "step_id": step_id}
            completed += 1
        elif ok:
            # Step succeeded but has findings that need attention
            yield {"type": "log", "step": idx,
                   "line": "⚠️ Step needs attention — not marked done"}
            yield {"type": "step_done", "step": idx, "elapsed_ms": elapsed,
                   "step_id": step_id, "needs_attention": True}
            completed += 1
        else:
            error_msg = result.get("error", "Step failed")
            yield {"type": "step_failed", "step": idx, "error": error_msg,
                   "elapsed_ms": elapsed}
            failed_step = idx
            break

    # Final summary
    if failed_step is not None:
        failed_aid = step_ids[failed_step].split(":")[0] if ":" in step_ids[failed_step] else ""
        is_test = failed_aid.startswith("run_") and "test" in failed_aid
        is_subprocess = failed_aid.startswith("run_")

        remediation = None
        if is_test:
            # Check if the handler returned compat hints
            compat_hints = result.get("compat_hints", []) if result else []
            rem_options = []
            if compat_hints:
                for hint in compat_hints:
                    if hint.get("auto_fixable"):
                        rem_options.append({
                            "id": "compat_fix",
                            "label": f"🔧 Fix: {hint['search']} → {hint['replace']}",
                            "description": hint["fix"],
                            "search": hint["search"],
                            "replace": hint["replace"],
                        })
                    else:
                        rem_options.append({
                            "id": "info",
                            "label": f"⚠️ {hint['feature']} (Python {hint['since']}+)",
                            "description": hint["fix"],
                        })
            rem_options.append(
                {"id": "skip", "label": "Mark as done anyway",
                 "description": "Mark this step complete and move on"})
            rem_options.append(
                {"id": "skip", "label": "Skip — fix tests later",
                 "description": "Continue and revisit test failures separately"})
            remediation = {
                "packages": [],
                "options": rem_options,
                "compat_hints": compat_hints,
            }
        elif is_subprocess:
            remediation = {
                "packages": [],
                "options": [
                    {"id": "skip", "label": "Skip — handle manually",
                     "description": "Run the command manually and resolve the issue"},
                ],
            }

        done_event = {
            "type": "done", "ok": False,
            "summary": f"Stopped at step {failed_step + 1}: {step_labels[failed_step]}",
            "completed": completed, "total": total,
            "failed_step_id": step_ids[failed_step],
            "failed_step_idx": failed_step,
        }
        if remediation:
            done_event["remediation"] = remediation
        yield done_event
    else:
        yield {"type": "done", "ok": True,
               "summary": f"All {completed} steps completed",
               "completed": completed, "total": total}
