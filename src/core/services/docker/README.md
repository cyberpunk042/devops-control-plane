# Docker Domain

> **6 files · 2,038 lines · Container lifecycle management for the devops control plane.**
>
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

#### Streaming Architecture

```
Route (SSE endpoint)
    │
    ▼
docker_action_stream(root, "up", service="web")
    │
    ├── 1. Lookup _STREAMABLE_ACTIONS["up"]
    │      → cmd: "compose", args: ["up", "-d"]
    │
    ├── 2. yield {"type": "start", "action": "up", "label": "▶ Starting..."}
    │
    ├── 3. run_compose_stream("up", "-d", "web", cwd=root)
    │      │
    │      └── _popen_stream(["docker", "compose", "up", "-d", "web"])
    │            │
    │            ├── Popen with stdout+stderr PIPE
    │            ├── selectors.DefaultSelector (concurrent read)
    │            ├── yield ("stdout", line) / ("stderr", line)
    │            └── yield ("exit", returncode)
    │
    ├── 4. For each (source, line): yield {"type": "log", "line": ..., "source": ...}
    │
    └── 5. Final event:
           exit_code == 0 → yield {"type": "done", "ok": True, "duration_ms": ...}
           exit_code != 0 → yield {"type": "error", "message": ..., "duration_ms": ...}
```

#### Streamable Actions Registry

| Action | Command | Args | Label | Audit Icon |
|--------|---------|------|-------|-----------|
| `up` | compose | `up -d` | ▶ Starting services… | ▶️ |
| `down` | compose | `down` | ⏹ Stopping services… | ⏹ |
| `restart` | compose | `restart` | 🔄 Restarting services… | 🔄 |
| `build` | compose | `build` | 🔨 Building images… | 🔨 |
| `build-nc` | compose | `build --no-cache` | 🔨 Building images (no-cache)… | 🔨 |
| `prune` | docker | `system prune -f` | 🧹 Pruning unused resources… | 🧹 |

Adding a new streamable action = add one dict entry to `_STREAMABLE_ACTIONS`.

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

## Key Data Shapes

### docker_status response

```python
{
    "available": True,               # Docker CLI detected
    "version": "24.0.7",
    "compose_available": True,       # docker compose subcommand works
    "compose_version": "2.23.0",
    "daemon_running": True,          # Docker daemon is responsive
    "compose_file": "docker-compose.yml",  # or None
    "compose_services": ["web", "db", "redis"],
    "compose_service_details": [...],  # 42-field dicts per service
    "services_count": 3,
    "dockerfiles": ["Dockerfile", "services/api/Dockerfile"],
    "dockerfile_details": [          # parsed Dockerfile info
        {
            "path": "Dockerfile",
            "base_images": ["python:3.12-slim"],
            "stages": ["builder", "runtime"],
            "stage_count": 2,
            "ports": [8000],
            "warnings": [],
        },
    ],
    "has_dockerignore": True,
    "dockerignore_patterns": [".git", "node_modules", "__pycache__"],
    "compose_warnings": [],
}
```

### docker_containers response

```python
{
    "available": True,
    "containers": [
        {
            "id": "abc123def456",
            "name": "myproject-web-1",
            "image": "myproject-web:latest",
            "status": "Up 2 hours",
            "state": "running",
            "ports": "0.0.0.0:3000->3000/tcp",
            "created": "2026-02-28 14:30:00 -0500 EST",
        },
        {
            "id": "789xyz000111",
            "name": "myproject-db-1",
            "image": "postgres:16-alpine",
            "status": "Up 2 hours (healthy)",
            "state": "running",
            "ports": "0.0.0.0:5432->5432/tcp",
            "created": "2026-02-28 14:30:01 -0500 EST",
        },
    ],
}
```

### docker_images response

```python
{
    "available": True,
    "images": [
        {
            "id": "sha256:abc123",
            "repository": "myproject-web",
            "tag": "latest",
            "size": "245MB",
            "created": "2 hours ago",
        },
    ],
}
```

### docker_compose_status response

```python
{
    "available": True,
    "services": [
        {
            "name": "web",
            "state": "running",
            "status": "Up 2 hours",
            "ports": "0.0.0.0:3000->3000/tcp",
            "image": "myproject-web:latest",
        },
    ],
}
```

### docker_stats response

```python
{
    "available": True,
    "stats": [
        {
            "name": "myproject-web-1",
            "cpu": "0.23%",
            "memory": "128.5MiB / 7.77GiB",
            "memory_pct": "1.61%",
            "net_io": "1.2MB / 456kB",
            "block_io": "12.3MB / 0B",
            "pids": "12",
        },
    ],
}
```

### docker_inspect response

```python
{
    "ok": True,
    "detail": {
        "id": "abc123def456",
        "name": "myproject-web-1",
        "image": "myproject-web:latest",
        "state": {
            "Status": "running",
            "Running": True,
            "Paused": False,
            "StartedAt": "2026-02-28T19:30:00.000Z",
        },
        "created": "2026-02-28T19:30:00.000Z",
        "platform": "linux",
        "restart_policy": {"Name": "unless-stopped", "MaximumRetryCount": 0},
        "ports": {"3000/tcp": [{"HostIp": "0.0.0.0", "HostPort": "3000"}]},
        "mounts": [
            {"source": "/app/data", "destination": "/data", "mode": "rw"},
        ],
        "env": ["NODE_ENV=production", "PORT=3000"],
        "cmd": ["node", "server.js"],
        "labels": {"com.docker.compose.service": "web"},
    },
}
```

### docker_logs response

```python
# Success
{"ok": True, "service": "web", "logs": "2026-02-28 14:30:00 Server started...\n..."}

# Failure
{"error": "No compose file found"}
```

### docker_exec_cmd response

```python
{
    "ok": True,
    "container": "myproject-web-1",
    "command": "ls -la /app",
    "output": "total 24\ndrwxr-xr-x 1 node node 4096 ...",
    "stderr": "",
    "exit_code": 0,
}
```

### docker_networks response

```python
{
    "available": True,
    "networks": [
        {
            "id": "abc123def456",
            "name": "myproject_default",
            "driver": "bridge",
            "scope": "local",
        },
    ],
}
```

### docker_volumes response

```python
{
    "available": True,
    "volumes": [
        {
            "name": "myproject_db-data",
            "driver": "local",
            "mountpoint": "/var/lib/docker/volumes/myproject_db-data/_data",
            "labels": {"com.docker.compose.project": "myproject"},
        },
    ],
}
```

### docker_to_k8s_services response

```python
[
    {
        "name": "web",
        "image": "web:latest",
        "port": 3000,
        "kind": "Deployment",
        "build_args": {"NODE_ENV": "production"},  # only if compose has build.args
    },
]
```

### Streaming event sequence

```python
# Event 1: Start
{"type": "start", "action": "up", "label": "▶ Starting services…"}

# Events 2-N: Log lines
{"type": "log", "line": "Creating network myproject_default", "source": "stderr"}
{"type": "log", "line": "Creating container myproject-web-1", "source": "stderr"}

# Final event: Done (success)
{"type": "done", "ok": True, "duration_ms": 3456, "message": "Docker Up completed."}

# Final event: Error (failure)
{"type": "error", "message": "Docker Build failed (exit code 1)", "duration_ms": 12345}
```

### Streaming error events (validation)

```python
# Unknown action
{"type": "error", "message": "Unknown action: <action>"}

# No compose file (for compose actions)
{"type": "error", "message": "No compose file found"}
```

---

## Architecture

```
                  CLI (ui/cli/docker.py)
                  Routes (routes/docker/)
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
├── common.py        Subprocess runners — sync + streaming variants (140 lines)
├── detect.py        Docker/Compose environment detection + Dockerfile/compose parsing (585 lines)
├── containers.py    Container/image/network/volume CRUD + streaming action dispatch (734 lines)
├── generate.py      Dockerfile, .dockerignore, compose generation + write_generated_file (375 lines)
├── k8s_bridge.py    Docker → K8s service translation — pure data, no I/O (134 lines)
└── README.md        This file
```

---

## Per-File Documentation

### `common.py` — Subprocess Runners (140 lines)

| Function | What It Does |
|----------|-------------|
| `run_docker(*args)` | `subprocess.run(["docker", *args])` with timeout, capture |
| `run_compose(*args)` | `subprocess.run(["docker", "compose", *args])` with timeout |
| `run_docker_stream(*args)` | `Popen` generator — yields `(source, line)` tuples |
| `run_compose_stream(*args)` | Same for compose commands |
| `_popen_stream(cmd)` | Internal: Popen + selectors for concurrent stdout/stderr reading |

The streaming runners use `selectors.DefaultSelector` to read stdout
and stderr concurrently without deadlocks. Docker compose sends
progress to stderr, so both streams must be read simultaneously.
The `StreamLine` type is `tuple[Literal["stdout", "stderr", "exit"], str | int]`.

**Timeout defaults:**

| Runner | Default Timeout | Rationale |
|--------|----------------|-----------|
| `run_docker` | 60s | Standard docker commands |
| `run_compose` | 120s | Compose may start multiple services |
| `run_docker_stream` | 300s | Streaming docker commands with ceiling |
| `run_compose_stream` | 600s | Streaming compose with longer ceiling |
| `_popen_stream` | 600s | Internal — per-line read timeout for selector |

### `detect.py` — Environment Probing (585 lines)

| Function | What It Does |
|----------|-------------|
| `docker_status(project_root)` | **Main entry** — full Docker/Compose environment report |
| `find_compose_file(project_root)` | Find first compose file (4 naming conventions) |
| `_parse_dockerfile(path, rel_path)` | Extract base images, stages, ports, warnings |
| `_parse_compose_services(path)` | Service names from compose YAML |
| `_parse_compose_service_details(path)` | Full 42-field service specs |
| `_env_list_to_dict(items)` | `["KEY=VAL", ...]` → `{"KEY": "VAL", ...}` |
| `_normalise_ports(raw)` | Normalize all port formats → `[{host, container, protocol}]` |
| `_long_volume_to_str(vol)` | Dict volume → short string format |

**Compose file detection order:**
1. `docker-compose.yml`
2. `docker-compose.yaml`
3. `compose.yml`
4. `compose.yaml`

**Compose service detail — 42 normalised fields per service:**

| Group | Fields | Count |
|-------|--------|-------|
| **Original 14** | `name`, `image`, `build`, `ports`, `environment`, `volumes`, `depends_on`, `command`, `entrypoint`, `restart`, `healthcheck`, `deploy`, `networks`, `labels` | 14 |
| **Identity** | `container_name`, `hostname`, `domainname`, `platform`, `profiles` | 5 |
| **Runtime** | `user`, `working_dir`, `stdin_open`, `tty`, `privileged`, `init`, `read_only`, `pid`, `shm_size` | 9 |
| **Networking** | `network_mode`, `dns`, `dns_search`, `extra_hosts`, `expose` | 5 |
| **Files** | `env_file`, `configs`, `secrets`, `tmpfs`, `devices` | 5 |
| **Logging** | `logging` → `{driver, options}` | 1 |
| **Lifecycle** | `stop_signal`, `stop_grace_period`, `pull_policy` | 3 |
| | | **42** |

**Sub-field shapes:**
- `build` → `{context, dockerfile, args}` or `null`
- `healthcheck` → `{test, interval, timeout, retries}` or `null`
- `deploy` → `{replicas, cpu_limit, memory_limit, cpu_request, memory_request}` or `null`

**Port normalisation:**

All Docker port formats are normalized to a consistent shape:

```python
# Input formats handled:
"3000"                    # short
"3000:3000"               # host:container
"8080:3000/tcp"           # with protocol
{"target": 3000, "published": 8080, "protocol": "tcp"}  # long

# Normalized output (integers, not strings):
{"host": 8080, "container": 3000, "protocol": "tcp"}
```

### `containers.py` — Operations (734 lines)

Contains 9 observe functions and 9 act functions, plus the streaming
action dispatch system. All act functions are audited via `make_auditor("docker")`.

Two sections: **Observe** (read-only queries) and **Act** (mutations).

**Observe functions:**

| Function | Return Shape |
|----------|-------------|
| `docker_containers(root, all_)` | `{available, containers: [{id, name, image, status, state, ports, created}]}` |
| `docker_images(root)` | `{available, images: [{id, repository, tag, size, created}]}` |
| `docker_compose_status(root)` | `{available, services: [{name, state, status, ports, image}]}` |
| `docker_logs(root, service, tail)` | `{ok, service, logs}` or `{error}` |
| `docker_stats(root)` | `{available, stats: [{name, cpu, memory, memory_pct, net_io, block_io, pids}]}` |
| `docker_networks(root)` | `{available, networks: [{id, name, driver, scope}]}` |
| `docker_volumes(root)` | `{available, volumes: [{name, driver, mountpoint, labels}]}` |
| `docker_inspect(root, container_id)` | `{ok, detail: {id, name, image, state, ports, mounts, env, cmd, labels, ...}}` |

**Act functions:**

| Function | What It Does | Return Shape | Audited |
|----------|-------------|-------------|---------|
| `docker_build(root, service, no_cache)` | Build images via compose | `{ok, service, output}` | ✅ |
| `docker_up(root, service, detach)` | Start compose services | `{ok, service, output}` | ✅ |
| `docker_down(root, volumes)` | Stop + remove compose services | `{ok, output}` | ✅ |
| `docker_restart(root, service)` | Restart compose services | `{ok, service, output}` | ✅ |
| `docker_prune(root)` | System prune (containers, images, networks, cache) | `{ok, output}` | ✅ |
| `docker_pull(root, image)` | Pull a Docker image | `{ok, image, output}` | ✅ |
| `docker_exec_cmd(root, container_id, command)` | Execute in running container | `{ok, container, command, output, stderr, exit_code}` | ✅ |
| `docker_rm(root, container_id, force)` | Remove a container | `{ok, container}` | ✅ |
| `docker_rmi(root, image, force)` | Remove an image | `{ok, image, output}` | ✅ |

**Compose JSON parsing:**

`docker compose ps --format json` may output either a JSON array
or line-delimited JSON objects depending on Docker version. The
parser handles both:

```python
try:
    parsed = json.loads(output)     # Try array first
    raw_list = parsed if isinstance(parsed, list) else [parsed]
except json.JSONDecodeError:
    raw_list = [json.loads(line) for line in output.splitlines()]  # Fallback
```

### `generate.py` — Config Generation (375 lines)

| Function | What It Does |
|----------|-------------|
| `generate_dockerfile(root, stack, base_image)` | Dockerfile from stack template |
| `generate_dockerignore(root, stacks)` | .dockerignore from stack patterns |
| `generate_compose(root, modules, project_name)` | Compose from project module detection |
| `generate_compose_from_wizard(root, services, project_name)` | Compose from wizard service specs (with diff) |
| `write_generated_file(root, file_data)` | Write any generated file to disk (with audit + security) |

**`write_generated_file()` security checks:**
1. Path traversal protection — rejects `../` escapes
2. Overwrite guard — only writes if `file_data["overwrite"]` is True
3. Before/after diff — records old content for audit trail

### `k8s_bridge.py` — Cross-Domain Translation (134 lines)

| Function | What It Does |
|----------|-------------|
| `docker_to_k8s_services(docker_status)` | Translate Docker detection → K8s wizard service definitions |
| `_from_compose(compose_details)` | Build K8s service defs from compose details |
| `_from_dockerfiles(dockerfile_details)` | Build K8s service defs from Dockerfile parsing |

**Translation priority:**
1. Compose service details (richer data: ports, build args, names)
2. Dockerfile analysis (fallback: EXPOSE ports only)

These sources are mutually exclusive (`if/elif`): if compose details
exist, Dockerfiles are NOT consulted. Compose takes full priority.

---

## Audit Trail

All mutating operations are logged via `make_auditor("docker")`:

| Event | Icon | Title | Target |
|-------|------|-------|--------|
| Service started | ▶️ | Docker Up | service name |
| Service stopped | ⏹️ | Docker Down | `"all"` |
| Service restarted | 🔄 | Docker Restart | service name |
| Image built | 📦 | Docker Build | service name |
| System pruned | 🧹 | Docker Prune | `"system"` |
| Image pulled | ⬇️ | Docker Pull | image name |
| Command executed | ▶️ | Docker Exec | container ID |
| Container removed | 🗑️ | Container Removed | container ID |
| Image removed | 🗑️ | Image Removed | image name |
| File written | 💾 | Docker File Written | file path |

Streaming actions also audit: the `docker_action_stream()` function
records the audit entry after the action completes (on success only).

---

## Dependency Graph

```
common.py  ← standalone (subprocess only)
   ▲
   │
   ├── detect.py     (imports run_docker, run_compose)
   │
   └── containers.py (imports run_docker, run_compose,
                       run_docker_stream, run_compose_stream,
                       find_compose_file from detect)

generate.py      ← self-contained
   │
   ├── generators/dockerfile.py
   ├── generators/dockerignore.py
   ├── generators/compose.py
   ├── audit_helpers
   └── models/template (GeneratedFile)

k8s_bridge.py    ← self-contained (pure data, zero imports from docker)
```

**External dependencies:**

| Module | Uses |
|--------|------|
| `common.py` | `subprocess`, `selectors`, `pathlib` |
| `detect.py` | `yaml`, `re`, `pathlib`, `common.*` |
| `containers.py` | `json`, `time`, `pathlib`, `common.*`, `detect.find_compose_file` |
| `generate.py` | `yaml`, `pathlib`, `generators.*`, `audit_helpers`, `models/template` |
| `k8s_bridge.py` | `pathlib` only |

---

## Error Handling Patterns

All functions return structured dicts. Two patterns:

```python
# Pattern 1: "available" flag (observe functions)
{"available": False, "error": "Docker not available"}
{"available": True,  "containers": [...]}

# Pattern 2: "ok" or "error" (act functions)
{"error": "No compose file found"}
{"ok": True, "output": "..."}
```

Streaming errors yield error events without crashing the generator:
```python
{"type": "error", "message": "Unknown action: foo"}
{"type": "error", "message": "No compose file found"}
{"type": "error", "message": "Docker Build failed (exit code 1)", "duration_ms": 12345}
```

**Input validation:**

Act functions validate parameters before executing:

```python
if not container_id:
    return {"error": "Missing container ID"}
if not image:
    return {"error": "Missing image name"}
if not command:
    return {"error": "Missing command"}
```

---

## Backward Compatibility

| Old path | Re-exports from |
|----------|----------------|
| `services/docker_ops.py` | `docker/` — all public functions |

```python
# ✅ New (package-level)
from src.core.services.docker import docker_status, docker_containers

# ⚠️ Legacy shim — still works, avoid in new code
from src.core.services.docker_ops import docker_status
```

---

## Consumers

| Layer | Module | What It Uses |
|-------|--------|-------------|
| **CLI** | `ui/cli/docker.py` | All container ops, generation, `write_generated_file` |
| **CLI** | `ui/cli/security.py`, `ci.py`, `k8s.py`, etc. | `write_generated_file` (shared writer) |
| **Routes** | `routes/docker/` | `docker_ops.*` — all detection + operations + generation |
| **Services** | `k8s_validate.py` | `docker_status` (for cross-domain validation L6) |
| **Services** | `wizard/helpers.py` | `docker_status` (for wizard environment detection) |
| **Services** | `metrics/ops.py` | `docker_status` (for metrics collection) |

---

## API Endpoints

| Route | Method | Purpose | Observe/Act |
|-------|--------|---------|-------------|
| `/api/docker/status` | GET | Full docker_status() + compose detection | Observe |
| `/api/docker/containers` | GET | Container list (all or running) | Observe |
| `/api/docker/images` | GET | Local image list | Observe |
| `/api/docker/compose/status` | GET | Compose service states | Observe |
| `/api/docker/logs/<service>` | GET | Service log tail | Observe |
| `/api/docker/stats` | GET | Container resource usage | Observe |
| `/api/docker/networks` | GET | Docker networks | Observe |
| `/api/docker/volumes` | GET | Docker volumes | Observe |
| `/api/docker/inspect/<id>` | POST | Container inspect | Observe |
| `/api/docker/action` | POST | Streaming action (up/down/restart/build/prune) via SSE | Act |
| `/api/docker/build` | POST | Build images | Act |
| `/api/docker/pull` | POST | Pull an image | Act |
| `/api/docker/exec` | POST | Execute command in container | Act |
| `/api/docker/rm` | POST | Remove container | Act |
| `/api/docker/rmi` | POST | Remove image | Act |
| `/api/docker/prune` | POST | System prune | Act |
| `/api/docker/generate/dockerfile` | POST | Generate Dockerfile | Generate |
| `/api/docker/generate/dockerignore` | POST | Generate .dockerignore | Generate |
| `/api/docker/generate/compose` | POST | Generate docker-compose.yml | Generate |
| `/api/docker/write` | POST | Write generated file to disk | Generate |

---

## Advanced Feature Showcase

### 1. Concurrent Stdout/Stderr Streaming via Selectors (`common.py` lines 67-121)

Docker Compose sends progress to stderr while stdout carries data output.
Reading one at a time causes deadlocks — if stderr's buffer fills while
we're blocking on stdout, the process hangs. The solution uses Python's
`selectors` module to read whichever stream has data first:

```python
# common.py — _popen_stream (the most complex function in the domain)
def _popen_stream(cmd, *, cwd, timeout=600):
    proc = subprocess.Popen(
        cmd, cwd=str(cwd),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1,       # line-buffered
    )

    sel = selectors.DefaultSelector()
    try:
        if proc.stdout:
            sel.register(proc.stdout, selectors.EVENT_READ, "stdout")
        if proc.stderr:
            sel.register(proc.stderr, selectors.EVENT_READ, "stderr")

        open_streams = 2
        while open_streams > 0:
            events = sel.select(timeout=timeout)
            if not events:
                proc.kill()          # timeout — kill the process
                proc.wait()
                yield ("stderr", f"⏰ Timed out after {timeout}s — process killed")
                yield ("exit", -1)
                return

            for key, _ in events:
                source = key.data     # "stdout" or "stderr"
                line = key.fileobj.readline()
                if not line:          # EOF on this stream
                    sel.unregister(key.fileobj)
                    open_streams -= 1
                    continue
                yield (source, line.rstrip("\n"))
    finally:
        sel.close()

    proc.wait()
    yield ("exit", proc.returncode)
```

**Why this matters:** Every SSE endpoint that streams Docker output depends
on this function. Without concurrent reading, a `docker compose build` with
verbose output would silently hang. The `timeout` on `sel.select()` acts
as a per-line watchdog — if the process stops producing output for 600s,
it gets killed rather than leaving an orphan.

### 2. 42-Field Compose Normalisation with Format Coercion (`detect.py` lines 239-527)

The most data-intensive function in the domain. Each of the 42 fields
requires format-specific coercion because Docker Compose YAML allows
multiple input forms for the same field:

```python
# detect.py — _parse_compose_service_details
# Example: environment can be a dict OR a list
env_raw = svc.get("environment")
if isinstance(env_raw, dict):
    detail["environment"] = {
        str(k): str(v) if v is not None else ""
        for k, v in env_raw.items()
    }
elif isinstance(env_raw, list):
    detail["environment"] = _env_list_to_dict(env_raw)  # ["KEY=VAL", ...] → dict
else:
    detail["environment"] = {}

# Example: depends_on can be a list OR a condition dict
deps = svc.get("depends_on")
if isinstance(deps, list):
    detail["depends_on"] = list(deps)
elif isinstance(deps, dict):
    detail["depends_on"] = sorted(deps.keys())  # {svc: {condition: ...}} → names
else:
    detail["depends_on"] = []

# Example: ports supports 4 formats → normalised to [{host, container, protocol}]
# Short: "3000", Pair: "8080:3000", Protocol: "8080:3000/udp",
# Bind: "127.0.0.1:8080:3000", Long: {target: 3000, published: 8080}
detail["ports"] = _normalise_ports(svc.get("ports"))
```

**Why this matters:** Every downstream consumer (wizard, K8s bridge,
dashboard card) receives a **uniform shape** regardless of how the
user wrote their compose file. The wizard can do `svc["ports"][0]["container"]`
without checking whether the original YAML said `"3000"`, `"8080:3000"`,
or `{target: 3000, published: 8080}`.

### 3. Wizard Compose Generation with Diff Tracking (`generate.py` lines 109-294)

The longest function in the domain. When generating a compose file from
wizard input, it doesn't just write — it computes a unified diff against
the existing file on disk and includes it in the audit trail:

```python
# generate.py — generate_compose_from_wizard
# 1. Build the compose dict from user service specs
compose = {"services": {}}
for svc in services:
    spec = {}
    # ... 80 lines of field extraction: image/build, ports, volumes,
    #     environment, depends_on, restart, command, networks,
    #     container_name, healthcheck, build_args, platform

    compose["services"][name] = spec

# 2. If file exists, compute diff
existing = root / "docker-compose.yml"
if existing.is_file():
    old_content = existing.read_text(encoding="utf-8", errors="ignore")
    diff_lines = list(difflib.unified_diff(
        old_content.splitlines(), content.splitlines(),
        fromfile="a/docker-compose.yml",
        tofile="b/docker-compose.yml",
        lineterm="",
    ))
    added = sum(1 for l in diff_lines if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in diff_lines if l.startswith("-") and not l.startswith("---"))

# 3. Audit with full diff detail
_audit(
    "📝 Compose Wizard Generated",
    f"Generated docker-compose.yml ({len(compose['services'])} service(s) via wizard)"
    + (f" — +{added} -{removed} lines" if "diff" in diff_detail else ""),
    action="generated",
    target="docker-compose.yml",
    detail=diff_detail,        # includes truncated diff (50 lines max)
    before_state={"lines": len(old_lines), "size": len(old_content.encode())},
    after_state={"lines": len(content.splitlines()), "services": list(...)},
)
```

**Why this matters:** The audit trail doesn't just say "compose file generated" —
it records exactly what changed, how many lines were added/removed, and the
before/after file sizes. This enables undo reasoning and change review
without leaving the admin panel.

### 4. Streaming Action Dispatch — Data-Driven Pattern (`containers.py` lines 35-161)

All 6 streaming actions (up, down, restart, build, build-nc, prune) go
through a single code path. Each action is a pure data declaration:

```python
# containers.py — _STREAMABLE_ACTIONS registry
_STREAMABLE_ACTIONS = {
    "up":       {"cmd": "compose", "args": ["up", "-d"],
                 "label": "▶ Starting services…",
                 "audit_icon": "▶️", "audit_title": "Docker Up", "audit_verb": "started"},
    "down":     {"cmd": "compose", "args": ["down"],
                 "label": "⏹ Stopping services…",
                 "audit_icon": "⏹️", "audit_title": "Docker Down", "audit_verb": "stopped"},
    "build-nc": {"cmd": "compose", "args": ["build", "--no-cache"],
                 "label": "🔨 Building images (no-cache)…",
                 "audit_icon": "📦", "audit_title": "Docker Build (no-cache)", "audit_verb": "built"},
    "prune":    {"cmd": "docker", "args": ["system", "prune", "-f"],
                 "label": "🧹 Pruning unused resources…",
                 "audit_icon": "🧹", "audit_title": "Docker Prune", "audit_verb": "pruned"},
    # ... + restart, build
}

# The dispatch function — 56 lines handling ALL actions:
def docker_action_stream(project_root, action, *, service=None):
    cfg = _STREAMABLE_ACTIONS.get(action)
    if not cfg:
        yield {"type": "error", "message": f"Unknown action: {action}"}
        return

    # Compose actions need a compose file (prune is plain docker)
    if cfg["cmd"] == "compose":
        compose_file = find_compose_file(project_root)
        if not compose_file:
            yield {"type": "error", "message": "No compose file found"}
            return

    yield {"type": "start", "action": action, "label": cfg["label"]}

    # Same runner selection for all actions
    args = list(cfg["args"])
    if service and cfg["cmd"] == "compose":
        args.append(service)

    stream = (run_compose_stream if cfg["cmd"] == "compose"
              else run_docker_stream)(*args, cwd=project_root)

    for source, line in stream:
        if source == "exit":
            exit_code = int(line)
        else:
            yield {"type": "log", "line": str(line), "source": source}

    # Success → audit; failure → error event
    if exit_code == 0:
        _audit(f"{cfg['audit_icon']} {cfg['audit_title']}", ...)
        yield {"type": "done", "ok": True, "duration_ms": ...}
    else:
        yield {"type": "error", "message": f"... failed (exit code {exit_code})"}
```

**Why this matters:** Adding a 7th streaming action (e.g., `pull`) requires
exactly one dict entry — no new function, no new route handler, no new
SSE plumbing. The dispatch, audit, error handling, and event protocol
are all shared. This is the extensibility pattern for Docker operations.

### 5. Multi-Stage Dockerfile Parsing (`detect.py` lines 157-223)

The parser extracts structural information from Dockerfiles using line-by-line
analysis. It handles multi-stage builds, EXPOSE ports with protocol suffixes,
and produces validation warnings:

```python
# detect.py — _parse_dockerfile
def _parse_dockerfile(path, rel_path):
    result = {"path": rel_path, "base_images": [], "stages": [],
              "stage_count": 0, "ports": [], "warnings": []}

    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        has_content = True
        upper = stripped.upper()

        if upper.startswith("FROM "):
            parts = stripped.split()
            image = parts[1]                   # e.g. "python:3.12-slim"
            result["base_images"].append(image)
            result["stage_count"] += 1
            if len(parts) >= 4 and parts[2].upper() == "AS":
                result["stages"].append(parts[3])  # stage name

        elif upper.startswith("EXPOSE "):
            for token in stripped.split()[1:]:
                port_str = token.split("/")[0]  # strip "/tcp", "/udp"
                try:
                    result["ports"].append(int(port_str))
                except ValueError:
                    pass  # skip $PORT variables

    # Validation
    if not has_content:
        result["warnings"].append("Dockerfile is empty")
    elif result["stage_count"] == 0:
        result["warnings"].append("No FROM instruction found")
```

**Why this matters:** This feeds two consumers — the dashboard card
(shows base images and stage count) and the K8s bridge (needs ports
from EXPOSE for service definitions). The parser handles real-world
edge cases: variable ports (`$PORT`), protocol suffixes (`8080/tcp`),
empty Dockerfiles, and missing FROM instructions.

### 6. Write-Protected File Writer with Audit Diffs (`generate.py` lines 297-375)

The shared writer (`write_generated_file`) implements three safety layers
before touching disk, then records a detailed audit trail:

```python
# generate.py — write_generated_file
def write_generated_file(project_root, file_data):
    rel_path = file_data.get("path", "")
    content = file_data.get("content", "")
    overwrite = file_data.get("overwrite", False)

    # Safety 1: path traversal protection
    target = (project_root / rel_path).resolve()
    if not target.is_relative_to(project_root.resolve()):
        return {"error": f"Path traversal outside project root: {rel_path}"}

    # Safety 2: overwrite guard
    if target.exists() and not overwrite:
        return {"error": f"File already exists: {rel_path} (use overwrite=true)"}

    # Capture old content for diff
    was_override = target.exists()
    old_content = target.read_text(...) if was_override else ""

    # Write
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")

    # Audit with before/after diff
    if was_override and old_content:
        diff_lines = list(difflib.unified_diff(...))
        added = sum(1 for l in diff_lines if l.startswith("+") and not l.startswith("+++"))
        removed = sum(1 for l in diff_lines if l.startswith("-") and not l.startswith("---"))

    _audit(
        "💾 Docker File Written",
        f"{rel_path}" + (f" (overwritten, +{added} -{removed} lines)" if was_override else " (new)"),
        before_state={"lines": old_lines, "size": len(old_content.encode())} if was_override else None,
        after_state={"lines": new_lines, "size": target.stat().st_size},
    )
```

**Why this matters:** Every generated file (Dockerfile, .dockerignore,
docker-compose.yml) goes through this single writer. The path traversal
check prevents `{"path": "../../../etc/passwd"}` attacks. The overwrite
guard prevents accidental data loss. The diff tracking means the audit
log shows exactly what changed — not just "file written" but "+12 -3 lines"
with the actual unified diff stored in the audit detail.

### Feature Coverage Summary

| Feature | Where | Lines | Complexity |
|---------|-------|-------|------------|
| Concurrent stdout/stderr via selectors | `common.py` | 67-121 | High — deadlock prevention |
| 42-field compose normalisation | `detect.py` | 239-527 | High — 7+ format coercions per field |
| Wizard compose with diff tracking | `generate.py` | 109-294 | High — YAML gen + difflib + audit |
| Streaming action dispatch registry | `containers.py` | 35-161 | Medium — data-driven extensibility |
| Multi-stage Dockerfile parsing | `detect.py` | 157-223 | Medium — multi-format edge cases |
| Write-protected file writer | `generate.py` | 297-375 | Medium — 3 safety layers + diff audit |
| Docker → K8s translation bridge | `k8s_bridge.py` | 18-134 | Medium — compose/dockerfile priority |
| Dual JSON parsing for compose ps | `containers.py` | 256-276 | Low — version compatibility |
| Port normalisation (4 formats) | `detect.py` | 543-573 | Low — format coercion |
| Compose file detection (4 names) | `detect.py` | 17-30 | Low — ordered search |

---

## Design Decisions

### Why separate common.py instead of inline subprocess calls?

Every Docker module needs to call `docker` or `docker compose`. Without
shared runners, each module would have its own `subprocess.run()` call
with slightly different timeout, capture, and cwd handling. `common.py`
ensures consistent behavior: same timeout defaults, same text mode,
same `cwd` wiring. Streaming runners add complexity (Popen + selectors)
that should not be duplicated.

### Why a streaming action registry instead of per-action functions?

The streaming dispatch (`_STREAMABLE_ACTIONS`) means `docker_action_stream`
handles all 6 actions via a single code path. Each action entry is a data
declaration — no logic, just args and labels. Adding a new streamable
action is one dict entry, not a new 30-line function. The trade-off:
non-streaming actions (`docker_build`, `docker_up`, etc.) still exist as
separate functions for direct CLI/service use — they return dicts instead
of yielding events.

### Why does detect.py parse Dockerfiles manually?

The `_parse_dockerfile()` function uses regex to extract `FROM`, `EXPOSE`,
and `AS` lines. A proper Dockerfile parser would be more robust, but
detection only needs base images, stages, and ports — three simple patterns.
Adding a dependency for just this would violate the minimal dependency
principle.

### Why 42 fields in compose service details?

The wizard and K8s bridge need comprehensive service information to
generate accurate manifests. Partial parsing would lose configuration
that matters: health checks affect readiness probes, resource limits
map to K8s resource requests, `depends_on` informs job ordering.
The 42 fields cover everything in the Docker Compose specification
except security options (cap_add, cap_drop, security_opt) and kernel
tunables (ulimits, sysctls), which are excluded as out-of-scope for
the control plane.

### Why does k8s_bridge.py live in the docker package?

The bridge reads `docker_status()` output and produces K8s input.
It could live in `k8s/`, but it's a consumer of Docker data, not
K8s data. It transforms FROM Docker TO K8s — so it belongs next to
the data it reads, not the data it produces. The K8s package imports
the result but doesn't need to know how it was derived.

### Why do blocking and streaming versions of the same action coexist?

`docker_up()` (blocking) and `docker_action_stream(root, "up")` (streaming)
both start compose services. Blocking is used by CLI and non-interactive
contexts. Streaming is used by the web admin panel's SSE endpoint.
Different consumers, different transport needs. The blocking functions
also have finer-grained parameter control (e.g., `docker_build(no_cache=True)`)
that the streaming registry simplifies.

### Why dual JSON parsing for compose ps?

Different Docker Compose versions output `docker compose ps --format json`
differently — some produce a JSON array, others produce line-delimited
JSON objects (one per line). Rather than requiring a minimum version,
the parser tries JSON array first and falls back to line-delimited.
This works transparently across Docker Compose v2.x versions.
