# Feature Gap Analysis: DevOps & Integrations Tabs

## Overview

**217 total API endpoints** exist across the project.  
Below is a card-by-card analysis of what each card currently exposes vs what backend APIs support.

---

## INTEGRATIONS TAB (7 cards)

### 1. 🔀 Git Card
| Feature | Status | API | Notes |
|---------|--------|-----|-------|
| Branch + status | ✅ Exposed | `GET /git/status` | |
| Changed files list | ✅ Exposed | `GET /git/status` | |
| Commit modal | ✅ Has modal | `POST /git/commit` | |
| Pull | ✅ Button | `POST /git/pull` | |
| Push | ✅ Button | `POST /git/push` | |
| Log modal | ✅ Has modal | `GET /git/log` | |
| **⬜ Diff viewer** | ❌ Missing | N/A | Could show file diffs in modal |
| **⬜ Stash support** | ❌ Missing | N/A | No backend yet |
| **⬜ Branch switch** | ❌ Missing | N/A | No backend yet |

**Git: 6/6 existing APIs exposed. Well covered.**

---

### 2. 🐙 GitHub Card
| Feature | Status | API | Notes |
|---------|--------|-----|-------|
| Auth status | ✅ Exposed | `GET /integrations/gh/status` | |
| Pull requests | ✅ Live panel | `GET /gh/pulls` | |
| **⬜ Environments** | ❌ Missing | `GET /gh/environments` | Backend exists, not shown |
| **⬜ Create environment** | ❌ Missing | `POST /gh/environment/create` | Backend exists, not shown |
| **⬜ GitHub Secrets** | ❌ Missing | `GET /gh/secrets` | Backend exists, not shown |
| **⬜ Auto-detect** | ❌ Missing | `GET /gh/auto` | Backend exists, not shown |
| **⬜ Push secrets** | ❌ Missing | `POST /secrets/push` | Backend exists, not in GH card |

**GitHub: 2/7 APIs exposed. 5 features missing.**

---

### 3. 🔄 CI/CD Card
| Feature | Status | API | Notes |
|---------|--------|-----|-------|
| Workflow runs | ✅ Exposed | `GET /gh/actions/runs` | |
| Workflows list | ✅ Exposed | `GET /gh/actions/workflows` | |
| Dispatch workflow | ✅ Button | `POST /gh/actions/dispatch` | |
| **⬜ CI status overview** | ❌ Missing | `GET /ci/status` | Backend exists, not shown |
| **⬜ CI workflows config** | ❌ Missing | `GET /ci/workflows` | Backend exists, not shown |
| **⬜ Coverage report** | ❌ Missing | `GET /ci/coverage` | Backend exists, not shown |
| **⬜ Generate CI config** | ❌ Missing | `POST /ci/generate/ci` | Backend exists, needs modal |
| **⬜ Generate lint config** | ❌ Missing | `POST /ci/generate/lint` | Backend exists, needs modal |

**CI/CD: 3/8 APIs exposed. 5 features missing.**

---

### 4. 🐳 Docker Card
| Feature | Status | API | Notes |
|---------|--------|-----|-------|
| Status + version | ✅ Exposed | `GET /docker/status` | |
| Containers panel | ✅ Live panel | `GET /docker/containers` | |
| Images panel | ✅ Live panel | `GET /docker/images` | |
| Compose status panel | ✅ Live panel | `GET /docker/compose/status` | |
| Stats panel | ✅ Live panel | `GET /docker/stats` | |
| Start/Stop/Restart | ✅ Actions | `POST /docker/up|down|restart` | |
| Build | ✅ Actions | `POST /docker/build` | |
| Prune | ✅ Actions | `POST /docker/prune` | |
| **⬜ Container logs** | ❌ Missing | `GET /docker/logs` | Backend exists, needs modal |
| **⬜ Generate Dockerfile** | ❌ Missing | `POST /docker/generate/dockerfile` | Backend exists, needs modal |
| **⬜ Generate .dockerignore** | ❌ Missing | `POST /docker/generate/dockerignore` | Backend exists, needs modal |
| **⬜ Generate docker-compose** | ❌ Missing | `POST /docker/generate/compose` | Backend exists, needs modal |
| **⬜ Write generated file** | ❌ Missing | `POST /docker/generate/write` | Backend exists |

**Docker: 8/13 APIs exposed. 5 features missing (all generators + logs).**

---

### 5. ☸ Kubernetes Card
| Feature | Status | API | Notes |
|---------|--------|-----|-------|
| Status + version | ✅ Exposed | `GET /k8s/status` | |
| Pods panel | ✅ Live panel | `_intK8sLive('pods')` | |
| Services panel | ✅ Live panel | `_intK8sLive('services')` | |
| Deployments panel | ✅ Live panel | `_intK8sLive('deployments')` | |
| Cluster panel | ✅ Live panel | `_intK8sLive('cluster')` | |
| Validate | ✅ Action | `GET /k8s/validate` | |
| **⬜ Generate manifests** | ❌ Missing | `POST /k8s/generate/manifests` | Backend exists, needs modal |
| **⬜ Resource details modal** | ❌ Missing | `GET /k8s/resources` | Backend exists, not in modal |

**K8s: 6/7 APIs exposed. 1 feature missing.**

---

### 6. 🏗 Terraform Card
| Feature | Status | API | Notes |
|---------|--------|-----|-------|
| Status + version | ✅ Exposed | `GET /terraform/status` | |
| State panel | ✅ Live panel | `_intTfLive('state')` | |
| Workspaces panel | ✅ Live panel | `_intTfLive('workspaces')` | |
| Validate | ✅ Action | `POST /terraform/validate` | |
| Plan | ✅ Action | `POST /terraform/plan` | |
| **⬜ Generate TF config** | ❌ Missing | `POST /terraform/generate` | Backend exists, needs modal |

**Terraform: 5/6 APIs exposed. 1 feature missing.**

---

### 7. 📄 Pages Card
| Feature | Status | API | Notes |
|---------|--------|-----|-------|
| Segments + builders | ✅ Full | Multiple | Very well implemented |
| Build / Build All | ✅ SSE stream | Multiple | |
| Merge / Deploy | ✅ Actions | Multiple | |
| Add/Remove/Configure | ✅ Modals | Multiple | |
| Preview | ✅ Actions | Multiple | |
| Features | ✅ Registry | Multiple | |

**Pages: Fully implemented. No gaps.**

---

## DEVOPS TAB (9 cards)

### 8. 🔒 Security Card
| Feature | Status | API | Notes |
|---------|--------|-----|-------|
| Posture summary | ✅ Exposed | `GET /security/posture-summary` | |
| Sensitive files panel | ✅ Live panel | `GET /security/files` | |
| Gitignore analysis | ✅ Live panel | `GET /security/gitignore` | |
| Generate .gitignore | ✅ Action | `POST /security/generate/gitignore` | |
| **⬜ Full security scan** | ❌ Missing | `GET /security/scan` | Backend exists, not in card |
| **⬜ Security posture detail** | ❌ Missing | `GET /security/posture` | Backend exists, not in card |
| **⬜ Security status** | ❌ Missing | `GET /security/status` | Backend exists, not in card |

**Security: 4/7 APIs exposed. 3 features missing.**

---

### 9. 🧪 Testing Card
| Feature | Status | API | Notes |
|---------|--------|-----|-------|
| Status overview | ✅ Exposed | `GET /testing/status` | |
| Run tests | ✅ Action | `POST /testing/run` | |
| Coverage | ✅ Live panel | `POST /testing/coverage` | |
| Inventory | ✅ Live panel | `GET /testing/inventory` | |
| Generate template | ✅ Modal | `POST /testing/generate/template` | |

**Testing: 5/5 APIs exposed. Fully covered.**

---

### 10. 📐 Quality Card
| Feature | Status | API | Notes |
|---------|--------|-----|-------|
| Status overview | ✅ Exposed | `GET /quality/status` | |
| Run category | ✅ Action (modal) | `POST /quality/check|lint|typecheck|test|format` | |
| Generate config | ✅ Modal | `POST /quality/generate/config` | |

**Quality: 7/7 APIs exposed. Fully covered.**

---

### 11. 📦 Packages Card
| Feature | Status | API | Notes |
|---------|--------|-----|-------|
| Status overview | ✅ Exposed | `GET /packages/status` | |
| Outdated | ✅ Live panel | `GET /packages/outdated` | |
| Audit | ✅ Live panel | `GET /packages/audit` | |
| List | ✅ Live panel | `GET /packages/list` | |
| Install | ✅ Action | `POST /packages/install` | |
| Update | ✅ Action | `POST /packages/update` | |

**Packages: 6/6 APIs exposed. Fully covered.**

---

### 12. 🌍 Environment Card
| Feature | Status | API | Notes |
|---------|--------|-----|-------|
| Status overview | ✅ Exposed | `GET /env/card-status` | |
| Environment drift modal | ✅ Modal | Multiple | |
| Activate env | ✅ Action | Multiple | |
| **⬜ Env vars list** | ❌ Missing | `GET /infra/env/vars` | Backend exists, not shown |
| **⬜ Env validation** | ❌ Missing | `GET /infra/env/validate` | Backend exists, not shown |
| **⬜ Env diff** | ❌ Missing | `GET /infra/env/diff` | Backend exists, not shown |
| **⬜ Generate .env.example** | ❌ Missing | `POST /infra/env/generate-example` | Backend exists, needs button |
| **⬜ Generate .env** | ❌ Missing | `POST /infra/env/generate-env` | Backend exists, needs button |
| **⬜ IaC status** | ❌ Missing | `GET /infra/iac/status` | Backend exists, not shown |
| **⬜ IaC resources** | ❌ Missing | `GET /infra/iac/resources` | Backend exists, not shown |
| **⬜ Infra overview** | ❌ Missing | `GET /infra/status` | Backend exists, not shown |

**Environment: 3/11 APIs exposed. 8 features missing!**

---

### 13. 📖 Documentation Card
| Feature | Status | API | Notes |
|---------|--------|-----|-------|
| Status overview | ✅ Exposed | `GET /docs/status` | |
| Coverage report | ✅ Live panel | `GET /docs/coverage` | |
| Link checker | ✅ Live panel | `GET /docs/links` | |
| Generate changelog | ✅ Action | `POST /docs/generate/changelog` | |
| Generate README | ✅ Action | `POST /docs/generate/readme` | |

**Docs: 5/5 APIs exposed. Fully covered.**

---

### 14. ☸ Kubernetes Card (DevOps)
| Feature | Status | API | Notes |
|---------|--------|-----|-------|
| Status overview | ✅ Exposed | `GET /k8s/status` | |
| Validate | ✅ Action | `GET /k8s/validate` | |
| Cluster modal | ✅ Modal | `GET /k8s/cluster` | |
| Resources modal | ✅ Modal | `GET /k8s/resources` | |
| Generate manifests | ✅ Modal | `POST /k8s/generate/manifests` | |

**K8s DevOps: 5/5 APIs exposed. Fully covered.**

---

### 15. 🏗 Terraform Card (DevOps)
| Feature | Status | API | Notes |
|---------|--------|-----|-------|
| Status overview | ✅ Exposed | `GET /terraform/status` | |
| Validate | ✅ Action | `POST /terraform/validate` | |
| Plan | ✅ Action | `POST /terraform/plan` | |
| State | ✅ Live panel | `GET /terraform/state` | |
| Workspaces | ✅ Live panel | `GET /terraform/workspaces` | |
| Generate config | ✅ Modal | `POST /terraform/generate` | |

**Terraform DevOps: 6/6 APIs exposed. Fully covered.**

---

### 16. 🌐 DNS & CDN Card (DevOps)
| Feature | Status | API | Notes |
|---------|--------|-----|-------|
| Status overview | ✅ Exposed | `GET /dns/status` | |
| DNS lookup modal | ✅ Modal | `GET /dns/lookup/:domain` | |
| SSL check modal | ✅ Modal | `GET /dns/ssl/:domain` | |
| Generate config modal | ✅ Modal | `POST /dns/generate` | |

**DNS: 4/4 APIs exposed. Fully covered.**

---

## SUMMARY: 28 Missing Features

### Integrations Tab — 17 missing features:

| # | Card | Feature | API | Priority |
|---|------|---------|-----|----------|
| 1 | 🐙 GitHub | Environments list | `GET /gh/environments` | 🔴 High |
| 2 | 🐙 GitHub | Create environment modal | `POST /gh/environment/create` | 🔴 High |
| 3 | 🐙 GitHub | Secrets list panel | `GET /gh/secrets` | 🔴 High |
| 4 | 🐙 GitHub | Push secrets action | `POST /secrets/push` | 🔴 High |
| 5 | 🐙 GitHub | Auto-detect config | `GET /gh/auto` | 🟡 Medium |
| 6 | 🔄 CI/CD | CI status overview | `GET /ci/status` | 🔴 High |
| 7 | 🔄 CI/CD | CI workflows config | `GET /ci/workflows` | 🟡 Medium |
| 8 | 🔄 CI/CD | Coverage report panel | `GET /ci/coverage` | 🔴 High |
| 9 | 🔄 CI/CD | Generate CI config modal | `POST /ci/generate/ci` | 🟡 Medium |
| 10 | 🔄 CI/CD | Generate lint config modal | `POST /ci/generate/lint` | 🟡 Medium |
| 11 | 🐳 Docker | Container logs modal | `GET /docker/logs` | 🔴 High |
| 12 | 🐳 Docker | Generate Dockerfile modal | `POST /docker/generate/dockerfile` | 🟡 Medium |
| 13 | 🐳 Docker | Generate .dockerignore modal | `POST /docker/generate/dockerignore` | 🟢 Low |
| 14 | 🐳 Docker | Generate docker-compose modal | `POST /docker/generate/compose` | 🟡 Medium |
| 15 | ☸ K8s | Generate manifests modal | `POST /k8s/generate/manifests` | 🟡 Medium |
| 16 | 🏗 Terraform | Generate TF config modal | `POST /terraform/generate` | 🟡 Medium |
| 17 | 🐳 Docker | Write generated file action | `POST /docker/generate/write` | 🟢 Low |

### DevOps Tab — 11 missing features:

| # | Card | Feature | API | Priority |
|---|------|---------|-----|----------|
| 18 | 🔒 Security | Full security scan panel | `GET /security/scan` | 🔴 High |
| 19 | 🔒 Security | Security posture detail modal | `GET /security/posture` | 🔴 High |
| 20 | 🔒 Security | Security status info | `GET /security/status` | 🟡 Medium |
| 21 | 🌍 Environment | Env vars list panel | `GET /infra/env/vars` | 🔴 High |
| 22 | 🌍 Environment | Env validation panel | `GET /infra/env/validate` | 🔴 High |
| 23 | 🌍 Environment | Env diff (local vs remote) | `GET /infra/env/diff` | 🔴 High |
| 24 | 🌍 Environment | Generate .env.example | `POST /infra/env/generate-example` | 🟡 Medium |
| 25 | 🌍 Environment | Generate .env | `POST /infra/env/generate-env` | 🟡 Medium |
| 26 | 🌍 Environment | IaC status & resources | `GET /infra/iac/*` | 🟡 Medium |
| 27 | 🌍 Environment | Infra overview | `GET /infra/status` | 🟡 Medium |
| 28 | 🌍 Environment | Env cleanup action | `POST /env/cleanup` | 🟢 Low |

---

## Implementation Roadmap (Suggested Order)

### Phase 1: High Priority (12 features)
Quick wins — backend API already exists, just need UI panel/button/modal:

1. **Docker: Container logs modal** — `/docker/logs` — show per-container logs
2. **GitHub: Environments panel** — `/gh/environments` — list deployment envs
3. **GitHub: Secrets panel** — `/gh/secrets` — show synced secrets
4. **GitHub: Push secrets** — `POST /secrets/push` — action button
5. **GitHub: Create environment** — `POST /gh/environment/create` — modal
6. **CI/CD: Status overview** — `/ci/status` — show CI config detection
7. **CI/CD: Coverage panel** — `/ci/coverage` — show test coverage
8. **Security: Full scan panel** — `/security/scan` — show deep scan results
9. **Security: Posture detail modal** — `/security/posture` — show full posture
10. **Environment: Vars list panel** — `/infra/env/vars` — show env variables
11. **Environment: Validation panel** — `/infra/env/validate` — show env health
12. **Environment: Env diff panel** — `/infra/env/diff` — show local vs remote diff

### Phase 2: Medium Priority (12 features)
Generators and config helpers — need modals with inputs:

13. **Docker: Generate Dockerfile modal**
14. **Docker: Generate docker-compose modal**
15. **K8s Int: Generate manifests modal**
16. **Terraform Int: Generate TF config modal**
17. **CI/CD: Generate CI config modal**
18. **CI/CD: Generate lint config modal**
19. **CI/CD: Workflows config panel**
20. **GitHub: Auto-detect config**
21. **Security: Status info**
22. **Environment: Generate .env.example**
23. **Environment: Generate .env**
24. **Environment: IaC status + resources panels**

### Phase 3: Low Priority (4 features)
Polish items:

25. **Docker: Generate .dockerignore modal**
26. **Docker: Write generated file action**
27. **Environment: Infra overview**
28. **Environment: Env cleanup action**
