# Tool Health Sweep — Plan

> Created: 2026-02-18  
> Status: **Phase 1 in progress**  
> Supersedes: `.gemini/plans/tool-health-dashboard.md` (dashboard piece parked)

---

## Scope

Every place a tool is checked, detected, or needed:
- Show clear status (available / missing)
- Offer install action (using existing `tool_install.py` recipes)
- No silent failures — if something is missing, the user SEES it

Dashboard redesign is **PARKED** (separate task).

---

## Phase 1: Unify tool detection (backend)

### 1a. Central `_TOOLS` list in `l0_detection.py`

**Current (26 tools):**
python3, pip, node, npm, npx, go, cargo, rustc, docker, docker-compose,
kubectl, terraform, helm, git, gh, ruff, mypy, pytest, black, eslint,
prettier, ffmpeg, gzip, curl, jq, make

**To add (10 tools used elsewhere but not detected):**
| Tool | CLI | Used where |
|---|---|---|
| pip-audit | pip-audit | package_actions.py, wizard_ops.py |
| bandit | bandit | wizard_ops.py |
| safety | safety | wizard_ops.py |
| dig | dig | dns_cdn_ops.py |
| openssl | openssl | dns_cdn_ops.py |
| rsync | rsync | pages_builders/raw.py |
| skaffold | skaffold | k8s_wizard_detect.py |
| cargo-outdated | cargo-outdated | package_actions.py |
| cargo-audit | cargo-audit | package_actions.py |
| trivy | trivy | tool_install.py (has recipe) |

Also: add `install_recipe` field to each tool entry (keyed to tool_install.py).
Also: add `category` field for grouping in UI.

### 1b. Fix pip detection

- [x] Already done: `sys.executable -m pip` in package_ops.py
- [ ] Also fix in l0_detection.py `_detect_tools()` for pip

### 1c. Expose a `/api/tools/status` endpoint

Returns all tools with availability + install recipe info.
Cards can reference this centrally.

---

## Phase 2: Cards return `missing_tools` (backend)

Each card's status function gains:
```python
"missing_tools": [
    {"id": "kubectl", "label": "kubectl", "install_recipe": "sudo"},
    ...
]
```

Cards to update:
- [ ] docker_detect.py → docker_status()
- [ ] k8s_detect.py → k8s_status()  (kubectl, helm)
- [ ] terraform_ops.py → terraform_status()
- [ ] dns_cdn_ops.py → dns_cdn_status() (dig, openssl)
- [ ] quality_ops.py → quality_status() (ruff, mypy, eslint, etc.)
- [ ] package_ops.py → package_status_enriched() (pip, npm, cargo, etc.)
- [ ] security_ops.py → (pip-audit, bandit, trivy, safety)
- [ ] testing_ops.py → testing_status() (pytest)
- [ ] ci_ops.py → ci_status() (gh)
- [ ] git_ops.py → (git, gh)

---

## Phase 3: UI — Tab cards show missing tools with install buttons

Every DevOps/Infra tab card:
- When `missing_tools` is present and non-empty, show a banner
- Banner has install buttons that call `/api/tools/install`
- Pattern: `⚠️ kubectl not installed — [Install]`

Tabs to update:
- [ ] _tab_docker.html / _docker.html
- [ ] _tab_k8s.html / _k8s.html
- [ ] _tab_terraform.html / _terraform.html
- [ ] _tab_dns.html / _dns.html
- [ ] _tab_quality.html / _quality.html
- [ ] _tab_packages.html / _packages.html
- [ ] _tab_security.html / _security.html
- [ ] _tab_testing.html / _testing.html
- [ ] _tab_git.html / _git.html
- [ ] _tab_ci.html / _ci.html

---

## Phase 4: UI — Setup Wizard tool status + install

The wizard already detects tools (wizard_ops.py line 38-53) but:
- Align with the unified `_TOOLS` list
- Show install buttons in the wizard UI for each missing tool
- Especially in integration setup modals (K8s → helm/skaffold, etc.)

---

## Phase 5: Dashboard redesign (PARKED)

Separate task. Will add tool health card to dashboard.
