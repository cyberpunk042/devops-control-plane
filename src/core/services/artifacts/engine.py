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
    """Build an artifact target, yielding JSON event strings for SSE.

    Resolves the builder, runs the build, saves the result.
    Yields each event as a JSON string.
    """
    target = get_target(project_root, name)
    if not target:
        yield json.dumps({"type": "pipeline_start", "stages": []})
        yield json.dumps({
            "type": "pipeline_done", "ok": False,
            "error": f"Target '{name}' not found",
            "total_ms": 0, "stages": [],
        })
        return

    from .builders import get_builder

    builder = get_builder(target.builder)
    if not builder:
        yield json.dumps({"type": "pipeline_start", "stages": []})
        yield json.dumps({
            "type": "pipeline_done", "ok": False,
            "error": f"Builder '{target.builder}' not found",
            "total_ms": 0, "stages": [],
        })
        return

    # Run the build — generator yields dicts, returns ArtifactBuildResult
    gen = builder.build(target, project_root)
    result = None
    try:
        while True:
            event = next(gen)
            yield json.dumps(event)
    except StopIteration as e:
        result = e.value

    if result is None:
        result = ArtifactBuildResult(
            ok=False, target_name=name, error="Builder returned no result"
        )

    # Save build metadata
    _save_build_status(project_root, name, result)


# ── Publish support ─────────────────────────────────────────────────


def detect_publish_capabilities(project_root: Path) -> dict:
    """Detect what publishing tools and auth are available.

    Stack-agnostic — detects all possible publish tools across every stack.
    """
    import os
    import shutil
    import subprocess

    caps: dict = {
        # Git / GitHub
        "gh_cli": shutil.which("gh") is not None,
        "gh_authenticated": False,
        "gh_repo": "",
        # Containers
        "docker_cli": shutil.which("docker") is not None or shutil.which("podman") is not None,
        # Python
        "twine_available": False,
        "pypi_token": bool(os.environ.get("PYPI_TOKEN")),
        "test_pypi_token": bool(os.environ.get("TEST_PYPI_TOKEN")),
        # Node / JavaScript / TypeScript
        "npm_cli": shutil.which("npm") is not None,
        "npm_token": bool(os.environ.get("NPM_TOKEN")),
        # Rust
        "cargo_cli": shutil.which("cargo") is not None,
        "cargo_token": bool(os.environ.get("CARGO_REGISTRY_TOKEN") or os.environ.get("CRATES_TOKEN")),
        # Go
        "go_cli": shutil.which("go") is not None,
        # Ruby
        "gem_cli": shutil.which("gem") is not None,
        "gem_credentials": False,
        # Java
        "mvn_cli": shutil.which("mvn") is not None or shutil.which("gradle") is not None,
        # .NET
        "dotnet_cli": shutil.which("dotnet") is not None,
        "nuget_token": bool(os.environ.get("NUGET_API_KEY")),
        # Elixir
        "mix_cli": shutil.which("mix") is not None,
        "hex_token": bool(os.environ.get("HEX_API_KEY")),
        # Terraform
        "terraform_cli": shutil.which("terraform") is not None,
        # Helm
        "helm_cli": shutil.which("helm") is not None,
    }

    # Check gh auth
    if caps["gh_cli"]:
        try:
            from src.core.services.git.ops import run_gh
            r = run_gh("auth", "status", cwd=project_root, timeout=10)
            caps["gh_authenticated"] = r.returncode == 0
        except Exception:
            pass

        try:
            from src.core.services.git.ops import run_gh
            r = run_gh("repo", "view", "--json", "nameWithOwner",
                       "--jq", ".nameWithOwner", cwd=project_root, timeout=10)
            if r.returncode == 0:
                caps["gh_repo"] = r.stdout.strip()
        except Exception:
            pass

    # Check twine (venv or global)
    venv_twine = project_root / ".venv" / "bin" / "twine"
    if venv_twine.exists() or shutil.which("twine"):
        caps["twine_available"] = True

    # Check gem credentials
    gem_creds = Path.home() / ".gem" / "credentials"
    if gem_creds.exists():
        caps["gem_credentials"] = True

    # Check env files for tokens
    for env_file in [".env", ".env.production", ".env.active"]:
        env_path = project_root / env_file
        if env_path.exists():
            try:
                content = env_path.read_text()
                for line in content.splitlines():
                    key_val = line.split("=", 1)
                    if len(key_val) != 2:
                        continue
                    key, val = key_val[0].strip(), key_val[1].strip()
                    if not val:
                        continue
                    if key == "PYPI_TOKEN":
                        caps["pypi_token"] = True
                    elif key == "TEST_PYPI_TOKEN":
                        caps["test_pypi_token"] = True
                    elif key == "NPM_TOKEN":
                        caps["npm_token"] = True
                    elif key in ("CARGO_REGISTRY_TOKEN", "CRATES_TOKEN"):
                        caps["cargo_token"] = True
                    elif key == "NUGET_API_KEY":
                        caps["nuget_token"] = True
                    elif key == "HEX_API_KEY":
                        caps["hex_token"] = True
            except OSError:
                pass

    return caps


# ── Stack → Publish Targets Registry ──────────────────────────────────
#
# Loaded from data layer: src/core/data/catalogs/publish_targets.json
# Maps stack name prefixes to their publish targets.
# Stacks inherit from their base prefix (python-flask → python).
# _default applies to ALL stacks (GitHub Release is universal).


def _get_publish_registry() -> dict[str, list[dict]]:
    """Load publish targets registry from the data layer."""
    from src.core.data import DataRegistry
    return DataRegistry().publish_targets


def _resolve_publish_options_for_stacks(
    detected_stacks: list[str], caps: dict,
) -> list[dict]:
    """Resolve publish options from detected stacks and capabilities.

    Checks ALL detected stacks, merges their targets (deduped),
    and evaluates availability against detected capabilities.
    """
    # Always start with _default
    seen_targets: set[str] = set()
    options: list[dict] = []

    def _add_entries(entries: list[dict]) -> None:
        for entry in entries:
            if entry["target"] in seen_targets:
                continue
            seen_targets.add(entry["target"])

            required = entry.get("requires", [])
            available = all(caps.get(r) for r in required)

            if available:
                reason = entry.get("reason_ok", "Ready")
            else:
                fail_keys = entry.get("reason_fail_keys", {})
                if fail_keys:
                    missing = [fail_keys[k] for k in required if not caps.get(k) and k in fail_keys]
                    reason = "Missing: " + ", ".join(missing) if missing else entry.get("reason_fail", "Not available")
                else:
                    reason = entry.get("reason_fail", "Not available")

            options.append({
                "target": entry["target"],
                "available": available,
                "reason": reason,
                "configured": available,
                "label": entry["label"],
                "icon": entry.get("icon", "📦"),
            })

    registry = _get_publish_registry()

    # Default targets (GitHub Release)
    _add_entries(registry.get("_default", []))

    # Stack-specific targets
    for stack_name in detected_stacks:
        # Exact match first
        if stack_name in registry:
            _add_entries(registry[stack_name])
        # Prefix match (python-flask → python, node-express → node)
        base = stack_name.split("-")[0] if "-" in stack_name else ""
        if base and base in registry:
            _add_entries(registry[base])

    # Also check builder/kind for container targets
    # (docker builder might not come from a stack named "docker")
    if "docker" not in [s.split("-")[0] for s in detected_stacks]:
        if caps.get("docker_cli"):
            _add_entries(registry.get("docker", []))

    return options


def _detect_project_stacks(project_root: Path) -> list[str]:
    """Get the detected stacks for this project from the module detection system."""
    try:
        from src.core.config.loader import load_project
        from src.core.config.stack_loader import discover_stacks
        from src.core.services.detection import detect_modules

        project = load_project(project_root / "project.yml")
        stacks = discover_stacks(project_root / "stacks")
        detection = detect_modules(project, project_root, stacks)

        seen: set[str] = set()
        names: list[str] = []
        for m in detection.modules:
            stack = m.effective_stack
            if stack and stack not in seen:
                names.append(stack)
                seen.add(stack)
        return names
    except Exception:
        return []


def get_publishable_artifacts(
    project_root: Path,
    target_name: str,
) -> dict:
    """Get publishable artifacts and available publish targets.

    Publish options are STACK-DRIVEN — derived from the project's
    detected module stacks, not hardcoded per builder.
    """
    targets = get_targets(project_root) # Changed from load_targets to get_targets
    target = next((t for t in targets if t.name == target_name), None)
    if not target:
        return {"error": f"Target '{target_name}' not found"}

    # Version
    from .version import resolve_version
    version, version_source = resolve_version(project_root)

    # Capabilities
    caps = detect_publish_capabilities(project_root)

    # Scan dist/ for artifacts
    dist_dir = project_root / (target.output_dir or "dist/")
    artifacts = []
    if dist_dir.exists():
        for f in sorted(dist_dir.iterdir()):
            if f.is_file() and not f.name.startswith("."):
                ext = f.suffix.lower()
                ftype = "file"
                if ext == ".whl":
                    ftype = "wheel"
                elif ext in (".tar.gz", ".tgz"):
                    ftype = "sdist"
                elif ext == ".zip":
                    ftype = "archive"
                elif ext in (".deb", ".rpm"):
                    ftype = "system-package"
                elif ext in (".tgz", ".tar"):
                    ftype = "tarball"
                elif ext in (".js", ".mjs", ".cjs"):
                    ftype = "js-module"
                elif ext in (".exe", ".bin", ".AppImage"):
                    ftype = "binary"
                artifacts.append({
                    "name": f.name,
                    "path": str(f),
                    "size": f.stat().st_size,
                    "type": ftype,
                })

    # Detect project stacks → resolve publish options
    detected_stacks = _detect_project_stacks(project_root)
    publish_options = _resolve_publish_options_for_stacks(detected_stacks, caps)

    # Check if this version already has a GitHub release
    existing_release = None
    if caps["gh_authenticated"]:
        try:
            from src.core.services.git.ops import run_gh
            tag = f"v{version}"
            r = run_gh("release", "view", tag, "--json",
                       "tagName,publishedAt,url",
                       cwd=project_root, timeout=10)
            if r.returncode == 0:
                import json as _json
                info_data = _json.loads(r.stdout)
                existing_release = {
                    "tag": info_data.get("tagName", tag),
                    "url": info_data.get("url", ""),
                    "published_at": info_data.get("publishedAt", ""),
                }
        except Exception:
            pass

    # Version bumps
    from .version import bump_version
    bumps = {
        "patch": bump_version(version, "patch"),
        "minor": bump_version(version, "minor"),
        "major": bump_version(version, "major"),
    }

    return {
        "target": target_name,
        "kind": target.kind,
        "builder": target.builder,
        "version": version,
        "version_source": version_source,
        "artifacts": artifacts,
        "publish_options": publish_options,
        "capabilities": caps,
        "existing_release": existing_release,
        "bumps": bumps,
        "detected_stacks": detected_stacks,
    }


def publish_target_stream(
    project_root: Path,
    target_name: str,
    publish_target: str,
    *,
    version: str = "",
    release_notes: str = "",
    tag_name: str = "",
) -> __import__("typing").Generator[str, None, None]:
    """Publish an artifact, yielding JSON event strings for SSE.

    Args:
        project_root: Project root.
        target_name: Artifact target name (e.g. 'pip-package').
        publish_target: Publisher name (e.g. 'github-release').
        version: Override version.
        release_notes: Release notes markdown.
        tag_name: Override tag name.
    """
    target = get_target(project_root, target_name)
    if not target:
        yield json.dumps({"type": "pipeline_start", "stages": []})
        yield json.dumps({
            "type": "pipeline_done", "ok": False,
            "error": f"Target '{target_name}' not found",
            "total_ms": 0, "stages": [],
        })
        return

    from .publishers import get_publisher

    publisher = get_publisher(publish_target)
    if not publisher:
        yield json.dumps({"type": "pipeline_start", "stages": []})
        yield json.dumps({
            "type": "pipeline_done", "ok": False,
            "error": f"Publisher '{publish_target}' not found",
            "total_ms": 0, "stages": [],
        })
        return

    # Resolve version if not provided
    if not version:
        from .version import resolve_version
        version, _ = resolve_version(project_root)

    # Find files to publish
    output_dir = project_root / (target.output_dir or "dist/")
    files = []
    if output_dir.exists():
        files = [f for f in sorted(output_dir.iterdir())
                 if f.is_file() and not f.name.startswith(".")]

    # Run the publisher
    gen = publisher.publish(
        target, project_root, version, files,
        release_notes=release_notes,
        tag_name=tag_name,
    )
    result = None
    try:
        while True:
            event = next(gen)
            yield json.dumps(event)
    except StopIteration as e:
        result = e.value

    if result is None:
        yield json.dumps({
            "type": "pipeline_done", "ok": False,
            "error": "Publisher returned no result",
            "total_ms": 0, "stages": [],
        })

    # Save publish metadata
    if result:
        workspace = project_root / ARTIFACTS_WORKSPACE / target_name
        workspace.mkdir(parents=True, exist_ok=True)
        meta_path = workspace / ".publish_meta.json"
        meta = {
            "target": target_name,
            "publish_target": result.publish_target,
            "ok": result.ok,
            "version": result.version,
            "url": result.url,
            "duration_ms": result.duration_ms,
            "published_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "files": result.files_published,
            "error": result.error,
        }
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2)

