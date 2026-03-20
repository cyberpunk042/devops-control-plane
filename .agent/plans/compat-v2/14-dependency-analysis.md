# 14 — Dependency Analysis Spec

> **Document**: 14 of 37
> **Milestone**: M7 — Direction & constraint resolution
> **Status**: Draft

---

## 1. Purpose

Dependency analysis checks whether a module's EXTERNAL dependencies (packages from registries like PyPI, npm, crates.io) support the target language version. This is separate from code analysis (which looks at the module's own source code) and import chain resolution (which traces project-internal imports).

A module's code can be fully compatible with Python 3.8, but if one of its pip packages requires Python 3.9+, the module still can't run on 3.8.

---

## 2. What It Analyzes

### 2.1 Package manifests per language

| Language | Manifest file | Version constraint field |
|----------|--------------|------------------------|
| Python | `requirements.txt`, `pyproject.toml`, `setup.py`, `setup.cfg`, `Pipfile` | `requires-python` in package metadata |
| JavaScript | `package.json` | `engines.node` |
| TypeScript | `package.json` | `engines.node` |
| Go | `go.mod` | `go` directive |
| Rust | `Cargo.toml` | `rust-version` (MSRV) |
| Ruby | `Gemfile`, `*.gemspec` | `required_ruby_version` |
| Java | `pom.xml`, `build.gradle` | `<maven.compiler.source>`, `sourceCompatibility` |
| C# | `*.csproj` | `<TargetFramework>` |
| PHP | `composer.json` | `require.php` |
| Elixir | `mix.exs` | `elixir` in `project` |

### 2.2 Registry APIs

| Registry | API | What it returns |
|----------|-----|----------------|
| PyPI | `https://pypi.org/pypi/{package}/json` | `info.requires_python` per version |
| npm | `https://registry.npmjs.org/{package}` | `engines.node` per version |
| crates.io | `https://crates.io/api/v1/crates/{package}` | `rust_version` per version |
| RubyGems | `https://rubygems.org/api/v1/versions/{gem}.json` | `required_ruby_version` |
| Maven Central | `https://search.maven.org/solrsearch/select?q=g:{group}+a:{artifact}` | Compile target |
| NuGet | `https://api.nuget.org/v3-flatcontainer/{package}/index.json` | Target framework |
| Packagist | `https://repo.packagist.org/p2/{vendor}/{package}.json` | `require.php` |
| Hex | `https://hex.pm/api/packages/{package}` | `requirements` |

---

## 3. Analysis Flow

```python
class DependencyAnalyzer:
    """Analyze external dependency compatibility."""

    def __init__(self, backend_factory: Callable[[str], LanguageBackend]):
        self._backend_factory = backend_factory
        self._cache: dict[str, PackageInfo] = {}

    def analyze(
        self,
        module_dir: Path,
        language: str,
        target_version: str,
    ) -> DependencyAnalysisResult:
        """Analyze all dependencies for target version compatibility.

        1. Find and parse the manifest file(s)
        2. Extract dependency list with version constraints
        3. For each dependency:
           a. Query the package registry
           b. Get requires-python (or equivalent) for the installed version
           c. Check if target version satisfies the constraint
        4. Aggregate results
        """

    def check_package(
        self,
        package: str,
        installed_version: str | None,
        language: str,
        target_version: str,
    ) -> PackageCompatResult:
        """Check a single package's compatibility."""

    def find_compatible_version(
        self,
        package: str,
        language: str,
        target_version: str,
        max_results: int = 5,
    ) -> list[CompatibleVersion]:
        """Find versions of a package that support the target version.

        Searches from newest to oldest, returns up to max_results
        compatible versions.
        """
```

### 3.1 DependencyAnalysisResult

```python
@dataclass
class DependencyAnalysisResult:
    module_dir: str
    language: str
    target_version: str
    manifest_file: str              # Which file was parsed

    packages: list[PackageCompatResult]
    compatible_count: int
    incompatible_count: int
    unknown_count: int              # Packages where we couldn't determine compat
    dependency_floor: str           # Highest min version among all deps

    @property
    def all_compatible(self) -> bool:
        return self.incompatible_count == 0

    @property
    def incompatible_packages(self) -> list[PackageCompatResult]:
        return [p for p in self.packages if not p.compatible and not p.unknown]

@dataclass
class PackageCompatResult:
    package: str
    installed_version: str | None
    requires_python: str | None     # ">=3.8" or equivalent
    min_version: str | None         # Parsed minimum: "3.8"
    compatible: bool                # Does target satisfy requires-python?
    unknown: bool                   # Could not determine (no metadata)
    alternatives: list[CompatibleVersion]  # Other versions that support target

@dataclass
class CompatibleVersion:
    version: str                    # Package version: "1.10.0"
    requires_python: str            # ">=3.7"
    release_date: str | None        # When this version was published
```

---

## 4. Manifest Parsing

### 4.1 Python

**requirements.txt:**
```
flask>=2.0
pydantic>=2.0,<3.0
cryptography>=41.0
pyyaml>=6.0
```

Parse each line, extract package name and version constraint.

**pyproject.toml:**
```toml
[project]
dependencies = [
    "flask>=2.0",
    "pydantic>=2.0,<3.0",
]

[project.optional-dependencies]
dev = ["pytest>=7.0", "mypy>=1.0"]
```

Parse `[project].dependencies` and optionally `[project.optional-dependencies]`.

**setup.py / setup.cfg:**
```python
install_requires=[
    "flask>=2.0",
    "pydantic>=2.0",
]
```

Parse `install_requires` list.

### 4.2 JavaScript / TypeScript

**package.json:**
```json
{
  "dependencies": {
    "express": "^4.18.0",
    "lodash": "^4.17.0"
  },
  "devDependencies": {
    "jest": "^29.0.0",
    "typescript": "^5.0.0"
  }
}
```

### 4.3 Go

**go.mod:**
```
module github.com/user/project

go 1.21

require (
    github.com/gin-gonic/gin v1.9.1
    google.golang.org/grpc v1.58.0
)
```

The `go` directive itself is the version constraint. Dependencies are checked against their own `go.mod` `go` directive.

### 4.4 Rust

**Cargo.toml:**
```toml
[package]
rust-version = "1.70"

[dependencies]
serde = "1.0"
tokio = { version = "1.32", features = ["full"] }
```

`rust-version` is the MSRV. Dependencies declare their own MSRV in their Cargo.toml.

### 4.5 Other languages

Similar patterns — parse the manifest, extract dependencies, query registry.

---

## 5. Registry Querying

### 5.1 Caching

Registry queries are expensive (HTTP requests). Cache aggressively:

```python
class RegistryCache:
    """Cache package registry responses."""

    def __init__(self, ttl_seconds: int = 3600):
        self._cache: dict[str, CachedResponse] = {}
        self._ttl = ttl_seconds

    def get(self, cache_key: str) -> dict | None:
        """Get cached response if still valid."""

    def put(self, cache_key: str, response: dict) -> None:
        """Cache a response."""

    def invalidate(self, package: str) -> None:
        """Invalidate cache for a package."""
```

### 5.2 Rate limiting

Registries have rate limits. The analyzer must:
- Batch queries where possible
- Respect rate limit headers (`X-RateLimit-Remaining`)
- Back off on 429 responses
- Cache responses to minimize repeat queries

### 5.3 Offline mode

When registry is unreachable:
- Use cached responses if available
- Mark packages as `unknown` if no cache
- Warn the user that results may be incomplete

### 5.4 Query implementation per registry

```python
class PyPIQuerier:
    """Query PyPI for package version information."""

    def query(self, package: str) -> PackageInfo:
        """Query PyPI JSON API for package metadata.

        Returns:
            PackageInfo with requires_python for each version
        """
        resp = httpx.get(f"https://pypi.org/pypi/{package}/json", timeout=10)
        data = resp.json()

        return PackageInfo(
            package=package,
            latest_version=data["info"]["version"],
            requires_python=data["info"]["requires_python"],
            all_versions={
                ver: {
                    "requires_python": files[0].get("requires_python", "")
                    if files else ""
                }
                for ver, files in data["releases"].items()
                if files  # Skip yanked/empty releases
            },
        )
```

---

## 6. Compatibility Checking

### 6.1 Parsing requires-python

```python
def check_python_compat(requires_python: str, target: str) -> bool:
    """Check if target version satisfies requires-python constraint.

    Examples:
      requires_python=">=3.8"     target="3.8"  → True
      requires_python=">=3.9"     target="3.8"  → False
      requires_python=">=3.7,<4"  target="3.8"  → True
      requires_python="~=3.8"     target="3.8"  → True
      requires_python=""          target="3.8"  → True (no constraint = any version)
    """
```

Uses PEP 440 version specifiers for Python. Each language has its own constraint syntax:
- Python: PEP 440 (`>=3.8`, `~=3.8`, `>=3.7,<4`)
- Node.js: semver ranges (`>=18`, `^18.0.0`, `18.x`)
- Go: go directive (`go 1.21` means minimum 1.21)
- Rust: semver with MSRV
- Ruby: gem version constraints (`>= 2.7`, `~> 3.0`)

### 6.2 Version resolution for alternatives

When the installed version is incompatible, find alternatives:

```python
def find_alternatives(
    package_info: PackageInfo,
    target_version: str,
    max_results: int = 5,
) -> list[CompatibleVersion]:
    """Find package versions that support the target.

    Strategy:
    1. Sort all versions by release date (newest first)
    2. For each version, check requires-python against target
    3. Return first max_results compatible versions

    Prefers:
    - Newest compatible version (most features, most security fixes)
    - Same major version as currently installed (less breaking changes)
    """
```

---

## 7. Dependency Fix Actions

### 7.1 Downgrade package

When a package's current version doesn't support the target, but an older version does:

```
Package: pydantic
Installed: 2.5.0 (requires Python >=3.8)
Target: 3.7

Alternatives:
  pydantic 1.10.13 (requires Python >=3.7) ← compatible
  pydantic 1.10.12 (requires Python >=3.7) ← compatible

Action: Downgrade pydantic to 1.x
Warning: Major version change — API differences likely
```

### 7.2 Pin version

Lock to a specific compatible version:

```
Package: cryptography
Installed: 42.0.0 (requires Python >=3.7)
Target: 3.7

Action: Pin to cryptography==42.0.0 (already compatible)
```

### 7.3 Remove dependency

If the package has no compatible versions:

```
Package: some-new-package
Installed: 1.0.0 (requires Python >=3.12)
Target: 3.8

No compatible versions found.
Action: Remove dependency or find alternative package
```

### 7.4 Update requirements file

After resolving dependency conflicts, update the manifest:

```python
def update_requirements(
    module_dir: Path,
    changes: list[DependencyChange],
) -> list[str]:
    """Update the requirements file with version changes.

    Returns list of modified files.
    """
```

---

## 8. Dependency Tree Analysis

### 8.1 Transitive dependencies

A module's direct dependency might itself depend on packages that don't support the target:

```
Module depends on: flask>=2.0
flask depends on: werkzeug>=2.3
werkzeug 2.3+ requires Python >=3.8

If target is 3.7:
  flask 2.0 supports 3.7 ✅
  But werkzeug 2.3 does NOT ✅ (it does support 3.8, example adjusted)

  Actually, werkzeug 2.3 requires >=3.8, so if target is 3.7:
  flask 2.0 → werkzeug 2.3 → requires 3.8 → INCOMPATIBLE with 3.7 target
```

### 8.2 Depth of analysis

Full transitive dependency analysis is expensive. Options:
- **Depth 1** (direct only): Fast, covers most cases
- **Depth 2** (direct + their direct deps): Catches most transitive issues
- **Full tree**: Complete but slow — uses `pip install --dry-run` or equivalent

Default: depth 1 with option to go deeper.

### 8.3 Lock file analysis

Lock files (`requirements.lock`, `package-lock.json`, `Cargo.lock`, `Gemfile.lock`) contain the RESOLVED dependency tree. If available, use them for accurate transitive analysis:

```python
def analyze_lockfile(
    lockfile_path: Path,
    language: str,
    target_version: str,
) -> list[PackageCompatResult]:
    """Analyze all packages in a lock file."""
```

---

## 9. Integration Points

### 9.1 With Version Constraint Resolution (Document 13)
- Dependency floor feeds into effective floor calculation
- Incompatible packages are blockers in the assessment

### 9.2 With Feature Database (Document 02)
- Backport packages listed in feature entries (tomli, backports.strenum)
- When a fix adds a backport, dependency analyzer verifies it's available

### 9.3 With Lifecycle (Document 06)
- Dependency check is a step type
- Incompatible deps → NEEDS_ATTENTION with alternatives
- All compatible → PASSED

### 9.4 With Fix Engine (Document 05)
- When a fix adds a backport import, the dependency analyzer is consulted
- "You need to add `tomli` to requirements.txt"
- Can auto-add the dependency to the manifest

### 9.5 With Project-Wide Analysis (Document 08)
- Dependency analysis per module feeds into project report
- Shared dependencies across modules may have conflicting version needs
