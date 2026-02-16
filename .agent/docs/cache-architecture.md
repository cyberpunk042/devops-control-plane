---
description: Cache architecture — the three separate cache systems and how they relate
---

# Cache Architecture

## THREE SEPARATE CACHE SYSTEMS — DO NOT CONFUSE THEM

### 1. `.pages/` — Pages Build Cache (disk)

- **Purpose**: Build output for GitHub Pages (Docusaurus, MkDocs, etc.)
- **Location**: `<project_root>/.pages/`
- **Managed by**: `pages_engine.py` (builders)
- **Contains**: Built static site files (HTML, JS, CSS)
- **Has NOTHING to do with the UI dashboard card caching**

### 2. `.state/devops_cache.json` — Server-Side Card Cache (disk)

- **Purpose**: Caches the computed results of DevOps/integration cards so the server doesn't re-scan the filesystem on every request
- **Location**: `<project_root>/.state/devops_cache.json`
- **Managed by**: `devops_cache.py` (`get_cached`, `_load_cache`, `_save_cache`)
- **Keys**: `security`, `testing`, `quality`, `packages`, `env`, `docs`, `k8s`, `terraform`, `dns`, `git`, `github`, `ci`, `docker`, `pages`, `gh-pulls`, `gh-runs`, `gh-workflows`, etc.
- **The `pages` key here** stores the result of `list_segments` API compute (segments + build_status) — it is NOT the Pages build output
- **Invalidation**: mtime-based (watches specific files per card) or manual bust via `/devops/cache/bust`

### 3. `sessionStorage` — Browser-Side Card Cache (browser)

- **Purpose**: Avoids redundant API calls within a browser session (10-min TTL)
- **Location**: Browser `sessionStorage` under `_cc:<key>` prefix
- **Managed by**: `_globals.html` (`cardCached`, `cardStore`, `cardInvalidate`)
- **Shape**: Whatever the card loader stores — varies per card
- **The `pages` key in sessionStorage** is stored by `loadPagesCard()` as `{ segData, bdData }` (wrapper around two API calls: `/pages/segments` + `/pages/builders`)
- **Conflict risk**: The SSE event stream (`_event_stream.html`) also writes to sessionStorage via `storeSet` → `cardStore`, but it writes RAW server data (from cache system #2), which has a DIFFERENT shape than what `loadPagesCard` expects

## KEY RULES

1. **`.pages/` is build output. Not a UI cache. Never treat it as one.**
2. The `"pages"` key exists in BOTH server cache (#2) and browser cache (#3) but they serve completely different purposes
3. Server cache (#2) stores raw computed data; browser cache (#3) may wrap it differently per card
4. SSE pushes from server cache (#2) into browser cache (#3) — this can corrupt entries if the card uses a non-standard wrapper shape
