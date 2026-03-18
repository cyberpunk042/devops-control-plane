"""
Module stack health bridge — evaluates module runtime constraints.

This bridge reads module detection results and evaluates each module's
runtime version constraint against lifecycle data:
  - What's the constraint floor? (e.g. >=3.8 → floor is 3.8)
  - Is the floor still receiving security patches?
  - Does the floor have known CVEs?
  - How wide is the compatibility range?

Two strategies determine the lens:
  - "latest": module tracks current ecosystem version
  - "compatibility": module deliberately supports a wide range

The bridge does NOT reuse rank_tool_version(). Module floor health
answers a different question than tool version ranking.

Why a bridge, not a scanner?
  The data already exists — detection results and lifecycle JSON.
  No subprocess calls needed.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from ..models import PillarResult, PostureItem, RankLevel

logger = logging.getLogger(__name__)

# Map language → lifecycle key
_LANGUAGE_MAP: dict[str, str] = {
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
}


def bridge_modules(project_root: Path | None = None) -> PillarResult:
    """Bridge module detection results into posture format.

    Reads detection state and project config, evaluates each module's
    runtime constraint floor against lifecycle data.

    Returns:
        PillarResult with one PostureItem per module that has a
        runtime constraint, plus floor advisories.
    """
    if project_root is None:
        project_root = _get_project_root()

    if project_root is None:
        return PillarResult(
            pillar="modules",
            rank=RankLevel.UNKNOWN,
            warnings=["No project root detected"],
        )

    # Load data
    lifecycle_db = _load_lifecycle_db()
    modules_data = _load_module_data(project_root)

    if not modules_data:
        return PillarResult(
            pillar="modules",
            rank=RankLevel.CURRENT,
            items=[PostureItem(
                name="modules",
                value="—",
                rank=RankLevel.CURRENT,
                detail="No modules with runtime constraints detected",
            )],
        )

    items: list[PostureItem] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    # Import intel functions for deep analysis
    from .module_intel import (
        compute_code_floor,
        compute_dependency_floor,
        compute_effective_floor,
        compute_verdict,
        is_deferral_expired,
        is_plan_met,
        is_plan_overdue,
    )

    for mod in modules_data:
        name = mod["name"]
        language = mod.get("language")
        floor = mod.get("runtime_floor")
        constraint = mod.get("runtime_constraint")
        module_path = mod.get("module_path", "")
        strategy_explicit = mod.get("version_strategy", "")
        note = mod.get("version_note", "")

        # No constraint or no language → show as n/a
        if not floor or not language:
            items.append(PostureItem(
                name=name,
                value="—",
                rank=RankLevel.NA,
                detail="No runtime constraint detected",
            ))
            continue

        # Map language to lifecycle key
        lifecycle_key = _LANGUAGE_MAP.get(language)
        if not lifecycle_key or lifecycle_key not in lifecycle_db:
            items.append(PostureItem(
                name=f"{name} ({language})",
                value=constraint or floor,
                rank=RankLevel.UNKNOWN,
                detail=f"No lifecycle data for {language}",
            ))
            continue

        lifecycle = lifecycle_db[lifecycle_key]
        current = lifecycle.get("current", "")

        # Strategy deduction
        strategy, deduced = _resolve_strategy(
            strategy_explicit, floor, current, lifecycle_key,
        )

        # ── Deep analysis: deps floor + code floor ────────────
        deps_floor, deps_details = compute_dependency_floor(
            project_root, module_path, language,
        )
        code_floor, code_features = compute_code_floor(
            project_root, module_path, language,
        )
        effective = compute_effective_floor(floor, deps_floor, code_floor)
        floor_source = mod.get("runtime_floor_source")
        verdict, verdict_detail = compute_verdict(
            floor, deps_floor, code_floor, floor_source=floor_source,
        )

        # Floor health — evaluate against the EFFECTIVE floor, not just declared
        eval_floor = effective or floor
        floor_rank, floor_detail, floor_eol, floor_cves = check_floor_health(
            eval_floor, lifecycle,
        )

        # Compatibility range — from effective floor to current
        compat_count = compute_compat_range(
            eval_floor, current, lifecycle_key,
        )

        # Build detail string (for fallback / debugging)
        detail_parts = [f"declared {floor}"]
        if deps_floor:
            detail_parts.append(f"deps {deps_floor}")
        if code_floor:
            detail_parts.append(f"code {code_floor}")
        if effective and effective != floor:
            detail_parts.append(f"effective {effective}")

        item = PostureItem(
            name=f"{name} ({language})",
            value=f"≥{floor}",
            rank=floor_rank,
            detail=" · ".join(detail_parts),
            current_version=current,
            eol_date=floor_eol,
            cves=floor_cves,
        )
        items.append(item)

        # Store deep analysis results in module data for enrichment to pick up
        mod["_deps_floor"] = deps_floor
        mod["_code_floor"] = code_floor
        mod["_effective_floor"] = effective
        mod["_verdict"] = verdict
        mod["_verdict_detail"] = verdict_detail
        mod["_compat_count"] = compat_count
        mod["_code_features"] = code_features[:3] if code_features else []

        # ── Check decisions: deferral + plan ─────────────────
        deferral = mod.get("deferral")
        plan = mod.get("version_plan")
        is_deferred_active = False

        if deferral:
            expired = is_deferral_expired(deferral.get("until", ""))
            deferral["expired"] = expired
            if not expired:
                is_deferred_active = True
            else:
                warnings.append(
                    f"{name}: ⏰ deferral expired (was deferred until "
                    f"{deferral.get('until', '?')} because: {deferral.get('reason', '?')})"
                )

        if plan:
            plan_target = plan.get("target", "")
            plan_date = plan.get("date", "")
            plan["overdue"] = is_plan_overdue(plan_date) if plan_date else False
            plan["met"] = is_plan_met(plan_target, effective or floor) if plan_target else False
            if plan["overdue"] and not plan["met"]:
                warnings.append(
                    f"{name}: ⏰ version plan overdue — target ≥{plan_target} "
                    f"by {plan_date}, currently at {effective or floor}"
                )

        # Floor advisories — suppress for actively deferred modules
        if not is_deferred_active:
            if floor_rank == RankLevel.DANGEROUS:
                warnings.append(
                    f"{name}: {language} {eval_floor} has known CVEs — "
                    f"deployments on {eval_floor} are exposed"
                )
            elif floor_rank in (RankLevel.OUTDATED, RankLevel.DEPRECATED):
                warnings.append(
                    f"{name}: {language} {eval_floor} no longer receives "
                    f"security patches ({floor_detail})"
                )

            # Verdict warnings
            if verdict == "gap":
                warnings.append(f"{name}: ⚠️ {verdict_detail}")

        # Notes always visible when set
        if note:
            recommendations.append(f"{name}: 📝 {note}")
        elif deduced:
            recommendations.append(
                f"{name}: strategy deduced from constraint gap — "
                f"set version_strategy in project.yml"
            )

    from ..ranking import worst_rank

    return PillarResult(
        pillar="modules",
        rank=worst_rank(items) if items else RankLevel.UNKNOWN,
        items=items,
        warnings=warnings,
        recommendations=recommendations,
    )


def check_floor_health(
    floor: str,
    lifecycle: dict,
) -> tuple[RankLevel, str, str, list[str]]:
    """Evaluate the health of a module's constraint floor version.

    Returns (rank, detail, eol_date, cves):
      - rank: RankLevel based on floor status
      - detail: human-readable explanation
      - eol_date: YYYY-MM if floor is EOL, else ""
      - cves: list of CVE IDs if any
    """
    eol_versions = lifecycle.get("eol_versions", {})
    min_supported = lifecycle.get("min_supported", "")

    # Check exact floor match first, then major.minor, then major
    floor_parts = floor.split(".")
    candidates = [floor]
    if len(floor_parts) >= 2:
        candidates.append(f"{floor_parts[0]}.{floor_parts[1]}")
    candidates.append(floor_parts[0])

    for candidate in candidates:
        if candidate in eol_versions:
            entry = eol_versions[candidate]

            if isinstance(entry, dict):
                eol_date = entry.get("eol", "")
                cves = entry.get("cves", [])
                if cves:
                    return (
                        RankLevel.DANGEROUS,
                        f"EOL {eol_date}, {len(cves)} known CVE(s)",
                        eol_date,
                        cves,
                    )
                return (
                    RankLevel.OUTDATED,
                    f"EOL {eol_date}",
                    eol_date,
                    [],
                )
            else:
                # entry is a date string
                return (
                    RankLevel.OUTDATED,
                    f"EOL {entry}",
                    str(entry),
                    [],
                )

    # Check min_supported
    if min_supported and _version_lt(floor, min_supported):
        return (
            RankLevel.OUTDATED,
            f"Below minimum supported ({min_supported})",
            "",
            [],
        )

    return (RankLevel.CURRENT, "floor supported", "", [])


def compute_compat_range(
    floor: str,
    current: str,
    language: str,
) -> int:
    """Count the number of versions between floor and current.

    This is a rough estimate — counts minor versions for most
    languages, major versions for node.
    """
    try:
        floor_parts = [int(x) for x in floor.split(".")]
        current_parts = [int(x) for x in current.split(".")]
    except (ValueError, IndexError):
        return 0

    if language == "node":
        # Node uses major versions (16, 18, 20, 22)
        # Count even numbers (LTS) between floor and current
        f_major = floor_parts[0]
        c_major = current_parts[0]
        count = 0
        for v in range(f_major, c_major + 1):
            if v % 2 == 0:  # LTS only
                count += 1
        return max(count, 1)

    if language == "go":
        # Go uses 1.X minor versions
        if len(floor_parts) >= 2 and len(current_parts) >= 2:
            return current_parts[1] - floor_parts[1] + 1
        return 1

    # Python, rust, ruby, java, php, elixir: minor versions
    if len(floor_parts) >= 2 and len(current_parts) >= 2:
        if floor_parts[0] == current_parts[0]:
            return current_parts[1] - floor_parts[1] + 1
        # Cross-major: rough estimate
        return abs(current_parts[1] - floor_parts[1]) + 1

    return 1


def deduce_strategy(
    floor: str,
    current: str,
    language: str,
) -> tuple[str, bool]:
    """Deduce version strategy from constraint gap.

    Returns (strategy, is_deduced):
      - strategy: "latest" or "compatibility"
      - is_deduced: True (always, since this is deduction)
    """
    gap = compute_compat_range(floor, current, language) - 1

    if gap <= 2:
        return "latest", True
    elif gap >= 4:
        return "compatibility", True
    else:
        # Ambiguous — default to compatibility with deduced marker
        return "compatibility", True


# ── Internal helpers ──────────────────────────────────────────────


def _resolve_strategy(
    explicit: str,
    floor: str,
    current: str,
    language: str,
) -> tuple[str, bool]:
    """Resolve strategy: explicit from project.yml wins, otherwise deduce.

    Returns (strategy, is_deduced).
    """
    if explicit in ("latest", "compatibility"):
        return explicit, False
    return deduce_strategy(floor, current, language)


def _version_lt(a: str, b: str) -> bool:
    """Compare two version strings: is a < b?"""
    try:
        a_parts = [int(x) for x in a.split(".")]
        b_parts = [int(x) for x in b.split(".")]
        return a_parts < b_parts
    except (ValueError, IndexError):
        return False


def _load_lifecycle_db() -> dict:
    """Load module lifecycle data from JSON."""
    data_path = Path(__file__).parent.parent / "data" / "module_lifecycle.json"
    try:
        with open(data_path, encoding="utf-8") as f:
            data = json.load(f)
        # Remove meta key
        return {k: v for k, v in data.items() if k != "_meta"}
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Failed to load module lifecycle data: %s", exc)
        return {}


def _load_module_data(project_root: Path) -> list[dict]:
    """Load module detection results and project config.

    Merges detection state (runtime_floor, language) with project
    config (version_strategy, version_note) per module.
    """
    modules = []

    try:
        from src.core.config.loader import load_project
        from src.core.persistence.state_file import default_state_path, load_state

        # Load project config for version_strategy + version_note
        project = load_project()
        module_refs = {ref.name: ref for ref in project.modules}

        # Load detection state for runtime_floor + language
        state_path = default_state_path(project_root)
        state = load_state(state_path)

        # Load stacks for tier-2 detection (stack requires)
        from src.core.config.stack_loader import discover_stacks
        all_stacks = discover_stacks()

        for name, mod_state in state.modules.items():
            ref = module_refs.get(name)
            deferral = getattr(ref, "deferral", None) if ref else None
            plan = getattr(ref, "version_plan", None) if ref else None

            entry = {
                "name": name,
                "stack": mod_state.stack or "",
                "module_path": ref.path if ref else name,
                "language": None,
                "runtime_floor": None,
                "runtime_constraint": None,
                "runtime_floor_source": None,
                "version_strategy": getattr(ref, "version_strategy", "") if ref else "",
                "version_note": getattr(ref, "version_note", "") if ref else "",
                "deferral": {
                    "until": deferral.until,
                    "reason": deferral.reason,
                } if deferral and deferral.until else None,
                "version_plan": {
                    "target": plan.target,
                    "date": plan.date,
                } if plan and plan.target else None,
            }

            if mod_state.detected and mod_state.stack:
                mod_dir = project_root / (ref.path if ref else name)
                if mod_dir.is_dir():
                    from src.core.services.detection import (
                        detect_language,
                        detect_runtime_constraint,
                    )

                    language = detect_language(mod_state.stack)
                    constraint, floor, source = detect_runtime_constraint(
                        mod_dir, mod_state.stack,
                        project_root=project_root,
                        stacks=all_stacks,
                    )
                    entry["language"] = language
                    entry["runtime_floor"] = floor
                    entry["runtime_constraint"] = constraint
                    entry["runtime_floor_source"] = source

            modules.append(entry)

    except Exception as exc:
        logger.error("Failed to load module data: %s", exc)

    return modules


def _get_project_root() -> Path | None:
    """Get project root from context, if available."""
    try:
        from src.core.context import get_project_root
        return get_project_root()
    except Exception:
        return None
