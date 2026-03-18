"""
System Posture API routes — deprecation awareness for the nav badge.

Blueprint: ``posture_bp``
Prefix: ``/api``

Endpoints:
    GET /posture           → Full posture scan with all 5 pillars
    GET /posture/summary   → Lightweight summary for nav badge polling
    POST /posture/rescan   → Force rescan (cache bust)
    GET /posture/cache     → Cache diagnostics
"""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from src.core.services.events.tracked import tracked

posture_bp = Blueprint("posture", __name__)


@posture_bp.route("/posture")
def posture_full():  # type: ignore[no-untyped-def]
    """Full system posture scan with action enrichment.

    Returns all five pillars with item-level detail.  Each item
    is enriched with an ``actions`` list describing what the user
    can do about it (update, navigate, reset, etc.).

    Query params:
        bust=1  → Force rescan (bypass all caches).

    Returns:
        200 with full posture JSON including:
        - overall_rank, overall_status, summary
        - pillars: {platform, toolchain, project, runtime, modules}
        - each pillar: {rank, items[], warnings[], recommendations[]}
        - each item may include: actions[]
    """
    force = request.args.get("bust", "") == "1"
    via = request.args.get("via", "")

    try:
        if via == "mediator":
            from src.core.services.mediator import get_mediator

            m = get_mediator()
            if force:
                m.put("posture.full", cascade=True)
            r = m.get("posture.full", force=force)
            posture = r["data"]
            result = posture.to_dict()
        else:
            from src.core.services.system_posture import scan_posture

            root = current_app.config.get("PROJECT_ROOT")
            posture = scan_posture(force=force, project_root=root)
            result = posture.to_dict()

        _enrich_posture_actions(result)
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


def _enrich_posture_actions(posture_dict: dict) -> None:
    """Add ``actions`` metadata to posture items for frontend buttons.

    Modifies ``posture_dict`` in place.  Each pillar is handled
    differently:

    - **toolchain**: Cross-references ``TOOL_RECIPES`` and
      ``get_update_map()`` to determine if a tool can be updated.
    - **modules**: Attaches version_strategy, version_note, and
      strategy_deduced metadata from project.yml for frontend display.
    - **project**: Adds navigation links to the audit tab.
    - **runtime**: Adds reset actions for degraded circuit breakers.
    - **platform**: Adds guide flags for outdated OS versions.
    """
    pillars = posture_dict.get("pillars", {})

    # ── Toolchain — update actions ─────────────────────────────
    toolchain = pillars.get("toolchain", {})
    tc_items = toolchain.get("items", [])

    if tc_items:
        from src.core.services.tool_install.data.recipes import TOOL_RECIPES
        from src.core.services.tool_install.resolver.method_selection import (
            get_update_map,
        )

        # Ranks that qualify for an update action
        _updatable_ranks = {"aging", "outdated", "deprecated", "dangerous"}
        updatable_count = 0

        for item in tc_items:
            rank = item.get("rank", "")
            name = item.get("name", "")

            # Strip common prefixes used by the toolchain scanner
            # (e.g. "toolchain:docker" → "docker")
            tool_id = name.split(":")[-1] if ":" in name else name

            recipe = TOOL_RECIPES.get(tool_id)
            if not recipe:
                # No recipe — no automated action
                continue

            if rank not in _updatable_ranks:
                continue

            update_map = get_update_map(recipe)
            if update_map:
                needs_sudo = any(
                    recipe.get("needs_sudo", {}).get(m, False)
                    for m in update_map
                )
                item["actions"] = [{
                    "type": "update",
                    "available": True,
                    "tool_id": tool_id,
                    "label": f"Update {recipe.get('label', tool_id)}",
                    "needs_sudo": needs_sudo,
                }]
                updatable_count += 1
            else:
                # Has recipe but no update command — manual hint
                cli = recipe.get("cli", tool_id)
                item["actions"] = [{
                    "type": "manual",
                    "available": True,
                    "tool_id": tool_id,
                    "label": f"Manual update for {recipe.get('label', tool_id)}",
                    "hint": _manual_update_hint_simple(tool_id, recipe),
                }]

        # Store count for batch button
        if updatable_count > 0:
            toolchain["updatable_count"] = updatable_count

    # ── Project — audit navigation links ───────────────────────
    project = pillars.get("project", {})
    for item in project.get("items", []):
        name = item.get("name", "")
        # project items are named like "project:git", "project:docker"
        probe_id = name.split(":")[-1] if ":" in name else name
        rank = item.get("rank", "")

        if rank in ("outdated", "deprecated", "dangerous", "aging"):
            item["actions"] = [{
                "type": "link",
                "target": "audit",
                "card_id": probe_id,
                "label": "View in Audit",
            }]

    # ── Runtime — reset actions ────────────────────────────────
    runtime = pillars.get("runtime", {})
    for item in runtime.get("items", []):
        name = item.get("name", "")
        rank = item.get("rank", "")

        if "circuit_breaker" in name and rank in ("outdated", "deprecated", "dangerous"):
            breaker_name = name.split(":")[-1] if ":" in name else name
            item["actions"] = [{
                "type": "reset",
                "target": "circuit_breaker",
                "breaker_id": breaker_name,
                "label": "Reset Breaker",
            }]
        elif "retry_queue" in name and rank in ("outdated", "deprecated", "dangerous"):
            item["actions"] = [{
                "type": "clear",
                "target": "retry_queue",
                "label": "Clear Exhausted",
            }]

    # ── Modules — full structured display metadata ──────────────
    modules_pillar = pillars.get("modules", {})
    mod_items = modules_pillar.get("items", [])

    if mod_items:
        # Load project config
        try:
            from src.core.config.loader import load_project

            project = load_project()
            module_refs = {ref.name: ref for ref in project.modules}
        except Exception:
            module_refs = {}

        # Load all helpers
        try:
            from src.core.config.stack_loader import discover_stacks
            from src.core.services.detection import detect_runtime_constraint
            from src.core.services.system_posture.bridges.module_intel import (
                compute_code_floor,
                compute_dependency_floor,
                compute_effective_floor,
                compute_verdict,
            )
            from src.core.services.system_posture.bridges.modules import (
                compute_compat_range,
                deduce_strategy,
            )

            all_stacks = discover_stacks()
            _project_root = current_app.config.get("PROJECT_ROOT")
        except ImportError:
            all_stacks = None
            _project_root = None
            detect_runtime_constraint = None
            compute_compat_range = None
            deduce_strategy = None
            compute_dependency_floor = None
            compute_code_floor = None
            compute_effective_floor = None
            compute_verdict = None

        for item in mod_items:
            item_name = item.get("name", "")
            module_name = item_name.split(" (")[0] if " (" in item_name else item_name
            lang_match = item_name.split("(")[-1].rstrip(")") if "(" in item_name else ""

            ref = module_refs.get(module_name)
            strategy_explicit = getattr(ref, "version_strategy", "") if ref else ""
            note = getattr(ref, "version_note", "") if ref else ""
            module_path = ref.path if ref else module_name

            floor = item.get("value", "").lstrip("≥") or ""
            current = item.get("current_version", "")
            eol_date = item.get("eol_date", "")
            cves = item.get("cves", [])
            rank = item.get("rank", "")

            # Stack name
            item["stack"] = getattr(ref, "stack", "") if ref else lang_match

            # Strategy
            if strategy_explicit:
                item["version_strategy"] = strategy_explicit
                item["strategy_deduced"] = False
            elif floor and current and deduce_strategy:
                lifecycle_key = _module_lang_to_lifecycle(lang_match)
                deduced_strat, _ = deduce_strategy(floor, current, lifecycle_key)
                item["version_strategy"] = deduced_strat
                item["strategy_deduced"] = True
            else:
                item["version_strategy"] = ""
                item["strategy_deduced"] = True

            item["version_note"] = note

            # ── Deep analysis: deps floor, code floor, verdict ──
            deps_floor = None
            deps_details = []
            code_floor_ver = None
            code_features = []
            effective = None
            verdict = ""
            verdict_detail = ""
            floor_source = None

            if _project_root and rank != "na":
                from pathlib import Path as _Path
                pr = _Path(_project_root)

                # Floor source (3-tier detection)
                if ref and detect_runtime_constraint and all_stacks:
                    mod_dir = pr / ref.path
                    _, _, floor_source = detect_runtime_constraint(
                        mod_dir, ref.stack or lang_match,
                        project_root=pr, stacks=all_stacks,
                    )

                # Deps floor — FULL details, not discarded
                if compute_dependency_floor:
                    deps_floor, deps_details = compute_dependency_floor(
                        pr, module_path, lang_match or None,
                    )

                # Code floor — FULL features, not truncated
                if compute_code_floor:
                    code_floor_ver, code_features = compute_code_floor(
                        pr, module_path, lang_match or None,
                    )

                # Effective floor
                if compute_effective_floor:
                    effective = compute_effective_floor(
                        floor, deps_floor, code_floor_ver,
                    )

                # Verdict — with floor source for context-aware wording
                if compute_verdict:
                    verdict, verdict_detail = compute_verdict(
                        floor, deps_floor, code_floor_ver,
                        floor_source=floor_source,
                    )

            # ── Set all fields for frontend ──
            item["floor_source"] = floor_source or ""
            item["deps_floor"] = f"≥{deps_floor}" if deps_floor else "—"
            item["deps_details"] = deps_details  # full per-package breakdown
            item["code_floor"] = code_floor_ver or "—"
            item["code_features"] = code_features  # full list, not truncated
            item["effective_floor"] = f"≥{effective}" if effective else "—"
            item["verdict"] = verdict
            item["verdict_detail"] = verdict_detail

            # Range display — from effective floor to current
            range_floor = effective or floor
            if range_floor and current:
                item["range_display"] = f"{range_floor} — {current}"
            else:
                item["range_display"] = ""

            # Compat count — from effective floor
            if range_floor and current and compute_compat_range:
                lifecycle_key = _module_lang_to_lifecycle(lang_match)
                item["compat_count"] = compute_compat_range(
                    range_floor, current, lifecycle_key,
                )
            else:
                item["compat_count"] = 0

            # Floor health detail
            if rank == "dangerous" and cves:
                item["floor_detail"] = f"EOL {eol_date}, {len(cves)} CVE(s)"
            elif rank in ("outdated", "deprecated") and eol_date:
                item["floor_detail"] = f"EOL {eol_date}"
            elif rank == "current":
                item["floor_detail"] = "supported"
            elif rank == "na":
                item["floor_detail"] = ""
            else:
                item["floor_detail"] = item.get("detail", "")

            # Module metadata for tooltips
            item["module_meta"] = {
                "path": module_path,
                "domain": getattr(ref, "domain", "") if ref else "",
                "description": getattr(ref, "description", "") if ref else "",
            }

            # Stack metadata for tooltips
            stack_name = item.get("stack", "")
            if all_stacks and stack_name and stack_name in all_stacks:
                sdef = all_stacks[stack_name]
                item["stack_meta"] = {
                    "parent": sdef.parent,
                    "requires": [
                        {"adapter": r.adapter, "min_version": r.min_version}
                        for r in sdef.requires
                    ],
                    "capabilities": [c.name for c in sdef.capabilities],
                }
            else:
                item["stack_meta"] = {}

            # Floor tier analysis for tooltip
            item["floor_tiers"] = _build_floor_tiers(
                ref, floor, floor_source, _project_root, all_stacks,
            ) if ref and _project_root else {}

            # Decisions from project.yml — with computed flags
            deferral = getattr(ref, "deferral", None) if ref else None
            plan = getattr(ref, "version_plan", None) if ref else None

            if deferral and deferral.until:
                from src.core.services.system_posture.bridges.module_intel import (
                    is_deferral_expired,
                )
                item["deferral"] = {
                    "until": deferral.until,
                    "reason": deferral.reason,
                    "expired": is_deferral_expired(deferral.until),
                }
            else:
                item["deferral"] = None

            if plan and plan.target:
                from src.core.services.system_posture.bridges.module_intel import (
                    is_plan_met,
                    is_plan_overdue,
                )
                eff_raw = (effective or floor or "").replace("≥", "")
                item["version_plan"] = {
                    "target": plan.target,
                    "date": plan.date,
                    "overdue": is_plan_overdue(plan.date) if plan.date else False,
                    "met": is_plan_met(plan.target, eff_raw),
                    "checklist": [
                        {"label": s.label, "description": s.description, "done": s.done}
                        for s in (plan.checklist or [])
                    ],
                }
            else:
                item["version_plan"] = None

    # ── Platform — guide flags ─────────────────────────────────
    platform = pillars.get("platform", {})
    for item in platform.get("items", []):
        name = item.get("name", "")
        rank = item.get("rank", "")

        if rank in ("outdated", "deprecated", "dangerous"):
            # Platform items are named after distro/kernel/etc.
            # (e.g., "Ubuntu", "Kernel", "Debian", "CentOS")
            name_lower = name.lower()
            _platform_guide_names = {
                "ubuntu", "debian", "centos", "rhel", "fedora",
                "kernel", "glibc", "wsl",
            }
            if name_lower in _platform_guide_names or "os" in name_lower or "distro" in name_lower:
                item["actions"] = [{
                    "type": "guide",
                    "target": "os_upgrade",
                    "label": "Upgrade Guide",
                }]


def _manual_update_hint_simple(tool_id: str, recipe: dict) -> str:
    """Short manual update hint based on recipe install methods."""
    install_map = recipe.get("install", {})
    cli = recipe.get("cli", tool_id)

    if "pip" in install_map:
        return f"pip install --upgrade {cli}"
    if "npm" in install_map:
        return f"npm update -g {cli}"
    if "cargo" in install_map:
        return f"cargo install {cli}"
    if "brew" in install_map:
        return f"brew upgrade {cli}"
    if "apt" in install_map:
        return f"sudo apt update && sudo apt upgrade {cli}"

    return f"See official docs for {recipe.get('label', tool_id)}"


@posture_bp.route("/posture/summary")
def posture_summary():  # type: ignore[no-untyped-def]
    """Lightweight posture summary for the nav badge.

    Returns only overall rank and per-pillar ranks, without
    individual item details.  Designed for periodic polling
    (30s TTL in cache).

    Query params:
        bust=1  → Force rescan.

    Returns:
        200 with summary dict:
        - overall_rank, overall_status, overall_css_class
        - summary (human-readable string)
        - pillar_ranks: {platform, toolchain, project, runtime}
        - timestamp
    """
    force = request.args.get("bust", "") == "1"
    via = request.args.get("via", "")

    try:
        if via == "standalone":
            from src.core.services.system_posture import get_summary

            summary = get_summary(force=force)
            return jsonify(summary)
        else:
            # Default: use mediator (persisted, no TTL discard on load)
            from src.core.services.mediator import get_mediator

            m = get_mediator()
            if force:
                m.put("posture.summary", cascade=False)
            r = m.get("posture.summary", force=force)
            return jsonify(r["data"])
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@posture_bp.route("/posture/rescan", methods=["POST"])
@tracked("posture.rescanned")
def posture_rescan():  # type: ignore[no-untyped-def]
    """Force a full posture rescan.

    Invalidates all caches and runs a fresh scan.
    Returns the new full posture.
    """
    via = request.args.get("via", "")

    try:
        from src.core.services.mediator import get_mediator

        m = get_mediator()
        # Invalidate all pillar nodes + full + summary
        invalidated = []
        for path in ["posture.platform", "posture.toolchain", "posture.project",
                      "posture.runtime", "posture.modules"]:
            inv = m.put(path, cascade=True)
            invalidated.extend(inv.get("invalidated", []))
        r = m.get("posture.full", force=True)
        posture = r["data"]
        result = posture.to_dict()
        _enrich_posture_actions(result)
        result["cache_invalidated"] = invalidated

        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@posture_bp.route("/posture/rescan-tool", methods=["POST"])
@tracked("posture.tool.rescanned")
def posture_rescan_tool():  # type: ignore[no-untyped-def]
    """Lightweight single-tool cache invalidation.

    After updating one tool, invalidate only the toolchain and
    summary caches, then return the new summary for badge update.
    Much cheaper than a full rescan (~0.5s vs ~10s).

    Request body:
        {"tool": "go"}

    Returns:
        Fresh posture summary (same shape as ``/posture/summary``).
    """
    body = request.get_json(silent=True) or {}
    tool = body.get("tool", "")
    via = request.args.get("via", "")

    try:
        from src.core.services.mediator import get_mediator

        m = get_mediator()
        m.put("posture.toolchain", cascade=True)
        r = m.get("posture.summary", force=True)
        return jsonify(r["data"])
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


def _build_automation_meta(ref):
    """Build a lookup dict of automation metadata from the recipe JSON.

    Reads the recipe for the module's language and returns a dict
    mapping automation_id → {automatable, risk, category}.
    Used by plan-detail to enrich step responses.
    """
    meta = {}
    try:
        from src.core.services.detection import detect_language

        language = detect_language(ref.stack) if ref.stack else None
        if not language:
            return meta

        from src.core.services.module_upgrade.generator import _load_recipe

        recipe = _load_recipe(language)
        if not recipe:
            return meta

        # Collect from both upgrade and downgrade arrays
        for direction in ("upgrade", "downgrade"):
            for step in recipe.get(direction, []):
                aid = step.get("automation_id", "")
                if aid and aid not in meta:
                    meta[aid] = {
                        "automatable": step.get("automatable", False),
                        "risk": step.get("risk", "low"),
                        "category": step.get("category", ""),
                    }
    except Exception:
        pass  # graceful degradation — steps just won't show automation buttons

    return meta


def _build_floor_tiers(ref, floor, floor_source, project_root, all_stacks):
    """Build the 3-tier floor analysis for tooltip display."""
    from pathlib import Path as _Path

    tiers = {}
    pr = _Path(project_root) if project_root else None

    # Tier 1: module's own config
    tier1_found = False
    if pr and ref:
        mod_dir = pr / ref.path
        from src.core.services.detection import _extract_constraint_from_dir
        raw, _ = _extract_constraint_from_dir(mod_dir, ref.stack or "")
        tier1_found = raw is not None
        tiers["tier1"] = {
            "source": "module config",
            "found": tier1_found,
            "value": raw or "no config file in module directory",
        }

    # Tier 2: stack definition
    stack_name = ref.stack if ref else ""
    tier2_found = False
    tier2_value = ""
    if all_stacks and stack_name and stack_name in all_stacks:
        sdef = all_stacks[stack_name]
        for req in sdef.requires:
            if req.adapter in ("python", "node") and req.min_version:
                tier2_found = True
                tier2_value = f"{req.adapter} ≥{req.min_version}"
                break
    tiers["tier2"] = {
        "source": "stack definition",
        "found": tier2_found,
        "value": tier2_value or "no runtime requirement in stack",
        "stack_name": stack_name,
    }

    # Tier 3: project root config
    tier3_found = False
    if pr:
        from src.core.services.detection import _extract_constraint_from_dir
        raw, _ = _extract_constraint_from_dir(pr, ref.stack or "")
        tier3_found = raw is not None
        tiers["tier3"] = {
            "source": "project root",
            "found": tier3_found,
            "value": raw or "no constraint in root config",
        }

    tiers["used"] = floor_source or ""
    return tiers


def _module_lang_to_lifecycle(lang: str) -> str:
    """Map display language name to lifecycle key."""
    return {
        "python": "python",
        "javascript": "node",
        "typescript": "node",
        "go": "go",
        "rust": "rust",
        "ruby": "ruby",
        "java": "java",
        "csharp": "dotnet",
        "php": "php",
        "elixir": "elixir",
    }.get(lang, lang)


@posture_bp.route("/posture/module-fix-floor", methods=["POST"])
@tracked("posture.module.floor_fixed")
def posture_module_fix_floor():  # type: ignore[no-untyped-def]
    """Create or update a module's pyproject.toml with requires-python.

    Body: {module, target_floor, preview (bool)}
    If preview=true: returns the file content without writing.
    If preview=false: writes the file and invalidates posture.
    """
    body = request.get_json(silent=True) or {}
    module_name = body.get("module", "")
    target_floor = body.get("target_floor", "")
    preview_only = body.get("preview", True)

    if not module_name or not target_floor:
        return jsonify({"error": "module and target_floor required"}), 400

    try:
        from pathlib import Path as _Path

        from src.core.config.loader import load_project

        project = load_project()
        ref = project.get_module(module_name)
        if not ref:
            return jsonify({"error": f"module '{module_name}' not found"}), 404

        project_root = _Path(current_app.config.get("PROJECT_ROOT", "."))
        target_path = project_root / ref.path / "pyproject.toml"
        rel_path = str(target_path.relative_to(project_root))

        if target_path.is_file():
            # Modify existing
            content = target_path.read_text(encoding="utf-8")
            import re as _re
            if _re.search(r'requires-python\s*=', content):
                new_content = _re.sub(
                    r'requires-python\s*=\s*"[^"]*"',
                    f'requires-python = ">={target_floor}"',
                    content,
                )
            else:
                # Add under [project] section
                new_content = content.rstrip() + f'\nrequires-python = ">={target_floor}"\n'
            is_new = False
        else:
            # Create minimal pyproject.toml
            new_content = (
                f'[project]\n'
                f'name = "{module_name}"\n'
                f'requires-python = ">={target_floor}"\n'
            )
            is_new = True

        result = {"path": rel_path, "content": new_content, "is_new": is_new}

        if preview_only:
            return jsonify({"preview": result})

        # Apply
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(new_content, encoding="utf-8")

        # Invalidate posture
        from src.core.services.mediator import get_mediator
        get_mediator().put("posture.modules", cascade=True)

        return jsonify({"applied": True, "path": rel_path})

    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@posture_bp.route("/posture/module-dep-alternatives", methods=["POST"])
@tracked("posture.module.dep_alternatives")
def posture_module_dep_alternatives():  # type: ignore[no-untyped-def]
    """Find older versions of a dep that support a target Python floor.

    Body: {package, target_python}
    Queries PyPI JSON API for all versions and filters by requires_python.
    """
    body = request.get_json(silent=True) or {}
    package = body.get("package", "")
    target_python = body.get("target_python", "")

    if not package or not target_python:
        return jsonify({"error": "package and target_python required"}), 400

    try:
        import re as _re
        import urllib.request

        url = f"https://pypi.org/pypi/{package}/json"
        with urllib.request.urlopen(url, timeout=10) as resp:
            import json
            data = json.loads(resp.read().decode())

        current_version = data.get("info", {}).get("version", "")
        releases = data.get("releases", {})
        target_parts = [int(x) for x in target_python.split(".")]

        alternatives = []
        for ver, files in releases.items():
            if not files:
                continue
            # Skip pre-releases
            if any(c in ver for c in ("a", "b", "rc", "dev", "post")):
                continue

            # Find requires_python from the first file with metadata
            requires_python = None
            for f in files:
                rp = f.get("requires_python")
                if rp:
                    requires_python = rp
                    break

            if not requires_python:
                continue

            # Check if target_python satisfies requires_python
            match = _re.search(r">=\s*(\d+(?:\.\d+)*)", requires_python)
            if not match:
                continue
            req_parts = [int(x) for x in match.group(1).split(".")]

            if target_parts >= req_parts:
                # This version supports our target python
                try:
                    ver_parts = [int(x) for x in ver.split(".")]
                    cur_parts = [int(x) for x in current_version.split(".")]
                    behind = 0
                    if len(cur_parts) >= 2 and len(ver_parts) >= 2:
                        if cur_parts[0] == ver_parts[0]:
                            behind = cur_parts[1] - ver_parts[1]
                        else:
                            behind = abs(cur_parts[0] - ver_parts[0]) * 10
                except (ValueError, IndexError):
                    behind = 0

                alternatives.append({
                    "version": ver,
                    "requires_python": requires_python,
                    "versions_behind": behind,
                    "breaking": ver.split(".")[0] != current_version.split(".")[0],
                })

        # Sort by version descending (latest compatible first)
        alternatives.sort(
            key=lambda a: [int(x) for x in a["version"].split(".")[:3] if x.isdigit()],
            reverse=True,
        )

        return jsonify({
            "package": package,
            "current_version": current_version,
            "target_python": target_python,
            "alternatives": alternatives[:10],
        })

    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@posture_bp.route("/posture/module-defer", methods=["POST"])
@tracked("posture.module.deferred")
def posture_module_defer():  # type: ignore[no-untyped-def]
    """Defer a module posture warning until a date.

    Body: {module, until, reason}
    Writes deferral object to the module in project.yml.
    """
    body = request.get_json(silent=True) or {}
    module_name = body.get("module", "")
    until = body.get("until", "")
    reason = body.get("reason", "")

    if not module_name or not until:
        return jsonify({"error": "module and until required"}), 400

    try:
        import yaml
        from src.core.config.loader import find_project_file

        config_path = find_project_file()
        if not config_path:
            return jsonify({"error": "project.yml not found"}), 404

        raw = config_path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw)
        project_data = data.get("project", data) if "project" in data else data

        found = False
        for mod in project_data.get("modules", []):
            if mod.get("name") == module_name:
                mod["deferral"] = {"until": until, "reason": reason}
                found = True
                break

        if not found:
            return jsonify({"error": f"module '{module_name}' not found"}), 404

        config_path.write_text(
            yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

        from src.core.services.mediator import get_mediator
        get_mediator().put("posture.modules", cascade=True)

        return jsonify({"ok": True, "module": module_name, "deferred_until": until})

    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@posture_bp.route("/posture/module-clear-defer", methods=["POST"])
@tracked("posture.module.deferral_cleared")
def posture_module_clear_defer():  # type: ignore[no-untyped-def]
    """Clear a module's deferral from project.yml.

    Body: {module}
    Removes the deferral object from the module.
    """
    body = request.get_json(silent=True) or {}
    module_name = body.get("module", "")

    if not module_name:
        return jsonify({"error": "module required"}), 400

    try:
        import yaml
        from src.core.config.loader import find_project_file

        config_path = find_project_file()
        if not config_path:
            return jsonify({"error": "project.yml not found"}), 404

        raw = config_path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw)
        project_data = data.get("project", data) if "project" in data else data

        found = False
        for mod in project_data.get("modules", []):
            if mod.get("name") == module_name:
                mod.pop("deferral", None)
                found = True
                break

        if not found:
            return jsonify({"error": f"module '{module_name}' not found"}), 404

        config_path.write_text(
            yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

        from src.core.services.mediator import get_mediator
        get_mediator().put("posture.modules", cascade=True)

        return jsonify({"ok": True, "module": module_name})

    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@posture_bp.route("/posture/module-plan", methods=["POST"])
@tracked("posture.module.plan_created")
def posture_module_plan():  # type: ignore[no-untyped-def]
    """Create or update a version upgrade plan for a module.

    Body: {module, target_floor, target_date}
    Writes version_plan object to the module in project.yml.
    """
    body = request.get_json(silent=True) or {}
    module_name = body.get("module", "")
    target_floor = body.get("target_floor", "")
    target_date = body.get("target_date", "")

    if not module_name:
        return jsonify({"error": "module required"}), 400

    try:
        import yaml
        from pathlib import Path as _Path
        from src.core.config.loader import find_project_file

        config_path = find_project_file()
        if not config_path:
            return jsonify({"error": "project.yml not found"}), 404

        raw = config_path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw)
        project_data = data.get("project", data) if "project" in data else data

        found = False
        for mod in project_data.get("modules", []):
            if mod.get("name") == module_name:
                if not target_floor:
                    # Clear plan
                    mod.pop("version_plan", None)
                else:
                    # Generate context-aware checklist from recipe
                    from src.core.services.module_upgrade import generate_checklist

                    project_root = _Path(
                        current_app.config.get("PROJECT_ROOT", "."),
                    )
                    checklist_steps = generate_checklist(
                        module_name, target_floor, project_root,
                    )
                    mod["version_plan"] = {
                        "target": target_floor,
                        "date": target_date,
                        "checklist": checklist_steps,
                    }
                found = True
                break

        if not found:
            return jsonify({"error": f"module '{module_name}' not found"}), 404

        config_path.write_text(
            yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

        from src.core.services.mediator import get_mediator
        get_mediator().put("posture.modules", cascade=True)

        return jsonify({"ok": True, "module": module_name, "target_floor": target_floor})

    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@posture_bp.route("/posture/module-plan-detail")
def posture_module_plan_detail():  # type: ignore[no-untyped-def]
    """Get full plan detail for a module.

    Query: ?module=core
    Returns plan from project.yml with checklist steps and their done status.
    """
    module_name = request.args.get("module", "")
    if not module_name:
        return jsonify({"error": "module required"}), 400

    try:
        from src.core.config.loader import load_project

        project = load_project()
        ref = project.get_module(module_name)
        if not ref or not ref.version_plan:
            return jsonify({"error": "no plan found"}), 404

        plan = ref.version_plan

        # Build automation metadata lookup from recipe
        auto_meta = _build_automation_meta(ref)

        checklist = []
        for s in plan.checklist:
            # Extract automation_id from step id prefix
            aid = s.id.split(":")[0] if s.id and ":" in s.id else ""
            meta = auto_meta.get(aid, {})
            checklist.append({
                "id": s.id,
                "label": s.label,
                "description": s.description,
                "done": s.done,
                "automatable": meta.get("automatable", False),
                "automation_id": aid if aid not in ("manual", "custom", "") else "",
                "risk": meta.get("risk", "low"),
                "category": meta.get("category", ""),
            })

        result = {
            "target": plan.target,
            "date": plan.date,
            "checklist": checklist,
        }
        return jsonify(result)

    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@posture_bp.route("/posture/module-plan-progress", methods=["PATCH"])
def posture_module_plan_progress():  # type: ignore[no-untyped-def]
    """Toggle a plan step's done status.

    Body: {module, step_index, done}
    Updates the checklist step's done field in project.yml.
    """
    body = request.get_json(silent=True) or {}
    module_name = body.get("module", "")
    step_index = body.get("step_index")
    done = body.get("done", False)

    if not module_name or step_index is None:
        return jsonify({"error": "module and step_index required"}), 400

    try:
        import yaml
        from src.core.config.loader import find_project_file

        config_path = find_project_file()
        if not config_path:
            return jsonify({"error": "project.yml not found"}), 404

        raw = config_path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw)
        project_data = data.get("project", data) if "project" in data else data

        found = False
        for mod in project_data.get("modules", []):
            if mod.get("name") == module_name:
                plan = mod.get("version_plan")
                if not plan or "checklist" not in plan:
                    return jsonify({"error": "no checklist found"}), 404
                idx = int(step_index)
                if 0 <= idx < len(plan["checklist"]):
                    plan["checklist"][idx]["done"] = done
                    found = True
                else:
                    return jsonify({"error": "step_index out of range"}), 400
                break

        if not found:
            return jsonify({"error": f"module '{module_name}' not found"}), 404

        config_path.write_text(
            yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

        from src.core.services.mediator import get_mediator
        get_mediator().put("posture.modules", cascade=True)

        return jsonify({"ok": True, "step_index": step_index, "done": done})

    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@posture_bp.route("/posture/module-plan-step", methods=["POST"])
@tracked("posture.module.plan_step_added")
def posture_module_plan_add_step():  # type: ignore[no-untyped-def]
    """Add a custom step to a module's version plan checklist.

    Body: {module, label, description?}
    Adds to project.yml version_plan.checklist.
    """
    body = request.get_json(silent=True) or {}
    module_name = body.get("module", "")
    label = body.get("label", "")
    description = body.get("description", "")

    if not module_name or not label:
        return jsonify({"error": "module and label required"}), 400

    try:
        import uuid as _uuid
        import yaml
        from src.core.config.loader import find_project_file

        config_path = find_project_file()
        if not config_path:
            return jsonify({"error": "project.yml not found"}), 404

        raw = config_path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw)
        project_data = data.get("project", data) if "project" in data else data

        found = False
        for mod in project_data.get("modules", []):
            if mod.get("name") == module_name:
                plan = mod.get("version_plan")
                if not plan:
                    return jsonify({"error": "no plan exists for this module"}), 404
                plan.setdefault("checklist", [])
                step_id = f"custom:{_uuid.uuid4().hex[:8]}"
                step_entry = {"id": step_id, "label": label}
                if description:
                    step_entry["description"] = description
                plan["checklist"].append(step_entry)
                found = True
                break

        if not found:
            return jsonify({"error": f"module '{module_name}' not found"}), 404

        config_path.write_text(
            yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

        from src.core.services.mediator import get_mediator
        get_mediator().put("posture.modules", cascade=True)

        return jsonify({"ok": True, "module": module_name, "label": label})

    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@posture_bp.route("/posture/module-plan-step", methods=["DELETE"])
@tracked("posture.module.plan_step_removed")
def posture_module_plan_remove_step():  # type: ignore[no-untyped-def]
    """Remove a step from a module's version plan checklist.

    Body: {module, step_index}
    Removes from project.yml version_plan.checklist.
    """
    body = request.get_json(silent=True) or {}
    module_name = body.get("module", "")
    step_index = body.get("step_index")

    if not module_name or step_index is None:
        return jsonify({"error": "module and step_index required"}), 400

    try:
        import yaml
        from src.core.config.loader import find_project_file

        config_path = find_project_file()
        if not config_path:
            return jsonify({"error": "project.yml not found"}), 404

        raw = config_path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw)
        project_data = data.get("project", data) if "project" in data else data

        found = False
        for mod in project_data.get("modules", []):
            if mod.get("name") == module_name:
                plan = mod.get("version_plan")
                if not plan or "checklist" not in plan:
                    return jsonify({"error": "no checklist found"}), 404
                idx = int(step_index)
                if 0 <= idx < len(plan["checklist"]):
                    plan["checklist"].pop(idx)
                    found = True
                else:
                    return jsonify({"error": "step_index out of range"}), 400
                break

        if not found:
            return jsonify({"error": f"module '{module_name}' not found"}), 404

        config_path.write_text(
            yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

        from src.core.services.mediator import get_mediator
        get_mediator().put("posture.modules", cascade=True)

        return jsonify({"ok": True, "module": module_name})

    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@posture_bp.route("/posture/module-step-execute", methods=["POST"])
@tracked("posture.module.step_executed")
def posture_module_step_execute():  # type: ignore[no-untyped-def]
    """Execute an automation step in preview or execute mode.

    Body: {module, step_id, mode}
      - module: module name from project.yml
      - step_id: step ID (format: automation_id:suffix)
      - mode: "preview" or "execute"

    Preview returns what would change. Execute performs the action
    and marks the step done in project.yml.
    """
    body = request.get_json(silent=True) or {}
    module_name = body.get("module", "")
    step_id = body.get("step_id", "")
    mode = body.get("mode", "preview")

    if not module_name or not step_id:
        return jsonify({"error": "module and step_id required"}), 400
    if mode not in ("preview", "execute"):
        return jsonify({"error": "mode must be 'preview' or 'execute'"}), 400

    try:
        from pathlib import Path as _Path

        from src.core.services.module_upgrade.automation.executor import execute_step

        project_root = _Path(current_app.config.get("PROJECT_ROOT", "."))
        result = execute_step(module_name, step_id, mode, project_root)

        status_code = 200 if result.get("ok") else 400
        return jsonify(result), status_code

    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@posture_bp.route("/posture/module-note", methods=["POST"])
@tracked("posture.module.noted")
def posture_module_note():  # type: ignore[no-untyped-def]
    """Update version_note or version_strategy for a module in project.yml.

    Request body:
        {"module": "core", "version_note": "...", "version_strategy": "compatibility"}

    At least one of version_note or version_strategy must be provided.
    Updates the ModuleRef in project.yml and invalidates posture caches.
    """
    body = request.get_json(silent=True) or {}
    module_name = body.get("module", "")
    note = body.get("version_note")
    strategy = body.get("version_strategy")

    if not module_name:
        return jsonify({"error": "module name required"}), 400
    if note is None and strategy is None:
        return jsonify({"error": "version_note or version_strategy required"}), 400

    try:
        from pathlib import Path as _Path

        from src.core.config.loader import find_project_file

        import yaml

        config_path = find_project_file()
        if not config_path:
            return jsonify({"error": "project.yml not found"}), 404

        # Read, modify, write
        raw = config_path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw)

        # Find module in the YAML data
        project_data = data.get("project", data) if "project" in data else data
        modules_list = project_data.get("modules", [])

        found = False
        for mod in modules_list:
            if mod.get("name") == module_name:
                if note is not None:
                    mod["version_note"] = note
                if strategy is not None:
                    if strategy not in ("latest", "compatibility", ""):
                        return jsonify({"error": f"invalid strategy: {strategy}"}), 400
                    if strategy:
                        mod["version_strategy"] = strategy
                    elif "version_strategy" in mod:
                        del mod["version_strategy"]
                found = True
                break

        if not found:
            return jsonify({"error": f"module '{module_name}' not found in project.yml"}), 404

        # Write back
        config_path.write_text(
            yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

        # Invalidate posture caches
        from src.core.services.mediator import get_mediator
        get_mediator().put("posture.modules", cascade=True)

        return jsonify({
            "ok": True,
            "module": module_name,
            "version_note": note,
            "version_strategy": strategy,
        })

    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@posture_bp.route("/posture/cache")
def posture_cache():  # type: ignore[no-untyped-def]
    """Cache diagnostics for posture data.

    Returns per-key cache statistics:
    - age_s:     Seconds since last computation
    - ttl_s:     Configured TTL
    - fresh:     Whether the cached value is still within TTL
    - elapsed_s: How long the last computation took
    """
    from src.core.services.system_posture import cache_stats

    try:
        return jsonify(cache_stats())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
