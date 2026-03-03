"""
CI job YAML generators — per-language test/build job blocks.

Each function returns a YAML string fragment for a GitHub Actions job.
The ``_CI_JOBS`` registry maps stack names to their generators, and
``_resolve_job`` does prefix-matching for derived stack names
(e.g. "python-flask" → python CI job).
"""

from __future__ import annotations


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
