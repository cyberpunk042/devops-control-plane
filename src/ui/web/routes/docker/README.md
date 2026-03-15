# Docker Routes — Container & Compose Management, Generation & SSE Streaming API

> **6 files · 428 lines · 24 endpoints · Blueprint: `docker_bp` · Prefix: `/api`**
>
> Full Docker lifecycle management. These routes cover five domains:
> **detection** (Docker availability, daemon status, project files),
> **observation** (containers, images, compose services, logs, stats,
> networks, volumes, inspection), **actions** (build, up, down, restart,
> prune, pull, exec, rm, rmi — all run-tracked), **generation**
> (Dockerfile, .dockerignore, docker-compose.yml, wizard-based compose,
> file writing — all run-tracked), and **streaming** (SSE real-time
> output for long-running operations). All delegate to
> `src.core.services.docker_ops`.

---

## How It Works

### Request Flow

```
Frontend
│
├── integrations/_docker.html ────── Docker integration panel
│   ├── GET  /api/docker/status       (detection)
│   ├── GET  /api/docker/containers   (observation)
│   ├── GET  /api/docker/images       (observation)
│   ├── POST /api/docker/build        (action)
│   ├── POST /api/docker/up           (action)
│   ├── POST /api/docker/down         (action)
│   └── POST /api/docker/restart      (action)
│
├── integrations/_docker_compose.html ─ Compose panel
│   ├── GET  /api/docker/compose/status
│   ├── GET  /api/docker/logs
│   ├── GET  /api/docker/stats
│   ├── GET  /api/docker/networks
│   └── GET  /api/docker/volumes
│
├── integrations/setup/_docker.html ── Docker setup wizard
│   ├── POST /api/docker/generate/dockerfile
│   ├── POST /api/docker/generate/dockerignore
│   ├── POST /api/docker/generate/compose
│   └── POST /api/docker/generate/write
│
├── docker_wizard/ ─────────────────── Docker wizard
│   ├── POST /api/docker/generate/compose-wizard
│   └── POST /api/docker/generate/write
│
└── wizard/_integration_actions.html
    └── Various docker actions
     │
     ▼
routes/docker/                          ← HTTP layer (this package)
├── __init__.py   — blueprint definition
├── detect.py     — status endpoint (cached)
├── observe.py    — 8 observation endpoints (live)
├── actions.py    — 9 action endpoints (run-tracked)
├── generate.py   — 5 generation endpoints (run-tracked)
└── stream.py     — 1 SSE streaming endpoint
     │
     ▼
core/services/docker_ops.py            ← Business logic (all functions)
```

### Detection Pipeline

```
GET /api/docker/status?bust=1
     │
     ▼
devops_cache.get_cached(root, "docker", ...)
     │
     ├── Cache HIT → return cached snapshot
     └── Cache MISS → docker_ops.docker_status(root)
         │
         ├── Check docker binary availability
         ├── Read docker version
         ├── Check daemon connectivity
         ├── Scan for Dockerfile, docker-compose.yml
         └── Return status dictionary
```

### Observation Pipeline

```
GET /api/docker/containers?all=true
     │
     ▼
docker_ops.docker_containers(root, all_=True)
     │
     └── subprocess: docker ps (or docker ps -a)
         Parse JSON output → structured container list
```

```
GET /api/docker/logs?service=web&tail=100
     │
     ▼
docker_ops.docker_logs(root, "web", tail=100)
     │
     └── subprocess: docker compose logs --tail=100 web
         Capture stdout → structured log output
```

### Action Pipeline (Run-Tracked)

```
POST /api/docker/build  { service: "web", no_cache: true }
     │
     ├── @tracked("docker.built")
     │   └── Records action in run history for audit trail
     │
     ▼
docker_ops.docker_build(root, service="web", no_cache=True)
     │
     └── subprocess: docker compose build --no-cache web
         Capture output → { ok: true, output: "..." }
```

All 9 action endpoints follow the same pattern:

```
Request → @run_tracked( category, label ) → docker_ops.function()
                                              └→ subprocess call
                                              └→ Result dict
```

**Run-tracking categories for actions:**

| Category | Actions |
|----------|---------|
| `build` | `docker_build` |
| `deploy` | `docker_up`, `docker_restart` |
| `destroy` | `docker_down`, `docker_prune`, `docker_rm`, `docker_rmi` |
| `install` | `docker_pull` |
| `test` | `docker_exec` |

### Generation Pipeline (Run-Tracked)

```
POST /api/docker/generate/dockerfile  { stack: "python", base_image: "python:3.12-slim" }
     │
     ├── @tracked("docker.dockerfile.generated")
     │
     ▼
docker_ops.generate_dockerfile(root, "python", base_image="python:3.12-slim")
     │
     └── Generate Dockerfile content based on stack template
         → { ok: true, content: "FROM python:3.12-slim\n...", path: "Dockerfile" }
```

```
POST /api/docker/generate/compose-wizard
{ project_name: "my-app",
  services: [
    { name: "web", image: "python:3.12", ports: ["8080:8080"],
      volumes: [".:/app"], depends_on: ["db"] },
    { name: "db", image: "postgres:16",
      environment: { POSTGRES_DB: "mydb" },
      volumes: ["pgdata:/var/lib/postgresql/data"] }
  ]
}
     │
     ├── @tracked("docker.compose.wizard")
     │
     ▼
docker_ops.generate_compose_from_wizard(root, services, project_name="my-app")
     │
     └── Build docker-compose.yml from service definitions
         Each service: name, image, build_context, dockerfile, ports,
         volumes, environment, depends_on, restart, command, networks
```

### SSE Streaming Pipeline

```
POST /api/docker/stream/build  { service: "web" }
     │
     ├── Validate: action ∈ { up, down, restart, build, build-nc, prune }
     │
     ▼
docker_ops.docker_action_stream(root, "build", service="web")
     │ (generator function — yields events)
     │
     ├── yield { type: "stdout", line: "Step 1/10 : FROM python:3.12" }
     ├── yield { type: "stdout", line: "Step 2/10 : WORKDIR /app" }
     ├── yield { type: "stdout", line: "Successfully built abc123" }
     └── yield { type: "done", exit_code: 0 }
     │
     ▼
Response: text/event-stream
     data: {"type":"stdout","line":"Step 1/10 ..."}
     data: {"type":"stdout","line":"Step 2/10 ..."}
     data: {"type":"done","exit_code":0}
```

---

## File Map

```
routes/docker/
├── __init__.py       21 lines — blueprint, sub-module imports
├── detect.py         24 lines — 1 endpoint: status (cached)
├── observe.py        74 lines — 8 endpoints: containers, images, compose, logs, stats, networks, volumes, inspect
├── actions.py       158 lines — 9 endpoints: build, up, down, restart, prune, pull, exec, rm, rmi
├── generate.py      115 lines — 5 endpoints: dockerfile, dockerignore, compose, compose-wizard, write
├── stream.py         36 lines — 1 endpoint: SSE streaming
└── README.md                  — this file
```

---

## Per-File Documentation

### `__init__.py` — Blueprint Definition (21 lines)

```python
docker_bp = Blueprint("docker", __name__)

from . import detect, observe, actions, generate, stream
```

Blueprint-only file. Sub-module imports at the end register all
route handlers on `docker_bp`.

### `detect.py` — Status Detection (24 lines)

| Function | Method | Route | What It Does |
|----------|--------|-------|-------------|
| `docker_status()` | GET | `/docker/status` | Docker availability, version, daemon (**cached**) |

```python
from src.core.services.devops.cache import get_cached

root = _project_root()
force = request.args.get("bust", "") == "1"
return jsonify(get_cached(
    root, "docker",
    lambda: docker_ops.docker_status(root),
    force=force,
))
```

The cache import is lazy (inside the handler function), not at
module level, to avoid importing the cache subsystem just to
define the blueprint.

### `observe.py` — Observation Endpoints (74 lines)

| Function | Method | Route | Params | What It Does |
|----------|--------|-------|--------|-------------|
| `docker_containers()` | GET | `/docker/containers` | `?all=true` | List containers |
| `docker_images()` | GET | `/docker/images` | — | List local images |
| `docker_compose_status()` | GET | `/docker/compose/status` | — | Compose service status |
| `docker_logs()` | GET | `/docker/logs` | `?service=web&tail=100` | Service logs |
| `docker_stats()` | GET | `/docker/stats` | — | Container resource usage |
| `docker_networks()` | GET | `/docker/networks` | — | List networks |
| `docker_volumes()` | GET | `/docker/volumes` | — | List volumes |
| `docker_inspect()` | GET | `/docker/inspect` | `?id=container_id` | Container details |

**Containers — all param with default:**

```python
all_ = request.args.get("all", "true").lower() in ("true", "1", "yes")
return jsonify(docker_ops.docker_containers(_project_root(), all_=all_))
```

Defaults to showing all containers (including stopped). The frontend
typically wants all; interactive use might pass `?all=false` to see
only running.

**Logs — service + tail params:**

```python
service = request.args.get("service", "")
if not service:
    return jsonify({"error": "Missing 'service' parameter"}), 400
tail = request.args.get("tail", 100, type=int)
result = docker_ops.docker_logs(_project_root(), service, tail=tail)
```

### `actions.py` — Docker Actions (158 lines)

| Function | Method | Route | Tracked As | What It Does |
|----------|--------|-------|-----------|-------------|
| `docker_build()` | POST | `/docker/build` | `build:docker` | Build images via compose |
| `docker_up()` | POST | `/docker/up` | `deploy:docker_up` | Start compose services |
| `docker_down()` | POST | `/docker/down` | `destroy:docker_down` | Stop compose services |
| `docker_restart()` | POST | `/docker/restart` | `deploy:docker_restart` | Restart compose services |
| `docker_prune()` | POST | `/docker/prune` | `destroy:docker_prune` | Remove unused resources |
| `docker_pull()` | POST | `/docker/pull` | `install:docker_pull` | Pull a Docker image |
| `docker_exec()` | POST | `/docker/exec` | `test:docker_exec` | Execute command in container |
| `docker_rm()` | POST | `/docker/rm` | `destroy:docker_rm` | Remove a container |
| `docker_rmi()` | POST | `/docker/rmi` | `destroy:docker_rmi` | Remove an image |

All action endpoints follow the same pattern:

```python
@docker_bp.route("/docker/build", methods=["POST"])
@tracked("docker.built")
def docker_build():
    data = request.get_json(silent=True) or {}
    service = data.get("service")
    no_cache = data.get("no_cache", False)
    root = _project_root()
    result = docker_ops.docker_build(root, service=service, no_cache=no_cache)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)
```

**Down with volumes option:**

```python
volumes = data.get("volumes", False)  # if True, also removes volumes
result = docker_ops.docker_down(root, volumes=volumes)
```

**Rm/Rmi with force option:**

```python
force = data.get("force", False)
result = docker_ops.docker_rm(root, container, force=force)
```

**Exec — container + command required:**

```python
container = data.get("container", "")
command = data.get("command", "")
if not container:
    return jsonify({"error": "Missing 'container' field"}), 400
if not command:
    return jsonify({"error": "Missing 'command' field"}), 400
result = docker_ops.docker_exec_cmd(root, container, command)
```

### `generate.py` — File Generation (115 lines)

| Function | Method | Route | Tracked As | What It Does |
|----------|--------|-------|-----------|-------------|
| `generate_dockerfile()` | POST | `/docker/generate/dockerfile` | `generate:dockerfile` | Generate Dockerfile for stack |
| `generate_dockerignore()` | POST | `/docker/generate/dockerignore` | `generate:dockerignore` | Generate .dockerignore for stacks |
| `generate_compose()` | POST | `/docker/generate/compose` | `generate:compose` | Generate compose from detection |
| `generate_compose_wizard()` | POST | `/docker/generate/compose-wizard` | `generate:compose_wizard` | Generate compose from wizard defs |
| `write_generated()` | POST | `/docker/generate/write` | `generate:docker_write` | Write generated file to disk |

**Dockerfile with optional base image:**

```python
stack_name = data.get("stack", "")
base_image = data.get("base_image") or None  # None → auto-detect
result = docker_ops.generate_dockerfile(root, stack_name, base_image=base_image)
```

**Dockerignore — multi-stack:**

```python
stacks = data.get("stacks", [])  # e.g., ["python", "node"]
result = docker_ops.generate_dockerignore(root, stacks)
```

**Compose wizard — rich service definitions:**

```python
result = docker_ops.generate_compose_from_wizard(
    root, services,
    project_name=data.get("project_name", ""),
)
```

Each service accepts: `name`, `image`, `build_context`, `dockerfile`,
`ports`, `volumes`, `environment`, `depends_on`, `restart`, `command`,
`networks`.

**Write to disk — two-phase generation:**

```python
file_data = data.get("file")  # { path: "Dockerfile", content: "..." }
result = docker_ops.write_generated_file(root, file_data)
```

The generate endpoints produce content in memory. The write endpoint
persists it. This two-phase pattern lets the frontend preview
before writing.

### `stream.py` — SSE Streaming (36 lines)

| Function | Method | Route | What It Does |
|----------|--------|-------|-------------|
| `docker_stream()` | POST | `/docker/stream/<action>` | SSE stream for Docker actions |

```python
_ALLOWED_STREAM_ACTIONS = frozenset({
    "up", "down", "restart", "build", "build-nc", "prune"
})

@docker_bp.route("/docker/stream/<action>", methods=["POST"])
def docker_stream(action: str):
    if action not in _ALLOWED_STREAM_ACTIONS:
        return jsonify({"error": f"Unknown action: {action}"}), 400

    data = request.get_json(silent=True) or {}
    service = data.get("service")  # optional service filter
    root = _project_root()

    def sse():
        for event in docker_ops.docker_action_stream(root, action, service=service):
            yield f"data: {json.dumps(event)}\n\n"

    return Response(sse(), mimetype="text/event-stream")
```

The `build-nc` action is `build --no-cache` for streaming.

---

## Dependency Graph

```
__init__.py
└── Imports: detect, observe, actions, generate, stream

detect.py
├── docker_ops            ← docker_status (eager)
├── devops.cache          ← get_cached (lazy, inside handler)
└── helpers               ← project_root

observe.py
├── docker_ops            ← 8 observation functions (eager)
└── helpers               ← project_root

actions.py
├── docker_ops            ← 9 action functions (eager)
├── run_tracker           ← @run_tracked decorator
└── helpers               ← project_root

generate.py
├── docker_ops            ← 5 generation functions (eager)
├── run_tracker           ← @run_tracked decorator
└── helpers               ← project_root

stream.py
├── docker_ops            ← docker_action_stream (eager)
└── helpers               ← project_root
```

**Note:** `docker_ops` is imported eagerly (at module level) by
observe, actions, generate, and stream. Only detect uses a lazy
import for the cache module. This is because the Docker routes
are always used together — if any Docker UI element is loaded,
all sub-modules are imported.

---

## Consumers

| Layer | Module | What It Uses |
|-------|--------|-------------|
| Server | `ui/web/server.py` | Imports `docker_bp`, registers at `/api` prefix |
| Dashboard | `scripts/devops/_env.html` | `/docker/status` (env detection) |
| Docker panel | `scripts/integrations/_docker.html` | status, containers, images, build, up, down, restart |
| Compose panel | `scripts/integrations/_docker_compose.html` | compose/status, logs, stats, networks, volumes |
| Docker setup | `scripts/integrations/setup/_docker.html` | generate endpoints |
| Docker wizard | `scripts/docker_wizard/_raw_step3_preview.html` | compose-wizard, write |
| Wizard | `scripts/wizard/_integration_actions.html` | various docker actions |
| CI/CD panel | `scripts/integrations/_cicd.html` | `/docker/status` (for CI context) |
| K8s panel | `scripts/integrations/_k8s.html` | `/docker/status` (for K8s container context) |
| Terraform panel | `scripts/integrations/_terraform.html` | `/docker/status` (for Terraform context) |

---

## Service Delegation Map

```
Route Handler           →   Core Service Function
──────────────────────────────────────────────────────────────────
DETECT:
docker_status()         →   cache.get_cached("docker", ...)
                              └→ docker_ops.docker_status(root)

OBSERVE:
docker_containers()     →   docker_ops.docker_containers(root, all_)
docker_images()         →   docker_ops.docker_images(root)
docker_compose_status() →   docker_ops.docker_compose_status(root)
docker_logs()           →   docker_ops.docker_logs(root, service, tail)
docker_stats()          →   docker_ops.docker_stats(root)
docker_networks()       →   docker_ops.docker_networks(root)
docker_volumes()        →   docker_ops.docker_volumes(root)
docker_inspect()        →   docker_ops.docker_inspect(root, container)

ACTIONS (all @run_tracked):
docker_build()          →   docker_ops.docker_build(root, service, no_cache)
docker_up()             →   docker_ops.docker_up(root, service)
docker_down()           →   docker_ops.docker_down(root, volumes)
docker_restart()        →   docker_ops.docker_restart(root, service)
docker_prune()          →   docker_ops.docker_prune(root)
docker_pull()           →   docker_ops.docker_pull(root, image)
docker_exec()           →   docker_ops.docker_exec_cmd(root, container, command)
docker_rm()             →   docker_ops.docker_rm(root, container, force)
docker_rmi()            →   docker_ops.docker_rmi(root, image, force)

GENERATE (all @run_tracked):
generate_dockerfile()   →   docker_ops.generate_dockerfile(root, stack, base_image)
generate_dockerignore() →   docker_ops.generate_dockerignore(root, stacks)
generate_compose()      →   docker_ops.generate_compose(root)
generate_compose_wiz()  →   docker_ops.generate_compose_from_wizard(root, services, project_name)
write_generated()       →   docker_ops.write_generated_file(root, file_data)

STREAM:
docker_stream(action)   →   docker_ops.docker_action_stream(root, action, service)
```

---

## Data Shapes

### `GET /api/docker/status` response

```json
{
    "installed": true,
    "version": "24.0.7",
    "daemon_running": true,
    "compose_version": "2.23.3",
    "has_dockerfile": true,
    "has_compose": true,
    "compose_file": "docker-compose.yml"
}
```

### `GET /api/docker/containers?all=true` response

```json
[
    {
        "id": "abc123def456",
        "name": "my-app-web-1",
        "image": "my-app-web:latest",
        "status": "Up 2 hours",
        "state": "running",
        "ports": "0.0.0.0:8080->8080/tcp"
    },
    {
        "id": "789ghi012jkl",
        "name": "my-app-db-1",
        "image": "postgres:16",
        "status": "Exited (0) 1 hour ago",
        "state": "exited",
        "ports": ""
    }
]
```

### `GET /api/docker/compose/status` response

```json
{
    "ok": true,
    "services": [
        { "name": "web", "status": "running", "health": "healthy" },
        { "name": "db", "status": "running", "health": "healthy" },
        { "name": "redis", "status": "exited", "health": "none" }
    ]
}
```

### `GET /api/docker/logs?service=web&tail=50` response

```json
{
    "ok": true,
    "service": "web",
    "lines": [
        "2026-03-02 15:00:01 INFO  Server started on :8080",
        "2026-03-02 15:00:02 INFO  Connected to database",
        "2026-03-02 15:01:15 INFO  GET /api/status 200 12ms"
    ],
    "tail": 50
}
```

### `GET /api/docker/stats` response

```json
[
    {
        "container": "my-app-web-1",
        "cpu_percent": "0.32%",
        "memory_usage": "45.2MiB / 4GiB",
        "memory_percent": "1.10%",
        "net_io": "1.2kB / 850B",
        "block_io": "12.3MB / 0B"
    }
]
```

### `POST /api/docker/build` request + response

```json
// Request:
{ "service": "web", "no_cache": true }

// Response:
{ "ok": true, "output": "Successfully built abc123\nSuccessfully tagged my-app-web:latest" }
```

### `POST /api/docker/up` response

```json
{ "ok": true, "output": "Container my-app-web-1  Started\nContainer my-app-db-1  Started" }
```

### `POST /api/docker/exec` request + response

```json
// Request:
{ "container": "my-app-web-1", "command": "python manage.py migrate" }

// Response:
{ "ok": true, "output": "Running migrations...\nApplied 3 migrations." }
```

### `POST /api/docker/generate/dockerfile` request + response

```json
// Request:
{ "stack": "python", "base_image": "python:3.12-slim" }

// Response:
{
    "ok": true,
    "content": "FROM python:3.12-slim\n\nWORKDIR /app\n\nCOPY requirements.txt .\nRUN pip install --no-cache-dir -r requirements.txt\n\nCOPY . .\n\nEXPOSE 8080\nCMD [\"python\", \"app.py\"]\n",
    "path": "Dockerfile"
}
```

### `POST /api/docker/generate/compose-wizard` request

```json
{
    "project_name": "my-app",
    "services": [
        {
            "name": "web",
            "image": "",
            "build_context": ".",
            "dockerfile": "Dockerfile",
            "ports": ["8080:8080"],
            "volumes": [".:/app"],
            "environment": { "DEBUG": "1" },
            "depends_on": ["db"],
            "restart": "unless-stopped"
        },
        {
            "name": "db",
            "image": "postgres:16",
            "ports": ["5432:5432"],
            "volumes": ["pgdata:/var/lib/postgresql/data"],
            "environment": { "POSTGRES_DB": "mydb", "POSTGRES_PASSWORD": "dev" },
            "restart": "unless-stopped"
        }
    ]
}
```

### `POST /api/docker/stream/build` — SSE events

```
data: {"type":"stdout","line":"Step 1/10 : FROM python:3.12-slim"}

data: {"type":"stdout","line":"Step 2/10 : WORKDIR /app"}

data: {"type":"stdout","line":"Step 3/10 : COPY requirements.txt ."}

data: {"type":"stdout","line":"Successfully built abc123def456"}

data: {"type":"done","exit_code":0}
```

### Error responses

```json
// Missing required field:
{ "error": "Missing 'service' parameter" }

// Docker operation failed:
{ "error": "Docker daemon is not running" }

// Unknown stream action:
{ "error": "Unknown action: invalid" }
```

---

## Advanced Feature Showcase

### 1. Run-Tracked Actions

Every action and generation endpoint uses the `@run_tracked` decorator
to record the operation in the run history:

```python
from src.core.services.events.tracked import tracked

@docker_bp.route("/docker/build", methods=["POST"])
@tracked("docker.built")
def docker_build():
    ...
```

The tracker records:
- Category (`build`, `deploy`, `destroy`, `install`, `test`, `generate`)
- Label (`build:docker`, `deploy:docker_up`, etc.)
- Timestamp, duration, success/failure
- This enables the activity log and audit trail features

### 2. Two-Phase File Generation

Generation endpoints produce content in memory. Writing is a
separate endpoint:

```
Phase 1: POST /docker/generate/dockerfile
         → preview content (not written to disk)

Phase 2: POST /docker/generate/write
         { file: { path: "Dockerfile", content: "..." } }
         → actually writes to disk
```

This lets the frontend show a preview with diff highlighting
before committing the file. The Docker wizard uses this pattern
extensively.

### 3. SSE Streaming for Long Operations

Docker build/up can take minutes. Instead of a timeout risk, the
stream endpoint uses Server-Sent Events:

```python
def sse():
    for event in docker_ops.docker_action_stream(root, action, service=service):
        yield f"data: {json.dumps(event)}\n\n"

return Response(sse(), mimetype="text/event-stream")
```

The frontend receives real-time line-by-line output and shows it
in a terminal-style UI. The `build-nc` action variant maps to
`build --no-cache` for full rebuilds.

**Allowed stream actions (whitelist):**

```python
_ALLOWED_STREAM_ACTIONS = frozenset({
    "up", "down", "restart", "build", "build-nc", "prune"
})
```

### 4. Containers Default to Show All

```python
all_ = request.args.get("all", "true").lower() in ("true", "1", "yes")
```

By default, the containers endpoint shows **all** containers, including
stopped ones. This matches the dashboard's need to show the complete
state. Users can pass `?all=false` for only running containers.

### 5. Wizard-Based Compose Generation

The compose-wizard endpoint accepts detailed service definitions
with all Docker Compose features:

```python
# Each service definition supports:
# name, image, build_context, dockerfile, ports, volumes,
# environment, depends_on, restart, command, networks
```

This is distinct from the auto-detect `generate/compose` endpoint,
which scans the project and generates a compose file automatically.
The wizard endpoint gives full manual control.

---

## Design Decisions

### Why 6 files instead of a monolith

428 lines split into 5 concern-based modules (plus __init__). Each
file is independently readable and maps to a clear responsibility:
detect, observe, act, generate, stream. A 428-line monolith would
mix GET status checks with POST destructive actions.

### Why actions import docker_ops eagerly but detect imports cache lazily

Action endpoints always need `docker_ops` — you can't build/up/down
without it. The cache import in detect is lazy because the detection
endpoint is the only one that needs caching, and importing the full
cache subsystem for a blueprint definition is wasteful.

### Why stream uses POST not GET

SSE typically uses GET, but Docker stream actions can modify state
(build, up, down, prune). GET requests should be safe (no side
effects per HTTP spec). POST preserves the semantic correctness
while still using SSE for the response format.

### Why separate endpoints for each action instead of a dispatcher

`/docker/build`, `/docker/up`, `/docker/down` etc. are separate routes
instead of `POST /docker/action { action: "build" }` because:
1. Each has different required fields (service vs container vs image)
2. Each has different `@run_tracked` categories
3. URL-based routing is more RESTful and auditable

### Why write is separate from generate

Generated content should be reviewable before writing. The two-phase
approach prevents accidental overwrites and enables "preview → confirm"
UI flows. It also allows the frontend to show diffs against existing
files.

### Why the allowed stream actions are a frozen set

Using `frozenset` instead of a list for the whitelist ensures O(1)
membership checks and signals immutability. Adding a stream action
requires deliberately modifying the frozenset, which is safer than
accidentally appending to a list.

---

## Coverage Summary

| Capability | Endpoint | File | Tracked |
|-----------|----------|------|---------|
| Status detection | GET `/docker/status` | `detect.py` | No (cached) |
| List containers | GET `/docker/containers` | `observe.py` | No |
| List images | GET `/docker/images` | `observe.py` | No |
| Compose status | GET `/docker/compose/status` | `observe.py` | No |
| Service logs | GET `/docker/logs` | `observe.py` | No |
| Container stats | GET `/docker/stats` | `observe.py` | No |
| List networks | GET `/docker/networks` | `observe.py` | No |
| List volumes | GET `/docker/volumes` | `observe.py` | No |
| Inspect container | GET `/docker/inspect` | `observe.py` | No |
| Build images | POST `/docker/build` | `actions.py` | ✅ build |
| Start services | POST `/docker/up` | `actions.py` | ✅ deploy |
| Stop services | POST `/docker/down` | `actions.py` | ✅ destroy |
| Restart services | POST `/docker/restart` | `actions.py` | ✅ deploy |
| Prune resources | POST `/docker/prune` | `actions.py` | ✅ destroy |
| Pull image | POST `/docker/pull` | `actions.py` | ✅ install |
| Execute command | POST `/docker/exec` | `actions.py` | ✅ test |
| Remove container | POST `/docker/rm` | `actions.py` | ✅ destroy |
| Remove image | POST `/docker/rmi` | `actions.py` | ✅ destroy |
| Generate Dockerfile | POST `/docker/generate/dockerfile` | `generate.py` | ✅ generate |
| Generate .dockerignore | POST `/docker/generate/dockerignore` | `generate.py` | ✅ generate |
| Generate compose | POST `/docker/generate/compose` | `generate.py` | ✅ generate |
| Generate compose (wizard) | POST `/docker/generate/compose-wizard` | `generate.py` | ✅ generate |
| Write file | POST `/docker/generate/write` | `generate.py` | ✅ generate |
| SSE streaming | POST `/docker/stream/<action>` | `stream.py` | No |
