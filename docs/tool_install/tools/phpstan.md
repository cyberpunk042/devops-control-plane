# phpstan — Full Spectrum Analysis

> **Tool ID:** `phpstan`
> **Last audited:** 2026-02-26
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | PHPStan — PHP Static Analysis Tool |
| Language | PHP |
| CLI binary | `phpstan` |
| Category | `php` |
| Verify command | `phpstan --version` |
| Recipe key | `phpstan` |

### What PHPStan does

PHPStan finds bugs in PHP code without running it. It performs
static analysis — type checking, dead code detection, and error
finding at analysis time rather than runtime.

```bash
phpstan analyse src/       # analyse source directory
phpstan analyse --level 5  # set strictness level (0-9)
```

PHPStan is comparable to mypy for Python, eslint for JavaScript,
or ruff for Python — a static analysis / linting tool.

### Relationship to Composer

PHPStan is a Composer package (`phpstan/phpstan`). The canonical
install method is `composer global require phpstan/phpstan`.
The recipe has `requires: {"binaries": ["composer"]}` which
transitively requires PHP.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ❌ | — | Not in Debian/Ubuntu repos |
| `dnf` | ❌ | — | Not in Fedora repos |
| `apk` | ❌ | — | Not in Alpine repos |
| `pacman` | ❌ | — | AUR only (`phpstan-bin`), not official |
| `zypper` | ❌ | — | Not in openSUSE repos |
| `brew` | ✅ | `phpstan` | formulae.brew.sh — macOS + Linux bottles |
| `snap` | ❌ | — | Not available |
| `composer` | ✅ | `phpstan/phpstan` | Primary install method |

### Why so few PMs?

PHPStan is a PHP-ecosystem tool distributed exclusively through
Composer (PHP's package manager) and Homebrew. Linux distributions
don't package PHP development tools in their system repos — only
the PHP interpreter and core extensions.

This is the same pattern as mypy (pip-only), eslint (npm-only),
or ruff (pip/cargo-only) — language-specific tools live in their
language's package ecosystem.

---

## 3. Install Methods

### _default (composer global require) — PREFERRED

```bash
composer global require phpstan/phpstan
```

Why preferred:
1. Official recommended method
2. Always latest version
3. Supports PHPStan extensions (`phpstan-extension-installer`)
4. No sudo needed

Requires: `composer` binary (which requires `php`)

PATH note: `composer global require` installs to
`$HOME/.config/composer/vendor/bin`. The recipe's `post_env`
adds this to PATH.

### brew

```bash
brew install phpstan
```

Good for macOS users who prefer brew over composer global.
Pre-compiled bottles available for macOS (ARM64 + x86_64)
and Linux (ARM64 + x86_64). No composer dependency when
installing via brew.

### Not in system PMs

PHPStan is not available in apt, dnf, apk, pacman, or zypper.
The only system-level option is brew.

### macOS

- **brew** is the simplest path — `brew install phpstan`
- `_default` also works (needs `composer` from brew)
- No Xcode CLT dependency — pure PHP

### Raspbian

- No apt package — must use `_default` (composer)
- Requires `composer` + `php` installed first
- ARM64 — no architecture issues (pure PHP)

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Required | `composer` | PHPStan IS a Composer package |
| Transitive | `php` | Composer requires PHP |
| Runtime | None beyond PHP | Pure PHP |

### Dependency chain

```
phpstan → composer → php
```

### No C library deps

PHPStan is entirely PHP — no native extensions, no compilation.

---

## 5. Post-install

Composer global packages install binaries to a vendor bin directory.
The recipe's `post_env` handles this:

```bash
export PATH="$HOME/.config/composer/vendor/bin:$PATH"
```

Note: The actual path may vary:
- Linux: `$HOME/.config/composer/vendor/bin`
- macOS (brew PHP): `$HOME/.composer/vendor/bin`

The verify command wraps this PATH setup to ensure detection works
regardless of shell configuration.

For brew installs, no PATH changes needed — brew manages its own
bin directory.

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
| `phpstan_composer_memory_limit` | resources | `Allowed memory size of X bytes exhausted` — PHP memory cap during composer | Retry with `COMPOSER_MEMORY_LIMIT=-1` (recommended), switch to brew |
| `phpstan_php_version_too_old` | environment | `phpstan/phpstan requires php ^7.4` — system PHP too old | Upgrade PHP (recommended), switch to brew |

**Platform considerations:**

- **macOS:** brew is the ideal fallback — `brew install phpstan`
  bundles its own PHP, bypassing both memory and version issues.
- **Raspbian (ARM64):** Most likely to hit composer memory limit
  on 1GB/2GB models. `COMPOSER_MEMORY_LIMIT=-1` is the primary fix.
  brew is available on Raspbian but less common.
- **Alpine (Docker):** Minimal containers may have low memory
  limits. Same memory fix applies.

---

## 7. Recipe Structure

```python
"phpstan": {
    "cli": "phpstan",
    "label": "PHPStan (PHP static analysis)",
    "category": "php",
    "install": {
        "_default": [
            "bash", "-c",
            "composer global require phpstan/phpstan",
        ],
        "brew": ["brew", "install", "phpstan"],
    },
    "needs_sudo": {"_default": False, "brew": False},
    "requires": {"binaries": ["composer"]},
    "post_env": 'export PATH="$HOME/.config/composer/vendor/bin:$PATH"',
    "verify": ["bash", "-c",
               'export PATH="..." && phpstan --version'],
    "update": {
        "_default": [..., "composer global update phpstan/phpstan"],
        "brew": ["brew", "upgrade", "phpstan"],
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

### Composer global vs project-local

PHPStan can be installed two ways via Composer:
- `composer global require` — system-wide, in `~/.config/composer`
- `composer require --dev` — per-project, in `./vendor`

Our recipe uses `global` because the tool_install system installs
tools system-wide for the user, not per-project.

### Why brew is important

Brew is the only non-Composer install method. On macOS, `brew install
phpstan` bypasses the composer dependency entirely — brew's phpstan
formula bundles its own PHP. This is simpler for macOS users who
don't use Composer.

### PHAR alternative (not used)

PHPStan also distributes a `.phar` file (self-contained PHP archive):
```bash
curl -sSL https://github.com/phpstan/phpstan/releases/latest/download/phpstan.phar \
  -o /usr/local/bin/phpstan && chmod +x /usr/local/bin/phpstan
```
We don't use this because:
1. No auto-update mechanism
2. Composer method supports PHPStan extensions
3. PHAR needs manual version management
