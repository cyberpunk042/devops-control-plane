"""Docker config generation — Dockerfile, .dockerignore, compose."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _audit(label: str, summary: str, **kwargs) -> None:
    """Record an audit event if a project root is registered."""
    try:
        from src.core.context import get_project_root
        root = get_project_root()
    except Exception:
        return
    if root is None:
        return
    from src.core.services.devops_cache import record_event
    record_event(root, label=label, summary=summary, card="docker", **kwargs)

def generate_dockerfile(project_root: Path, stack_name: str) -> dict:
    """Generate a Dockerfile for the given stack.

    Returns:
        {"ok": True, "file": {...}} or {"error": "..."}
    """
    from src.core.services.generators.dockerfile import generate_dockerfile as _gen

    result = _gen(project_root, stack_name)
    if result is None:
        from src.core.services.generators.dockerfile import supported_stacks

        return {
            "error": f"No Dockerfile template for stack '{stack_name}'",
            "supported": supported_stacks(),
        }

    _audit(
        "📝 Dockerfile Generated",
        f"Generated Dockerfile for stack: {stack_name}",
        action="generated",
        target="Dockerfile",
        after_state={"stack": stack_name},
    )
    return {"ok": True, "file": result.model_dump()}


def generate_dockerignore(project_root: Path, stack_names: list[str]) -> dict:
    """Generate a .dockerignore for the given stacks.

    Returns:
        {"ok": True, "file": {...}}
    """
    from src.core.services.generators.dockerignore import generate_dockerignore as _gen

    result = _gen(project_root, stack_names)
    _audit(
        "📝 .dockerignore Generated",
        f"Generated .dockerignore for stacks: {', '.join(stack_names)}",
        action="generated",
        target=".dockerignore",
        after_state={"stacks": stack_names},
    )
    return {"ok": True, "file": result.model_dump()}


def generate_compose(
    project_root: Path,
    modules: list[dict] | None = None,
    *,
    project_name: str = "",
) -> dict:
    """Generate a docker-compose.yml from detected modules.

    If *modules* is not provided, auto-detects from project config.

    Returns:
        {"ok": True, "file": {...}} or {"error": "..."}
    """
    if modules is None or not project_name:
        from src.core.config.loader import load_project
        from src.core.config.stack_loader import discover_stacks
        from src.core.services.detection import detect_modules

        project = load_project(project_root / "project.yml")
        if not project_name:
            project_name = project.name
        if modules is None:
            stacks = discover_stacks(project_root / "stacks")
            detection = detect_modules(project, project_root, stacks)
            modules = [m.model_dump() for m in detection.modules]

    from src.core.services.generators.compose import generate_compose as _gen

    result = _gen(project_root, modules, project_name=project_name)
    if result is None:
        return {"error": "No eligible modules for compose generation"}

    _audit(
        "📝 Compose Generated",
        f"Generated docker-compose.yml ({len(modules)} module(s))",
        action="generated",
        target="docker-compose.yml",
        after_state={"modules": len(modules), "project_name": project_name or "(auto)"},
    )
    return {"ok": True, "file": result.model_dump()}


def generate_compose_from_wizard(
    project_root: Path,
    services: list[dict],
    *,
    project_name: str = "",
) -> dict:
    """Generate a docker-compose.yml from user-defined service specifications.

    Args:
        project_root: Project root directory.
        services: List of service dicts with:
            name, image, build_context, dockerfile, ports, volumes,
            environment, depends_on, restart, command, networks.
        project_name: Optional project name for compose.

    Returns:
        {"ok": True, "file": {...}} or {"error": "..."}
    """
    from src.core.models.template import GeneratedFile

    if not services:
        return {"error": "At least one service is required"}

    import yaml

    compose: dict = {"services": {}}
    if project_name:
        compose["name"] = project_name

    all_networks: set[str] = set()

    for svc in services:
        name = (svc.get("name") or "").strip()
        if not name:
            continue

        spec: dict = {}

        # Image vs build
        image = (svc.get("image") or "").strip()
        build_ctx = (svc.get("build_context") or "").strip()
        dockerfile = (svc.get("dockerfile") or "").strip()

        if image and not build_ctx:
            spec["image"] = image
        elif build_ctx:
            build_def: dict = {"context": build_ctx}
            if dockerfile:
                build_def["dockerfile"] = dockerfile
            spec["build"] = build_def
            if image:
                spec["image"] = image
        elif not image and not build_ctx:
            spec["image"] = name  # fallback

        # Ports
        ports = svc.get("ports", [])
        if ports:
            spec["ports"] = [str(p) for p in ports if p]

        # Volumes
        volumes = svc.get("volumes", [])
        if volumes:
            spec["volumes"] = [str(v) for v in volumes if v]

        # Environment
        env = svc.get("environment", {})
        if isinstance(env, dict) and env:
            spec["environment"] = {k: str(v) for k, v in env.items()}
        elif isinstance(env, list) and env:
            spec["environment"] = [str(e) for e in env if e]

        # Depends on
        deps = svc.get("depends_on", [])
        if deps:
            spec["depends_on"] = [str(d) for d in deps if d]

        # Restart
        restart = (svc.get("restart") or "unless-stopped").strip()
        if restart:
            spec["restart"] = restart

        # Command
        command = (svc.get("command") or "").strip()
        if command:
            spec["command"] = command

        # Networks
        networks = svc.get("networks", [])
        if networks:
            spec["networks"] = [str(n) for n in networks if n]
            all_networks.update(n for n in networks if n)

        # Container name
        container_name = (svc.get("container_name") or "").strip()
        if container_name:
            spec["container_name"] = container_name

        # Health check
        healthcheck = svc.get("healthcheck")
        if isinstance(healthcheck, dict) and healthcheck:
            spec["healthcheck"] = healthcheck

        # Build args
        build_args = svc.get("build_args")
        if isinstance(build_args, dict) and build_args:
            if "build" in spec and isinstance(spec["build"], dict):
                spec["build"]["args"] = {k: str(v) for k, v in build_args.items()}
            elif "build" in spec:
                spec["build"] = {"context": spec["build"], "args": {k: str(v) for k, v in build_args.items()}}

        # Platform
        platform = (svc.get("platform") or "").strip()
        if platform:
            spec["platform"] = platform

        compose["services"][name] = spec

    # Add top-level networks if any
    if all_networks:
        compose["networks"] = {n: {} for n in sorted(all_networks)}

    content = "# Generated by DevOps Control Plane — Compose Wizard\n"
    content += yaml.dump(
        compose,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
    )

    file_data = GeneratedFile(
        path="docker-compose.yml",
        content=content,
        overwrite=False,
        reason=f"Compose wizard: {len(compose['services'])} service(s)",
    )

    # Compute diff if the file already exists on disk
    diff_detail: dict[str, Any] = {
        "file": "docker-compose.yml",
        "services": list(compose["services"].keys()),
    }
    before_state = None
    try:
        from src.core.context import get_project_root
        root = get_project_root()
        if root:
            existing = root / "docker-compose.yml"
            if existing.is_file():
                import difflib
                old_content = existing.read_text(encoding="utf-8", errors="ignore")
                old_lines_list = old_content.splitlines()
                new_lines_list = content.splitlines()
                diff_lines = list(difflib.unified_diff(
                    old_lines_list, new_lines_list,
                    fromfile="a/docker-compose.yml",
                    tofile="b/docker-compose.yml",
                    lineterm="",
                ))
                added = sum(1 for l in diff_lines if l.startswith("+") and not l.startswith("+++"))
                removed = sum(1 for l in diff_lines if l.startswith("-") and not l.startswith("---"))
                diff_text = "\n".join(diff_lines[:50])
                if len(diff_lines) > 50:
                    diff_text += f"\n... ({len(diff_lines) - 50} more lines)"
                diff_detail["lines_added"] = added
                diff_detail["lines_removed"] = removed
                diff_detail["diff"] = diff_text
                before_state = {"lines": len(old_lines_list), "size": len(old_content.encode())}
    except Exception:
        pass

    _audit(
        "📝 Compose Wizard Generated",
        f"Generated docker-compose.yml ({len(compose['services'])} service(s) via wizard)"
        + (f" — +{diff_detail.get('lines_added', 0)} -{diff_detail.get('lines_removed', 0)} lines" if "diff" in diff_detail else ""),
        action="generated",
        target="docker-compose.yml",
        detail=diff_detail,
        before_state=before_state,
        after_state={
            "lines": len(content.splitlines()),
            "services": list(compose["services"].keys()),
            "project_name": project_name or "(auto)",
        },
    )
    return {"ok": True, "file": file_data.model_dump()}


def write_generated_file(project_root: Path, file_data: dict) -> dict:
    """Write a GeneratedFile to disk.

    Args:
        project_root: Project root directory.
        file_data: Dict with 'path', 'content', 'overwrite'.

    Returns:
        {"ok": True, "path": "...", "written": True} or {"error": "..."}
    """
    rel_path = file_data.get("path", "")
    content = file_data.get("content", "")
    overwrite = file_data.get("overwrite", False)

    if not rel_path or not content:
        return {"error": "Missing path or content"}

    target = project_root / rel_path

    if target.exists() and not overwrite:
        return {
            "error": f"File already exists: {rel_path} (use overwrite=true to replace)",
            "path": rel_path,
            "written": False,
        }

    target.parent.mkdir(parents=True, exist_ok=True)
    was_override = target.exists()

    # Capture old content for diff if overwriting
    old_content = ""
    if was_override:
        try:
            old_content = target.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            pass

    target.write_text(content, encoding="utf-8")
    logger.info("Wrote generated file: %s", target)

    # Compute diff for audit
    diff_detail: dict[str, Any] = {"file": rel_path}
    old_lines = len(old_content.splitlines()) if old_content else 0
    new_lines = len(content.splitlines())

    if was_override and old_content:
        import difflib
        diff_lines = list(difflib.unified_diff(
            old_content.splitlines(),
            content.splitlines(),
            fromfile=f"a/{rel_path}",
            tofile=f"b/{rel_path}",
            lineterm="",
        ))
        added = sum(1 for l in diff_lines if l.startswith("+") and not l.startswith("+++"))
        removed = sum(1 for l in diff_lines if l.startswith("-") and not l.startswith("---"))
        diff_text = "\n".join(diff_lines[:50])
        if len(diff_lines) > 50:
            diff_text += f"\n... ({len(diff_lines) - 50} more lines)"
        diff_detail["lines_added"] = added
        diff_detail["lines_removed"] = removed
        diff_detail["diff"] = diff_text

    _audit(
        "💾 Docker File Written",
        f"{rel_path}" + (f" (overwritten, +{diff_detail.get('lines_added', 0)} -{diff_detail.get('lines_removed', 0)} lines)" if was_override else " (new)"),
        action="saved",
        target=rel_path,
        detail=diff_detail,
        before_state={"lines": old_lines, "size": len(old_content.encode())} if was_override else None,
        after_state={"lines": new_lines, "size": target.stat().st_size},
    )
    return {"ok": True, "path": rel_path, "written": True}

