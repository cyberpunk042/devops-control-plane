"""
.dockerignore generator — produce a .dockerignore from detected stacks.

Combines a base set of common exclusions with stack-specific patterns.
"""

from __future__ import annotations

from pathlib import Path

from src.core.models.template import GeneratedFile


_BASE_IGNORE = """\
# ── Version control ─────────────────────────────────────────────
.git
.gitignore

# ── IDE / Editor ────────────────────────────────────────────────
.vscode
.idea
*.swp
*.swo
*~

# ── OS files ────────────────────────────────────────────────────
.DS_Store
Thumbs.db

# ── Docker ──────────────────────────────────────────────────────
docker-compose*.yml
Dockerfile*
.dockerignore

# ── CI/CD ───────────────────────────────────────────────────────
.github
.gitlab-ci.yml
Jenkinsfile

# ── Documentation ───────────────────────────────────────────────
docs/
*.md
LICENSE
"""

_STACK_PATTERNS: dict[str, str] = {
    "python": """\
# ── Python ──────────────────────────────────────────────────────
__pycache__
*.pyc
*.pyo
.pytest_cache
.mypy_cache
.ruff_cache
.venv
venv
env
*.egg-info
dist
build
.tox
.coverage
htmlcov
""",
    "node": """\
# ── Node.js ─────────────────────────────────────────────────────
node_modules
npm-debug.log*
yarn-debug.log*
yarn-error.log*
.npm
.yarn
dist
coverage
""",
    "typescript": """\
# ── TypeScript / Node ───────────────────────────────────────────
node_modules
npm-debug.log*
dist
coverage
*.js.map
tsconfig.tsbuildinfo
""",
    "go": """\
# ── Go ──────────────────────────────────────────────────────────
vendor/
*.test
*.out
""",
    "rust": """\
# ── Rust ────────────────────────────────────────────────────────
target/
Cargo.lock
""",
    "java": """\
# ── Java ────────────────────────────────────────────────────────
target/
build/
*.class
*.jar
*.war
.gradle
""",
    "dotnet": """\
# ── .NET ────────────────────────────────────────────────────────
bin/
obj/
*.user
*.suo
""",
    "elixir": """\
# ── Elixir ──────────────────────────────────────────────────────
_build/
deps/
*.ez
""",
    "ruby": """\
# ── Ruby ────────────────────────────────────────────────────────
.bundle
vendor/bundle
log/
tmp/
""",
}


def generate_dockerignore(
    project_root: Path,
    stack_names: list[str],
) -> GeneratedFile:
    """Generate a .dockerignore combining base patterns with stack-specific ones.

    Args:
        project_root: Project root (unused but kept for consistency).
        stack_names: List of detected stack names in the project.

    Returns:
        GeneratedFile for .dockerignore.
    """
    parts = [_BASE_IGNORE.rstrip()]

    # Deduplicate: resolve stack prefixes
    added: set[str] = set()
    for name in stack_names:
        # Exact match
        if name in _STACK_PATTERNS and name not in added:
            parts.append(_STACK_PATTERNS[name].rstrip())
            added.add(name)
            continue

        # Prefix match (e.g. python-flask → python)
        for prefix in _STACK_PATTERNS:
            if name.startswith(prefix + "-") and prefix not in added:
                parts.append(_STACK_PATTERNS[prefix].rstrip())
                added.add(prefix)
                break

    content = "\n\n".join(parts) + "\n"

    return GeneratedFile(
        path=".dockerignore",
        content=content,
        overwrite=False,
        reason=f"Generated .dockerignore for stacks: {', '.join(stack_names)}",
    )
