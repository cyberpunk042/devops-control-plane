# Route Quality Audit

> Generated: 2026-03-16 15:12 UTC  |  Framework: flask  |  Style: **smart**

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [API Surface Map](#api-surface-map)
3. [Blueprint Architecture](#blueprint-architecture)
4. [Decorator Inventory](#decorator-inventory)
5. [Route Contracts](#route-contracts)
6. [Complexity Analysis](#complexity-analysis)
7. [Consistency Matrix](#consistency-matrix)
8. [Anomaly Detection](#anomaly-detection)

## Executive Summary

| Metric | Value |
|--------|-------|
| Blueprints | **37** |
| Routes | **507** |
| 📝 Docstrings | **99%** (502/507) |
| 📊 Run tracking | **0%** (0/507) |
| 🛡️ Error handling | **21%** (104/507) |
| 📋 Explicit methods | **60%** (302/507) |
| 🎭 Unique decorators | **3** |
| 📏 Avg body size | **23 lines** |
| 🔀 Avg branches | **2.0** |
| 📌 Init-file routes | **13** / 37 blueprints |

## API Surface Map

> Endpoint tree organized by blueprint. Each route shows its HTTP method, decorators, and detected parameters.

### 📦 audit (46 routes)

```
  POST    /audit/check-deps  → 200
  POST    /audit/check-updates
  GET     /audit/clients
  GET     /audit/code-health
  POST    /audit/data-status  → 400
  GET     /audit/data-usage
  GET     /audit/dependencies
  POST    /audit/install-cache/artifacts  → 400
  POST    /audit/install-cache/clear
  GET     /audit/install-cache/status
  POST    /audit/install-plan  → 400
  POST    /audit/install-plan/archive  → 400,404
  POST    /audit/install-plan/cache  [tracked]  → 400
  POST    /audit/install-plan/cancel  → 400,404
  POST    /audit/install-plan/execute  [tracked]  → 400
  POST    /audit/install-plan/execute-sync  [tracked]  → 400
  GET     /audit/install-plan/pending
  POST    /audit/install-plan/resume  → 400
  POST    /audit/install-tool  [tracked]
  POST    /audit/remediate  → 400
  POST    /audit/remove-tool  [tracked]  → 400,500
  GET     /audit/repo
  POST    /audit/resolve-choices  → 400
  GET     /audit/risks
  POST    /audit/scan  → 202,409
  GET     /audit/scan/<task_id> <task_id>  → 404
  GET     /audit/scores
  GET     /audit/scores/enriched
  GET     /audit/scores/history
  POST    /audit/service-status  → 400
  GET     /audit/structure
  GET     /audit/structure-analysis
  GET     /audit/system
  POST    /audit/system/deep-detect
  POST    /audit/tool-version  → 400
  POST    /audit/update-plan  → 400
  POST    /audit/update-plan/batch  → 400
  POST    /audit/update-tool  [tracked]  → 400
  POST    /audits/discard
  GET     /audits/pending
  GET     /audits/pending/<snapshot_id> <snapshot_id>  → 404
  POST    /audits/save
  GET     /audits/saved
  GET     /audits/saved/<snapshot_id> <snapshot_id>  → 404
  DELETE  /audits/saved/<snapshot_id> <snapshot_id>  → 404,500
  GET     /tools/status  ← query:bust?
```

> CRUD: **CRD** — missing: Update/PUT

### 📦 integrations (43 routes)

```
  POST    /gh/actions/dispatch  [tracked, requires_gh_auth]  → 400
  GET     /gh/actions/runs  [requires_gh_auth]  ← query:bust?
  GET     /gh/actions/workflows  [requires_gh_auth]  ← query:bust?
  POST    /gh/auth/device  [tracked]  → 200
  GET     /gh/auth/device/poll  ← query:session?  → 400
  POST    /gh/auth/login  [tracked]
  POST    /gh/auth/logout  [tracked]  → 400
  GET     /gh/auth/terminal/poll
  GET     /gh/auth/token
  GET     /gh/pulls  [requires_gh_auth]  ← query:bust?
  POST    /gh/repo/create  [tracked, requires_gh_auth]  → 400
  POST    /gh/repo/default-branch  [tracked, requires_gh_auth]  → 400
  GET     /gh/repo/info  [requires_gh_auth]
  POST    /gh/repo/rename  [tracked, requires_gh_auth]  → 400
  POST    /gh/repo/visibility  [tracked, requires_gh_auth]  → 400
  GET     /gh/user  [requires_gh_auth]
  POST    /git/checkout-file  [tracked]  → 400
  POST    /git/commit  [tracked]  → 400
  GET     /git/diff
  GET     /git/diff/file  ← query:path?, query:staged?  → 400
  POST    /git/filter-repo  [requires_git_auth, tracked]  → 400
  POST    /git/gc  [tracked]  → 400
  POST    /git/history-reset  [requires_git_auth, tracked]  → 400
  GET     /git/log  ← query:n?
  GET     /git/merge-status
  POST    /git/merge/abort  [tracked]  → 400
  POST    /git/pull  [requires_git_auth, tracked]  → 400
  POST    /git/push  [requires_git_auth, tracked]  → 400
  POST    /git/remote/add  [tracked]  → 400
  POST    /git/remote/remove  [tracked]  → 400
  POST    /git/remote/rename  [tracked]  → 400
  POST    /git/remote/set-url  [tracked]  → 400
  GET     /git/remotes
  POST    /git/stash  [tracked]  → 400
  GET     /git/stash/list
  POST    /git/stash/pop  [tracked]  → 400
  GET     /git/status  ← query:bust?
  GET     /github/status
  GET     /integrations/gh/status  ← query:bust?
  POST    /ledger/push  [requires_git_auth]  → 409
  POST    /ledger/resolve-conflict  [requires_git_auth]  → 400
  GET     /ledger/sync-status
  GET     /ops/terminal/status
```

> CRUD: **CR** — missing: Update/PUT, Delete/DELETE

### 📦 cdp_test (36 routes)

```
  GET     /cdp-test/browser-status
  POST    /cdp-test/io/configure  [tracked]  → 400
  POST    /cdp-test/kill-browser  [tracked]  → 400,404,500
  POST    /cdp-test/launch-browser  [tracked]  → 500,503
  POST    /cdp-test/record/add-step  → 404
  POST    /cdp-test/record/eval  → 400,404,500
  POST    /cdp-test/record/event  → 400,404
  OPTIONS /cdp-test/record/event
  POST,OPTIONS /cdp-test/record/log
  POST    /cdp-test/record/modify-step  → 400,404
  POST    /cdp-test/record/pause  → 404
  POST    /cdp-test/record/restart  → 404
  POST    /cdp-test/record/resume  → 404
  POST    /cdp-test/record/start  [tracked]  → 400,404,500,503
  GET     /cdp-test/record/status
  POST    /cdp-test/record/stop  [tracked]  → 404
  POST    /cdp-test/replay/cancel  [tracked]  → 404
  POST    /cdp-test/replay/start  [tracked]  → 400,404,409,503
  GET     /cdp-test/replay/status
  GET     /cdp-test/results  ← query:suite_id?, query:last?
  GET     /cdp-test/results/<run_id> <run_id>  → 404
  GET     /cdp-test/screenshots/<filename> <filename>  → 400,404
  GET     /cdp-test/suites
  POST    /cdp-test/suites  [tracked]  → 201,400
  GET     /cdp-test/suites/<suite_id> <suite_id>  → 404
  PUT     /cdp-test/suites/<suite_id> <suite_id>  [tracked]  → 404
  DELETE  /cdp-test/suites/<suite_id> <suite_id>  [tracked]  → 404
  GET     /cdp-test/suites/<suite_id>/check-history <suite_id>
  POST    /cdp-test/suites/<suite_id>/duplicate <suite_id>  [tracked]  → 201,404
  GET     /cdp-test/suites/<suite_id>/git-dependents <suite_id>
  POST    /cdp-test/suites/add-to-git  [tracked]  → 400,404
  POST    /cdp-test/suites/recover  [tracked]  → 400,404
  POST    /cdp-test/suites/remove-from-git  [tracked]  → 400,404
  POST    /cdp-test/suites/sync-to-git  [tracked]  → 400,404
  GET     /cdp-test/targets  → 503
  POST    /cdp-test/warm
```

> CRUD: **CRUD** — complete

### 📦 content (30 routes)

```
  GET     /content/all-folders
  POST    /content/clean-release-sidecar  → 400,404
  POST    /content/create-folder  [tracked]
  POST    /content/decrypt  [tracked]  → 400
  POST    /content/delete  [tracked]
  GET     /content/download  ← query:path?, query:download?  → 400,404
  GET     /content/enc-key-status
  POST    /content/encrypt  [tracked]  → 400
  GET     /content/folders
  GET     /content/glossary  ← query:smart_folder?, query:path?, query:recursive?  → 400,404
  GET     /content/list  ← query:path?, query:recursive?, query:check_release?  → 400,404
  GET     /content/metadata  ← query:path?  → 400,404
  POST    /content/move  [tracked]
  POST    /content/optimize-cancel
  GET     /content/optimize-status
  GET     /content/outline  ← query:path?  → 400,404
  GET     /content/peek-refs  ← query:path?
  POST    /content/peek-resolve
  GET     /content/preview  ← query:path?  → 400,404
  POST    /content/preview-encrypted  → 400,404
  POST    /content/release-cancel/<file_id> <file_id>
  GET     /content/release-inventory
  GET     /content/release-status
  GET     /content/release-status/<file_id> <file_id>  → 404
  POST    /content/rename  [tracked]
  POST    /content/restore-large
  POST    /content/save  [tracked]
  POST    /content/save-encrypted  → 400,404,500
  POST    /content/setup-enc-key  [tracked]  → 400
  POST    /content/upload  [tracked]  ← form:folder?  → 400
```

> CRUD: **CR** — missing: Update/PUT, Delete/DELETE

### 📦 pages (27 routes)

```
  GET     /
  POST    /pages/build-all  [tracked]
  GET     /pages/build-status/<name> <name>
  POST    /pages/build-stream/<name> <name>  ← query:clean?, query:wipe?, query:no_minify?
  POST    /pages/build/<name> <name>  [tracked]
  GET     /pages/builders  ← query:bust?
  POST    /pages/builders/<name>/install <name>
  POST    /pages/ci  [tracked]
  POST    /pages/deploy  [requires_git_auth, tracked]
  POST    /pages/detect
  GET     /pages/features
  POST    /pages/init  [tracked]
  POST    /pages/merge  [tracked]
  GET     /pages/meta
  POST    /pages/meta
  POST    /pages/patch-script  → 400,404,409,500
  POST    /pages/preview/<name> <name>
  DELETE  /pages/preview/<name> <name>
  GET     /pages/previews
  GET     /pages/resolve-file  ← query:path?
  POST    /pages/scan-pipeline  → 400
  GET     /pages/segments  ← query:bust?
  POST    /pages/segments  [tracked]  → 400,409
  PUT     /pages/segments/<name> <name>  [tracked]  → 404
  DELETE  /pages/segments/<name> <name>  [tracked]
  GET     /pages/site/<segment>/<path:filepath> <segment> <filepath>
  GET     /sw.js
```

> CRUD: **CRUD** — complete

### 📦 tab_mesh (27 routes)

```
  GET     /tab-mesh/cdp-diagnose
  POST    /tab-mesh/cdp-invalidate  → 204
  POST    /tab-mesh/cdp-remediate  → 400,500
  GET     /tab-mesh/cdp-status
  GET     /tab-mesh/chrome-status
  POST    /tab-mesh/discover-target  → 400
  POST    /tab-mesh/focus  → 503
  POST    /tab-mesh/kill-chrome  → 500
  POST    /tab-mesh/leave  → 204
  POST    /tab-mesh/restart-chrome  → 400,500
  POST    /tab-mesh/suggest-cdp
  POST    /tab-mesh/trigger-chrome-signin  → 400,500,503
  GET     /tab-mesh/wsl-channel-status
  GET     /tab-mesh/wsl-curl-state
  GET     /tab-mesh/wsl-firewall-state
  GET     /tab-mesh/wsl-firewall-status  ← query:port?
  POST    /tab-mesh/wsl-fix-firewall  ← body:port?, body:scope?  → 500,504
  POST    /tab-mesh/wsl-install-curl  → 500
  GET     /tab-mesh/wsl-portproxy-state
  POST    /tab-mesh/wsl-remove-firewall  → 500,504
  POST    /tab-mesh/wsl-remove-portproxy  → 500,504
  POST    /tab-mesh/wsl-setup-routing  → 400,500
  POST    /tab-mesh/wsl-start-tunnel  → 400,500
  POST    /tab-mesh/wsl-stop-tunnel
  POST    /tab-mesh/wsl-test-hostname  ← body:port?
  GET     /tab-mesh/wsl-tunnel-state
  POST    /tab-mesh/wsl-validate
```

> CRUD: **CR** — missing: Update/PUT, Delete/DELETE

### 📦 docker (24 routes)

```
  POST    /docker/build  [tracked]  → 400
  GET     /docker/compose/status
  GET     /docker/containers  ← query:all?
  POST    /docker/down  [tracked]  → 400
  POST    /docker/exec  [tracked]  → 400
  POST    /docker/generate/compose  [tracked]  → 400
  POST    /docker/generate/compose-wizard  [tracked]  → 400
  POST    /docker/generate/dockerfile  [tracked]  → 400
  POST    /docker/generate/dockerignore  [tracked]  → 400
  POST    /docker/generate/write  [tracked]  → 400
  GET     /docker/images
  GET     /docker/inspect  ← query:id?  → 400
  GET     /docker/logs  ← query:service?, query:tail?  → 400
  GET     /docker/networks
  POST    /docker/prune  [tracked]  → 400
  POST    /docker/pull  [tracked]  → 400
  POST    /docker/restart  [tracked]  → 400
  POST    /docker/rm  [tracked]  → 400
  POST    /docker/rmi  [tracked]  → 400
  GET     /docker/stats
  GET     /docker/status  ← query:bust?
  POST    /docker/stream/<action> <action>  → 400
  POST    /docker/up  [tracked]  → 400
  GET     /docker/volumes
```

> CRUD: **CR** — missing: Update/PUT, Delete/DELETE

### 📦 k8s (24 routes)

```
  POST    /k8s/apply  [tracked]  → 400
  GET     /k8s/cluster
  POST    /k8s/delete  [tracked]  → 400
  GET     /k8s/describe  ← query:kind?, query:name?, query:namespace?  → 400
  GET     /k8s/env-namespaces
  GET     /k8s/events  ← query:namespace?  → 400
  POST    /k8s/generate/manifests  [tracked]  → 400
  POST    /k8s/generate/wizard  [tracked]  → 400
  POST    /k8s/helm/install  [tracked]  → 400
  GET     /k8s/helm/list  ← query:namespace?
  POST    /k8s/helm/template  [tracked]  → 400
  POST    /k8s/helm/upgrade  [tracked]  → 400
  GET     /k8s/helm/values  ← query:release?, query:namespace?  → 400
  GET     /k8s/namespaces  → 400
  GET     /k8s/pod-logs  ← query:pod?, query:namespace?, query:tail?, query:container?  → 400
  GET     /k8s/resources  ← query:namespace?, query:kind?
  POST    /k8s/scale  [tracked]  → 400
  GET     /k8s/skaffold/status
  GET     /k8s/status  ← query:bust?
  GET     /k8s/storageclasses  → 400
  GET     /k8s/validate
  GET     /k8s/wizard-state
  POST    /k8s/wizard-state  → 400
  DELETE  /k8s/wizard-state
```

> CRUD: **CRD** — missing: Update/PUT

### 📦 vault (21 routes)

```
  POST    /vault/activate-env  → 400
  GET     /vault/active-env
  POST    /vault/add-keys  [tracked]  → 400
  POST    /vault/auto-lock  → 400
  POST    /vault/create  [tracked]  → 400
  POST    /vault/delete-key  [tracked]
  POST    /vault/export  [tracked]  → 400
  POST    /vault/import  [tracked]  → 400
  GET     /vault/keys
  POST    /vault/lock  [tracked]  → 400
  POST    /vault/move-key  [tracked]
  POST    /vault/raw-value
  POST    /vault/register  [tracked]  → 400
  POST    /vault/rename-section  [tracked]
  GET     /vault/secrets
  POST    /vault/set-meta  [tracked]
  GET     /vault/status
  GET     /vault/templates
  POST    /vault/toggle-local-only  [tracked]
  POST    /vault/unlock  [tracked]  → 400
  POST    /vault/update-key  [tracked]
```

> CRUD: **CR** — missing: Update/PUT, Delete/DELETE

### 📦 backup (18 routes)

```
  POST    /backup/decrypt  [tracked]  → 400
  POST    /backup/delete  [tracked]  → 400
  POST    /backup/delete-release  [tracked]
  GET     /backup/download/<path:filepath> <filepath>  → 400,404
  POST    /backup/encrypt  [tracked]  → 400
  POST    /backup/export  [tracked]
  GET     /backup/folder-tree  ← query:depth?
  GET     /backup/folders
  POST    /backup/import  [tracked]  → 400
  GET     /backup/list  ← query:path?, query:check_release?  → 400
  POST    /backup/mark-special  [tracked]  → 400
  GET     /backup/preview  ← query:path?  → 400
  POST    /backup/rename  [tracked]  → 400
  POST    /backup/restore  [tracked]
  GET     /backup/tree  ← query:types?, query:path?, query:depth?, query:gitignore?  → 400,404
  POST    /backup/upload  [tracked]  ← form:target_folder?  → 400
  POST    /backup/upload-release  [tracked]
  POST    /backup/wipe  [tracked]
```

> CRUD: **CR** — missing: Update/PUT, Delete/DELETE

### 📦 plans (17 routes)

```
  GET     /plans
  POST    /plans  [tracked]  → 201,400
  GET     /plans/<plan_id> <plan_id>  → 404
  PUT     /plans/<plan_id> <plan_id>  [tracked]  → 404
  DELETE  /plans/<plan_id> <plan_id>  [tracked]  → 404
  POST    /plans/<plan_id>/duplicate <plan_id>  [tracked]  → 201,404
  POST    /plans/<plan_id>/execute <plan_id>  [tracked]  → 404,409
  GET     /plans/<plan_id>/git-check <plan_id>
  POST    /plans/add-to-git  [tracked]  → 400,404
  POST    /plans/remove-from-git  [tracked]  → 400,404
  GET     /plans/results  ← query:plan_id?, query:last?
  GET     /plans/results/<run_id> <run_id>  → 404
  POST    /plans/run/<run_id>/cancel <run_id>  [tracked]  → 404
  POST    /plans/run/<run_id>/resume <run_id>  [tracked]  → 404
  POST    /plans/run/<run_id>/skip <run_id>  [tracked]  → 404
  GET     /plans/run/active
  POST    /plans/sync-to-git  [tracked]  → 400,404
```

> CRUD: **CRUD** — complete

### 📦 artifacts (16 routes)

```
  GET     /<name>/publishable <name>  → 404
  GET     /<name>/release-notes <name>  ← query:since_tag?
  POST    /build/<name>/stream <name>  → 404
  GET     /builders
  POST    /detect  [tracked]  → 404
  GET     /makefile/evolution
  POST    /makefile/patch  [tracked]  → 404,500
  POST    /publish/<name>/stream <name>
  GET     /publish/capabilities
  GET     /targets
  POST    /targets  [tracked]  → 400,409
  PUT     /targets/<name> <name>  [tracked]  → 404
  DELETE  /targets/<name> <name>  [tracked]  → 404
  GET     /targets/<name>/status <name>  → 404
  POST    /workflow/generate  [tracked]
  GET     /workflow/preview
```

> CRUD: **CRUD** — complete

### 📦 mediator (15 routes)

```
  POST    /mediator/bust  → 400,500
  GET     /mediator/config
  PUT     /mediator/config
  GET     /mediator/diag  → 500
  GET     /mediator/diag/<path:path> <path>  → 404,500
  POST    /mediator/dispatch  → 400,500
  GET     /mediator/events/recent  ← query:limit?  → 500
  GET     /mediator/index/delta  → 500
  POST    /mediator/index/rebuild-peek  → 500
  POST    /mediator/index/rebuild-symbols  → 500
  POST    /mediator/index/rescan  → 500
  GET     /mediator/index/status  → 500
  POST    /mediator/refresh  → 400,500
  POST    /mediator/refresh-branch  → 400,500
  POST    /mediator/refresh-stale  → 500
```

> CRUD: **CRU** — missing: Delete/DELETE

### 📦 devops (13 routes)

```
  POST    /devops/audit/dismissals  [tracked]  → 400
  DELETE  /devops/audit/dismissals  [tracked]  → 400
  POST    /devops/cache/bust
  GET     /devops/integration-prefs
  PUT     /devops/integration-prefs
  GET     /devops/prefs
  PUT     /devops/prefs
  POST    /wizard/check-tools  → 400
  POST    /wizard/compose-ci  [tracked]  → 400,500
  DELETE  /wizard/config  [tracked]  → 400
  GET     /wizard/detect  ← query:bust?
  POST    /wizard/setup  [tracked]  → 400,500
  POST    /wizard/validate  → 400
```

> CRUD: **CRUD** — complete

### 📦 chat (12 routes)

```
  POST    /chat/delete-message  [requires_gh_auth, requires_git_auth, tracked]  → 400,404,500
  POST    /chat/delete-thread  [requires_gh_auth, requires_git_auth, tracked]  → 400,404,500
  GET     /chat/messages  ← query:n?, query:thread_id?, query:run_id?  → 500
  POST    /chat/move-message  [requires_gh_auth, requires_git_auth, tracked]  → 400,404,500
  POST    /chat/poll  [requires_gh_auth, requires_git_auth]  → 500
  GET     /chat/refs/autocomplete  ← query:prefix?  → 500
  GET     /chat/refs/resolve  ← query:ref?  → 400,404,500
  POST    /chat/send  [requires_gh_auth, requires_git_auth, tracked]  → 400,500
  POST    /chat/sync  [requires_gh_auth, requires_git_auth]  → 500
  GET     /chat/threads  → 500
  POST    /chat/threads/create  [requires_gh_auth, requires_git_auth, tracked]  → 400,500
  POST    /chat/update-message  [requires_gh_auth, requires_git_auth, tracked]  → 400,404,500
```

> CRUD: **CR** — missing: Update/PUT, Delete/DELETE

### 📦 scripts (12 routes)

```
  GET     /scripts/categories
  GET     /scripts/coverage
  POST    /scripts/detect
  GET     /scripts/history  ← query:last?, query:script_id?
  GET     /scripts/history/<run_id> <run_id>  → 404
  GET     /scripts/info/<path:script_id> <script_id>  → 404
  GET     /scripts/list  ← query:category?, query:source?
  GET     /scripts/packages
  POST    /scripts/run  [tracked]  → 400
  POST    /scripts/run/stream  → 400,404
  GET     /scripts/status/<run_id> <run_id>  → 404
  GET     /scripts/templates
```

> CRUD: **CR** — missing: Update/PUT, Delete/DELETE

### 📦 terraform (12 routes)

```
  POST    /terraform/apply  [tracked]  → 400
  POST    /terraform/destroy  [tracked]  → 400
  POST    /terraform/fmt  [tracked]  → 400
  POST    /terraform/generate  [tracked]  → 400
  POST    /terraform/init  [tracked]  → 400
  GET     /terraform/output  → 400
  POST    /terraform/plan  [tracked]  → 400
  GET     /terraform/state
  GET     /terraform/status  ← query:bust?
  POST    /terraform/validate  [tracked]  → 400
  POST    /terraform/workspace/select  [tracked]  → 400
  GET     /terraform/workspaces
```

> CRUD: **CR** — missing: Update/PUT, Delete/DELETE

### 📦 secrets (11 routes)

```
  POST    /env/cleanup  [tracked]  → 400
  POST    /env/seed  [tracked]
  GET     /gh/auto
  POST    /gh/environment/create  [tracked]  → 400
  GET     /gh/environments
  GET     /gh/secrets
  GET     /gh/status
  POST    /keys/generate  [tracked]
  POST    /secret/remove  [tracked]  → 400
  POST    /secret/set  [tracked]  → 400
  POST    /secrets/push  [tracked]  → 400
```

> CRUD: **CR** — missing: Update/PUT, Delete/DELETE

### 📦 infra (10 routes)

```
  GET     /env/card-status  ← query:bust?
  GET     /infra/env/diff  ← query:source?, query:target?  → 404
  POST    /infra/env/generate-env  [tracked]  → 400
  POST    /infra/env/generate-example  [tracked]  → 400
  GET     /infra/env/status
  GET     /infra/env/validate  ← query:file?  → 404
  GET     /infra/env/vars  ← query:file?, query:redact?  → 404
  GET     /infra/iac/resources
  GET     /infra/iac/status
  GET     /infra/status
```

> CRUD: **CR** — missing: Update/PUT, Delete/DELETE

### 📦 trace (10 routes)

```
  GET     /trace/active  → 500
  POST    /trace/delete  [tracked]  → 400,404,500
  GET     /trace/events  ← query:trace_id?  → 400,500
  GET     /trace/get  ← query:trace_id?  → 400,404,500
  GET     /trace/list  ← query:n?  → 500
  POST    /trace/share  [tracked]  → 400,404,500
  POST    /trace/start  [tracked]  → 500
  POST    /trace/stop  [tracked]  → 400,404,500
  POST    /trace/unshare  [tracked]  → 400,404,500
  POST    /trace/update  [tracked]  → 400,404,500
```

> CRUD: **CR** — missing: Update/PUT, Delete/DELETE

### 📦 api (9 routes)

```
  GET     /audit  ← query:n?
  GET     /audit/activity  ← query:n?, query:offset?, query:limit?, query:card?, query:q?
  POST    /batch
  GET     /capabilities  → 404
  POST    /detect  → 400
  GET     /health
  POST    /run  → 400
  GET     /stacks
  GET     /status  → 404
```

> CRUD: **CR** — missing: Update/PUT, Delete/DELETE

### 📦 notifications (8 routes)

```
  GET     /errors  ← query:page?, query:per_page?
  POST    /errors  → 400
  POST    /errors/ack
  GET     /notifications  ← query:all?
  DELETE  /notifications/<notif_id> <notif_id>  [tracked]  → 404
  GET     /notifications/badge
  POST    /notifications/dismiss  [tracked]  → 400,404
  POST    /notifications/silence  → 400,404
```

> CRUD: **CRD** — missing: Update/PUT

### 📦 quality (7 routes)

```
  POST    /quality/check  [tracked]  → 400
  POST    /quality/format  [tracked]
  POST    /quality/generate/config  [tracked]  → 400
  POST    /quality/lint  [tracked]
  GET     /quality/status  ← query:bust?
  POST    /quality/test  [tracked]
  POST    /quality/typecheck  [tracked]
```

> CRUD: **CR** — missing: Update/PUT, Delete/DELETE

### 📦 security_scan (7 routes)

```
  GET     /security/files
  POST    /security/generate/gitignore  [tracked]  → 400
  GET     /security/gitignore
  GET     /security/posture
  GET     /security/posture-summary
  GET     /security/scan
  GET     /security/status  ← query:bust?
```

> CRUD: **CR** — missing: Update/PUT, Delete/DELETE

### 📦 packages (6 routes)

```
  GET     /packages/audit  ← query:manager?  → 400
  POST    /packages/install  [tracked]  → 400
  GET     /packages/list  ← query:manager?  → 400
  GET     /packages/outdated  ← query:manager?  → 400
  GET     /packages/status  ← query:bust?
  POST    /packages/update  [tracked]  → 400
```

> CRUD: **CR** — missing: Update/PUT, Delete/DELETE

### 📦 server (6 routes)

```
  POST    /server/accept-port  → 400,500
  POST    /server/factory-reset  [tracked]  → 500
  POST    /server/restart  [tracked]  → 500
  GET     /server/settings
  PUT     /server/settings  [tracked]
  GET     /server/status
```

> CRUD: **CRU** — missing: Delete/DELETE

### 📦 ci (5 routes)

```
  GET     /ci/coverage
  POST    /ci/generate/ci  [tracked]  → 400
  POST    /ci/generate/lint  [tracked]  → 400
  GET     /ci/status  ← query:bust?
  GET     /ci/workflows
```

> CRUD: **CR** — missing: Update/PUT, Delete/DELETE

### 📦 docs (5 routes)

```
  GET     /docs/coverage
  POST    /docs/generate/changelog  [tracked]  → 400
  POST    /docs/generate/readme  [tracked]
  GET     /docs/links  ← query:file?
  GET     /docs/status  ← query:bust?
```

> CRUD: **CR** — missing: Update/PUT, Delete/DELETE

### 📦 git_auth (5 routes)

```
  POST    /git/auth-https  → 400,500
  POST    /git/auth-ssh  → 400,500
  GET     /git/auth-status  → 500
  GET     /git/identity  → 500
  POST    /git/identity  → 400,500
```

> CRUD: **CR** — missing: Update/PUT, Delete/DELETE

### 📦 smart_folders (5 routes)

```
  GET     /smart-folders
  GET     /smart-folders/<name>/file <name>  ← query:path?  → 400,403,404,500
  GET     /smart-folders/<name>/peek <name>  ← query:module?, query:topic?  → 400,404
  GET     /smart-folders/<name>/tree <name>  → 404
  GET     /smart-folders/discover  ← query:pattern?
```

> CRUD: **R** — missing: Create/POST, Update/PUT, Delete/DELETE

### 📦 testing (5 routes)

```
  POST    /testing/coverage  [tracked]
  POST    /testing/generate/template  [tracked]  → 400
  GET     /testing/inventory
  POST    /testing/run  [tracked]  → 400
  GET     /testing/status  ← query:bust?
```

> CRUD: **CR** — missing: Update/PUT, Delete/DELETE

### 📦 dns (4 routes)

```
  POST    /dns/generate  [tracked]  → 400
  GET     /dns/lookup/<domain> <domain>  → 400
  GET     /dns/ssl/<domain> <domain>  → 400
  GET     /dns/status  ← query:bust?
```

> CRUD: **CR** — missing: Update/PUT, Delete/DELETE

### 📦 config (3 routes)

```
  GET     /config  → 500
  POST    /config  [tracked]  → 400
  GET     /config/content-folders  ← query:include_hidden?
```

> CRUD: **CR** — missing: Update/PUT, Delete/DELETE

### 📦 dev (3 routes)

```
  GET     /dev/scenarios  ← query:system?
  GET     /dev/scenarios/<scenario_id> <scenario_id>  ← query:system?  → 404
  GET     /dev/status
```

> CRUD: **R** — missing: Create/POST, Update/PUT, Delete/DELETE

### 📦 metrics (2 routes)

```
  GET     /metrics/health  ← query:bust?
  GET     /metrics/summary
```

> CRUD: **R** — missing: Create/POST, Update/PUT, Delete/DELETE

### 📦 project (2 routes)

```
  GET     /project/next  ← query:bust?
  GET     /project/status  ← query:bust?
```

> CRUD: **R** — missing: Create/POST, Update/PUT, Delete/DELETE

### 📦 events (1 routes)

```
  GET     /events  ← query:since?
```

> CRUD: **R** — missing: Create/POST, Update/PUT, Delete/DELETE

## Blueprint Architecture

> File distribution and structure per blueprint.

### 📁 audit/

```
  analysis.py                     11 routes    104 lines
  async_scan.py                    2 routes     66 lines
  deep_detection.py                1 routes     94 lines
  offline_cache.py                 7 routes    130 lines
  staging.py                       7 routes     68 lines
  tool_execution.py                6 routes    858 lines
  tool_install.py                 12 routes    311 lines
```

> Naming: 45/46 functions (97%) follow `audit_*` convention

### 📁 integrations/

```
  gh_auth.py                       6 routes    125 lines
  gh_repo.py                       4 routes     49 lines
  git.py                          16 routes    160 lines
  github.py                        8 routes     50 lines
  history.py                       3 routes     52 lines
  remotes.py                       5 routes     39 lines
  terminal.py                      1 routes      3 lines
```

### 📁 cdp_test/

```
  browser.py                       3 routes    168 lines
  io.py                            1 routes     87 lines
  recording.py                    13 routes    811 lines
  replay.py                        4 routes    252 lines
  suites.py                       15 routes    293 lines
```

> Naming: 36/36 functions (100%) follow `cdp_test_*` convention

### 📁 content/

```
  __init__.py                      6 routes    136 lines (📌 init)
  files.py                         7 routes     79 lines
  manage.py                       10 routes    119 lines
  outline.py                       2 routes    129 lines
  peek.py                          2 routes    163 lines
  preview.py                       3 routes    226 lines
```

> Naming: 28/30 functions (93%) follow `content_*` convention

### 📁 pages/

```
  api.py                          24 routes    226 lines
  serving.py                       3 routes     55 lines
```

### 📁 tab_mesh/

```
  __init__.py                     27 routes   1857 lines (📌 init)
```

> Naming: 2/27 functions (7%) follow `tab_mesh_*` convention

### 📁 docker/

```
  actions.py                       9 routes    102 lines
  detect.py                        1 routes      7 lines
  generate.py                      5 routes     79 lines
  observe.py                       8 routes     32 lines
  stream.py                        1 routes     17 lines
```

> Naming: 19/24 functions (79%) follow `docker_*` convention

### 📁 k8s/

```
  actions.py                       3 routes     31 lines
  cluster.py                       8 routes     46 lines
  detect.py                        2 routes      9 lines
  generate.py                      2 routes     28 lines
  helm.py                          5 routes     65 lines
  skaffold.py                      1 routes      3 lines
  wizard.py                        3 routes     10 lines
```

> Naming: 18/24 functions (75%) follow `k8s_*` convention

### 📁 vault/

```
  env_mgmt.py                      4 routes     32 lines
  keys.py                          9 routes    107 lines
  security.py                      4 routes     53 lines
  status.py                        2 routes      6 lines
  transfer.py                      2 routes     38 lines
```

> Naming: 21/21 functions (100%) follow `vault_*` convention

### 📁 backup/

```
  __init__.py                      2 routes      7 lines (📌 init)
  archive.py                       5 routes     81 lines
  ops.py                           6 routes     78 lines
  restore.py                       4 routes     79 lines
  tree.py                          1 routes     24 lines
```

### 📁 plans/

```
  crud.py                         10 routes    211 lines
  execution.py                     7 routes    153 lines
```

> Naming: 17/17 functions (100%) follow `plans_*` convention

### 📁 artifacts/

```
  api.py                          16 routes    318 lines
```

### 📁 mediator/

```
  __init__.py                     15 routes    411 lines (📌 init)
```

> Naming: 15/15 functions (100%) follow `mediator_*` convention

### 📁 devops/

```
  __init__.py                      5 routes     42 lines (📌 init)
  apply.py                         5 routes     99 lines
  audit.py                         2 routes     39 lines
  detect.py                        1 routes     14 lines
```

> Naming: 3/13 functions (23%) follow `devops_*` convention

### 📁 chat/

```
  messages.py                      5 routes    254 lines
  refs.py                          2 routes     35 lines
  sync.py                          2 routes     92 lines
  threads.py                       3 routes    103 lines
```

> Naming: 12/12 functions (100%) follow `chat_*` convention

### 📁 scripts/

```
  execution.py                     4 routes    252 lines
  history.py                       2 routes     44 lines
  registry.py                      6 routes    203 lines
```

> Naming: 12/12 functions (100%) follow `scripts_*` convention

### 📁 terraform/

```
  actions.py                       8 routes     68 lines
  status.py                        4 routes     16 lines
```

### 📁 secrets/

```
  actions.py                       7 routes    109 lines
  status.py                        4 routes      9 lines
```

### 📁 infra/

```
  env.py                           7 routes     39 lines
  iac.py                           3 routes     11 lines
```

> Naming: 1/10 functions (10%) follow `infra_*` convention

### 📁 trace/

```
  queries.py                       3 routes     55 lines
  recording.py                     3 routes     62 lines
  sharing.py                       4 routes    110 lines
```

> Naming: 10/10 functions (100%) follow `trace_*` convention

### 📁 api/

```
  audit.py                         2 routes     60 lines
  batch.py                         1 routes     61 lines
  stacks.py                        1 routes     16 lines
  status.py                        5 routes     65 lines
```

> Naming: 8/9 functions (88%) follow `api_*` convention

### 📁 notifications/

```
  __init__.py                      8 routes    180 lines (📌 init)
```

### 📁 quality/

```
  actions.py                       6 routes     33 lines
  status.py                        1 routes      7 lines
```

> Naming: 7/7 functions (100%) follow `quality_*` convention

### 📁 security_scan/

```
  actions.py                       1 routes      9 lines
  detect.py                        6 routes     57 lines
```

> Naming: 1/7 functions (14%) follow `security_scan_*` convention

### 📁 packages/

```
  actions.py                       2 routes     23 lines
  status.py                        4 routes     28 lines
```

> Naming: 6/6 functions (100%) follow `packages_*` convention

### 📁 server/

```
  __init__.py                      6 routes    136 lines (📌 init)
```

> Naming: 6/6 functions (100%) follow `server_*` convention

### 📁 ci/

```
  generate.py                      2 routes     16 lines
  status.py                        3 routes     11 lines
```

> Naming: 3/5 functions (60%) follow `ci_*` convention

### 📁 docs/

```
  generate.py                      2 routes     12 lines
  status.py                        3 routes     12 lines
```

> Naming: 5/5 functions (100%) follow `docs_*` convention

### 📁 git_auth/

```
  credentials.py                   5 routes     94 lines
```

### 📁 smart_folders/

```
  __init__.py                      5 routes    164 lines (📌 init)
```

### 📁 testing/

```
  actions.py                       3 routes     32 lines
  status.py                        2 routes      9 lines
```

> Naming: 5/5 functions (100%) follow `testing_*` convention

### 📁 dns/

```
  __init__.py                      4 routes     34 lines (📌 init)
```

> Naming: 4/4 functions (100%) follow `dns_*` convention

### 📁 config/

```
  __init__.py                      3 routes     33 lines (📌 init)
```

### 📁 dev/

```
  __init__.py                      3 routes     61 lines (📌 init)
```

> Naming: 3/3 functions (100%) follow `dev_*` convention

### 📁 metrics/

```
  health.py                        1 routes     69 lines
  summary.py                       1 routes      2 lines
```

### 📁 project/

```
  __init__.py                      2 routes     14 lines (📌 init)
```

> Naming: 2/2 functions (100%) follow `project_*` convention

### 📁 events/

```
  __init__.py                      1 routes     37 lines (📌 init)
```

> Naming: 1/1 functions (100%) follow `events_*` convention

## Decorator Inventory

> All decorators used across the project, categorized by type.

| Decorator | Routes | Blueprints | Used In |
|-----------|--------|------------|---------|
| `tracked` | 183 | 28 | artifacts, audit, backup, cdp_test, chat +23 |
| `requires_gh_auth` | 18 | 2 | chat, integrations |
| `requires_git_auth` | 15 | 3 | chat, integrations, pages |

### Decorator Combinations

| Combination | Count | % |
|-------------|-------|---|
| (route only) | 315 | 62.1% |
| tracked | 167 | 32.9% |
| requires_gh_auth + requires_git_auth + tracked | 6 | 1.2% |
| requires_gh_auth + tracked | 5 | 1.0% |
| requires_git_auth + tracked | 5 | 1.0% |
| requires_gh_auth | 5 | 1.0% |
| requires_gh_auth + requires_git_auth | 2 | 0.4% |
| requires_git_auth | 2 | 0.4% |

## Route Contracts

> Per-route input/output analysis. Shows what each route accepts and what it returns.

### audit

**`POST /audit/check-deps`** — `audit_check_deps`

- 📤 Codes: ✅ 200

**`POST /audit/data-status`** — `audit_data_status`

- 📤 Codes: ⚠️ 400

**`POST /audit/install-cache/artifacts`** — `audit_cache_artifacts`

- 📤 Codes: ⚠️ 400

**`POST /audit/install-plan`** — `audit_install_plan`

- 📤 Codes: ⚠️ 400

**`POST /audit/install-plan/archive`** — `audit_archive_plan`

- 📤 Codes: ⚠️ 400, ⚠️ 404

**`POST /audit/install-plan/cache`** — `audit_cache_plan`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`POST /audit/install-plan/cancel`** — `audit_cancel_plan`

- 📤 Codes: ⚠️ 400, ⚠️ 404

**`POST /audit/install-plan/execute`** — `audit_execute_plan`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`POST /audit/install-plan/execute-sync`** — `audit_execute_plan_sync`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`POST /audit/install-plan/resume`** — `audit_resume_plan`

- 📤 Codes: ⚠️ 400

**`POST /audit/remediate`** — `audit_remediate`

- 📤 Codes: ⚠️ 400

**`POST /audit/remove-tool`** — `audit_remove_tool`  🎭 tracked

- 📤 Codes: ⚠️ 400, ❌ 500

**`POST /audit/resolve-choices`** — `audit_resolve_choices`

- 📤 Codes: ⚠️ 400

**`POST /audit/scan`** — `audit_scan_start`

- 📤 Codes: ✅ 202, ⚠️ 409

**`GET /audit/scan/<task_id>`** — `audit_scan_status`

- 🔗 URL: `<task_id>`
- 📤 Codes: ⚠️ 404

**`POST /audit/service-status`** — `audit_service_status`

- 📤 Codes: ⚠️ 400

**`POST /audit/tool-version`** — `audit_tool_version`

- 📤 Codes: ⚠️ 400

**`POST /audit/update-plan`** — `audit_update_plan`

- 📤 Codes: ⚠️ 400

**`POST /audit/update-plan/batch`** — `audit_update_plan_batch`

- 📤 Codes: ⚠️ 400

**`POST /audit/update-tool`** — `audit_update_tool`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`GET /audits/pending/<snapshot_id>`** — `audits_pending_detail`

- 🔗 URL: `<snapshot_id>`
- 📤 Codes: ⚠️ 404

**`GET /audits/saved/<snapshot_id>`** — `audits_saved_detail`

- 🔗 URL: `<snapshot_id>`
- 📤 Codes: ⚠️ 404

**`DELETE /audits/saved/<snapshot_id>`** — `audits_saved_delete`

- 🔗 URL: `<snapshot_id>`
- 📤 Codes: ⚠️ 404, ❌ 500

**`GET /tools/status`** — `tools_status`

- 📥 `query.bust` (optional)

### integrations

**`POST /gh/actions/dispatch`** — `gh_actions_dispatch`  🎭 tracked, requires_gh_auth

- 📤 Codes: ⚠️ 400

**`GET /gh/actions/runs`** — `gh_actions_runs`  🎭 requires_gh_auth

- 📥 `query.bust` (optional)

**`GET /gh/actions/workflows`** — `gh_actions_workflows`  🎭 requires_gh_auth

- 📥 `query.bust` (optional)

**`POST /gh/auth/device`** — `gh_auth_device_start_route`  🎭 tracked

- 📤 Codes: ✅ 200

**`GET /gh/auth/device/poll`** — `gh_auth_device_poll_route`

- 📥 `query.session` (optional)
- 📤 Codes: ⚠️ 400

**`POST /gh/auth/logout`** — `gh_auth_logout`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`GET /gh/pulls`** — `gh_pulls`  🎭 requires_gh_auth

- 📥 `query.bust` (optional)

**`POST /gh/repo/create`** — `gh_repo_create`  🎭 tracked, requires_gh_auth

- 📤 Codes: ⚠️ 400

**`POST /gh/repo/default-branch`** — `gh_repo_set_default_branch`  🎭 tracked, requires_gh_auth

- 📤 Codes: ⚠️ 400

**`POST /gh/repo/rename`** — `gh_repo_rename`  🎭 tracked, requires_gh_auth

- 📤 Codes: ⚠️ 400

**`POST /gh/repo/visibility`** — `gh_repo_set_visibility`  🎭 tracked, requires_gh_auth

- 📤 Codes: ⚠️ 400

**`POST /git/checkout-file`** — `git_checkout_file_route`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`POST /git/commit`** — `git_commit`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`GET /git/diff/file`** — `git_diff_file_route`

- 📥 `query.path` (optional)
- 📥 `query.staged` (optional)
- 📤 Codes: ⚠️ 400

**`POST /git/filter-repo`** — `git_filter_repo_route`  🎭 requires_git_auth, tracked

- 📤 Codes: ⚠️ 400

**`POST /git/gc`** — `git_gc_route`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`POST /git/history-reset`** — `git_history_reset_route`  🎭 requires_git_auth, tracked

- 📤 Codes: ⚠️ 400

**`GET /git/log`** — `git_log`

- 📥 `query.n` (optional)

**`POST /git/merge/abort`** — `git_merge_abort_route`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`POST /git/pull`** — `git_pull`  🎭 requires_git_auth, tracked

- 📤 Codes: ⚠️ 400

**`POST /git/push`** — `git_push`  🎭 requires_git_auth, tracked

- 📤 Codes: ⚠️ 400

**`POST /git/remote/add`** — `git_remote_add`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`POST /git/remote/remove`** — `git_remote_remove`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`POST /git/remote/rename`** — `git_remote_rename`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`POST /git/remote/set-url`** — `git_remote_set_url`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`POST /git/stash`** — `git_stash_route`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`POST /git/stash/pop`** — `git_stash_pop_route`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`GET /git/status`** — `git_status`

- 📥 `query.bust` (optional)

**`GET /integrations/gh/status`** — `gh_status_extended`

- 📥 `query.bust` (optional)

**`POST /ledger/push`** — `ledger_push_route`  🎭 requires_git_auth

- 📤 Codes: ⚠️ 409

**`POST /ledger/resolve-conflict`** — `ledger_resolve_conflict_route`  🎭 requires_git_auth

- 📤 Codes: ⚠️ 400

### cdp_test

**`POST /cdp-test/io/configure`** — `cdp_test_io_configure`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`POST /cdp-test/kill-browser`** — `cdp_test_kill_browser`  🎭 tracked

- 📤 Codes: ⚠️ 400, ⚠️ 404, ❌ 500

**`POST /cdp-test/launch-browser`** — `cdp_test_launch_browser`  🎭 tracked

- 📤 Codes: ❌ 500, ❌ 503

**`POST /cdp-test/record/add-step`** — `cdp_test_record_add_step`

- 📤 Codes: ⚠️ 404

**`POST /cdp-test/record/eval`** — `cdp_test_record_eval`

- 📤 Codes: ⚠️ 400, ⚠️ 404, ❌ 500

**`POST /cdp-test/record/event`** — `cdp_test_record_event`

- 📤 Codes: ⚠️ 400, ⚠️ 404

**`POST /cdp-test/record/modify-step`** — `cdp_test_record_modify_step`

- 📤 Codes: ⚠️ 400, ⚠️ 404

**`POST /cdp-test/record/pause`** — `cdp_test_record_pause`

- 📤 Codes: ⚠️ 404

**`POST /cdp-test/record/restart`** — `cdp_test_record_restart`

- 📤 Codes: ⚠️ 404

**`POST /cdp-test/record/resume`** — `cdp_test_record_resume`

- 📤 Codes: ⚠️ 404

**`POST /cdp-test/record/start`** — `cdp_test_record_start`  🎭 tracked

- 📤 Codes: ⚠️ 400, ⚠️ 404, ❌ 500, ❌ 503

**`POST /cdp-test/record/stop`** — `cdp_test_record_stop`  🎭 tracked

- 📤 Codes: ⚠️ 404

**`POST /cdp-test/replay/cancel`** — `cdp_test_replay_cancel`  🎭 tracked

- 📤 Codes: ⚠️ 404

**`POST /cdp-test/replay/start`** — `cdp_test_replay_start`  🎭 tracked

- 📤 Codes: ⚠️ 400, ⚠️ 404, ⚠️ 409, ❌ 503

**`GET /cdp-test/results`** — `cdp_test_list_results`

- 📥 `query.suite_id` (optional)
- 📥 `query.last` (optional)

**`GET /cdp-test/results/<run_id>`** — `cdp_test_get_result`

- 🔗 URL: `<run_id>`
- 📤 Codes: ⚠️ 404

**`GET /cdp-test/screenshots/<filename>`** — `cdp_test_screenshot`

- 🔗 URL: `<filename>`
- 📤 Codes: ⚠️ 400, ⚠️ 404

**`POST /cdp-test/suites`** — `cdp_test_create_suite`  🎭 tracked

- 📤 Codes: ✅ 201, ⚠️ 400

**`GET /cdp-test/suites/<suite_id>`** — `cdp_test_get_suite`

- 🔗 URL: `<suite_id>`
- 📤 Codes: ⚠️ 404

**`PUT /cdp-test/suites/<suite_id>`** — `cdp_test_update_suite`  🎭 tracked

- 🔗 URL: `<suite_id>`
- 📤 Codes: ⚠️ 404

**`DELETE /cdp-test/suites/<suite_id>`** — `cdp_test_delete_suite`  🎭 tracked

- 🔗 URL: `<suite_id>`
- 📤 Codes: ⚠️ 404

**`GET /cdp-test/suites/<suite_id>/check-history`** — `cdp_test_check_suite_history`

- 🔗 URL: `<suite_id>`

**`POST /cdp-test/suites/<suite_id>/duplicate`** — `cdp_test_duplicate_suite`  🎭 tracked

- 🔗 URL: `<suite_id>`
- 📤 Codes: ✅ 201, ⚠️ 404

**`GET /cdp-test/suites/<suite_id>/git-dependents`** — `cdp_test_suite_git_dependents`

- 🔗 URL: `<suite_id>`

**`POST /cdp-test/suites/add-to-git`** — `cdp_test_add_suite_to_git`  🎭 tracked

- 📤 Codes: ⚠️ 400, ⚠️ 404

**`POST /cdp-test/suites/recover`** — `cdp_test_recover_suite`  🎭 tracked

- 📤 Codes: ⚠️ 400, ⚠️ 404

**`POST /cdp-test/suites/remove-from-git`** — `cdp_test_remove_suite_from_git`  🎭 tracked

- 📤 Codes: ⚠️ 400, ⚠️ 404

**`POST /cdp-test/suites/sync-to-git`** — `cdp_test_sync_suite_to_git`  🎭 tracked

- 📤 Codes: ⚠️ 400, ⚠️ 404

**`GET /cdp-test/targets`** — `cdp_test_list_targets`

- 📤 Codes: ❌ 503

### content

**`POST /content/clean-release-sidecar`** — `content_clean_release_sidecar`

- 📤 Codes: ⚠️ 400, ⚠️ 404

**`POST /content/decrypt`** — `content_decrypt`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`GET /content/download`** — `content_download`

- 📥 `query.path` (optional)
- 📥 `query.download` (optional)
- 📤 Codes: ⚠️ 400, ⚠️ 404

**`POST /content/encrypt`** — `content_encrypt`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`GET /content/glossary`** — `content_glossary`

- 📥 `query.smart_folder` (optional)
- 📥 `query.path` (optional)
- 📥 `query.recursive` (optional)
- 📤 Codes: ⚠️ 400, ⚠️ 404

**`GET /content/list`** — `content_list`

- 📥 `query.path` (optional)
- 📥 `query.recursive` (optional)
- 📥 `query.check_release` (optional)
- 📤 Codes: ⚠️ 400, ⚠️ 404

**`GET /content/metadata`** — `content_metadata`

- 📥 `query.path` (optional)
- 📤 Codes: ⚠️ 400, ⚠️ 404

**`GET /content/outline`** — `content_outline`

- 📥 `query.path` (optional)
- 📤 Codes: ⚠️ 400, ⚠️ 404

**`GET /content/peek-refs`** — `peek_refs`

- 📥 `query.path` (optional)

**`GET /content/preview`** — `content_preview`

- 📥 `query.path` (optional)
- 📤 Codes: ⚠️ 400, ⚠️ 404

**`POST /content/preview-encrypted`** — `content_preview_encrypted`

- 📤 Codes: ⚠️ 400, ⚠️ 404

**`POST /content/release-cancel/<file_id>`** — `content_release_cancel`

- 🔗 URL: `<file_id>`

**`GET /content/release-status/<file_id>`** — `content_release_status_single`

- 🔗 URL: `<file_id>`
- 📤 Codes: ⚠️ 404

**`POST /content/save-encrypted`** — `content_save_encrypted`

- 📤 Codes: ⚠️ 400, ⚠️ 404, ❌ 500

**`POST /content/setup-enc-key`** — `content_setup_enc_key`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`POST /content/upload`** — `content_upload`  🎭 tracked

- 📥 `form.folder` (optional)
- 📤 Codes: ⚠️ 400

### pages

**`GET /pages/build-status/<name>`** — `build_status_route`

- 🔗 URL: `<name>`

**`POST /pages/build-stream/<name>`** — `build_stream_route`

- 🔗 URL: `<name>`
- 📥 `query.clean` (optional)
- 📥 `query.wipe` (optional)
- 📥 `query.no_minify` (optional)

**`POST /pages/build/<name>`** — `build_segment_route`  🎭 tracked

- 🔗 URL: `<name>`

**`GET /pages/builders`** — `list_builders_route`

- 📥 `query.bust` (optional)

**`POST /pages/builders/<name>/install`** — `install_builder_route`

- 🔗 URL: `<name>`

**`POST /pages/patch-script`** — `patch_script`

- 📤 Codes: ⚠️ 400, ⚠️ 404, ⚠️ 409, ❌ 500

**`POST /pages/preview/<name>`** — `start_preview_route`

- 🔗 URL: `<name>`

**`DELETE /pages/preview/<name>`** — `stop_preview_route`

- 🔗 URL: `<name>`

**`GET /pages/resolve-file`** — `resolve_file_to_pages`

- 📥 `query.path` (optional)

**`POST /pages/scan-pipeline`** — `scan_pipeline`

- 📤 Codes: ⚠️ 400

**`GET /pages/segments`** — `list_segments`

- 📥 `query.bust` (optional)

**`POST /pages/segments`** — `create_segment`  🎭 tracked

- 📤 Codes: ⚠️ 400, ⚠️ 409

**`PUT /pages/segments/<name>`** — `update_segment_route`  🎭 tracked

- 🔗 URL: `<name>`
- 📤 Codes: ⚠️ 404

**`DELETE /pages/segments/<name>`** — `delete_segment_route`  🎭 tracked

- 🔗 URL: `<name>`

**`GET /pages/site/<segment>/<path:filepath>`** — `serve_pages_site`

- 🔗 URL: `<segment>`, `<filepath>`

### tab_mesh

**`POST /tab-mesh/cdp-invalidate`** — `tab_mesh_cdp_invalidate`

- 📤 Codes: ✅ 204

**`POST /tab-mesh/cdp-remediate`** — `cdp_remediate`

- 📤 Codes: ⚠️ 400, ❌ 500

**`POST /tab-mesh/discover-target`** — `discover_target`

- 📤 Codes: ⚠️ 400

**`POST /tab-mesh/focus`** — `focus_tab`

- 📤 Codes: ❌ 503

**`POST /tab-mesh/kill-chrome`** — `kill_chrome`

- 📤 Codes: ❌ 500

**`POST /tab-mesh/leave`** — `tab_mesh_leave`

- 📤 Codes: ✅ 204

**`POST /tab-mesh/restart-chrome`** — `restart_chrome`

- 📤 Codes: ⚠️ 400, ❌ 500

**`POST /tab-mesh/trigger-chrome-signin`** — `trigger_chrome_signin`

- 📤 Codes: ⚠️ 400, ❌ 500, ❌ 503

**`GET /tab-mesh/wsl-firewall-status`** — `wsl_firewall_status`

- 📥 `query.port` (optional)

**`POST /tab-mesh/wsl-fix-firewall`** — `wsl_fix_firewall`

- 📥 `body.port` (optional)
- 📥 `body.scope` (optional)
- 📤 Codes: ❌ 500, ❌ 504

**`POST /tab-mesh/wsl-install-curl`** — `wsl_install_curl`

- 📤 Codes: ❌ 500

**`POST /tab-mesh/wsl-remove-firewall`** — `wsl_remove_firewall`

- 📤 Codes: ❌ 500, ❌ 504

**`POST /tab-mesh/wsl-remove-portproxy`** — `wsl_remove_portproxy`

- 📤 Codes: ❌ 500, ❌ 504

**`POST /tab-mesh/wsl-setup-routing`** — `wsl_setup_routing`

- 📤 Codes: ⚠️ 400, ❌ 500

**`POST /tab-mesh/wsl-start-tunnel`** — `wsl_start_tunnel`

- 📤 Codes: ⚠️ 400, ❌ 500

**`POST /tab-mesh/wsl-test-hostname`** — `wsl_test_hostname`

- 📥 `body.port` (optional)

### docker

**`POST /docker/build`** — `docker_build`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`GET /docker/containers`** — `docker_containers`

- 📥 `query.all` (optional)

**`POST /docker/down`** — `docker_down`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`POST /docker/exec`** — `docker_exec`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`POST /docker/generate/compose`** — `generate_compose`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`POST /docker/generate/compose-wizard`** — `generate_compose_wizard`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`POST /docker/generate/dockerfile`** — `generate_dockerfile`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`POST /docker/generate/dockerignore`** — `generate_dockerignore`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`POST /docker/generate/write`** — `write_generated`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`GET /docker/inspect`** — `docker_inspect`

- 📥 `query.id` (optional)
- 📤 Codes: ⚠️ 400

**`GET /docker/logs`** — `docker_logs`

- 📥 `query.service` (optional)
- 📥 `query.tail` (optional)
- 📤 Codes: ⚠️ 400

**`POST /docker/prune`** — `docker_prune`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`POST /docker/pull`** — `docker_pull`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`POST /docker/restart`** — `docker_restart`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`POST /docker/rm`** — `docker_rm`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`POST /docker/rmi`** — `docker_rmi`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`GET /docker/status`** — `docker_status`

- 📥 `query.bust` (optional)

**`POST /docker/stream/<action>`** — `docker_stream`

- 🔗 URL: `<action>`
- 📤 Codes: ⚠️ 400

**`POST /docker/up`** — `docker_up`  🎭 tracked

- 📤 Codes: ⚠️ 400

### k8s

**`POST /k8s/apply`** — `k8s_apply`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`POST /k8s/delete`** — `k8s_delete`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`GET /k8s/describe`** — `k8s_describe`

- 📥 `query.kind` (optional)
- 📥 `query.name` (optional)
- 📥 `query.namespace` (optional)
- 📤 Codes: ⚠️ 400

**`GET /k8s/events`** — `k8s_events`

- 📥 `query.namespace` (optional)
- 📤 Codes: ⚠️ 400

**`POST /k8s/generate/manifests`** — `k8s_generate_manifests`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`POST /k8s/generate/wizard`** — `k8s_generate_wizard`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`POST /k8s/helm/install`** — `helm_install`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`GET /k8s/helm/list`** — `helm_list`

- 📥 `query.namespace` (optional)

**`POST /k8s/helm/template`** — `helm_template`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`POST /k8s/helm/upgrade`** — `helm_upgrade`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`GET /k8s/helm/values`** — `helm_values`

- 📥 `query.release` (optional)
- 📥 `query.namespace` (optional)
- 📤 Codes: ⚠️ 400

**`GET /k8s/namespaces`** — `k8s_namespaces`

- 📤 Codes: ⚠️ 400

**`GET /k8s/pod-logs`** — `k8s_pod_logs`

- 📥 `query.pod` (optional)
- 📥 `query.namespace` (optional)
- 📥 `query.tail` (optional)
- 📥 `query.container` (optional)
- 📤 Codes: ⚠️ 400

**`GET /k8s/resources`** — `k8s_resources`

- 📥 `query.namespace` (optional)
- 📥 `query.kind` (optional)

**`POST /k8s/scale`** — `k8s_scale`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`GET /k8s/status`** — `k8s_status`

- 📥 `query.bust` (optional)

**`GET /k8s/storageclasses`** — `k8s_storage_classes`

- 📤 Codes: ⚠️ 400

**`POST /k8s/wizard-state`** — `k8s_wizard_state_save`

- 📤 Codes: ⚠️ 400

### vault

**`POST /vault/activate-env`** — `vault_activate_env`

- 📤 Codes: ⚠️ 400

**`POST /vault/add-keys`** — `vault_add_keys`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`POST /vault/auto-lock`** — `vault_auto_lock`

- 📤 Codes: ⚠️ 400

**`POST /vault/create`** — `vault_create`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`POST /vault/export`** — `vault_export`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`POST /vault/import`** — `vault_import`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`POST /vault/lock`** — `vault_lock`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`POST /vault/register`** — `vault_register`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`POST /vault/unlock`** — `vault_unlock`  🎭 tracked

- 📤 Codes: ⚠️ 400

### backup

**`POST /backup/decrypt`** — `api_decrypt_backup`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`POST /backup/delete`** — `api_delete`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`GET /backup/download/<path:filepath>`** — `api_download`

- 🔗 URL: `<filepath>`
- 📤 Codes: ⚠️ 400, ⚠️ 404

**`POST /backup/encrypt`** — `api_encrypt_backup`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`GET /backup/folder-tree`** — `api_folder_tree`

- 📥 `query.depth` (optional)

**`POST /backup/import`** — `api_import`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`GET /backup/list`** — `api_list`

- 📥 `query.path` (optional)
- 📥 `query.check_release` (optional)
- 📤 Codes: ⚠️ 400

**`POST /backup/mark-special`** — `api_mark_special`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`GET /backup/preview`** — `api_preview`

- 📥 `query.path` (optional)
- 📤 Codes: ⚠️ 400

**`POST /backup/rename`** — `api_rename_backup`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`GET /backup/tree`** — `api_tree`

- 📥 `query.types` (optional)
- 📥 `query.path` (optional)
- 📥 `query.depth` (optional)
- 📥 `query.gitignore` (optional)
- 📤 Codes: ⚠️ 400, ⚠️ 404

**`POST /backup/upload`** — `api_upload`  🎭 tracked

- 📥 `form.target_folder` (optional)
- 📤 Codes: ⚠️ 400

### plans

**`POST /plans`** — `plans_create`  🎭 tracked

- 📤 Codes: ✅ 201, ⚠️ 400

**`GET /plans/<plan_id>`** — `plans_get`

- 🔗 URL: `<plan_id>`
- 📤 Codes: ⚠️ 404

**`PUT /plans/<plan_id>`** — `plans_update`  🎭 tracked

- 🔗 URL: `<plan_id>`
- 📤 Codes: ⚠️ 404

**`DELETE /plans/<plan_id>`** — `plans_delete`  🎭 tracked

- 🔗 URL: `<plan_id>`
- 📤 Codes: ⚠️ 404

**`POST /plans/<plan_id>/duplicate`** — `plans_duplicate`  🎭 tracked

- 🔗 URL: `<plan_id>`
- 📤 Codes: ✅ 201, ⚠️ 404

**`POST /plans/<plan_id>/execute`** — `plans_execute`  🎭 tracked

- 🔗 URL: `<plan_id>`
- 📤 Codes: ⚠️ 404, ⚠️ 409

**`GET /plans/<plan_id>/git-check`** — `plans_git_check`

- 🔗 URL: `<plan_id>`

**`POST /plans/add-to-git`** — `plans_add_to_git`  🎭 tracked

- 📤 Codes: ⚠️ 400, ⚠️ 404

**`POST /plans/remove-from-git`** — `plans_remove_from_git`  🎭 tracked

- 📤 Codes: ⚠️ 400, ⚠️ 404

**`GET /plans/results`** — `plans_list_results`

- 📥 `query.plan_id` (optional)
- 📥 `query.last` (optional)

**`GET /plans/results/<run_id>`** — `plans_get_result`

- 🔗 URL: `<run_id>`
- 📤 Codes: ⚠️ 404

**`POST /plans/run/<run_id>/cancel`** — `plans_cancel`  🎭 tracked

- 🔗 URL: `<run_id>`
- 📤 Codes: ⚠️ 404

**`POST /plans/run/<run_id>/resume`** — `plans_resume`  🎭 tracked

- 🔗 URL: `<run_id>`
- 📤 Codes: ⚠️ 404

**`POST /plans/run/<run_id>/skip`** — `plans_skip`  🎭 tracked

- 🔗 URL: `<run_id>`
- 📤 Codes: ⚠️ 404

**`POST /plans/sync-to-git`** — `plans_sync_to_git`  🎭 tracked

- 📤 Codes: ⚠️ 400, ⚠️ 404

### artifacts

**`GET /<name>/publishable`** — `publishable_artifacts`

- 🔗 URL: `<name>`
- 📤 Codes: ⚠️ 404

**`GET /<name>/release-notes`** — `release_notes_preview`

- 🔗 URL: `<name>`
- 📥 `query.since_tag` (optional)

**`POST /build/<name>/stream`** — `build_stream`

- 🔗 URL: `<name>`
- 📤 Codes: ⚠️ 404

**`POST /detect`** — `detect_targets`  🎭 tracked

- 📤 Codes: ⚠️ 404

**`POST /makefile/patch`** — `makefile_patch`  🎭 tracked

- 📤 Codes: ⚠️ 404, ❌ 500

**`POST /publish/<name>/stream`** — `publish_stream`

- 🔗 URL: `<name>`

**`POST /targets`** — `create_target`  🎭 tracked

- 📤 Codes: ⚠️ 400, ⚠️ 409

**`PUT /targets/<name>`** — `modify_target`  🎭 tracked

- 🔗 URL: `<name>`
- 📤 Codes: ⚠️ 404

**`DELETE /targets/<name>`** — `delete_target`  🎭 tracked

- 🔗 URL: `<name>`
- 📤 Codes: ⚠️ 404

**`GET /targets/<name>/status`** — `target_build_status`

- 🔗 URL: `<name>`
- 📤 Codes: ⚠️ 404

### mediator

**`POST /mediator/bust`** — `mediator_bust`

- 📤 Codes: ⚠️ 400, ❌ 500

**`GET /mediator/diag`** — `mediator_diag`

- 📤 Codes: ❌ 500

**`GET /mediator/diag/<path:path>`** — `mediator_diag_path`

- 🔗 URL: `<path>`
- 📤 Codes: ⚠️ 404, ❌ 500

**`POST /mediator/dispatch`** — `mediator_dispatch`

- 📤 Codes: ⚠️ 400, ❌ 500

**`GET /mediator/events/recent`** — `mediator_events_recent`

- 📥 `query.limit` (optional)
- 📤 Codes: ❌ 500

**`GET /mediator/index/delta`** — `mediator_index_delta`

- 📤 Codes: ❌ 500

**`POST /mediator/index/rebuild-peek`** — `mediator_index_rebuild_peek`

- 📤 Codes: ❌ 500

**`POST /mediator/index/rebuild-symbols`** — `mediator_index_rebuild_symbols`

- 📤 Codes: ❌ 500

**`POST /mediator/index/rescan`** — `mediator_index_rescan`

- 📤 Codes: ❌ 500

**`GET /mediator/index/status`** — `mediator_index_status`

- 📤 Codes: ❌ 500

**`POST /mediator/refresh`** — `mediator_refresh`

- 📤 Codes: ⚠️ 400, ❌ 500

**`POST /mediator/refresh-branch`** — `mediator_refresh_branch`

- 📤 Codes: ⚠️ 400, ❌ 500

**`POST /mediator/refresh-stale`** — `mediator_refresh_stale`

- 📤 Codes: ❌ 500

### devops

**`POST /devops/audit/dismissals`** — `audit_dismissals_add`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`DELETE /devops/audit/dismissals`** — `audit_dismissals_remove`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`POST /wizard/check-tools`** — `wizard_check_tools`

- 📤 Codes: ⚠️ 400

**`POST /wizard/compose-ci`** — `wizard_compose_ci`  🎭 tracked

- 📤 Codes: ⚠️ 400, ❌ 500

**`DELETE /wizard/config`** — `wizard_delete_config`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`GET /wizard/detect`** — `wizard_detect`

- 📥 `query.bust` (optional)

**`POST /wizard/setup`** — `wizard_setup`  🎭 tracked

- 📤 Codes: ⚠️ 400, ❌ 500

**`POST /wizard/validate`** — `wizard_validate`

- 📤 Codes: ⚠️ 400

### chat

**`POST /chat/delete-message`** — `chat_delete_message`  🎭 requires_gh_auth, requires_git_auth, tracked

- 📤 Codes: ⚠️ 400, ⚠️ 404, ❌ 500

**`POST /chat/delete-thread`** — `chat_delete_thread`  🎭 requires_gh_auth, requires_git_auth, tracked

- 📤 Codes: ⚠️ 400, ⚠️ 404, ❌ 500

**`GET /chat/messages`** — `chat_messages`

- 📥 `query.n` (optional)
- 📥 `query.thread_id` (optional)
- 📥 `query.run_id` (optional)
- 📤 Codes: ❌ 500

**`POST /chat/move-message`** — `chat_move_message`  🎭 requires_gh_auth, requires_git_auth, tracked

- 📤 Codes: ⚠️ 400, ⚠️ 404, ❌ 500

**`POST /chat/poll`** — `chat_poll`  🎭 requires_gh_auth, requires_git_auth

- 📤 Codes: ❌ 500

**`GET /chat/refs/autocomplete`** — `chat_autocomplete`

- 📥 `query.prefix` (optional)
- 📤 Codes: ❌ 500

**`GET /chat/refs/resolve`** — `chat_resolve_ref`

- 📥 `query.ref` (optional)
- 📤 Codes: ⚠️ 400, ⚠️ 404, ❌ 500

**`POST /chat/send`** — `chat_send`  🎭 requires_gh_auth, requires_git_auth, tracked

- 📤 Codes: ⚠️ 400, ❌ 500

**`POST /chat/sync`** — `chat_sync`  🎭 requires_gh_auth, requires_git_auth

- 📤 Codes: ❌ 500

**`GET /chat/threads`** — `chat_threads`

- 📤 Codes: ❌ 500

**`POST /chat/threads/create`** — `chat_thread_create`  🎭 requires_gh_auth, requires_git_auth, tracked

- 📤 Codes: ⚠️ 400, ❌ 500

**`POST /chat/update-message`** — `chat_update_message`  🎭 requires_gh_auth, requires_git_auth, tracked

- 📤 Codes: ⚠️ 400, ⚠️ 404, ❌ 500

### scripts

**`GET /scripts/history`** — `scripts_history`

- 📥 `query.last` (optional)
- 📥 `query.script_id` (optional)

**`GET /scripts/history/<run_id>`** — `scripts_history_detail`

- 🔗 URL: `<run_id>`
- 📤 Codes: ⚠️ 404

**`GET /scripts/info/<path:script_id>`** — `scripts_info`

- 🔗 URL: `<script_id>`
- 📤 Codes: ⚠️ 404

**`GET /scripts/list`** — `scripts_list`

- 📥 `query.category` (optional)
- 📥 `query.source` (optional)

**`POST /scripts/run`** — `scripts_run`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`POST /scripts/run/stream`** — `scripts_run_stream`

- 📤 Codes: ⚠️ 400, ⚠️ 404

**`GET /scripts/status/<run_id>`** — `scripts_status`

- 🔗 URL: `<run_id>`
- 📤 Codes: ⚠️ 404

### terraform

**`POST /terraform/apply`** — `tf_apply`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`POST /terraform/destroy`** — `tf_destroy`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`POST /terraform/fmt`** — `tf_fmt`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`POST /terraform/generate`** — `tf_generate`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`POST /terraform/init`** — `tf_init`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`GET /terraform/output`** — `tf_output`

- 📤 Codes: ⚠️ 400

**`POST /terraform/plan`** — `tf_plan`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`GET /terraform/status`** — `tf_status`

- 📥 `query.bust` (optional)

**`POST /terraform/validate`** — `tf_validate`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`POST /terraform/workspace/select`** — `tf_workspace_select`  🎭 tracked

- 📤 Codes: ⚠️ 400

### secrets

**`POST /env/cleanup`** — `api_env_cleanup`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`POST /gh/environment/create`** — `api_gh_environment_create`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`POST /secret/remove`** — `api_secret_remove`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`POST /secret/set`** — `api_secret_set`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`POST /secrets/push`** — `api_push_secrets`  🎭 tracked

- 📤 Codes: ⚠️ 400

### infra

**`GET /env/card-status`** — `env_card_status`

- 📥 `query.bust` (optional)

**`GET /infra/env/diff`** — `env_diff`

- 📥 `query.source` (optional)
- 📥 `query.target` (optional)
- 📤 Codes: ⚠️ 404

**`POST /infra/env/generate-env`** — `env_generate_env`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`POST /infra/env/generate-example`** — `env_generate_example`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`GET /infra/env/validate`** — `env_validate`

- 📥 `query.file` (optional)
- 📤 Codes: ⚠️ 404

**`GET /infra/env/vars`** — `env_vars`

- 📥 `query.file` (optional)
- 📥 `query.redact` (optional)
- 📤 Codes: ⚠️ 404

### trace

**`GET /trace/active`** — `trace_active`

- 📤 Codes: ❌ 500

**`POST /trace/delete`** — `trace_delete`  🎭 tracked

- 📤 Codes: ⚠️ 400, ⚠️ 404, ❌ 500

**`GET /trace/events`** — `trace_events`

- 📥 `query.trace_id` (optional)
- 📤 Codes: ⚠️ 400, ❌ 500

**`GET /trace/get`** — `trace_get`

- 📥 `query.trace_id` (optional)
- 📤 Codes: ⚠️ 400, ⚠️ 404, ❌ 500

**`GET /trace/list`** — `trace_list`

- 📥 `query.n` (optional)
- 📤 Codes: ❌ 500

**`POST /trace/share`** — `trace_share`  🎭 tracked

- 📤 Codes: ⚠️ 400, ⚠️ 404, ❌ 500

**`POST /trace/start`** — `trace_start`  🎭 tracked

- 📤 Codes: ❌ 500

**`POST /trace/stop`** — `trace_stop`  🎭 tracked

- 📤 Codes: ⚠️ 400, ⚠️ 404, ❌ 500

**`POST /trace/unshare`** — `trace_unshare`  🎭 tracked

- 📤 Codes: ⚠️ 400, ⚠️ 404, ❌ 500

**`POST /trace/update`** — `trace_update`  🎭 tracked

- 📤 Codes: ⚠️ 400, ⚠️ 404, ❌ 500

### api

**`GET /audit`** — `api_audit`

- 📥 `query.n` (optional)

**`GET /audit/activity`** — `api_audit_activity`

- 📥 `query.n` (optional)
- 📥 `query.offset` (optional)
- 📥 `query.limit` (optional)
- 📥 `query.card` (optional)
- 📥 `query.q` (optional)

**`GET /capabilities`** — `api_capabilities`

- 📤 Codes: ⚠️ 404

**`POST /detect`** — `api_detect`

- 📤 Codes: ⚠️ 400

**`POST /run`** — `api_run`

- 📤 Codes: ⚠️ 400

**`GET /status`** — `api_status`

- 📤 Codes: ⚠️ 404

### notifications

**`GET /errors`** — `list_errors`

- 📥 `query.page` (optional)
- 📥 `query.per_page` (optional)

**`POST /errors`** — `log_frontend_error`

- 📤 Codes: ⚠️ 400

**`GET /notifications`** — `list_notifications`

- 📥 `query.all` (optional)

**`DELETE /notifications/<notif_id>`** — `delete`  🎭 tracked

- 🔗 URL: `<notif_id>`
- 📤 Codes: ⚠️ 404

**`POST /notifications/dismiss`** — `dismiss`  🎭 tracked

- 📤 Codes: ⚠️ 400, ⚠️ 404

**`POST /notifications/silence`** — `silence`

- 📤 Codes: ⚠️ 400, ⚠️ 404

### quality

**`POST /quality/check`** — `quality_check`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`POST /quality/generate/config`** — `quality_generate_config`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`GET /quality/status`** — `quality_status`

- 📥 `query.bust` (optional)

### security_scan

**`POST /security/generate/gitignore`** — `security_generate_gitignore`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`GET /security/status`** — `security_status`

- 📥 `query.bust` (optional)

### packages

**`GET /packages/audit`** — `package_audit`

- 📥 `query.manager` (optional)
- 📤 Codes: ⚠️ 400

**`POST /packages/install`** — `package_install`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`GET /packages/list`** — `package_list`

- 📥 `query.manager` (optional)
- 📤 Codes: ⚠️ 400

**`GET /packages/outdated`** — `package_outdated`

- 📥 `query.manager` (optional)
- 📤 Codes: ⚠️ 400

**`GET /packages/status`** — `package_status`

- 📥 `query.bust` (optional)

**`POST /packages/update`** — `package_update`  🎭 tracked

- 📤 Codes: ⚠️ 400

### server

**`POST /server/accept-port`** — `server_accept_port`

- 📤 Codes: ⚠️ 400, ❌ 500

**`POST /server/factory-reset`** — `server_factory_reset_route`  🎭 tracked

- 📤 Codes: ❌ 500

**`POST /server/restart`** — `server_restart_route`  🎭 tracked

- 📤 Codes: ❌ 500

### ci

**`POST /ci/generate/ci`** — `generate_ci`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`POST /ci/generate/lint`** — `generate_lint`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`GET /ci/status`** — `ci_status`

- 📥 `query.bust` (optional)

### docs

**`POST /docs/generate/changelog`** — `docs_generate_changelog`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`GET /docs/links`** — `docs_links`

- 📥 `query.file` (optional)

**`GET /docs/status`** — `docs_status`

- 📥 `query.bust` (optional)

### git_auth

**`POST /git/auth-https`** — `auth_https`

- 📤 Codes: ⚠️ 400, ❌ 500

**`POST /git/auth-ssh`** — `auth_ssh`

- 📤 Codes: ⚠️ 400, ❌ 500

**`GET /git/auth-status`** — `auth_status`

- 📤 Codes: ❌ 500

**`GET /git/identity`** — `identity_status`

- 📤 Codes: ❌ 500

**`POST /git/identity`** — `identity_set`

- 📤 Codes: ⚠️ 400, ❌ 500

### smart_folders

**`GET /smart-folders/<name>/file`** — `api_smart_folders_file`

- 🔗 URL: `<name>`
- 📥 `query.path` (optional)
- 📤 Codes: ⚠️ 400, ⚠️ 403, ⚠️ 404, ❌ 500

**`GET /smart-folders/<name>/peek`** — `api_smart_folders_peek`

- 🔗 URL: `<name>`
- 📥 `query.module` (optional)
- 📥 `query.topic` (optional)
- 📤 Codes: ⚠️ 400, ⚠️ 404

**`GET /smart-folders/<name>/tree`** — `api_smart_folders_tree`

- 🔗 URL: `<name>`
- 📤 Codes: ⚠️ 404

**`GET /smart-folders/discover`** — `api_smart_folders_discover`

- 📥 `query.pattern` (optional)

### testing

**`POST /testing/generate/template`** — `testing_generate_template`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`POST /testing/run`** — `testing_run`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`GET /testing/status`** — `testing_status`

- 📥 `query.bust` (optional)

### dns

**`POST /dns/generate`** — `dns_generate`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`GET /dns/lookup/<domain>`** — `dns_lookup`

- 🔗 URL: `<domain>`
- 📤 Codes: ⚠️ 400

**`GET /dns/ssl/<domain>`** — `dns_ssl`

- 🔗 URL: `<domain>`
- 📤 Codes: ⚠️ 400

**`GET /dns/status`** — `dns_status`

- 📥 `query.bust` (optional)

### config

**`GET /config`** — `api_config_read`

- 📤 Codes: ❌ 500

**`POST /config`** — `api_config_save`  🎭 tracked

- 📤 Codes: ⚠️ 400

**`GET /config/content-folders`** — `api_config_content_folders`

- 📥 `query.include_hidden` (optional)

### dev

**`GET /dev/scenarios`** — `dev_scenarios`

- 📥 `query.system` (optional)

**`GET /dev/scenarios/<scenario_id>`** — `dev_scenario_by_id`

- 🔗 URL: `<scenario_id>`
- 📥 `query.system` (optional)
- 📤 Codes: ⚠️ 404

### metrics

**`GET /metrics/health`** — `project_health`

- 📥 `query.bust` (optional)

### project

**`GET /project/next`** — `project_next`

- 📥 `query.bust` (optional)

**`GET /project/status`** — `project_status`

- 📥 `query.bust` (optional)

### events

**`GET /events`** — `event_stream`

- 📥 `query.since` (optional)

## Complexity Analysis

### Size Distribution

🟢 **Small**: `██████████████░░░░░░` 344 routes (68%)
🟡 **Medium**: `█████░░░░░░░░░░░░░░░` 115 routes (23%)
🟠 **Large**: `█░░░░░░░░░░░░░░░░░░░` 34 routes (7%)
🔴 **Very Large**: `█░░░░░░░░░░░░░░░░░░░` 14 routes (3%)

### Highest Complexity Routes

> Sorted by composite complexity: body lines × branch count × nesting depth.

| # | Function | Blueprint | Lines | Branches | Depth | Complexity |
|---|----------|-----------|-------|----------|-------|-----------|
| 1 | `audit_execute_plan` | audit | 536 | 57 | 6 | **183,312** |
| 2 | `cdp_test_record_event` | cdp_test | 332 | 35 | 6 | **69,720** |
| 3 | `wsl_channel_status` | tab_mesh | 182 | 12 | 7 | **15,288** |
| 4 | `audit_resume_plan` | audit | 193 | 15 | 3 | **8,685** |
| 5 | `wsl_start_tunnel` | tab_mesh | 144 | 15 | 4 | **8,640** |
| 6 | `cdp_test_replay_start` | cdp_test | 186 | 15 | 3 | **8,370** |
| 7 | `cdp_diagnose` | tab_mesh | 139 | 12 | 4 | **6,672** |
| 8 | `makefile_patch` | artifacts | 100 | 13 | 5 | **6,500** |
| 9 | `scripts_run_stream` | scripts | 173 | 12 | 3 | **6,228** |
| 10 | `wsl_install_curl` | tab_mesh | 117 | 11 | 4 | **5,148** |
| 11 | `chat_poll` | chat | 70 | 10 | 6 | **4,200** |
| 12 | `audit_deep_detect` | audit | 94 | 14 | 3 | **3,948** |
| 13 | `cdp_remediate` | tab_mesh | 117 | 9 | 3 | **3,159** |
| 14 | `project_health` | metrics | 69 | 11 | 4 | **3,036** |
| 15 | `content_preview` | content | 89 | 11 | 3 | **2,937** |

### Docstring Quality

| Tier | Count | Description |
|------|-------|-------------|
| 🟢 Detailed (5+ lines) | 180 | Comprehensive documentation |
| 🟡 Brief (1-4 lines) | 322 | Short description |
| 🔴 Missing | 5 | No docstring |

**Missing docstrings:**
- `audit.audit_system` (/audit/system)
- `audit.audit_dependencies` (/audit/dependencies)
- `audit.audit_structure` (/audit/structure)
- `audit.audit_clients` (/audit/clients)
- `audit.audit_scores_endpoint` (/audit/scores)

## Consistency Matrix

> Cross-blueprint pattern comparison. Highlights where a blueprint deviates from the project norm.

> **Project norms**: docs=99%, tracking=0%, error handling=21%, explicit methods=60%

| Blueprint | Routes | Docs | Track | ErrH | Methods | vs Norm |
|-----------|--------|------|-------|------|---------|---------|
| **audit** | 46 | 89% | 0% | 13% | 61% | ≈ |
| **integrations** | 43 | 100% | 0% | 5% | 56% | 🛡️↓ |
| **cdp_test** | 36 | 100% | 0% | 14% | 69% | ≈ |
| **content** | 30 | 100% | 0% | 23% | 63% | ≈ |
| **pages** | 27 | 100% | 0% | 11% | 63% | ≈ |
| **tab_mesh** | 27 | 100% | 0% | 56% | 67% | 🛡️↑ |
| **docker** | 24 | 100% | 0% | 0% | 62% | 🛡️↓ |
| **k8s** | 24 | 100% | 0% | 0% | 46% | 🛡️↓ |
| **vault** | 21 | 100% | 0% | 29% | 76% | ≈ |
| **backup** | 18 | 100% | 0% | 11% | 67% | ≈ |
| **plans** | 17 | 100% | 0% | 0% | 65% | 🛡️↓ |
| **artifacts** | 16 | 100% | 0% | 25% | 100% | 📋↑ |
| **mediator** | 15 | 100% | 0% | 93% | 67% | 🛡️↑ |
| **devops** | 13 | 100% | 0% | 23% | 92% | 📋↑ |
| **chat** | 12 | 100% | 0% | 100% | 67% | 🛡️↑ |
| **scripts** | 12 | 100% | 0% | 17% | 25% | 📋↓ |
| **terraform** | 12 | 100% | 0% | 0% | 67% | 🛡️↓ |
| **secrets** | 11 | 100% | 0% | 0% | 64% | 🛡️↓ |
| **infra** | 10 | 100% | 0% | 0% | 20% | 🛡️↓ 📋↓ |
| **trace** | 10 | 100% | 0% | 100% | 60% | 🛡️↑ |
| **api** | 9 | 100% | 0% | 11% | 33% | 📋↓ |
| **notifications** | 8 | 100% | 0% | 0% | 62% | 🛡️↓ |
| **quality** | 7 | 100% | 0% | 0% | 86% | 🛡️↓ 📋↑ |
| **security_scan** | 7 | 100% | 0% | 14% | 14% | 📋↓ |
| **packages** | 6 | 100% | 0% | 0% | 33% | 🛡️↓ 📋↓ |
| **server** | 6 | 100% | 0% | 33% | 83% | 📋↑ |
| **ci** | 5 | 100% | 0% | 0% | 40% | 🛡️↓ |
| **docs** | 5 | 100% | 0% | 0% | 40% | 🛡️↓ |
| **git_auth** | 5 | 100% | 0% | 100% | 60% | 🛡️↑ |
| **smart_folders** | 5 | 100% | 0% | 40% | 0% | 📋↓ |
| **testing** | 5 | 100% | 0% | 0% | 60% | 🛡️↓ |
| **dns** | 4 | 100% | 0% | 0% | 25% | 🛡️↓ 📋↓ |
| **config** | 3 | 100% | 0% | 0% | 33% | 🛡️↓ 📋↓ |
| **dev** | 3 | 100% | 0% | 0% | 0% | 🛡️↓ 📋↓ |
| **metrics** | 2 | 100% | 0% | 50% | 0% | 📋↓ |
| **project** | 2 | 100% | 0% | 0% | 0% | 🛡️↓ 📋↓ |
| **events** | 1 | 100% | 0% | 100% | 0% | 🛡️↑ 📋↓ |

## Anomaly Detection

> Routes that break the dominant pattern of their blueprint. Not violations — just observations worth reviewing.

### audit

- 📏 Avg body 35 lines — outliers: `audit_execute_plan` (536L), `audit_resume_plan` (193L)
- 📝 41/46 documented — missing: `audit_system`, `audit_dependencies`, `audit_structure`, `audit_clients`, `audit_scores_endpoint`

### integrations

- 📏 Avg body 11 lines — outliers: `git_commit` (54L), `gh_auth_terminal_poll_route` (53L)

### cdp_test

- 📏 Avg body 45 lines — outliers: `cdp_test_record_event` (332L), `cdp_test_replay_start` (186L)

### content

- 🛡️ Only 7/30 routes have error handling: `content_metadata`, `content_outline`, `peek_refs`, `peek_resolve`, `content_preview`
- 📏 Avg body 28 lines — outliers: `content_preview_encrypted` (110L), `peek_refs` (96L), `content_glossary` (93L)

### pages

- 📏 Avg body 10 lines — outliers: `patch_script` (63L)

### tab_mesh

- 🛡️ 15/27 routes have error handling — without: `cdp_status`, `focus_tab`, `cdp_diagnose`, `cdp_remediate`, `trigger_chrome_signin`

### vault

- 🛡️ Only 6/21 routes have error handling: `vault_lock`, `vault_unlock`, `vault_register`, `vault_auto_lock`, `vault_export`

### plans

- 📏 Avg body 21 lines — outliers: `plans_execute` (74L)

### artifacts

- 🛡️ Only 4/16 routes have error handling: `create_target`, `modify_target`, `delete_target`, `makefile_patch`
- 📏 Avg body 20 lines — outliers: `makefile_patch` (100L)

### mediator

- 📏 Avg body 27 lines — outliers: `mediator_index_status` (83L)

### devops

- 🛡️ Only 3/13 routes have error handling: `devops_cache_bust`, `wizard_setup`, `wizard_compose_ci`

### scripts

- 📏 Avg body 42 lines — outliers: `scripts_run_stream` (173L)

### server

- 🛡️ Only 2/6 routes have error handling: `server_factory_reset_route`, `server_accept_port`

### smart_folders

- 🛡️ Only 2/5 routes have error handling: `api_smart_folders_list`, `api_smart_folders_file`
