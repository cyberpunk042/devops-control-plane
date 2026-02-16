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
from src.core.services.pages_engine import (
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
