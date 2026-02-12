"""
GitHub Actions workflow generator.

Produces CI and lint workflows from detected stack information.
Templates follow GitHub Actions best practices:
- Pinned action versions
- Dependency caching
- Matrix testing where appropriate
- Minimal permissions
"""

from __future__ import annotations

from pathlib import Path

from src.core.models.template import GeneratedFile


def _python_ci_job(version_matrix: list[str] | None = None) -> str:
    """Python CI job: install, lint, type-check, test."""
    versions = version_matrix or ["3.11", "3.12"]
    matrix_str = ", ".join(f'"{v}"' for v in versions)
    return f"""\
  python:
    name: Python — lint, types, test
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: [{matrix_str}]

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python ${{{{ matrix.python-version }}}}
        uses: actions/setup-python@v5
        with:
          python-version: ${{{{ matrix.python-version }}}}
          cache: pip

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -e ".[dev]" 2>/dev/null || pip install -e .
          pip install ruff mypy pytest 2>/dev/null || true

      - name: Lint (ruff)
        run: ruff check .

      - name: Type check (mypy)
        run: mypy src/ --ignore-missing-imports

      - name: Test (pytest)
        run: pytest --tb=short -q
"""


def _node_ci_job(version_matrix: list[str] | None = None) -> str:
    """Node.js CI job: install, lint, test, build."""
    versions = version_matrix or ["18", "20"]
    matrix_str = ", ".join(f'"{v}"' for v in versions)
    return f"""\
  node:
    name: Node.js — lint, test, build
    runs-on: ubuntu-latest
    strategy:
      matrix:
        node-version: [{matrix_str}]

    steps:
      - uses: actions/checkout@v4

      - name: Set up Node.js ${{{{ matrix.node-version }}}}
        uses: actions/setup-node@v4
        with:
          node-version: ${{{{ matrix.node-version }}}}
          cache: npm

      - name: Install dependencies
        run: npm ci

      - name: Lint
        run: npm run lint --if-present

      - name: Test
        run: npm test --if-present

      - name: Build
        run: npm run build --if-present
"""


def _go_ci_job(version_matrix: list[str] | None = None) -> str:
    """Go CI job: vet, lint, test, build."""
    versions = version_matrix or ["1.21", "1.22"]
    matrix_str = ", ".join(f'"{v}"' for v in versions)
    return f"""\
  go:
    name: Go — vet, test, build
    runs-on: ubuntu-latest
    strategy:
      matrix:
        go-version: [{matrix_str}]

    steps:
      - uses: actions/checkout@v4

      - name: Set up Go ${{{{ matrix.go-version }}}}
        uses: actions/setup-go@v5
        with:
          go-version: ${{{{ matrix.go-version }}}}

      - name: Vet
        run: go vet ./...

      - name: Test
        run: go test -race -count=1 ./...

      - name: Build
        run: go build ./...
"""


def _rust_ci_job() -> str:
    """Rust CI job: check, clippy, test."""
    return """\
  rust:
    name: Rust — clippy, test
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Install Rust
        uses: dtolnay/rust-toolchain@stable
        with:
          components: clippy, rustfmt

      - name: Cache
        uses: actions/cache@v4
        with:
          path: |
            ~/.cargo/registry
            ~/.cargo/git
            target
          key: ${{ runner.os }}-cargo-${{ hashFiles('**/Cargo.lock') }}

      - name: Check
        run: cargo check

      - name: Clippy
        run: cargo clippy -- -D warnings

      - name: Format check
        run: cargo fmt -- --check

      - name: Test
        run: cargo test
"""


def _java_maven_ci_job() -> str:
    """Java Maven CI job."""
    return """\
  java:
    name: Java — build, test
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Set up JDK 21
        uses: actions/setup-java@v4
        with:
          java-version: '21'
          distribution: temurin
          cache: maven

      - name: Build and test
        run: mvn -B verify
"""


def _java_gradle_ci_job() -> str:
    """Java Gradle CI job."""
    return """\
  java:
    name: Java — build, test
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Set up JDK 21
        uses: actions/setup-java@v4
        with:
          java-version: '21'
          distribution: temurin
          cache: gradle

      - name: Build and test
        run: ./gradlew build
"""


# Map stack name → job generator
_CI_JOBS: dict[str, callable] = {
    "python": _python_ci_job,
    "node": _node_ci_job,
    "typescript": _node_ci_job,
    "go": _go_ci_job,
    "rust": _rust_ci_job,
    "java-maven": _java_maven_ci_job,
    "java-gradle": _java_gradle_ci_job,
}


def _resolve_job(stack_name: str) -> callable | None:
    """Resolve a stack to its CI job generator."""
    if stack_name in _CI_JOBS:
        return _CI_JOBS[stack_name]
    for prefix, gen in _CI_JOBS.items():
        if stack_name.startswith(prefix + "-") or stack_name.startswith(prefix):
            return gen
    return None


# ── Public API ──────────────────────────────────────────────────


def generate_ci(
    project_root: Path,
    stack_names: list[str],
    *,
    project_name: str = "",
) -> GeneratedFile | None:
    """Generate a comprehensive CI workflow for detected stacks.

    Args:
        project_root: Project root directory.
        stack_names: List of detected stack names.
        project_name: Optional project name for workflow naming.

    Returns:
        GeneratedFile or None if no stacks match.
    """
    job_blocks: list[str] = []
    seen_generators: set[int] = set()

    for name in stack_names:
        gen = _resolve_job(name)
        if gen and id(gen) not in seen_generators:
            job_blocks.append(gen())
            seen_generators.add(id(gen))

    if not job_blocks:
        return None

    wf_name = f"{project_name} CI" if project_name else "CI"

    header = f"""\
# Generated by DevOps Control Plane
name: {wf_name}

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  contents: read

jobs:
"""

    content = header + "\n".join(job_blocks)

    return GeneratedFile(
        path=".github/workflows/ci.yml",
        content=content,
        overwrite=False,
        reason=f"Generated CI workflow for stacks: {', '.join(stack_names)}",
    )


# ── Lint workflow ───────────────────────────────────────────────


def _python_lint_steps() -> str:
    return """\
      - name: Lint (ruff)
        run: ruff check .

      - name: Format check (ruff)
        run: ruff format --check .

      - name: Type check (mypy)
        run: mypy src/ --ignore-missing-imports
"""


def _node_lint_steps() -> str:
    return """\
      - name: Lint (eslint)
        run: npm run lint --if-present

      - name: Format check (prettier)
        run: npx prettier --check . 2>/dev/null || true
"""


_LINT_STEPS: dict[str, callable] = {
    "python": _python_lint_steps,
    "node": _node_lint_steps,
    "typescript": _node_lint_steps,
}


def generate_lint(
    project_root: Path,
    stack_names: list[str],
) -> GeneratedFile | None:
    """Generate a lightweight lint-only workflow.

    Returns:
        GeneratedFile or None.
    """
    setup_blocks: list[str] = []
    lint_blocks: list[str] = []

    for name in stack_names:
        # Resolve lint steps
        gen = _LINT_STEPS.get(name)
        if not gen:
            for prefix, g in _LINT_STEPS.items():
                if name.startswith(prefix):
                    gen = g
                    break

        if gen and gen not in [g for g in lint_blocks]:
            if name.startswith("python") or name == "python":
                setup_blocks.append("""\
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: pip

      - name: Install lint tools
        run: pip install ruff mypy
""")
            elif name.startswith("node") or name == "node" or name == "typescript":
                setup_blocks.append("""\
      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: npm

      - name: Install dependencies
        run: npm ci
""")
            lint_blocks.append(gen())

    if not lint_blocks:
        return None

    content = """\
# Generated by DevOps Control Plane
name: Lint

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  contents: read

jobs:
  lint:
    name: Lint
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

""" + "\n".join(setup_blocks) + "\n" + "\n".join(lint_blocks)

    return GeneratedFile(
        path=".github/workflows/lint.yml",
        content=content,
        overwrite=False,
        reason=f"Generated lint workflow for stacks: {', '.join(stack_names)}",
    )
