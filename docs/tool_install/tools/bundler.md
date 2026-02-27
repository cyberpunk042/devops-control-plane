# bundler — Full Spectrum Analysis

> **Tool ID:** `bundler`
> **Last audited:** 2026-02-26
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | Bundler — Ruby dependency manager |
| Language | Ruby |
| CLI binary | `bundle` (NOT `bundler`) |
| Category | `ruby` |
| Verify command | `bundle --version` |
| Recipe key | `bundler` |

### What bundler does

Bundler manages Ruby gem dependencies via `Gemfile` and
`Gemfile.lock`. It's the standard dependency manager for
Ruby projects — equivalent to pip + requirements.txt for
Python or npm + package.json for Node.

```bash
bundle install       # install gems from Gemfile
bundle exec rake     # run command with bundle context
bundle update        # update gems within version constraints
```

### Modern Ruby note

Ruby 2.6+ ships with Bundler built-in. On most modern
systems, installing Ruby automatically gives you `bundle`.
The standalone install is mainly for:
- Upgrading to a newer Bundler version
- Systems with stripped-down Ruby packages
- CI/Docker images with minimal Ruby

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ✅ | `ruby-bundler` | Debian/Ubuntu |
| `dnf` | ✅ | `rubygem-bundler` | Fedora/RHEL |
| `apk` | ✅ | `ruby-bundler` | Alpine |
| `pacman` | ✅ | `ruby-bundler` | Arch |
| `zypper` | ✅ | `ruby-bundler` | openSUSE |
| `brew` | ❌ | — | No separate formula; ships with brewed Ruby |
| `snap` | ❌ | — | Not available |
| `gem` | ✅ | `bundler` | RubyGems (_default method) |

### Package name divergence

- **apt/apk/pacman/zypper:** `ruby-bundler`
- **dnf:** `rubygem-bundler` (Fedora naming convention)
- **gem:** `bundler`

### No brew formula

Homebrew doesn't have a separate `bundler` formula because
`brew install ruby` includes Bundler. The recipe omits
brew as an install method.

---

## 3. Install Methods

### _default (gem install) — PREFERRED

```bash
gem install bundler
```

Preferred because:
1. Always latest version
2. Ruby is already required anyway
3. No sudo needed (installs to user gem dir)
4. Consistent across all platforms

### PM methods (apt/dnf/apk/pacman/zypper)

System packages — distro-maintained, may lag behind latest.
All require sudo.

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Required | `ruby` | Bundler IS a Ruby gem |
| Runtime | None beyond Ruby | Self-contained |

### No C library deps

Bundler is pure Ruby — no native extensions, no C deps.

---

## 5. Post-install

No special PATH or shell config needed. The `gem` command
installs binaries to a location already in Ruby's PATH
(e.g. `~/.gem/ruby/X.Y/bin` or system gem bin dir).

---

## 6. Failure Handlers

### Layer 1: PM-family handlers
- `apt` (2), `dnf` (1), `apk` (2), `pacman` (2), `zypper` (2)
- `_default` (5) — missing curl/git/wget/unzip/npm

### Layer 2: gem method-family handlers (2) — via category mapping

Bundler has `category: "ruby"` which maps to the `gem` method family:

| Handler | Category | Trigger | Options |
|---------|----------|---------|---------|
| `gem_permission_error` | permissions | `Gem::FilePermissionError` — no write to system gem dir | Install to user gem dir (recommended), use sudo |
| `gem_native_extension_failed` | dependency | `mkmf.rb can't find header files` — missing ruby-dev | Install ruby-dev (recommended), install build tools, install Xcode CLT (macOS) |

Note: `gem_native_extension_failed` won't fire for bundler itself
(pure Ruby, no native extensions) but applies to other gems in the
`ruby` category.

**Platform considerations:**

- **macOS:** `gem install bundler` can hit `Gem::FilePermissionError`
  when using system Ruby (deprecated since Catalina). The permission
  handler offers GEM_HOME fix (recommended) or sudo.
  The Xcode CLT option in `gem_native_extension_failed` is irrelevant
  for bundler (pure Ruby) but helps other ruby-category tools.
- **Raspbian (ARM64):** `apt install ruby-bundler` works identically
  to x86 Debian. `gem install bundler` also works (pure Ruby, no
  architecture-dependent compilation).

### Layer 3: INFRA handlers (9 cross-tool)
Network, disk, permissions, OOM, timeout — all standard.

### Layer 4: per-tool on_failure handlers

**None needed.** Remediation audit evaluated potential candidates:

1. **`gem: command not found`** — Already caught by the dependency
   resolver (`requires: {"binaries": ["ruby"]}`).
   If Ruby is present, `gem` is present.

2. **SSL/TLS errors with rubygems.org** — Covered by INFRA
   network unreachable handler.

3. **Bundler version conflict** — `gem install bundler` always
   succeeds (installs latest). Not an install failure.

**Conclusion:** All install-time failures are covered by PM-family
(Layer 1), gem method-family (Layer 2), and INFRA (Layer 3).

---

## 7. Recipe Structure

```python
"bundler": {
    "cli": "bundle",
    "label": "Bundler (Ruby dependency manager)",
    "category": "ruby",
    "install": {
        "apt":    ["apt-get", "install", "-y", "ruby-bundler"],
        "dnf":    ["dnf", "install", "-y", "rubygem-bundler"],
        "apk":    ["apk", "add", "ruby-bundler"],
        "pacman": ["pacman", "-S", "--noconfirm", "ruby-bundler"],
        "zypper": ["zypper", "install", "-y", "ruby-bundler"],
        "_default": ["gem", "install", "bundler"],
    },
    "needs_sudo": {
        "apt": True, "dnf": True, "apk": True,
        "pacman": True, "zypper": True, "_default": False,
    },
    "prefer": ["_default"],
    "requires": {"binaries": ["ruby"]},
    "verify": ["bundle", "--version"],
    "update": {
        "apt":    [...], "dnf": [...], ...
        "_default": ["gem", "update", "bundler"],
    },
}
```

---

## 8. Validation Results

```
Schema:    VALID (recipe + all method-family handlers + gem handlers)
Coverage:  475/475 (100%) — 25 scenarios × 19 presets
Handlers:  9 PM-family + 5 _default + 2 gem (via category) + 9 INFRA = 25 total
```

---

## 9. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Expanded bundler recipe from 1 method to 6 (added apt/dnf/apk/pacman/zypper) |
| `data/recipes.py` | Added `prefer`, `update` fields |
| `data/remediation_handlers.py` | Created `gem` method-family (2 handlers: permission, native extension) |
| `tests/test_remediation_coverage.py` | Added `ruby → gem` category-to-family mapping |

---

## 10. Design Notes

### Why no brew method?

Homebrew's Ruby formula includes Bundler since Ruby 2.6.
Adding `brew install bundler` would fail because there's no
such formula — users should `brew install ruby` instead.

### gem as _default with category mapping

`gem install` is mapped to `_default` in the recipe. Bundler
automatically inherits gem method-family handlers via its
`category: "ruby"` → `gem` family mapping. This means both
`gem_permission_error` and `gem_native_extension_failed`
apply to bundler without needing tool-specific `on_failure`.

### Package name divergence

Fedora uses `rubygem-` prefix for all Ruby gem system packages
(e.g. `rubygem-bundler`, `rubygem-rake`). All other distros use
`ruby-` prefix. This is handled in the recipe's per-PM install
commands.
