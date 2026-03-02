# Revolution Progress Tracker

> Started: 2026-02-28
> Rule: <500 lines per file. ~700 absolute max exception. SRP. Onion folders.
> Process: Refactor → fix imports → verify → document README per domain.
> **Done = moved + split + imports fixed + app verified + README ≥ 450 lines.**

---

## Status Legend

- ⬜ Not started
- 🔵 Planned (chunk scoped)
- 🟡 In progress
- 🟢 Complete (structure + imports + README)
- 🏗️ Structure done, README missing or below standard
- ⏸️ Blocked / Parked

---

## Chunk 1 — Recent Concerns (Priority)

### Backend `core/services/`

| # | Domain | Structure | README | Status |
|---|--------|-----------|--------|--------|
| 1 | **git/** | ✅ `git/` folder, split `gh_ops.py` | ✅ 937 lines ⭐ | 🟢 |
| 2 | **wizard/** | ✅ `wizard/` folder, split `setup.py` by integration | ✅ 579 lines ⭐ | 🟢 |
| 3 | **vault/** | ✅ `vault/` folder | ✅ 628 lines ⭐ | 🟢 |
| 4 | **secrets/** | ✅ `secrets/` folder | ✅ 546 lines ⭐ | 🟢 |
| 5 | **audit/** (existing) | ✅ Split oversized files | ✅ 530 lines | 🟢 |
| 6 | **tool_install/data/** | ✅ All data files split | ✅ recipes 562, handlers 643, failures 455 | 🟢 |
| 7 | **ci/** | ✅ `ci/` folder | ✅ 954 lines ⭐ | 🟢 |

### Routes `ui/web/`

| # | Domain | Structure | README | Status |
|---|--------|-----------|--------|--------|
| 8 | **routes/ package** | ✅ `routes/` package (Option B: domain grouping) | ✅ 469 lines | 🟢 |
| 9 | **routes_audit.py** | ✅ Split into `routes/audit/` (7 modules) | ✅ 507 lines | 🟢 |
| 10 | **routes_integrations.py** | ✅ Evaluated: stays as-is | N/A (covered by routes README) | 🟢 |

### Frontend `templates/scripts/`

| # | Domain | Structure | README | Status |
|---|--------|-----------|--------|--------|
| 11 | **globals/ split** | ✅ 7 files in `globals/` | ✅ 699 lines | 🟢 |
| 12 | **auth/ group** | ✅ 2 files in `auth/` | ✅ 402 lines (small domain exception) | 🟢 |
| 13 | **integrations/ group** | ✅ 13 + `setup/` (10) in `integrations/` | ✅ 590 lines | 🟢 |
| 14 | **secrets/ group** | ✅ 7 files in `secrets/` | ✅ 503 lines | 🟢 |
| 15 | **audit/ group** | ✅ 6 files in `audit/` | ✅ 455 lines | 🟢 |
| 16 | **wizard/ group** | ✅ 9 files in `wizard/` | ✅ 698 lines | 🟢 |
| 17 | **assistant/ group** | ✅ 6 files in `assistant/` | ✅ 533 lines | 🟢 |
| 17b | **content/ group** | ✅ 14 files in `content/` | ✅ 656 lines | 🟢 |
| 17c | **devops/ group** | ✅ 12 files in `devops/` | ✅ 480 lines | 🟢 |

---

## Chunk 2 — Remaining Backend Domains

| # | Domain | Structure | README | Status |
|---|--------|-----------|--------|--------|
| 18 | **docker/** | ✅ `docker/` package (5 modules + shim) | ✅ 784 lines | 🟢 |
| 19 | **k8s/** | ✅ `k8s/` package (19 modules + shim) | ✅ 757 lines ⭐ | 🟢 |
| 20 | **content/** | ✅ `content/` package (9 modules) | ✅ 1,073 lines ⭐ | 🟢 |
| 21 | **terraform/** | ✅ `terraform/` package (3 modules + shims) | ✅ 861 lines ⭐ | 🟢 |
| 22 | **backup/** | ✅ `backup/` package (5 modules + shims) | ✅ 782 lines ⭐ | 🟢 |
| 23 | **devops/** | ✅ `devops/` package (2 modules + shims) | ✅ 478 lines | 🟢 |
| 24 | **security/** | ✅ `security/` package (4 modules + shims) | ✅ 475 lines | 🟢 |
| 25 | **pages/** | ✅ `pages/` package (6 modules + shims) | ✅ 484 lines | 🟢 |
| 26 | **dns/** | ✅ `dns/` package (1 module + shim) | ✅ 476 lines | 🟢 |
| 27 | **docs_svc/** | ✅ `docs_svc/` package (2 modules + shims) | ✅ 809 lines | 🟢 |
| 28 | **quality/** | ✅ `quality/` package (1 module + shim) | ✅ 725 lines | 🟢 |
| 29 | **testing/** | ✅ `testing/` package (2 modules + shims) | ✅ 979 lines | 🟢 |
| 30 | **metrics/** | ✅ `metrics/` package (1 module + shim) | ✅ 836 lines | 🟢 |
| 31a | **env/** | ✅ `env/` package (2 modules + shims) | ✅ 690 lines | 🟢 |
| 31b | **packages_svc/** | ✅ `packages_svc/` package (2 modules + shims) | ✅ 636 lines | 🟢 |
| 31c | **routes → folders** | ✅ All routes in domain folders | ❌ Per-domain READMEs missing | 🏗️ |
| 31d | **CLI → folders** | ✅ All CLI in domain folders | ❌ Per-domain READMEs missing | 🏗️ |
| 31e | **shared cross-cutting** | ~15 cross-cutting files at services root | ⬜ Evaluate in doc sweep | ⬜ |
| 32 | **chat/** (existing) | `chat_refs.py` (1,280), `chat_ops.py` (731) | ⬜ Split first | ⬜ |
| 33 | **generators/** (existing) | `github_workflow.py` (1,081) | ⬜ Split first | ⬜ |

---

## Chunk 3 — Remaining Frontend + Polish

| # | Domain | Structure | README | Status |
|---|--------|-----------|--------|--------|
| 34 | **content/ group** | ~~duplicate of #17b~~ | Done in Chunk 1 | 🟢 |
| 35 | **devops/ group** | ~~duplicate of #17c~~ | Done in Chunk 1 | 🟢 |
| 36 | **debug/ group** | `_debugging.html` (1,145), `_stage_debugger.html` (702) | ⬜ Split first | ⬜ |
| 37 | **CSS split** | `admin.css` (5,948) single file | ⬜ | ⬜ |
| 38 | **Tests follow** | Large test files mirror old paths | ⬜ | ⬜ |
| 39 | **Stale docs** | `docs/ARCHITECTURE.md` etc. outdated | ⬜ | ⬜ |

---

## Completion Summary

| Chunk | Items | 🟢 Done | 🏗️ Structure only | ⬜ Not started |
|-------|-------|---------|-------------------|---------------|
| Chunk 1 (Recent Concerns) | 19 | 19 | 0 | 0 |
| Chunk 2 (Remaining Backend) | 18 | 15 | 2 | 3 |
| Chunk 3 (Remaining FE + Polish) | 6 | 2 | 0 | 4 |
| **Total** | **43** | **36** | **2** | **7** |

### README Queue (in order)

Items with structure done but README missing or below standard:

**Missing READMEs (❌):**
1. ~~globals/~~ ✅ 699 lines — done
2. auth/ (frontend)
3. integrations/ (frontend)
4. secrets/ (frontend)
5. audit/ (frontend scripts)
6. wizard/ (frontend)
7. assistant/ (frontend)
8. content/ (frontend)
9. devops/ (frontend)
10. routes/audit/ (route domain)
11. ~~content/ (backend)~~ ✅ 1,073 lines — gold standard (rewritten)
12. ~~terraform/ (backend)~~ ✅ 861 lines — gold standard (rewritten)
13. ~~backup/ (backend)~~ ✅ 782 lines — gold standard (rewritten)
14. ~~devops/ (backend)~~ ✅ 478 lines — done
15. ~~security/ (backend)~~ ✅ 475 lines — done
16. ~~pages/ (backend)~~ ✅ 484 lines — done
17. ~~dns/ (backend)~~ ✅ 476 lines — done
18. ~~docs_svc/ (backend)~~ ✅ 809 lines — done (gold)
19. ~~quality/ (backend)~~ ✅ 725 lines — done (gold)
20. ~~testing/ (backend)~~ ✅ 979 lines — done (gold)
21. ~~metrics/ (backend)~~ ✅ 836 lines — done (gold)
22. ~~env/ (backend)~~ ✅ 690 lines — done (gold)
23. ~~packages_svc/ (backend)~~ ✅ 636 lines — done (gold)
24. routes per-domain (31c)
25. CLI per-domain (31d)

**At minimum bar (450+) — candidates for gold-standard upgrade (700+):**
26. ~~k8s/~~ ✅ 757 lines — gold standard
27. ~~secrets/~~ ✅ 546 lines — gold standard
28. ~~docker/~~ ✅ 784 lines — gold standard
29. ~~git/~~ ✅ 937 lines — gold standard
30. ~~ci/~~ ✅ 954 lines — gold standard
31. ~~vault/~~ ✅ 628 lines — gold standard
32. ~~wizard/~~ ✅ 579 lines — gold standard
33. ~~routes/ top-level~~ ✅ 343 lines — services/README.md (lower standard ok)
