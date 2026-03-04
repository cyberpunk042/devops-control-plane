"""
Artifacts engine — target CRUD and build orchestration.

Manages the artifacts: section in project.yml.
Each target defines how to build a distributable artifact
(CLI binary, pip package, tarball, container image, etc.).

Workspace: .artifacts/<target-name>/
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml


# ── Data Models ─────────────────────────────────────────────────────

ARTIFACTS_WORKSPACE = ".artifacts"


@dataclass
class ArtifactTarget:
    """A build target that produces a distributable artifact."""

    name: str
    kind: str = "local"               # local | package | bundle | script | container
    builder: str = "makefile"          # makefile | pip | script | docker
    description: str = ""
    build_target: str = ""            # Makefile target or script path
    build_cmd: str = ""               # Full command override
    output_dir: str = "dist/"         # Where artifact lands
    modules: list[str] = field(default_factory=list)
    config: dict = field(default_factory=dict)


@dataclass
class ArtifactBuildResult:
    """Result of building an artifact target."""

    ok: bool
    target_name: str
    output_dir: str = ""
    log: str = ""
    duration_ms: int = 0
    error: str = ""


# ── Config I/O ──────────────────────────────────────────────────────


def _load_project_yml(project_root: Path) -> dict:
    """Load project.yml as raw dict."""
    yml_path = project_root / "project.yml"
    if not yml_path.exists():
        return {}
    with open(yml_path) as f:
        return yaml.safe_load(f) or {}


def _save_project_yml(project_root: Path, data: dict) -> None:
    """Write back to project.yml."""
    yml_path = project_root / "project.yml"
    with open(yml_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def _get_artifacts_config(project_root: Path) -> dict:
    """Get the artifacts: section from project.yml."""
    data = _load_project_yml(project_root)
    return data.get("artifacts", {})


def _set_artifacts_config(project_root: Path, artifacts_config: dict) -> None:
    """Write the artifacts: section to project.yml."""
    data = _load_project_yml(project_root)
    data["artifacts"] = artifacts_config
    _save_project_yml(project_root, data)


# ── Target CRUD ─────────────────────────────────────────────────────


def get_targets(project_root: Path) -> list[ArtifactTarget]:
    """Load all artifact targets from project.yml."""
    cfg = _get_artifacts_config(project_root)
    raw_targets = cfg.get("targets", [])
    targets = []
    for raw in raw_targets:
        targets.append(ArtifactTarget(
            name=raw.get("name", ""),
            kind=raw.get("kind", "local"),
            builder=raw.get("builder", "makefile"),
            description=raw.get("description", ""),
            build_target=raw.get("build_target", ""),
            build_cmd=raw.get("build_cmd", ""),
            output_dir=raw.get("output_dir", "dist/"),
            modules=raw.get("modules", []),
            config=raw.get("config", {}),
        ))
    return targets


def get_target(project_root: Path, name: str) -> ArtifactTarget | None:
    """Get a single target by name."""
    for t in get_targets(project_root):
        if t.name == name:
            return t
    return None


def add_target(project_root: Path, target: ArtifactTarget) -> None:
    """Add a new artifact target to project.yml."""
    cfg = _get_artifacts_config(project_root)
    targets = cfg.get("targets", [])

    # Check for duplicate names
    for existing in targets:
        if existing.get("name") == target.name:
            raise ValueError(f"Artifact target '{target.name}' already exists")

    targets.append(asdict(target))
    cfg["targets"] = targets
    _set_artifacts_config(project_root, cfg)


def update_target(project_root: Path, name: str, updates: dict) -> None:
    """Update an existing target's config."""
    cfg = _get_artifacts_config(project_root)
    targets = cfg.get("targets", [])

    for i, raw in enumerate(targets):
        if raw.get("name") == name:
            raw.update(updates)
            targets[i] = raw
            cfg["targets"] = targets
            _set_artifacts_config(project_root, cfg)
            return

    raise ValueError(f"Artifact target '{name}' not found")


def remove_target(project_root: Path, name: str) -> None:
    """Remove an artifact target from project.yml and clean its workspace."""
    cfg = _get_artifacts_config(project_root)
    targets = cfg.get("targets", [])
    new_targets = [t for t in targets if t.get("name") != name]

    if len(new_targets) == len(targets):
        raise ValueError(f"Artifact target '{name}' not found")

    cfg["targets"] = new_targets
    _set_artifacts_config(project_root, cfg)

    # Clean workspace
    workspace = project_root / ARTIFACTS_WORKSPACE / name
    if workspace.exists():
        import shutil
        shutil.rmtree(workspace)


# ── Build Status ────────────────────────────────────────────────────


def get_build_status(project_root: Path, name: str) -> dict | None:
    """Get the last build metadata for a target."""
    meta_path = (
        project_root / ARTIFACTS_WORKSPACE / name / ".build_meta.json"
    )
    if not meta_path.exists():
        return None
    try:
        with open(meta_path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _save_build_status(
    project_root: Path, name: str, result: ArtifactBuildResult
) -> None:
    """Save build metadata for a target."""
    workspace = project_root / ARTIFACTS_WORKSPACE / name
    workspace.mkdir(parents=True, exist_ok=True)
    meta_path = workspace / ".build_meta.json"
    meta = {
        "target": name,
        "ok": result.ok,
        "output_dir": result.output_dir,
        "duration_ms": result.duration_ms,
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "error": result.error,
    }
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)


# ── Build Orchestration ─────────────────────────────────────────────


def build_target_stream(
    project_root: Path, name: str
) -> __import__("typing").Generator[str, None, None]:
    """Build an artifact target, yielding log lines for SSE streaming.

    Resolves the builder, runs the build, saves the result.
    Yields each log line as a string.
    """
    target = get_target(project_root, name)
    if not target:
        yield f"❌ Target '{name}' not found"
        return

    from .builders import get_builder

    builder = get_builder(target.builder)
    if not builder:
        yield f"❌ Builder '{target.builder}' not found"
        return

    # Run the build — the generator yields log lines and returns a result
    gen = builder.build(target, project_root)
    result = None
    try:
        while True:
            line = next(gen)
            yield line
    except StopIteration as e:
        result = e.value

    if result is None:
        result = ArtifactBuildResult(
            ok=False, target_name=name, error="Builder returned no result"
        )

    # Save build metadata
    _save_build_status(project_root, name, result)
    yield f"__BUILD_RESULT__:{json.dumps({'ok': result.ok, 'duration_ms': result.duration_ms, 'error': result.error})}"
