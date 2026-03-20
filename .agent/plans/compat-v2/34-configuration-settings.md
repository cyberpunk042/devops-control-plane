# 34 — Configuration & Settings Spec

> **Document**: 34 of 37
> **Milestone**: M10 — Integration & UX
> **Status**: Draft

---

## 1. Purpose

Configuration for the compat system — what can be customized, where settings live, and what the defaults are.

---

## 2. Configuration Layers

### 2.1 Project-level (project.yml)

```yaml
compat:
  # Default target direction
  default_direction: downgrade

  # Default behavior for NEEDS_ATTENTION in batch
  batch_stop_on_attention: true    # Stop batch when findings need attention

  # Verification settings
  verification:
    import_check: true             # Run import checks after fixes
    related_imports_check: true    # Check files that import fixed files
    max_related_files: 10          # Limit related import checks

  # Exclusions
  exclude_patterns:
    - "**/test_*.py"               # Don't scan test files for downgrade
    - "**/__pycache__/**"
    - "**/node_modules/**"
    - "**/vendor/**"
    - "**/.venv/**"

  # Per-module overrides
  modules:
    core:
      exclude_patterns:
        - "src/core/scripts/**"    # Skip generated scripts
    web:
      exclude_patterns: []         # No extra exclusions
```

### 2.2 Feature database level (_meta.yml)

Per-language defaults defined in `database/entries/{language}/_meta.yml`:

```yaml
language: python
parser: ast
file_extensions: [".py"]
default_exclusions:
  - "__pycache__"
  - ".venv"
  - "venv"
  - ".tox"
  - ".mypy_cache"
  - ".pytest_cache"
  - "*.pyc"
  - "*.pyo"
```

### 2.3 Environment variables

```
COMPAT_DB_PATH          Path to feature database (default: bundled)
COMPAT_CACHE_TTL        Registry cache TTL in seconds (default: 3600)
COMPAT_IMPORT_DEPTH     Max import chain depth (default: 50)
COMPAT_VERIFY_TIMEOUT   Verification timeout per file in seconds (default: 30)
COMPAT_PARALLEL         Enable parallel file processing (default: false)
```

---

## 3. Module-Level Configuration

Each module's version plan can have configuration:

```yaml
modules:
  - name: web
    path: src/ui/web
    stack: python-flask
    version_plan:
      target: "3.8"
      direction: downgrade
      config:
        skip_test_files: true      # Don't flag findings in test files
        fix_scope: module_only     # Only fix files in this module
        include_dev_deps: false    # Don't check dev dependencies
        custom_python: "/usr/bin/python3.8"  # Specific Python for verification
```

---

## 4. Defaults

| Setting | Default | Description |
|---------|---------|-------------|
| `default_direction` | `downgrade` | Default direction for analysis |
| `batch_stop_on_attention` | `true` | Stop batch on NEEDS_ATTENTION |
| `verification.import_check` | `true` | Run import checks |
| `verification.related_imports_check` | `true` | Check importers |
| `verification.max_related_files` | `10` | Max files for related check |
| `import_depth` | `50` | Max transitive import depth |
| `cache_ttl` | `3600` | Registry cache TTL (seconds) |
| `skip_test_files` | `false` | Exclude test files from scan |
| `fix_scope` | `module_only` | Fix only within module boundary |

---

## 5. Integration Points

### 5.1 With project.yml
- Compat config lives under `compat:` key
- Module-specific config under each module's `version_plan.config`
- Backward compatible — missing config uses defaults

### 5.2 With Engine
- Engine reads config at startup
- Config influences analysis scope, verification behavior, exclusions

### 5.3 With CLI
- CLI flags override config: `--no-verify`, `--include-tests`, etc.
- Config file values are the defaults when flags are not provided
