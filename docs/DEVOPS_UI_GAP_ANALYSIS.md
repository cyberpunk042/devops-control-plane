# DevOps UI — Complete Gap Analysis

**Date:** 2026-02-12  
**Last Updated:** 2026-02-12 13:03  
**Status:** 🟡 IN PROGRESS — Phase 1, 2 & 3 complete, Phase 4-5 remaining  
**⚠️ Note:** Status markers below may be stale — significant work done since Feb 12.

---

## Executive Summary

The DevOps Control Plane has **26 core service files** totaling thousands of lines
of sophisticated backend logic. Routes exist for all of them. **The UI exposes
a small fraction of this capability.** Four entire domains have **ZERO** UI
presence. The tabs that do exist lack per-card caching, per-card refresh,
and surface only a subset of available actions.

---

## 1. Current UI Architecture

### Tabs Present
| Tab | Script | Card Count | Has Caching? | Has Per-Card Refresh? | Has Global Refresh? |
|-----|--------|------------|-------------|----------------------|---------------------|
| Dashboard | `_dashboard.html` | N/A (widgets) | ❌ | ❌ | ❌ |
| Integrations | `_integrations.html` | 5 (Git, GitHub, CI/CD, Docker, Pages) | ✅ shared | ✅ per-card | ✅ Refresh All |
| DevOps | `_devops.html` | 9 (Security, Testing, Quality, Packages, Env, Docs, K8s, Terraform, DNS) | ✅ shared | ✅ per-card | ✅ Refresh All |
| Secrets | `_secrets.html` | N/A | ❌ | ❌ | ❌ |
| Content | `_content.html` | N/A | ❌ | ❌ | ❌ |
| Commands | `_commands.html` | N/A | ❌ | ❌ | ❌ |

### Cross-Cutting Issues (remaining)
- ~~**No per-card caching.**~~ ✅ FIXED — shared `cardCached`/`cardStore` in `_globals.html`
- ~~**No per-card refresh.**~~ ✅ FIXED — every card has 🔄 button + `cardRefresh()` helper
- ~~**No "last updated" per card.**~~ ✅ FIXED — `data-cache-key` + `_tickCardAges()` every 5s
- **No loading skeleton.** Just a spinner dot, no structural placeholder.
- ~~**Integrations tab: no caching at all.**~~ ✅ FIXED — uses shared cache

---

## 2. Core Services → Routes → UI Mapping

### ✅ FORMERLY MISSING — NOW IMPLEMENTED

#### `env_ops.py` — Environment & IaC (555 lines) ✅ DONE
**Route file:** `routes_infra.py` — 8 endpoints registered, **8 used in UI** (Environment card)

| API Endpoint | Method | UI Exposure |
|---|---|---|
| `/infra/status` | GET | ✅ Card status loader |
| `/infra/env/vars` | GET | ✅ Variables modal |
| `/infra/env/diff` | GET | ✅ Diff modal |
| `/infra/env/validate` | GET | ✅ Validate modal |
| `/infra/env/generate-example` | POST | ✅ Gen .env.example button |
| `/infra/env/generate-env` | POST | ✅ Gen .env button |
| `/infra/iac/resources` | GET | ✅ IaC Resources modal |

#### `quality_ops.py` — Code Quality (513 lines) ✅ DONE
**Route file:** `routes_quality.py` — 7 endpoints registered, **6 used in UI** (Quality card)

| API Endpoint | Method | UI Exposure |
|---|---|---|
| `/quality/status` | GET | ✅ Card status loader |
| `/quality/lint` | POST | ✅ Lint runner modal (with auto-fix) |
| `/quality/typecheck` | POST | ✅ Typecheck runner modal |
| `/quality/test` | POST | ✅ Test runner modal |
| `/quality/format` | POST | ✅ Format runner modal (with auto-fix) |
| `/quality/generate/config` | POST | ✅ Generate Config modal |

#### `package_ops.py` — Package Management (653 lines) ✅ DONE
**Route file:** `routes_packages.py` — 6 endpoints registered, **6 used in UI** (Packages card)

| API Endpoint | Method | UI Exposure |
|---|---|---|
| `/packages/status` | GET | ✅ Card status loader |
| `/packages/outdated` | GET | ✅ Outdated modal |
| `/packages/audit` | GET | ✅ Security Audit modal |
| `/packages/list` | GET | ✅ Package List modal |
| `/packages/install` | POST | ✅ Install button (toast) |
| `/packages/update` | POST | ✅ Update button (toast) |

### 🔴 STILL MISSING FROM UI

*(None — all 4 previously missing services are now implemented!)*

---

### 🟡 PARTIALLY EXPOSED — DevOps Tab

#### `security_ops.py` (889 lines) — via `routes_security_scan.py`
| API Endpoint | Core Function | In UI? | Card Actions |
|---|---|---|---|
| `/security/status` | combined scan+posture | ✅ | Card loads this |
| `/security/scan` | `scan_secrets()` | ✅ | 🔍 Scan button |
| `/security/files` | `detect_sensitive_files()` | ✅ | 📄 Sensitive Files modal |
| `/security/gitignore` | `gitignore_analysis()` | ✅ | 📋 .gitignore modal |
| `/security/posture` | `security_posture()` | ✅ | Included in /status |
| `/security/generate/gitignore` | `generate_gitignore()` | ✅ | ⚙️ Generate button |

**Previously missing, now fixed:** ✅ Per-card refresh button, ✅ per-card cache with age indicator.

#### `testing_ops.py` (751 lines) — via `routes_testing.py`
| API Endpoint | Core Function | In UI? | Card Actions |
|---|---|---|---|
| `/testing/status` | `testing_status()` | ✅ | Card loads this |
| `/testing/inventory` | `test_inventory()` | ✅ | 📋 Inventory modal |
| `/testing/run` | `run_tests()` | ✅ | ▶️ Run button (toast) |
| `/testing/coverage` | `test_coverage()` | ✅ | 📊 Coverage button (toast) |
| `/testing/generate/template` | `generate_test_template()` | ✅ | ⚙️ Generate Template modal |

**Previously missing, now fixed:** ✅ Per-card refresh, ✅ cache indicator.

#### `docs_ops.py` (680 lines) — via `routes_docs.py`
| API Endpoint | Core Function | In UI? | Card Actions |
|---|---|---|---|
| `/docs/status` | `docs_status()` | ✅ | Card loads this |
| `/docs/coverage` | `docs_coverage()` | ✅ | 📊 Coverage modal |
| `/docs/links` | `check_links()` | ✅ | 🔗 Check Links (toast) |
| `/docs/generate/changelog` | `generate_changelog()` | ✅ | 📝 Gen Changelog (toast) |
| `/docs/generate/readme` | `generate_readme()` | ✅ | 📄 Gen README (toast) |

**Previously missing, now fixed:** ✅ Per-card refresh, ✅ cache indicator.

#### `k8s_ops.py` (784 lines) — via `routes_k8s.py`
| API Endpoint | Core Function | In UI? | Card Actions |
|---|---|---|---|
| `/k8s/status` | `k8s_status()` | ✅ | Card loads this |
| `/k8s/validate` | `validate_manifests()` | ✅ | ✅ Validate (toast) |
| `/k8s/cluster` | `cluster_status()` | ✅ | ☸️ Cluster modal |
| `/k8s/resources` | `get_resources()` | ✅ | 📦 Resources modal |
| `/k8s/generate/manifests` | `generate_manifests()` | ✅ | 📄 Generate modal |

**Previously missing, now fixed:** ✅ Per-card refresh, ✅ cache indicator.

#### `terraform_ops.py` (688 lines) — via `routes_terraform.py`
| API Endpoint | Core Function | In UI? | Card Actions |
|---|---|---|---|
| `/terraform/status` | `terraform_status()` | ✅ | Card loads this |
| `/terraform/validate` | `terraform_validate()` | ✅ | ✅ Validate (toast) |
| `/terraform/plan` | `terraform_plan()` | ✅ | 📋 Plan (toast) |
| `/terraform/state` | `terraform_state()` | ✅ | 📦 State modal |
| `/terraform/workspaces` | `terraform_workspaces()` | ✅ | 🗂️ Workspaces modal |
| `/terraform/generate` | `generate_terraform()` | ✅ | 🏗️ Generate modal |

**Previously missing, now fixed:** ✅ Per-card refresh, ✅ cache indicator.

#### `dns_cdn_ops.py` (549 lines) — via `routes_dns.py`
| API Endpoint | Core Function | In UI? | Card Actions |
|---|---|---|---|
| `/dns/status` | `dns_cdn_status()` | ✅ | Card loads this |
| `/dns/lookup/<d>` | `dns_lookup()` | ✅ | 🔍 Lookup modal |
| `/dns/ssl/<d>` | `ssl_check()` | ✅ | 🔒 SSL Check modal |
| `/dns/generate` | `generate_dns_records()` | ✅ | 🌐 Generate modal |

**Previously missing, now fixed:** ✅ Per-card refresh, ✅ cache indicator.

---

### ✅ FIXED — Integrations Tab

All 5 cards now have shared caching, per-card refresh buttons, and age indicators:
- `git_ops.py` → `routes_integrations.py` — ✅ cached + refresh
- `ci_ops.py` → `routes_ci.py` — ✅ cached + refresh
- `docker_ops.py` → `routes_docker.py` — ✅ cached + refresh
- `pages_engine.py` → `routes_pages.py` — ✅ cached + refresh
- Refresh All button in tab header — ✅

---

## 3. Required Infrastructure (Cross-Cutting)

Before adding any new cards, these patterns must be established:

### A. Per-Card Cache
```javascript
// Shared cache infrastructure (goes in _globals.html or _boot.html)
const _cardCache = {};
const _CARD_TTL = 120_000; // 2 minutes

function cardCached(key) {
    const c = _cardCache[key];
    return c && (Date.now() - c.ts < _CARD_TTL) ? c.data : null;
}
function cardStore(key, data) {
    _cardCache[key] = { data, ts: Date.now() };
}
function cardInvalidate(key) { delete _cardCache[key]; }
function cardAge(key) {
    const c = _cardCache[key];
    return c ? Math.round((Date.now() - c.ts) / 1000) : null;
}
```

### B. Per-Card Refresh Button
Every card header should include a refresh icon:
```html
<div class="card-header">
    <span class="card-title">🔐 Security</span>
    <div style="display:flex;align-items:center;gap:0.4rem">
        <span class="card-age" id="devops-security-age" style="font-size:0.64rem;color:var(--text-muted)"></span>
        <button class="btn-icon" onclick="cardInvalidate('security');loadSecurityCard()"
                title="Refresh this card" style="font-size:0.7rem;cursor:pointer;background:none;border:none;color:var(--text-muted)">🔄</button>
        <span class="status-badge" id="devops-security-badge">—</span>
    </div>
</div>
```

### C. Card Age Indicator
Each card should display "Updated Xs ago" that ticks:
```javascript
function updateCardAges() {
    for (const [key, entry] of Object.entries(_cardCache)) {
        const el = document.getElementById(`devops-${key}-age`) ||
                   document.getElementById(`int-${key}-age`);
        if (el) {
            const secs = Math.round((Date.now() - entry.ts) / 1000);
            el.textContent = secs < 60 ? `${secs}s ago` : `${Math.round(secs/60)}m ago`;
        }
    }
}
setInterval(updateCardAges, 5000);
```

---

## 4. Implementation Plan

### Phase 1: Cross-Cutting Infrastructure ✅ COMPLETE
1. ✅ Moved cache functions to `_globals.html` (shared by ALL tabs)
2. ✅ Updated `_tab_devops.html` — per-card refresh + age for all 9 cards
3. ✅ Updated `_tab_integrations.html` — per-card refresh + age for all 5 cards
4. ✅ Updated `_devops.html` — uses shared cache, Refresh All
5. ✅ Updated `_integrations.html` — uses shared cache, Refresh All

### Phase 2: Missing DevOps Cards ✅ COMPLETE
6. ✅ **📦 Packages card** — status, outdated modal, audit modal, list modal, install, update
7. ✅ **🔧 Quality card** — status, lint/typecheck/format/test runner modals (with auto-fix), gen config modal
8. ✅ **⚙️ Environment card** — status, vars modal, diff modal, validate modal, IaC resources modal, gen .env/.env.example

### Phase 3: Dashboard Health Score ✅ COMPLETE
9. ✅ **📊 Project Health widget** — score circle (SVG), grade, per-domain probe bars, top recommendations
10. ✅ Wired into boot sequence and dashboard tab switch, uses shared cache

### Phase 4: Integrate IaC into existing Terraform card (or new card)
11. Merge `iac_status` + `iac_resources` into the Terraform/Infra card

### Phase 5: Operability Pass
12. All toast-only actions (validate, plan, lint, etc.) get detail modals
13. All modals get error states and loading spinners
14. All action buttons get disabled state during execution

---

## 5. Priority Order

| Priority | Item | Impact |
|----------|------|--------|
| P0 | Shared cache infrastructure | Fixes stale data and redundant fetches everywhere |
| P0 | Per-card refresh + age | Gives user control and visibility |
| P1 | Project Health widget (Dashboard) | Single most valuable overview, aggregates everything |
| P1 | Packages card | Security audit + outdated = critical operability |
| P1 | Quality card | Lint/typecheck/format = daily developer workflow |
| P2 | Environment card | .env management = setup/config workflow |
| P2 | IaC integration | Expands infrastructure observability |
| P3 | Integrations tab caching | Consistency |
| P3 | Detail modals for toast-only actions | Observability |
