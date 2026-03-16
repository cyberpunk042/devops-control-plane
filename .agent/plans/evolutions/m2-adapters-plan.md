# M2 Adapters Plan — Ecosystem Implementations

> Status: COMPLETE — all 9 adapters implemented and verified
> Parent: [m2-foundation-plan.md](m2-foundation-plan.md)
> Last updated: 2026-03-16

---

## Overview

Each adapter is **one file implementing `EcosystemAdapter`** + **one file
extending `BaseOutputParser`**. Zero changes to scanner, pipeline, tree
builder, or routes when adding a new ecosystem.

4 phases, ordered by real-world frequency and this project's own needs:

| Phase | Ecosystems | Why this order |
|-------|-----------|---------------|
| **Phase 1** | pip (Python) | This project uses Python. Testable immediately. Most complex manifest parsing (5 file types). |
| **Phase 2** | npm (Node) | This project has Node (`package.json` in `.pages/`). Second most common ecosystem globally. |
| **Phase 3** | go, cargo | Strong ecosystems with good structured output. Go has `go list -json`, Cargo has `--message-format=json`. |
| **Phase 4** | bundler, maven, gradle, mix, dotnet | Long tail. Simpler manifests (Gemfile, pom.xml) or niche. Generic parser fallback covers them until specialized. |

After Phase 2, the system handles the two ecosystems this project actually
uses. Phases 3-4 extend coverage for managed projects.

---

## Phase 1 — pip (Python)

### Files
- `adapters/pip_adapter.py`
- `parsers/pip_parser.py`
- Update `__init__.py` → `_register_adapters()` adds `PipAdapter`

### PipAdapter complexity

pip is the most complex adapter because Python has 5 manifest formats:

| File | Format | Parse method | Deps location |
|------|--------|-------------|---------------|
| `requirements.txt` | Line-based | `pkg==ver`, `pkg>=ver`, `-r other.txt` (recursive), `-e .` (editable), comments, env markers | Each line is a dep |
| `pyproject.toml` | TOML | `[project.dependencies]` list, `[project.optional-dependencies]` groups | Standard PEP 621 |
| `setup.py` | Python AST | `install_requires=[]` in `setup()` call | AST extraction or regex |
| `setup.cfg` | INI | `[options] install_requires` | ConfigParser |
| `Pipfile` | TOML | `[packages]`, `[dev-packages]` | Direct key-value |

**Decision needed:** Do we parse all 5 or start with the 2-3 most common?
- `requirements.txt` + `pyproject.toml` cover ~90% of real projects
- `Pipfile` is a third common one
- `setup.py` / `setup.cfg` are legacy — lower priority

### PipAdapter methods

```
detect()           → Check for all 5 file patterns, stat() for mtime
is_available()     → sys.executable -m pip --version (special — not shutil.which)
parse_manifest()   → Dispatch by file: .txt → line parser, .toml → tomllib, .cfg → configparser
install_cmd()      → pip install -r requirements.txt (or pip install -e . for pyproject.toml)
update_cmd()       → pip install --upgrade -r requirements.txt (or specific packages)
update_single_cmd()→ pip install --upgrade <pkg>
snapshot_files()   → requirements.txt + any lock file present
restore_cmd()      → pip install -r requirements.txt
create_output_parser() → PipParser(scope)
fetch_latest_version()  → pip index versions <pkg> --format=json (pip 22.3+) or PyPI JSON API
check_deprecated()      → PyPI JSON API → info.classifiers contains "Development Status :: 7 - Inactive"
```

### PipParser patterns

| Pattern | Event type | Regex |
|---------|-----------|-------|
| `Successfully installed flask-3.0.1 requests-2.31.0` | `package_resolved` × N | `Successfully installed (.+)` → split by space, each `name-version` |
| `Requirement already satisfied: flask>=3.0 in ...` | `package_resolved` (action=satisfied) | `Requirement already satisfied: (\S+)` |
| `Collecting requests==2.31.0` | `progress` | `Collecting (\S+)` |
| `Downloading requests-2.31.0.tar.gz (100 kB)` | `progress` | `Downloading (.+)` |
| `DEPRECATION: ...` | `warning` (category=deprecated) | `^DEPRECATION:` |
| `WARNING: ...` | `warning` (category=generic) | `^WARNING:` |
| `ERROR: No matching distribution found for X` | `error` (category=missing_dep) | `ERROR: No matching distribution` |
| `ERROR: Could not find a version that satisfies X` | `error` (category=conflict) | `ERROR: Could not find a version` |
| `error: subprocess-exited-with-error` | `error` (category=build_error) | `subprocess-exited-with-error` |
| `ERROR: pip's dependency resolver does not currently take into account...` | `warning` (category=conflict) | `dependency resolver` |

### Lock file handling

pip doesn't have a single lock format. Snapshot strategy:
- If `requirements.txt` has pinned versions (`==`) → it IS the lock
- If `Pipfile.lock` exists → snapshot both `Pipfile` + `Pipfile.lock`
- If `poetry.lock` exists → snapshot `pyproject.toml` + `poetry.lock`
- If `pdm.lock` exists → snapshot `pyproject.toml` + `pdm.lock`

### Version intelligence

- `pip index versions <pkg>` — available since pip 21.2, returns all versions
- Fallback: PyPI JSON API `https://pypi.org/pypi/<pkg>/json` → `info.version` (latest), `releases` dict
- Deprecation: `info.classifiers` contains `"Development Status :: 7 - Inactive"` or `info.yanked`

---

## Phase 2 — npm (Node)

### Files
- `adapters/npm_adapter.py`
- `parsers/npm_parser.py`
- Update `__init__.py` → adds `NpmAdapter`

### NpmAdapter — simpler than pip

Only one manifest format: `package.json` (JSON).

| Aspect | Detail |
|--------|--------|
| **detect()** | Check `package.json` exists, check lock files (`package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`) |
| **parse_manifest()** | JSON → `dependencies`, `devDependencies`, `peerDependencies`, `optionalDependencies` |
| **install_cmd()** | `npm ci` (frozen, lock present) or `npm install` (no lock) |
| **update_cmd()** | `npm update` (all) or `npm update <pkg>` |
| **snapshot_files()** | `package.json` + `package-lock.json` (or `yarn.lock`) |
| **restore_cmd()** | `npm ci` |
| **is_available()** | `shutil.which("npm")` (default) |
| **fetch_latest_version()** | `npm view <pkg> version` (latest) or npm registry JSON |
| **check_deprecated()** | `npm view <pkg> deprecated` — returns deprecation message or empty |

### NpmParser patterns

npm output is less structured than pip — many patterns:

| Pattern | Event type | Detail |
|---------|-----------|--------|
| `added N packages in Xs` | `package_resolved` (batch) | Final summary — parse N |
| `npm WARN deprecated <pkg>@<ver>: <msg>` | `warning` (deprecated) | Package + message |
| `npm WARN <pkg> requires a peer of <dep>@<ver>` | `warning` (peer_dep) | Peer dependency conflict |
| `npm WARN optional SKIPPING OPTIONAL DEPENDENCY: <pkg>` | `warning` (optional_skip) | Non-fatal |
| `npm ERR! code ERESOLVE` | `error` (conflict) | Version resolution failure |
| `npm ERR! code ENOENT` | `error` (missing_dep) | File not found |
| `npm ERR! ...` | `error` (generic) | Any `npm ERR!` line |

**Note:** `npm install --verbose` gives per-package lines but changes output
format. Default (non-verbose) gives summary only. We may want `--loglevel verbose`
for the parser to have per-package data.

### Lock file handling

- `package-lock.json` → `npm ci` for restore
- `yarn.lock` → detect yarn, use `yarn install --frozen-lockfile`
- `pnpm-lock.yaml` → detect pnpm, use `pnpm install --frozen-lockfile`

**Decision needed:** Do we detect yarn/pnpm as sub-variants of the npm adapter,
or as separate adapters? I lean toward **one adapter with sub-variant detection**
since the manifest is always `package.json`, just the lock and CLI differ.

---

## Phase 3 — go + cargo

### Go

**Files:** `adapters/go_adapter.py`, `parsers/go_parser.py`

| Aspect | Detail |
|--------|--------|
| **detect()** | `go.mod` exists |
| **parse_manifest()** | Line-based: `require ( ... )` block. Each line: `module/path v1.2.3` |
| **install_cmd()** | `go mod download` |
| **update_cmd()** | `go get -u ./...` (all) or `go get -u <module>` |
| **snapshot_files()** | `go.mod` + `go.sum` |
| **restore_cmd()** | `go mod download` |
| **fetch_latest_version()** | `go list -m -versions <module>` → last version |
| **check_deprecated()** | `retract` directive in go.mod (limited) |

**GoParser:** Go output is clean — `go: downloading X v1.2.3` per module.
Errors: `go: X: not found`, checksum mismatch. Relatively simple parser.

### Cargo

**Files:** `adapters/cargo_adapter.py`, `parsers/cargo_parser.py`

| Aspect | Detail |
|--------|--------|
| **detect()** | `Cargo.toml` exists |
| **parse_manifest()** | TOML → `[dependencies]`, `[dev-dependencies]`, `[build-dependencies]` |
| **install_cmd()** | `cargo fetch` |
| **update_cmd()** | `cargo update` (all) or `cargo update -p <crate>` |
| **snapshot_files()** | `Cargo.toml` + `Cargo.lock` |
| **restore_cmd()** | `cargo fetch` |
| **fetch_latest_version()** | `cargo search <crate>` or crates.io API |
| **check_deprecated()** | crates.io API → `yanked` flag |

**CargoParser:** Cargo writes progress to **stderr** (compilation lines).
Key patterns: `Downloading X v1.2.3`, `Compiling X v1.2.3`, `warning:`,
`error[E...]`. The `merge_stderr=True` default in our subprocess handles this.

**Cargo bonus:** `cargo build --message-format=json` gives structured JSON
per event. We could parse this instead of regex — but only for build, not
for `cargo fetch`/`cargo update`.

---

## Phase 4 — bundler, maven, gradle, mix, dotnet

These are lower priority. Each gets an adapter + parser, but the parsers
can start with `GenericParser` (base class fallback) and get specialized
patterns later as users exercise them.

### Bundler (Ruby)

| Aspect | Detail |
|--------|--------|
| **detect()** | `Gemfile` |
| **parse_manifest()** | Line-based: `gem 'name', '~> ver'` |
| **commands** | `bundle install`, `bundle update`, `bundle update <gem>` |
| **snapshot** | `Gemfile` + `Gemfile.lock` |
| **parser** | `Installing X 1.2.3`, `Using X 1.2.3`, `Fetching X 1.2.3` |

### Maven (Java)

| Aspect | Detail |
|--------|--------|
| **detect()** | `pom.xml` |
| **parse_manifest()** | XML → `<dependencies><dependency>` elements |
| **commands** | `mvn dependency:resolve -q`, update = manual POM edit |
| **snapshot** | `pom.xml` only (no lock file) |
| **parser** | Maven output is verbose XML/log — generic fallback initially |

### Gradle (Java)

| Aspect | Detail |
|--------|--------|
| **detect()** | `build.gradle` or `build.gradle.kts` |
| **parse_manifest()** | Groovy/Kotlin DSL — regex for `implementation 'group:artifact:version'` |
| **commands** | `gradle dependencies --no-daemon -q` |
| **snapshot** | `build.gradle` + `gradle.lockfile` |
| **parser** | Gradle output is tree-formatted — generic fallback initially |

### Mix (Elixir)

| Aspect | Detail |
|--------|--------|
| **detect()** | `mix.exs` |
| **parse_manifest()** | Regex in Elixir source: `{:dep, "~> ver"}` |
| **commands** | `mix deps.get`, `mix deps.update --all`, `mix deps.update <dep>` |
| **snapshot** | `mix.exs` + `mix.lock` |
| **parser** | `* Getting X (Hex package)` — simple line patterns |

### .NET (NuGet)

| Aspect | Detail |
|--------|--------|
| **detect()** | `*.csproj`, `*.fsproj` (glob) |
| **parse_manifest()** | XML → `<PackageReference Include="X" Version="Y" />` |
| **commands** | `dotnet restore` |
| **snapshot** | `.csproj` + `packages.lock.json` |
| **parser** | `Restored X in Yms` — generic fallback initially |

---

## Implementation checklist per adapter

Every adapter follows the same steps:

```
1. Read the manifest format spec / examples
2. Write the adapter file implementing all EcosystemAdapter methods
3. Write the parser file extending BaseOutputParser._match_line()
4. Add one line to _register_adapters() in __init__.py
5. Test: detect → parse → tree shows packages → install stream works
```

---

## Shared concerns across all adapters

### TOML parsing (pip pyproject.toml, cargo Cargo.toml, pipfile)
Python 3.11+ has `tomllib`. For 3.8 compat, use `tomli` (pure Python
backport) with try/except fallback:
```python
try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib
```

### XML parsing (maven pom.xml, dotnet csproj)
Standard library `xml.etree.ElementTree`. No external dep needed.

### Version spec normalization
Each ecosystem has its own version constraint syntax:
- pip: `==`, `>=`, `~=`, `!=`, `<`, `>`
- npm: `^`, `~`, `>=`, `<`, `||`, `-`
- cargo: `=`, `>=`, `~`, `*`, `^`
- go: just the version string (implicit `>=`)

We store `version_spec` as the raw string from the manifest.
`pinned_version` is resolved from the lock file if available.
No normalization across ecosystems — each adapter owns its format.

### `sys.executable` for pip
pip must use `sys.executable -m pip` (not bare `pip`) to ensure it runs
in the correct venv. The adapter overrides `is_available()` for this.
All pip commands use `[sys.executable, "-m", "pip", ...]`.

---

## Files created per phase

| Phase | New files | Modified |
|-------|-----------|----------|
| **1 (pip)** | `adapters/pip_adapter.py`, `parsers/pip_parser.py` | `__init__.py` (+1 line) |
| **2 (npm)** | `adapters/npm_adapter.py`, `parsers/npm_parser.py` | `__init__.py` (+1 line) |
| **3 (go+cargo)** | 4 files | `__init__.py` (+2 lines) |
| **4 (5 ecosystems)** | 10 files | `__init__.py` (+5 lines) |

**Total: 16 new files, 4 single-line modifications to `__init__.py`.**

---

## Verification per phase

| Phase | Test |
|-------|------|
| **1** | Run scanner on this project → detects `pyproject.toml`. Tree shows Python ecosystem with parsed deps. Install stream runs `pip install` with live output. Parser detects `Successfully installed`. |
| **2** | Scanner detects `package.json` in `.pages/code-docs/` and `.pages/docs/`. Tree shows 2 Node ecosystems. Install stream runs `npm ci`. |
| **3** | Create test `go.mod` / `Cargo.toml` → scanner detects, tree shows, commands work. |
| **4** | Each adapter detects its manifest, parses deps, builds correct commands. Generic parser catches errors/warnings. |
