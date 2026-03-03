# CLI Domain: Docker — Detection, Observation, Actions & Generation

> **5 files · 468 lines · 14 commands + 1 subgroup · Group: `controlplane docker`**
>
> The largest CLI domain. Full Docker lifecycle management: detect
> Docker/Compose availability, observe containers/images/services/logs/stats,
> execute Compose actions (build, up, down, restart, prune), and generate
> Dockerfiles, .dockerignore, and docker-compose.yml from project context.
>
> Core service: `core/services/docker/ops.py` (re-exported via `docker_ops.py`)

---

## How It Works

```
┌──────────────────────────────────────────────────────────────────────┐
│                       controlplane docker                           │
│                                                                      │
│  ┌─ Detect ──┐  ┌──── Observe ─────────┐  ┌── Act ─────────────┐   │
│  │ status    │  │ containers           │  │ build              │   │
│  └───────────┘  │ images               │  │ up                 │   │
│                  │ ps (compose status)  │  │ down               │   │
│                  │ logs SERVICE         │  │ restart            │   │
│                  │ stats                │  │ prune              │   │
│                  └─────────────────────-┘  └────────────────────┘   │
│                                                                      │
│  ┌── Generate ──────────────────────────────────────────────────┐   │
│  │ generate dockerfile STACK  [--write] [--base-image]         │   │
│  │ generate dockerignore STACKS... [--write]                   │   │
│  │ generate compose [--write]                                  │   │
│  └─────────────────────────────────────────────────────────────┘   │
└──────────┬───────────────────┬───────────────────┬─────────────────┘
           │                   │                   │
           ▼                   ▼                   ▼
┌──────────────────────────────────────────────────────────────────────┐
│                core/services/docker/ops.py (via docker_ops.py)      │
│                                                                      │
│  docker_status(root)          → version, daemon, compose, files     │
│  docker_containers(root)      → containers[] with state, ports      │
│  docker_images(root)          → images[] with repo, tag, size       │
│  docker_compose_status(root)  → services[] with state, status       │
│  docker_logs(root, svc, n)    → logs text                           │
│  docker_stats(root)           → stats[] with cpu, memory            │
│  docker_build(root, svc)      → build output                        │
│  docker_up(root, svc)         → start result                        │
│  docker_down(root, vols)      → stop result                         │
│  docker_restart(root, svc)    → restart result                      │
│  docker_prune(root)           → prune output                        │
│  generate_dockerfile(root, stack, base) → file data                 │
│  generate_dockerignore(root, stacks)    → file data                 │
│  generate_compose(root)                 → file data                 │
│  write_generated_file(root, file_data)  → write result              │
└──────────────────────────────────────────────────────────────────────┘
```

### Four-Phase Pattern

Docker is the only CLI domain that has **four** phases instead of
the usual three (detect-observe-generate). The addition of **Act** is
unique because Docker has side effects (start/stop containers):

1. **Detect** (`status`) — is Docker installed, is the daemon running,
   what project files exist?
2. **Observe** (`containers`, `images`, `ps`, `logs`, `stats`) — what's
   the current state of the Docker environment?
3. **Act** (`build`, `up`, `down`, `restart`, `prune`) — change state
4. **Generate** (`generate dockerfile`, `generate dockerignore`,
   `generate compose`) — create configuration files

### File Organization

The domain is split into 4 sub-modules (plus `__init__.py`) matching
the four phases:

```
__init__.py   → group definition + _resolve_project_root
detect.py     → Detect phase (status)
observe.py    → Observe phase (containers, images, ps, logs, stats)
actions.py    → Act phase (build, up, down, restart, prune)
generate.py   → Generate phase (dockerfile, dockerignore, compose)
```

### Preview-or-Write Pattern

All three `generate` commands follow the same pattern:

```
generate dockerfile python
├── Call core: generate_dockerfile(root, "python")
│   └── Returns {file: {path, content, reason}}
├── --write provided?
│   ├── Yes → write_generated_file(root, file) → "✅ Written: path"
│   └── No  → Preview: show content + "(use --write to save to disk)"
└── Error? → Show error + exit(1)
```

This pattern is shared across Docker, CI, K8s, Security, Terraform,
Testing, Quality, and Infra generate commands. The `write_generated_file`
utility lives in `docker_ops` for historical reasons.

---

## Commands

### `controlplane docker status`

Show Docker integration status.

```bash
controlplane docker status
controlplane docker status --json
```

**Output example:**

```
🐳 Docker
   Version:  24.0.5
   Daemon:   ✅ running
   Compose:  ✅ available
   Compose v: 2.21.0

   📄 Dockerfiles (2):
      Dockerfile
      Dockerfile.dev
   📋 Compose: docker-compose.yml
      Services: web, db, redis
```

---

### `controlplane docker containers`

List Docker containers with state icons.

```bash
controlplane docker containers
controlplane docker containers --running
controlplane docker containers --json
```

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--running` | flag | off | Only show running containers (default: show all) |
| `--json` | flag | off | JSON output |

**Output example:**

```
📦 Containers (3):
   🟢 myapp-web               myapp:latest
      Status: Up 2 hours  Ports: 0.0.0.0:8080->8080/tcp
   🟢 myapp-db                postgres:15
      Status: Up 2 hours  Ports: 5432/tcp
   🔴 myapp-worker            myapp:latest
      Status: Exited (1) 30 minutes ago  Ports: -
```

**State icons:** 🟢 = running, 🔴 = exited, ⚪ = other (paused, created, etc.)

---

### `controlplane docker images`

List local Docker images.

```bash
controlplane docker images
controlplane docker images --json
```

**Output example:**

```
🖼️  Images (4):
   myapp:latest  (245MB)
   postgres:15  (390MB)
   redis:7-alpine  (32MB)
   node:20-slim  (180MB)
```

---

### `controlplane docker ps`

Show Compose service status (project-scoped, not global).

```bash
controlplane docker ps
controlplane docker ps --json
```

**Output example:**

```
🐳 Compose services (3):
   🟢 web                     running
   🟢 db                      running
   🔴 worker                  exited (1)
```

---

### `controlplane docker logs SERVICE`

Show logs for a Compose service.

```bash
controlplane docker logs web
controlplane docker logs web -n 50    # last 50 lines
```

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `SERVICE` | argument | (required) | Compose service name |
| `-n` | int | 100 | Number of lines to show (tail) |

---

### `controlplane docker stats`

Show container resource usage (CPU and memory).

```bash
controlplane docker stats
controlplane docker stats --json
```

**Output example:**

```
📊 Resource usage (3):
   web                      CPU: 2.5%  Mem: 128.4MiB
   db                       CPU: 0.3%  Mem: 256.2MiB
   redis                    CPU: 0.1%  Mem: 12.8MiB
```

---

### `controlplane docker build`

Build images via Compose.

```bash
controlplane docker build                # build all services
controlplane docker build -s web         # build specific service
```

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `-s/--service` | string | (all) | Specific service to build |

**Output:** Shows build progress and last 500 characters of build output.

---

### `controlplane docker up`

Start Compose services (detached mode).

```bash
controlplane docker up
controlplane docker up -s web
```

---

### `controlplane docker down`

Stop and remove Compose services.

```bash
controlplane docker down                 # stop services
controlplane docker down -v             # also remove named volumes
```

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `-v/--volumes` | flag | off | Also remove named volumes |

---

### `controlplane docker restart`

Restart Compose services.

```bash
controlplane docker restart
controlplane docker restart -s web
```

---

### `controlplane docker prune`

Remove unused containers, images, and build cache.

```bash
controlplane docker prune
```

---

### `controlplane docker generate dockerfile STACK`

Generate a Dockerfile for a specific stack.

```bash
controlplane docker generate dockerfile python
controlplane docker generate dockerfile python --write
controlplane docker generate dockerfile node --base-image node:20-alpine --write
```

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `STACK` | argument | (required) | Stack name (python, node, go, etc.) |
| `--write` | flag | off | Write to disk |
| `--base-image` | string | (auto) | Custom base image for builder stage |

**Error on unsupported stack:**

```
❌ Unsupported stack: rust
   Supported: python, node, go, java, ruby
```

---

### `controlplane docker generate dockerignore STACKS...`

Generate a `.dockerignore` for one or more stacks.

```bash
controlplane docker generate dockerignore python node
controlplane docker generate dockerignore python node --write
```

Takes multiple stack names to combine their ignore patterns.

---

### `controlplane docker generate compose`

Generate a `docker-compose.yml` from detected project modules.

```bash
controlplane docker generate compose
controlplane docker generate compose --write
```

---

## File Map

```
cli/docker/
├── __init__.py     36 lines — group definition, _resolve_project_root,
│                              sub-module imports (detect, observe, actions, generate)
├── detect.py       61 lines — status command
├── observe.py     155 lines — containers, images, ps, logs, stats commands
├── actions.py     108 lines — build, up, down, restart, prune commands
├── generate.py    108 lines — generate subgroup (dockerfile, dockerignore, compose)
└── README.md               — this file
```

**Total: 468 lines of Python across 5 files.**

---

## Per-File Documentation

### `__init__.py` — Group definition (36 lines)

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `_resolve_project_root(ctx)` | helper | Reads `config_path` from context, falls back to `find_project_file()` |
| `docker()` | Click group | Top-level `docker` group |
| `from . import detect, observe, actions, generate` | import | Registers all sub-modules |

---

### `detect.py` — Status command (61 lines)

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `status(ctx, as_json)` | command | Show Docker version, daemon status, Compose availability, Dockerfiles, compose file + services |

**Core service import (lazy):**

| Import | From | Used For |
|--------|------|----------|
| `docker_status` | `docker_ops` | All detection logic |

**Display logic:** The `status` command renders 5 distinct sections:
version/daemon/compose, Dockerfiles list, and compose file + services.
Each section is conditionally displayed (e.g., if no Dockerfiles exist,
shows "📄 No Dockerfiles found").

---

### `observe.py` — 5 observation commands (155 lines)

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `containers(ctx, running, as_json)` | command | List containers with state icons, image, status, ports |
| `images(ctx, as_json)` | command | List images with repo:tag and size |
| `compose_ps(ctx, as_json)` | command (`ps`) | Show compose service states |
| `logs(ctx, service, tail)` | command | Show service logs (last N lines) |
| `stats(ctx, as_json)` | command | Show CPU + memory per container |

**Core service imports (all lazy):**

| Import | From | Used For |
|--------|------|----------|
| `docker_containers` | `docker_ops` | Container listing with `all_` toggle |
| `docker_images` | `docker_ops` | Image listing |
| `docker_compose_status` | `docker_ops` | Compose service status |
| `docker_logs` | `docker_ops` | Service log retrieval |
| `docker_stats` | `docker_ops` | Resource usage metrics |

**Note on `containers --running`:** The `--running` flag is inverted
when passed to the core service: `all_=not running`. This means by
default all containers are shown (`all_=True`), and `--running` limits
to only running ones.

**Note on `logs`:** Unlike other commands, `logs` has no `--json` flag —
log output is always raw text. It also has no `--json` because logs
aren't structured data. The command truncates to the last `n` lines
(default 100).

---

### `actions.py` — 5 action commands (108 lines)

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `build(ctx, service)` | command | Build images via `docker compose build` |
| `up(ctx, service)` | command | Start services via `docker compose up -d` |
| `down(ctx, volumes)` | command | Stop + remove via `docker compose down` |
| `restart(ctx, service)` | command | Restart via `docker compose restart` |
| `prune(ctx)` | command | Remove unused resources via `docker system prune` |

**Core service imports (all lazy):**

| Import | From | Used For |
|--------|------|----------|
| `docker_build` | `docker_ops` | Image building |
| `docker_up` | `docker_ops` | Service startup (detached) |
| `docker_down` | `docker_ops` | Service teardown (optional volume removal) |
| `docker_restart` | `docker_ops` | Service restart |
| `docker_prune` | `docker_ops` | Resource cleanup |

**Side effects:** These are the only commands in any CLI domain that
have destructive side effects on the host system. `prune` in particular
removes unused containers, images, and build cache. `down -v` removes
named volumes (data loss risk).

**Build output truncation:** `build` shows only the last 500 characters
of build output (`result["output"][-500:]`) to keep terminal output
manageable for large builds.

---

### `generate.py` — Generate subgroup + 3 commands (108 lines)

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `generate()` | Click group | `docker generate` subgroup |
| `gen_dockerfile(ctx, stack_name, write, base_image)` | command (`generate dockerfile`) | Generate Dockerfile for a stack |
| `gen_dockerignore(ctx, stack_names, write)` | command (`generate dockerignore`) | Generate .dockerignore for stacks |
| `gen_compose(ctx, write)` | command (`generate compose`) | Generate docker-compose.yml from modules |

**Core service imports (all lazy):**

| Import | From | Used For |
|--------|------|----------|
| `generate_dockerfile` | `docker_ops` | Dockerfile generation (stack-aware) |
| `generate_dockerignore` | `docker_ops` | .dockerignore generation (multi-stack) |
| `generate_compose` | `docker_ops` | docker-compose.yml from detected modules |
| `write_generated_file` | `docker_ops` | Shared file writer utility |

**dockerignore multi-stack:** `gen_dockerignore` takes `nargs=-1` (variadic
argument), so it can combine ignore patterns from multiple stacks
(e.g., `python node` combines Python and Node.js patterns).

**dockerfile --base-image:** Allows overriding the builder stage base image.
Useful for custom registries or specific image requirements.

---

## Dependency Graph

```
__init__.py
├── click                     ← click.group
├── core.config.loader        ← find_project_file (lazy)
└── Imports: detect, observe, actions, generate

detect.py
├── click                     ← click.command
└── core.services.docker_ops  ← docker_status (lazy)

observe.py
├── click                     ← click.command
└── core.services.docker_ops  ← docker_containers, docker_images,
                                 docker_compose_status, docker_logs,
                                 docker_stats (all lazy)

actions.py
├── click                     ← click.command
└── core.services.docker_ops  ← docker_build, docker_up, docker_down,
                                 docker_restart, docker_prune (all lazy)

generate.py
├── click                     ← click.group, click.command
└── core.services.docker_ops  ← generate_dockerfile, generate_dockerignore,
                                 generate_compose, write_generated_file (all lazy)
```

All 4 sub-modules import only from `docker_ops`. No cross-domain imports.
No cross-file imports between sub-modules.

---

## Consumers

### Who registers this CLI group

| Layer | Module | What It Does |
|-------|--------|-------------|
| CLI entry | `src/main.py:453` | `from src.ui.cli.docker import docker` |

### Who also uses the same core service

| Layer | Module | Core Service Used |
|-------|--------|------------------|
| Web routes | `routes/docker/` | `docker_ops` (status, containers, images, compose, build, up, down) |
| Core | `metrics/ops.py:87` | `docker_status` (health probe) |
| Core | `wizard/helpers.py:44` | `docker_status` (wizard environment detection) |

### Who uses `write_generated_file` from `docker_ops`

This utility is the shared file-writing function for all generate commands:

| CLI Domain | Commands |
|-----------|----------|
| `cli/ci` | generate ci, generate lint |
| `cli/docs` | generate mkdocs, generate readme |
| `cli/infra` | generate env, compose helper |
| `cli/k8s` | generate k8s |
| `cli/quality` | generate editorconfig |
| `cli/security` | generate security |
| `cli/terraform` | generate terraform |
| `cli/testing` | generate pytest, generate coverage |

---

## Design Decisions

### Why four sub-modules (not one file)

At 468 lines and 14 commands, a single file would be unwieldy. The
four-file split maps directly to the four phases (detect, observe, act,
generate), making it easy to find any command by its category.

### Why actions.py doesn't have --json output

Actions are imperative commands with side effects. Their output is
a simple success/failure message, not structured data. Adding `--json`
would only wrap a `{"status": "ok"}` message that provides no value
over the exit code.

### Why logs has no --json flag

Log output is unstructured text by nature. JSON-wrapping a text blob
adds no value. The web UI handles log rendering separately with
streaming and syntax highlighting.

### Why build truncates output to 500 characters

Docker build output can be extremely long (pulling layers, compiling,
installing dependencies). The CLI shows only the tail end to confirm
the build completed. Users who need full output should use
`docker compose build` directly.

### Why `write_generated_file` lives in docker_ops

This is a historical artifact. The utility predates the domain split
and was originally only used by Docker generate commands. Rather than
creating a separate utility module, it was left in `docker_ops` and
imported by other domains. Moving it now would require updating 15+
import sites across the CLI codebase.

### Why `down -v` is a flag (not a separate command)

`docker compose down` and `docker compose down -v` are the same
operation with different cleanup scope. Making volume removal a flag
on `down` mirrors Docker's own CLI interface, reducing learning curve.

---

## JSON Output Examples

### `docker status --json`

```json
{
  "available": true,
  "version": "24.0.5",
  "daemon_running": true,
  "compose_available": true,
  "compose_version": "2.21.0",
  "dockerfiles": ["Dockerfile", "Dockerfile.dev"],
  "has_compose": true,
  "compose_file": "docker-compose.yml",
  "compose_services": ["web", "db", "redis"]
}
```

### `docker containers --json`

```json
{
  "available": true,
  "containers": [
    {
      "name": "myapp-web",
      "image": "myapp:latest",
      "state": "running",
      "status": "Up 2 hours",
      "ports": "0.0.0.0:8080->8080/tcp"
    }
  ]
}
```

### `docker stats --json`

```json
{
  "available": true,
  "stats": [
    {"name": "web", "cpu": "2.5%", "memory": "128.4MiB"},
    {"name": "db", "cpu": "0.3%", "memory": "256.2MiB"}
  ]
}
```
