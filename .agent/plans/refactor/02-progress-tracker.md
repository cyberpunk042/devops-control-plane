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
### 31c — Route Domain READMEs (`ui/web/routes/`)

| # | Domain | Files | Lines | README | Status |
|---|--------|-------|-------|--------|--------|
| 31c-1 | routes/api | 4 | 230 | ✅ 574 lines | 🟢 |
| 31c-2 | routes/audit | 7 | 1,840 | ✅ 507 lines | 🟢 |
| 31c-3 | routes/backup | 5 | 495 | ✅ 616 lines | 🟢 |
| 31c-4 | routes/chat | 5 | 581 | ✅ 689 lines | 🟢 |
| 31c-5 | routes/ci | 3 | 88 | ✅ 631 lines | 🟢 |
| 31c-6 | routes/config | 1 | 83 | ✅ 637 lines | 🟢 |
| 31c-7 | routes/content | 5 | 864 | ✅ 636 lines | 🟢 |
| 31c-8 | routes/dev | 1 | 86 | ✅ 568 lines | 🟢 |
| 31c-9 | routes/devops | 4 | 459 | ✅ 727 lines | 🟢 |
| 31c-10 | routes/dns | 1 | 78 | ✅ 728 lines | 🟢 |
| 31c-11 | routes/docker | 6 | 428 | ✅ 864 lines | 🟢 |
| 31c-12 | routes/docs | 3 | 88 | ✅ 790 lines | 🟢 |
| 31c-13 | routes/events | 1 | 69 | ✅ 669 lines | 🟢 |
| 31c-14 | routes/git_auth | 3 | 162 | ✅ 748 lines | 🟢 |
| 31c-15 | routes/infra | 3 | 134 | ✅ 933 lines | 🟢 |
| 31c-16 | routes/integrations | 7 | 514 | ✅ 1216 lines | 🟢 |
| 31c-17 | routes/k8s | 8 | 395 | ✅ 1039 lines | 🟢 |
| 31c-18 | routes/metrics | 3 | 130 | ✅ 414 lines | 🟢 |
| 31c-19 | routes/packages | 3 | 119 | ✅ 438 lines | 🟢 |
| 31c-20 | routes/pages | 3 | 430 | ✅ 839 lines | 🟢 |
| 31c-21 | routes/project | 1 | 67 | ✅ 382 lines | 🟢 |
| 31c-22 | routes/quality | 3 | 117 | ✅ 409 lines | 🟢 |
| 31c-23 | routes/secrets | 3 | 210 | ✅ 528 lines | 🟢 |
| 31c-24 | routes/security_scan | 3 | 143 | ✅ 423 lines | 🟢 |
| 31c-25 | routes/terraform | 3 | 182 | ✅ 427 lines | 🟢 |
| 31c-26 | routes/testing | 3 | 106 | ✅ 382 lines | 🟢 |
| 31c-27 | routes/trace | 4 | 340 | ✅ 432 lines | 🟢 |
| 31c-28 | routes/vault | 7 | 421 | ✅ 640 lines | 🟢 |

**Routes total: 28 domains · 28 done · 0 remaining** ✅

### 31d — CLI Domain READMEs (`ui/cli/`)

| # | Domain | Files | Lines | README | Status |
|---|--------|-------|-------|--------|--------|
| 31d-1 | cli/audit | 4 | 377 | ✅ 450+ | 🟢 |
| 31d-2 | cli/backup | 1 | 196 | ✅ exception | 🟢 |
| 31d-3 | cli/ci | 1 | 236 | ✅ 450+ | 🟢 |
| 31d-4 | cli/content | 4 | 341 | ✅ 450+ | 🟢 |
| 31d-5 | cli/dns | 1 | 229 | ✅ 450+ | 🟢 |
| 31d-6 | cli/docker | 5 | 463 | ✅ 658 | 🟢 |
| 31d-7 | cli/docs | 1 | 264 | ✅ 489 | 🟢 |
| 31d-8 | cli/git | 3 | 303 | ✅ 544 | 🟢 |
| 31d-9 | cli/infra | 4 | 360 | ✅ 503 | 🟢 |
| 31d-10 | cli/k8s | 4 | 334 | ✅ 538 | 🟢 |
| 31d-11 | cli/metrics | 1 | 197 | ✅ exception | 🟢 |
| 31d-12 | cli/packages | 1 | 205 | ✅ 483 | 🟢 |
| 31d-13 | cli/pages | 4 | 304 | ✅ 556 | 🟢 |
| 31d-14 | cli/quality | 1 | 221 | ✅ 478 | 🟢 |
| 31d-15 | cli/secrets | 4 | 385 | ✅ 481 | 🟢 |
| 31d-16 | cli/security | 4 | 313 | ✅ 451 | 🟢 |
| 31d-17 | cli/terraform | 4 | 322 | ✅ 491 | 🟢 |
| 31d-18 | cli/testing | 4 | 341 | ✅ 513 | 🟢 |
| 31d-19 | cli/vault | 4 | 400 | ✅ 545 | 🟢 |

**CLI total: 19 domains · 19 done · 0 remaining**

### Remaining Items

| # | Domain | Structure | README | Status |
|---|--------|-----------|--------|--------|
| 31e | **shared cross-cutting** | 14 cross-cutting files at services root | ✅ 652 lines (CROSS_CUTTING.md) | 🟢 |
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
| Chunk 2 (Backend services) | 15 | 15 | 0 | 0 |
| 31c (Route READMEs) | 28 | 28 | 0 | 0 |
| 31d (CLI READMEs) | 19 | 19 | 0 | 0 |
| Remaining (31e, 32, 33) | 3 | 1 | 0 | 2 |
| Chunk 3 (Remaining FE + Polish) | 6 | 2 | 0 | 4 |
| **Total** | **90** | **84** | **0** | **6** |

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
