# Tier 3 — Recipe Data Analysis

> **Created: 2026-02-24 (evening)**
>
> Pre-implementation analysis for Tier 3. 36 recipe definitions
> exist in domain docs but have no code representation in TOOL_RECIPES.

---

## Scope Assessment

The status doc says 36 recipes are missing:

| Category | Count | Domain Doc | Tier 2 Feature Used |
|----------|-------|-----------|---------------------|
| GPU/kernel drivers | 4 | domain-build-from-source, domain-ml-ai | Build adapters, risk system |
| Data packs | 28 | domain-data-packs, domain-ml-ai | Download step executor |
| Config templates | 4 | domain-config-files | Config template system |

### Reality Check

**GPU drivers** (4 recipes) — These are HIGH risk, complex, multi-step
recipes with build-from-source, kernel modules, DKMS, repo setup.
The Tier 2 infrastructure (risk system, build adapters) supports them.
But: these need careful per-distro testing. The recipes themselves are
factual and deterministic — we can write them based on documented
official install procedures.

**Data packs** (28 recipes) — These are Phase 7 download steps.
The download executor exists. But 28 individual recipes is a LOT of
data — each one needs: ID, label, URL, size, checksum rules, install
path, verification command.

**IMPORTANT:** The 28 data pack count from the status doc is misleading.
Looking at domain-data-packs, these are MODEL entries within tool recipes,
not 28 separate TOOL_RECIPES entries. A single tool recipe (e.g. `spacy`)
would have a `data_packs` array with 9 model entries. So the actual
recipe count is much smaller.

**Config templates** (4 recipes) — These use the template system we
just built. Straightforward: Docker daemon.json, journald.conf,
logrotate, nginx.

---

## What To Actually Implement

### Group A: Config Template Recipes (simplest, uses Phase C directly)

These are the most immediately useful — they use the template system
we just built in Tier 2.

| Recipe | Config File | Format | Risk |
|--------|------------|--------|------|
| `docker-daemon-config` | `/etc/docker/daemon.json` | JSON | medium |
| `journald-config` | `/etc/systemd/journald.conf` | INI | medium |
| `logrotate-docker` | `/etc/logrotate.d/docker` | raw | medium |
| `nginx-reverse-proxy` | `/etc/nginx/conf.d/app.conf` | raw | medium |

These are NOT tools in the traditional sense — they're config options
that attach to existing tool recipes via `config_templates`. The docker
recipe already exists; what's missing is the config template definitions.

**Approach:** Add `config_templates` field to the existing `docker` recipe.
Add standalone config recipes for journald/logrotate/nginx.

### Group B: GPU/Kernel Recipes (complex, high-risk)

| Recipe | Install Method | Build System | Risk |
|--------|---------------|-------------|------|
| `nvidia-driver` | repo_setup + apt/dnf | DKMS (kernel module) | **high** |
| `cuda-toolkit` | repo_setup + apt/dnf | — | **high** |
| `rocm` | repo_setup + apt | — | **high** |
| `vfio-pci` | modprobe config | kernel module passthrough | **high** |

These are the most dangerous recipes. They modify kernel state,
load kernel modules, and can brick a system if wrong.

**Approach:** Implement nvidia-driver and cuda-toolkit first (most
commonly needed for ML/DevOps). rocm and vfio-pci are niche.

### Group C: Data Pack Entries (download metadata)

These aren't separate TOOL_RECIPES entries. They're `data_packs`
arrays within existing tool recipes. We need to:

1. Create placeholder tool recipes for spaCy, NLTK, Tesseract
2. Add `data_packs` arrays with model metadata

**Approach:** Defer to after Groups A and B. The download executor
works but the UI (multi-select modal with checksizes) is a Tier 4
concern. Adding recipe data without the UI is premature.

---

## Implementation Order

### Priority 1: Config Templates (Group A)

Directly validates the Tier 2 config template system we just built.
~60 lines of recipe data per template recipe.

### Priority 2: GPU Drivers (Group B — nvidia + cuda only)

High value for ML scenarios. Uses Tier 2 risk system. ~80 lines each.
rocm and vfio-pci deferred.

### Priority 3: Data Pack Stubs (Group C — deferred)

Needs UI (multi-select modal) to be useful. Recipe data without
the frontend experience is dead code. Move to Tier 4.

---

## Decision Point

The "36 missing recipes" breaks down to:

| Actually Needed Now | Count | Lines |
|--------------------|-------|-------|
| Config templates (4) | 4 | ~240 |
| GPU drivers (2 of 4) | 2 | ~160 |
| **Total Tier 3** | **6** | **~400** |

| Deferred to Tier 4+ | Count | Reason |
|---------------------|-------|--------|
| GPU drivers (2 niche) | 2 | rocm/vfio are rare |
| Data pack entries (28) | 28 | Needs multi-select UI first |
| **Total deferred** | **30** | **Missing frontend** |

---

## Traceability

| This analysis | References |
|---------------|-----------|
| Config templates | domain-config-files §Examples |
| GPU recipes | domain-ml-ai §GPU Detection, domain-build-from-source |
| Data packs | domain-data-packs, tool-install-v2-implementation-status §Phase 7 |
| Recipe format | arch-recipe-format.md |
