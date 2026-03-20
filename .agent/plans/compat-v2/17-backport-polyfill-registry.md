# 17 — Backport & Polyfill Registry

> **Document**: 17 of 37
> **Milestone**: M8 — Fix system
> **Status**: Draft

---

## 1. Purpose

When downgrading, some features can't be replicated with pure code rewrites — they need a BACKPORT PACKAGE. The backport registry is a curated database of known backport/polyfill packages for each language feature.

When a fix strategy is `add_backport_import`, the engine needs to know:
- Which backport package to use
- What to import from it
- What minimum version is needed
- Whether it's maintained / trustworthy
- How to install it

---

## 2. Registry Schema

```yaml
backports:
  - feature_id: python.stdlib.tomllib
    language: python
    backport_package: tomli
    min_version: "1.0.0"
    max_version: null              # No upper bound
    import_name: tomli
    import_as: tomllib             # import tomli as tomllib
    install_command: "pip install tomli>=1.0.0"
    pypi_url: "https://pypi.org/project/tomli/"
    maintained: true
    notes: "Official backport by the stdlib author"
    supports_versions: ">=3.7"     # What Python versions the backport supports

  - feature_id: python.stdlib.strenum
    language: python
    backport_package: backports.strenum
    min_version: "1.0.0"
    import_name: backports.strenum
    import_as: null
    import_statement: "from backports.strenum import StrEnum"
    install_command: "pip install backports.strenum"
    maintained: true
    notes: "Backport of enum.StrEnum for Python < 3.11"
    supports_versions: ">=3.8"

  - feature_id: python.stdlib.exceptiongroup
    language: python
    backport_package: exceptiongroup
    min_version: "1.0.0"
    import_name: exceptiongroup
    import_statement: "from exceptiongroup import ExceptionGroup, BaseExceptionGroup"
    install_command: "pip install exceptiongroup"
    maintained: true
    notes: "Backport of ExceptionGroup for Python < 3.11"
    supports_versions: ">=3.7"

  - feature_id: python.typing.typing_extensions
    language: python
    backport_package: typing-extensions
    min_version: "4.0.0"
    import_name: typing_extensions
    install_command: "pip install typing-extensions>=4.0.0"
    maintained: true
    notes: "Backport of typing features for older Python. Covers ParamSpec, TypeGuard, etc."
    supports_versions: ">=3.7"
    provides_features:
      - "typing.ParamSpec"          # 3.10+
      - "typing.TypeGuard"         # 3.10+
      - "typing.TypeAlias"         # 3.10+
      - "typing.Self"              # 3.11+
      - "typing.Never"             # 3.11+
      - "typing.TypeVarTuple"      # 3.11+
      - "typing.override"          # 3.12+
```

### 2.1 JavaScript/TypeScript polyfills

```yaml
backports:
  - feature_id: javascript.es2020.optional_chaining
    language: javascript
    backport_package: "@babel/plugin-transform-optional-chaining"
    type: babel_plugin
    install_command: "npm install --save-dev @babel/plugin-transform-optional-chaining"
    notes: "Babel plugin — transforms ?. at build time"
    alternative: "core-js (runtime polyfill)"

  - feature_id: javascript.es2022.array_at
    language: javascript
    backport_package: core-js
    type: runtime_polyfill
    import_statement: "import 'core-js/actual/array/at'"
    install_command: "npm install core-js"
    notes: "Runtime polyfill — adds Array.prototype.at"

  - feature_id: javascript.es2022.structuredClone
    language: javascript
    backport_package: "@ungap/structured-clone"
    type: runtime_polyfill
    import_statement: "import structuredClone from '@ungap/structured-clone'"
    install_command: "npm install @ungap/structured-clone"
```

### 2.2 Go backports

Go has fewer backport packages — the ecosystem prefers copying code:

```yaml
backports:
  - feature_id: go.1_21.slices
    language: go
    backport_package: "golang.org/x/exp/slices"
    install_command: "go get golang.org/x/exp/slices"
    notes: "Experimental package — precursor to stdlib slices. API mostly compatible."
    supports_versions: ">=1.18"

  - feature_id: go.1_21.maps
    language: go
    backport_package: "golang.org/x/exp/maps"
    install_command: "go get golang.org/x/exp/maps"
    notes: "Experimental package — precursor to stdlib maps."
    supports_versions: ">=1.18"

  - feature_id: go.1_21.slog
    language: go
    backport_package: "golang.org/x/exp/slog"
    install_command: "go get golang.org/x/exp/slog"
    notes: "Experimental slog — API may differ slightly from stdlib."
    supports_versions: ">=1.20"
```

### 2.3 Rust backports

Rust uses feature flags and edition-specific crates:

```yaml
backports:
  - feature_id: rust.std.once_lock
    language: rust
    backport_package: once_cell
    install_command: 'cargo add once_cell'
    notes: "OnceLock/LazyLock backport. Widely used."
    import_statement: "use once_cell::sync::OnceCell;"
```

### 2.4 Ruby backports

```yaml
backports:
  - feature_id: ruby.3_2.data
    language: ruby
    backport_package: data_class
    install_command: "gem install data_class"
    notes: "Backport of Ruby 3.2 Data class"
```

### 2.5 PHP backports

```yaml
backports:
  - feature_id: php.8_1.enum
    language: php
    backport_package: "myclabs/php-enum"
    install_command: "composer require myclabs/php-enum"
    notes: "Enum polyfill for PHP < 8.1"

  - feature_id: php.8_0.match
    language: php
    backport_package: null
    notes: "No backport — match expressions must be rewritten as switch statements"
```

---

## 3. Backport Types

| Type | Description | Example |
|------|-------------|---------|
| `drop_in` | Import replaces stdlib, same API | `tomli` as `tomllib` |
| `shim` | Provides the same names but may differ slightly | `typing_extensions` |
| `babel_plugin` | Build-time transform (JS) | `@babel/plugin-transform-optional-chaining` |
| `runtime_polyfill` | Runtime shim added at startup (JS) | `core-js` |
| `experimental` | Official experimental package (Go) | `golang.org/x/exp/slices` |
| `community` | Community-maintained alternative | various |
| `none` | No backport exists — manual rewrite needed | `match/case` |

---

## 4. Backport Lifecycle

### 4.1 Adding a backport (downgrade)

When a fix uses a backport:

```
1. Detection: found "import tomllib" (3.11+)
2. Fix strategy: add_backport_import
3. Registry lookup: tomli, version >=1.0.0
4. Transforms:
   a. Replace import: "import tomllib" → "import tomli as tomllib"
   b. Add to requirements: "tomli>=1.0.0"
5. Verification: file imports correctly with backport
```

### 4.2 Removing a backport (upgrade)

When upgrading past the backport's version:

```
1. Detection: found "import tomli as tomllib" (backport pattern)
2. Fix strategy: replace_import (remove backport)
3. Transforms:
   a. Replace import: "import tomli as tomllib" → "import tomllib"
   b. Remove from requirements: "tomli"
4. Verification: file imports correctly with stdlib
```

### 4.3 Conditional backport (support both)

When the project needs to support BOTH old and new versions:

```python
try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib
```

The backport stays in requirements as an optional dependency. The try/except handles both cases.

---

## 5. Dependency Manifest Updates

When a backport is added or removed, the dependency manifest must be updated:

```python
class DependencyManifestUpdater:
    """Update dependency manifests when backports change."""

    def add_dependency(
        self,
        module_dir: Path,
        package: str,
        version_constraint: str,
        language: str,
    ) -> ManifestChange:
        """Add a dependency to the manifest.

        Python: append to requirements.txt or pyproject.toml [project].dependencies
        JS: npm install --save {package}
        Go: go get {package}
        Rust: cargo add {package}
        Ruby: add to Gemfile
        PHP: composer require {package}
        Elixir: add to mix.exs deps
        """

    def remove_dependency(
        self,
        module_dir: Path,
        package: str,
        language: str,
    ) -> ManifestChange:
        """Remove a dependency from the manifest."""

    def check_dependency_exists(
        self,
        module_dir: Path,
        package: str,
        language: str,
    ) -> bool:
        """Check if a dependency is already in the manifest."""
```

---

## 6. Trustworthiness Assessment

Not all backport packages are equally trustworthy. The registry includes metadata to help the user decide:

| Field | Purpose |
|-------|---------|
| `maintained` | Is the package actively maintained? |
| `official` | Is it by the language core team or stdlib author? |
| `downloads` | Monthly download count (from registry) |
| `last_release` | When was the last version published? |
| `license` | Is the license compatible? |
| `notes` | Human-readable assessment |

The system does NOT auto-install untrusted packages. It presents the information and lets the user decide.

---

## 7. Integration Points

### 7.1 With Feature Database (Document 02)
- Each entry's `fix.backport` references the registry
- Registry entries keyed by `feature_id`

### 7.2 With Fix Engine (Document 05)
- Fix engine looks up backport info when applying `add_backport_import`
- Reports required package additions

### 7.3 With Dependency Analysis (Document 14)
- After adding a backport, dependency analysis re-checks compatibility
- After removing a backport, verifies it's no longer needed

### 7.4 With Upgrade Direction (Document 11)
- Upgrade detects backport imports as removal candidates
- Registry tells the engine which imports are backport patterns
