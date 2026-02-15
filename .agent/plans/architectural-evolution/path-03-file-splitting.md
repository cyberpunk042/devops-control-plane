# Path 3: File Splitting & Template Extraction

> **Status**: Analysis & Planning
> **Effort**: 3–5 days (phased)
> **Risk**: High — JS template splits must preserve variable scoping; Python splits must preserve imports
> **Prereqs**: Path 2 (Data Extraction) ✅
> **Unlocks**: Path 5 (Layer Push-down), Path 7 (Modal Preview)

---

## 1. Current State

### 1.1 The Monster File

`src/ui/web/templates/scripts/_integrations_setup_modals.html` — **7,612 lines**

Contains 6 complete setup wizards + shared infrastructure + a dispatcher:

| Section | Lines | Span | Est. Size |
|---------|------:|------|----------:|
| Shared (cache banner, validation, collision detector) | 1–215 | 215 | small |
| Git Setup Wizard | 216–701 | 486 | medium |
| Data aliases (infra, docker, secrets from DataRegistry) | 702–746 | 45 | tiny |
| Docker Setup Wizard | 708–2003 | 1,296 | large |
| CI/CD Setup Wizard | 2004–2146 | 143 | small |
| **Kubernetes Setup Wizard** | **2147–6715** | **4,569** | **massive** |
| Terraform Setup Wizard | 6716–6862 | 147 | small |
| GitHub Setup Wizard | 6863–7588 | 726 | medium |
| Dispatcher (`openSetupWizard`) | 7589–7613 | 25 | tiny |

The K8s wizard alone is **60% of the file** (4,569 lines).

### 1.2 K8s Wizard Internal Structure

The K8s wizard has three steps, but Step 2 (Configure) is the bulk:

| Sub-section | Internal Lines | Absolute Lines | Size |
|-------------|---------------:|---------------|-----:|
| Helpers (QoS, compose parsing, probes) | 1–133 | 2147–2280 | 133 |
| Step 1: Detect | 134–339 | 2281–2486 | 206 |
| Step 2 env/var infrastructure | 340–814 | 2487–2961 | 475 |
| Step 2 StorageClass + volumes | 815–1213 | 2962–3360 | 399 |
| Step 2 init/sidecar/companion containers | 1214–1785 | 3361–3932 | 572 |
| Step 2 Section A: App services + saved state | 1786–2515 | 3933–4662 | 730 |
| Step 2 infra cards + Section B/C + skaffold | 2516–3468 | 4663–5615 | 953 |
| Step 2 collectors + persist | 3469–4105 | 5616–6252 | 637 |
| Step 3: Review & Apply | 4106–4569 | 6253–6715 | 463 |

### 1.3 Large Python Files

| File | Lines | Content |
|------|------:|---------|
| `k8s_ops.py` | 2,753 | detect + validate + cluster + generate + wizard backend |
| `backup_ops.py` | 1,179 | create + restore + archive + wipe + encrypt + release |
| `docker_ops.py` | 1,173 | detect + validate + compose + dockerfile + container ops |
| `routes_devops.py` | 1,020 | routes for 10+ devops sub-features |
| `security_ops.py` | 994 | scan + fix + audit + gitignore |

### 1.4 Other >500-line JS Template Files

| File | Lines |
|------|------:|
| `_integrations_k8s.html` | 734 |
| `_secrets_keys.html` | 693 |
| `_content_browser.html` | 687 |
| `_wizard_steps.html` | 638 |
| `_content_archive.html` | 624 |
| `_content_upload.html` | 591 |
| `_content_archive_modals.html` | 563 |
| `_secrets_render.html` | 533 |
| `_integrations_pages.html` | 532 |
| `_globals.html` | 517 |
| `_secrets_init.html` | 514 |
| `_content_preview_enc.html` | 514 |
| `_wizard_integrations.html` | 511 |
| `_integrations_pages_config.html` | 508 |

---

## 2. JS Template Split Strategy

### 2.1 Key Constraint

Each `scripts/*.html` file sits inside its own `<script>` tag. They share scope
via `window.*` globals. When splitting, each new file gets its own `<script>` /
`</script>` wrapper and must expose anything shared via `window.*`.

### 2.2 Shared Dependencies (lines 1–215)

These are used by ALL wizards:
- `window._wizForceRescan` (flag)
- `_wizDetectBanner(key)` (function)
- `window._wizValidation` (object: register, recheck, run)
- `_envCollisionValidator` (registered validator)

**Decision needed**: Keep in the monster file as `_integrations_shared.html`, or
leave as the first section of a renamed `_integrations_setup_modals.html`?

### 2.3 Data Aliases (lines 702–746)

These are already done (Path 2). They reference `window._dcp.*` and set
`window._infraOptions`, `window._infraCategories`. Used by both Docker and K8s wizards.

**Decision needed**: Move into `_integrations_shared.html` since they're cross-wizard?

### 2.4 Proposed Split — Monster File

| New File | Source Lines | Size | Content |
|----------|-------------|-----:|---------|
| `_integrations_shared.html` | 1–215, 702–746 | ~260 | Shared validation, cache banner, data aliases |
| `_integrations_setup_git.html` | 216–701 | 486 | Git Setup Wizard |
| `_integrations_setup_docker.html` | 708–2003 | 1,296 | Docker Setup Wizard |
| `_integrations_setup_cicd.html` | 2004–2146 | 143 | CI/CD Setup Wizard |
| `_integrations_setup_k8s.html` | 2147–6715 | 4,569 | Kubernetes Setup Wizard (needs further split) |
| `_integrations_setup_terraform.html` | 6716–6862 | 147 | Terraform Setup Wizard |
| `_integrations_setup_github.html` | 6863–7588 | 726 | GitHub Setup Wizard |
| `_integrations_setup_dispatch.html` | 7589–7613 | 25 | Dispatcher (openSetupWizard) |

**The K8s file at 4,569 lines still exceeds the 700-line limit.** Further splitting
requires extracting reusable helper subsystems:

### 2.5 Proposed K8s Sub-Split

| New File | K8s Internal Lines | Size | Content |
|----------|-------------------|-----:|---------|
| `_integrations_setup_k8s_helpers.html` | 1–133 (abs 2147–2280) | 133 | QoS, compose parser, probes |
| `_integrations_setup_k8s_env.html` | 340–814 (abs 2487–2961) | 475 | Env var selects, vault integration, collision |
| `_integrations_setup_k8s_volumes.html` | 815–1213 (abs 2962–3360) | 399 | StorageClass, volume rows, PVC |
| `_integrations_setup_k8s_containers.html` | 1214–1785 (abs 3361–3932) | 572 | Init, sidecar, companion containers |
| `_integrations_setup_k8s.html` | Steps 1+2 framework + Step 3 | ~2,990 | Main wizard flow (still large) |

Even with helpers extracted, the main K8s wizard would be ~2,990 lines because
the Step 2 Section A (app services + saved state restoration = 730 lines) and
the infra cards + Section B/C (953 lines) are tightly coupled to the wizard's
DOM context. These can't be trivially extracted without significant refactoring
because they contain:
- Closures that capture local variables from `openK8sSetupWizard()`
- DOM manipulation that references parent wizard elements by ID
- Event handlers defined inline

**This is a fundamental tension**: the 500-line limit is aspirational for this
file because the wizard is a single huge closure. True decomposition would mean
refactoring to a class-based or module-based pattern, which is a larger effort.

### 2.6 Realistic Target for Phase 3A (JS)

**Phase 3A** (the monster split = low-risk, high-value):
1. Extract 6 wizard files → kills the monster file
2. Extract K8s helpers, env, volumes, containers → 4 helper files
3. Main K8s wizard → still ~2,500–3,000 lines (acknowledged exception)

This brings the monster from **7,612 → 0** (eliminated) and the largest
resulting file to ~2,500–3,000 lines (the K8s wizard core). Further K8s
decomposition would be a separate effort requiring deeper refactoring.

---

## 3. Python Split Strategy

### 3.1 `k8s_ops.py` (2,753 lines)

Natural split by function group:

| New File | Functions | Est. Lines |
|----------|-----------|----------:|
| `k8s_detect.py` | `_kubectl_available`, `k8s_status`, `_collect_yaml_files`, `_detect_helm_charts`, `_detect_kustomize` | ~210 |
| `k8s_validate.py` | `validate_manifests`, `_validate_deployment`, `_validate_service`, `_validate_pod_spec` | ~230 |
| `k8s_cluster.py` | `cluster_status`, `get_resources`, `_summarize_conditions`, `k8s_pod_logs`, `k8s_apply`, `k8s_delete_resource`, `k8s_scale`, `k8s_events`, `k8s_describe`, `k8s_namespaces`, `k8s_storage_classes` | ~500 |
| `k8s_helm.py` | `_helm_available`, `helm_list`, `helm_values`, `helm_install`, `helm_upgrade`, `helm_template` | ~180 |
| `k8s_generate.py` | `generate_manifests`, `_build_probe`, `_build_wizard_volume`, `_build_pod_template`, `_build_env_vars` | ~600 |
| `k8s_wizard.py` | `wizard_state_to_resources`, `generate_k8s_wizard`, `k8s_env_namespaces`, `_svc_env_to_resources`, `_svc_volumes_to_pvc_resources`, `_generate_skaffold`, `skaffold_status` | ~700 |
| `k8s_ops.py` (kept) | `_run_kubectl`, `_parse_k8s_yaml` (shared utils) + re-exports for backward compat | ~80 |

### 3.2 `docker_ops.py` (1,173 lines)

| New File | Functions | Est. Lines |
|----------|-----------|----------:|
| `docker_detect.py` | `docker_status`, `find_compose_file`, `_parse_compose_services`, `_parse_compose_service_details`, `_env_list_to_dict`, `_normalise_ports`, `_long_volume_to_str` | ~400 |
| `docker_containers.py` | `docker_containers`, `docker_images`, `docker_compose_status`, `docker_logs`, `docker_stats`, `docker_build`, `docker_up`, `docker_down`, `docker_restart`, `docker_prune`, `docker_networks`, `docker_volumes`, `docker_inspect`, `docker_pull`, `docker_exec_cmd`, `docker_rm`, `docker_rmi` | ~500 |
| `docker_generate.py` | `generate_dockerfile`, `generate_dockerignore`, `generate_compose`, `generate_compose_from_wizard`, `write_generated_file` | ~250 |
| `docker_ops.py` (kept) | `run_docker`, `run_compose` (shared utils) + re-exports | ~50 |

### 3.3 `backup_ops.py` (1,179 lines)

| New File | Functions | Est. Lines |
|----------|-----------|----------:|
| `backup_core.py` | `classify_file`, `backup_dir_for`, `safe_backup_name`, `resolve_folder`, `read_manifest`, `get_enc_key`, `encrypt_archive`, `decrypt_archive`, `folder_tree`, `list_folders` | ~180 |
| `backup_manage.py` | `create_backup`, `list_backups`, `preview_backup`, `delete_backup`, `rename_backup`, `restore_backup`, `import_backup`, `wipe_folder` | ~650 |
| `backup_crypto.py` | `encrypt_backup_inplace`, `decrypt_backup_inplace` | ~100 |
| `backup_release.py` | `mark_special`, `file_tree_scan`, `_cleanup_release_sidecar` | ~200 |
| `backup_ops.py` (kept) | Re-exports for backward compat | ~50 |

### 3.4 `security_ops.py` (994 lines)

| New File | Functions | Est. Lines |
|----------|-----------|----------:|
| `security_scan.py` | `scan_secrets`, `detect_sensitive_files`, `_iter_files`, `_should_scan`, `_has_nosec` | ~300 |
| `security_dismiss.py` | `dismiss_finding`, `undismiss_finding` | ~90 |
| `security_gitignore.py` | `_is_gitignored`, `gitignore_analysis`, `generate_gitignore` | ~250 |
| `security_posture.py` | `security_posture` | ~300 |
| `security_ops.py` (kept) | Re-exports for backward compat | ~50 |

### 3.5 `routes_devops.py` (1,020 lines)

| New File | Routes | Est. Lines |
|----------|--------|----------:|
| `routes_devops_prefs.py` | `/devops/prefs`, `/integrations/prefs` | ~50 |
| `routes_devops_wizard.py` | `/wizard/detect`, `/wizard/setup`, `/wizard/config` DELETE, cache bust | ~800 |
| `routes_devops_audit.py` | `/devops/audit/dismissals` POST/DELETE | ~80 |
| `routes_devops.py` (kept) | Blueprint definition + register sub-blueprints | ~80 |

---

## 4. Execution Order

### Phase 3A: Monster File Split (JS)

Priority — this is the most impactful change.

1. Create `_integrations_shared.html` (shared infra)
2. Extract each wizard into its own file
3. Create dispatcher file
4. Update `dashboard.html` includes
5. Delete original monster file
6. Verify server loads and all wizards open

### Phase 3B: K8s Wizard Helpers (JS)

Extract the helper subsystems from the K8s wizard:

1. `_integrations_setup_k8s_helpers.html`
2. `_integrations_setup_k8s_env.html`
3. `_integrations_setup_k8s_volumes.html`
4. `_integrations_setup_k8s_containers.html`

### Phase 3C: Python Service Splits

Lower risk — Python imports are straightforward to rewire.

1. Split `k8s_ops.py`
2. Split `docker_ops.py`
3. Split `backup_ops.py`
4. Split `security_ops.py`
5. Split `routes_devops.py`

### Phase 3D: Other >500-line JS (if desired)

The 14 other JS files at 500–700 lines. These are borderline — some
may be fine at their current size. Assess individually.

---

## 5. Risk Assessment

### High Risk
- **K8s wizard closure scoping**: The entire wizard is one big closure.
  Extracted helpers must be attached to `window.*` and called from within.
- **Variable shadowing**: Multiple wizards define locally-scoped `_CK`,
  `el`, `html` etc. Splitting preserves this since each file has its own
  `<script>` scope.

### Medium Risk
- **Include order in dashboard.html**: Shared infra must load before wizards.
  Dispatcher must load after all wizards.
- **Python re-exports**: Breaking existing imports from other files.
  Mitigated by re-export shims in the original modules.

### Low Risk
- **CI/CD and Terraform wizards**: Tiny, self-contained, trivial to extract.
- **Git and GitHub wizards**: Medium-sized, self-contained.

---

## 6. Testing Strategy

### Per-file extraction:
1. Extract file
2. Update dashboard.html includes
3. Restart server
4. Open the specific wizard
5. Walk through all 3 steps (Detect → Configure → Review)
6. Verify no JS console errors

### Post-split:
- Full regression: open every wizard once
- Check that env collision detection works across Docker ↔ K8s
- Check that the dispatcher routes to all wizards correctly

---

## 7. Open Questions (for user decision)

1. **K8s wizard residual size**: Even after extracting helpers, the main
   K8s wizard will be ~2,500–3,000 lines. Accept as justified exception,
   or plan deeper refactoring (class-based pattern)?

2. **Phase ordering**: Start with JS (3A/3B) or Python (3C) first?

3. **Backward compat shims in Python**: Keep re-export shims in original
   `k8s_ops.py` etc., or update all imports immediately?

4. **Other 500-line JS files (Phase 3D)**: Tackle now or defer?
