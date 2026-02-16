"""
Markdown transform utilities — optional pre-processing for builders.

These transforms handle common cross-builder compatibility:
  - Admonition syntax normalization
  - Frontmatter enrichment (add title from filename if missing)
  - Link rewriting (fix cross-segment references)

Each transform works on individual files and is builder-aware.
Transforms are opt-in — called by builders that need them.
"""

from __future__ import annotations

import re
from pathlib import Path


# ── Admonition Conversion ───────────────────────────────────────────

# Input format: GitHub/MyST-style admonitions
#   :::note
#   Content here
#   :::
#
# Docusaurus uses the same format natively.
# MkDocs with Material uses:
#   !!! note
#       Content here
# Hugo uses shortcodes:
#   {{< admonition note >}} Content {{< /admonition >}}
import logging

logger = logging.getLogger(__name__)


_ADMONITION_RE = re.compile(
    r"^(:::)\s*(note|tip|warning|danger|info|caution|important)[ \t]*(.*?)$"
    r"(.*?)"
    r"^:::\s*$",
    re.MULTILINE | re.DOTALL,
)

_MKDOCS_ADMONITION_RE = re.compile(
    r"^!!!\s*(note|tip|warning|danger|info|caution|important)(?:\s+\"(.*?)\")?\s*$"
    r"((?:\n    .*$|\n\s*$)+)",
    re.MULTILINE,
)


def admonitions_to_docusaurus(content: str) -> str:
    """Convert MkDocs-style admonitions to Docusaurus/GFM.

    !!! note "Title"
        Content

    becomes:

    :::note[Title]
    Content
    :::
    """
    def _replace(m: re.Match) -> str:
        kind = m.group(1)
        title = m.group(2) or ""
        body = m.group(3)
        # Dedent body (remove 4-space indent)
        lines = body.split("\n")
        dedented = "\n".join(
            line[4:] if line.startswith("    ") else line
            for line in lines
        ).strip()
        title_part = f"[{title}]" if title else ""
        return f":::{kind}{title_part}\n{dedented}\n:::"

    return _MKDOCS_ADMONITION_RE.sub(_replace, content)


def admonitions_to_mkdocs(content: str) -> str:
    """Convert GFM/Docusaurus-style admonitions to MkDocs.

    :::note
    Content
    :::

    becomes:

    !!! note
        Content
    """
    def _replace(m: re.Match) -> str:
        kind = m.group(2)
        title = m.group(3).strip()
        body = m.group(4).strip()
        # Indent body by 4 spaces
        indented = "\n".join(f"    {line}" for line in body.split("\n"))
        title_part = f' "{title}"' if title else ""
        return f"!!! {kind}{title_part}\n{indented}"

    return _ADMONITION_RE.sub(_replace, content)


# ── Frontmatter Enrichment ──────────────────────────────────────────

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def enrich_frontmatter(content: str, filepath: Path) -> str:
    """Add missing title from filename if frontmatter exists but has no title.

    If no frontmatter exists, add one with a title derived from the filename.
    """
    title = filepath.stem.replace("-", " ").replace("_", " ").title()

    m = _FRONTMATTER_RE.match(content)
    if m:
        fm = m.group(1)
        if "title:" not in fm:
            new_fm = f"title: \"{title}\"\n{fm}"
            return f"---\n{new_fm}\n---\n" + content[m.end():]
        return content  # Already has title

    # No frontmatter — add one
    return f"---\ntitle: \"{title}\"\n---\n\n{content}"


# ── Link Rewriting ──────────────────────────────────────────────────

_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")


def rewrite_links(
    content: str,
    segment_path: str,
    base_url: str = "",
) -> str:
    """Rewrite relative links to work within a segment's URL path.

    Only rewrites:
    - Links starting with ./ or without / (relative)
    - NOT external URLs (http://, https://)
    - NOT anchor links (#)
    """
    segment_prefix = f"{base_url.rstrip('/')}/{segment_path.strip('/')}/"

    def _replace(m: re.Match) -> str:
        text = m.group(1)
        url = m.group(2)

        # Skip external, anchor, and absolute links
        if url.startswith(("http://", "https://", "#", "/")):
            return m.group(0)

        # Remove ./ prefix
        clean = url.lstrip("./")
        return f"[{text}]({segment_prefix}{clean})"

    return _MD_LINK_RE.sub(_replace, content)


# ── Batch Transform ─────────────────────────────────────────────────


def transform_directory(
    source_dir: Path,
    target_dir: Path,
    target_format: str = "docusaurus",
    segment_path: str = "/",
    base_url: str = "",
) -> list[str]:
    """Transform all .md files from source to target directory.

    Args:
        source_dir: Input directory with Markdown files.
        target_dir: Output directory for transformed files.
        target_format: "docusaurus" or "mkdocs".
        segment_path: URL path prefix for link rewriting.
        base_url: Base URL for link rewriting.

    Returns:
        List of transformed file paths (relative).
    """
    import shutil

    target_dir.mkdir(parents=True, exist_ok=True)
    transformed = []

    for src_file in source_dir.rglob("*"):
        rel = src_file.relative_to(source_dir)
        dst_file = target_dir / rel

        if src_file.is_dir():
            dst_file.mkdir(parents=True, exist_ok=True)
            continue

        if src_file.suffix.lower() in (".md", ".mdx"):
            content = src_file.read_text(encoding="utf-8")

            # Apply transforms
            content = enrich_frontmatter(content, src_file)

            if target_format == "docusaurus":
                content = admonitions_to_docusaurus(content)
            elif target_format == "mkdocs":
                content = admonitions_to_mkdocs(content)

            content = rewrite_links(content, segment_path, base_url)

            dst_file.parent.mkdir(parents=True, exist_ok=True)
            dst_file.write_text(content, encoding="utf-8")
            transformed.append(str(rel))
        else:
            # Copy non-markdown files as-is
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src_file), str(dst_file))

    return transformed
