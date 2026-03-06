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


def inject_crossref_links(
    content: str,
    refs: list[dict],
    docs_dir: Path,
    doc_rel: str,
) -> str:
    """Replace resolved file references with Docusaurus markdown links.

    For refs that resolve to files WITHIN the docs_dir, rewrite as relative
    markdown links so Docusaurus renders them as SPA navigation links.

    Refs that resolve OUTSIDE docs_dir are left as-is — the usePeekLinks.ts
    hook handles them at runtime.

    Args:
        content: MDX content (post-transform).
        refs: List of resolved reference dicts from peek scanning.
              Each has {text, resolved_path, is_directory, resolved}.
        docs_dir: Absolute path to the docs directory in workspace.
        doc_rel: Relative path of this document within docs_dir
                 (e.g. "core/services/audit/index.mdx").

    Returns:
        Content with internal references replaced by markdown links.
    """
    if not refs:
        return content

    # Build map: source_path → docs-relative mdx path
    # e.g. "src/core/services/audit/README.md" → "core/services/audit/index.mdx"
    internal_map: dict[str, str] = {}
    for ref in refs:
        if not ref.get("resolved") or ref.get("resolved") is False:
            continue
        resolved = ref.get("resolved_path", "")
        if not resolved:
            continue
        # Check if this resolved path has a corresponding .mdx in docs_dir
        # Smart folder staging copies files into docs_dir with structure:
        #   src/core/services/audit/README.md → docs/core/services/audit/index.mdx
        # We need to find if ANY file in docs_dir corresponds to this source path
        _find_internal_target(ref, docs_dir, internal_map)

    if not internal_map:
        return content

    # Now rewrite references in content
    # Process line by line, skip code fences and frontmatter
    lines = content.split("\n")
    result = []
    in_fence = False
    in_frontmatter = False
    frontmatter_count = 0

    for line in lines:
        stripped = line.lstrip()

        # Track frontmatter
        if stripped.startswith("---"):
            frontmatter_count += 1
            if frontmatter_count == 1:
                in_frontmatter = True
            elif frontmatter_count == 2:
                in_frontmatter = False
            result.append(line)
            continue

        if in_frontmatter:
            result.append(line)
            continue

        # Track fenced code blocks
        if stripped.startswith("```"):
            in_fence = not in_fence
            result.append(line)
            continue

        if in_fence:
            result.append(line)
            continue

        # Outside code: try to replace references with links
        # Process segments between backticks (inline code) separately
        parts = line.split("`")
        for i, part in enumerate(parts):
            if i % 2 == 0:  # Outside inline code — rewrite refs
                for ref_text, target_mdx in internal_map.items():
                    if ref_text not in part:
                        continue
                    # Don't replace if already inside a markdown link
                    # Check: is this ref_text preceded by [ and followed by ]
                    idx = part.find(ref_text)
                    while idx >= 0:
                        # Check if already linked: [ref_text](...)
                        before = part[:idx]
                        if before.endswith("["):
                            idx = part.find(ref_text, idx + len(ref_text))
                            continue
                        # Build relative link from this doc to target
                        doc_dir = str(Path(doc_rel).parent)
                        rel_link = _relative_link(doc_dir, target_mdx)
                        link = f"[`{ref_text}`]({rel_link})"
                        part = part[:idx] + link + part[idx + len(ref_text):]
                        # Move past the replacement to avoid re-matching
                        idx = part.find(ref_text, idx + len(link))
                parts[i] = part
            # Odd segments (inside backticks) are inline code — skip.
            # References inside `backticks` are handled by usePeekLinks.ts
            # at runtime, not rewritten as static links.

        result.append("`".join(parts))

    return "\n".join(result)


def _find_internal_target(
    ref: dict,
    docs_dir: Path,
    internal_map: dict[str, str],
) -> None:
    """Check if a resolved ref has a corresponding page in docs_dir.

    Populates internal_map with {ref_text: docs-relative-mdx-path}.
    """
    resolved = ref["resolved_path"]
    text = ref["text"]

    # The docs tree mirrors project structure but with README.md→index.md rename
    # and .md→.mdx extension change.
    # Try common mappings:

    # 1. Direct: resolved_path parts match docs_dir structure
    #    e.g. resolved="src/core/services/audit/README.md"
    #    docs might have: core/services/audit/index.mdx
    #    (the "src/" prefix is stripped, README→index, .md→.mdx)
    for prefix in ("src/", ""):
        if resolved.startswith(prefix):
            rel = resolved[len(prefix):]
        else:
            continue

        # README.md → index.mdx, other.md → other.mdx
        if rel.endswith("/README.md"):
            mdx_rel = rel[:-len("/README.md")] + "/index.mdx"
        elif rel.endswith(".md"):
            mdx_rel = rel[:-3] + ".mdx"
        else:
            # Non-markdown file — not a doc page
            continue

        target = docs_dir / mdx_rel
        if target.is_file():
            internal_map[text] = mdx_rel
            return

    # 2. Directory reference: check for index.mdx inside
    if ref.get("is_directory"):
        for prefix in ("src/", ""):
            if resolved.startswith(prefix):
                rel = resolved[len(prefix):]
            else:
                continue
            idx = docs_dir / rel / "index.mdx"
            if idx.is_file():
                internal_map[text] = f"{rel}/index.mdx"
                return


def _relative_link(from_dir: str, to_path: str) -> str:
    """Compute a relative path from one doc directory to another doc file.

    Args:
        from_dir: Directory of the source doc (e.g. "core/services/audit").
        to_path: Target doc path (e.g. "core/services/docker/index.mdx").

    Returns:
        Relative link (e.g. "../docker/index.mdx").
    """
    from_parts = Path(from_dir).parts if from_dir and from_dir != "." else ()
    to_parts = Path(to_path).parts

    # Find common prefix length
    common = 0
    for a, b in zip(from_parts, to_parts):
        if a == b:
            common += 1
        else:
            break

    # Go up from from_dir, then down to to_path
    ups = len(from_parts) - common
    downs = to_parts[common:]

    parts = [".."] * ups + list(downs)
    return "/".join(parts) if parts else to_path

