# 🐳 Docker Setup Wizard — Implementation Plan

> **Date**: 2026-02-13
> **Status**: DONE ✅ — Implemented with interactive module config + editable previews
> **Predecessor**: GitHub wizard (#2) — complete ✅

---

## 1. THE REAL PROBLEM

The current wizard asks the user to type `python:3.12-slim` and `pip install -e .` into text fields.
It generates a flat single-stage Dockerfile. It doesn't know what the project contains.

The backend generators are excellent — multi-stage Dockerfiles with non-root users, dependency
caching, 10 stack templates with prefix matching. But the wizard doesn't use them, and worse,
it doesn't ask the right questions.

**The right question is not** "what base image do you want?"
**The right question is** "which of your modules need their own container?"

---

## 2. THE USER'S ACTUAL DECISIONS

When containerizing a project, the user needs to decide:

### A. What gets its own container?

This project has 5 modules:
```
core         python-lib       library     src/core
adapters     python-lib       library     src/adapters
cli          python-cli       ops         src/ui/cli
web          python-flask     ops         src/ui/web
docs         markdown         docs        docs
```

- `core` and `adapters` are **libraries** — they don't run, they get `import`ed. NO container.
- `cli` is a CLI tool — usually no container, but maybe? The user should decide.
- `web` is a Flask web server — YES, this needs a container (port 8000).
- `docs` is markdown — NO container.

The wizard should **pre-select** modules that are likely containers (domain=ops/service with
a deployable stack like `python-flask`, `node`, `go`, etc.) and let the user adjust.

### B. What stack template for each container?

`python-flask` → matches the `python` Dockerfile template (multi-stage, pip, gunicorn-ready).
The prefix matching in `_resolve_template` handles this automatically.

But the user might want to override — maybe they want `python:3.11-slim` instead of `3.12`,
or a different base. The wizard should show the detected template and let them preview + adjust.

### C. One Dockerfile or many?

**Monolith**: One Dockerfile at root that packages the entire project. The `web` module imports
`core` and `adapters`, so they all go in one image. This is the "single-container" path.

**Microservices**: If you have a `frontend/` (node) and `api/` (python-flask), each gets its
own Dockerfile in its own directory. Two containers, two images.

The wizard should detect this: if all selected modules share the same language prefix AND are
in subdirectories of a common root, suggest monolith. If they're independent directories with
different stacks, suggest per-module Dockerfiles.

### D. Compose: How do the containers talk to each other?

If you have multiple containers, you need compose. The wizard should auto-generate the
compose file with:
- One service per selected module
- Correct build contexts (per-module dirs or root)
- Correct ports from stack defaults
- Common network
- Optional external services (postgres, redis, etc.)

Even with a single container, compose is useful for volume mounts, env vars, and restart policies.

### E. What else goes in compose?

The user might want:
- **Databases**: postgres, mysql, redis, mongodb
- **Message queues**: rabbitmq, kafka
- **Monitoring**: prometheus, grafana
- **Reverse proxy**: nginx, traefik

These aren't detected from code — the wizard should offer common add-ons.

### F. .dockerignore

Generated from the union of all selected stacks. Straightforward, auto-checked.

---

## 3. DATA AVAILABLE

### From `/api/config` → `config.modules[]`
```json
{
  "name": "web",
  "path": "src/ui/web",
  "stack": "python-flask",
  "domain": "ops",
  "description": "Flask admin web interface"
}
```
Key fields: `name`, `path`, `stack`, `domain`

### From `/api/docker/status`
```json
{
  "available": true,
  "daemon_running": true,
  "has_dockerfile": true,
  "has_compose": false,
  "has_dockerignore": false,
  "dockerfiles": ["Dockerfile"],
  "version": "Docker version 23.0.5"
}
```

### From `/api/stacks`
Stack definitions with capabilities. No domain info at this level — domain comes from the
module declaration in project.yml.

### Dockerfile template matching
`_resolve_template(stack_name)` uses prefix matching:
- `python-flask` → `python` template (multi-stage Python Dockerfile)
- `python-lib` → `python` template (matches, but shouldn't be offered — it's a library)
- `python-cli` → `python` template (matches, could be a container)
- `markdown` → no template
- `node`, `go`, `rust`, etc. → direct match

### Smart filtering: what's "container-worthy"?
- `domain == "library"` → skip (e.g. core, adapters)
- `domain == "docs"` → skip (e.g. docs with markdown stack)
- `stack == "markdown"` → skip
- Stack has no Dockerfile template → skip (e.g. kubernetes, helm, terraform stacks)
- Everything else → candidate, pre-checked

---

## 4. WIZARD FLOW (4 steps)

### Step 1: Detect

Fetch:
- `/project/status` → Docker probe (CLI, daemon, files)
- `/docker/status` → detailed Docker info
- `/config` → modules with stacks + domains

Display:
```
Docker Environment
──────────────────────────────────
🐳 Docker Engine    23.0.5          ✓
⚙️  Docker Compose   2.39.4          ✓
📄 Dockerfile       Present         ✓
📋 Compose file     Missing         ⚠
🚫 .dockerignore    Missing         ⚠

Project Modules
──────────────────────────────────
📦 web          python-flask   src/ui/web       🟢 deployable
📦 cli          python-cli     src/ui/cli       🟡 maybe
📦 core         python-lib     src/core         ⚪ library
📦 adapters     python-lib     src/adapters     ⚪ library
📦 docs         markdown       docs             ⚪ docs

💡 1 deployable module detected (web). Click Next to configure containers.
```

Store: `data._modules`, `data._dockerStatus`, `data._docker`

### Step 2: Configure — Container Selection

This is the core step. Two sections:

**Section A: Module Containers** (interactive expandable cards)

Each deployable module is shown as an expandable card with:
- Checkbox to include/exclude (checked by default)
- **Stack template dropdown** — all supported stacks, auto-selected to detected family
- **Port input** — editable number field, auto-offset (+i) to prevent conflicts
- **Dockerfile path** — text field, smart default:
  - Single module → `Dockerfile` (root)
  - Multiple modules → `{path}/Dockerfile` (per-module)

Libraries/docs/ops-tools are excluded from the list entirely (only shown in Detect step).
Unchecking a module collapses its config panel.

Manual fallback: if no deployable modules detected, shows a simple stack + port form.

**Section B: Additional Compose Services** (optional, collapsible)

Quick-add common infrastructure:
```
☐ PostgreSQL        postgres:16-alpine      port 5432
☐ Redis             redis:7-alpine          port 6379
☐ MySQL             mysql:8                 port 3306
☐ MongoDB           mongo:7                 port 27017
☐ RabbitMQ          rabbitmq:3-management   port 5672 / 15672
☐ Nginx             nginx:alpine            port 80
```

Each adds a service to the compose file with standard defaults.

**Section C: Options**

```
☑ Generate docker-compose.yml      (pre-check if >1 container or any infra selected)
☑ Generate .dockerignore           (pre-check if missing)
☐ Overwrite existing Dockerfile    (show only if exists)
```

`collect()`: Store per-module container choices + infra selections + options.

`validate()`:
- At least one module must be selected
- Ports must not conflict across modules + infra

### Step 3: Preview & Edit

For each file to be generated, call the generate endpoint and show the content in
**editable textareas** (not read-only pre blocks). The user can tweak:
- Base image version (e.g. `python:3.11-slim` instead of `3.12`)
- CMD / entrypoint
- Install commands
- Compose environment variables
- Anything else in the generated output

API calls for preview:
- Dockerfile: `POST /docker/generate/dockerfile` per selected module
- Compose: `POST /docker/generate/compose-wizard` with module services + infra services
- .dockerignore: `POST /docker/generate/dockerignore` with union of all stacks

A `collect()` callback syncs textarea edits back into `data._generatedFiles[]` before
the Apply step writes them. This gives the user full control: best-practice templates
as a starting point, with the ability to customize every line.

### Step 4: Review & Apply (merged with success)

Summary of what will be written:
```
📄 Dockerfile               create
📋 docker-compose.yml       create
🚫 .dockerignore            create
```

On apply:
- Write each file via `POST /docker/generate/write`
- Show per-file result (✅ / ❌)
- CTA: "Next: Set up CI/CD →"

---

## 5. ENDPOINTS USED

| Step | Endpoint | Purpose |
|------|----------|---------|
| Detect | `GET /docker/status` | CLI, daemon, files |
| Detect | `GET /config` | Modules with stacks/domains |
| Preview | `POST /docker/generate/dockerfile` | Per-module Dockerfile |
| Preview | `POST /docker/generate/compose-wizard` | Compose with custom services |
| Preview | `POST /docker/generate/dockerignore` | .dockerignore from stacks |
| Apply | `POST /docker/generate/write` | Write each file to disk |

**No new endpoints needed.** Everything exists.

---

## 6. COMPOSE GENERATION STRATEGY

The existing `/docker/generate/compose` endpoint auto-generates from detected modules, BUT
it has a problem: it doesn't filter by domain, so `core` (library) would get its own service.
Fix options:

**Option A**: Use `/docker/generate/compose-wizard` instead (recommended).
We have full control over the services list. We build it in the frontend from the user's
selections:

```javascript
const services = [];

// Module containers
for (const mod of selectedModules) {
    services.push({
        name: mod.name,
        build_context: dockerfileLocation === 'module' ? `./${mod.path}` : '.',
        ports: [`${mod.port}:${mod.port}`],
        restart: 'unless-stopped',
    });
}

// Infra services
if (usePostgres) {
    services.push({
        name: 'postgres',
        image: 'postgres:16-alpine',
        ports: ['5432:5432'],
        environment: { POSTGRES_DB: 'app', POSTGRES_USER: 'app', POSTGRES_PASSWORD: 'changeme' },
        volumes: ['pgdata:/var/lib/postgresql/data'],
        restart: 'unless-stopped',
    });
}
// ...etc
```

**Option B**: Fix the compose generator to accept a filter.
This would require a backend change. Not needed since Option A works perfectly.

→ **Going with Option A.**

---

## 7. MULTI-CONTAINER DOCKERFILE STRATEGY

When multiple modules are selected:
- Each needs a Dockerfile generated from its stack
- Each Dockerfile should be in `{module.path}/Dockerfile`
- Compose build contexts point to each module directory

When a single module is selected:
- Dockerfile at project root (or user can choose module dir)
- Compose build context is `.`

The generator's `output_path` parameter supports this:
```python
generate_dockerfile(project_root, stack_name, output_path="src/ui/web/Dockerfile")
```

But the current API endpoint (`POST /docker/generate/dockerfile`) doesn't accept `output_path`.
It always returns `path: "Dockerfile"`. We can handle this client-side by modifying the
file data before calling write:

```javascript
fileData.path = `${mod.path}/Dockerfile`;
```

The write endpoint respects whatever path is in the file data.

---

## 8. FILES TO EDIT

| File | What changes |
|------|-------------|
| `_integrations_setup_modals.html` | Replace `openDockerSetupWizard()` (lines 418-592) |

**One file.** No backend changes. No new endpoints.

Optional follow-up:
- `_integrations_docker.html` — add "Reconfigure" button (but not required for this ticket)

---

## 9. KEY EDGE CASES

| Scenario | Handling |
|----------|---------|
| No modules in config | Show "No modules detected — configure modules in Settings first" |
| All modules are libraries | Show "No deployable modules found" with option to force-select |
| Only 1 deployable module | Pre-select it, suggest root Dockerfile, compose optional |
| Multiple deployable modules | Pre-select all, suggest per-module Dockerfiles, compose auto-checked |
| Dockerfile already exists | Show warning, offer overwrite |
| Multiple existing Dockerfiles | Show each with status |
| Docker not installed | Allow config generation, disable "build now" options |
| Daemon not running | Allow config generation, show warning |
| Port conflicts | Validation error in Configure step with specific ports listed |
| Monolith (all same language, all in subdir of src/) | Smart suggestion: single Dockerfile at root |
| Microservices (different languages, independent dirs) | Smart suggestion: per-module Dockerfiles |

---

## 10. WHAT I WILL NOT DO

- **No backend changes.** Everything needed exists.
- **No new UI components.** Reuse wizard infrastructure (wizSection, wizFormGrid, wizStatusRow, etc.)
- **No changes to generators.** They work perfectly.
- **No changes to the Docker card.** The wizard replaces the setup flow, not the card.
- **No `setup_docker` action.** The new wizard uses proper generators + write endpoint.
