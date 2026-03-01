# Docker Service

> Container lifecycle management for the devops control plane.
> Handles detection, generation, operations, and cross-domain bridging
> for Docker and Docker Compose — from environment probing to live
> container streaming actions.

---

## How It Works

The Docker service operates in **four modes** depending on what the user
needs:

### 1. Detection — What exists?

`detect.py` probes the host and the project simultaneously:

```
HOST PROBES                           PROJECT PROBES
  docker --version                      Scan for Dockerfile, Dockerfile.*
  docker info (daemon?)                 Parse Dockerfile → base images, stages, ports
  docker compose version                Scan for compose.yml / docker-compose.yml
                                        Parse compose → services, ports, env, volumes
                                        Scan for .dockerignore → patterns
                                        Validate compose structure → warnings
```

The result is a single `docker_status()` dict that feeds every consumer:
dashboard cards, K8s bridge, wizard detection, audit system cards.

**Key design:** File detection always runs, even when Docker CLI is missing.
The UI can still show "you have a Dockerfile but Docker isn't installed"
— which triggers the tool_install flow.

### 2. Operations — Observe and act

`containers.py` wraps every Docker and Compose command into a structured
dict API. Two execution modes:

| Mode | Implementation | Use Case |
|------|---------------|----------|
| **Blocking** | `run_docker()` / `run_compose()` → `subprocess.run` | Status, logs, inspect — fast, returns dict |
| **Streaming** | `docker_action_stream()` → `Popen` + line generator | Up, down, build, prune — yields events live via SSE |

The streaming dispatch uses the `_STREAMABLE_ACTIONS` registry — each
action maps to its compose/docker args, display label, and audit metadata.
Adding a new streamable action = add one dict entry.

Every mutating action (`up`, `down`, `build`, `prune`, `rm`, `pull`) is
audited via `make_auditor("docker")` — the activity log tracks who did
what, when, and the outcome.

### 3. Generation — Create configs

`generate.py` produces Docker configs from two sources:

- **Auto-detect:** Uses `generators/*.py` to generate Dockerfiles,
  .dockerignore, and compose files from project module detection.
- **Wizard:** Takes user-defined service specs and produces compose YAML
  with full diff tracking against existing files.

Both paths go through `write_generated_file()` — the shared writer that
handles path traversal protection, overwrite confirmation, and audit
logging with before/after diffs.

### 4. K8s Bridge — Cross-domain translation

`k8s_bridge.py` is **pure data transformation** — no I/O, no subprocess:

```
compose_service_details     →     K8s service definitions
  name, image, ports,               name, image, port,
  build.args                         kind: Deployment,
                                     build_args
```

Priority: compose services > Dockerfile analysis.
Output feeds directly into `wizard_state_to_resources()`.

---

## Architecture

```
                  CLI (ui/cli/docker.py)
                  Routes (routes/docker.py)
                         │
                         │ imports
                         │
              ┌──────────▼──────────┐
              │  docker_ops.py      │  backward-compat shim
              │  (re-exports all)   │  → imports from docker/
              └──────────┬──────────┘
                         │
              ┌──────────▼──────────────────────────┐
              │  docker/__init__.py                   │
              │  Public API — re-exports all symbols  │
              └────┬──────┬──────┬──────┬──────┬─────┘
                   │      │      │      │      │
         ┌─────┐  │  ┌───┘  ┌───┘  ┌───┘   ┌──┘
         ▼     ▼  ▼  ▼      ▼      ▼       ▼
    common.py  detect.py  containers.py  generate.py  k8s_bridge.py
    (runners)  (probes)   (CRUD+stream)  (configs)    (pure data)
         ▲        ▲
         │        │
         └────────┘
      detect + containers
      import from common
```

### Dependency Rules

| Rule | Example |
|------|---------|
| `common.py` is standalone | No imports from other docker modules |
| `detect.py` imports `common` only | Uses `run_docker`, `run_compose` for CLI probes |
| `containers.py` imports `common` + `detect` | Uses runners + `find_compose_file()` |
| `generate.py` is self-contained | Imports from `generators/` and `audit_helpers`, not from docker |
| `k8s_bridge.py` is self-contained | Pure data transformation, zero imports from docker |

---

## File Map

```
docker/
├── __init__.py      Public API re-exports (70 lines)
├── common.py        Subprocess runners — run_docker, run_compose + streaming variants (139 lines)
├── detect.py        Docker/Compose environment detection + Dockerfile/compose parsing (585 lines)
├── containers.py    Container/image/network/volume CRUD + streaming action dispatch (734 lines)
├── generate.py      Dockerfile, .dockerignore, compose generation + write_generated_file (375 lines)
├── k8s_bridge.py    Docker → K8s service translation — pure data, no I/O (134 lines)
└── README.md        This file
```

Backward compat: `docker_ops.py` (10 lines) remains in `services/` as a
thin re-export shim. All existing `from src.core.services.docker_ops import X`
keeps working. New code should import from `src.core.services.docker`.

---

## Key Functions

### common.py — Subprocess Runners

| Function | What It Does |
|----------|-------------|
| `run_docker(*args)` | `subprocess.run(["docker", *args])` with timeout, capture |
| `run_compose(*args)` | `subprocess.run(["docker", "compose", *args])` with timeout |
| `run_docker_stream(*args)` | `Popen` generator — yields `(source, line)` tuples |
| `run_compose_stream(*args)` | Same for compose commands |

### detect.py — Environment Probing

| Function | What It Does |
|----------|-------------|
| `docker_status(project_root)` | **Main entry** — full Docker/Compose environment report |
| `find_compose_file(project_root)` | Find first compose file (4 naming conventions) |
| `_parse_dockerfile(path)` | Extract base images, stages, ports, warnings |
| `_parse_compose_services(path)` | Service names from compose YAML |
| `_parse_compose_service_details(path)` | Full 42-field service specs (identity, runtime, networking, files, logging, lifecycle) |
| `_env_list_to_dict(items)` | `["KEY=VAL", ...]` → `{"KEY": "VAL", ...}` |
| `_normalise_ports(raw)` | Normalize all port formats → `[{host, container, protocol}]` |

### containers.py — Operations

| Function | What It Does |
|----------|-------------|
| `docker_action_stream(root, action)` | **Streaming dispatch** — up/down/restart/build/prune via SSE |
| `docker_containers(root)` | List containers (JSON format) |
| `docker_images(root)` | List local images |
| `docker_compose_status(root)` | Compose service states |
| `docker_logs(root, service)` | Service log tail |
| `docker_stats(root)` | One-shot CPU/memory/IO stats |
| `docker_build/up/down/restart/prune` | Individual compose commands (blocking) |
| `docker_networks/volumes/inspect` | Infrastructure queries |
| `docker_pull/exec_cmd/rm/rmi` | Container/image management |

### generate.py — Config Generation

| Function | What It Does |
|----------|-------------|
| `generate_dockerfile(root, stack)` | Dockerfile from stack template |
| `generate_dockerignore(root, stacks)` | .dockerignore from stack patterns |
| `generate_compose(root, modules)` | Compose from project module detection |
| `generate_compose_from_wizard(root, services)` | Compose from wizard service specs (with diff) |
| `write_generated_file(root, file_data)` | Write any generated file to disk (with audit + security) |

### k8s_bridge.py — Cross-Domain Translation

| Function | What It Does |
|----------|-------------|
| `docker_to_k8s_services(docker_status)` | Translate Docker detection → K8s wizard service definitions |

---

## Consumers

| Layer | Module | What It Uses |
|-------|--------|-------------|
| **CLI** | `ui/cli/docker.py` | All container ops, generation, `write_generated_file` |
| **CLI** | `ui/cli/security.py`, `ci.py`, `k8s.py`, etc. | `write_generated_file` (shared writer) |
| **Routes** | `routes/docker.py` | `docker_ops.*` — all detection + operations + generation |
| **Services** | `k8s_validate.py` | `docker_status` (for cross-domain validation L6) |
| **Services** | `wizard/helpers.py` | `docker_status` (for wizard environment detection) |
| **Services** | `metrics_ops.py` | `docker_status` (for metrics collection) |

---

## API Endpoints

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/docker/status` | GET | Full docker_status() + compose detection |
| `/api/docker/containers` | GET | Container list (all or running) |
| `/api/docker/images` | GET | Local image list |
| `/api/docker/compose/status` | GET | Compose service states |
| `/api/docker/logs/<service>` | GET | Service log tail |
| `/api/docker/stats` | GET | Container resource usage |
| `/api/docker/action` | POST | Streaming action (up/down/restart/build/prune) via SSE |
| `/api/docker/build` | POST | Build images |
| `/api/docker/networks` | GET | Docker networks |
| `/api/docker/volumes` | GET | Docker volumes |
| `/api/docker/inspect/<id>` | POST | Container inspect |
| `/api/docker/pull` | POST | Pull an image |
| `/api/docker/exec` | POST | Execute command in container |
| `/api/docker/rm` | POST | Remove container |
| `/api/docker/rmi` | POST | Remove image |
| `/api/docker/generate/dockerfile` | POST | Generate Dockerfile |
| `/api/docker/generate/dockerignore` | POST | Generate .dockerignore |
| `/api/docker/generate/compose` | POST | Generate docker-compose.yml |
| `/api/docker/write` | POST | Write generated file to disk |
