"""
Smart Folder Peek — data aggregation service.

Aggregates all data needed by the peek panel in a single call:
overview text, flattened outline, doc tree summary, and references.

Public API:
    peek_module(project_root, resolved, module_name) → dict
    peek_topic(project_root, resolved, module_name, topic_path) → dict

Dependencies:
    - src.core.services.content.outline.extract_outline  (heading extraction)
    - src.core.services.peek.scan_and_resolve_all        (cross-references)
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ── Public API ──────────────────────────────────────────────────────


def peek_module(
    project_root: Path,
    resolved: dict,
    module_name: str,
) -> dict:
    """Aggregate peek data for a module card.

    Args:
        project_root: Absolute path to the project root.
        resolved: Full resolved smart folder dict (from sf.resolve()).
        module_name: Module name (e.g. "core", "cli").

    Returns:
        Dict with keys:
            type:     "module"
            module:   str
            module_path: str
            overview: {text, source_path, line_count, size} | None
            outline:  [{text, level}, ...]   (flat, max 15 items)
            doc_tree: [{name, has_doc, source_path, children}, ...]
            stats:    {total_docs, total_topics, depth}
    """
    group = _find_group(resolved, module_name)
    if group is None:
        return {
            "type": "module",
            "module": module_name,
            "error": f"Module '{module_name}' not found",
        }

    tree = group["tree"]
    module_path = group["module_path"]

    # --- Overview: find root README and extract text ---
    doc = _find_first_doc(tree, 3)
    overview = None
    outline: list[dict] = []

    if doc:
        source_path = doc["source_path"]
        file_path = project_root / source_path

        if file_path.is_file():
            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
                # Send raw markdown (truncated) — frontend renders it
                text = content[:1500]
                if len(content) > 1500:
                    text += "\n\n…"
                overview = {
                    "text": text,
                    "source_path": source_path,
                    "line_count": content.count("\n") + 1,
                    "size": len(content.encode("utf-8")),
                }

                # --- Outline: extract and flatten ---
                outline = _get_flat_outline(file_path, content, 15)

            except OSError as exc:
                logger.warning("Cannot read %s for peek: %s", source_path, exc)

    # --- Doc tree summary ---
    doc_tree = _build_doc_tree_summary(tree.get("children", []))

    # --- Stats ---
    total_topics = _count_topics(tree)
    depth = _tree_depth(tree)

    return {
        "type": "module",
        "module": module_name,
        "module_path": module_path,
        "overview": overview,
        "outline": outline,
        "doc_tree": doc_tree,
        "stats": {
            "total_docs": group["file_count"],
            "total_topics": total_topics,
            "depth": depth,
        },
    }


def peek_topic(
    project_root: Path,
    resolved: dict,
    module_name: str,
    topic_path: str,
) -> dict:
    """Aggregate peek data for a ToC topic entry.

    Args:
        project_root: Absolute path to the project root.
        resolved: Full resolved smart folder dict (from sf.resolve()).
        module_name: Module name (e.g. "core", "cli").
        topic_path: Slash-separated path within the module tree
                    (e.g. "audit" or "services/audit").

    Returns:
        Dict with keys:
            type:         "topic"
            module:       str
            topic:        str  (leaf name)
            topic_path:   str  (full path within module)
            preview_text: str | None  (raw markdown, truncated)
            outline:      [{text, level}, ...]   (flat, max 12 items)
            sub_topics:   [{name, has_doc}, ...]
            references:   [{text, type, resolved_path}, ...]
            source_path:  str | None
    """
    group = _find_group(resolved, module_name)
    if group is None:
        return {
            "type": "topic",
            "module": module_name,
            "topic_path": topic_path,
            "error": f"Module '{module_name}' not found",
        }

    tree = group["tree"]
    node = _find_topic_node(tree, topic_path)
    if node is None:
        return {
            "type": "topic",
            "module": module_name,
            "topic_path": topic_path,
            "error": f"Topic '{topic_path}' not found in module '{module_name}'",
        }

    # --- Find the README for this topic ---
    doc = _find_first_doc(node, 3)
    preview_text: str | None = None
    outline: list[dict] = []
    references: list[dict] = []
    source_path: str | None = None

    if doc:
        source_path = doc["source_path"]
        file_path = project_root / source_path

        if file_path.is_file():
            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")

                # Truncated raw markdown for preview (first ~2000 chars)
                preview_text = content[:2000]
                if len(content) > 2000:
                    preview_text += "\n\n…"

                # Outline
                outline = _get_flat_outline(file_path, content, 12)

                # References (cross-document links)
                references = _get_references(
                    project_root, source_path, content,
                )

            except OSError as exc:
                logger.warning("Cannot read %s for peek: %s", source_path, exc)

    # --- Sub-topics ---
    sub_topics = [
        {
            "name": child["name"],
            "has_doc": len(child.get("files", [])) > 0,
        }
        for child in node.get("children", [])
    ]

    topic_name = topic_path.rsplit("/", 1)[-1] if "/" in topic_path else topic_path

    return {
        "type": "topic",
        "module": module_name,
        "topic": topic_name,
        "topic_path": topic_path,
        "preview_text": preview_text,
        "outline": outline,
        "sub_topics": sub_topics,
        "references": references,
        "source_path": source_path,
    }


# ── Private helpers ─────────────────────────────────────────────────


def _find_group(resolved: dict, module_name: str) -> dict | None:
    """Find a module group by name in the resolved smart folder."""
    for g in resolved.get("groups", []):
        if g["module"] == module_name:
            return g
    return None


def _find_first_doc(node: dict, max_depth: int) -> dict | None:
    """Walk tree to find the first file (README) at or below this node.

    Handles multi-level intermediates:
        core → services → audit → README.md  (depth 2)

    Args:
        node: Tree node with ``children`` and ``files``.
        max_depth: Maximum levels to recurse (3 recommended).

    Returns:
        File dict ``{name, source_path, ...}`` or ``None``.
    """
    if max_depth < 0:
        return None
    # This node's own files
    if node.get("files"):
        return node["files"][0]
    # Recurse into children
    for child in node.get("children", []):
        found = _find_first_doc(child, max_depth - 1)
        if found:
            return found
    return None


def _find_topic_node(tree: dict, topic_path: str) -> dict | None:
    """Navigate to a specific node in the tree by slash-separated path.

    Example: ``topic_path="services/audit"`` navigates
    tree → children["services"] → children["audit"].
    """
    parts = [p for p in topic_path.split("/") if p]
    node = tree
    for part in parts:
        children = node.get("children", [])
        match = next((c for c in children if c["name"] == part), None)
        if match is None:
            return None
        node = match
    return node


def _flatten_outline(
    items: list[dict],
    max_items: int,
    result: list[dict] | None = None,
) -> list[dict]:
    """Flatten a nested outline tree into a list of ``{text, level}`` dicts.

    The outline API returns headings nested via ``children``:
        [{text: "H1", level: 1, children: [{text: "H2", level: 2, ...}]}]

    This walks depth-first and collects up to ``max_items`` entries.
    """
    if result is None:
        result = []
    for item in items:
        if len(result) >= max_items:
            break
        text = item.get("text", "")
        if text:
            result.append({"text": text, "level": item.get("level", 1), "line": item.get("line", 0)})
        children = item.get("children", [])
        if children:
            _flatten_outline(children, max_items, result)
    return result


def _get_flat_outline(
    file_path: Path,
    content: str,
    max_items: int,
) -> list[dict]:
    """Extract outline from a file and return flattened heading list."""
    try:
        from src.core.services.content.outline import extract_outline
        result = extract_outline(file_path, content=content)
        raw_outline = result.get("outline", [])
        return _flatten_outline(raw_outline, max_items)
    except Exception as exc:
        logger.warning("Outline extraction failed for %s: %s", file_path, exc)
        return []


def _extract_text(markdown: str, max_chars: int) -> str:
    """Strip markdown syntax to produce a plain-text excerpt.

    Removes code fences, inline code, heading markers, images, links,
    bold/italic, horizontal rules, and HTML tags.  Collapses whitespace
    and truncates at word boundary.
    """
    text = markdown
    # Code fences
    text = re.sub(r"```[\s\S]*?```", "", text)
    # Inline code
    text = re.sub(r"`[^`]+`", "", text)
    # Heading markers
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # Images
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    # Links — keep text
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    # Bold/italic markers
    text = re.sub(r"[*_]{1,3}([^*_]+)[*_]{1,3}", r"\1", text)
    # Horizontal rules
    text = re.sub(r"^[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)
    # HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    # Blockquote markers
    text = re.sub(r"^>\s*", "", text, flags=re.MULTILINE)
    # List markers
    text = re.sub(r"^[\s]*[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[\s]*\d+\.\s+", "", text, flags=re.MULTILINE)
    # Collapse whitespace
    text = text.strip()
    text = re.sub(r"\s+", " ", text)

    if len(text) > max_chars:
        # Truncate at last word boundary
        text = text[:max_chars]
        last_space = text.rfind(" ")
        if last_space > max_chars * 0.6:
            text = text[:last_space]
        text += "…"

    return text


def _build_doc_tree_summary(children: list[dict]) -> list[dict]:
    """Build a compact tree summary for the peek response.

    Returns a simplified tree where each node has:
        name, has_doc, source_path (if has_doc), children (recursive)
    """
    result = []
    for child in children:
        files = child.get("files", [])
        has_doc = len(files) > 0
        entry: dict[str, Any] = {
            "name": child["name"],
            "has_doc": has_doc,
        }
        if has_doc:
            entry["source_path"] = files[0]["source_path"]
        sub_children = child.get("children", [])
        if sub_children:
            entry["children"] = _build_doc_tree_summary(sub_children)
        else:
            entry["children"] = []
        result.append(entry)
    return result


def _count_topics(node: dict) -> int:
    """Count total topic nodes (children with files) in the tree."""
    count = 0
    for child in node.get("children", []):
        if child.get("files"):
            count += 1
        count += _count_topics(child)
    return count


def _tree_depth(node: dict, current: int = 0) -> int:
    """Calculate maximum depth of the tree."""
    children = node.get("children", [])
    if not children:
        return current
    return max(_tree_depth(c, current + 1) for c in children)


def _get_references(
    project_root: Path,
    doc_path: str,
    content: str,
) -> list[dict]:
    """Get cross-references from a document using the peek service.

    Returns a simplified list of resolved references.
    Falls back to empty list on any error.
    """
    try:
        from src.core.services.peek import scan_and_resolve_all, build_symbol_index
        sym_idx = build_symbol_index(project_root, block=False) or None
        refs, _unresolved, _pending = scan_and_resolve_all(
            content, doc_path, project_root, sym_idx,
        )
        return [
            {
                "text": r.text,
                "type": r.type,
                "resolved_path": r.resolved_path,
            }
            for r in refs[:10]  # cap at 10 for peek
        ]
    except Exception as exc:
        logger.warning("Peek refs failed for %s: %s", doc_path, exc)
        return []
