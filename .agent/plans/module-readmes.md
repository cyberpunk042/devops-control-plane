# Module README Creation Plan

> Created: 2026-03-04
> Standard: `.agent/workflows/readme-standard.md` (450+ lines, 8 required sections)

## Overview

5 configured modules need root-level README.md files.
Each README enables the audit-data directive to render module-level health cards.

## Module Order (by complexity, smallest first)

| # | Module | Path | .py files | Dirs | Sub-READMEs | Est. chunks |
|---|--------|------|-----------|------|-------------|-------------|
| 1 | adapters | `src/adapters` | 14 | 4 | 0 | 2 (analysis + write) |
| 2 | docs | `docs` | 0 | 5 | 0 | 2 (analysis + write) |
| 3 | cli | `src/ui/cli` | 56 | 20 | 19 | 3 (analysis × 2 + write) |
| 4 | web | `src/ui/web` | 115 | 4 | 38 | 4 (analysis × 3 + write) |
| 5 | core | `src/core` | 435 | 11 | 34 | 5+ (analysis × 4 + write) |

## Per-Module Process

Each module follows this chunked workflow:

### Chunk A: Analysis
- Read every file outline in the module root
- Read every direct child's purpose
- Map the dependency graph (grep imports)
- Identify consumers (who imports from this module)
- Collect line counts, function counts

### Chunk B: Writing (may split into B1/B2 for large modules)
- Write all 8 required sections per readme-standard
- Verify ≥ 450 lines
- Verify all function/file references match source

### Chunk C: Validation (optional, for complex modules)
- Cross-check against existing sub-module READMEs
- Verify no fabricated content

## Progress

| Module | Analysis | Writing | Validation | Lines | Status |
|--------|----------|---------|------------|-------|--------|
| adapters | ✅ | ✅ | — | 682 | Complete |
| docs | ✅ | ✅ | — | 642 | Complete |
| cli | ✅ | ✅ | — | 711 | Complete |
| web | ✅ | ✅ | — | 594 | Complete |
| core | ✅ | ✅ | — | 664 | Complete |
