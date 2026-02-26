# Tool Install v2 — Phase 2.4: Install Execution & Replacement

## Context

Phase 2.3 produces an **install plan** — an ordered list of steps.
Phase 2.4 **executes** that plan, replacing the current `install_tool()`
function with a plan-based execution engine.

### Dependencies

```
Phase 2.1 (package checking)  ── provides: _is_pkg_installed(), check_system_deps()
Phase 2.2 (recipes)           ── provides: TOOL_RECIPES, recipe format
Phase 2.3 (resolver)          ── provides: resolve_install_plan() → step list
Phase 2.4 (THIS)              ── provides: execute_plan() → replaces install_tool()
```

### What gets REPLACED

| Current code | Replaced by |
|-------------|-------------|
| `install_tool()` (lines 277-470) | `execute_plan()` |
| `_NO_SUDO_RECIPES` (lines 34-46) | `TOOL_RECIPES` (from 2.2) |
| `_SUDO_RECIPES` (lines 49-83) | `TOOL_RECIPES` (from 2.2) |
| `CARGO_BUILD_DEPS` (line 88) | `TOOL_RECIPES["cargo-audit"].requires.packages` |
| `_RUNTIME_DEPS` (lines 354-358) | `TOOL_RECIPES[tool].requires.binaries` |
| `_TOOL_REQUIRES` (lines 360-363) | `TOOL_RECIPES[tool].requires.binaries` |
| `check_system_deps()` dpkg-only (lines 91-104) | Multi-PM `check_system_deps()` (from 2.1) |

### What gets KEPT

| Current code | Why kept |
|-------------|---------|
| `_analyse_install_failure()` (lines 111-271) | Enhanced, not replaced. New recipes feed it more context. |
| `_audit()` calls | Same pattern, applied to plan steps. |
| `sudo -S -k` piping | Same mechanism, now per-step. |

---

## The Plan Format (input to this phase)

From Phase 2.3, `resolve_install_plan()` returns:

```python
{
    "tool": "cargo-audit",
    "steps": [
        {"type": "packages", "label": "Install build dependencies",
         "packages": ["pkg-config", "libssl-dev", "libcurl4-openssl-dev"],
         "command": ["apt-get", "install", "-y", "pkg-config", "libssl-dev", "libcurl4-openssl-dev"],
         "needs_sudo": True},
        {"type": "tool", "label": "Install cargo-audit",
         "command": ["cargo", "install", "cargo-audit"],
         "needs_sudo": False,
         "timeout": 300},
        {"type": "verify", "label": "Verify cargo-audit",
         "command": ["cargo-audit", "--version"],
         "needs_sudo": False},
    ],
    "post_env": {"PATH": "$HOME/.cargo/bin:$PATH"},
}
```

---

## New Public API

### execute_plan()

```python
def execute_plan(
    plan: dict,
    *,
    sudo_password: str = "",
) -> dict[str, Any]:
    """Execute an install plan step by step.

    Args:
        plan: Install plan from resolve_install_plan().
        sudo_password: Sudo password for steps that need it.

    Returns:
        {"ok": True, "tool": "...", "steps_completed": N, ...} on success,
        {"ok": False, "error": "...", "step": N, "needs_sudo": bool, ...} on failure.
    """
```

### execute_plan_step()

```python
def execute_plan_step(
    step: dict,
    *,
    sudo_password: str = "",
    env_overrides: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Execute a single plan step.

    Args:
        step: Single step dict from plan["steps"].
        sudo_password: Sudo password if step.needs_sudo.
        env_overrides: Extra env vars (e.g. PATH from post_env).

    Returns:
        {"ok": True, "stdout": "...", "elapsed_ms": N} on success,
        {"ok": False, "error": "...", "stderr": "...", "remediation": {...}} on failure.
    """
```

### install_tool() (backward-compatible wrapper)

```python
def install_tool(
    tool: str,
    *,
    cli: str = "",
    sudo_password: str = "",
    override_command: list[str] | None = None,
) -> dict[str, Any]:
    """Install a tool — backward-compatible wrapper.

    Generates a plan via resolve_install_plan(), then executes it.
    Existing callers don't need to change.
    """
    if override_command:
        # Legacy path: direct command execution (remediation options)
        return _execute_single_command(tool, cli, override_command, sudo_password)

    plan = resolve_install_plan(tool, get_system_profile())
    if plan.get("error"):
        return {"ok": False, "error": plan["error"]}

    return execute_plan(plan, sudo_password=sudo_password)
```

---

## Step Execution Logic

### Step type dispatch

```python
def execute_plan_step(step, *, sudo_password="", env_overrides=None):
    step_type = step.get("type", "tool")

    if step_type == "packages":
        return _execute_package_step(step, sudo_password=sudo_password)
    elif step_type == "repo":
        return _execute_repo_step(step, sudo_password=sudo_password)
    elif step_type == "tool":
        return _execute_command_step(step, sudo_password=sudo_password,
                                    env_overrides=env_overrides)
    elif step_type == "post_install":
        return _execute_command_step(step, sudo_password=sudo_password)
    elif step_type == "verify":
        return _execute_verify_step(step, env_overrides=env_overrides)
    else:
        return {"ok": False, "error": f"Unknown step type: {step_type}"}
```

### Package step

```python
def _execute_package_step(step, *, sudo_password=""):
    """Install system packages (apt, dnf, apk, etc.)."""
    # Skip already-installed packages
    missing = check_system_deps(step["packages"])["missing"]
    if not missing:
        return {"ok": True, "message": "All packages already installed",
                "skipped": True}

    # Rebuild command with only missing packages
    cmd = _build_pkg_install_cmd(missing, step.get("package_manager", "apt"))
    return _run_subprocess(cmd, needs_sudo=True,
                           sudo_password=sudo_password,
                           timeout=step.get("timeout", 120))
```

### Repo setup step

```python
def _execute_repo_step(step, *, sudo_password=""):
    """Set up a package repository (GPG key + source list)."""
    results = []
    for sub_step in step.get("sub_steps", [step]):
        result = _run_subprocess(
            sub_step["command"],
            needs_sudo=sub_step.get("needs_sudo", True),
            sudo_password=sudo_password,
            timeout=sub_step.get("timeout", 60),
        )
        results.append(result)
        if not result["ok"]:
            return result
    return {"ok": True, "message": "Repository configured",
            "sub_results": results}
```

### Command step (tool install, post_install)

```python
def _execute_command_step(step, *, sudo_password="", env_overrides=None):
    """Execute a command step (tool install or post_install action)."""
    return _run_subprocess(
        step["command"],
        needs_sudo=step.get("needs_sudo", False),
        sudo_password=sudo_password,
        timeout=step.get("timeout", 120),
        env_overrides=env_overrides,
    )
```

### Verify step

```python
def _execute_verify_step(step, *, env_overrides=None):
    """Verify a tool is installed and working."""
    cli = step.get("cli", step["command"][0])

    # Build environment with post_env
    env = _build_env(env_overrides)

    # Check PATH first
    binary = shutil.which(cli, path=env.get("PATH"))
    if not binary:
        return {
            "ok": False,
            "error": f"'{cli}' not found in PATH after install",
            "needs_shell_restart": True,
        }

    # Run verify command
    result = _run_subprocess(
        step["command"],
        needs_sudo=False,
        timeout=10,
        env_overrides=env_overrides,
    )
    return result
```

---

## Subprocess Runner

### Core runner (replaces inline subprocess.run)

```python
import os
import time

def _run_subprocess(
    cmd: list[str],
    *,
    needs_sudo: bool = False,
    sudo_password: str = "",
    timeout: int = 120,
    env_overrides: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Run a subprocess command with sudo and env support.

    This is the SINGLE PLACE where subprocess.run is called for
    install operations. All security, logging, and error handling
    is centralized here.
    """
    # Sudo handling
    if needs_sudo:
        if os.geteuid() == 0:
            # Already root — no sudo needed
            pass
        elif not sudo_password:
            return {
                "ok": False,
                "needs_sudo": True,
                "error": "This step requires sudo. Please enter your password.",
            }
        else:
            cmd = ["sudo", "-S", "-k"] + cmd

    # Environment
    env = os.environ.copy()
    if env_overrides:
        for key, value in env_overrides.items():
            env[key] = os.path.expandvars(value)

    # Execute
    start = time.monotonic()
    try:
        stdin_data = (sudo_password + "\n") if (needs_sudo and sudo_password) else None
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            input=stdin_data,
            env=env,
        )
        elapsed_ms = int((time.monotonic() - start) * 1000)

        if result.returncode == 0:
            return {
                "ok": True,
                "stdout": result.stdout[-2000:] if result.stdout else "",
                "elapsed_ms": elapsed_ms,
            }

        stderr = result.stderr[-2000:] if result.stderr else ""

        # Wrong password?
        if needs_sudo and ("incorrect password" in stderr.lower()
                           or "sorry" in stderr.lower()):
            return {
                "ok": False,
                "needs_sudo": True,
                "error": "Wrong password. Try again.",
            }

        return {
            "ok": False,
            "error": f"Command failed (exit {result.returncode})",
            "stderr": stderr,
            "stdout": result.stdout[-2000:] if result.stdout else "",
            "elapsed_ms": elapsed_ms,
        }

    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"Command timed out ({timeout}s)"}
    except Exception as e:
        logger.exception("Subprocess error: %s", cmd)
        return {"ok": False, "error": str(e)}
```

---

## Plan Execution Engine

### Full plan runner

```python
def execute_plan(plan, *, sudo_password=""):
    """Execute all steps in a plan sequentially."""
    tool = plan["tool"]
    steps = plan["steps"]
    post_env = plan.get("post_env", {})
    completed = []
    env_overrides = {}

    for i, step in enumerate(steps):
        step_label = step.get("label", f"Step {i+1}")
        step_type = step.get("type", "tool")

        _audit(
            f"🔧 Plan Step {i+1}/{len(steps)}",
            f"{tool}: {step_label}",
            action="started",
            target=tool,
        )

        # Accumulate env overrides as steps complete
        if step_type == "tool" and post_env:
            env_overrides.update(post_env)

        result = execute_plan_step(
            step,
            sudo_password=sudo_password,
            env_overrides=env_overrides if env_overrides else None,
        )

        if result.get("skipped"):
            _audit(
                f"⏭️ Step Skipped",
                f"{tool}: {step_label} (already satisfied)",
                action="skipped",
                target=tool,
            )
            completed.append({"step": i, "label": step_label, "skipped": True})
            continue

        if not result["ok"]:
            # Sudo needed — propagate to caller
            if result.get("needs_sudo"):
                return {
                    "ok": False,
                    "needs_sudo": True,
                    "error": result["error"],
                    "step": i,
                    "step_label": step_label,
                    "completed": completed,
                }

            # Step failed — try remediation analysis
            remediation = None
            if step_type == "tool":
                remediation = _analyse_install_failure(
                    tool, plan.get("cli", tool),
                    result.get("stderr", ""),
                )

            _audit(
                f"❌ Step Failed",
                f"{tool}: {step_label} — {result['error']}",
                action="failed",
                target=tool,
                detail={"step": i, "stderr": result.get("stderr", "")[:500]},
            )

            response = {
                "ok": False,
                "error": result["error"],
                "step": i,
                "step_label": step_label,
                "completed": completed,
                "stderr": result.get("stderr", ""),
            }
            if remediation:
                response["remediation"] = remediation
            return response

        _audit(
            f"✅ Step Done",
            f"{tool}: {step_label}",
            action="completed",
            target=tool,
        )
        completed.append({
            "step": i, "label": step_label,
            "elapsed_ms": result.get("elapsed_ms"),
        })

    # All steps complete
    _audit(
        "✅ Tool Installed",
        f"{tool}: all {len(steps)} steps completed",
        action="installed",
        target=tool,
    )

    return {
        "ok": True,
        "tool": tool,
        "message": f"{tool} installed successfully",
        "steps_completed": len(completed),
        "completed": completed,
    }
```

---

## Sudo Password Handling Across Steps

### Problem

A plan may have multiple sudo steps:
```
Step 1: apt-get install pkg-config libssl-dev  (needs sudo)
Step 2: cargo install cargo-audit              (no sudo)
Step 3: systemctl enable someservice           (needs sudo)
```

The password is passed ONCE by the caller. The engine reuses
it for ALL sudo steps in the plan.

### Behavior

| Scenario | Behavior |
|----------|----------|
| No sudo steps | Password ignored |
| One sudo step, no password | Return `needs_sudo: True` at that step |
| One sudo step, with password | Execute with `sudo -S -k` |
| Multiple sudo steps, wrong password | Fail at first sudo step |
| First sudo step passes, later fails | Second attempt still uses -k, re-validates |

### sudo -k rationale

We use `sudo -k` on EVERY call to ensure the password we provide
is actually validated. This means each subprocess re-authenticates.
On a 3-step plan with 2 sudo steps, the user enters the password
once (in the frontend), and the engine pipes it twice.

---

## Post-Env Propagation

### Problem

Some tools install binaries to non-standard paths:
- `cargo install` → `~/.cargo/bin/`
- `go install` → `~/go/bin/`
- `rustup` → `~/.cargo/bin/`

The verify step (and any subsequent steps) need these paths.

### Solution

```python
# Plan has post_env
"post_env": {"PATH": "$HOME/.cargo/bin:$PATH"}

# Engine applies it to subsequent steps
env = os.environ.copy()
env["PATH"] = os.path.expandvars("$HOME/.cargo/bin:$PATH")
```

### When applied

| Step type | Gets post_env? |
|-----------|---------------|
| packages | No — system packages go to system PATH |
| repo | No — repo setup doesn't need tool PATH |
| tool | Yes — the install itself may need updated PATH |
| post_install | Yes — may call the just-installed binary |
| verify | Yes — must find the just-installed binary |

---

## Cache Invalidation

### After successful install

```python
# After execute_plan() returns ok=True:
# 1. l0_detection cache is stale — installed tools changed
# 2. System deps cache is stale — packages changed
# 3. Frontend tool status needs refresh

# Signal to routes_audit.py:
return {
    "ok": True,
    ...,
    "invalidates": ["l0_detection", "system_deps", "tool_status"],
}
```

### Frontend cache invalidation

```javascript
// After successful install response
if (resp.ok) {
    // Clear cached detection results
    sessionStorage.removeItem('l0_detection');
    sessionStorage.removeItem('system_deps_cache');
    // Trigger re-scan
    refreshToolStatus();
}
```

---

## SSE Streaming (Future — Phase 3)

### Current: synchronous

Phase 2.4 uses `subprocess.run()` — waits for completion.
This is fine for the backend. The frontend shows a spinner.

### Phase 3: SSE streaming

Phase 3 will replace `subprocess.run` with `subprocess.Popen`
and yield SSE events per output line:

```python
def execute_plan_stream(plan, *, sudo_password=""):
    """Execute plan with SSE streaming."""
    for i, step in enumerate(plan["steps"]):
        yield {"type": "step_start", "step": i, "label": step["label"]}

        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        for line in proc.stdout:
            yield {"type": "log", "step": i, "line": line.rstrip()}

        proc.wait()
        if proc.returncode == 0:
            yield {"type": "step_done", "step": i}
        else:
            yield {"type": "step_failed", "step": i}
            return

    yield {"type": "plan_done"}
```

Phase 2.4 focuses on the LOGIC. Phase 3 adds the STREAMING.

---

## Removing Old Code

### Deletion checklist

After `execute_plan()` is verified working:

| Line range | What | Remove? |
|-----------|------|---------|
| 34-46 | `_NO_SUDO_RECIPES` | ✅ Remove — recipes in TOOL_RECIPES |
| 49-83 | `_SUDO_RECIPES` | ✅ Remove — recipes in TOOL_RECIPES |
| 88 | `CARGO_BUILD_DEPS` | ✅ Remove — in recipe requires |
| 91-104 | `check_system_deps()` (dpkg-only) | ✅ Replace with multi-PM version (from 2.1) |
| 354-358 | `_RUNTIME_DEPS` | ✅ Remove — in recipe requires.binaries |
| 360-363 | `_TOOL_REQUIRES` | ✅ Remove — in recipe requires.binaries |
| 277-470 | `install_tool()` | 🔄 Keep as wrapper, guts replaced |

### Backward compatibility guarantee

`install_tool(tool, cli=..., sudo_password=...)` continues to work.
Internally it calls `resolve_install_plan()` then `execute_plan()`.
Existing route handlers (`routes_audit.py`) don't need changes.

---

## New Route: POST /audit/install-plan

### Expose the plan before execution

```python
@app.post("/audit/install-plan")
def get_install_plan():
    """Return the install plan for a tool (without executing)."""
    tool = request.json.get("tool")
    profile = get_system_profile()
    plan = resolve_install_plan(tool, profile)
    return jsonify(plan)
```

### Why

The frontend can show the plan BEFORE the user clicks "Install":
- "This will: 1) Install build deps, 2) Install cargo-audit, 3) Verify"
- "Steps 1 and 3 need sudo"
- User confirms, THEN execution begins

---

## Error Handling

### Per-step error enrichment

```python
# Each step failure includes:
{
    "ok": False,
    "error": "Command failed (exit 1)",
    "stderr": "...",
    "step": 1,                          # Which step failed
    "step_label": "Install cargo-audit", # Human-readable
    "completed": [...],                  # Steps that succeeded
    "remediation": {...},                # From _analyse_install_failure()
}
```

### Step retry

If a step fails and the user fixes the issue (e.g., provides
correct password, installs missing dep manually), the frontend
can retry from the failed step:

```python
def execute_plan(plan, *, sudo_password="", start_from=0):
    """Execute plan from a specific step (for retry)."""
    steps = plan["steps"]
    for i, step in enumerate(steps):
        if i < start_from:
            continue  # Skip already-completed steps
        ...
```

---

## Files Touched

| File | Changes |
|------|---------|
| `tool_install.py` | Add execute_plan(), execute_plan_step(), _run_subprocess(). Replace install_tool() guts. Remove old recipe dicts. |
| `routes_audit.py` | Add POST /audit/install-plan endpoint. |

---

## Test Scenarios

| Scenario | Expected |
|----------|----------|
| Simple pip tool (ruff) | 1 step: pip install. No sudo. Verify find ruff. |
| System package (jq) | 1 step: apt install. Sudo required. |
| Cargo tool (cargo-audit) | 3 steps: deps → install → verify. |
| Already installed | Plan returns "already installed", no execution. |
| Missing dependency (npm tool, no npm) | Plan includes npm install step first. |
| Wrong sudo password | Fail at first sudo step, return needs_sudo. |
| No recipe | Return error, no plan generated. |
| Step 2 fails | Step 1 completed, step 2 error with remediation. |
| Post-env needed (cargo) | Verify step finds binary via updated PATH. |
| Override command | Legacy path works unchanged. |

---

## Traceability

| Topic | Source |
|-------|--------|
| Plan format (input) | Phase 2.3 resolver output |
| Recipe format | Phase 2.2 dependency declarations |
| Package checking | Phase 2.1 multi-distro package checking |
| Current install_tool() | tool_install.py lines 277-470 |
| Sudo -S -k mechanism | domain-sudo-security §password flow |
| Post-env (PATH) | domain-shells §PATH propagation |
| Cache invalidation | domain-devops-tools §l0_detection |
| SSE streaming (Phase 3) | domain-pages-install §SSE format |
| Remediation analysis | tool_install.py _analyse_install_failure() |
