# Route Quality Audit

> Generated: 2026-03-08 15:40 UTC  |  Framework: flask  |  Style: **smart**

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
| Blueprints | **34** |
| Routes | **414** |
| 📝 Docstrings | **99%** (409/414) |
| 📊 Run tracking | **28%** (116/414) |
| 🛡️ Error handling | **17%** (70/414) |
| 📋 Explicit methods | **57%** (238/414) |
| 🎭 Unique decorators | **3** |
| 📏 Avg body size | **19 lines** |
| 🔀 Avg branches | **1.7** |
| 📌 Init-file routes | **12** / 34 blueprints |

## API Surface Map

> Endpoint tree organized by blueprint. Each route shows its HTTP method, decorators, and detected parameters.

### 📦 audit (44 routes)

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
  POST    /audit/install-plan/cache  [run_tracked]  → 400
  POST    /audit/install-plan/cancel  → 400,404
  POST    /audit/install-plan/execute  [run_tracked]  → 400
  POST    /audit/install-plan/execute-sync  [run_tracked]  → 400
  GET     /audit/install-plan/pending
  POST    /audit/install-plan/resume  → 400
  POST    /audit/install-tool  [run_tracked]
  POST    /audit/remediate  → 400
  POST    /audit/remove-tool  [run_tracked]  → 400,500
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
  POST    /audit/update-tool  [run_tracked]  → 400
  POST    /audits/discard
  GET     /audits/pending
  GET     /audits/pending/<snapshot_id> <snapshot_id>  → 404
  POST    /audits/save
  GET     /audits/saved
  GET     /audits/saved/<snapshot_id> <snapshot_id>  → 404
  DELETE  /audits/saved/<snapshot_id> <snapshot_id>  → 404,500
  GET     /tools/status
```

> CRUD: **CRD** — missing: Update/PUT

### 📦 integrations (42 routes)

```
  POST    /gh/actions/dispatch  [run_tracked, requires_gh_auth]  → 400
  GET     /gh/actions/runs  [requires_gh_auth]  ← query:n?, query:bust?
  GET     /gh/actions/workflows  [requires_gh_auth]  ← query:bust?
  POST    /gh/auth/device  [run_tracked]  → 200
  GET     /gh/auth/device/poll  ← query:session?  → 400
  POST    /gh/auth/login  [run_tracked]
  POST    /gh/auth/logout  [run_tracked]  → 400
  GET     /gh/auth/terminal/poll
  GET     /gh/auth/token
  GET     /gh/pulls  [requires_gh_auth]  ← query:bust?
  POST    /gh/repo/create  [run_tracked, requires_gh_auth]  → 400
  POST    /gh/repo/default-branch  [run_tracked, requires_gh_auth]  → 400
  GET     /gh/repo/info  [requires_gh_auth]
  POST    /gh/repo/rename  [run_tracked, requires_gh_auth]  → 400
  POST    /gh/repo/visibility  [run_tracked, requires_gh_auth]  → 400
  GET     /gh/user  [requires_gh_auth]
  POST    /git/checkout-file  [run_tracked]  → 400
  POST    /git/commit  [run_tracked]  → 400
  GET     /git/diff
  GET     /git/diff/file  ← query:path?, query:staged?  → 400
  POST    /git/filter-repo  [requires_git_auth, run_tracked]  → 400
  POST    /git/gc  [run_tracked]  → 400
  POST    /git/history-reset  [requires_git_auth, run_tracked]  → 400
  GET     /git/log  ← query:n?
  GET     /git/merge-status
  POST    /git/merge/abort  [run_tracked]  → 400
  POST    /git/pull  [requires_git_auth, run_tracked]  → 400
  POST    /git/push  [requires_git_auth, run_tracked]  → 400
  POST    /git/remote/add  [run_tracked]  → 400
  POST    /git/remote/remove  [run_tracked]  → 400
  POST    /git/remote/rename  [run_tracked]  → 400
  POST    /git/remote/set-url  [run_tracked]  → 400
  GET     /git/remotes
  POST    /git/stash  [run_tracked]  → 400
  GET     /git/stash/list
  POST    /git/stash/pop  [run_tracked]  → 400
  GET     /git/status  ← query:bust?
  GET     /github/status
  GET     /integrations/gh/status  ← query:bust?
  POST    /ledger/resolve-conflict  → 400
  GET     /ledger/sync-status
  GET     /ops/terminal/status
```

> CRUD: **CR** — missing: Update/PUT, Delete/DELETE

### 📦 content (30 routes)

```
  GET     /content/all-folders
  POST    /content/clean-release-sidecar  → 400,404
  POST    /content/create-folder
  POST    /content/decrypt  [run_tracked]  → 400
  POST    /content/delete
  GET     /content/download  ← query:path?, query:download?  → 400,404
  GET     /content/enc-key-status
  POST    /content/encrypt  [run_tracked]  → 400
  GET     /content/folders
  GET     /content/glossary  ← query:smart_folder?, query:path?, query:recursive?  → 400,404
  GET     /content/list  ← query:path?, query:recursive?, query:check_release?  → 400,404
  GET     /content/metadata  ← query:path?  → 400,404
  POST    /content/move
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
  POST    /content/rename
  POST    /content/restore-large
  POST    /content/save
  POST    /content/save-encrypted  → 400,404,500
  POST    /content/setup-enc-key  → 400
  POST    /content/upload  ← form:folder?  → 400
```

> CRUD: **CR** — missing: Update/PUT, Delete/DELETE

### 📦 pages (27 routes)

```
  GET     /
  POST    /pages/build-all  [run_tracked]
  GET     /pages/build-status/<name> <name>
  POST    /pages/build-stream/<name> <name>  ← query:clean?, query:wipe?, query:no_minify?
  POST    /pages/build/<name> <name>  [run_tracked]
  GET     /pages/builders
  POST    /pages/builders/<name>/install <name>
  POST    /pages/ci  [run_tracked]
  POST    /pages/deploy  [requires_git_auth, run_tracked]
  POST    /pages/detect
  GET     /pages/features
  POST    /pages/init  [run_tracked]
  POST    /pages/merge  [run_tracked]
  GET     /pages/meta
  POST    /pages/meta
  POST    /pages/patch-script  → 400,404,409,500
  POST    /pages/preview/<name> <name>
  DELETE  /pages/preview/<name> <name>
  GET     /pages/previews
  GET     /pages/resolve-file  ← query:path?
  POST    /pages/scan-pipeline  → 400
  GET     /pages/segments  ← query:bust?
  POST    /pages/segments  → 400,409
  PUT     /pages/segments/<name> <name>  → 404
  DELETE  /pages/segments/<name> <name>
  GET     /pages/site/<segment>/<path:filepath> <segment> <filepath>
  GET     /sw.js
```

> CRUD: **CRUD** — complete

### 📦 docker (24 routes)

```
  POST    /docker/build  [run_tracked]  → 400
  GET     /docker/compose/status
  GET     /docker/containers  ← query:all?
  POST    /docker/down  [run_tracked]  → 400
  POST    /docker/exec  [run_tracked]  → 400
  POST    /docker/generate/compose  [run_tracked]  → 400
  POST    /docker/generate/compose-wizard  [run_tracked]  → 400
  POST    /docker/generate/dockerfile  [run_tracked]  → 400
  POST    /docker/generate/dockerignore  [run_tracked]  → 400
  POST    /docker/generate/write  [run_tracked]  → 400
  GET     /docker/images
  GET     /docker/inspect  ← query:id?  → 400
  GET     /docker/logs  ← query:service?, query:tail?  → 400
  GET     /docker/networks
  POST    /docker/prune  [run_tracked]  → 400
  POST    /docker/pull  [run_tracked]  → 400
  POST    /docker/restart  [run_tracked]  → 400
  POST    /docker/rm  [run_tracked]  → 400
  POST    /docker/rmi  [run_tracked]  → 400
  GET     /docker/stats
  GET     /docker/status  ← query:bust?
  POST    /docker/stream/<action> <action>  → 400
  POST    /docker/up  [run_tracked]  → 400
  GET     /docker/volumes
```

> CRUD: **CR** — missing: Update/PUT, Delete/DELETE

### 📦 k8s (24 routes)

```
  POST    /k8s/apply  [run_tracked]  → 400
  GET     /k8s/cluster
  POST    /k8s/delete  [run_tracked]  → 400
  GET     /k8s/describe  ← query:kind?, query:name?, query:namespace?  → 400
  GET     /k8s/env-namespaces
  GET     /k8s/events  ← query:namespace?  → 400
  POST    /k8s/generate/manifests  [run_tracked]  → 400
  POST    /k8s/generate/wizard  [run_tracked]  → 400
  POST    /k8s/helm/install  [run_tracked]  → 400
  GET     /k8s/helm/list  ← query:namespace?
  POST    /k8s/helm/template  [run_tracked]  → 400
  POST    /k8s/helm/upgrade  [run_tracked]  → 400
  GET     /k8s/helm/values  ← query:release?, query:namespace?  → 400
  GET     /k8s/namespaces  → 400
  GET     /k8s/pod-logs  ← query:pod?, query:namespace?, query:tail?, query:container?  → 400
  GET     /k8s/resources  ← query:namespace?, query:kind?
  POST    /k8s/scale  [run_tracked]  → 400
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
  POST    /vault/add-keys  → 400
  POST    /vault/auto-lock  → 400
  POST    /vault/create  [run_tracked]  → 400
  POST    /vault/delete-key
  POST    /vault/export  [run_tracked]  → 400
  POST    /vault/import  [run_tracked]  → 400
  GET     /vault/keys
  POST    /vault/lock  [run_tracked]  → 400
  POST    /vault/move-key
  POST    /vault/raw-value
  POST    /vault/register  [run_tracked]  → 400
  POST    /vault/rename-section
  GET     /vault/secrets
  POST    /vault/set-meta
  GET     /vault/status
  GET     /vault/templates
  POST    /vault/toggle-local-only
  POST    /vault/unlock  [run_tracked]  → 400
  POST    /vault/update-key
```

> CRUD: **CR** — missing: Update/PUT, Delete/DELETE

### 📦 backup (18 routes)

```
  POST    /backup/decrypt  [run_tracked]  → 400
  POST    /backup/delete  [run_tracked]  → 400
  POST    /backup/delete-release  [run_tracked]
  GET     /backup/download/<path:filepath> <filepath>  → 400,404
  POST    /backup/encrypt  [run_tracked]  → 400
  POST    /backup/export  [run_tracked]
  GET     /backup/folder-tree  ← query:depth?
  GET     /backup/folders
  POST    /backup/import  [run_tracked]  → 400
  GET     /backup/list  ← query:path?, query:check_release?  → 400
  POST    /backup/mark-special  [run_tracked]  → 400
  GET     /backup/preview  ← query:path?  → 400
  POST    /backup/rename  [run_tracked]  → 400
  POST    /backup/restore  [run_tracked]
  GET     /backup/tree  ← query:types?, query:path?, query:depth?, query:gitignore?  → 400,404
  POST    /backup/upload  [run_tracked]  ← form:target_folder?  → 400
  POST    /backup/upload-release  [run_tracked]
  POST    /backup/wipe  [run_tracked]
```

> CRUD: **CR** — missing: Update/PUT, Delete/DELETE

### 📦 artifacts (16 routes)

```
  GET     /<name>/publishable <name>  → 404
  GET     /<name>/release-notes <name>  ← query:since_tag?
  POST    /build/<name>/stream <name>  → 404
  GET     /builders
  POST    /detect  → 404
  GET     /makefile/evolution
  POST    /makefile/patch  → 404,500
  POST    /publish/<name>/stream <name>
  GET     /publish/capabilities
  GET     /targets
  POST    /targets  → 400,409
  PUT     /targets/<name> <name>  → 404
  DELETE  /targets/<name> <name>  → 404
  GET     /targets/<name>/status <name>  → 404
  POST    /workflow/generate
  GET     /workflow/preview
```

> CRUD: **CRUD** — complete

### 📦 devops (13 routes)

```
  POST    /devops/audit/dismissals  [run_tracked]  → 400
  DELETE  /devops/audit/dismissals  [run_tracked]  → 400
  POST    /devops/cache/bust
  GET     /devops/integration-prefs
  PUT     /devops/integration-prefs
  GET     /devops/prefs
  PUT     /devops/prefs
  POST    /wizard/check-tools  → 400
  POST    /wizard/compose-ci  [run_tracked]  → 400,500
  DELETE  /wizard/config  [run_tracked]  → 400
  GET     /wizard/detect  ← query:bust?
  POST    /wizard/setup  [run_tracked]  → 400,500
  POST    /wizard/validate  → 400
```

> CRUD: **CRUD** — complete

### 📦 chat (12 routes)

```
  POST    /chat/delete-message  [requires_gh_auth, requires_git_auth]  → 400,404,500
  POST    /chat/delete-thread  [requires_gh_auth, requires_git_auth]  → 400,404,500
  GET     /chat/messages  ← query:n?, query:thread_id?, query:run_id?  → 500
  POST    /chat/move-message  [requires_gh_auth, requires_git_auth]  → 400,404,500
  POST    /chat/poll  [requires_gh_auth, requires_git_auth]  → 500
  GET     /chat/refs/autocomplete  ← query:prefix?  → 500
  GET     /chat/refs/resolve  ← query:ref?  → 400,404,500
  POST    /chat/send  [requires_gh_auth, requires_git_auth]  → 400,500
  POST    /chat/sync  [requires_gh_auth, requires_git_auth]  → 500
  GET     /chat/threads  → 500
  POST    /chat/threads/create  [requires_gh_auth, requires_git_auth]  → 400,500
  POST    /chat/update-message  [requires_gh_auth, requires_git_auth]  → 400,404,500
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
  POST    /scripts/run  → 400
  POST    /scripts/run/stream  → 400,404
  GET     /scripts/status/<run_id> <run_id>  → 404
  GET     /scripts/templates
```

> CRUD: **CR** — missing: Update/PUT, Delete/DELETE

### 📦 terraform (12 routes)

```
  POST    /terraform/apply  [run_tracked]  → 400
  POST    /terraform/destroy  [run_tracked]  → 400
  POST    /terraform/fmt  [run_tracked]  → 400
  POST    /terraform/generate  [run_tracked]  → 400
  POST    /terraform/init  [run_tracked]  → 400
  GET     /terraform/output  → 400
  POST    /terraform/plan  [run_tracked]  → 400
  GET     /terraform/state
  GET     /terraform/status  ← query:bust?
  POST    /terraform/validate  [run_tracked]  → 400
  POST    /terraform/workspace/select  [run_tracked]  → 400
  GET     /terraform/workspaces
```

> CRUD: **CR** — missing: Update/PUT, Delete/DELETE

### 📦 secrets (11 routes)

```
  POST    /env/cleanup  [run_tracked]  → 400
  POST    /env/seed  [run_tracked]
  GET     /gh/auto
  POST    /gh/environment/create  [run_tracked]  → 400
  GET     /gh/environments
  GET     /gh/secrets
  GET     /gh/status
  POST    /keys/generate  [run_tracked]
  POST    /secret/remove  [run_tracked]  → 400
  POST    /secret/set  [run_tracked]  → 400
  POST    /secrets/push  [run_tracked]  → 400
```

> CRUD: **CR** — missing: Update/PUT, Delete/DELETE

### 📦 infra (10 routes)

```
  GET     /env/card-status  ← query:bust?
  GET     /infra/env/diff  ← query:source?, query:target?  → 404
  POST    /infra/env/generate-env  [run_tracked]  → 400
  POST    /infra/env/generate-example  [run_tracked]  → 400
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
  POST    /trace/delete  → 400,404,500
  GET     /trace/events  ← query:trace_id?  → 400,500
  GET     /trace/get  ← query:trace_id?  → 400,404,500
  GET     /trace/list  ← query:n?  → 500
  POST    /trace/share  → 400,404,500
  POST    /trace/start  → 500
  POST    /trace/stop  → 400,404,500
  POST    /trace/unshare  → 400,404,500
  POST    /trace/update  → 400,404,500
```

> CRUD: **CR** — missing: Update/PUT, Delete/DELETE

### 📦 tab_mesh (9 routes)

```
  GET     /tab-mesh/cdp-diagnose
  POST    /tab-mesh/cdp-remediate  → 400,500
  GET     /tab-mesh/cdp-status
  POST    /tab-mesh/discover-target  → 400
  POST    /tab-mesh/focus  → 503
  POST    /tab-mesh/kill-chrome  → 400,500
  POST    /tab-mesh/restart-chrome  → 400,500
  POST    /tab-mesh/suggest-cdp
  POST    /tab-mesh/trigger-chrome-signin  → 400,500,503
```

> CRUD: **CR** — missing: Update/PUT, Delete/DELETE

### 📦 api (8 routes)

```
  GET     /audit  ← query:n?
  GET     /audit/activity  ← query:n?, query:offset?, query:limit?, query:card?, query:q?
  GET     /capabilities  → 404
  POST    /detect  → 400
  GET     /health
  POST    /run  → 400
  GET     /stacks
  GET     /status  → 404
```

> CRUD: **CR** — missing: Update/PUT, Delete/DELETE

### 📦 notifications (7 routes)

```
  GET     /errors  ← query:page?, query:per_page?
  POST    /errors  → 400
  POST    /errors/ack
  GET     /notifications  ← query:all?
  DELETE  /notifications/<notif_id> <notif_id>  → 404
  GET     /notifications/badge
  POST    /notifications/dismiss  → 400,404
```

> CRUD: **CRD** — missing: Update/PUT

### 📦 quality (7 routes)

```
  POST    /quality/check  [run_tracked]  → 400
  POST    /quality/format  [run_tracked]
  POST    /quality/generate/config  [run_tracked]  → 400
  POST    /quality/lint  [run_tracked]
  GET     /quality/status  ← query:bust?
  POST    /quality/test  [run_tracked]
  POST    /quality/typecheck  [run_tracked]
```

> CRUD: **CR** — missing: Update/PUT, Delete/DELETE

### 📦 security_scan (7 routes)

```
  GET     /security/files
  POST    /security/generate/gitignore  [run_tracked]  → 400
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
  POST    /packages/install  [run_tracked]  → 400
  GET     /packages/list  ← query:manager?  → 400
  GET     /packages/outdated  ← query:manager?  → 400
  GET     /packages/status  ← query:bust?
  POST    /packages/update  [run_tracked]  → 400
```

> CRUD: **CR** — missing: Update/PUT, Delete/DELETE

### 📦 ci (5 routes)

```
  GET     /ci/coverage
  POST    /ci/generate/ci  [run_tracked]  → 400
  POST    /ci/generate/lint  [run_tracked]  → 400
  GET     /ci/status  ← query:bust?
  GET     /ci/workflows
```

> CRUD: **CR** — missing: Update/PUT, Delete/DELETE

### 📦 docs (5 routes)

```
  GET     /docs/coverage
  POST    /docs/generate/changelog  [run_tracked]  → 400
  POST    /docs/generate/readme  [run_tracked]
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
  POST    /testing/coverage  [run_tracked]
  POST    /testing/generate/template  [run_tracked]  → 400
  GET     /testing/inventory
  POST    /testing/run  [run_tracked]  → 400
  GET     /testing/status  ← query:bust?
```

> CRUD: **CR** — missing: Update/PUT, Delete/DELETE

### 📦 dns (4 routes)

```
  POST    /dns/generate  [run_tracked]  → 400
  GET     /dns/lookup/<domain> <domain>  → 400
  GET     /dns/ssl/<domain> <domain>  → 400
  GET     /dns/status  ← query:bust?
```

> CRUD: **CR** — missing: Update/PUT, Delete/DELETE

### 📦 server (4 routes)

```
  POST    /server/restart  → 500
  GET     /server/settings
  PUT     /server/settings
  GET     /server/status
```

> CRUD: **CRU** — missing: Delete/DELETE

### 📦 config (3 routes)

```
  GET     /config  → 500
  POST    /config  [run_tracked]  → 400
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
  analysis.py                     11 routes    112 lines
  async_scan.py                    2 routes     66 lines
  deep_detection.py                1 routes     94 lines
  offline_cache.py                 7 routes    130 lines
  staging.py                       7 routes     68 lines
  tool_execution.py                6 routes    761 lines
  tool_install.py                 10 routes    267 lines
```

> Naming: 43/44 functions (97%) follow `audit_*` convention

### 📁 integrations/

```
  gh_auth.py                       6 routes    148 lines
  gh_repo.py                       4 routes     49 lines
  git.py                          15 routes    147 lines
  github.py                        8 routes     55 lines
  history.py                       3 routes     52 lines
  remotes.py                       5 routes     39 lines
  terminal.py                      1 routes      3 lines
```

### 📁 content/

```
  __init__.py                      6 routes    136 lines (📌 init)
  files.py                         7 routes     79 lines
  manage.py                       10 routes    100 lines
  outline.py                       2 routes    129 lines
  peek.py                          2 routes    158 lines
  preview.py                       3 routes    226 lines
```

> Naming: 28/30 functions (93%) follow `content_*` convention

### 📁 pages/

```
  api.py                          24 routes    238 lines
  serving.py                       3 routes     55 lines
```

### 📁 docker/

```
  actions.py                       9 routes    102 lines
  detect.py                        1 routes     10 lines
  generate.py                      5 routes     79 lines
  observe.py                       8 routes     32 lines
  stream.py                        1 routes     17 lines
```

> Naming: 19/24 functions (79%) follow `docker_*` convention

### 📁 k8s/

```
  actions.py                       3 routes     31 lines
  cluster.py                       8 routes     46 lines
  detect.py                        2 routes     12 lines
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

### 📁 artifacts/

```
  api.py                          16 routes    318 lines
```

### 📁 devops/

```
  __init__.py                      5 routes     58 lines (📌 init)
  apply.py                         5 routes     99 lines
  audit.py                         2 routes     39 lines
  detect.py                        1 routes     18 lines
```

> Naming: 3/13 functions (23%) follow `devops_*` convention

### 📁 chat/

```
  messages.py                      5 routes    245 lines
  refs.py                          2 routes     35 lines
  sync.py                          2 routes     92 lines
  threads.py                       3 routes    103 lines
```

> Naming: 12/12 functions (100%) follow `chat_*` convention

### 📁 scripts/

```
  execution.py                     4 routes    252 lines
  history.py                       2 routes     44 lines
  registry.py                      6 routes    200 lines
```

> Naming: 12/12 functions (100%) follow `scripts_*` convention

### 📁 terraform/

```
  actions.py                       8 routes     68 lines
  status.py                        4 routes     19 lines
```

### 📁 secrets/

```
  actions.py                       7 routes    109 lines
  status.py                        4 routes      9 lines
```

### 📁 infra/

```
  env.py                           7 routes     39 lines
  iac.py                           3 routes     14 lines
```

> Naming: 1/10 functions (10%) follow `infra_*` convention

### 📁 trace/

```
  queries.py                       3 routes     55 lines
  recording.py                     3 routes     62 lines
  sharing.py                       4 routes    110 lines
```

> Naming: 10/10 functions (100%) follow `trace_*` convention

### 📁 tab_mesh/

```
  __init__.py                      9 routes    516 lines (📌 init)
```

### 📁 api/

```
  audit.py                         2 routes     60 lines
  stacks.py                        1 routes     17 lines
  status.py                        5 routes     65 lines
```

> Naming: 8/8 functions (100%) follow `api_*` convention

### 📁 notifications/

```
  __init__.py                      7 routes    155 lines (📌 init)
```

### 📁 quality/

```
  actions.py                       6 routes     33 lines
  status.py                        1 routes     11 lines
```

> Naming: 7/7 functions (100%) follow `quality_*` convention

### 📁 security_scan/

```
  actions.py                       1 routes      9 lines
  detect.py                        6 routes     66 lines
```

> Naming: 1/7 functions (14%) follow `security_scan_*` convention

### 📁 packages/

```
  actions.py                       2 routes     23 lines
  status.py                        4 routes     31 lines
```

> Naming: 6/6 functions (100%) follow `packages_*` convention

### 📁 ci/

```
  generate.py                      2 routes     16 lines
  status.py                        3 routes     14 lines
```

> Naming: 3/5 functions (60%) follow `ci_*` convention

### 📁 docs/

```
  generate.py                      2 routes     12 lines
  status.py                        3 routes     15 lines
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
  status.py                        2 routes     12 lines
```

> Naming: 5/5 functions (100%) follow `testing_*` convention

### 📁 dns/

```
  __init__.py                      4 routes     37 lines (📌 init)
```

> Naming: 4/4 functions (100%) follow `dns_*` convention

### 📁 server/

```
  __init__.py                      4 routes     58 lines (📌 init)
```

> Naming: 4/4 functions (100%) follow `server_*` convention

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
  __init__.py                      2 routes     27 lines (📌 init)
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
| `run_tracked` | 116 | 20 | audit, backup, ci, config, content +15 |
| `requires_gh_auth` | 18 | 2 | chat, integrations |
| `requires_git_auth` | 13 | 3 | chat, integrations, pages |

### Decorator Combinations

| Combination | Count | % |
|-------------|-------|---|
| (route only) | 285 | 68.8% |
| run_tracked | 106 | 25.6% |
| requires_gh_auth + requires_git_auth | 8 | 1.9% |
| requires_gh_auth + run_tracked | 5 | 1.2% |
| requires_git_auth + run_tracked | 5 | 1.2% |
| requires_gh_auth | 5 | 1.2% |

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

**`POST /audit/install-plan/cache`** — `audit_cache_plan`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`POST /audit/install-plan/cancel`** — `audit_cancel_plan`

- 📤 Codes: ⚠️ 400, ⚠️ 404

**`POST /audit/install-plan/execute`** — `audit_execute_plan`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`POST /audit/install-plan/execute-sync`** — `audit_execute_plan_sync`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`POST /audit/install-plan/resume`** — `audit_resume_plan`

- 📤 Codes: ⚠️ 400

**`POST /audit/remediate`** — `audit_remediate`

- 📤 Codes: ⚠️ 400

**`POST /audit/remove-tool`** — `audit_remove_tool`  🎭 run_tracked

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

**`POST /audit/update-tool`** — `audit_update_tool`  🎭 run_tracked

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

### integrations

**`POST /gh/actions/dispatch`** — `gh_actions_dispatch`  🎭 run_tracked, requires_gh_auth

- 📤 Codes: ⚠️ 400

**`GET /gh/actions/runs`** — `gh_actions_runs`  🎭 requires_gh_auth

- 📥 `query.n` (optional)
- 📥 `query.bust` (optional)

**`GET /gh/actions/workflows`** — `gh_actions_workflows`  🎭 requires_gh_auth

- 📥 `query.bust` (optional)

**`POST /gh/auth/device`** — `gh_auth_device_start_route`  🎭 run_tracked

- 📤 Codes: ✅ 200

**`GET /gh/auth/device/poll`** — `gh_auth_device_poll_route`

- 📥 `query.session` (optional)
- 📤 Codes: ⚠️ 400

**`POST /gh/auth/logout`** — `gh_auth_logout`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`GET /gh/pulls`** — `gh_pulls`  🎭 requires_gh_auth

- 📥 `query.bust` (optional)

**`POST /gh/repo/create`** — `gh_repo_create`  🎭 run_tracked, requires_gh_auth

- 📤 Codes: ⚠️ 400

**`POST /gh/repo/default-branch`** — `gh_repo_set_default_branch`  🎭 run_tracked, requires_gh_auth

- 📤 Codes: ⚠️ 400

**`POST /gh/repo/rename`** — `gh_repo_rename`  🎭 run_tracked, requires_gh_auth

- 📤 Codes: ⚠️ 400

**`POST /gh/repo/visibility`** — `gh_repo_set_visibility`  🎭 run_tracked, requires_gh_auth

- 📤 Codes: ⚠️ 400

**`POST /git/checkout-file`** — `git_checkout_file_route`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`POST /git/commit`** — `git_commit`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`GET /git/diff/file`** — `git_diff_file_route`

- 📥 `query.path` (optional)
- 📥 `query.staged` (optional)
- 📤 Codes: ⚠️ 400

**`POST /git/filter-repo`** — `git_filter_repo_route`  🎭 requires_git_auth, run_tracked

- 📤 Codes: ⚠️ 400

**`POST /git/gc`** — `git_gc_route`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`POST /git/history-reset`** — `git_history_reset_route`  🎭 requires_git_auth, run_tracked

- 📤 Codes: ⚠️ 400

**`GET /git/log`** — `git_log`

- 📥 `query.n` (optional)

**`POST /git/merge/abort`** — `git_merge_abort_route`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`POST /git/pull`** — `git_pull`  🎭 requires_git_auth, run_tracked

- 📤 Codes: ⚠️ 400

**`POST /git/push`** — `git_push`  🎭 requires_git_auth, run_tracked

- 📤 Codes: ⚠️ 400

**`POST /git/remote/add`** — `git_remote_add`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`POST /git/remote/remove`** — `git_remote_remove`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`POST /git/remote/rename`** — `git_remote_rename`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`POST /git/remote/set-url`** — `git_remote_set_url`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`POST /git/stash`** — `git_stash_route`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`POST /git/stash/pop`** — `git_stash_pop_route`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`GET /git/status`** — `git_status`

- 📥 `query.bust` (optional)

**`GET /integrations/gh/status`** — `gh_status_extended`

- 📥 `query.bust` (optional)

**`POST /ledger/resolve-conflict`** — `ledger_resolve_conflict_route`

- 📤 Codes: ⚠️ 400

### content

**`POST /content/clean-release-sidecar`** — `content_clean_release_sidecar`

- 📤 Codes: ⚠️ 400, ⚠️ 404

**`POST /content/decrypt`** — `content_decrypt`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`GET /content/download`** — `content_download`

- 📥 `query.path` (optional)
- 📥 `query.download` (optional)
- 📤 Codes: ⚠️ 400, ⚠️ 404

**`POST /content/encrypt`** — `content_encrypt`  🎭 run_tracked

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

**`POST /content/setup-enc-key`** — `content_setup_enc_key`

- 📤 Codes: ⚠️ 400

**`POST /content/upload`** — `content_upload`

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

**`POST /pages/build/<name>`** — `build_segment_route`  🎭 run_tracked

- 🔗 URL: `<name>`

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

**`POST /pages/segments`** — `create_segment`

- 📤 Codes: ⚠️ 400, ⚠️ 409

**`PUT /pages/segments/<name>`** — `update_segment_route`

- 🔗 URL: `<name>`
- 📤 Codes: ⚠️ 404

**`DELETE /pages/segments/<name>`** — `delete_segment_route`

- 🔗 URL: `<name>`

**`GET /pages/site/<segment>/<path:filepath>`** — `serve_pages_site`

- 🔗 URL: `<segment>`, `<filepath>`

### docker

**`POST /docker/build`** — `docker_build`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`GET /docker/containers`** — `docker_containers`

- 📥 `query.all` (optional)

**`POST /docker/down`** — `docker_down`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`POST /docker/exec`** — `docker_exec`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`POST /docker/generate/compose`** — `generate_compose`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`POST /docker/generate/compose-wizard`** — `generate_compose_wizard`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`POST /docker/generate/dockerfile`** — `generate_dockerfile`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`POST /docker/generate/dockerignore`** — `generate_dockerignore`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`POST /docker/generate/write`** — `write_generated`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`GET /docker/inspect`** — `docker_inspect`

- 📥 `query.id` (optional)
- 📤 Codes: ⚠️ 400

**`GET /docker/logs`** — `docker_logs`

- 📥 `query.service` (optional)
- 📥 `query.tail` (optional)
- 📤 Codes: ⚠️ 400

**`POST /docker/prune`** — `docker_prune`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`POST /docker/pull`** — `docker_pull`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`POST /docker/restart`** — `docker_restart`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`POST /docker/rm`** — `docker_rm`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`POST /docker/rmi`** — `docker_rmi`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`GET /docker/status`** — `docker_status`

- 📥 `query.bust` (optional)

**`POST /docker/stream/<action>`** — `docker_stream`

- 🔗 URL: `<action>`
- 📤 Codes: ⚠️ 400

**`POST /docker/up`** — `docker_up`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

### k8s

**`POST /k8s/apply`** — `k8s_apply`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`POST /k8s/delete`** — `k8s_delete`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`GET /k8s/describe`** — `k8s_describe`

- 📥 `query.kind` (optional)
- 📥 `query.name` (optional)
- 📥 `query.namespace` (optional)
- 📤 Codes: ⚠️ 400

**`GET /k8s/events`** — `k8s_events`

- 📥 `query.namespace` (optional)
- 📤 Codes: ⚠️ 400

**`POST /k8s/generate/manifests`** — `k8s_generate_manifests`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`POST /k8s/generate/wizard`** — `k8s_generate_wizard`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`POST /k8s/helm/install`** — `helm_install`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`GET /k8s/helm/list`** — `helm_list`

- 📥 `query.namespace` (optional)

**`POST /k8s/helm/template`** — `helm_template`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`POST /k8s/helm/upgrade`** — `helm_upgrade`  🎭 run_tracked

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

**`POST /k8s/scale`** — `k8s_scale`  🎭 run_tracked

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

**`POST /vault/add-keys`** — `vault_add_keys`

- 📤 Codes: ⚠️ 400

**`POST /vault/auto-lock`** — `vault_auto_lock`

- 📤 Codes: ⚠️ 400

**`POST /vault/create`** — `vault_create`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`POST /vault/export`** — `vault_export`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`POST /vault/import`** — `vault_import`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`POST /vault/lock`** — `vault_lock`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`POST /vault/register`** — `vault_register`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`POST /vault/unlock`** — `vault_unlock`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

### backup

**`POST /backup/decrypt`** — `api_decrypt_backup`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`POST /backup/delete`** — `api_delete`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`GET /backup/download/<path:filepath>`** — `api_download`

- 🔗 URL: `<filepath>`
- 📤 Codes: ⚠️ 400, ⚠️ 404

**`POST /backup/encrypt`** — `api_encrypt_backup`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`GET /backup/folder-tree`** — `api_folder_tree`

- 📥 `query.depth` (optional)

**`POST /backup/import`** — `api_import`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`GET /backup/list`** — `api_list`

- 📥 `query.path` (optional)
- 📥 `query.check_release` (optional)
- 📤 Codes: ⚠️ 400

**`POST /backup/mark-special`** — `api_mark_special`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`GET /backup/preview`** — `api_preview`

- 📥 `query.path` (optional)
- 📤 Codes: ⚠️ 400

**`POST /backup/rename`** — `api_rename_backup`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`GET /backup/tree`** — `api_tree`

- 📥 `query.types` (optional)
- 📥 `query.path` (optional)
- 📥 `query.depth` (optional)
- 📥 `query.gitignore` (optional)
- 📤 Codes: ⚠️ 400, ⚠️ 404

**`POST /backup/upload`** — `api_upload`  🎭 run_tracked

- 📥 `form.target_folder` (optional)
- 📤 Codes: ⚠️ 400

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

**`POST /detect`** — `detect_targets`

- 📤 Codes: ⚠️ 404

**`POST /makefile/patch`** — `makefile_patch`

- 📤 Codes: ⚠️ 404, ❌ 500

**`POST /publish/<name>/stream`** — `publish_stream`

- 🔗 URL: `<name>`

**`POST /targets`** — `create_target`

- 📤 Codes: ⚠️ 400, ⚠️ 409

**`PUT /targets/<name>`** — `modify_target`

- 🔗 URL: `<name>`
- 📤 Codes: ⚠️ 404

**`DELETE /targets/<name>`** — `delete_target`

- 🔗 URL: `<name>`
- 📤 Codes: ⚠️ 404

**`GET /targets/<name>/status`** — `target_build_status`

- 🔗 URL: `<name>`
- 📤 Codes: ⚠️ 404

### devops

**`POST /devops/audit/dismissals`** — `audit_dismissals_add`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`DELETE /devops/audit/dismissals`** — `audit_dismissals_remove`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`POST /wizard/check-tools`** — `wizard_check_tools`

- 📤 Codes: ⚠️ 400

**`POST /wizard/compose-ci`** — `wizard_compose_ci`  🎭 run_tracked

- 📤 Codes: ⚠️ 400, ❌ 500

**`DELETE /wizard/config`** — `wizard_delete_config`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`GET /wizard/detect`** — `wizard_detect`

- 📥 `query.bust` (optional)

**`POST /wizard/setup`** — `wizard_setup`  🎭 run_tracked

- 📤 Codes: ⚠️ 400, ❌ 500

**`POST /wizard/validate`** — `wizard_validate`

- 📤 Codes: ⚠️ 400

### chat

**`POST /chat/delete-message`** — `chat_delete_message`  🎭 requires_gh_auth, requires_git_auth

- 📤 Codes: ⚠️ 400, ⚠️ 404, ❌ 500

**`POST /chat/delete-thread`** — `chat_delete_thread`  🎭 requires_gh_auth, requires_git_auth

- 📤 Codes: ⚠️ 400, ⚠️ 404, ❌ 500

**`GET /chat/messages`** — `chat_messages`

- 📥 `query.n` (optional)
- 📥 `query.thread_id` (optional)
- 📥 `query.run_id` (optional)
- 📤 Codes: ❌ 500

**`POST /chat/move-message`** — `chat_move_message`  🎭 requires_gh_auth, requires_git_auth

- 📤 Codes: ⚠️ 400, ⚠️ 404, ❌ 500

**`POST /chat/poll`** — `chat_poll`  🎭 requires_gh_auth, requires_git_auth

- 📤 Codes: ❌ 500

**`GET /chat/refs/autocomplete`** — `chat_autocomplete`

- 📥 `query.prefix` (optional)
- 📤 Codes: ❌ 500

**`GET /chat/refs/resolve`** — `chat_resolve_ref`

- 📥 `query.ref` (optional)
- 📤 Codes: ⚠️ 400, ⚠️ 404, ❌ 500

**`POST /chat/send`** — `chat_send`  🎭 requires_gh_auth, requires_git_auth

- 📤 Codes: ⚠️ 400, ❌ 500

**`POST /chat/sync`** — `chat_sync`  🎭 requires_gh_auth, requires_git_auth

- 📤 Codes: ❌ 500

**`GET /chat/threads`** — `chat_threads`

- 📤 Codes: ❌ 500

**`POST /chat/threads/create`** — `chat_thread_create`  🎭 requires_gh_auth, requires_git_auth

- 📤 Codes: ⚠️ 400, ❌ 500

**`POST /chat/update-message`** — `chat_update_message`  🎭 requires_gh_auth, requires_git_auth

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

**`POST /scripts/run`** — `scripts_run`

- 📤 Codes: ⚠️ 400

**`POST /scripts/run/stream`** — `scripts_run_stream`

- 📤 Codes: ⚠️ 400, ⚠️ 404

**`GET /scripts/status/<run_id>`** — `scripts_status`

- 🔗 URL: `<run_id>`
- 📤 Codes: ⚠️ 404

### terraform

**`POST /terraform/apply`** — `tf_apply`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`POST /terraform/destroy`** — `tf_destroy`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`POST /terraform/fmt`** — `tf_fmt`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`POST /terraform/generate`** — `tf_generate`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`POST /terraform/init`** — `tf_init`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`GET /terraform/output`** — `tf_output`

- 📤 Codes: ⚠️ 400

**`POST /terraform/plan`** — `tf_plan`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`GET /terraform/status`** — `tf_status`

- 📥 `query.bust` (optional)

**`POST /terraform/validate`** — `tf_validate`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`POST /terraform/workspace/select`** — `tf_workspace_select`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

### secrets

**`POST /env/cleanup`** — `api_env_cleanup`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`POST /gh/environment/create`** — `api_gh_environment_create`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`POST /secret/remove`** — `api_secret_remove`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`POST /secret/set`** — `api_secret_set`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`POST /secrets/push`** — `api_push_secrets`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

### infra

**`GET /env/card-status`** — `env_card_status`

- 📥 `query.bust` (optional)

**`GET /infra/env/diff`** — `env_diff`

- 📥 `query.source` (optional)
- 📥 `query.target` (optional)
- 📤 Codes: ⚠️ 404

**`POST /infra/env/generate-env`** — `env_generate_env`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`POST /infra/env/generate-example`** — `env_generate_example`  🎭 run_tracked

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

**`POST /trace/delete`** — `trace_delete`

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

**`POST /trace/share`** — `trace_share`

- 📤 Codes: ⚠️ 400, ⚠️ 404, ❌ 500

**`POST /trace/start`** — `trace_start`

- 📤 Codes: ❌ 500

**`POST /trace/stop`** — `trace_stop`

- 📤 Codes: ⚠️ 400, ⚠️ 404, ❌ 500

**`POST /trace/unshare`** — `trace_unshare`

- 📤 Codes: ⚠️ 400, ⚠️ 404, ❌ 500

**`POST /trace/update`** — `trace_update`

- 📤 Codes: ⚠️ 400, ⚠️ 404, ❌ 500

### tab_mesh

**`POST /tab-mesh/cdp-remediate`** — `cdp_remediate`

- 📤 Codes: ⚠️ 400, ❌ 500

**`POST /tab-mesh/discover-target`** — `discover_target`

- 📤 Codes: ⚠️ 400

**`POST /tab-mesh/focus`** — `focus_tab`

- 📤 Codes: ❌ 503

**`POST /tab-mesh/kill-chrome`** — `kill_chrome`

- 📤 Codes: ⚠️ 400, ❌ 500

**`POST /tab-mesh/restart-chrome`** — `restart_chrome`

- 📤 Codes: ⚠️ 400, ❌ 500

**`POST /tab-mesh/trigger-chrome-signin`** — `trigger_chrome_signin`

- 📤 Codes: ⚠️ 400, ❌ 500, ❌ 503

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

**`DELETE /notifications/<notif_id>`** — `delete`

- 🔗 URL: `<notif_id>`
- 📤 Codes: ⚠️ 404

**`POST /notifications/dismiss`** — `dismiss`

- 📤 Codes: ⚠️ 400, ⚠️ 404

### quality

**`POST /quality/check`** — `quality_check`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`POST /quality/generate/config`** — `quality_generate_config`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`GET /quality/status`** — `quality_status`

- 📥 `query.bust` (optional)

### security_scan

**`POST /security/generate/gitignore`** — `security_generate_gitignore`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`GET /security/status`** — `security_status`

- 📥 `query.bust` (optional)

### packages

**`GET /packages/audit`** — `package_audit`

- 📥 `query.manager` (optional)
- 📤 Codes: ⚠️ 400

**`POST /packages/install`** — `package_install`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`GET /packages/list`** — `package_list`

- 📥 `query.manager` (optional)
- 📤 Codes: ⚠️ 400

**`GET /packages/outdated`** — `package_outdated`

- 📥 `query.manager` (optional)
- 📤 Codes: ⚠️ 400

**`GET /packages/status`** — `package_status`

- 📥 `query.bust` (optional)

**`POST /packages/update`** — `package_update`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

### ci

**`POST /ci/generate/ci`** — `generate_ci`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`POST /ci/generate/lint`** — `generate_lint`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`GET /ci/status`** — `ci_status`

- 📥 `query.bust` (optional)

### docs

**`POST /docs/generate/changelog`** — `docs_generate_changelog`  🎭 run_tracked

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

**`POST /testing/generate/template`** — `testing_generate_template`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`POST /testing/run`** — `testing_run`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`GET /testing/status`** — `testing_status`

- 📥 `query.bust` (optional)

### dns

**`POST /dns/generate`** — `dns_generate`  🎭 run_tracked

- 📤 Codes: ⚠️ 400

**`GET /dns/lookup/<domain>`** — `dns_lookup`

- 🔗 URL: `<domain>`
- 📤 Codes: ⚠️ 400

**`GET /dns/ssl/<domain>`** — `dns_ssl`

- 🔗 URL: `<domain>`
- 📤 Codes: ⚠️ 400

**`GET /dns/status`** — `dns_status`

- 📥 `query.bust` (optional)

### server

**`POST /server/restart`** — `server_restart_route`

- 📤 Codes: ❌ 500

### config

**`GET /config`** — `api_config_read`

- 📤 Codes: ❌ 500

**`POST /config`** — `api_config_save`  🎭 run_tracked

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

🟢 **Small**: `███████████████░░░░░` 306 routes (74%)
🟡 **Medium**: `████░░░░░░░░░░░░░░░░` 81 routes (20%)
🟠 **Large**: `█░░░░░░░░░░░░░░░░░░░` 22 routes (5%)
🔴 **Very Large**: `░░░░░░░░░░░░░░░░░░░░` 5 routes (1%)

### Highest Complexity Routes

> Sorted by composite complexity: body lines × branch count × nesting depth.

| # | Function | Blueprint | Lines | Branches | Depth | Complexity |
|---|----------|-----------|-------|----------|-------|-----------|
| 1 | `audit_execute_plan` | audit | 450 | 48 | 6 | **129,600** |
| 2 | `audit_resume_plan` | audit | 193 | 15 | 3 | **8,685** |
| 3 | `makefile_patch` | artifacts | 100 | 13 | 5 | **6,500** |
| 4 | `scripts_run_stream` | scripts | 173 | 12 | 3 | **6,228** |
| 5 | `chat_poll` | chat | 70 | 10 | 6 | **4,200** |
| 6 | `audit_deep_detect` | audit | 94 | 14 | 3 | **3,948** |
| 7 | `project_health` | metrics | 69 | 11 | 4 | **3,036** |
| 8 | `content_preview` | content | 89 | 11 | 3 | **2,937** |
| 9 | `gh_auth_terminal_poll_route` | integrations | 65 | 8 | 5 | **2,600** |
| 10 | `content_glossary` | content | 93 | 8 | 3 | **2,232** |
| 11 | `cdp_diagnose` | tab_mesh | 83 | 7 | 3 | **1,743** |
| 12 | `trigger_chrome_signin` | tab_mesh | 77 | 7 | 3 | **1,617** |
| 13 | `discover_target` | tab_mesh | 67 | 12 | 2 | **1,608** |
| 14 | `chat_move_message` | chat | 63 | 8 | 3 | **1,512** |
| 15 | `chat_threads` | chat | 40 | 6 | 6 | **1,440** |

### Docstring Quality

| Tier | Count | Description |
|------|-------|-------------|
| 🟢 Detailed (5+ lines) | 116 | Comprehensive documentation |
| 🟡 Brief (1-4 lines) | 293 | Short description |
| 🔴 Missing | 5 | No docstring |

**Missing docstrings:**
- `audit.audit_system` (/audit/system)
- `audit.audit_dependencies` (/audit/dependencies)
- `audit.audit_structure` (/audit/structure)
- `audit.audit_clients` (/audit/clients)
- `audit.audit_scores_endpoint` (/audit/scores)

## Consistency Matrix

> Cross-blueprint pattern comparison. Highlights where a blueprint deviates from the project norm.

> **Project norms**: docs=99%, tracking=28%, error handling=17%, explicit methods=57%

| Blueprint | Routes | Docs | Track | ErrH | Methods | vs Norm |
|-----------|--------|------|-------|------|---------|---------|
| **audit** | 44 | 89% | 14% | 14% | 59% | ≈ |
| **integrations** | 42 | 100% | 52% | 10% | 55% | 📊↑ |
| **content** | 30 | 100% | 7% | 23% | 63% | 📊↓ |
| **pages** | 27 | 100% | 22% | 11% | 63% | ≈ |
| **docker** | 24 | 100% | 58% | 0% | 62% | 📊↑ 🛡️↓ |
| **k8s** | 24 | 100% | 33% | 0% | 46% | 🛡️↓ |
| **vault** | 21 | 100% | 29% | 29% | 76% | ≈ |
| **backup** | 18 | 100% | 67% | 11% | 67% | 📊↑ |
| **artifacts** | 16 | 100% | 0% | 25% | 100% | 📊↓ 📋↑ |
| **devops** | 13 | 100% | 38% | 15% | 92% | 📋↑ |
| **chat** | 12 | 100% | 0% | 100% | 67% | 📊↓ 🛡️↑ |
| **scripts** | 12 | 100% | 0% | 17% | 25% | 📊↓ 📋↓ |
| **terraform** | 12 | 100% | 67% | 0% | 67% | 📊↑ 🛡️↓ |
| **secrets** | 11 | 100% | 64% | 0% | 64% | 📊↑ 🛡️↓ |
| **infra** | 10 | 100% | 20% | 0% | 20% | 🛡️↓ 📋↓ |
| **trace** | 10 | 100% | 0% | 100% | 60% | 📊↓ 🛡️↑ |
| **tab_mesh** | 9 | 100% | 0% | 33% | 78% | 📊↓ 📋↑ |
| **api** | 8 | 100% | 0% | 0% | 25% | 📊↓ 🛡️↓ 📋↓ |
| **notifications** | 7 | 100% | 0% | 0% | 57% | 📊↓ 🛡️↓ |
| **quality** | 7 | 100% | 86% | 0% | 86% | 📊↑ 🛡️↓ 📋↑ |
| **security_scan** | 7 | 100% | 14% | 0% | 14% | 🛡️↓ 📋↓ |
| **packages** | 6 | 100% | 33% | 0% | 33% | 🛡️↓ 📋↓ |
| **ci** | 5 | 100% | 40% | 0% | 40% | 🛡️↓ |
| **docs** | 5 | 100% | 40% | 0% | 40% | 🛡️↓ |
| **git_auth** | 5 | 100% | 0% | 100% | 60% | 📊↓ 🛡️↑ |
| **smart_folders** | 5 | 100% | 0% | 40% | 0% | 📊↓ 📋↓ |
| **testing** | 5 | 100% | 60% | 0% | 60% | 📊↑ 🛡️↓ |
| **dns** | 4 | 100% | 25% | 0% | 25% | 🛡️↓ 📋↓ |
| **server** | 4 | 100% | 0% | 0% | 75% | 📊↓ 🛡️↓ |
| **config** | 3 | 100% | 33% | 0% | 33% | 🛡️↓ 📋↓ |
| **dev** | 3 | 100% | 0% | 0% | 0% | 📊↓ 🛡️↓ 📋↓ |
| **metrics** | 2 | 100% | 0% | 50% | 0% | 📊↓ 🛡️↑ 📋↓ |
| **project** | 2 | 100% | 0% | 0% | 0% | 📊↓ 🛡️↓ 📋↓ |
| **events** | 1 | 100% | 0% | 100% | 0% | 📊↓ 🛡️↑ 📋↓ |

## Anomaly Detection

> Routes that break the dominant pattern of their blueprint. Not violations — just observations worth reviewing.

### audit

- 📏 Avg body 34 lines — outliers: `audit_execute_plan` (450L), `audit_resume_plan` (193L)
- 📝 39/44 documented — missing: `audit_system`, `audit_dependencies`, `audit_structure`, `audit_clients`, `audit_scores_endpoint`

### integrations

- 📊 22/42 routes tracked — untracked: `gh_auth_token_route`, `gh_auth_device_poll_route`, `gh_auth_terminal_poll_route`, `git_status`, `git_log`
- 📏 Avg body 12 lines — outliers: `gh_auth_terminal_poll_route` (65L), `git_commit` (54L)

### content

- 🛡️ Only 7/30 routes have error handling: `content_metadata`, `content_outline`, `peek_refs`, `peek_resolve`, `content_preview`
- 📏 Avg body 28 lines — outliers: `content_preview_encrypted` (110L), `content_glossary` (93L), `peek_refs` (91L)

### pages

- 📊 Only 6/27 routes tracked: `build_segment_route`, `build_all_route`, `merge_route`, `deploy_route`, `init_pages`
- 📏 Avg body 11 lines — outliers: `patch_script` (63L)

### docker

- 📊 14/24 routes tracked — untracked: `docker_status`, `docker_containers`, `docker_images`, `docker_compose_status`, `docker_logs`

### k8s

- 📊 Only 8/24 routes tracked: `k8s_apply`, `k8s_delete`, `k8s_scale`, `k8s_generate_manifests`, `k8s_generate_wizard`

### vault

- 📊 Only 6/21 routes tracked: `vault_create`, `vault_lock`, `vault_unlock`, `vault_register`, `vault_export`
- 🛡️ Only 6/21 routes have error handling: `vault_lock`, `vault_unlock`, `vault_register`, `vault_auto_lock`, `vault_export`

### backup

- 📊 12/18 routes tracked — untracked: `api_folder_tree`, `api_folders`, `api_list`, `api_preview`, `api_download`

### artifacts

- 🛡️ Only 4/16 routes have error handling: `create_target`, `modify_target`, `delete_target`, `makefile_patch`
- 📏 Avg body 20 lines — outliers: `makefile_patch` (100L)

### devops

- 📊 Only 5/13 routes tracked: `wizard_setup`, `wizard_delete_config`, `wizard_compose_ci`, `audit_dismissals_add`, `audit_dismissals_remove`

### scripts

- 📏 Avg body 41 lines — outliers: `scripts_run_stream` (173L)

### terraform

- 📊 8/12 routes tracked — untracked: `tf_status`, `tf_state`, `tf_workspaces`, `tf_output`

### secrets

- 📊 7/11 routes tracked — untracked: `api_gh_status`, `api_gh_auto`, `api_gh_environments`, `api_gh_secrets`

### tab_mesh

- 🛡️ Only 3/9 routes have error handling: `kill_chrome`, `restart_chrome`, `discover_target`

### packages

- 📊 Only 2/6 routes tracked: `package_install`, `package_update`

### ci

- 📊 Only 2/5 routes tracked: `generate_ci`, `generate_lint`

### docs

- 📊 Only 2/5 routes tracked: `docs_generate_changelog`, `docs_generate_readme`

### smart_folders

- 🛡️ Only 2/5 routes have error handling: `api_smart_folders_list`, `api_smart_folders_file`

### testing

- 📊 3/5 routes tracked — untracked: `testing_status`, `testing_inventory`

### dns

- 📊 Only 1/4 routes tracked: `dns_generate`

### config

- 📊 Only 1/3 routes tracked: `api_config_save`
