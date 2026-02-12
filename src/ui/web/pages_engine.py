"""
Pages engine — orchestrates segment lifecycle.

This is the core logic for the GitHub Pages multi-segment builder.
It manages segments (CRUD), runs builds through pluggable builders,
merges outputs, and handles deployment to gh-pages.

All state is persisted in project.yml under the `pages:` key.
Build artifacts live in .pages/ (gitignored).
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import time
from pathlib import Path

import yaml

from .pages_builders import BuildResult, SegmentConfig, get_builder, list_builders, run_pipeline

logger = logging.getLogger(__name__)

# ── Constants ───────────────────────────────────────────────────────

PAGES_WORKSPACE = ".pages"


# ── Config I/O ──────────────────────────────────────────────────────


def _load_project_yml(project_root: Path) -> dict:
    """Load project.yml as raw dict."""
    yml_path = project_root / "project.yml"
    if not yml_path.is_file():
        return {}
    return yaml.safe_load(yml_path.read_text(encoding="utf-8")) or {}


def _save_project_yml(project_root: Path, data: dict) -> None:
    """Write back to project.yml preserving comments is not possible
    with PyYAML, but we keep it clean."""
    yml_path = project_root / "project.yml"
    yml_path.write_text(
        yaml.dump(data, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )


def _get_pages_config(project_root: Path) -> dict:
    """Get the pages: section from project.yml."""
    data = _load_project_yml(project_root)
    return data.get("pages", {})


def _set_pages_config(project_root: Path, pages_config: dict) -> None:
    """Write the pages: section to project.yml."""
    data = _load_project_yml(project_root)
    data["pages"] = pages_config
    _save_project_yml(project_root, data)


# ── Segment CRUD ────────────────────────────────────────────────────


def get_segments(project_root: Path) -> list[SegmentConfig]:
    """Load all segment configs from project.yml."""
    pages = _get_pages_config(project_root)
    raw_segments = pages.get("segments", [])
    segments = []
    for s in raw_segments:
        segments.append(SegmentConfig(
            name=s.get("name", "unnamed"),
            source=s.get("source", ""),
            builder=s.get("builder", "raw"),
            path=s.get("path", "/"),
            auto=s.get("auto", False),
            config=s.get("config", {}),
        ))
    return segments


def get_segment(project_root: Path, name: str) -> SegmentConfig | None:
    """Get a single segment by name."""
    for seg in get_segments(project_root):
        if seg.name == name:
            return seg
    return None


def add_segment(project_root: Path, segment: SegmentConfig) -> None:
    """Add a new segment to project.yml."""
    pages = _get_pages_config(project_root)
    segments = pages.get("segments", [])

    # Check for duplicates
    for s in segments:
        if s.get("name") == segment.name:
            raise ValueError(f"Segment '{segment.name}' already exists")

    segments.append({
        "name": segment.name,
        "source": segment.source,
        "builder": segment.builder,
        "path": segment.path,
        "auto": segment.auto,
        "config": segment.config,
    })
    pages["segments"] = segments
    _set_pages_config(project_root, pages)


def update_segment(project_root: Path, name: str, updates: dict) -> None:
    """Update an existing segment's config."""
    pages = _get_pages_config(project_root)
    segments = pages.get("segments", [])

    for s in segments:
        if s.get("name") == name:
            for k, v in updates.items():
                if k != "name":  # Can't rename through update
                    s[k] = v
            pages["segments"] = segments
            _set_pages_config(project_root, pages)
            return

    raise ValueError(f"Segment '{name}' not found")


def remove_segment(project_root: Path, name: str) -> None:
    """Remove a segment from project.yml and clean its workspace."""
    pages = _get_pages_config(project_root)
    segments = pages.get("segments", [])
    pages["segments"] = [s for s in segments if s.get("name") != name]
    _set_pages_config(project_root, pages)

    # Clean workspace
    ws = project_root / PAGES_WORKSPACE / name
    if ws.exists():
        shutil.rmtree(ws)


# ── Pages metadata ──────────────────────────────────────────────────


def get_pages_meta(project_root: Path) -> dict:
    """Get top-level pages metadata (base_url, deploy_branch, etc.)."""
    pages = _get_pages_config(project_root)
    return {
        "base_url": pages.get("base_url", ""),
        "deploy_branch": pages.get("deploy_branch", "gh-pages"),
        "root_segment": pages.get("root_segment", None),
    }


def set_pages_meta(project_root: Path, meta: dict) -> None:
    """Update top-level pages metadata."""
    pages = _get_pages_config(project_root)
    for k in ("base_url", "deploy_branch", "root_segment"):
        if k in meta:
            pages[k] = meta[k]
    _set_pages_config(project_root, pages)


# ── Build ───────────────────────────────────────────────────────────


def build_segment(project_root: Path, name: str) -> BuildResult:
    """Build a single segment using the pipeline model.

    Returns:
        BuildResult with ok, output_dir, log, duration_ms.
    """
    segment = get_segment(project_root, name)
    if segment is None:
        return BuildResult(ok=False, segment=name, error=f"Segment '{name}' not found")

    builder = get_builder(segment.builder)
    if builder is None:
        return BuildResult(ok=False, segment=name, error=f"Builder '{segment.builder}' not found")

    if not builder.detect():
        info = builder.info()
        return BuildResult(
            ok=False, segment=name,
            error=f"Builder '{info.label}' not available (requires: {', '.join(info.requires)})",
        )

    # Resolve source path
    source_path = (project_root / segment.source).resolve()
    if not source_path.is_dir():
        return BuildResult(ok=False, segment=name, error=f"Source folder not found: {segment.source}")

    segment.source = str(source_path)
    workspace = project_root / PAGES_WORKSPACE / name
    workspace.mkdir(parents=True, exist_ok=True)

    # Run the full pipeline
    result = run_pipeline(builder, segment, workspace)

    # Collect log lines from all stages
    log_lines: list[str] = []
    for stage in result.stages:
        log_lines.append(f"[{stage.name}] {stage.label} — {stage.status} ({stage.duration_ms}ms)")
        log_lines.extend(stage.log_lines)
        if stage.error:
            log_lines.append(f"  ERROR: {stage.error}")

    if result.ok:
        # Write build metadata
        meta = {
            "segment": name,
            "builder": segment.builder,
            "built_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "duration_ms": result.total_duration_ms,
            "output_dir": result.output_dir,
            "serve_url": result.serve_url,
        }
        (workspace / "build.json").write_text(
            json.dumps(meta, indent=2), encoding="utf-8",
        )

    # Convert to legacy BuildResult
    error = ""
    if not result.ok:
        # Find the failed stage
        for stage in result.stages:
            if stage.status == "error":
                error = f"Stage '{stage.name}' failed: {stage.error}"
                break

    return BuildResult(
        ok=result.ok,
        segment=name,
        output_dir=Path(result.output_dir) if result.output_dir else None,
        duration_ms=result.total_duration_ms,
        error=error,
        log=log_lines,
    )


def get_build_status(project_root: Path, name: str) -> dict | None:
    """Get the last build metadata for a segment."""
    meta_path = project_root / PAGES_WORKSPACE / name / "build.json"
    if not meta_path.is_file():
        return None
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return None


# ── Merge ───────────────────────────────────────────────────────────


def merge_segments(project_root: Path) -> dict:
    """Merge all built segment outputs into _merged/.

    Returns:
        Dict with {ok, merged_dir, segments_merged, errors}.
    """
    merged_dir = project_root / PAGES_WORKSPACE / "_merged"
    if merged_dir.exists():
        shutil.rmtree(merged_dir)
    merged_dir.mkdir(parents=True)

    segments = get_segments(project_root)
    pages_meta = get_pages_meta(project_root)
    root_segment = pages_meta.get("root_segment")

    merged = []
    errors = []

    for seg in segments:
        build_meta = get_build_status(project_root, seg.name)
        if build_meta is None:
            errors.append(f"Segment '{seg.name}' has not been built yet")
            continue

        output = Path(build_meta.get("output_dir", ""))
        if not output.is_dir():
            errors.append(f"Segment '{seg.name}' output dir missing: {output}")
            continue

        # Determine target path
        if root_segment and seg.name == root_segment:
            target = merged_dir
        else:
            path = seg.path.strip("/") or seg.name
            target = merged_dir / path

        target.mkdir(parents=True, exist_ok=True)
        shutil.copytree(str(output), str(target), dirs_exist_ok=True)
        merged.append(seg.name)

    # Generate hub page if no root segment
    if not root_segment:
        _generate_hub_page(merged_dir, segments)

    return {
        "ok": len(errors) == 0,
        "merged_dir": str(merged_dir),
        "segments_merged": merged,
        "errors": errors,
    }


def _generate_hub_page(merged_dir: Path, segments: list[SegmentConfig]) -> None:
    """Auto-generate a landing page linking to all segments."""
    cards_html = ""
    for seg in segments:
        path = seg.path.strip("/") or seg.name
        cards_html += f"""
        <a href="./{path}/" class="card">
            <h2>{seg.name.title()}</h2>
            <p>{seg.config.get('title', seg.name)} &rarr;</p>
        </a>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Documentation Hub</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: system-ui, -apple-system, sans-serif;
               background: #0f1117; color: #e0e0e0; min-height: 100vh;
               display: flex; flex-direction: column; align-items: center;
               padding: 4rem 2rem; }}
        h1 {{ font-size: 2rem; margin-bottom: 0.5rem; }}
        .subtitle {{ color: #888; margin-bottom: 3rem; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                 gap: 1.5rem; width: 100%; max-width: 800px; }}
        .card {{ background: #1a1d27; border: 1px solid #2a2d37; border-radius: 12px;
                 padding: 1.5rem; text-decoration: none; color: #e0e0e0;
                 transition: all 0.2s; }}
        .card:hover {{ border-color: #6366f1; transform: translateY(-2px);
                       box-shadow: 0 4px 16px rgba(99, 102, 241, 0.15); }}
        .card h2 {{ font-size: 1.1rem; margin-bottom: 0.5rem; }}
        .card p {{ color: #888; font-size: 0.9rem; }}
    </style>
</head>
<body>
    <h1>📄 Documentation Hub</h1>
    <p class="subtitle">Select a section to browse</p>
    <div class="grid">
        {cards_html}
    </div>
</body>
</html>"""
    (merged_dir / "index.html").write_text(html, encoding="utf-8")


# ── Deploy ──────────────────────────────────────────────────────────


def deploy_to_ghpages(project_root: Path) -> dict:
    """Force-push _merged/ to the gh-pages branch.

    Returns:
        Dict with {ok, output, error}.
    """
    merged_dir = project_root / PAGES_WORKSPACE / "_merged"
    if not merged_dir.is_dir():
        return {"ok": False, "error": "No merged output. Run build-all first."}

    try:
        # Create a temporary orphan branch approach using git worktree
        # or a simpler approach: init a fresh repo in _merged and push
        cwd = str(merged_dir)

        # Init fresh git repo in merged dir
        subprocess.run(["git", "init"], cwd=cwd, capture_output=True, check=True)
        subprocess.run(["git", "checkout", "-b", "gh-pages"], cwd=cwd, capture_output=True, check=True)
        subprocess.run(["git", "add", "-A"], cwd=cwd, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Deploy to GitHub Pages"],
            cwd=cwd, capture_output=True, check=True,
        )

        # Get the remote URL from the main repo
        r = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=str(project_root), capture_output=True, text=True,
        )
        if r.returncode != 0:
            return {"ok": False, "error": "No 'origin' remote configured"}

        remote_url = r.stdout.strip()

        # Force push
        r_push = subprocess.run(
            ["git", "push", "--force", remote_url, "gh-pages"],
            cwd=cwd, capture_output=True, text=True, timeout=120,
        )

        # Clean up the temp git repo
        shutil.rmtree(merged_dir / ".git", ignore_errors=True)

        if r_push.returncode != 0:
            return {"ok": False, "error": f"Push failed: {r_push.stderr.strip()}"}

        return {
            "ok": True,
            "output": r_push.stdout.strip() or r_push.stderr.strip(),
        }

    except subprocess.CalledProcessError as e:
        return {"ok": False, "error": f"Git error: {e.stderr if hasattr(e, 'stderr') else str(e)}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Ensure .pages in .gitignore ─────────────────────────────────────


def ensure_gitignore(project_root: Path) -> None:
    """Ensure .pages/ is in .gitignore."""
    gitignore = project_root / ".gitignore"
    if gitignore.is_file():
        content = gitignore.read_text(encoding="utf-8")
        if ".pages" in content:
            return
        # Append
        content = content.rstrip() + "\n\n# Pages build workspace\n.pages/\n"
        gitignore.write_text(content, encoding="utf-8")
    else:
        gitignore.write_text("# Pages build workspace\n.pages/\n", encoding="utf-8")


# ── Preview Server Management ───────────────────────────────────────

# In-memory tracking — survives within a single server process
_preview_servers: dict[str, dict] = {}  # name -> {proc, port, started_at}
_MAX_PREVIEWS = 3


def start_preview(project_root: Path, name: str) -> dict:
    """Start a preview server for a segment.

    Returns:
        Dict with {ok, port, error}.
    """
    # Check if already running
    if name in _preview_servers:
        info = _preview_servers[name]
        proc = info["proc"]
        if proc.poll() is None:  # Still running
            return {"ok": True, "port": info["port"], "already_running": True}
        # Dead — clean up
        del _preview_servers[name]

    # Enforce max concurrency
    _cleanup_dead_previews()
    if len(_preview_servers) >= _MAX_PREVIEWS:
        return {"ok": False, "error": f"Max {_MAX_PREVIEWS} concurrent previews. Stop one first."}

    segment = get_segment(project_root, name)
    if segment is None:
        return {"ok": False, "error": f"Segment '{name}' not found"}

    builder = get_builder(segment.builder)
    if builder is None:
        return {"ok": False, "error": f"Builder '{segment.builder}' not found"}

    workspace = project_root / PAGES_WORKSPACE / name

    # Resolve source for the builder
    source_path = (project_root / segment.source).resolve()
    segment.source = str(source_path)

    # Ensure scaffolded
    if not workspace.exists():
        builder.scaffold(segment, workspace)

    try:
        proc, port = builder.preview(segment, workspace)
        _preview_servers[name] = {
            "proc": proc,
            "port": port,
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        return {"ok": True, "port": port}
    except NotImplementedError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"Failed to start preview: {e}"}


def stop_preview(name: str) -> dict:
    """Stop a preview server.

    Returns:
        Dict with {ok, error}.
    """
    if name not in _preview_servers:
        return {"ok": False, "error": f"No preview running for '{name}'"}

    info = _preview_servers.pop(name)
    proc = info["proc"]
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    return {"ok": True}


def list_previews() -> list[dict]:
    """List all running preview servers."""
    _cleanup_dead_previews()
    result = []
    for name, info in _preview_servers.items():
        result.append({
            "name": name,
            "port": info["port"],
            "started_at": info["started_at"],
            "running": info["proc"].poll() is None,
        })
    return result


def _cleanup_dead_previews() -> None:
    """Remove entries for processes that have died."""
    dead = [name for name, info in _preview_servers.items() if info["proc"].poll() is not None]
    for name in dead:
        del _preview_servers[name]


# ── CI Workflow Generation ──────────────────────────────────────────


def generate_ci_workflow(project_root: Path) -> dict:
    """Generate a GitHub Actions workflow for Pages deployment.

    Creates .github/workflows/deploy-pages.yml that:
    1. Checks out the repo
    2. Installs builder dependencies
    3. Builds all segments
    4. Merges outputs
    5. Deploys to GitHub Pages

    Returns:
        Dict with {ok, path, error}.
    """
    segments = get_segments(project_root)
    if not segments:
        return {"ok": False, "error": "No segments configured"}

    # Detect required builders
    builders_used = set(seg.builder for seg in segments)

    # Build install steps
    install_steps: list[str] = []
    build_commands: list[str] = []

    for seg in segments:
        builder = seg.builder
        src = seg.source
        path = seg.path.strip("/") or seg.name

        if builder == "raw":
            build_commands.append(f"mkdir -p _merged/{path}")
            build_commands.append(f"cp -r {src}/. _merged/{path}/")

        elif builder == "mkdocs":
            if "mkdocs" not in [s for s in install_steps if "mkdocs" in s]:
                install_steps.append("pip install mkdocs mkdocs-material")
            build_commands.append(
                f"mkdocs build --config-file .pages/{seg.name}/mkdocs.yml"
            )
            build_commands.append(f"cp -r .pages/{seg.name}/build/. _merged/{path}/")

        elif builder == "hugo":
            build_commands.append(
                f"hugo --source .pages/{seg.name} --destination build"
            )
            build_commands.append(f"cp -r .pages/{seg.name}/build/. _merged/{path}/")

        elif builder == "docusaurus":
            if "node" not in [s for s in install_steps if "node" in s]:
                install_steps.append("# Node.js setup handled by actions/setup-node")
            # CI builds from the committed source, not local .pages workspace.
            # The scaffold files (package.json, docusaurus.config.ts, etc.)
            # must already exist in .pages/<name>/ (committed to repo).
            ws = f".pages/{seg.name}"
            build_commands.append(f"cp -r {src}/. {ws}/docs/")
            build_commands.append(f"cd {ws} && npm ci && npx docusaurus build --out-dir build")
            build_commands.append(f"cp -r {ws}/build/. _merged/{path}/")

    # Assemble workflow
    install_block = "\n          ".join(install_steps) if install_steps else "echo 'No additional deps'"
    build_block = "\n          ".join(build_commands)

    needs_node = "docusaurus" in builders_used
    needs_python = "mkdocs" in builders_used or "sphinx" in builders_used
    needs_hugo = "hugo" in builders_used

    setup_steps = ""
    if needs_python:
        setup_steps += """
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
"""
    if needs_node:
        setup_steps += """
      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
"""
    if needs_hugo:
        setup_steps += """
      - name: Set up Hugo
        uses: peaceiris/actions-hugo@v3
        with:
          hugo-version: 'latest'
"""

    workflow = f"""# Auto-generated by DevOps Control Plane
# Deploy documentation to GitHub Pages
name: Deploy Pages

on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: false

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4
{setup_steps}
      - name: Install dependencies
        run: |
          {install_block}

      - name: Build segments
        run: |
          mkdir -p _merged
          {build_block}

      - name: Upload artifact
        uses: actions/upload-pages-artifact@v3
        with:
          path: _merged

  deploy:
    environment:
      name: github-pages
      url: ${{{{ steps.deployment.outputs.page_url }}}}
    runs-on: ubuntu-latest
    needs: build
    steps:
      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@v4
"""

    # Write workflow file
    workflow_dir = project_root / ".github" / "workflows"
    workflow_dir.mkdir(parents=True, exist_ok=True)
    workflow_path = workflow_dir / "deploy-pages.yml"
    workflow_path.write_text(workflow, encoding="utf-8")

    return {
        "ok": True,
        "path": str(workflow_path.relative_to(project_root)),
        "builders": list(builders_used),
    }

