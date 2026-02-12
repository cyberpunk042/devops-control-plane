"""
Documentation operations — channel-independent service.

Analyzes project documentation health: README presence per module,
API spec detection, documentation file inventory, link validation,
and changelog generation from git log.

Complements existing:
- pages_engine.py (builds and deploys doc sites)
- md_transforms.py (markdown transformations)
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
#  Detect: Documentation inventory
# ═══════════════════════════════════════════════════════════════════


_DOC_EXTENSIONS = frozenset({
    ".md", ".rst", ".txt", ".adoc", ".asciidoc", ".textile",
})

_DOC_DIRS = frozenset({
    "docs", "doc", "documentation", "wiki",
})

_API_SPEC_FILES = [
    ("openapi.yaml", "OpenAPI", "openapi"),
    ("openapi.yml", "OpenAPI", "openapi"),
    ("openapi.json", "OpenAPI", "openapi"),
    ("swagger.yaml", "Swagger", "openapi"),
    ("swagger.yml", "Swagger", "openapi"),
    ("swagger.json", "Swagger", "openapi"),
    ("api.yaml", "API Spec", "openapi"),
    ("api.yml", "API Spec", "openapi"),
    ("schema.graphql", "GraphQL", "graphql"),
    ("schema.gql", "GraphQL", "graphql"),
    ("*.graphql", "GraphQL", "graphql"),
    ("*.proto", "Protocol Buffers", "protobuf"),
    ("asyncapi.yaml", "AsyncAPI", "asyncapi"),
    ("asyncapi.yml", "AsyncAPI", "asyncapi"),
]

_SKIP_DIRS = frozenset({
    ".git", ".venv", "venv", "node_modules", "__pycache__",
    ".mypy_cache", ".ruff_cache", ".pytest_cache", ".tox",
    "dist", "build", ".eggs", ".terraform", ".pages",
    "htmlcov", ".backup", "state", ".pages",
})


def docs_status(project_root: Path) -> dict:
    """Comprehensive documentation status.

    Returns:
        {
            "readme": {exists, path, size, headings},
            "doc_dirs": [{name, file_count, total_size}, ...],
            "doc_files": int,
            "api_specs": [{file, type, format}, ...],
            "changelog": {exists, path},
            "license": {exists, path},
            "contributing": {exists, path},
        }
    """
    result: dict[str, Any] = {}

    # README
    readme = _find_readme(project_root)
    if readme:
        headings = _extract_headings(readme)
        result["readme"] = {
            "exists": True,
            "path": str(readme.relative_to(project_root)),
            "size": readme.stat().st_size,
            "lines": len(readme.read_text(encoding="utf-8", errors="ignore").splitlines()),
            "headings": headings[:10],
        }
    else:
        result["readme"] = {"exists": False}

    # Doc directories
    doc_dirs: list[dict] = []
    for dir_name in _DOC_DIRS:
        dir_path = project_root / dir_name
        if dir_path.is_dir():
            files = list(f for f in dir_path.rglob("*") if f.is_file())
            doc_files = [f for f in files if f.suffix.lower() in _DOC_EXTENSIONS]
            total_size = sum(f.stat().st_size for f in files)
            doc_dirs.append({
                "name": dir_name,
                "file_count": len(files),
                "doc_count": len(doc_files),
                "total_size": total_size,
            })
    result["doc_dirs"] = doc_dirs

    # Total doc files at root level
    root_docs = [
        f for f in project_root.iterdir()
        if f.is_file() and f.suffix.lower() in _DOC_EXTENSIONS
    ]
    result["root_doc_files"] = len(root_docs)

    # API specs
    result["api_specs"] = _detect_api_specs(project_root)

    # Key documentation files
    for name, patterns in [
        ("changelog", ["CHANGELOG.md", "CHANGELOG", "CHANGES.md", "HISTORY.md"]),
        ("license", ["LICENSE", "LICENSE.md", "LICENSE.txt", "LICENCE"]),
        ("contributing", ["CONTRIBUTING.md", "CONTRIBUTING", "CONTRIBUTE.md"]),
        ("code_of_conduct", ["CODE_OF_CONDUCT.md"]),
        ("security_policy", ["SECURITY.md"]),
    ]:
        found = None
        for pattern in patterns:
            path = project_root / pattern
            if path.is_file():
                found = str(path.relative_to(project_root))
                break
        result[name] = {"exists": found is not None, "path": found}

    return result


def _find_readme(project_root: Path) -> Path | None:
    """Find README file (case-insensitive)."""
    for name in ("README.md", "README.rst", "README.txt", "README", "readme.md"):
        path = project_root / name
        if path.is_file():
            return path
    return None


def _extract_headings(path: Path) -> list[dict]:
    """Extract markdown headings from a file."""
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []

    headings: list[dict] = []
    for line in content.splitlines():
        match = re.match(r"^(#{1,6})\s+(.+)$", line.strip())
        if match:
            headings.append({
                "level": len(match.group(1)),
                "text": match.group(2).strip(),
            })
    return headings


def _detect_api_specs(project_root: Path) -> list[dict]:
    """Detect API specification files."""
    found: list[dict] = []

    for filename, spec_type, spec_format in _API_SPEC_FILES:
        if "*" in filename:
            # Glob pattern
            for match in project_root.rglob(filename):
                rel = str(match.relative_to(project_root))
                skip = False
                for part in match.relative_to(project_root).parts:
                    if part in _SKIP_DIRS:
                        skip = True
                        break
                if not skip:
                    found.append({
                        "file": rel,
                        "type": spec_type,
                        "format": spec_format,
                    })
        else:
            path = project_root / filename
            if path.is_file():
                found.append({
                    "file": filename,
                    "type": spec_type,
                    "format": spec_format,
                })

    return found


# ═══════════════════════════════════════════════════════════════════
#  Observe: Per-module documentation coverage
# ═══════════════════════════════════════════════════════════════════


def docs_coverage(project_root: Path) -> dict:
    """Check documentation coverage per detected module.

    Returns:
        {
            "modules": [{
                name, path, has_readme, readme_path,
                doc_files, has_api_spec
            }, ...],
            "coverage": float (0-1),
            "total": int,
            "documented": int,
        }
    """
    modules: list[dict] = []

    try:
        from src.core.config.loader import load_project
        from src.core.config.stack_loader import discover_stacks
        from src.core.services.detection import detect_modules

        project = load_project(project_root / "project.yml")
        stacks = discover_stacks(project_root / "stacks")
        detection = detect_modules(project, project_root, stacks)

        for module in detection.modules:
            mod_path = project_root / module.path if module.path != "." else project_root
            has_readme = _find_readme(mod_path) is not None

            # Count doc files in module directory
            doc_count = 0
            if mod_path.is_dir():
                for f in mod_path.rglob("*"):
                    if f.is_file() and f.suffix.lower() in _DOC_EXTENSIONS:
                        skip = False
                        for part in f.relative_to(mod_path).parts:
                            if part in _SKIP_DIRS:
                                skip = True
                                break
                        if not skip:
                            doc_count += 1

            modules.append({
                "name": module.name,
                "path": module.path,
                "stack": module.effective_stack,
                "has_readme": has_readme,
                "doc_files": doc_count,
            })

    except Exception as e:
        logger.debug("Module detection failed: %s", e)
        # Fallback: check root only
        has_readme = _find_readme(project_root) is not None
        modules.append({
            "name": project_root.name,
            "path": ".",
            "stack": None,
            "has_readme": has_readme,
            "doc_files": 0,
        })

    documented = sum(1 for m in modules if m["has_readme"])
    total = len(modules)
    coverage = documented / total if total > 0 else 0

    return {
        "modules": modules,
        "coverage": round(coverage, 2),
        "total": total,
        "documented": documented,
    }


# ═══════════════════════════════════════════════════════════════════
#  Observe: Link validation
# ═══════════════════════════════════════════════════════════════════


_LINK_PATTERN = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
_HEADING_ANCHOR_PATTERN = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)


def check_links(project_root: Path, *, file_path: str | None = None) -> dict:
    """Check for broken internal links in markdown files.

    Only checks internal links (relative paths and anchors).
    Does NOT check external URLs (no network requests).

    Returns:
        {
            "files_checked": int,
            "total_links": int,
            "broken": [{file, line, link, reason}, ...],
            "ok": bool,
        }
    """
    broken: list[dict] = []
    total_links = 0
    files_checked = 0

    if file_path:
        target = project_root / file_path
        if target.is_file():
            files = [target]
        else:
            return {"files_checked": 0, "total_links": 0, "broken": [], "ok": True}
    else:
        files = _collect_md_files(project_root)

    for md_file in files:
        try:
            content = md_file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        files_checked += 1

        # Collect anchors defined in this file
        defined_anchors = set()
        for heading_match in _HEADING_ANCHOR_PATTERN.finditer(content):
            text = heading_match.group(1).strip()
            anchor = _heading_to_anchor(text)
            defined_anchors.add(anchor)

        for line_num, line in enumerate(content.splitlines(), 1):
            for match in _LINK_PATTERN.finditer(line):
                link_text = match.group(1)
                link_target = match.group(2)
                total_links += 1

                # Skip external URLs
                if link_target.startswith(("http://", "https://", "mailto:", "ftp://")):
                    continue

                # Skip image data URIs
                if link_target.startswith("data:"):
                    continue

                rel_path = str(md_file.relative_to(project_root))

                # Anchor-only link (#heading)
                if link_target.startswith("#"):
                    anchor = link_target[1:]
                    if anchor not in defined_anchors:
                        broken.append({
                            "file": rel_path,
                            "line": line_num,
                            "link": link_target,
                            "text": link_text,
                            "reason": f"Anchor not found in file",
                        })
                    continue

                # Relative file link
                # Split off anchor if present
                file_part = link_target.split("#")[0]
                if not file_part:
                    continue  # Pure anchor, already handled

                target_path = md_file.parent / file_part
                if not target_path.exists():
                    broken.append({
                        "file": rel_path,
                        "line": line_num,
                        "link": link_target,
                        "text": link_text,
                        "reason": f"File not found: {file_part}",
                    })

    return {
        "files_checked": files_checked,
        "total_links": total_links,
        "broken": broken,
        "broken_count": len(broken),
        "ok": len(broken) == 0,
    }


def _heading_to_anchor(text: str) -> str:
    """Convert heading text to GitHub-style anchor."""
    anchor = text.lower()
    anchor = re.sub(r"[^\w\s-]", "", anchor)
    anchor = re.sub(r"\s+", "-", anchor)
    return anchor.strip("-")


def _collect_md_files(project_root: Path) -> list[Path]:
    """Collect all markdown files, respecting skip dirs."""
    files: list[Path] = []
    for f in project_root.rglob("*.md"):
        skip = False
        for part in f.relative_to(project_root).parts:
            if part in _SKIP_DIRS:
                skip = True
                break
        if not skip:
            files.append(f)
    return files[:100]  # Cap at 100


# ═══════════════════════════════════════════════════════════════════
#  Facilitate: Changelog generation
# ═══════════════════════════════════════════════════════════════════


def generate_changelog(
    project_root: Path,
    *,
    max_commits: int = 50,
    since: str | None = None,
) -> dict:
    """Generate a changelog from git commit history.

    Returns:
        {
            "ok": True,
            "file": {path, content, reason, overwrite},
            "commits": int,
        }
    """
    from src.core.models.template import GeneratedFile

    cmd = ["git", "log", f"--max-count={max_commits}", "--format=%H|%ai|%s|%an"]
    if since:
        cmd.append(f"--since={since}")

    try:
        result = subprocess.run(
            cmd,
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return {"error": f"Git unavailable: {e}"}

    if result.returncode != 0:
        return {"error": f"Git log failed: {result.stderr.strip()}"}

    lines = [
        "# Changelog",
        "",
        f"> Generated from git history ({max_commits} most recent commits)",
        "",
    ]

    current_date = ""
    commit_count = 0

    for raw in result.stdout.strip().splitlines():
        parts = raw.split("|", 3)
        if len(parts) < 4:
            continue

        commit_hash, date_str, subject, author = parts
        short_hash = commit_hash[:7]
        date_only = date_str.split(" ")[0]  # YYYY-MM-DD

        commit_count += 1

        if date_only != current_date:
            current_date = date_only
            lines.append(f"## {date_only}")
            lines.append("")

        # Categorize by conventional commit prefix
        icon = _commit_icon(subject)
        lines.append(f"- {icon} {subject} (`{short_hash}` by {author})")

    lines.append("")

    content = "\n".join(lines)

    file_data = GeneratedFile(
        path="CHANGELOG.md",
        content=content,
        overwrite=True,
        reason=f"Generated changelog from {commit_count} commits",
    )

    return {
        "ok": True,
        "file": file_data.model_dump(),
        "commits": commit_count,
    }


def _commit_icon(subject: str) -> str:
    """Return emoji for conventional commit type."""
    lower = subject.lower()
    if lower.startswith("feat"):
        return "✨"
    elif lower.startswith("fix"):
        return "🐛"
    elif lower.startswith("docs"):
        return "📝"
    elif lower.startswith("style"):
        return "💅"
    elif lower.startswith("refactor"):
        return "♻️"
    elif lower.startswith("test"):
        return "🧪"
    elif lower.startswith("chore"):
        return "🔧"
    elif lower.startswith("ci"):
        return "⚙️"
    elif lower.startswith("perf"):
        return "⚡"
    elif lower.startswith("build"):
        return "📦"
    elif "merge" in lower:
        return "🔀"
    return "📋"


# ═══════════════════════════════════════════════════════════════════
#  Facilitate: README template generation
# ═══════════════════════════════════════════════════════════════════


def generate_readme(project_root: Path) -> dict:
    """Generate a README.md template from project metadata.

    Returns:
        {"ok": True, "file": {path, content, reason, overwrite}}
    """
    from src.core.models.template import GeneratedFile

    name = project_root.name
    stacks: list[str] = []
    modules: list[dict] = []

    try:
        from src.core.config.loader import load_project
        from src.core.config.stack_loader import discover_stacks
        from src.core.services.detection import detect_modules

        project = load_project(project_root / "project.yml")
        name = project.name
        all_stacks = discover_stacks(project_root / "stacks")
        detection = detect_modules(project, project_root, all_stacks)
        stacks = list({m.effective_stack for m in detection.modules if m.effective_stack})
        modules = [
            {"name": m.name, "path": m.path, "stack": m.effective_stack}
            for m in detection.modules
        ]
    except Exception:
        pass

    lines = [
        f"# {name}",
        "",
        "> TODO: Add a description of your project here.",
        "",
    ]

    # Badges placeholder
    lines.extend([
        "<!-- Badges -->",
        "<!-- ![CI](https://github.com/OWNER/REPO/actions/workflows/ci.yml/badge.svg) -->",
        "",
    ])

    # Table of contents
    lines.extend([
        "## Table of Contents",
        "",
        "- [Overview](#overview)",
        "- [Getting Started](#getting-started)",
        "- [Project Structure](#project-structure)",
        "- [Development](#development)",
        "- [Contributing](#contributing)",
        "- [License](#license)",
        "",
    ])

    # Overview
    lines.extend([
        "## Overview",
        "",
        "> TODO: Describe what this project does and why it exists.",
        "",
    ])

    # Getting started
    lines.extend([
        "## Getting Started",
        "",
        "### Prerequisites",
        "",
    ])

    if any("python" in s for s in stacks):
        lines.append("- Python 3.12+")
    if any("node" in s or "typescript" in s for s in stacks):
        lines.append("- Node.js 18+")
    if any("go" in s for s in stacks):
        lines.append("- Go 1.21+")
    if any("rust" in s for s in stacks):
        lines.append("- Rust (stable)")

    lines.extend([
        "",
        "### Installation",
        "",
        "```bash",
        f"git clone <repo-url>",
        f"cd {project_root.name}",
    ])

    if any("python" in s for s in stacks):
        lines.extend([
            "python -m venv .venv",
            "source .venv/bin/activate",
            "pip install -e '.[dev]'",
        ])
    elif any("node" in s or "typescript" in s for s in stacks):
        lines.append("npm install")

    lines.extend(["```", ""])

    # Project structure
    if modules:
        lines.extend([
            "## Project Structure",
            "",
            "| Module | Path | Stack |",
            "|--------|------|-------|",
        ])
        for m in modules:
            lines.append(f"| {m['name']} | `{m['path']}` | {m['stack'] or 'N/A'} |")
        lines.append("")

    # Development
    lines.extend([
        "## Development",
        "",
        "```bash",
        "# Run tests",
    ])
    if any("python" in s for s in stacks):
        lines.append("pytest")
    elif any("node" in s or "typescript" in s for s in stacks):
        lines.append("npm test")
    lines.extend([
        "",
        "# Lint",
    ])
    if any("python" in s for s in stacks):
        lines.append("ruff check .")
    elif any("node" in s or "typescript" in s for s in stacks):
        lines.append("npx eslint .")
    lines.extend(["```", ""])

    # Contributing + License
    lines.extend([
        "## Contributing",
        "",
        "> TODO: Add contribution guidelines.",
        "",
        "## License",
        "",
        "> TODO: Specify your license.",
        "",
    ])

    content = "\n".join(lines)

    file_data = GeneratedFile(
        path="README.md",
        content=content,
        overwrite=False,
        reason="Generated README template from project metadata",
    )

    return {"ok": True, "file": file_data.model_dump()}
