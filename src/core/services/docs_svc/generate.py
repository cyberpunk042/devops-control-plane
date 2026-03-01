"""
Documentation generation — changelog and README templates.

Extracted from docs_ops.py. Channel-independent.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


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
