# L4 Execution — System Writers

> Runs commands, writes config files, manages plan state.
> All side effects live here and ONLY here.

---

## Files

### `subprocess_runner.py` — Command Execution

The single bottleneck for ALL subprocess calls in the system.
Two modes:

**Blocking** (`_run_subprocess`):
```python
result = _run_subprocess(
    ["apt-get", "install", "-y", "pkg-config"],
    needs_sudo=True,
    sudo_password="...",
    timeout=120,
)
# → {"ok": True, "stdout": "...", "stderr": "...", "elapsed_ms": 2340}
```

**Streaming** (`_run_subprocess_streaming`):
```python
for chunk in _run_subprocess_streaming(
    ["cargo", "install", "cargo-audit"],
    needs_sudo=False,
    timeout=600,
):
    if "line" in chunk:
        print(chunk["line"])   # live output line
    if chunk.get("done"):
        print(chunk["ok"])     # final result
```

Streaming merges stdout + stderr into one stream (because cargo writes
compilation progress to stderr, not stdout). All output streams live.

**Security invariants** (both modes):
- `sudo -S -k` — password via stdin, cached creds invalidated
- Password NEVER appears in command args
- Password NEVER logged

### `step_executors.py` — Step Type Dispatchers

14 step type executors. Each takes a step dict and returns a result dict.

| Executor | Step Type | What it does |
|----------|-----------|-------------|
| `_execute_package_step` | `packages` | apt-get/dnf/brew install |
| `_execute_repo_step` | `repo_setup` | Add PPA, import GPG key |
| `_execute_command_step` | `tool`, `post_install` | Run arbitrary command |
| `_execute_verify_step` | `verify` | Check exit code 0 |
| `_execute_config_step` | `config` | Write/modify config files |
| `_execute_shell_config_step` | `shell_config` | Add lines to .bashrc/.zshrc |
| `_execute_service_step` | `service` | systemctl start/enable |
| `_execute_download_step` | `download` | Download file |
| `_execute_github_release_step` | `github_release` | GitHub release binary |
| `_execute_source_step` | `source` | git clone |
| `_execute_build_step` | `build` | make/cmake/cargo build |
| `_execute_install_step` | `install` | Install built artifacts |
| `_execute_cleanup_step` | `cleanup` | Remove temp files |
| `_execute_notification_step` | `notification` | Emit user message |
| `_execute_rollback` | (rollback) | Undo completed steps |

### `plan_state.py` — Plan Persistence

Saves plan execution state to disk for resumability.

```python
from src.core.services.tool_install.execution.plan_state import (
    save_plan_state, load_plan_state, resume_plan, list_pending_plans,
)

# Save progress after each step
save_plan_state({"plan_id": "...", "status": "running", "current_step": 2, ...})

# Resume after interruption
state = resume_plan(plan_id)

# List all interrupted/pending plans
pending = list_pending_plans()
```

### `script_verify.py` — curl|bash Safety

Intercepts curl-pipe-bash commands, downloads the script first,
verifies SHA256 hash against recipe declaration, then executes.

```python
from src.core.services.tool_install.execution.script_verify import (
    is_curl_pipe_command, rewrite_curl_pipe_to_safe,
)

if is_curl_pipe_command(cmd):
    safe_cmd = rewrite_curl_pipe_to_safe(cmd, expected_sha256="abc123...")
    # Downloads script → verifies hash → runs local copy
```

### `config.py` — Config File Management

Writes shell config lines (PATH exports, etc.) to the correct rc file.

```python
from src.core.services.tool_install.execution.config import _shell_config_line

result = _shell_config_line("bash", 'export PATH="$HOME/.cargo/bin:$PATH"')
# → Appends to ~/.bashrc if not already present
```

### `download.py` — Download Utilities

GitHub release resolution and checksum verification.

### `backup.py` — Pre-Step Backup

Creates backups before risky modifications (config files, etc.).

### `build_helpers.py` — Build-from-Source

Generates build plans for autotools, cmake, and cargo-git projects.
Validates toolchain availability and checks resource requirements.

### `offline_cache.py` — Offline Install Support

Downloads and caches all artifacts needed for a plan, enabling
offline installation later.

### `tool_management.py` — Tool Lifecycle

Update and remove operations.

```python
from src.core.services.tool_install.execution.tool_management import update_tool, remove_tool

result = update_tool("cargo-audit", sudo_password="...")
result = remove_tool("cargo-audit", sudo_password="...")
```
