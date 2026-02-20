# UI & API Surface Audit — Honest Assessment

> Restarted: 2026-02-18
> Previous version was garbage — optimistic, marked things as done based on code existing on disk.
> This version is pessimistic. If it's not proven working end-to-end, it's NOT DONE.

---

## Ground Truth (from the user, not from code exploration)

| Integration | Real Status | Notes |
|-------------|-------------|-------|
| **Docker** | 🟡 Partial | Some detection + generation works, not fully integrated |
| **Kubernetes** | 🟡 Partial (biggest piece) | Most work done of any domain, but still not finished |
| **Skaffold** | 🟡 Partial | Tied to K8s, detection exists |
| **Helm** | 🔴 Never on the map | No standalone integration, no service files |
| **CI/CD** | 🔴 Never touched | Routes/templates exist on disk but never integrated |
| **Terraform** | 🔴 Never touched | Routes/templates exist on disk but never integrated |
| **DNS/CDN** | 🔴 Never touched | Routes/templates exist on disk but never integrated |

**"Code exists on disk" ≠ "integrated".** Files may have been scaffolded but never wired, tested, or finished.

---

## Audit Format

For each integration, answer:
1. What ACTUALLY works today that the user can see and use?
2. What exists as code but is NOT functional/integrated?
3. What's completely missing?

---

## 1. Docker

### What works:
- Detection card shows Dockerfile, docker-compose, .dockerignore presence
- Generate modal can produce Dockerfiles for 10 stacks
- Docker Setup Wizard (multi-step) walks through configuration
- Write-to-disk flow works (overwrite always true)

### Fixed during this audit (2026-02-17 + 2026-02-18):
- Dockerignore detection display (was missing from card)
- Dockerfile warning display (card wasn't reading `warnings`)
- Compose warning display (card wasn't reading `warnings`)
- **Removed crude Compose Wizard modal** — compose button now opens the real Docker Setup Wizard
- **Removed dead compose wizard code** (~340 lines) from `_integrations_docker_compose.html`
- **Removed hide-when-exists conditions** on generate toolbar — all 3 buttons always visible
- **Replaced raw textarea volumes** with structured rows (Source : Mount | rw/ro | ✕)
- **Replaced single-port number** with structured port mappings (Host → Container | tcp/udp | ✕)
- **Cleaned up Depends-on** checkboxes as pill-shaped chips with hover/checked styling
- Button consistency: Add port / Add volume now match Add variable style

### Remaining gaps:
- Card's quick Dockerfile generate modal doesn't pass `base_image` (only the Setup Wizard does)
- No UI toggle for overwrite vs skip — both paths hardcode `overwrite: true`
- Registry field: backend `setup_docker()` accepts it, wizard quick form doesn't offer it
- Preview pages need full redo (noted, not priority)

---

## 2. Kubernetes

### What works (most advanced integration):
- K8s integration card: detection, live tabs (9), action toolbar, generate modals
- K8s Setup Wizard: 9 files, 362KB — detect → cluster → containers → app services → infra → volumes → review
- Modals: Apply, Scale, Logs, Describe, Delete, Generate Manifests, Helm Install/Upgrade, Manifest Wizard

### Fixed during this audit (2026-02-17):
- `deployment_strategy`, `deployment_readiness`, `tool_availability` shown in status grid
- `infra_services` shown in detection list
- `secret_safety` warnings displayed
- `cluster_type` shown in Cluster live tab

### Gaps identified:
- ~~🔴 **No Skaffold setup wizard**~~ → ✅ Fixed 2026-02-18: Full Skaffold config panel in K8s wizard (deploy method, tag policy, per-profile config cards, port-forward, file sync, server-side apply, post-deploy verify, lifecycle hooks)
- ~~🔴 **No Helm setup wizard**~~ → ✅ Fixed 2026-02-18: Full Helm config panel in K8s wizard (chart name/dir/version, app version, description, env values, helmignore)
- ~~Neither `skaffold` nor `helm` appear in the setup wizard dispatch map~~ → They don't need to — they're configured *inside* the K8s wizard's infrastructure step, not as standalone wizards

### NOT verified:
- Whether any of this actually renders correctly in the browser
- Whether live cluster operations work
- Whether the wizard produces valid manifests

---

## 3. Skaffold

### Status: � Integrated (as part of K8s wizard)

- Detection: `GET /k8s/skaffold/status` → live tab in K8s card
- CLI install flow in wizard (detects, offers install button)
- **Config panel** (2026-02-18): deploy method (default kustomize), tag policy (5 options), per-profile config cards with pattern detection, port-forward, file sync, server-side apply, post-deploy verify, pre/post deploy hooks
- **Profile pattern detection**: any name containing "local" → local dev features (envsubst, no push, port-forward, file sync). Also detects staging/qa/preprod, prod/production patterns
- **Backend**: `_generate_skaffold()` fully wired — generates `skaffold.yaml` with build artifacts, deploy strategy, profiles, port-forward entries, envsubst hooks, kustomization files
- **Collector**: maps UI fields to backend flat fields (`deployStrategy`, `tagPolicy`, `environments`, `serverSideApply`, `postDeployVerify`, `preDeploy`, `postDeploy`)

---

## 4. Helm

### Status: � Partial (integrated as part of K8s, not standalone)

- **Config panel** (2026-02-18): chart name, chart dir, chart version, app version, description, per-env values toggle, helmignore toggle
- **Backend**: `k8s_helm_generate.py` (515 lines) — generates Chart.yaml, values.yaml, values-{env}.yaml, templates/ (helpers, deployment, service, ingress, configmap, secret, NOTES.txt), .helmignore
- **Wired into setup_k8s()**: called after manifest + skaffold generation
- Helm deploy option in Skaffold locked to Helm chart checkbox state
- K8s card has "⎈ Helm" live tab and Helm install/upgrade/template modals
- `GET /k8s/helm/list`, `/values`, `POST /install`, `/upgrade`, `/template` routes exist

### What's NOT there:
- No standalone Helm integration card (it lives inside K8s)
- No dedicated Helm setup wizard (configured inside K8s wizard)
- These are by design — Helm is a K8s deployment tool, not a separate domain

---

## 5. CI/CD

### Status: � Partial — code wired, expanded 2026-02-18

- **Routes**: `routes_ci.py` (89 lines) — 5 endpoints: status, workflows, coverage, generate CI, generate lint. Blueprint registered.
- **Backend**: `ci_ops.py` (590 lines) — detects 4 CI providers (GitHub Actions, GitLab CI, CircleCI, Jenkins), parses workflows, audits issues, coverage analysis, basic generation
- **Backend**: `ci_compose.py` (545 lines) — cross-domain orchestrator (unified/split strategies), generates test/Docker/K8s/Terraform/DNS jobs
- **Backend**: `wizard_setup.py:setup_ci()` — full workflow generation: per-stack test jobs, Docker build/push, K8s deploy (kubectl/skaffold/helm), multi-environment deploys, overwrite guard
- **Card**: `_integrations_cicd.html` (296 lines) — badge, live tabs (Runs, Workflows, Coverage), trigger dropdown, generate toolbar

### Fixed during this audit (2026-02-18):
- **Expanded setup wizard** from 3-step placeholder to full 5-step wizard:
  1. **Detect**: shows CI providers, workflow count, Docker, K8s, detected stacks
  2. **Pipeline**: test/lint/typecheck/coverage, trigger, branch filter, custom commands (when no stacks)
  3. **Build & Deploy**: Docker build/push (registry, image name), K8s deploy (method selector: kubectl/skaffold/helm with contextual options)
  4. **Environments**: multi-env deploy config with per-env branch, namespace, kubeconfig secret, skaffold profile or values file
  5. **Review**: summary + overwrite toggle
- All wizard data mapped to `setup_ci()` backend field names

### NOT verified:
- Whether the card actually renders in the browser
- Whether live tabs (Runs, Workflows, Coverage) work
- Whether generated ci.yml is valid GitHub Actions YAML
- Whether the `/docker/generate/write` endpoint works for CI files (it's generic but named under Docker)

---

## 6. Terraform

### Status: 🔴 Never touched

- `routes_terraform.py` exists (166 lines)
- `_integrations_terraform.html` exists (303 lines)
- `terraform_ops.py`, `terraform_generate.py`, `terraform_actions.py` exist as core services
- Integration card registered as `int:terraform` in `_INT_CARDS`
- alpha-milestones section 0.6 (lines 2046–2208) has checkboxes

### Reality:
- Code was scaffolded but never integrated end-to-end
- Not tested, not verified, not finished
- Full assessment not started

---

## 7. DNS/CDN

### Status: 🔴 Never touched

- `routes_dns.py` exists (79 lines)
- `dns_cdn_ops.py` exists as core service
- No dedicated integration card in `_INT_CARDS` (Pages card covers some DNS)
- alpha-milestones section 0.7 (lines 2211–2312) has checkboxes

### Reality:
- Code was scaffolded but never integrated end-to-end
- Not tested, not verified, not finished
- Full assessment not started

---

## Next Steps

The only domains with real work are **Docker** and **Kubernetes**. Even those are partial.

Before continuing the detailed subsection audit of any domain, confirm with the user:
1. Which integration to focus on next?
2. What is the priority — finish K8s first since it has the most work?
3. Should we fix gaps as we find them, or document everything first then batch fixes?
