# phpunit — Full Spectrum Analysis

> **Tool ID:** `phpunit`
> **Last audited:** 2026-02-26
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | PHPUnit — PHP testing framework |
| Language | PHP |
| CLI binary | `phpunit` |
| Category | `php` |
| Verify command | `phpunit --version` |
| Recipe key | `phpunit` |

### What PHPUnit does

PHPUnit is the standard testing framework for PHP. It provides
unit testing, integration testing, and code coverage analysis.

```bash
phpunit                    # run tests from phpunit.xml
phpunit tests/FooTest.php  # run specific test file
phpunit --coverage-text    # run with coverage report
```

PHPUnit is comparable to pytest for Python, jest for JavaScript,
or cargo test for Rust.

### Relationship to Composer

PHPUnit is a Composer package (`phpunit/phpunit`). The canonical
install method is `composer global require phpunit/phpunit`.
The recipe has `requires: {"binaries": ["composer"]}` which
transitively requires PHP.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ❌ | — | Not in Debian/Ubuntu repos |
| `dnf` | ❌ | — | Not in Fedora repos |
| `apk` | ❌ | — | Not in Alpine repos |
| `pacman` | ❌ | — | Not in official Arch repos |
| `zypper` | ❌ | — | Not in openSUSE repos |
| `brew` | ✅ | `phpunit` | formulae.brew.sh — macOS + Linux bottles |
| `snap` | ❌ | — | Not available |
| `composer` | ✅ | `phpunit/phpunit` | Primary install method |

Same distribution pattern as phpstan — Composer + brew only.

### PHP version requirements (aggressive)

PHPUnit has notably aggressive PHP version requirements:
- PHPUnit 10 → PHP 8.1+
- PHPUnit 11 → PHP 8.2+
- PHPUnit 12 → PHP 8.3+
- PHPUnit 13 (2026) → PHP 8.4+

This makes the PHP version handler especially important for
phpunit — users on stable LTS distros (Debian, Ubuntu LTS,
Raspbian) frequently have PHP versions too old for the latest
PHPUnit.

---

## 3. Install Methods

### _default (composer global require) — PREFERRED

```bash
composer global require phpunit/phpunit
```

Same rationale as phpstan — official method, latest version,
no sudo needed. PATH note: installs to
`$HOME/.config/composer/vendor/bin`.

### brew

```bash
brew install phpunit
```

Good for macOS users. Bundles its own PHP — no system PHP
dependency, bypasses version requirements.

### Not in system PMs

PHPUnit is not available in apt, dnf, apk, pacman, or zypper.

### macOS

- **brew** is the simplest path
- `_default` also works (needs `composer` from brew)

### Raspbian

- No apt package — must use `_default` (composer)
- Memory pressure likely on 1GB/2GB models
- PHP version from apt may be too old for latest PHPUnit

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Required | `composer` | PHPUnit IS a Composer package |
| Transitive | `php` | Composer requires PHP |
| Runtime | None beyond PHP | Pure PHP |

### Dependency chain

```
phpunit → composer → php
```

---

## 5. Post-install

Same as phpstan:

```bash
export PATH="$HOME/.config/composer/vendor/bin:$PATH"
```

For brew installs, no PATH changes needed.

---

## 6. Failure Handlers

### Layer 1: _default handlers (5)
Missing curl/git/wget/unzip/npm — standard `_default` family.

### Layer 1b: brew handler (1)
brew_no_formula — standard brew family.

### Layer 2: INFRA handlers (9 cross-tool)
Network, disk, permissions, OOM, timeout — all standard.

### Layer 3: per-tool on_failure handlers (2)

| Handler | Category | Trigger | Options |
|---------|----------|---------|---------|
| `phpunit_composer_memory_limit` | resources | `Allowed memory size of X bytes exhausted` — PHP memory cap during composer | Retry with `COMPOSER_MEMORY_LIMIT=-1` (recommended), switch to brew |
| `phpunit_php_version_too_old` | environment | `phpunit/phpunit requires php ^8.2` — system PHP too old | Upgrade PHP (recommended), switch to brew |

**Platform considerations:**

- **macOS:** brew is the ideal fallback — bundles compatible PHP.
- **Raspbian (ARM64):** Most likely to hit both handlers — low RAM
  (memory limit) and old PHP from apt repos (version too old).
  `COMPOSER_MEMORY_LIMIT=-1` for memory, `install_dep: php` for
  version.
- **Alpine (Docker):** Low memory limits in containers. Same fix.

---

## 7. Recipe Structure

```python
"phpunit": {
    "cli": "phpunit",
    "label": "PHPUnit (PHP testing)",
    "category": "php",
    "install": {
        "_default": [
            "bash", "-c",
            "composer global require phpunit/phpunit",
        ],
        "brew": ["brew", "install", "phpunit"],
    },
    "needs_sudo": {"_default": False, "brew": False},
    "requires": {"binaries": ["composer"]},
    "post_env": 'export PATH="$HOME/.config/composer/vendor/bin:$PATH"',
    "verify": ["bash", "-c",
               'export PATH="..." && phpunit --version'],
    "update": {
        "_default": [..., "composer global update phpunit/phpunit"],
        "brew": ["brew", "upgrade", "phpunit"],
    },
}
```

---

## 8. Validation Results

```
Schema:    VALID (recipe + all method-family handlers + on_failure)
Coverage:  323/323 (100%) — 17 scenarios × 19 presets
Handlers:  5 _default + 1 brew + 2 on_failure + 9 INFRA = 17 total
```

---

## 9. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Added `cli` field |
| `data/recipes.py` | Added `brew` install method |
| `data/recipes.py` | Added `update` for both methods |
| `data/tool_failure_handlers.py` | Added 2 `on_failure` handlers: composer memory limit, PHP version too old |

---

## 10. Design Notes

### PHPUnit vs phpstan — handler duplication

Both tools have the same two handlers (composer memory limit +
PHP version too old). This is deliberate:

1. The `failure_id` is tool-specific for tracking
2. The error patterns reference different package names
   (`phpunit/phpunit` vs `phpstan/phpstan`)
3. PHPUnit has much more aggressive PHP version requirements
   (8.2+ vs 7.4+), so the description guidance differs

If many more Composer-installed tools are added, consider
extracting a shared "composer-install" method family. For now,
per-tool duplication is cleaner.

### Aggressive PHP version requirements

PHPUnit's PHP version requirements increase every year. This
means the `phpunit_php_version_too_old` handler will fire
more frequently than phpstan's. Users on Debian 12 (PHP 8.2)
won't be able to install PHPUnit 12 (needs PHP 8.3) — this
is a real, common scenario.
