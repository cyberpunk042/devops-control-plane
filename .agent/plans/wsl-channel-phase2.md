# Phase 2: Alternative Tunnel Backends

## Status: ANALYSIS — Awaiting Review

## Implementation Priority: 6 of 7 (after tunnel, UI, firewall, notifications, validation)

---

## What This Phase Delivers

Additional tunnel implementations behind the SAME interface as Phase 1's
`WslTunnel`. The user picks which tunnel method to use from the setup UI.
All implementations share `start()`, `stop()`, `is_running`, `validate()`.

---

## Dependency: Phase 1 Must Exist First

Phase 2 builds ON Phase 1's interface. The `WslTunnel` class from Phase 1
becomes the **base pattern**. Alternative backends implement the same API:

```python
# Phase 1 creates this interface:
class WslTunnel:
    def start(self) -> bool: ...
    def stop(self) -> None: ...
    @property
    def is_running(self) -> bool: ...
    def validate(self) -> dict: ...
    @property
    def stats(self) -> dict: ...
```

Phase 2 adds:
```python
class SocatTunnel:     # same interface
class NetshTunnel:     # same interface
class SshTunnel:       # same interface
class MirroredConfig:  # different — modifies .wslconfig, not a running tunnel
```

---

## Backend Details

### 2A: SocatTunnel

**What:** Shells out to `socat` to create a TCP port forward.

```bash
socat TCP-LISTEN:9222,fork,reuseaddr TCP:$(hostname).local:9222
```

**Implementation:**
- `start()`: Check `shutil.which("socat")`, spawn as `subprocess.Popen`, store PID
- `stop()`: Kill the socat process by PID
- `is_running`: Check if PID is alive
- `validate()`: Same as Phase 1 — HTTP GET through localhost:9222

**Prerequisites:**
- `socat` package installed (`apt install socat`)
- hostname.local resolves
- Firewall rule exists

**Install plan for socat:**
```python
install_steps = [
    {"label": "Check if socat is installed", "cmd": "which socat", "type": "auto"},
    {"label": "Install socat via apt", "cmd": "sudo apt install -y socat", "type": "semi-auto"},
]
```

**Integration with Phase 4 (UI):**
- UI shows "socat" option
- If socat not installed → shows [Install socat] button
- If installed → shows [Start Tunnel] button

### 2B: NetshTunnel

**What:** Configures Windows `netsh interface portproxy` to forward from
0.0.0.0:9222 → 127.0.0.1:9222 on the Windows side.

```powershell
netsh interface portproxy add v4tov4 `
    listenport=9222 listenaddress=0.0.0.0 `
    connectport=9222 connectaddress=127.0.0.1
```

**Implementation:**
- `start()`: Run via elevated PowerShell (UAC prompt), verify with `netsh show`
- `stop()`: `netsh interface portproxy delete v4tov4 listenport=9222 listenaddress=0.0.0.0`
- `is_running`: `netsh interface portproxy show v4tov4` and parse output
- `validate()`: HTTP GET through hostname.local:9222 (not localhost!)

**Key difference:** This tunnel runs on Windows, not WSL. It's persistent
across reboots (survives WSL restarts). Chrome stays on 127.0.0.1.

**Prerequisites:**
- Elevated PowerShell (UAC prompt)
- Firewall rule exists (still needed — netsh opens a new listener)
- hostname.local resolves (WSL connects via hostname.local, not localhost)

**Integration with Phase 4 (UI):**
- UI shows "netsh portproxy (persistent)" option
- Shows warning: "Requires admin elevation"
- Shows benefit: "Survives reboots — set up once"

### 2C: SshTunnel

**What:** SSH local port forward from WSL to Windows.

```bash
ssh -N -L 9222:localhost:9222 user@$(hostname).local
```

**Implementation:**
- `start()`: Spawn SSH as background process, handle auth
- `stop()`: Kill SSH process
- `is_running`: Check PID
- `validate()`: HTTP GET through localhost:9222

**Prerequisites:**
- OpenSSH server running on Windows
- SSH key or password auth configured
- hostname.local resolves

**Complexity:** Higher than other options. SSH key management, server detection,
auth prompts. May integrate with existing SSH auth flow (git identity).

**Integration with Phase 4 (UI):**
- UI shows "SSH tunnel (encrypted)" option
- Shows prerequisite: "Needs OpenSSH server on Windows"
- Lower priority — most users won't have this set up

### 2D: MirroredConfig

**What:** Modifies `.wslconfig` to set `networkingMode=mirrored`.
NOT a tunnel — changes the networking model entirely.

```ini
[wsl2]
networkingMode=mirrored
```

**Implementation:**
- `start()`: Modify `.wslconfig`, prompt for WSL restart
- `stop()`: Remove the line, prompt for WSL restart
- `is_running`: Check `.wslconfig` for `networkingMode=mirrored`
- `validate()`: After restart, test localhost:9222 directly

**Key difference:** No tunnel process. localhost works natively after restart.
But this is RISKY — can break VS Code, IDE networking.

**Prerequisites:**
- Write access to `.wslconfig` (user-level, no admin)
- WSL restart required (disruptive)

**Integration with Phase 4 (UI):**
- UI shows "⚠️ Mirrored networking" with WARNING
- Clear message: "May break VS Code and other IDE networking"
- User must explicitly confirm before applying
- Shows as separate "risky" section, not alongside other options

---

## Tunnel Registry

A singleton that manages active tunnels:

```python
# In wsl_tunnel.py (Phase 1 file, extended in Phase 2)

_active_tunnel: WslTunnel | SocatTunnel | NetshTunnel | SshTunnel | None = None

def get_active_tunnel():
    """Return the currently active tunnel, or None."""
    return _active_tunnel

def start_tunnel(method: str, port: int, target_host: str) -> dict:
    """Start a tunnel using the specified method.
    
    Args:
        method: "python", "socat", "netsh", "ssh", "mirrored"
        port: Local port to listen on
        target_host: Windows host IP
    
    Returns:
        {"ok": True/False, "method": str, "error": str | None}
    """
    global _active_tunnel
    
    # Stop existing tunnel first
    if _active_tunnel and _active_tunnel.is_running:
        _active_tunnel.stop()
    
    # Create and start the requested type
    ...

def stop_tunnel() -> None:
    """Stop the active tunnel."""
    ...
```

**Only ONE tunnel active at a time.** The UI shows which one is running.

---

## Interconnection with Other Phases

| Phase | How Phase 2 Connects |
|-------|---------------------|
| Phase 1 | Extends the interface. Shares `validate()` logic. Same registry. |
| Phase 3 (Firewall) | socat, netsh, python proxy all need firewall rule. SSH doesn't. |
| Phase 4 (UI) | UI shows all tunnel choices. Calls `start_tunnel(method=...)` |
| Phase 5 (Notifications) | Notification says current level. After upgrade, notification dismissed. |
| Phase 7 (Validation) | All tunnels use same validation endpoint. |

---

## Files Created/Modified

| File | Action | What |
|------|--------|------|
| `src/core/services/chrome/wsl_tunnel.py` | **EXTEND** | Add SocatTunnel, NetshTunnel, SshTunnel, MirroredConfig |
| `src/core/services/chrome/wsl_tunnel.py` | **EXTEND** | Add tunnel registry (get_active, start, stop) |
| `tests/unit/test_wsl_tunnel_backends.py` | **NEW** | Tests for each backend |

---

## Testing Plan

| # | Test | What It Verifies |
|---|------|-----------------|
| 1 | `test_socat_start_stop` | socat process spawns and is killed correctly |
| 2 | `test_socat_not_installed` | Returns error when socat not on PATH |
| 3 | `test_netsh_creates_portproxy` | PowerShell command is constructed correctly |
| 4 | `test_netsh_removes_portproxy` | Cleanup command works |
| 5 | `test_netsh_detect_existing` | Parses `netsh show` output to detect running proxy |
| 6 | `test_ssh_start_stop` | SSH tunnel spawns and is killed |
| 7 | `test_mirrored_config_write` | .wslconfig is modified correctly |
| 8 | `test_mirrored_config_revert` | .wslconfig is restored correctly |
| 9 | `test_registry_one_at_a_time` | Starting a tunnel stops the previous one |
| 10 | `test_validate_through_each_backend` | Each backend's validate works with mock |
