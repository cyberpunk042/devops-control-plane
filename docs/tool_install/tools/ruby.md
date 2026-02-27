# ruby — Full Spectrum Analysis

> **Tool ID:** `ruby`
> **Last audited:** 2026-02-26
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | Ruby — programming language runtime |
| Language | C (CRuby/MRI) |
| CLI binary | `ruby` |
| Category | `ruby` |
| Verify command | `ruby --version` |
| Recipe key | `ruby` |

### What Ruby does

Ruby is a dynamic, object-oriented programming language.
The `ruby` binary is the interpreter. Installing Ruby also
provides:
- `gem` — Ruby's built-in package manager (RubyGems)
- `irb` — interactive Ruby shell
- `bundler` — dependency manager (since Ruby 2.6+)

### Relationship to bundler

Ruby is to bundler what Node is to npm. Installing Ruby
gives you `gem` (and often `bundler`). The `bundler` recipe
has `requires: {"binaries": ["ruby"]}`.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ✅ | `ruby-full` | Includes ruby + ruby-dev + ruby-doc |
| `dnf` | ✅ | `ruby` + `ruby-devel` | Fedora/RHEL — devel for gem native extensions |
| `apk` | ✅ | `ruby` + `ruby-dev` | Alpine — dev for gem native extensions |
| `pacman` | ✅ | `ruby` | Arch — includes everything |
| `zypper` | ✅ | `ruby-devel` | openSUSE — devel pulls in base ruby |
| `brew` | ✅ | `ruby` | Homebrew |
| `snap` | ❌ | — | Not available |

### Package naming patterns

- **apt:** `ruby-full` = meta-package that ensures ruby + dev + docs
- **dnf:** Installs `ruby` (base) + `ruby-devel` (headers for gem compilation)
- **apk:** `ruby` (base) + `ruby-dev` (headers)
- **zypper:** `ruby-devel` transitively installs `ruby`
- **pacman/brew:** Single package includes everything

### Why install dev headers?

Many Ruby gems include C extensions (native extensions) that
compile during `gem install`. Without dev headers (`ruby-dev`,
`ruby-devel`), these gems fail with missing header errors.
The recipe proactively installs dev headers on distros that
split them into separate packages.

---

## 3. Install Methods

### System packages only — no _default

Ruby from source requires:
1. `autoconf`, `bison`, `gcc`, `make`
2. C library dev packages (`libssl-dev`, `libyaml-dev`, `libreadline-dev`, `zlib1g-dev`, `libffi-dev`)
3. A long `./configure && make && make install` cycle

This is too complex for an automated `_default` method.
System packages are the correct path for Ruby.

For users needing specific Ruby versions, version managers
like `rbenv` or `rvm` are the right tool (separate recipes).

### No snap

Ruby is not available on snapcraft.

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Build (source) | gcc, make, autoconf, bison | Not needed for PM installs |
| Build (source) | libssl-dev, libyaml-dev, libffi-dev, zlib1g-dev | Not needed for PM installs |
| Runtime | None | Self-contained |

### Reverse deps

Ruby is a dependency for:
- `bundler` — Ruby dependency manager
- `rubocop` — Ruby linter
- `jekyll`, `fastlane`, `fpm`, `puppet`, `chef`, `vagrant` (partially)

---

## 5. Post-install

No special PATH configuration needed for PM-installed Ruby.
The binary is placed in system PATH (`/usr/bin/ruby` or
`/usr/local/bin/ruby` for brew).

For brew on macOS, the brew-installed Ruby may shadow the
system Ruby. Users may need to add `$(brew --prefix ruby)/bin`
to PATH if they want the brew version to take priority.

---

## 6. Failure Handlers

### Layer 1: PM-family handlers (10 total)
apt (2), dnf (1), apk (2), pacman (2), zypper (2), brew (1)

### Layer 2a: gem method-family handlers (2) — via category mapping

Ruby has `category: "ruby"` which maps to the `gem` method family.
These handlers apply to any tool that uses `gem install`:

| Handler | Category | Trigger | Options |
|---------|----------|---------|---------|
| `gem_permission_error` | permissions | `Gem::FilePermissionError` — no write to system gem dir | Install to user gem dir (recommended), use sudo |
| `gem_native_extension_failed` | dependency | `mkmf.rb can't find header files` — missing ruby-dev | Install ruby-dev (recommended), install build tools, install Xcode CLT (macOS) |

**Platform considerations:**

- **macOS:** System Ruby (deprecated since Catalina) has no headers.
  The `install-ruby-dev` option installs brew Ruby (includes headers).
  The `install-xcode-clt` manual option offers `xcode-select --install`
  for SDK headers + clang compiler.
- **Raspbian (ARM64):** Uses Debian family packages (`ruby-dev`,
  `build-essential`). ARM-native gcc is provided by `build-essential`.
  Native extension compilation is slower on Pi but functionally correct.

### Layer 2b: INFRA handlers (9 cross-tool)
Network, disk, permissions, OOM, timeout — all standard.

### Layer 3: per-tool on_failure handlers

**None needed.** Remediation audit evaluated three potential candidates:

1. **brew PATH shadowing** — After `brew install ruby`, system Ruby
   at `/usr/bin/ruby` shadows the brew version. However, the verify
   step (`ruby --version`) succeeds with no error stderr, so there's
   no pattern to match. Not an install failure.

2. **Missing dev headers (mkmf.rb)** — Happens during `gem install`
   with native extensions, not during Ruby install itself. Our recipe
   prevents this by using `ruby-full` (apt) and `ruby-devel` (dnf/zypper)
   / `ruby-dev` (apk). Handled by the `gem` method-family handler
   (`gem_native_extension_failed`) with macOS Xcode CLT option.

3. **Outdated distro Ruby version** — Manifests downstream when
   bundler/gems require newer Ruby, not during Ruby's own install.
   Not actionable as an on_failure handler.

**Conclusion:** All install-time failures are fully covered by
PM-family handlers (Layer 2) and INFRA handlers (Layer 1).

---

## 7. Recipe Structure

```python
"ruby": {
    "cli": "ruby",
    "label": "Ruby",
    "category": "ruby",
    "install": {
        "apt":    ["apt-get", "install", "-y", "ruby-full"],
        "dnf":    ["dnf", "install", "-y", "ruby", "ruby-devel"],
        "apk":    ["apk", "add", "ruby", "ruby-dev"],
        "pacman": ["pacman", "-S", "--noconfirm", "ruby"],
        "zypper": ["zypper", "install", "-y", "ruby-devel"],
        "brew":   ["brew", "install", "ruby"],
    },
    "needs_sudo": {
        "apt": True, "dnf": True, "apk": True,
        "pacman": True, "zypper": True, "brew": False,
    },
    "verify": ["ruby", "--version"],
    "update": {
        "apt": [..., "ruby-full"], "dnf": [..., "ruby"],
        "apk": [..., "ruby"], ...
    },
}
```

---

## 8. Validation Results

```
Schema:    VALID (recipe + all method-family handlers + gem handlers)
Coverage:  399/399 (100%) — 21 scenarios × 19 presets
Handlers:  10 PM-family + 2 gem (via category) + 9 INFRA = 21 total
```

---

## 9. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Added `cli: "ruby"`, `update` field |
| `resolver/dynamic_dep_resolver.py` | Fixed KNOWN_PACKAGES: `apk` was `"ruby-full"` (wrong), changed to `"ruby"` |
| `data/remediation_handlers.py` | Created `gem` method-family (2 handlers: permission, native extension) |
| `tests/test_remediation_coverage.py` | Added `ruby → gem` category-to-family mapping |

---

## 10. Design Notes

### No _default method

Unlike Go/Rust which have official binary downloads, Ruby's
installation model is system-package-centric. The Ruby core
team distributes source tarballs only. Binary packages come
from distros and Homebrew. Version managers (rbenv, rvm) fill
the "latest version" gap.

### Why ruby-full vs ruby

On Debian/Ubuntu, `ruby` is the bare interpreter. `ruby-full`
is a meta-package that includes:
- `ruby` (interpreter)
- `ruby-dev` (C headers for native gem compilation)
- `ruby-doc` (documentation)

Using `ruby-full` prevents the common "missing ruby.h" error
when users install gems with native extensions.

### KNOWN_PACKAGES fix

The resolver had `apk: "ruby-full"` — but Alpine Linux has no
`ruby-full` package. That's a Debian-only naming convention.
Fixed to `apk: "ruby"`.
