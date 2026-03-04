"""
Smart Folder Documentation Enrichment.

Transforms a raw tree of copied README.md files into a properly structured
Docusaurus project with:
  - README.md → index.md rename
  - Title extraction from # headings
  - Source path frontmatter injection
  - _category_.json generation at every directory level
  - Auto-generated landing pages for empty directories
  - Module landing pages with section tables
  - Root landing page with module overview
  - Child section tables appended to parent pages
  - Non-README .md files handled with proper titles

Called from the Docusaurus builder's _stage_source, after smart folder
file copying and before _stage_transform.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# Module emoji mapping — matches the project's established conventions
MODULE_EMOJI: dict[str, str] = {
    "core": "⚙️",
    "adapters": "🔌",
    "cli": "🖥️",
    "web": "🌐",
    "docs": "📖",
}


def enrich(
    docs_dir: Path,
    resolved: dict,
    modules: list[dict],
    smart_folder: dict,
) -> list[str]:
    """Run all enrichment passes on staged smart folder docs.

    Order matters:
      1. Rename README.md → index.md
      2. Generate module landing pages (before general landings)
      3. Generate landing pages for non-module dirs without index
      4. Generate root landing page
      5. Append child section tables to pages with sub-dirs
      6. Extract titles & inject frontmatter (AFTER all content is final)
      7. Generate _category_.json (AFTER all index.md exist)
    """
    logs: list[str] = []
    groups = resolved.get("groups", [])

    # Build module metadata lookup
    mod_meta: dict[str, dict] = {}
    for mod in modules:
        mod_meta[mod["name"]] = mod
    for g in groups:
        if g["module"] not in mod_meta:
            mod_meta[g["module"]] = {
                "name": g["module"],
                "path": g.get("module_path", ""),
                "description": "",
            }

    # Build set of module names for quick lookup
    module_names = {g["module"] for g in groups}

    # ── Pass 1: Rename README.md → index.md ────────────────────────
    rename_count = _rename_readmes(docs_dir)
    if rename_count:
        logs.append(f"  ✎ Renamed {rename_count} README.md → index.md")

    # ── Pass 2: Module landing pages (before general landings) ─────
    mod_count = _enrich_module_landings(docs_dir, groups, mod_meta)
    logs.append(f"  ✎ Enriched {mod_count} module landing pages")

    # ── Pass 3: Landing pages for non-module dirs without index ────
    landing_count = _generate_landing_pages(docs_dir, groups, mod_meta, module_names)
    logs.append(f"  ✎ Generated {landing_count} landing pages")

    # ── Pass 4: Root landing page ──────────────────────────────────
    _generate_root_landing(docs_dir, resolved, groups, mod_meta, smart_folder)
    logs.append("  ✎ Generated root landing page")

    # ── Pass 5: Append child section tables ────────────────────────
    section_count = _append_section_tables(docs_dir)
    logs.append(f"  ✎ Appended section tables to {section_count} pages")

    # ── Pass 5.5: Inject :::audit-data directives ──────────────────
    # Appended to module landing pages so the build pipeline
    # can resolve them with pre-computed audit data.
    audit_count = _inject_audit_directives(docs_dir, groups)
    if audit_count:
        logs.append(f"  📊 Injected audit directives on {audit_count} module pages")

    # ── Pass 6: Extract titles & inject frontmatter ────────────────
    # Done AFTER all content generation so every file gets frontmatter
    fm_count = _inject_frontmatter(docs_dir, groups, mod_meta)
    logs.append(f"  ✎ Enriched frontmatter on {fm_count} files")

    # ── Pass 7: Generate _category_.json files ─────────────────────
    # Done LAST so all index.md files exist for correct link type
    cat_count = _generate_categories(docs_dir, groups, mod_meta)
    logs.append(f"  ✎ Generated {cat_count} _category_.json files")

    return logs


# ═══════════════════════════════════════════════════════════════════
# Pass 1: Rename README.md → index.md
# ═══════════════════════════════════════════════════════════════════


def _rename_readmes(docs_dir: Path) -> int:
    """Rename all README.md files to index.md for Docusaurus directory pages."""
    count = 0
    for readme in sorted(docs_dir.rglob("README.md")):
        index = readme.parent / "index.md"
        if not index.exists():
            readme.rename(index)
            count += 1
    return count


# ═══════════════════════════════════════════════════════════════════
# Pass 2: Module landing pages
# ═══════════════════════════════════════════════════════════════════


def _enrich_module_landings(
    docs_dir: Path,
    groups: list[dict],
    mod_meta: dict[str, dict],
) -> int:
    """Enrich or generate module-level landing pages."""
    count = 0

    for g in groups:
        mod_name = g["module"]
        mod_dir = docs_dir / mod_name
        if not mod_dir.is_dir():
            continue

        index = mod_dir / "index.md"
        mod = mod_meta.get(mod_name, {})
        mod_path = mod.get("path", mod_name)
        description = mod.get("description", "")
        emoji = MODULE_EMOJI.get(mod_name, "📦")
        file_count = g.get("file_count", 0)

        if index.exists():
            # index.md exists (from README.md rename).
            # Prepend a module context banner at the top of the content.
            content = index.read_text(encoding="utf-8")

            # Don't double-inject
            if "<!-- module-banner -->" not in content:
                banner = (
                    f"<!-- module-banner -->\n"
                    f"> {emoji} **{_name_to_title(mod_name)}** · "
                    f"`{mod_path}` · {file_count} documentation topics\n\n"
                )
                # Insert banner after the first heading
                heading_match = re.search(r"^#\s+.+$", content, re.MULTILINE)
                if heading_match:
                    insert_pos = heading_match.end()
                    content = content[:insert_pos] + "\n\n" + banner + content[insert_pos:]
                else:
                    content = banner + content
                index.write_text(content, encoding="utf-8")
        else:
            # No README at module root — generate full landing
            title = f"{_name_to_title(mod_name)}"

            children = _get_child_sections(mod_dir)
            table = _build_child_table(children)

            content = (
                f"# {emoji} {title}\n\n"
                f"<!-- module-banner -->\n"
                f"> Source: `{mod_path}` · {file_count} documentation topics\n\n"
            )

            if description:
                content += f"{description}\n\n"

            if table:
                content += f"## Sections\n\n{table}\n"

            index.write_text(content, encoding="utf-8")

        count += 1

    return count


# ═══════════════════════════════════════════════════════════════════
# Pass 3: Landing pages for directories without index.md
# ═══════════════════════════════════════════════════════════════════


def _generate_landing_pages(
    docs_dir: Path,
    groups: list[dict],
    mod_meta: dict[str, dict],
    module_names: set[str],
) -> int:
    """Generate index.md for directories that have children but no index.

    Skips module roots (handled by pass 2).
    """
    count = 0

    for directory in sorted(docs_dir.rglob("*")):
        if not directory.is_dir():
            continue
        if directory == docs_dir:
            continue

        # Skip module roots — handled by _enrich_module_landings
        try:
            rel = directory.relative_to(docs_dir)
        except ValueError:
            continue
        if len(rel.parts) == 1 and rel.parts[0] in module_names:
            continue

        index = directory / "index.md"
        if index.exists():
            continue

        # Only generate if the directory has documented children
        children = _get_child_sections(directory)
        if not children:
            continue

        title = _name_to_title(directory.name)
        source_path = _resolve_source_path(index, docs_dir, groups, mod_meta)
        table = _build_child_table(children)

        content = (
            f"# {title}\n\n"
            f"> Source: `{source_path}`\n\n"
        )

        if table:
            content += f"## Sections\n\n{table}\n"

        index.write_text(content, encoding="utf-8")
        count += 1

    return count


# ═══════════════════════════════════════════════════════════════════
# Pass 4: Root landing page
# ═══════════════════════════════════════════════════════════════════


def _generate_root_landing(
    docs_dir: Path,
    resolved: dict,
    groups: list[dict],
    mod_meta: dict[str, dict],
    smart_folder: dict,
) -> None:
    """Generate the root index.md with module overview."""
    index = docs_dir / "index.md"
    label = smart_folder.get("label", resolved.get("name", "Code Documentation"))
    total = resolved.get("total_files", 0)
    mod_count = len(groups)

    content = (
        f"# {label}\n\n"
        f"Auto-discovered documentation from the codebase.  \n"
        f"**{total} topics** across **{mod_count} module{'s' if mod_count != 1 else ''}**.\n\n"
        f"---\n\n"
        f"## Modules\n\n"
    )

    # Module table
    content += "| Module | Source | Topics | Description |\n"
    content += "|--------|--------|--------|-------------|\n"
    for g in groups:
        mod_name = g["module"]
        mod = mod_meta.get(mod_name, {})
        mod_path = mod.get("path", mod_name)
        description = mod.get("description", "")
        emoji = MODULE_EMOJI.get(mod_name, "📦")
        file_count = g.get("file_count", 0)

        content += (
            f"| [{emoji} **{_name_to_title(mod_name)}**](./{mod_name}/) "
            f"| `{mod_path}` "
            f"| {file_count} "
            f"| {description} |\n"
        )

    content += "\n---\n\n"

    # Module detail cards
    for g in groups:
        mod_name = g["module"]
        mod = mod_meta.get(mod_name, {})
        mod_path = mod.get("path", mod_name)
        emoji = MODULE_EMOJI.get(mod_name, "📦")
        file_count = g.get("file_count", 0)
        description = mod.get("description", "")

        content += f"### {emoji} {_name_to_title(mod_name)}\n\n"
        content += f"> `{mod_path}` — {file_count} topics\n\n"
        if description:
            content += f"{description}\n\n"

        # List top-level sections
        mod_dir = docs_dir / mod_name
        if mod_dir.is_dir():
            children = _get_child_sections(mod_dir)
            if children:
                for child_name, child_desc, child_count in children[:8]:
                    content += f"- [{_name_to_title(child_name)}](./{mod_name}/{child_name}/)"
                    if child_desc:
                        content += f" — {child_desc}"
                    content += "\n"
                remaining = len(children) - 8
                if remaining > 0:
                    content += f"- *...and {remaining} more*\n"
                content += "\n"

    index.write_text(content, encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════
# Pass 5: Append child section tables
# ═══════════════════════════════════════════════════════════════════


def _append_section_tables(docs_dir: Path) -> int:
    """Append sub-section navigation tables to pages with child directories."""
    count = 0

    for md_file in sorted(docs_dir.rglob("index.md")):
        directory = md_file.parent
        if directory == docs_dir:
            continue  # Root handled separately

        children = _get_child_sections(directory)
        if not children:
            continue

        content = md_file.read_text(encoding="utf-8")

        # Skip if already has a section table (from generated landings)
        if "<!-- section-table -->" in content:
            continue
        # Skip generated landings that already have a "## Sections" table
        if "## Sections\n" in content:
            continue

        # Build the table
        table_lines = [
            "\n\n---\n\n<!-- section-table -->\n",
            "## Sub-sections\n\n",
            "| Section | Topics | Description |\n",
            "|---------|--------|-------------|\n",
        ]
        for child_name, child_desc, child_count in children:
            title = _name_to_title(child_name)
            table_lines.append(
                f"| [{title}](./{child_name}/) | {child_count} | {child_desc} |\n"
            )

        content += "".join(table_lines)
        md_file.write_text(content, encoding="utf-8")
        count += 1

    return count


# ═══════════════════════════════════════════════════════════════════
# Pass 5.5: Inject :::audit-data directives into module pages
# ═══════════════════════════════════════════════════════════════════


def _inject_audit_directives(
    docs_dir: Path,
    groups: list[dict],
) -> int:
    """Append :::audit-data directives to module landing pages.

    Adds the directive to each module's index.md so the build pipeline
    can resolve it with pre-computed audit data. Uses an HTML comment
    marker to prevent double-injection on re-runs.
    """
    count = 0
    marker = "<!-- audit-data-directive -->"

    for g in groups:
        mod_name = g["module"]
        mod_dir = docs_dir / mod_name
        index = mod_dir / "index.md"

        if not index.is_file():
            continue

        content = index.read_text(encoding="utf-8")

        # Don't double-inject
        if marker in content:
            continue

        # Append the directive at the end of the file
        directive_block = (
            f"\n\n{marker}\n"
            f":::audit-data\n"
            f":::\n"
        )
        content = content.rstrip() + directive_block
        index.write_text(content, encoding="utf-8")
        count += 1

    return count


# ═══════════════════════════════════════════════════════════════════
# Pass 6: Extract titles & inject frontmatter
# ═══════════════════════════════════════════════════════════════════


def _inject_frontmatter(
    docs_dir: Path,
    groups: list[dict],
    mod_meta: dict[str, dict],
) -> int:
    """Extract title from # heading and inject frontmatter into all .md files."""
    count = 0
    for md_file in sorted(docs_dir.rglob("*.md")):
        content = md_file.read_text(encoding="utf-8")

        # Skip if already has frontmatter
        if content.startswith("---"):
            continue

        # Extract title from first # heading
        title = _extract_title(content)
        if not title:
            # Derive from directory or file name
            if md_file.name == "index.md":
                title = _name_to_title(md_file.parent.name)
            else:
                title = _name_to_title(md_file.stem)

        # Build sidebar label (shortened)
        sidebar_label = title
        if len(sidebar_label) > 30:
            sidebar_label = sidebar_label[:27] + "..."

        # Determine source path
        source_path = _resolve_source_path(md_file, docs_dir, groups, mod_meta)

        # Build frontmatter
        fm = (
            f"---\n"
            f"title: \"{_escape_yaml(title)}\"\n"
            f"sidebar_label: \"{_escape_yaml(sidebar_label)}\"\n"
            f"description: \"Source: {_escape_yaml(source_path)}\"\n"
            f"custom_edit_url: null\n"
            f"---\n\n"
        )

        md_file.write_text(fm + content, encoding="utf-8")
        count += 1

    return count


# ═══════════════════════════════════════════════════════════════════
# Pass 7: Generate _category_.json files
# ═══════════════════════════════════════════════════════════════════


def _generate_categories(
    docs_dir: Path,
    groups: list[dict],
    mod_meta: dict[str, dict],
) -> int:
    """Generate _category_.json for every directory in the docs tree."""
    count = 0
    position = 1

    for item in sorted(docs_dir.iterdir()):
        if not item.is_dir():
            continue
        count += _generate_category_recursive(item, docs_dir, mod_meta, position)
        position += 1

    return count


def _generate_category_recursive(
    directory: Path,
    docs_dir: Path,
    mod_meta: dict[str, dict],
    position: int,
) -> int:
    """Recursively generate _category_.json for a directory and its children."""
    count = 0
    cat_file = directory / "_category_.json"

    if not cat_file.exists():
        name = directory.name
        label = _name_to_title(name)

        # Check if this is a module root (1 level deep from docs_dir)
        try:
            rel = directory.relative_to(docs_dir)
        except ValueError:
            rel = Path(name)
        if len(rel.parts) == 1:
            emoji = MODULE_EMOJI.get(name, "📦")
            label = f"{emoji} {_name_to_title(name)}"

        has_index = (directory / "index.md").exists()

        cat_data: dict[str, Any] = {
            "label": label,
            "position": position,
        }

        if has_index:
            cat_data["link"] = {"type": "doc", "id": "index"}
        else:
            cat_data["link"] = {
                "type": "generated-index",
                "description": f"Documentation for {_name_to_title(name)}",
            }

        cat_file.write_text(
            json.dumps(cat_data, indent=2) + "\n",
            encoding="utf-8",
        )
        count += 1

    # Recurse into children
    child_pos = 1
    for child in sorted(directory.iterdir()):
        if child.is_dir() and child.name != "node_modules":
            count += _generate_category_recursive(child, docs_dir, mod_meta, child_pos)
            child_pos += 1

    return count


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════


def _extract_title(content: str) -> str:
    """Extract the first # heading from markdown content."""
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("# ") and not line.startswith("##"):
            # Strip emoji and bold markers for cleaner title
            title = line[2:].strip()
            # Remove leading emoji (common pattern)
            title = re.sub(r"^[^\w\s]+\s*", "", title).strip()
            return title if title else line[2:].strip()
    return ""


def _name_to_title(name: str) -> str:
    """Convert a directory/file name to a human-readable title."""
    return name.replace("_", " ").replace("-", " ").title()


def _escape_yaml(value: str) -> str:
    """Escape special characters for YAML string values."""
    return value.replace('"', '\\"')


def _resolve_source_path(
    md_file: Path,
    docs_dir: Path,
    groups: list[dict],
    mod_meta: dict[str, dict],
) -> str:
    """Resolve the real source path for a staged file."""
    try:
        rel = md_file.relative_to(docs_dir)
    except ValueError:
        return str(md_file)

    parts = rel.parts
    if not parts:
        return ""

    # First part is the module name
    mod_name = parts[0]
    mod = mod_meta.get(mod_name, {})
    mod_path = mod.get("path", mod_name)

    if len(parts) == 1:
        return f"{mod_path}/"
    else:
        sub = "/".join(parts[1:])
        if sub.endswith("/index.md"):
            sub = sub[:-9]
        elif sub == "index.md":
            sub = ""
        elif sub.endswith(".md"):
            sub = sub[:-3]
        return f"{mod_path}/{sub}/" if sub else f"{mod_path}/"


def _get_child_sections(directory: Path) -> list[tuple[str, str, int]]:
    """Get child directories that contain documentation.

    Returns:
        List of (name, description, doc_count) tuples, sorted by name.
    """
    children: list[tuple[str, str, int]] = []

    for child in sorted(directory.iterdir()):
        if not child.is_dir():
            continue
        if child.name.startswith(".") or child.name == "node_modules":
            continue

        # Count .md files recursively
        doc_count = sum(1 for _ in child.rglob("*.md"))
        if doc_count == 0:
            continue

        desc = _extract_description(child)
        children.append((child.name, desc, doc_count))

    return children


def _extract_description(directory: Path) -> str:
    """Extract the first meaningful paragraph from a directory's index.md."""
    index = directory / "index.md"
    if not index.exists():
        return ""

    content = index.read_text(encoding="utf-8")

    # Skip frontmatter
    if content.startswith("---"):
        try:
            end = content.index("---", 3)
            content = content[end + 3:]
        except ValueError:
            pass

    # Find first non-empty, non-heading, non-blockquote, non-code line
    in_code_fence = False
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_fence = not in_code_fence
            continue
        if in_code_fence:
            continue
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        if stripped.startswith(">"):
            continue
        if stripped.startswith("|"):
            continue
        if stripped.startswith("-") or stripped.startswith("*"):
            continue
        if stripped.startswith("<!--"):
            continue
        if stripped.startswith(":::"):
            continue
        # Found a content paragraph — take first sentence
        sentence = stripped.split(". ")[0]
        if len(sentence) > 80:
            sentence = sentence[:77] + "..."
        return sentence

    return ""


def _build_child_table(children: list[tuple[str, str, int]]) -> str:
    """Build a markdown table from child section data."""
    if not children:
        return ""

    lines = [
        "| Section | Topics | Description |\n",
        "|---------|--------|-------------|\n",
    ]
    for child_name, child_desc, child_count in children:
        title = _name_to_title(child_name)
        lines.append(
            f"| [{title}](./{child_name}/) | {child_count} | {child_desc} |\n"
        )
    return "".join(lines)
