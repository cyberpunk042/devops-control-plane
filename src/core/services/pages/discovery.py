"""
Pages discovery — builder listing, feature listing, auto-init.

Handles builder/feature metadata retrieval, file-to-segment resolution,
and automatic segment initialization from project.yml content_folders.
"""

from __future__ import annotations

from pathlib import Path

from src.core.services.pages_builders import (
    SegmentConfig,
    get_builder,
    list_builders,
)
from .engine import (
    _get_pages_config,
    _load_project_yml,
    add_segment,
    ensure_gitignore,
    get_build_status,
    get_segments,
)


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


# ── Setup detection (for wizard) ───────────────────────────────────


def detect_pages_setup(project_root: Path) -> dict:
    """Detect pages setup state for the full setup wizard.

    Returns rich detection data showing what exists and what can be created.

    Returns:
        {
            "existing_segments": [{name, source, builder, path, auto, has_build}],
            "detected_folders": [{name, path, builder, reason, suggestion, exists}],
            "detected_smart_folders": [{name, label, target, builder, exists}],
            "builders": [{name, label, available, description}],
        }
    """
    project_data = _load_project_yml(project_root)
    pages = _get_pages_config(project_root)
    existing = pages.get("segments", [])
    existing_names = {s.get("name") for s in existing}

    # Existing segments with build status
    existing_segments = []
    for s in existing:
        build = get_build_status(project_root, s.get("name", ""))
        existing_segments.append({
            "name": s.get("name", ""),
            "source": s.get("source", ""),
            "builder": s.get("builder", "raw"),
            "path": s.get("path", ""),
            "auto": s.get("auto", False),
            "has_build": build is not None,
        })

    # Detected content folders
    content_folders = project_data.get("content_folders", [])
    detected_folders = []
    for folder in content_folders:
        folder_path = project_root / folder
        if not folder_path.is_dir():
            continue
        builder_name, reason, suggestion = detect_best_builder(folder_path)
        detected_folders.append({
            "name": folder,
            "path": str(folder_path),
            "builder": builder_name,
            "reason": reason,
            "suggestion": suggestion,
            "exists": folder in existing_names,
        })

    # Detected standalone smart folders
    smart_folders = project_data.get("smart_folders", [])
    content_set = set(content_folders)
    detected_smart = []
    for sf in smart_folders:
        name = sf.get("name", "")
        target = sf.get("target", "")
        if not name:
            continue
        if target in content_set:
            continue  # Not standalone
        detected_smart.append({
            "name": name,
            "label": sf.get("label", name),
            "target": target,
            "builder": "docusaurus",
            "exists": name in existing_names,
        })

    # Available builders
    builders = []
    for b in list_builders():
        builders.append({
            "name": b.name,
            "label": b.label,
            "available": b.available,
            "description": b.description,
        })

    return {
        "existing_segments": existing_segments,
        "detected_folders": detected_folders,
        "detected_smart_folders": detected_smart,
        "builders": builders,
    }


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


def init_pages_from_project(
    project_root: Path,
    flush_auto: bool = False,
    keep_segments: list[str] | None = None,
) -> dict:
    """Initialize pages segments from project.yml content_folders.

    Also creates segments for standalone smart folders (target == name).
    Smart folders targeting an existing content folder are handled
    by the builder's source stage during build.

    Args:
        project_root: Project root directory.
        flush_auto: If True, remove all auto-detected segments first.
        keep_segments: Segment names to preserve even during flush.

    Returns:
        {"ok": True, "added": [...], "removed": [...], "kept": [...],
         "details": [...], "total_segments": int}
    """
    project_data = _load_project_yml(project_root)
    pages = _get_pages_config(project_root)
    keep_set = set(keep_segments or [])

    removed = []
    kept = []
    if flush_auto:
        existing = pages.get("segments", [])
        for seg in list(existing):
            seg_name = seg.get("name", "")
            if seg.get("auto", False) and seg_name not in keep_set:
                try:
                    from .engine import remove_segment
                    remove_segment(project_root, seg_name)
                    removed.append(seg_name)
                except Exception:
                    pass
            elif seg_name in keep_set:
                kept.append(seg_name)
        # Reload after removals
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

    # ── Standalone smart folders (target == name) ────────────────
    # These become their own Pages segment. Smart folders targeting
    # an existing content folder are injected during the builder's
    # source stage, so they don't need a segment here.
    smart_folders = project_data.get("smart_folders", [])
    content_set = set(content_folders)
    for sf in smart_folders:
        name = sf.get("name", "")
        target = sf.get("target", "")
        if not name:
            continue
        # Only create a segment for standalone smart folders
        if target in content_set:
            continue
        if name in existing_names or name in {d["name"] for d in details}:
            continue

        # Standalone smart folder — use raw builder (build stage
        # will stage files from source directories)
        seg = SegmentConfig(
            name=name,
            source=name,  # virtual — builder will stage from smart folder sources
            builder="docusaurus",
            path=f"/{name}",
            auto=True,
        )
        try:
            add_segment(project_root, seg)
            added.append(name)
            details.append({
                "name": name,
                "builder": "raw",
                "reason": f"Standalone smart folder ({sf.get('label', name)})",
                "suggestion": "",
            })
        except ValueError:
            pass

    ensure_gitignore(project_root)

    return {
        "ok": True,
        "added": added,
        "removed": removed,
        "kept": kept,
        "details": details,
        "total_segments": len(pages.get("segments", [])) + len(added),
    }
