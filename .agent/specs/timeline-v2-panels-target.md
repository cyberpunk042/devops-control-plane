# Timeline V2 — Complete Panel Targets

---

## CHAINS SIDE-PANEL — Full List

```
filter chains...

── GIT ──────────────────────────────────────────────

▸ 📎 git:main                                    (363)
    git · config · plan
    Continuous commit history on main branch.
    Every commit is a member. Merges link branches.

▸ 📎 git:feature/xyz                               (8)
    git
    (one chain per branch with commits)

── GITHUB ───────────────────────────────────────────

▸ 📎 pr:42 — Add vault encryption                  (5)
    git
    ├─ PR opened
    ├─ commit pushed
    ├─ commit pushed
    ├─ checks passed
    └─ PR merged

▸ 📎 pr:41 — Fix CI pipeline                       (3)
    git
    ├─ PR opened
    ├─ commit pushed
    └─ PR closed

▸ 📎 workflow:12345 — CI Build                      (3)
    ci
    ├─ workflow triggered
    ├─ check: lint passed
    └─ workflow completed

▸ 📎 workflow:12340 — Deploy                        (2)
    ci
    ├─ workflow triggered
    └─ workflow completed

── INDEX CYCLES ─────────────────────────────────────

▼ 📎 cycle-20260315-031504                        (52)
    platform · git · ci · pkg · env · security ·
    tests · tools · audit · posture
    ├─ ● index:scan           1347 files
    ├─ ● index:delta          0 changes
    ├─ ● index:files          852 paths
    ├─ ● index:dirs           328 dirs
    ├─ ● index:paths          flat set
    ├─ ● index:classify       python/flask
    ├─ ● index:symbols        150 symbols
    ├─ ● index:peek           cache warm
    ├─ ● index:stats          aggregated
    ├─ ● index:view           built
    ├─ ● docker               17 keys
    ├─ ● k8s                  16 keys
    ├─ ● terraform            10 keys
    ├─ ● git status           16 keys
    ├─ ● github               ok
    ├─ ● ci scan              ok
    ├─ ● dns                  7 keys
    ├─ ● docs                 10 keys
    ├─ ● pages                1 key
    ├─ ● packages             6 keys
    ├─ ● env                  6 keys
    ├─ ● security scan        3 keys
    ├─ ● testing scan         5 keys
    ├─ ● quality              4 keys
    ├─ ● tools                detected
    ├─ ● builders             1 builder
    ├─ ● scripts              4 scripts
    ├─ ● toolchain            scanned
    ├─ ● gh-pulls             2 PRs
    ├─ ● gh-runs              2 runs
    ├─ ● gh-workflows         2 workflows
    ├─ ● project status       ok
    ├─ ● runtime              ok
    ├─ ● audit:structure      12 keys
    ├─ ● audit:deps           12 keys
    ├─ ● audit:clients        6 keys
    ├─ ● audit:system         L1 check
    ├─ ● audit:scores         computed
    ├─ ● audit:system:deep    L1 deep
    ├─ ● audit:l2:risks       risk analysis
    ├─ ● audit:l2:repo        repo analysis
    ├─ ● audit:l2:quality     quality scan
    ├─ ● audit:l2:structure   structure scan
    ├─ ● audit:scores:enriched enriched
    ├─ ● posture:toolchain    50 tools
    ├─ ● posture:platform     OS/hardware
    ├─ ● posture:project      project health
    ├─ ● posture:full         full assessment
    └─ ● posture:summary      score: 72/100

▸ 📎 cycle-20260315-031000                        (48)
▸ 📎 cycle-20260315-030500                        (35)

── VAULT SESSIONS ───────────────────────────────────

▼ 📎 vault-session:1773530100                      (5)
    config
    ├─ ● unlock
    ├─ ● key:add — API_KEY
    ├─ ● key:update — DB_HOST
    ├─ ● key:delete — OLD_KEY
    └─ ● lock

▸ 📎 vault-session:1773520000                      (3)
    config
    ├─ ● unlock
    ├─ ● sync — pushed to GitHub
    └─ ● lock

── PAGES PIPELINES ──────────────────────────────────

▸ 📎 pages:docs:1773530200                         (3)
    platform · ci
    ├─ ● build:start — docs segment
    ├─ ● build:done — merged
    └─ ● deploy:done — gh-pages

▸ 📎 pages:mkdocs:1773525000                       (2)
    platform
    ├─ ● build:start — mkdocs segment
    └─ ● build:done

── DOCKER PIPELINES ─────────────────────────────────

▸ 📎 docker-pipeline:1773530300                    (3)
    platform
    ├─ ● build — api service
    ├─ ● compose:up
    └─ ● compose:restart

── TERRAFORM PIPELINES ──────────────────────────────

▸ 📎 tf:default:1773530400                         (3)
    platform
    ├─ ● plan — 3 changes
    ├─ ● apply — applied
    └─ (terminal)

── K8S DEPLOYMENTS ──────────────────────────────────

▸ 📎 k8s-deploy:1773530500                         (3)
    platform
    ├─ ● apply — manifests
    ├─ ● scale — replicas=3
    └─ ● helm:upgrade

── CI/CD PIPELINES ──────────────────────────────────

▸ 📎 ci:gh-dispatch:1773530600                     (3)
    ci
    ├─ ● trigger — deploy workflow
    ├─ ● deploy — staging
    └─ ● done — success

── GIT FLOWS ────────────────────────────────────────

▸ 📎 git-flow:1773530700                           (2)
    git
    ├─ ● commit — feat: add vault
    └─ ● push — origin/main

▸ 📎 git-flow:1773529000                           (2)
    git
    ├─ ● commit — fix: bugs
    └─ ● push — origin/main

── BACKUP PIPELINES ─────────────────────────────────

▸ 📎 backup:1773530800                             (3)
    backup
    ├─ ● create — admin_export
    ├─ ● encrypt — AES-256
    └─ ● upload — GitHub Release

── CLI OPERATIONS ───────────────────────────────────

▸ 📎 op:op-20260315-031000-a1b2c3                  (4)
    tests · platform
    ├─ ● run:test — pytest
    ├─ ● card:testing — tests passed
    ├─ ● card:quality — lint ok
    └─ ● score:changed — 85→87

▸ 📎 op:op-20260315-025500-d4e5f6                  (3)
    security
    ├─ ● run:scan — trivy
    ├─ ● card:security — 2 findings
    └─ ● score:changed — 87→82

── QUALITY / TESTING ────────────────────────────────

▸ 📎 op:lint-20260315-030000                       (2)
    tests
    ├─ ● lint — ruff
    └─ ● format — black

── SCRIPTS / PLANS ──────────────────────────────────

▸ 📎 plan:deploy-pipeline                          (3)
    platform
    ├─ ● plan:create
    ├─ ● plan:execute — step 1/3
    └─ ● plan:execute — step 3/3

── CHAT THREADS ─────────────────────────────────────

▸ 📎 Test from mobile                             (16)
    chat
    ├─ ● thread created
    ├─ ● Hello from phone
    └─ ... +14 more

▸ 📎 Trace recorded: **demo**                      (2)
    chat

▸ 📎 Trace recorded: **test**                      (4)
    chat

── SECRETS / GITHUB ENVIRONMENTS ────────────────────

▸ 📎 secrets-push:staging:1773530900               (4)
    config
    ├─ ● secret:set — DB_URL
    ├─ ● secret:set — API_KEY
    ├─ ● secret:set — JWT_SECRET
    └─ ● deploy:secrets_push — staging

▸ 📎 env-setup:production:1773531000               (3)
    config
    ├─ ● env:create — production
    ├─ ● env:seed — from staging
    └─ ● secret:set — PROD_DB_URL

── CONTENT VAULT ────────────────────────────────────

▸ 📎 content-batch:1773531100                      (4)
    config
    ├─ ● encrypt — credentials.pdf
    ├─ ● encrypt — design-specs.psd
    ├─ ● optimize — hero-image.png (2.1MB → 340KB)
    └─ ● upload — hero-image.png → GitHub Release

── TOOL INSTALLATION ────────────────────────────────

▼ 📎 install:docker:1773531200                     (8)
    tools
    ├─ ● plan:resolve — 5 steps
    ├─ ● step:check — docker not found
    ├─ ● step:package — apt install docker.io
    ├─ ● step:service — systemctl enable docker
    ├─ ● step:config — daemon.json
    ├─ ● step:verify — docker --version
    ├─ ● step:post — add user to docker group
    └─ ● install:complete — Docker 24.0.7

▸ 📎 install:terraform:1773531300                  (5)
    tools
    ├─ ● plan:resolve — 3 steps
    ├─ ● step:download — terraform 1.7.0
    ├─ ● step:extract — /usr/local/bin
    ├─ ● step:verify — terraform --version
    └─ ● install:complete — Terraform 1.7.0

▸ 📎 update:node:1773531400                        (3)
    tools
    ├─ ● step:check — node 18.0 → 20.0
    ├─ ● step:package — nvm install 20
    └─ ● update:complete — Node 20.0.0

── CDP BROWSER TESTING ──────────────────────────────

▸ 📎 test-suite:login-flow:1773531500              (6)
    tests
    ├─ ● suite:create — login-flow
    ├─ ● record:start — recording session
    ├─ ● record:stop — 12 steps captured
    ├─ ● replay:start — headless
    ├─ ● replay:done — 12/12 passed
    └─ ● suite:sync — pushed to git

▸ 📎 test-suite:checkout:1773531600                (4)
    tests
    ├─ ● suite:create — checkout
    ├─ ● record:start
    ├─ ● record:stop — 8 steps
    └─ ● replay:start — 6/8 passed ⚠

── TRACES ───────────────────────────────────────────

▸ 📎 trace:demo-walkthrough:1773531700             (3)
    tests
    ├─ ● trace:start — demo-walkthrough
    ├─ ● trace:stop — 45s recorded
    └─ ● trace:share — pushed to ledger

── ARTIFACTS / BUILD TARGETS ────────────────────────

▸ 📎 artifact:api-server:1773531800                (4)
    platform
    ├─ ● target:create — api-server (docker)
    ├─ ● build:stream — api-server
    ├─ ● publish:stream — ghcr.io/org/api:v1.2
    └─ ● workflow:generate — release.yml

▸ 📎 artifact:cli-tool:1773531900                  (3)
    platform
    ├─ ● target:create — cli-tool (binary)
    ├─ ● build:stream — cli-tool
    └─ ● publish:stream — GitHub Release

── CHANGELOG ────────────────────────────────────────

▸ 📎 changelog:v1.2.0:1773532000                   (4)
    platform
    ├─ ● bootstrap — from git history
    ├─ ● entry:add — feat: vault encryption
    ├─ ● entry:add — fix: CI pipeline
    └─ ● release:cut — v1.2.0

── PLANS / AUTOMATION ───────────────────────────────

▸ 📎 plan:deploy-pipeline:1773532100               (5)
    platform
    ├─ ● plan:create — deploy-pipeline
    ├─ ● plan:execute — step 1: build
    ├─ ● plan:execute — step 2: test
    ├─ ● plan:execute — step 3: deploy
    └─ ● plan:sync — pushed to git

▸ 📎 plan:db-migration:1773532200                  (3)
    platform
    ├─ ● plan:create — db-migration
    ├─ ● plan:execute — step 1: backup
    └─ ● plan:cancel — user cancelled

── SCRIPTS ──────────────────────────────────────────

  (standalone events — no chain unless multi-step)
  ● script:run — analyze-deps.sh
  ● script:run — generate-api-docs.sh
  ● script:run — seed-database.sh

── NOTIFICATIONS ────────────────────────────────────

  (standalone events)
  ● notification:dismiss — CVE-2024-1234
  ● notification:delete — stale warning

── WIZARD SETUP ─────────────────────────────────────

▸ 📎 wizard:session:1773532300                     (6)
    config · wizard
    ├─ ● wizard:detect — 14 stacks found
    ├─ ● wizard:setup_git — remote configured
    ├─ ● wizard:setup_ci — GitHub Actions
    ├─ ● wizard:setup_dns — cloudflare
    ├─ ● config:saved — project.yml
    └─ ● wizard:complete

── ENVIRONMENT MANAGEMENT ──────────────────────────

▸ 📎 env:switch:1773532400                         (2)
    config
    ├─ ● env:activate — staging
    └─ ● env:create — .env.staging

── SERVER LIFECYCLE ─────────────────────────────────

  (standalone events — no chain)
  ● server:start — port 8000
  ● server:restart — code reload
  ● server:factory-reset — .state/ cleared
  ● server:settings — dev mode toggled

── SECURITY ─────────────────────────────────────────

▸ 📎 security-scan:1773532500                      (3)
    security
    ├─ ● scan:trivy — 2 CVEs found
    ├─ ● finding:dismiss — CVE-2024-1234 (accepted)
    └─ ● score:changed — 87→85

── DNS ──────────────────────────────────────────────

  (standalone events)
  ● dns:generate — zone records
  ● dns:validate — 5 records OK

── DOCUMENTATION ────────────────────────────────────

  (standalone events)
  ● generate:changelog — CHANGELOG.md
  ● generate:readme — README.md
```

---

## DOMAINS SIDE-PANEL — Full Tree

```
filter domains...

▼ git_log                                          (363)
    ▼ commit                                        (344)
        ● feat: timeline / history skaffold+++
        ● feat: timeline / history skaffold++
        ● fix: bugs
        ... +341 more
    ▸ merge                                           (3)
    ▸ ci                                              (2)
    ▸ docker                                          (1)
    ▸ k8s                                             (5)
    ▸ rules                                           (8)
    ▸ promoted                                        (3)
    ▸ tag                                             (0)
    ▸ branch                                          (0)

▼ mediator                                          (52)
    ▼ Index                                          (10)
        ▸ index:scan                                   (3)
        ▸ index:delta                                  (3)
        ▸ index:files                                  (3)
        ▸ index:dirs                                   (3)
        ▸ index:paths                                  (3)
        ▸ index:classify                               (3)
        ▸ index:symbols                                (2)
        ▸ index:peek                                   (2)
        ▸ index:stats                                  (3)
        ▸ index:view                                   (3)
    ▼ DevOps                                         (14)
        ▸ docker                                       (1)
        ▸ k8s                                          (1)
        ▸ terraform                                    (1)
        ▸ git status                                   (1)
        ▸ github                                       (1)
        ▸ ci scan                                      (1)
        ▸ dns                                          (1)
        ▸ docs                                         (1)
        ▸ pages                                        (1)
        ▸ env                                          (1)
        ▸ packages                                     (1)
        ▸ security scan                                (1)
        ▸ testing scan                                 (1)
        ▸ quality                                      (1)
    ▼ Audit                                          (11)
        ▸ structure                                    (1)
        ▸ deps                                         (1)
        ▸ clients                                      (1)
        ▸ L1 (system)                                  (1)
        ▸ scores                                       (1)
        ▸ L1:deep                                      (1)
        ▸ L2:risks                                     (1)
        ▸ L2:repo                                      (1)
        ▸ L2:quality                                   (1)
        ▸ L2:structure                                 (1)
        ▸ scores:enriched                              (1)
    ▼ Posture                                         (5)
        ▸ toolchain                                    (1)
        ▸ platform                                     (1)
        ▸ project                                      (1)
        ▸ full                                         (1)
        ▸ summary                                      (1)
    ▼ GitHub                                          (3)
        ▸ pulls                                        (1)
        ▸ runs                                         (1)
        ▸ workflows                                    (1)
    ▼ Catalog                                         (3)
        ▸ tools                                        (1)
        ▸ builders                                     (1)
        ▸ scripts                                      (1)
    ▼ Other                                           (3)
        ▸ runtime                                      (1)
        ▸ project status                               (1)
        ▸ toolchain                                    (1)

▼ runs                                               (N)
    ▸ setup:vault_lock                                 (1)
    ▸ setup:vault_unlock                               (1)
    ▸ setup:vault_add_keys                             (2)
    ▸ setup:vault_update_key                           (1)
    ▸ destroy:vault_key                                (1)
    ▸ build:docker                                     (1)
    ▸ deploy:docker_up                                 (1)
    ▸ deploy:docker_restart                            (1)
    ▸ destroy:docker_down                              (1)
    ▸ destroy:docker_prune                             (1)
    ▸ build:pages_segment                              (2)
    ▸ build:pages_all                                  (1)
    ▸ build:pages_merge                                (1)
    ▸ deploy:pages                                     (1)
    ▸ deploy:k8s                                       (1)
    ▸ deploy:k8s_scale                                 (1)
    ▸ install:helm                                     (1)
    ▸ deploy:helm_upgrade                              (1)
    ▸ plan:terraform                                   (1)
    ▸ setup:terraform                                  (1)
    ▸ deploy:terraform                                 (1)
    ▸ destroy:terraform                                (1)
    ▸ git:commit                                       (3)
    ▸ git:push                                         (2)
    ▸ git:pull                                         (1)
    ▸ backup:export                                    (1)
    ▸ setup:encrypt_backup                             (1)
    ▸ backup:upload_release                            (1)
    ▸ restore:backup                                   (1)
    ▸ setup:server_restart                             (1)
    ▸ destroy:factory_reset                            (1)
    ▸ setup:server_settings                            (1)
    ▸ setup:config_save                                (1)
    ▸ setup:encrypt                                    (1)
    ▸ setup:decrypt                                    (1)
    ▸ setup:content_upload                             (1)
    ▸ destroy:content_file                             (1)
    ▸ test:run                                         (2)
    ▸ test:coverage                                    (1)
    ▸ validate:quality                                 (1)
    ▸ validate:lint                                    (1)
    ▸ format:quality                                   (1)
    ▸ scan:dismiss_finding                             (1)
    ▸ install:tool                                     (1)
    ▸ install:packages                                 (1)
    ▸ generate:dockerfile                              (1)
    ▸ generate:compose                                 (1)
    ▸ generate:k8s_manifests                           (1)
    ▸ generate:changelog                               (1)
    ▸ generate:readme                                  (1)
    ▸ generate:ci_workflow                             (1)
    ▸ ci:gh_dispatch                                   (1)
    ▸ deploy:secrets_push                              (1)
    ▸ setup:gh_environment                             (1)
    ▸ setup:secret_set                                 (1)
    ▸ script:run                                       (1)
    ▸ script:plan_execute                              (1)
    ▸ setup:plan_create                                (1)
    ▸ setup:trace_start                                (1)
    ▸ setup:trace_stop                                 (1)
    ▸ test:record_start                                (1)
    ▸ test:replay_start                                (1)

▼ chat                                              (22)
    ▸ thread_created                                   (3)
    ▸ message                                         (19)

▼ scan_activity                                      (N)
    (user-initiated events only)
    ▸ wizard:saved                                     (1)
    ▸ wizard:setup_git                                 (1)
    ▸ wizard:setup_ci                                  (1)
    ▸ wizard:setup_dns                                 (1)
    ▸ security:dismiss                                 (1)
    ▸ security:undismiss                               (1)

▼ cli_ops                                            (N)
    ▸ test                                             (3)
    ▸ lint                                             (2)
    ▸ format                                           (2)
    ▸ detect                                           (1)
    ▸ scan                                             (1)

▼ github                                             (N)
    (from mediator nodes: github.pulls, runs, workflows)
    ▸ pr:opened                                        (2)
    ▸ pr:merged                                        (1)
    ▸ pr:closed                                        (1)
    ▸ workflow:triggered                               (5)
    ▸ workflow:completed                               (4)
    ▸ workflow:failed                                  (1)
    ▸ check:passed                                     (8)
    ▸ check:failed                                     (2)
    ▸ release:published                                (1)

▼ vault                                              (N)
    ▸ unlock                                           (3)
    ▸ lock                                             (3)
    ▸ key:add                                          (5)
    ▸ key:update                                       (2)
    ▸ key:delete                                       (1)
    ▸ key:move                                         (1)
    ▸ section:rename                                   (1)
    ▸ sync                                             (2)
    ▸ export                                           (1)
    ▸ import                                           (1)
    ▸ env:activate                                     (2)
    ▸ env:create                                       (1)
    ▸ auto-lock                                        (1)

▼ content                                            (N)
    ▸ encrypt                                          (3)
    ▸ decrypt                                          (2)
    ▸ upload                                           (4)
    ▸ delete                                           (1)
    ▸ create-folder                                    (1)
    ▸ save                                             (5)
    ▸ rename                                           (1)
    ▸ move                                             (1)
    ▸ optimize                                         (2)
    ▸ setup-enc-key                                    (1)
    ▸ restore-large                                    (1)

▼ backup                                             (N)
    ▸ export                                           (2)
    ▸ upload                                           (1)
    ▸ restore                                          (1)
    ▸ import                                           (1)
    ▸ wipe                                             (1)
    ▸ delete                                           (1)
    ▸ encrypt                                          (1)
    ▸ decrypt                                          (1)
    ▸ rename                                           (1)
    ▸ upload-release                                   (1)
    ▸ mark-special                                     (1)

▼ secrets                                            (N)
    ▸ generate:key                                     (2)
    ▸ setup:gh_environment                             (1)
    ▸ destroy:environment                              (1)
    ▸ setup:env_seed                                   (1)
    ▸ setup:secret_set                                 (3)
    ▸ destroy:secret                                   (1)
    ▸ deploy:secrets_push                              (2)

▼ docker                                             (N)
    ▸ build                                            (2)
    ▸ compose:up                                       (3)
    ▸ compose:down                                     (1)
    ▸ compose:restart                                  (2)
    ▸ prune                                            (1)
    ▸ pull                                             (1)
    ▸ exec                                             (2)
    ▸ rm                                               (1)
    ▸ rmi                                              (1)
    ▸ generate:dockerfile                              (1)
    ▸ generate:dockerignore                            (1)
    ▸ generate:compose                                 (1)

▼ k8s                                               (N)
    ▸ apply                                            (2)
    ▸ delete                                           (1)
    ▸ scale                                            (1)
    ▸ helm:install                                     (1)
    ▸ helm:upgrade                                     (1)
    ▸ helm:template                                    (1)
    ▸ generate:manifests                               (1)
    ▸ generate:wizard                                  (1)

▼ terraform                                          (N)
    ▸ plan                                             (2)
    ▸ init                                             (1)
    ▸ apply                                            (1)
    ▸ destroy                                          (1)
    ▸ validate                                         (1)
    ▸ generate                                         (1)
    ▸ workspace                                        (1)
    ▸ format                                           (1)

▼ ci                                                 (N)
    ▸ gh_dispatch                                      (2)
    ▸ generate:ci_workflow                             (1)
    ▸ generate:lint_workflow                           (1)

▼ quality                                            (N)
    ▸ validate:quality                                 (1)
    ▸ validate:lint                                    (1)
    ▸ validate:typecheck                               (1)
    ▸ test:quality                                     (1)
    ▸ format:quality                                   (1)
    ▸ generate:quality_config                          (1)

▼ testing                                            (N)
    ▸ test:run                                         (3)
    ▸ test:coverage                                    (1)
    ▸ generate:test_template                           (1)

▼ security                                           (N)
    ▸ scan                                             (2)
    ▸ dismiss_finding                                  (1)
    ▸ undismiss_finding                                (1)
    ▸ generate:gitignore                               (1)

▼ tools                                              (N)
    ▸ install:tool                                     (2)
    ▸ install:update                                   (1)
    ▸ install:remove                                   (1)
    ▸ install:cache-plan                               (1)

▼ pages                                              (N)
    ▸ build:segment                                    (3)
    ▸ build:all                                        (1)
    ▸ build:merge                                      (1)
    ▸ deploy                                           (1)
    ▸ init                                             (1)
    ▸ segment:create                                   (1)
    ▸ segment:update                                   (1)
    ▸ segment:delete                                   (1)
    ▸ preview:start                                    (1)
    ▸ preview:stop                                     (1)
    ▸ generate:ci                                      (1)
    ▸ patch-script                                     (1)

▼ packages                                           (N)
    ▸ install:packages                                 (1)
    ▸ install:packages_update                          (1)

▼ dns                                               (N)
    ▸ generate:dns_records                             (1)

▼ docs                                              (N)
    ▸ generate:changelog                               (1)
    ▸ generate:readme                                  (1)

▼ server                                             (N)
    ▸ restart                                          (1)
    ▸ factory-reset                                    (1)
    ▸ settings                                         (2)
    ▸ accept-port                                      (1)

▼ config                                             (N)
    ▸ config:save                                      (2)

▼ plans                                              (N)
    ▸ create                                           (2)
    ▸ update                                           (1)
    ▸ delete                                           (1)
    ▸ duplicate                                        (1)
    ▸ execute                                          (1)
    ▸ cancel                                           (1)
    ▸ resume                                           (1)
    ▸ skip                                             (1)
    ▸ git:add                                          (1)
    ▸ git:sync                                         (1)
    ▸ git:remove                                       (1)

▼ scripts                                            (N)
    ▸ run                                              (3)

▼ traces                                             (N)
    ▸ start                                            (2)
    ▸ stop                                             (2)
    ▸ delete                                           (1)
    ▸ share                                            (1)
    ▸ unshare                                          (1)
    ▸ update                                           (1)

▼ cdp_test                                           (N)
    ▸ suite:create                                     (2)
    ▸ suite:update                                     (1)
    ▸ suite:delete                                     (1)
    ▸ suite:duplicate                                  (1)
    ▸ record:start                                     (2)
    ▸ record:stop                                      (2)
    ▸ replay:start                                     (1)
    ▸ replay:cancel                                    (1)
    ▸ browser:launch                                   (1)
    ▸ browser:kill                                     (1)
    ▸ git:add                                          (1)
    ▸ git:sync                                         (1)
    ▸ git:remove                                       (1)

▼ changelog                                          (N)
    ▸ entry:add                                        (3)
    ▸ entry:edit                                       (1)
    ▸ entry:delete                                     (1)
    ▸ bootstrap                                        (1)
    ▸ release:cut                                      (1)

▼ artifacts                                          (N)
    ▸ target:create                                    (2)
    ▸ target:update                                    (1)
    ▸ target:delete                                    (1)
    ▸ detect                                           (1)
    ▸ makefile:patch                                   (1)
    ▸ workflow:generate                                (1)
    ▸ build:stream                                     (2)
    ▸ publish:stream                                   (1)

▼ integrations                                       (N)
    ▸ git:commit                                       (5)
    ▸ git:push                                         (3)
    ▸ git:pull                                         (2)
    ▸ git:stash                                        (1)
    ▸ git:stash-pop                                    (1)
    ▸ git:merge-abort                                  (1)
    ▸ git:checkout-file                                (1)
    ▸ git:gc                                           (1)
    ▸ git:history-reset                                (1)
    ▸ git:filter-repo                                  (1)
    ▸ remote:add                                       (1)
    ▸ remote:remove                                    (1)
    ▸ remote:rename                                    (1)
    ▸ remote:set-url                                   (1)
    ▸ gh:login                                         (1)
    ▸ gh:logout                                        (1)
    ▸ gh:device-flow                                   (1)
    ▸ gh:repo-create                                   (1)
    ▸ gh:visibility                                    (1)
    ▸ gh:default-branch                                (1)
    ▸ gh:repo-rename                                   (1)
    ▸ ledger:push                                      (1)
    ▸ ledger:resolve-conflict                          (1)

▼ wizard                                             (N)
    ▸ detect                                           (1)
    ▸ setup_git                                        (1)
    ▸ setup_ci                                         (1)
    ▸ setup_dns                                        (1)
    ▸ setup_terraform                                  (1)
    ▸ setup_docker                                     (1)
    ▸ setup_pages                                      (1)
    ▸ config:saved                                     (1)
    ▸ complete                                         (1)

▼ env                                               (N)
    ▸ generate:env_example                             (1)
    ▸ generate:env                                     (1)

▼ notifications                                      (N)
    ▸ dismiss                                          (2)
    ▸ delete                                           (1)

▸ ledger_runs                                        (0)
    (promoted runs — appears when ledger tags exist)

▸ ledger_audits                                      (0)
    (promoted audits — appears when audit tags exist)
```
