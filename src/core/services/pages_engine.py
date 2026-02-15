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

from src.core.services.pages_builders import BuildResult, SegmentConfig, get_builder, list_builders, run_pipeline

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


# ── Builder / Feature listing ──────────────────────────────────────


def list_builders_detail() -> list[dict]:
    """List all builders with pipeline stages and config schemas.

    Returns:
        List of dicts with name, label, description, available,
        requires, install_hint, installable, stages, config_fields.
    """
    result = []
    for b in list_builders():
        builder_obj = get_builder(b.name)
        stages = []
        config_fields = []
        if builder_obj:
            stages = [{"name": s.name, "label": s.label}
                      for s in builder_obj.pipeline_stages()]
            config_fields = [
                {
                    "key": f.key,
                    "label": f.label,
                    "type": f.type,
                    "description": f.description,
                    "default": f.default,
                    "placeholder": f.placeholder,
                    "options": f.options,
                    "category": f.category,
                    "required": f.required,
                }
                for f in builder_obj.config_schema()
            ]
        result.append({
            "name": b.name,
            "label": b.label,
            "description": b.description,
            "available": b.available,
            "requires": b.requires,
            "install_hint": b.install_hint,
            "installable": bool(b.install_cmd),
            "stages": stages,
            "config_fields": config_fields,
        })
    return result


def list_feature_categories() -> list[dict]:
    """List builder features grouped by category.

    Returns:
        List of category dicts with key, label, features.
    """
    from src.core.services.pages_builders.template_engine import (
        FEATURES,
        FEATURE_CATEGORIES,
    )

    categories = []
    for cat_key, cat_label in FEATURE_CATEGORIES:
        cat_features = []
        for feat_key, feat_def in FEATURES.items():
            if feat_def["category"] != cat_key:
                continue
            feat_data = {
                "key": feat_key,
                "label": feat_def["label"],
                "description": feat_def["description"],
                "default": feat_def["default"],
                "has_deps": bool(feat_def.get("deps") or feat_def.get("deps_dev")),
            }
            if "options" in feat_def:
                feat_data["options"] = feat_def["options"]
            cat_features.append(feat_data)
        if cat_features:
            categories.append({
                "key": cat_key,
                "label": cat_label,
                "features": cat_features,
            })
    return categories


# ── File → segment resolution ──────────────────────────────────────


def resolve_file_to_segments(
    project_root: Path,
    file_path: str,
) -> list[dict]:
    """Resolve a vault file path to matching segments with preview URLs.

    Args:
        project_root: Project root.
        file_path: Relative path to content file (e.g. 'docs/getting-started.md').

    Returns:
        List of dicts {segment, builder, preview_url, built}.
    """
    if not file_path:
        return []

    segments = get_segments(project_root)
    matches = []

    for seg in segments:
        source = seg.source.rstrip("/")
        if not file_path.startswith(source + "/") and file_path != source:
            continue

        build = get_build_status(project_root, seg.name)
        if not build:
            continue

        rel_path = file_path[len(source) + 1:] if file_path.startswith(source + "/") else ""
        if not rel_path:
            continue

        # Strip .md / .mdx extension for URL
        doc_slug = rel_path
        for ext in [".mdx", ".md"]:
            if doc_slug.endswith(ext):
                doc_slug = doc_slug[:-len(ext)]
                break

        # Handle index pages
        if doc_slug == "index":
            doc_slug = ""
        elif doc_slug.endswith("/index"):
            doc_slug = doc_slug[:-6]

        preview_url = (
            f"/pages/site/{seg.name}/{doc_slug}"
            if doc_slug
            else f"/pages/site/{seg.name}/"
        )

        matches.append({
            "segment": seg.name,
            "builder": seg.builder,
            "preview_url": preview_url,
            "built": bool(build),
        })

    return matches


# ── Auto-init from project.yml ─────────────────────────────────────


def detect_best_builder(
    folder: Path,
    get_builder_fn=None,
) -> tuple[str, str, str]:
    """Detect the best builder for a content folder.

    Returns:
        (builder_name, reason, suggestion).
    """
    if get_builder_fn is None:
        get_builder_fn = get_builder

    has_markdown = False
    for ext in ("*.md", "*.mdx"):
        if list(folder.glob(ext)) or list(folder.glob(f"*/{ext}")):
            has_markdown = True
            break

    if has_markdown:
        docusaurus = get_builder_fn("docusaurus")
        if docusaurus and docusaurus.detect():
            return "docusaurus", "Markdown files detected, Node.js available", ""

        mkdocs = get_builder_fn("mkdocs")
        if mkdocs and mkdocs.detect():
            return (
                "mkdocs",
                "Markdown files detected, MkDocs available",
                "Install Node.js for Docusaurus (better UX)",
            )

        return (
            "raw",
            "Markdown files detected but no doc builder available",
            "Install Node.js (for Docusaurus) or pip install mkdocs",
        )

    return "raw", "Static files (no markdown detected)", ""


def init_pages_from_project(project_root: Path) -> dict:
    """Initialize pages segments from project.yml content_folders.

    Detects markdown content and picks the best available builder.

    Returns:
        {"ok": True, "added": [...], "details": [...], "total_segments": int}
    """
    project_data = _load_project_yml(project_root)
    pages = _get_pages_config(project_root)
    existing_names = {s.get("name") for s in pages.get("segments", [])}

    content_folders = project_data.get("content_folders", [])

    added = []
    details = []
    for folder in content_folders:
        folder_path = project_root / folder
        if not folder_path.is_dir():
            continue
        if folder in existing_names:
            continue

        builder_name, reason, suggestion = detect_best_builder(folder_path)

        seg = SegmentConfig(
            name=folder,
            source=folder,
            builder=builder_name,
            path=f"/{folder}",
            auto=True,
        )
        try:
            add_segment(project_root, seg)
            added.append(folder)
            details.append({
                "name": folder,
                "builder": builder_name,
                "reason": reason,
                "suggestion": suggestion,
            })
        except ValueError:
            pass

    ensure_gitignore(project_root)

    return {
        "ok": True,
        "added": added,
        "details": details,
        "total_segments": len(pages.get("segments", [])) + len(added),
    }


# ── Builder installation (SSE generator) ───────────────────────────


def install_builder_stream(name: str) -> dict | None:
    """Install a builder's dependencies, yielding SSE events.

    Args:
        name: Builder name (e.g. 'mkdocs', 'hugo', 'docusaurus').

    Returns:
        None if builder not found or no install command.
        Otherwise returns an iterator yielding SSE-formatted lines.
        Use ``{"error": ...}`` dict to signal pre-flight errors.
    """
    builder = get_builder(name)
    if builder is None:
        return {"ok": False, "error": f"Builder '{name}' not found"}

    info = builder.info()
    if not info.install_cmd:
        return {"ok": False, "error": f"Builder '{name}' has no auto-install command"}

    if builder.detect():
        return {"ok": True, "already_installed": True}

    # Return None to signal "use the generator"
    return None


def install_builder_events(name: str):
    """Generator that yields SSE events for builder installation.

    Caller must verify install_builder_stream() returned None first.
    """
    import os
    import platform
    import subprocess
    import sys
    import tarfile
    import tempfile
    import urllib.request

    builder = get_builder(name)
    info = builder.info()

    def _pip_install():
        cmd = list(info.install_cmd)
        cmd[0] = str(Path(sys.executable).parent / "pip")
        cmd_str = ' '.join(cmd)
        yield {"type": "log", "line": f"▶ {cmd_str}"}

        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        if proc.stdout:
            for line in proc.stdout:
                yield {"type": "log", "line": line.rstrip()}
        proc.wait()

        if proc.returncode == 0:
            yield {"type": "done", "ok": True, "message": f"{info.label} installed in venv"}
        else:
            yield {"type": "done", "ok": False, "error": f"pip install failed (exit {proc.returncode})"}

    def _glibc_version() -> str:
        try:
            import ctypes
            libc = ctypes.CDLL("libc.so.6")
            libc.gnu_get_libc_version.restype = ctypes.c_char_p
            return libc.gnu_get_libc_version().decode()
        except Exception:
            return "unknown"

    def _hugo_binary_install():
        local_bin = Path.home() / ".local" / "bin"
        local_bin.mkdir(parents=True, exist_ok=True)

        machine = platform.machine().lower()
        if machine in ("x86_64", "amd64"):
            arch = "amd64"
        elif machine in ("aarch64", "arm64"):
            arch = "arm64"
        else:
            yield {"type": "done", "ok": False, "error": f"Unsupported arch: {machine}"}
            return

        system_name = platform.system().lower()
        if system_name != "linux":
            yield {"type": "done", "ok": False, "error": f"Hugo binary download only supports Linux, got {system_name}"}
            return

        yield {"type": "log", "line": f"Detecting latest Hugo release for linux/{arch}..."}

        try:
            req = urllib.request.Request(
                "https://api.github.com/repos/gohugoio/hugo/releases/latest",
                headers={"Accept": "application/vnd.github.v3+json", "User-Agent": "devops-cp"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                release = json.loads(resp.read().decode())

            version = release["tag_name"].lstrip("v")
            yield {"type": "log", "line": f"Latest version: {version}  (GLIBC: {_glibc_version()})"}

            candidates = [
                f"hugo_{version}_linux-{arch}.tar.gz",
                f"hugo_extended_{version}_linux-{arch}.tar.gz",
            ]
            dl_url = None
            tarball_name = None
            for candidate in candidates:
                for asset in release.get("assets", []):
                    if asset["name"] == candidate:
                        dl_url = asset["browser_download_url"]
                        tarball_name = candidate
                        break
                if dl_url:
                    break

            if not dl_url:
                yield {"type": "done", "ok": False, "error": f"Could not find release asset for linux/{arch}"}
                return

            yield {"type": "log", "line": f"Downloading {tarball_name}..."}

            with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
                urllib.request.urlretrieve(dl_url, tmp.name)
                tmp_path = tmp.name

            yield {"type": "log", "line": "Extracting..."}

            with tarfile.open(tmp_path, "r:gz") as tar:
                for member in tar.getmembers():
                    if member.name == "hugo" or member.name.endswith("/hugo"):
                        member.name = "hugo"
                        tar.extract(member, path=str(local_bin))
                        break

            os.unlink(tmp_path)

            hugo_path = local_bin / "hugo"
            hugo_path.chmod(0o755)

            path_dirs = os.environ.get("PATH", "").split(":")
            if str(local_bin) not in path_dirs:
                os.environ["PATH"] = f"{local_bin}:{os.environ.get('PATH', '')}"

            r = subprocess.run([str(hugo_path), "version"], capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                yield {"type": "log", "line": r.stdout.strip()}
                yield {"type": "done", "ok": True, "message": f"Hugo {version} installed to {hugo_path}"}
            else:
                err_detail = (r.stderr or r.stdout or "unknown error").strip()
                yield {"type": "log", "line": f"Execution failed: {err_detail}"}
                yield {"type": "done", "ok": False, "error": f"Hugo binary failed: {err_detail}"}

        except Exception as e:
            yield {"type": "done", "ok": False, "error": f"Download failed: {e}"}

    def _npm_install():
        cmd = list(info.install_cmd)
        cmd_str = ' '.join(cmd)
        yield {"type": "log", "line": f"▶ {cmd_str}"}

        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        if proc.stdout:
            for line in proc.stdout:
                yield {"type": "log", "line": line.rstrip()}
        proc.wait()

        if proc.returncode == 0:
            yield {"type": "done", "ok": True, "message": f"{info.label} installed"}
        else:
            yield {"type": "done", "ok": False, "error": f"npm install failed (exit {proc.returncode})"}

    yield {"type": "log", "line": f"Installing {info.label}..."}

    cmd = info.install_cmd
    if cmd[0] == "pip":
        yield from _pip_install()
    elif cmd[0] == "__hugo_binary__":
        yield from _hugo_binary_install()
    elif cmd[0] in ("npm", "npx"):
        yield from _npm_install()
    else:
        cmd_str = ' '.join(cmd)
        yield {"type": "log", "line": f"▶ {cmd_str}"}
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            )
            if proc.stdout:
                for line in proc.stdout:
                    yield {"type": "log", "line": line.rstrip()}
            proc.wait()
            ok = proc.returncode == 0
            if ok:
                yield {"type": "done", "ok": True, "message": f"{info.label} installed"}
            else:
                yield {"type": "done", "ok": False, "error": f"Install failed (exit {proc.returncode})"}
        except Exception as e:
            yield {"type": "done", "ok": False, "error": str(e)}


# ── Build streaming (SSE generator) ────────────────────────────────


def build_segment_stream(
    project_root: Path,
    name: str,
    *,
    clean: bool = False,
    wipe: bool = False,
    no_minify: bool = False,
):
    """Generator that yields SSE event dicts for a build pipeline.

    Caller wraps events in ``data: {json}\\n\\n`` for SSE transport.

    Args:
        project_root: Project root.
        name: Segment name.
        clean: If True, pass clean=True to builder config.
        wipe: If True, nuke entire workspace before building.
        no_minify: If True, set build_mode to no-minify.

    Yields:
        Dicts with 'type' key: pipeline_start, stage_start, log,
        stage_done, stage_error, pipeline_done, error.
    """
    ensure_gitignore(project_root)

    segment = get_segment(project_root, name)
    if segment is None:
        yield {"type": "error", "message": f"Segment not found: {name}"}
        return

    builder = get_builder(segment.builder)
    if builder is None or not builder.detect():
        yield {"type": "error", "message": f"Builder '{segment.builder}' not available"}
        return

    source_path = (project_root / segment.source).resolve()
    if not source_path.is_dir():
        yield {"type": "error", "message": f"Source not found: {segment.source}"}
        return

    segment.source = str(source_path)
    workspace = project_root / PAGES_WORKSPACE / name

    if wipe and workspace.is_dir():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True, exist_ok=True)

    if clean:
        segment.config["clean"] = True
    if no_minify:
        segment.config["build_mode"] = "no-minify"

    pipeline_start = time.monotonic()
    stages_info = builder.pipeline_stages()

    yield {
        "type": "pipeline_start",
        "segment": name,
        "builder": segment.builder,
        "stages": [{"name": s.name, "label": s.label} for s in stages_info],
    }

    stage_results = []
    all_ok = True

    for si in stages_info:
        yield {"type": "stage_start", "stage": si.name, "label": si.label}

        stage_start = time.monotonic()
        error = ""

        try:
            for line in builder.run_stage(si.name, segment, workspace):
                yield {"type": "log", "line": line, "stage": si.name}
            status = "done"
        except RuntimeError as e:
            error = str(e)
            status = "error"
            all_ok = False
        except Exception as e:
            error = f"Unexpected: {e}"
            status = "error"
            all_ok = False

        stage_ms = int((time.monotonic() - stage_start) * 1000)
        stage_results.append({
            "name": si.name,
            "label": si.label,
            "status": status,
            "duration_ms": stage_ms,
            "error": error,
        })

        if status == "done":
            yield {
                "type": "stage_done", "stage": si.name,
                "label": si.label, "duration_ms": stage_ms,
            }
        else:
            yield {
                "type": "stage_error", "stage": si.name,
                "label": si.label, "error": error, "duration_ms": stage_ms,
            }
            remaining = stages_info[stages_info.index(si) + 1:]
            for rem in remaining:
                stage_results.append({
                    "name": rem.name, "label": rem.label,
                    "status": "skipped", "duration_ms": 0, "error": "",
                })
            break

    total_ms = int((time.monotonic() - pipeline_start) * 1000)

    serve_url = ""
    if all_ok:
        output = builder.output_dir(workspace)
        serve_url = f"/pages/site/{name}/"

        meta = {
            "segment": name,
            "builder": segment.builder,
            "built_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "duration_ms": total_ms,
            "output_dir": str(output),
            "serve_url": serve_url,
        }
        (workspace / "build.json").write_text(
            json.dumps(meta, indent=2), encoding="utf-8",
        )

    yield {
        "type": "pipeline_done",
        "ok": all_ok,
        "segment": name,
        "total_ms": total_ms,
        "serve_url": serve_url,
        "stages": stage_results,
        "duration_ms": total_ms,
        "error": stage_results[-1]["error"] if not all_ok else "",
    }

