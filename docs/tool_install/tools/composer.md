# composer — Full Spectrum Analysis

> **Tool ID:** `composer`
> **Last audited:** 2026-02-26
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | Composer — PHP dependency manager |
| Language | PHP |
| CLI binary | `composer` |
| Category | `php` |
| Verify command | `composer --version` |
| Recipe key | `composer` |

### What Composer does

Composer manages PHP project dependencies via `composer.json` and
`composer.lock`. It is to PHP what npm is to Node or pip is to
Python. It handles:
- Autoloading (PSR-4)
- Dependency resolution with semantic versioning
- Package scripts (build hooks)
- Plugin extensions

```bash
composer install        # install deps from composer.lock
composer require X      # add a package
composer update         # update deps within constraints
```

### Relationship to PHP

Composer is a PHP application — it runs on the PHP interpreter.
The recipe has `requires: {"binaries": ["php", "curl"]}`.
PHP must be installed first (separate `php` recipe).

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ✅ | `composer` | Debian/Ubuntu — bullseye through sid |
| `dnf` | ✅ | `composer` | Fedora |
| `apk` | ✅ | `composer` | Alpine — v3.19+ and edge |
| `pacman` | ✅ | `composer` | Arch |
| `zypper` | ✅ | `php-composer` | openSUSE (**different name!**) |
| `brew` | ✅ | `composer` | Homebrew |
| `snap` | ❌ | — | Not officially maintained |

### Package naming

All PMs use `composer` EXCEPT:
- **zypper:** Uses `php-composer` (openSUSE convention for PHP tools)

This divergence is handled in the recipe's per-PM install commands
and update commands.

### Distro version lag

PM-installed Composer can lag behind the latest upstream release.
On Debian ≤ 12, `composer self-update` is disabled for
apt-installed versions. The `_default` (official installer)
method always gets the latest release.

---

## 3. Install Methods

### _default (official installer) — PREFERRED

```bash
curl -sS https://getcomposer.org/installer \
  | php -- --install-dir=/usr/local/bin --filename=composer
```

Why preferred:
1. Always latest stable version
2. Official installer verifies download hash
3. `--install-dir` and `--filename` flags avoid manual `mv`
4. Full `composer self-update` support

Requires: `php`, `curl` (both in `requires.binaries`)

### PM methods (apt/dnf/apk/pacman/zypper/brew)

System packages — distro-maintained, may lag behind latest.
All Linux PMs require sudo; brew does not.

### No snap

Composer depends on the host PHP interpreter and its extensions.
Snap's sandboxing prevents this — not a viable install path.

### macOS

- **brew** is the primary PM on macOS
- `_default` also works on macOS (needs PHP + curl from brew)
- No Xcode CLT dependency — Composer is pure PHP

### Raspbian

- Uses Debian family → `apt install composer` works
- ARM64 — no architecture issues (pure PHP, no native code)

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Required | `php` | Composer IS a PHP application |
| Required | `curl` | For _default installer download |
| Runtime | None beyond PHP | Pure PHP, no C extensions |

### No C library deps

Composer is entirely PHP — no native extensions, no compilation.
Unlike gems with native extensions, Composer never needs
build-essential or dev headers.

### Reverse deps

Composer is a dependency for:
- `phpstan` — PHP static analysis (`requires: {binaries: ["composer"]}`)
- `php-cs-fixer` — PHP code style fixer
- `phpunit` — PHP testing framework (via `composer require`)

---

## 5. Post-install

No special PATH configuration needed. The `_default` installer
places the binary at `/usr/local/bin/composer` which is in PATH.
PM-installed Composer also goes to system PATH.

For macOS brew, the binary goes to `$(brew --prefix)/bin/composer`
which is in the brew-managed PATH.

---

## 6. Failure Handlers

### Layer 1: PM-family handlers
- `apt` (2) — stale index, locked
- `dnf` (1) — no match
- `apk` (2) — unsatisfiable, locked
- `pacman` (2) — target not found, locked
- `zypper` (2) — not found, locked
- `brew` (1) — no formula
- `_default` (5) — missing curl/git/wget/unzip/npm

### Layer 2: INFRA handlers (9 cross-tool)
Network, disk, permissions, OOM, timeout — all standard.

### Layer 3: per-tool on_failure handlers (2)

| Handler | Category | Trigger | Options |
|---------|----------|---------|---------|
| `composer_php_version_too_old` | environment | `Composer requires PHP ^7.2.5` — PHP too old for Composer 2 | Upgrade PHP (recommended), switch to apt, switch to brew |
| `composer_missing_php_extension` | dependency | `The openssl extension is required` — missing PHP ext | Install PHP extension packages (recommended), switch to apt, switch to brew |

**Platform considerations:**

- **macOS:** Brew PHP includes all essential extensions (openssl,
  mbstring, etc.) — the missing extension handler rarely fires.
  PHP version is always current via brew.
- **Raspbian (ARM64):** Uses Debian `php-*` extension packages.
  Same as x86 Debian — no ARM-specific differences for Composer
  (pure PHP, no native code).
- **Alpine (Docker):** Minimal Alpine PHP often has missing extensions.
  The handler suggests `php-openssl`, `php-mbstring`, etc.

---

## 7. Recipe Structure

```python
"composer": {
    "cli": "composer",
    "label": "Composer (PHP dependency manager)",
    "category": "php",
    "install": {
        "apt":    ["apt-get", "install", "-y", "composer"],
        "dnf":    ["dnf", "install", "-y", "composer"],
        "apk":    ["apk", "add", "composer"],
        "pacman": ["pacman", "-S", "--noconfirm", "composer"],
        "zypper": ["zypper", "install", "-y", "php-composer"],
        "brew":   ["brew", "install", "composer"],
        "_default": [
            "bash", "-c",
            "curl -sS https://getcomposer.org/installer"
            " | php -- --install-dir=/usr/local/bin"
            " --filename=composer",
        ],
    },
    "needs_sudo": {
        "apt": True, "dnf": True, "apk": True,
        "pacman": True, "zypper": True,
        "brew": False, "_default": True,
    },
    "prefer": ["_default", "brew"],
    "requires": {"binaries": ["php", "curl"]},
    "verify": ["composer", "--version"],
    "update": {
        "apt":    [..., "composer"],
        "dnf":    [..., "composer"],
        "apk":    [..., "composer"],
        "pacman": [..., "composer"],
        "zypper": [..., "php-composer"],
        "brew":   ["brew", "upgrade", "composer"],
        "_default": ["composer", "self-update"],
    },
}
```

---

## 8. Validation Results

```
Schema:    VALID (recipe + all method-family handlers + on_failure)
Coverage:  494/494 (100%) — 26 scenarios × 19 presets
Handlers:  10 PM-family + 5 _default + 2 on_failure + 9 INFRA = 26 total
```

---

## 9. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Added `cli`, expanded from 2 to 7 install methods (apt/dnf/apk/pacman/zypper/brew/_default) |
| `data/recipes.py` | Added `prefer`, `update` fields |
| `data/recipes.py` | Improved _default to use `--install-dir`/`--filename` instead of manual `mv` |
| `data/tool_failure_handlers.py` | Added 2 `on_failure` handlers: PHP version too old, missing PHP extension |

---

## 10. Design Notes

### Why php-composer on zypper?

openSUSE follows a naming convention for PHP packages: tools
provided by/for PHP get the `php-` prefix. This is similar to
how Fedora uses `rubygem-` for Ruby gem packages. Only zypper
diverges from the `composer` package name.

### _default installer improvements

The original recipe had:
```bash
curl -sS https://getcomposer.org/installer | php \
  && sudo mv composer.phar /usr/local/bin/composer
```

This was replaced with:
```bash
curl -sS https://getcomposer.org/installer \
  | php -- --install-dir=/usr/local/bin --filename=composer
```

Benefits:
- No manual `mv` step
- The installer script handles hash verification
- `--install-dir` and `--filename` are official flags
- Cleaner one-step install

### No snap and why

Composer needs access to the host PHP interpreter and all its
installed extensions. Snap's strict confinement prevents this.
While a classic snap could work, no official snap is maintained.

### Composer self-update caveat

On Debian ≤ 12, the apt-installed Composer disables `self-update`
by patching the Composer source. This is a Debian policy decision
(system packages should be managed by apt). Our `update` field
uses `apt install --only-upgrade` for apt-installed Composer,
which is the correct path. The `_default` install supports
`composer self-update` natively.
