"""
Docusaurus MDX transform helpers — stateless text processors.

Converts Markdown content to Docusaurus-compatible MDX:
  - MkDocs admonitions → Docusaurus ::: syntax
  - Frontmatter enrichment (title, sidebar_position)
  - Link rewriting (.md → .mdx)
  - JSX angle/brace escaping
"""

from __future__ import annotations

import re
from pathlib import Path


def convert_admonitions(content: str) -> str:
    """Convert MkDocs-style admonitions to Docusaurus format.

    MkDocs:
        !!! note "Title"
            Content here

    Docusaurus:
        :::note[Title]
        Content here
        :::
    """
    pattern = re.compile(
        r"^!!!\s*(note|tip|warning|danger|info|caution|important)"
        r"(?:\s+\"(.*?)\")?\s*$"
        r"((?:\n(?:    .*|[ \t]*)$)+)",
        re.MULTILINE,
    )

    def _replace(m: re.Match) -> str:
        kind = m.group(1)
        title = m.group(2) or ""
        body = m.group(3)
        lines = body.split("\n")
        dedented = "\n".join(
            line[4:] if line.startswith("    ") else line
            for line in lines
        ).strip()
        title_part = f"[{title}]" if title else ""
        return f":::{kind}{title_part}\n{dedented}\n:::"

    return pattern.sub(_replace, content)


def enrich_frontmatter(content: str, filepath: Path) -> str:
    """Ensure frontmatter has title and sidebar_position for Docusaurus.

    If no frontmatter exists, creates one.
    Adds sidebar_position from filename if numeric prefix.
    """
    title = filepath.stem
    # Strip numeric prefix (01-getting-started → getting-started)
    clean_title = re.sub(r"^\d+[-_]", "", title)
    human_title = clean_title.replace("-", " ").replace("_", " ").title()

    # Extract sidebar position from numeric prefix
    pos_match = re.match(r"^(\d+)[-_]", title)
    sidebar_pos = int(pos_match.group(1)) if pos_match else None

    fm_re = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
    m = fm_re.match(content)

    if m:
        fm = m.group(1)
        additions = []
        if "title:" not in fm:
            additions.append(f'title: "{human_title}"')
        if sidebar_pos is not None and "sidebar_position:" not in fm:
            additions.append(f"sidebar_position: {sidebar_pos}")
        if not additions:
            return content
        new_fm = "\n".join(additions) + "\n" + fm
        return f"---\n{new_fm}\n---\n" + content[m.end():]

    # No frontmatter — create one
    fm_lines = [f'title: "{human_title}"']
    if sidebar_pos is not None:
        fm_lines.append(f"sidebar_position: {sidebar_pos}")
    fm_block = "\n".join(fm_lines)
    return f"---\n{fm_block}\n---\n\n{content}"


def rewrite_links(content: str, segment_path: str, base_url: str) -> str:
    """Rewrite .md links to .mdx for Docusaurus internal linking."""
    def _replace(m: re.Match) -> str:
        text = m.group(1)
        url = m.group(2)
        if url.startswith(("http://", "https://", "#", "/")):
            return m.group(0)
        if url.endswith(".md"):
            url = url[:-3] + ".mdx"
        return f"[{text}]({url})"

    return re.compile(r"\[([^\]]*)\]\(([^)]+)\)").sub(_replace, content)


def escape_jsx_angles(content: str) -> str:
    """Escape bare `<`, `{`, `}` that MDX would misinterpret as JSX.

    MDX parses `<` as the start of a JSX element and `{`/`}` as
    expression boundaries. Documentation prose containing patterns
    like `<2s`, `{name}`, or Python dict literals will fail MDX
    compilation. This escapes them while preserving:
    - Valid HTML tags: `<div>`, `</div>`, `<br/>`
    - HTML comments: `<!-- ... -->`
    - Content inside fenced code blocks (``` ... ```)
    - Content inside inline code (`...`)
    """
    lines = content.split("\n")
    result = []
    in_fence = False

    for line in lines:
        # Track fenced code blocks
        stripped = line.lstrip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            result.append(line)
            continue

        if in_fence:
            result.append(line)
            continue

        # Escape bare { and } BEFORE backtick splitting.
        # MDX treats { } as JSX expression boundaries. In table cells,
        # | inside inline code can break the backtick span, exposing
        # braces to the parser. \{ renders as { in both prose and
        # inline code, so escaping everywhere is safe.
        line = line.replace("{", "\\{").replace("}", "\\}")

        # Outside code fences: escape < that aren't valid HTML/JSX tags
        # We process segments outside of inline code spans
        parts = line.split("`")
        for i, part in enumerate(parts):
            if i % 2 == 0:  # Outside inline code
                # Escape < followed by non-letter, non-/, non-!
                part = re.sub(
                    r"<(?![a-zA-Z/!])",
                    "&lt;",
                    part,
                )
            parts[i] = part
        result.append("`".join(parts))

    return "\n".join(result)
