# Domain: Pages Install Unification

> ⚠️ **PHASE LABELS MAY BE STALE** — As of 2026-02-25, code has evolved far beyond
> what the phase roadmaps suggest. Many features labeled "Phase 4-8 future" are
> ALREADY IMPLEMENTED. See `audit-domain-docs.md` and `audit-missing-pieces.md`
> for the verified truth. Code is the source of truth, not these phase labels.


> This document catalogs the unification of pages_install.py
> (Hugo, Docusaurus, MkDocs) with the main tool install system.
> What the current separate system does, how each builder maps
> to TOOL_RECIPES, and the migration path.
>
> SOURCE DOCS: scope-expansion §2.18 (pages install unification),
>              pages_install.py (current implementation),
>              domain-package-managers §pip, npm,
>              domain-binary-installers §download pattern

---

## Overview

### Current state: SEPARATE system

`pages_install.py` is a standalone install system for page
builders. It duplicates functionality that the main tool install
system already provides or will provide.

### What pages_install.py does

| Feature | Implementation | Duplication |
|---------|---------------|-------------|
| SSE streaming | Own generator + yield events | Duplicates tool_install SSE |
| pip install | `_pip_install()` inner function | Duplicates pip recipe pattern |
| npm install | `_npm_install()` inner function | Duplicates npm recipe pattern |
| Hugo binary | `_hugo_binary_install()` function | Duplicates binary installer |
| Arch detection | `platform.machine()` inline | Duplicates Phase 1 profile |
| glibc version | `_glibc_version()` via ctypes | Duplicates hardware detect |
| GitHub API fetch | `urllib.request` to releases API | Duplicates version fetch |
| Already installed check | `builder.detect()` | Duplicates tool verify |

### Target state: UNIFIED

Hugo, MkDocs, Docusaurus become entries in TOOL_RECIPES.
Same resolver, same plan engine, same SSE streaming, same
frontend modals.

---

## Current pages_install.py Analysis

### 3 builders, 3 install methods

| Builder | Install method | Command | Sudo |
|---------|---------------|---------|------|
| MkDocs | pip | `pip install mkdocs mkdocs-material` | No |
| Docusaurus | npm | `npx create-docusaurus@latest` | No |
| Hugo | Binary download | GitHub releases → tar.gz → ~/.local/bin | No |

### Hugo binary installer (the complex one)

Current implementation in `_hugo_binary_install()`:

```python
# 1. Detect arch (x86_64 → amd64, aarch64 → arm64)
# 2. Verify Linux (only platform supported)
# 3. Fetch latest release from GitHub API
# 4. Find matching asset (hugo_VERSION_linux-ARCH.tar.gz)
# 5. Download tarball to temp file
# 6. Extract hugo binary from tarball
# 7. Move to ~/.local/bin/hugo
# 8. chmod 755
# 9. Add ~/.local/bin to PATH if needed
# 10. Verify: hugo version
```

This is exactly the binary installer pattern from
`domain-binary-installers.md` — it can be expressed as a recipe.

### pip installer

```python
# Current:
cmd = list(info.install_cmd)
cmd[0] = str(Path(sys.executable).parent / "pip")
# Uses venv pip, not system pip
```

This maps directly to a pip recipe with `venv: True`.

### npm installer

```python
# Current:
cmd = list(info.install_cmd)
# Runs npm/npx directly
```

This maps directly to an npm recipe.

---

## TOOL_RECIPES Mapping

### MkDocs

```python
"mkdocs": {
    "label": "MkDocs",
    "category": "pages",
    "install": {
        "_default": [sys.executable, "-m", "pip", "install",
                     "mkdocs", "mkdocs-material"],
    },
    "needs_sudo": {"_default": False},
    "verify": ["mkdocs", "--version"],
    "update": {
        "_default": [sys.executable, "-m", "pip", "install",
                     "--upgrade", "mkdocs", "mkdocs-material"],
    },
    "install_method": "pip",
    "venv_aware": True,
}
```

### Docusaurus

```python
"docusaurus": {
    "label": "Docusaurus",
    "category": "pages",
    "install": {
        "_default": ["npm", "install", "@docusaurus/core"],
    },
    "needs_sudo": {"_default": False},
    "verify": ["npx", "docusaurus", "--version"],
    "requires": {
        "binaries": ["node", "npm"],
    },
    "install_method": "npm",
}
```

### Hugo

```python
"hugo": {
    "label": "Hugo",
    "category": "pages",
    "install": {
        "binary": {
            "type": "github_release",
            "repo": "gohugoio/hugo",
            "asset_pattern": "hugo_{version}_linux-{arch}.tar.gz",
            "extract": "tar",
            "binary_name": "hugo",
            "install_dir": "~/.local/bin",
        },
        "brew": ["brew", "install", "hugo"],
        "snap": ["snap", "install", "hugo"],
    },
    "needs_sudo": {
        "binary": False,
        "brew": False,
        "snap": True,
    },
    "verify": ["hugo", "version"],
    "install_method": {
        "linux": "binary",
        "darwin": "brew",
    },
    "arch_map": {
        "x86_64": "amd64",
        "aarch64": "arm64",
    },
}
```

---

## Migration Plan

### Phase 3 migration

| Step | What | Breaking? |
|------|------|----------|
| 1 | Add MkDocs/Docusaurus/Hugo to TOOL_RECIPES | No — additive |
| 2 | Create binary installer for Hugo recipe | No — new code |
| 3 | Frontend: pages-install uses same modal as tool install | No — UI only |
| 4 | Pages tab calls unified install API | No — backend supports both |
| 5 | Deprecate pages_install.py (keep as fallback) | No — old code still works |
| 6 | Remove pages_install.py | Yes — old code removed |

### Backward compatibility

During migration, BOTH paths work:

```python
# Route handler
@app.post("/api/pages/install/{name}")
async def install_page_builder(name: str):
    # Try unified system first
    if name in TOOL_RECIPES:
        return unified_install(name)
    # Fallback to old system
    return legacy_install_builder_stream(name)
```

---

## What Changes

### Detection

| Current | Unified |
|---------|---------|
| `builder.detect()` (pages_builders.py) | `shutil.which("hugo")` (standard verify) |
| Custom detect per builder | Same verify pattern as all tools |

### SSE events

| Current | Unified |
|---------|---------|
| `{"type": "log", "line": "..."}` | Same format (compatible) |
| `{"type": "done", "ok": True}` | Same format (compatible) |
| Generator yielding events | Same pattern |

The SSE event format is already compatible. No frontend changes
needed for the event stream itself.

### Arch detection

| Current | Unified |
|---------|---------|
| `platform.machine().lower()` inline | Fast profile `arch` field |
| Manual map: x86_64 → amd64 | `arch_map` in recipe |

### Version detection

| Current | Unified |
|---------|---------|
| GitHub API fetch inline | Dynamic version source in recipe |
| No caching | Version cache with TTL |

---

## What Stays the Same

### pages_builders.py

The builder registry (`get_builder()`, `BuilderInfo`) stays.
It provides builder metadata beyond installation:

- Template generation
- Build commands
- Config structure
- Site structure

TOOL_RECIPES handles INSTALLATION. pages_builders handles
USAGE (build, serve, config). They are complementary.

### Frontend pages tab

The pages tab still shows builders. The install button just
calls the unified install API instead of the separate one.

---

## Hugo Binary Installer as Recipe

### Current implementation mapped to recipe fields

```python
# Step 1: Arch detection → recipe.arch_map
# Step 2: Platform check → recipe.install per platform
# Step 3: GitHub API fetch → recipe.install.binary.type = "github_release"
# Step 4: Asset matching → recipe.install.binary.asset_pattern
# Step 5: Download → binary installer engine
# Step 6: Extract → recipe.install.binary.extract = "tar"
# Step 7: Install to dir → recipe.install.binary.install_dir
# Step 8: chmod → binary installer engine (automatic)
# Step 9: PATH → binary installer engine (automatic)
# Step 10: Verify → recipe.verify
```

Every step maps cleanly to existing recipe fields or the
binary installer pattern from domain-binary-installers.

---

## Edge Cases

| Case | Impact | Handling |
|------|--------|---------|
| MkDocs in venv vs global | Wrong pip used | `venv_aware: True` → use venv pip |
| Hugo: no GitHub API access | Can't fetch latest version | Fallback to snap or brew |
| Docusaurus: no node/npm | Can't install | requires.binaries check → disabled with reason |
| Pages builder already installed | Skip install | verify check → "already installed" |
| Builder version mismatch | Old version in PATH | Update recipe handles upgrade |
| Hugo extended vs regular | Different binary name | Asset pattern tries extended first |
| npm global vs project-local | Different install scope | Docusaurus is project-local |
| Migration: old API still called | Must not break | Backward-compat route (both paths) |

---

## Phase Roadmap

| Phase | Pages install capability |
|-------|------------------------|
| Phase 2 | Separate pages_install.py (current). Works independently. |
| Phase 3 | Add to TOOL_RECIPES. Unified install API. Old code as fallback. |
| Phase 4 | Remove pages_install.py. Full unification. |

---

## Traceability

| Topic | Source |
|-------|--------|
| Separate system problem | scope-expansion §2.18 |
| 3 builders (MkDocs, Docusaurus, Hugo) | pages_install.py |
| Hugo binary installer code | pages_install.py lines 86-170 |
| pip install pattern | pages_install.py lines 58-75 |
| npm install pattern | pages_install.py lines 172-188 |
| SSE event format | pages_install.py (yield dicts) |
| Binary installer recipe pattern | domain-binary-installers |
| pip recipe pattern | domain-package-managers §pip |
| Dynamic version fetch | domain-version-selection §dynamic |
| Phase 3 migration | scope-expansion §2.18 |
