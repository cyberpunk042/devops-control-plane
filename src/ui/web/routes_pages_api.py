"""
Pages API routes — segment CRUD, build, deploy.

Blueprint: pages_api_bp
Prefix: /api

Endpoints:
    GET  /pages/segments         — list all segments
    POST /pages/segments         — add a new segment
    PUT  /pages/segments/<name>  — update segment config
    DEL  /pages/segments/<name>  — remove a segment
    GET  /pages/meta             — get pages metadata (base_url, deploy_branch)
    PUT  /pages/meta             — update pages metadata
    GET  /pages/builders         — list available builders
    GET  /pages/features          — list builder features for config wizard
    POST /pages/build/<name>     — build a single segment
    POST /pages/build-all        — build all segments
    GET  /pages/build/<name>/status — get build status
    POST /pages/merge            — merge all built segments
    POST /pages/deploy           — deploy merged output to gh-pages
    POST /pages/init             — initialize pages config for this project
"""

from __future__ import annotations

import logging
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

logger = logging.getLogger(__name__)

pages_api_bp = Blueprint("pages_api", __name__)


def _project_root() -> Path:
    return Path(current_app.config["PROJECT_ROOT"])


# ── Segments CRUD ───────────────────────────────────────────────────


@pages_api_bp.route("/pages/segments")
def list_segments():  # type: ignore[no-untyped-def]
    """List all configured segments."""
    from src.ui.web.pages_engine import get_build_status, get_segments

    root = _project_root()
    segments = get_segments(root)

    result = []
    for seg in segments:
        build = get_build_status(root, seg.name)
        result.append({
            "name": seg.name,
            "source": seg.source,
            "builder": seg.builder,
            "path": seg.path,
            "auto": seg.auto,
            "config": seg.config,
            "build": build,
        })

    return jsonify({"segments": result})


@pages_api_bp.route("/pages/segments", methods=["POST"])
def create_segment():  # type: ignore[no-untyped-def]
    """Add a new segment."""
    from src.core.services.pages_builders import SegmentConfig
    from src.ui.web.pages_engine import add_segment, ensure_gitignore

    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "Segment name is required"}), 400

    source = data.get("source", "").strip()
    if not source:
        return jsonify({"error": "Source folder is required"}), 400

    # Validate source exists
    root = _project_root()
    source_path = root / source
    if not source_path.is_dir():
        return jsonify({"error": f"Source folder not found: {source}"}), 400

    segment = SegmentConfig(
        name=name,
        source=source,
        builder=data.get("builder", "raw"),
        path=data.get("path", f"/{name}"),
        auto=data.get("auto", False),
        config=data.get("config", {}),
    )

    try:
        add_segment(root, segment)
        ensure_gitignore(root)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    return jsonify({"ok": True, "segment": name})


@pages_api_bp.route("/pages/segments/<name>", methods=["PUT"])
def update_segment_route(name: str):  # type: ignore[no-untyped-def]
    """Update segment config."""
    from src.ui.web.pages_engine import update_segment

    data = request.get_json(silent=True) or {}
    try:
        update_segment(_project_root(), name, data)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404

    return jsonify({"ok": True})


@pages_api_bp.route("/pages/segments/<name>", methods=["DELETE"])
def delete_segment_route(name: str):  # type: ignore[no-untyped-def]
    """Remove a segment."""
    from src.ui.web.pages_engine import remove_segment

    remove_segment(_project_root(), name)
    return jsonify({"ok": True})


# ── Pages metadata ──────────────────────────────────────────────────


@pages_api_bp.route("/pages/meta")
def get_meta():  # type: ignore[no-untyped-def]
    """Get top-level pages config."""
    from src.ui.web.pages_engine import get_pages_meta

    return jsonify(get_pages_meta(_project_root()))


@pages_api_bp.route("/pages/meta", methods=["PUT"])
def set_meta():  # type: ignore[no-untyped-def]
    """Update pages metadata."""
    from src.ui.web.pages_engine import set_pages_meta

    data = request.get_json(silent=True) or {}
    set_pages_meta(_project_root(), data)
    return jsonify({"ok": True})


# ── Builders ────────────────────────────────────────────────────────


@pages_api_bp.route("/pages/builders")
def list_builders_route():  # type: ignore[no-untyped-def]
    """List available page builders with pipeline stage info."""
    from src.core.services.pages_builders import get_builder, list_builders

    builders = list_builders()
    result = []
    for b in builders:
        builder_obj = get_builder(b.name)
        stages = []
        config_fields = []
        if builder_obj:
            stages = [{"name": s.name, "label": s.label} for s in builder_obj.pipeline_stages()]
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
    return jsonify({"builders": result})


@pages_api_bp.route("/pages/resolve-file")
def resolve_file_to_pages():  # type: ignore[no-untyped-def]
    """Resolve a content vault file path to Pages preview URLs.

    Given a vault path like 'docs/getting-started.md', finds any segment
    whose source folder contains this file and returns preview URLs for
    each matching segment's built output.

    Query params:
        path: vault file path (relative to project root)
    """
    from src.ui.web.pages_engine import get_build_status, get_segments

    file_path = request.args.get("path", "").strip()
    if not file_path:
        return jsonify({"matches": []})

    root = _project_root()
    segments = get_segments(root)
    matches = []

    for seg in segments:
        source = seg.source.rstrip("/")
        # Check if the file is under this segment's source folder
        if not file_path.startswith(source + "/") and file_path != source:
            continue

        build = get_build_status(root, seg.name)
        if not build:
            continue

        # Compute the doc-relative path (strip source prefix, strip .md/.mdx)
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
            doc_slug = doc_slug[:-6]  # strip trailing /index

        # Build preview URL — serve route is /pages/site/<name>/<path>
        # base_path is for merged output only, NOT individual preview
        preview_url = f"/pages/site/{seg.name}/{doc_slug}" if doc_slug else f"/pages/site/{seg.name}/"

        matches.append({
            "segment": seg.name,
            "builder": seg.builder,
            "preview_url": preview_url,
            "built": bool(build),
        })

    return jsonify({"matches": matches})


@pages_api_bp.route("/pages/features")
def list_features_route():  # type: ignore[no-untyped-def]
    """List available builder features for the configuration wizard.

    Returns the feature registry grouped by category, with labels,
    descriptions, defaults, and dependency info. The UI renders this
    as the step-by-step configuration wizard.
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

    return jsonify({"categories": categories})


@pages_api_bp.route("/pages/builders/<name>/install", methods=["POST"])
def install_builder_route(name: str):  # type: ignore[no-untyped-def]
    """Install a builder's dependencies.

    Strategies:
    - pip-based (mkdocs, sphinx): uses venv pip
    - Hugo: downloads binary from GitHub releases to ~/.local/bin/
    - npm-based: uses npm install -g
    """
    import json
    import os
    import platform
    import subprocess
    import sys
    import tarfile
    import tempfile
    import urllib.request

    from flask import Response

    from src.core.services.pages_builders import get_builder

    builder = get_builder(name)
    if builder is None:
        return jsonify({"ok": False, "error": f"Builder '{name}' not found"}), 404

    info = builder.info()
    if not info.install_cmd:
        return jsonify({"ok": False, "error": f"Builder '{name}' has no auto-install command"}), 400

    if builder.detect():
        return jsonify({"ok": True, "already_installed": True})

    def _pip_install() -> list[str]:  # type: ignore[no-untyped-def]
        """Install via pip in the project venv."""
        cmd = list(info.install_cmd)
        cmd[0] = str(Path(sys.executable).parent / "pip")

        cmd_str = ' '.join(cmd)
        yield f"data: {json.dumps({'type': 'log', 'line': f'▶ {cmd_str}'})}\n\n"

        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        if proc.stdout:
            for line in proc.stdout:
                yield f"data: {json.dumps({'type': 'log', 'line': line.rstrip()})}\n\n"
        proc.wait()

        if proc.returncode == 0:
            yield f"data: {json.dumps({'type': 'done', 'ok': True, 'message': f'{info.label} installed in venv'})}\n\n"
        else:
            yield f"data: {json.dumps({'type': 'done', 'ok': False, 'error': f'pip install failed (exit {proc.returncode})'})}\n\n"

    def _glibc_version() -> str:
        """Get the system's GLIBC version."""
        try:
            import ctypes
            libc = ctypes.CDLL("libc.so.6")
            libc.gnu_get_libc_version.restype = ctypes.c_char_p
            return libc.gnu_get_libc_version().decode()
        except Exception:
            return "unknown"

    def _hugo_binary_install() -> list[str]:  # type: ignore[no-untyped-def]
        """Download Hugo binary from GitHub releases."""
        local_bin = Path.home() / ".local" / "bin"
        local_bin.mkdir(parents=True, exist_ok=True)

        # Detect architecture
        machine = platform.machine().lower()
        if machine in ("x86_64", "amd64"):
            arch = "amd64"
        elif machine in ("aarch64", "arm64"):
            arch = "arm64"
        else:
            yield f"data: {json.dumps({'type': 'done', 'ok': False, 'error': f'Unsupported arch: {machine}'})}\n\n"
            return

        system = platform.system().lower()
        if system != "linux":
            yield f"data: {json.dumps({'type': 'done', 'ok': False, 'error': f'Hugo binary download only supports Linux, got {system}'})}\n\n"
            return

        yield f"data: {json.dumps({'type': 'log', 'line': f'Detecting latest Hugo release for linux/{arch}...'})}\n\n"

        try:
            # Get latest release tag
            req = urllib.request.Request(
                "https://api.github.com/repos/gohugoio/hugo/releases/latest",
                headers={"Accept": "application/vnd.github.v3+json", "User-Agent": "devops-cp"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                release = json.loads(resp.read().decode())

            version = release["tag_name"].lstrip("v")
            yield f"data: {json.dumps({'type': 'log', 'line': f'Latest version: {version}  (GLIBC: {_glibc_version()})'})}\n\n"

            # Try non-extended first (statically linked, works on older glibc)
            # then extended (needs newer glibc)
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
                yield f"data: {json.dumps({'type': 'done', 'ok': False, 'error': f'Could not find release asset for linux/{arch}'})}\n\n"
                return

            yield f"data: {json.dumps({'type': 'log', 'line': f'Downloading {tarball_name}...'})}\n\n"

            # Download to temp
            with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
                urllib.request.urlretrieve(dl_url, tmp.name)
                tmp_path = tmp.name

            yield f"data: {json.dumps({'type': 'log', 'line': 'Extracting...'})}\n\n"

            with tarfile.open(tmp_path, "r:gz") as tar:
                for member in tar.getmembers():
                    if member.name == "hugo" or member.name.endswith("/hugo"):
                        member.name = "hugo"  # Flatten path
                        tar.extract(member, path=str(local_bin))
                        break

            os.unlink(tmp_path)

            # Make executable
            hugo_path = local_bin / "hugo"
            hugo_path.chmod(0o755)

            # Ensure ~/.local/bin is on PATH for this process
            path_dirs = os.environ.get("PATH", "").split(":")
            if str(local_bin) not in path_dirs:
                os.environ["PATH"] = f"{local_bin}:{os.environ.get('PATH', '')}"

            # Verify
            r = subprocess.run([str(hugo_path), "version"], capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                yield f"data: {json.dumps({'type': 'log', 'line': r.stdout.strip()})}\n\n"
                yield f"data: {json.dumps({'type': 'done', 'ok': True, 'message': f'Hugo {version} installed to {hugo_path}'})}\n\n"
            else:
                err_detail = (r.stderr or r.stdout or "unknown error").strip()
                yield f"data: {json.dumps({'type': 'log', 'line': f'Execution failed: {err_detail}'})}\n\n"
                yield f"data: {json.dumps({'type': 'done', 'ok': False, 'error': f'Hugo binary failed: {err_detail}'})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'done', 'ok': False, 'error': f'Download failed: {e}'})}\n\n"

    def _npm_install() -> list[str]:  # type: ignore[no-untyped-def]
        """Install via npm (for node-based tools)."""
        cmd = list(info.install_cmd)
        cmd_str = ' '.join(cmd)
        yield f"data: {json.dumps({'type': 'log', 'line': f'▶ {cmd_str}'})}\n\n"

        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        if proc.stdout:
            for line in proc.stdout:
                yield f"data: {json.dumps({'type': 'log', 'line': line.rstrip()})}\n\n"
        proc.wait()

        if proc.returncode == 0:
            yield f"data: {json.dumps({'type': 'done', 'ok': True, 'message': f'{info.label} installed'})}\n\n"
        else:
            yield f"data: {json.dumps({'type': 'done', 'ok': False, 'error': f'npm install failed (exit {proc.returncode})'})}\n\n"

    def stream():  # type: ignore[no-untyped-def]
        yield f"data: {json.dumps({'type': 'log', 'line': f'Installing {info.label}...'})}\n\n"

        # Route to the correct install strategy
        cmd = info.install_cmd
        if cmd[0] == "pip":
            yield from _pip_install()
        elif cmd[0] == "__hugo_binary__":
            yield from _hugo_binary_install()
        elif cmd[0] in ("npm", "npx"):
            yield from _npm_install()
        else:
            # Generic subprocess
            cmd_str = ' '.join(cmd)
            yield f"data: {json.dumps({'type': 'log', 'line': f'▶ {cmd_str}'})}\n\n"
            try:
                proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                )
                if proc.stdout:
                    for line in proc.stdout:
                        yield f"data: {json.dumps({'type': 'log', 'line': line.rstrip()})}\n\n"
                proc.wait()
                ok = proc.returncode == 0
                if ok:
                    yield f"data: {json.dumps({'type': 'done', 'ok': True, 'message': f'{info.label} installed'})}\n\n"
                else:
                    yield f"data: {json.dumps({'type': 'done', 'ok': False, 'error': f'Install failed (exit {proc.returncode})'})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'type': 'done', 'ok': False, 'error': str(e)})}\n\n"

    return Response(stream(), mimetype="text/event-stream")


# ── Build ───────────────────────────────────────────────────────────


@pages_api_bp.route("/pages/build/<name>", methods=["POST"])
def build_segment_route(name: str):  # type: ignore[no-untyped-def]
    """Build a single segment."""
    from src.ui.web.pages_engine import build_segment, ensure_gitignore

    ensure_gitignore(_project_root())
    result = build_segment(_project_root(), name)
    return jsonify({
        "ok": result.ok,
        "segment": result.segment,
        "duration_ms": result.duration_ms,
        "output_dir": str(result.output_dir) if result.output_dir else None,
        "error": result.error,
        "log": result.log,
    })


@pages_api_bp.route("/pages/build/<name>/status")
def build_status_route(name: str):  # type: ignore[no-untyped-def]
    """Get build status for a segment."""
    from src.ui.web.pages_engine import get_build_status

    status = get_build_status(_project_root(), name)
    if status is None:
        return jsonify({"built": False})
    return jsonify({"built": True, **status})


@pages_api_bp.route("/pages/build-all", methods=["POST"])
def build_all_route():  # type: ignore[no-untyped-def]
    """Build all segments."""
    from src.ui.web.pages_engine import build_segment, ensure_gitignore, get_segments

    root = _project_root()
    ensure_gitignore(root)
    segments = get_segments(root)

    results = []
    for seg in segments:
        r = build_segment(root, seg.name)
        results.append({
            "ok": r.ok,
            "segment": r.segment,
            "duration_ms": r.duration_ms,
            "error": r.error,
        })

    ok = all(r["ok"] for r in results)
    return jsonify({"ok": ok, "results": results})


# ── Merge + Deploy ──────────────────────────────────────────────────


@pages_api_bp.route("/pages/merge", methods=["POST"])
def merge_route():  # type: ignore[no-untyped-def]
    """Merge all built segments into a single output."""
    from src.ui.web.pages_engine import merge_segments

    return jsonify(merge_segments(_project_root()))


@pages_api_bp.route("/pages/deploy", methods=["POST"])
def deploy_route():  # type: ignore[no-untyped-def]
    """Deploy merged output to gh-pages."""
    from src.ui.web.pages_engine import deploy_to_ghpages

    return jsonify(deploy_to_ghpages(_project_root()))


# ── Init ────────────────────────────────────────────────────────────


@pages_api_bp.route("/pages/init", methods=["POST"])
def init_pages():  # type: ignore[no-untyped-def]
    """Initialize pages config from project.yml content_folders.

    Detects markdown content and picks the best available builder:
      - .md/.mdx files present → docusaurus (if node available) → mkdocs → raw
      - Otherwise → raw
    """
    from src.ui.web.pages_engine import (
        _get_pages_config,
        _load_project_yml,
        add_segment,
        ensure_gitignore,
    )
    from src.core.services.pages_builders import SegmentConfig, get_builder

    root = _project_root()
    project_data = _load_project_yml(root)

    pages = _get_pages_config(root)
    existing_names = {s.get("name") for s in pages.get("segments", [])}

    content_folders = project_data.get("content_folders", [])

    added = []
    details = []  # per-segment detection info
    for folder in content_folders:
        folder_path = root / folder
        if not folder_path.is_dir():
            continue
        if folder in existing_names:
            continue

        # Detect best builder based on folder contents
        builder_name, reason, suggestion = _detect_best_builder(folder_path, get_builder)

        seg = SegmentConfig(
            name=folder,
            source=folder,
            builder=builder_name,
            path=f"/{folder}",
            auto=True,
        )
        try:
            add_segment(root, seg)
            added.append(folder)
            details.append({
                "name": folder,
                "builder": builder_name,
                "reason": reason,
                "suggestion": suggestion,
            })
        except ValueError:
            pass

    ensure_gitignore(root)

    return jsonify({
        "ok": True,
        "added": added,
        "details": details,
        "total_segments": len(pages.get("segments", [])) + len(added),
    })


def _detect_best_builder(folder: Path, get_builder_fn) -> tuple[str, str, str]:  # type: ignore[no-untyped-def]
    """Detect the best builder for a content folder.

    Returns (builder_name, reason, suggestion).

    Strategy:
      1. If folder has .md or .mdx files → documentation site
         - Prefer docusaurus (if node/npm detected)
         - Then mkdocs (if installed)
      2. If folder has index.html → raw (already a static site)
      3. Fallback → raw
    """
    # Check for markdown files (non-recursively in top level + one level deep)
    has_markdown = False
    for ext in ("*.md", "*.mdx"):
        if list(folder.glob(ext)) or list(folder.glob(f"*/{ext}")):
            has_markdown = True
            break

    if has_markdown:
        # Try docusaurus first (best experience for docs)
        docusaurus = get_builder_fn("docusaurus")
        if docusaurus and docusaurus.detect():
            return "docusaurus", "Markdown files detected, Node.js available", ""

        # Then mkdocs
        mkdocs = get_builder_fn("mkdocs")
        if mkdocs and mkdocs.detect():
            return "mkdocs", "Markdown files detected, MkDocs available", "Install Node.js for Docusaurus (better UX)"

        # Markdown found but no good builder available
        return "raw", "Markdown files detected but no doc builder available", "Install Node.js (for Docusaurus) or pip install mkdocs"

    return "raw", "Static files (no markdown detected)", ""


# ── Preview ─────────────────────────────────────────────────────────


@pages_api_bp.route("/pages/preview/<name>", methods=["POST"])
def start_preview_route(name: str):  # type: ignore[no-untyped-def]
    """Start a preview server for a segment."""
    from src.ui.web.pages_engine import start_preview

    return jsonify(start_preview(_project_root(), name))


@pages_api_bp.route("/pages/preview/<name>", methods=["DELETE"])
def stop_preview_route(name: str):  # type: ignore[no-untyped-def]
    """Stop a preview server."""
    from src.ui.web.pages_engine import stop_preview

    return jsonify(stop_preview(name))


@pages_api_bp.route("/pages/previews")
def list_previews_route():  # type: ignore[no-untyped-def]
    """List running preview servers."""
    from src.ui.web.pages_engine import list_previews

    return jsonify({"previews": list_previews()})


# ── CI Workflow Generation ──────────────────────────────────────────


@pages_api_bp.route("/pages/generate-ci", methods=["POST"])
def generate_ci_route():  # type: ignore[no-untyped-def]
    """Generate GitHub Actions workflow for Pages deployment."""
    from src.ui.web.pages_engine import generate_ci_workflow

    return jsonify(generate_ci_workflow(_project_root()))


# ── SSE Build Log Streaming (Pipeline-Aware) ───────────────────────


@pages_api_bp.route("/pages/build-stream/<name>", methods=["POST"])
def build_stream_route(name: str):  # type: ignore[no-untyped-def]
    """Build a segment with stage-aware SSE streaming.

    Emits events:
      - {type: 'pipeline_start', stages: [...], segment, builder}
      - {type: 'stage_start', stage, label}
      - {type: 'log', line, stage}
      - {type: 'stage_done', stage, label, duration_ms}  (or stage_error)
      - {type: 'pipeline_done', ok, segment, total_ms, serve_url, stages: [...]}
    """
    import json
    import time

    from flask import Response

    from src.core.services.pages_builders import get_builder
    from src.ui.web.pages_engine import (
        PAGES_WORKSPACE,
        ensure_gitignore,
        get_segment,
    )

    root = _project_root()
    ensure_gitignore(root)

    segment = get_segment(root, name)
    if segment is None:
        def error_stream():  # type: ignore[no-untyped-def]
            yield f"data: {json.dumps({'type': 'error', 'message': f'Segment not found: {name}'})}\n\n"
        return Response(error_stream(), mimetype="text/event-stream")

    builder = get_builder(segment.builder)
    if builder is None or not builder.detect():
        def error_stream():  # type: ignore[no-untyped-def]
            msg = f"Builder '{segment.builder}' not available"
            yield f"data: {json.dumps({'type': 'error', 'message': msg})}\n\n"
        return Response(error_stream(), mimetype="text/event-stream")

    # Resolve source
    source_path = (root / segment.source).resolve()
    if not source_path.is_dir():
        def error_stream():  # type: ignore[no-untyped-def]
            yield f"data: {json.dumps({'type': 'error', 'message': f'Source not found: {segment.source}'})}\n\n"
        return Response(error_stream(), mimetype="text/event-stream")

    segment.source = str(source_path)
    workspace = root / PAGES_WORKSPACE / name
    workspace.mkdir(parents=True, exist_ok=True)

    # Support ?clean=true for clean builds (wipe caches)
    # Support ?wipe=true for full rebuild (wipe entire workspace)
    # Support ?no_minify=true for builds without minification
    from flask import request as _req
    import shutil as _shutil

    if _req.args.get("wipe", "").lower() in ("true", "1", "yes"):
        # Full rebuild: nuke the entire workspace and recreate
        if workspace.is_dir():
            _shutil.rmtree(workspace)
        workspace.mkdir(parents=True, exist_ok=True)

    if _req.args.get("clean", "").lower() in ("true", "1", "yes"):
        segment.config["clean"] = True
    no_minify = _req.args.get("no_minify", "").lower()
    if no_minify in ("true", "1", "yes"):
        segment.config["build_mode"] = "no-minify"

    def stream():  # type: ignore[no-untyped-def]
        pipeline_start = time.monotonic()
        stages_info = builder.pipeline_stages()

        # Announce pipeline start with all stages
        yield f"data: {json.dumps({'type': 'pipeline_start', 'segment': name, 'builder': segment.builder, 'stages': [{'name': s.name, 'label': s.label} for s in stages_info]})}\n\n"

        stage_results = []
        all_ok = True

        for si in stages_info:
            # Announce stage start
            yield f"data: {json.dumps({'type': 'stage_start', 'stage': si.name, 'label': si.label})}\n\n"

            stage_start = time.monotonic()
            log_lines = []
            error = ""

            try:
                for line in builder.run_stage(si.name, segment, workspace):
                    log_lines.append(line)
                    yield f"data: {json.dumps({'type': 'log', 'line': line, 'stage': si.name})}\n\n"
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
                yield f"data: {json.dumps({'type': 'stage_done', 'stage': si.name, 'label': si.label, 'duration_ms': stage_ms})}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'stage_error', 'stage': si.name, 'label': si.label, 'error': error, 'duration_ms': stage_ms})}\n\n"
                # Mark remaining stages as skipped
                remaining = stages_info[stages_info.index(si) + 1:]
                for rem in remaining:
                    stage_results.append({"name": rem.name, "label": rem.label, "status": "skipped", "duration_ms": 0, "error": ""})
                break

        total_ms = int((time.monotonic() - pipeline_start) * 1000)

        # Compute serve URL — use segment name to match the Flask route
        serve_url = ""
        if all_ok:
            output = builder.output_dir(workspace)
            serve_url = f"/pages/site/{name}/"

            # Write build metadata
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

        result = {
            "type": "pipeline_done",
            "ok": all_ok,
            "segment": name,
            "total_ms": total_ms,
            "serve_url": serve_url,
            "stages": stage_results,
            # Legacy fields for backward compat
            "duration_ms": total_ms,
            "error": stage_results[-1]["error"] if not all_ok else "",
        }
        yield f"data: {json.dumps(result)}\n\n"

    return Response(stream(), mimetype="text/event-stream")
