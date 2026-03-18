"""
Upgrade context builder — collects module intelligence into one object.

The UpgradeContext captures everything the generator needs to produce
a context-aware checklist: floors, verdict, strategy, file presence,
and direction (upgrade vs downgrade).

All data comes from existing intelligence layers — this module is
a pure consumer, not a new intelligence source.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class UpgradeContext:
    """Everything the generator needs to produce a checklist.

    Built from existing module intelligence (detection, module_intel,
    project config). All fields are read-only inputs — the context
    does not mutate any state.
    """

    # Module identity
    module_name: str = ""
    language: str = ""
    stack: str = ""
    module_path: str = ""
    project_root: Path = field(default_factory=lambda: Path("."))

    # Version floors
    current_floor: str = ""
    target_floor: str = ""
    direction: str = ""           # "upgrade" | "downgrade"
    floor_source: str = ""        # "module" | "stack" | "project"

    # Deep analysis
    deps_floor: str | None = None
    code_floor: str | None = None
    code_features: list[dict] = field(default_factory=list)
    effective_floor: str = ""
    verdict: str = ""             # "gap" | "could_lower" | "consistent" | "unknown"

    # Strategy
    strategy: str = ""            # "latest" | "compatibility" | ""

    # File presence in module directory
    has_future_import: bool = False
    has_pyproject: bool = False
    has_setup_py: bool = False
    has_setup_cfg: bool = False
    has_requirements_txt: bool = False
    has_package_json: bool = False
    has_go_mod: bool = False
    has_cargo_toml: bool = False
    has_gemfile: bool = False
    has_composer_json: bool = False
    has_mix_exs: bool = False
    has_pom_xml: bool = False
    has_build_gradle: bool = False
    has_csproj: bool = False


def build_context(
    module_name: str,
    target: str,
    project_root: Path,
) -> UpgradeContext:
    """Build an UpgradeContext from module intelligence.

    Calls into existing detection and analysis systems to gather
    all data the generator needs. All imports are lazy to prevent
    circular dependency chains (follows project convention).

    Args:
        module_name: Name of the module (matches project.yml).
        target: Target floor version (e.g. "3.12").
        project_root: Absolute path to project root.

    Returns:
        Fully populated UpgradeContext.
    """
    ctx = UpgradeContext(
        module_name=module_name,
        target_floor=target,
        project_root=project_root,
    )

    # ── Load project config ──────────────────────────────────────
    try:
        from src.core.config.loader import load_project

        project = load_project()
        ref = project.get_module(module_name)
    except Exception as exc:
        logger.warning("Failed to load project config: %s", exc)
        return ctx

    if not ref:
        logger.warning("Module '%s' not found in project.yml", module_name)
        return ctx

    ctx.module_path = ref.path
    ctx.stack = ref.stack
    ctx.strategy = ref.version_strategy or ""

    # ── Detect language ──────────────────────────────────────────
    try:
        from src.core.services.detection import detect_language

        ctx.language = detect_language(ref.stack) or ""
    except Exception as exc:
        logger.warning("Failed to detect language: %s", exc)

    # ── Detect runtime constraint (3-tier) ───────────────────────
    module_dir = project_root / ref.path
    if module_dir.is_dir() and ref.stack:
        try:
            from src.core.config.stack_loader import discover_stacks
            from src.core.services.detection import detect_runtime_constraint

            stacks = discover_stacks()
            _constraint, floor, source = detect_runtime_constraint(
                module_dir, ref.stack,
                project_root=project_root,
                stacks=stacks,
            )
            ctx.current_floor = floor or ""
            ctx.floor_source = source or ""
        except Exception as exc:
            logger.warning("Failed to detect runtime constraint: %s", exc)

    # ── Direction ────────────────────────────────────────────────
    ctx.direction = _compute_direction(ctx.current_floor, target)

    # ── Deep analysis (deps floor, code floor, verdict) ──────────
    if ctx.language:
        try:
            from src.core.services.system_posture.bridges.module_intel import (
                compute_code_floor,
                compute_dependency_floor,
                compute_effective_floor,
                compute_verdict,
            )

            deps_floor, _deps_details = compute_dependency_floor(
                project_root, ref.path, ctx.language,
            )
            ctx.deps_floor = deps_floor

            code_floor, code_features = compute_code_floor(
                project_root, ref.path, ctx.language,
            )
            ctx.code_floor = code_floor
            ctx.code_features = code_features or []

            ctx.effective_floor = compute_effective_floor(
                ctx.current_floor or None,
                deps_floor,
                code_floor,
            ) or ""

            verdict, _verdict_detail = compute_verdict(
                ctx.current_floor or None,
                deps_floor,
                code_floor,
                floor_source=ctx.floor_source or None,
            )
            ctx.verdict = verdict

        except Exception as exc:
            logger.warning("Failed to compute deep analysis: %s", exc)

    # ── Check for __future__ imports ─────────────────────────────
    if ctx.language == "python" and module_dir.is_dir():
        ctx.has_future_import = _check_future_import(module_dir)

    # ── File presence ────────────────────────────────────────────
    if module_dir.is_dir():
        _detect_files(ctx, module_dir)

    return ctx


# ── Internal helpers ─────────────────────────────────────────────


def _compute_direction(current: str, target: str) -> str:
    """Determine upgrade vs downgrade from version comparison."""
    if not current or not target:
        return "upgrade"  # default assumption

    try:
        current_parts = [int(x) for x in current.split(".")]
        target_parts = [int(x) for x in target.split(".")]
    except ValueError:
        return "upgrade"

    if target_parts > current_parts:
        return "upgrade"
    elif target_parts < current_parts:
        return "downgrade"
    else:
        return "upgrade"  # same version — treat as upgrade (re-verify)


def _check_future_import(module_dir: Path) -> bool:
    """Check if any .py file in the module uses __future__ annotations."""
    import re

    pattern = re.compile(
        r"^from\s+__future__\s+import\s+annotations", re.MULTILINE,
    )

    for py_file in module_dir.rglob("*.py"):
        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
            if pattern.search(content):
                return True
        except OSError:
            continue

    return False


def _detect_files(ctx: UpgradeContext, module_dir: Path) -> None:
    """Check which config/project files exist in the module directory."""
    checks = [
        ("has_pyproject", "pyproject.toml"),
        ("has_setup_py", "setup.py"),
        ("has_setup_cfg", "setup.cfg"),
        ("has_requirements_txt", "requirements.txt"),
        ("has_package_json", "package.json"),
        ("has_go_mod", "go.mod"),
        ("has_cargo_toml", "Cargo.toml"),
        ("has_gemfile", "Gemfile"),
        ("has_composer_json", "composer.json"),
        ("has_mix_exs", "mix.exs"),
        ("has_pom_xml", "pom.xml"),
        ("has_build_gradle", "build.gradle"),
    ]

    for attr, filename in checks:
        if (module_dir / filename).exists():
            setattr(ctx, attr, True)

    # .csproj — glob for any .csproj file
    if any(module_dir.glob("*.csproj")):
        ctx.has_csproj = True
