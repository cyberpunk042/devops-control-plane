# Tool Install v2 — Phase 8: System Configuration & Restart Management

## Context

Phases 2-7 install software, drivers, and data. Phase 8 manages
the system-level consequences: service lifecycle, config file
writes, restart requirements, and parallel step execution. This
is the final phase — the system becomes a full provisioning engine.

### Dependencies

```
Phase 2.4 (execution)    ── provides: execute_plan(), _run_subprocess()
Phase 4 (choices)        ── provides: choice UI (service options)
Phase 6 (hardware)       ── provides: kernel detection (for module reload)
Phase 8 (THIS)           ── provides: service management, config writes, restart tracking, DAG execution
```

### Domains consumed

| Domain | What Phase 8 uses |
|--------|------------------|
| domain-services | systemd/init management, enable/disable, status |
| domain-config-files | Config file writes, ownership, permissions, backups |
| domain-restart | Restart detection, batching, shell/service/reboot |
| domain-parallel-execution | DAG engine, depends_on, concurrent steps |

---

## Service Management

### Service step types

```python
# type: service_start
{
    "type": "service",
    "action": "start",          # start | stop | restart | enable | disable | status
    "service": "docker",
    "needs_sudo": True,
    "condition": {"has_systemd": True},
}
```

### Service executor

```python
def _execute_service_step(step, *, sudo_password=""):
    """Manage a system service."""
    action = step["action"]
    service = step["service"]
    init_system = _detect_init_system()

    if init_system == "systemd":
        return _systemd_action(action, service, sudo_password)
    elif init_system == "openrc":
        return _openrc_action(action, service, sudo_password)
    elif init_system == "initd":
        return _initd_action(action, service, sudo_password)
    else:
        return {"ok": False, "error": f"No init system detected for service management"}


def _systemd_action(action, service, sudo_password):
    """Execute a systemd service action."""
    CMD_MAP = {
        "start":   ["systemctl", "start", service],
        "stop":    ["systemctl", "stop", service],
        "restart": ["systemctl", "restart", service],
        "enable":  ["systemctl", "enable", service],
        "disable": ["systemctl", "disable", service],
        "status":  ["systemctl", "is-active", service],
    }

    cmd = CMD_MAP.get(action)
    if not cmd:
        return {"ok": False, "error": f"Unknown action: {action}"}

    # Status check doesn't need sudo
    needs_sudo = action != "status"

    result = _run_subprocess(
        cmd,
        needs_sudo=needs_sudo,
        sudo_password=sudo_password,
        timeout=30,
    )

    # Enrich result for status checks
    if action == "status":
        result["active"] = result.get("ok", False)
        result["ok"] = True  # status check itself succeeded

    return result


def _detect_init_system() -> str:
    """Detect the init system."""
    if Path("/run/systemd/system").exists():
        return "systemd"
    if shutil.which("rc-service"):
        return "openrc"
    if Path("/etc/init.d").exists():
        return "initd"
    return "unknown"
```

### Service status enrichment

```python
def get_service_status(service: str) -> dict:
    """Get comprehensive service status."""
    init = _detect_init_system()

    if init == "systemd":
        result = {}
        for prop in ("ActiveState", "SubState", "LoadState"):
            r = subprocess.run(
                ["systemctl", "show", service, f"--property={prop}"],
                capture_output=True, text=True, timeout=5,
            )
            key, _, val = r.stdout.strip().partition("=")
            result[key.lower()] = val

        return {
            "service": service,
            "active": result.get("activestate") == "active",
            "state": result.get("activestate", "unknown"),
            "sub_state": result.get("substate", "unknown"),
            "loaded": result.get("loadstate") == "loaded",
        }

    return {"service": service, "active": None, "state": "unknown"}
```

---

## Config File Management

### Config step type

```python
# type: config
{
    "type": "config",
    "action": "write",     # write | append | template | ensure_line
    "path": "/etc/docker/daemon.json",
    "content": '{"features": {"buildkit": true}}',
    "owner": "root:root",
    "mode": "0644",
    "needs_sudo": True,
    "backup": True,         # create backup before writing
    "risk": "medium",
}
```

### Config executor

```python
def _execute_config_step(step, *, sudo_password=""):
    """Write or modify a config file."""
    action = step["action"]
    path = Path(step["path"])
    backup = step.get("backup", True)

    # Backup existing file before any modification
    if backup and path.exists():
        backup_result = _backup_file(path, sudo_password=sudo_password)
        if not backup_result["ok"]:
            return backup_result

    if action == "write":
        return _config_write(step, sudo_password=sudo_password)
    elif action == "append":
        return _config_append(step, sudo_password=sudo_password)
    elif action == "ensure_line":
        return _config_ensure_line(step, sudo_password=sudo_password)
    elif action == "template":
        return _config_template(step, sudo_password=sudo_password)
    else:
        return {"ok": False, "error": f"Unknown config action: {action}"}


def _config_write(step, *, sudo_password=""):
    """Write content to a file (overwrite)."""
    path = step["path"]
    content = step["content"]
    owner = step.get("owner")
    mode = step.get("mode")

    # Write via tee (handles sudo)
    cmd = ["tee", path]
    result = _run_subprocess(
        cmd,
        needs_sudo=step.get("needs_sudo", False),
        sudo_password=sudo_password,
        timeout=10,
        stdin_data=content,
    )

    if not result["ok"]:
        return result

    # Set ownership
    if owner and step.get("needs_sudo"):
        _run_subprocess(
            ["chown", owner, path],
            needs_sudo=True,
            sudo_password=sudo_password,
            timeout=5,
        )

    # Set permissions
    if mode and step.get("needs_sudo"):
        _run_subprocess(
            ["chmod", mode, path],
            needs_sudo=True,
            sudo_password=sudo_password,
            timeout=5,
        )

    return {"ok": True, "message": f"Config written: {path}"}


def _config_ensure_line(step, *, sudo_password=""):
    """Ensure a line exists in a file (idempotent)."""
    path = Path(step["path"])
    line = step["line"]

    # Check if line already exists
    if path.exists():
        content = path.read_text()
        if line in content:
            return {"ok": True, "message": "Line already present", "skipped": True}

    # Append the line
    cmd = ["bash", "-c", f"echo '{line}' >> {path}"]
    return _run_subprocess(
        cmd,
        needs_sudo=step.get("needs_sudo", False),
        sudo_password=sudo_password,
        timeout=5,
    )


def _backup_file(path: Path, *, sudo_password="") -> dict:
    """Create a timestamped backup of a file."""
    import time
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    backup_path = f"{path}.bak.{timestamp}"

    return _run_subprocess(
        ["cp", "-p", str(path), backup_path],
        needs_sudo=True,
        sudo_password=sudo_password,
        timeout=5,
    )
```

---

## Restart Management

### Restart detection

```python
RESTART_TRIGGERS = {
    "shell_restart": [
        "PATH modification",
        "Shell config change (.bashrc, .zshrc)",
        "New binary in non-standard directory",
    ],
    "service_restart": [
        "Config file changed",
        "Service installation",
        "Module loaded/unloaded",
    ],
    "reboot_required": [
        "Kernel module installed (DKMS)",
        "GPU driver installed",
        "Kernel updated",
        "Secure Boot key enrolled",
    ],
}

def detect_restart_needs(plan: dict, completed_steps: list) -> dict:
    """After plan execution, detect what needs restarting."""
    needs = {
        "shell_restart": False,
        "service_restart": [],
        "reboot_required": False,
        "reasons": [],
    }

    for step in completed_steps:
        # post_env → shell restart needed
        if plan.get("post_env"):
            needs["shell_restart"] = True
            needs["reasons"].append("PATH was modified — restart shell to use new tools")

        # Service config changed → service restart
        if step.get("type") == "config":
            service = step.get("restart_service")
            if service:
                needs["service_restart"].append(service)
                needs["reasons"].append(f"Config changed — restart {service}")

        # Kernel module → reboot may be needed
        if step.get("type") == "post_install":
            cmd = step.get("command", [])
            if cmd and cmd[0] == "modprobe":
                needs["reasons"].append(f"Kernel module loaded — reboot recommended")

        # GPU driver → reboot
        if step.get("gpu_driver"):
            needs["reboot_required"] = True
            needs["reasons"].append("GPU driver installed — reboot required")

    return needs
```

### Restart batching

```python
# Multiple config changes to the same service → ONE restart
def _batch_restarts(restart_needs: dict) -> list[dict]:
    """Batch restart requirements into minimal restart steps."""
    steps = []

    # Deduplicate service restarts
    services = list(set(restart_needs.get("service_restart", [])))
    for svc in services:
        steps.append({
            "type": "service",
            "action": "restart",
            "service": svc,
            "needs_sudo": True,
            "label": f"Restart {svc}",
        })

    # Shell restart notification (not a step — just a message)
    if restart_needs.get("shell_restart"):
        steps.append({
            "type": "notification",
            "message": "Restart your shell or run: source ~/.bashrc",
            "severity": "info",
        })

    # Reboot notification (not auto-executed!)
    if restart_needs.get("reboot_required"):
        steps.append({
            "type": "notification",
            "message": "A system reboot is required for changes to take effect",
            "severity": "warning",
        })

    return steps
```

---

## DAG Execution Engine

### Replacing linear execution

```python
import asyncio

async def execute_plan_dag(plan, *, sudo_password="", on_progress=None):
    """Execute a plan with parallel step support (DAG).

    Steps with depends_on run after their dependencies.
    Independent steps run in parallel.
    """
    steps = plan["steps"]

    # Add implicit linear deps for steps without depends_on
    steps = _add_implicit_deps(steps)

    # Validate DAG
    errors = _validate_dag(steps)
    if errors:
        return {"ok": False, "error": f"Invalid plan: {', '.join(errors)}"}

    completed = set()
    failed = set()
    results = {}

    while len(completed) + len(failed) < len(steps):
        ready = _get_ready_steps(steps, completed, set())

        if not ready:
            # Deadlock or all blocked by failures
            break

        # Filter out steps blocked by failed dependencies
        runnable = []
        for step in ready:
            deps = step.get("depends_on", [])
            if any(d in failed for d in deps):
                failed.add(step["id"])
                results[step["id"]] = {"ok": False, "skipped": True,
                                        "reason": "dependency failed"}
                continue
            runnable.append(step)

        if not runnable:
            break

        # Check parallelism safety
        if len(runnable) > 1:
            runnable = _enforce_parallel_safety(runnable)

        # Execute (parallel if multiple ready)
        if len(runnable) == 1:
            step = runnable[0]
            if on_progress:
                on_progress(step["id"], "started")
            result = execute_plan_step(step, sudo_password=sudo_password)
            results[step["id"]] = result
            if result["ok"]:
                completed.add(step["id"])
                if on_progress:
                    on_progress(step["id"], "done")
            else:
                failed.add(step["id"])
                if on_progress:
                    on_progress(step["id"], "failed")
        else:
            # Parallel execution
            tasks = []
            for step in runnable:
                if on_progress:
                    on_progress(step["id"], "started")
                tasks.append((step, execute_plan_step(step, sudo_password=sudo_password)))

            for step, result in tasks:
                results[step["id"]] = result
                if result["ok"]:
                    completed.add(step["id"])
                    if on_progress:
                        on_progress(step["id"], "done")
                else:
                    failed.add(step["id"])
                    if on_progress:
                        on_progress(step["id"], "failed")

    return {
        "ok": len(failed) == 0,
        "completed": list(completed),
        "failed": list(failed),
        "results": results,
    }


def _enforce_parallel_safety(steps):
    """Ensure parallel steps don't conflict."""
    # Same package manager → serialize (PM holds lock)
    pm_groups = {}
    for step in steps:
        pm = _get_step_pm(step)
        if pm:
            pm_groups.setdefault(pm, []).append(step)

    safe = []
    for pm, group in pm_groups.items():
        safe.append(group[0])  # Only first from each PM group

    # Non-PM steps can all run in parallel
    for step in steps:
        if not _get_step_pm(step) and step not in safe:
            safe.append(step)

    return safe
```

---

## Plan Format Extension

### Step IDs and depends_on

```python
{
    "tool": "docker",
    "steps": [
        {"id": "repo",     "type": "repo",
         "label": "Add Docker repo",
         "depends_on": []},
        {"id": "install",  "type": "packages",
         "label": "Install Docker CE",
         "depends_on": ["repo"]},
        {"id": "config",   "type": "config",
         "label": "Configure Docker daemon",
         "depends_on": ["install"]},
        {"id": "start",    "type": "service",
         "label": "Start Docker",
         "depends_on": ["config"]},
        {"id": "enable",   "type": "service",
         "label": "Enable Docker on boot",
         "depends_on": ["install"]},    # parallel with config+start
        {"id": "group",    "type": "post_install",
         "label": "Add user to docker group",
         "depends_on": ["install"]},    # parallel with config+start
        {"id": "verify",   "type": "verify",
         "label": "Verify Docker",
         "depends_on": ["start"]},
    ],
}
```

### Execution order (DAG)

```
repo → install → config → start → verify
                 ↘ enable (parallel)
                 ↘ group  (parallel)
```

Steps `config→start→verify`, `enable`, and `group` all depend
only on `install`. enable and group can run in parallel with
config→start.

---

## Files Touched

| File | Changes |
|------|---------|
| `tool_install.py` | Add _execute_service_step(), _execute_config_step(), detect_restart_needs(), execute_plan_dag(). Expand _run_subprocess() with stdin_data for tee. |
| `routes_audit.py` | Add POST /audit/service-status. Update execute-plan endpoint for DAG mode. |
| `_globals.html` | Restart notification rendering in step modal. |

---

## Edge Cases

| Case | Impact | Handling |
|------|--------|---------|
| No systemd (WSL1, Alpine) | Service commands fail | Detect init system, use appropriate commands |
| Config file doesn't exist yet | Can't backup | Create parent dirs, skip backup for new files |
| Config file owned by root | Can't read to check | Use sudo for all config operations |
| Reboot required but can't reboot | System in partial state | Warn user, document what needs reboot |
| Two steps write same config file | Race condition | depends_on prevents parallel writes to same file |
| DAG cycle in plan | Deadlock | Cycle detection at validation (Kahn's algorithm) |
| Parallel apt steps | dpkg lock conflict | PM lock detection, serialize same-PM steps |
| Service start fails after install | Tool installed but not running | Report service error, don't mark plan as failed |
| Shell restart needed | User may not know | Show notification with exact command |
| Docker group add needs re-login | Group not active until new session | Explain: "Log out and back in for group changes" |

---

## Phase 8 = System Complete

With Phase 8, the install system handles the FULL provisioning lifecycle:

```
Phase 1: Detect what you have
Phase 2: Know what to install and how
Phase 3: Show it to the user
Phase 4: Let the user choose
Phase 5: Build from source if needed
Phase 6: Handle hardware (GPU, kernel)
Phase 7: Download data packs
Phase 8: Configure the system, manage services, run in parallel
```

Every conceivable installation scenario — from `pip install ruff`
to GPU driver + CUDA + kernel module + service config + restart —
is covered by this architecture.

---

## Traceability

| Topic | Source |
|-------|--------|
| Service management (systemd/openrc) | domain-services §init systems |
| Config file writes + backups | domain-config-files §write operations |
| Restart detection + batching | domain-restart §restart types |
| DAG execution engine | domain-parallel-execution §async dispatcher |
| depends_on field + rules | domain-parallel-execution §dependency resolution |
| PM lock detection | domain-parallel-execution §lock-aware scheduling |
| Cycle detection | domain-parallel-execution §DAG validation |
| Docker post-install example | Phase 2 index §post-install |
| execute_plan() (Phase 2.4) | Phase 2.4 §plan execution engine |
