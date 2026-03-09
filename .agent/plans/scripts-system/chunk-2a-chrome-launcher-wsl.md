# Chunk 2a: ChromeLauncher — WSL→Windows Path

> **Status**: Planning
> **Created**: 2026-03-09
> **Parent**: `scripts-system-M7-plans.md` → Chunk 2
> **Depends on**: Chunk 1 (Chrome domain extraction) ✅ DONE

---

## 0. What This Chunk Builds

A `ChromeLauncher` service class in `src/core/services/chrome/launcher.py` that:
- Launches Chrome instances on the Windows side via PowerShell interop (WSL→Win)
- Allocates debug ports without collision
- Captures the Chrome PID for targeted kill
- Polls for CDP ready-state before returning
- Tracks all managed instances for lifecycle management
- Provides kill-by-PID and kill-all capabilities
- Thread-safe for concurrent callers

This is the **WSL→Windows path only** — the proven path that exists today in
`restart_chrome()`. Native Linux and Native Windows paths are Chunk 2b and 2c.

---

## 1. What Exists Today — Traced from Source

### 1.1 `restart_chrome()` route (tab_mesh lines 102-190)

Current flow:
```
1. Check _is_wsl()
2. Read JSON body: profile_dir, return_url, port (default 9222)
3. Get windows_user via _get_windows_user()
4. Read email from profile list (_read_chrome_profiles + match by dir)
5. Get debug dir path: _chrome_debug_data_dir_win(windows_user)
   → "C:\Users\{user}\AppData\Local\Google\ChromeDebug"
6. Build landing URL with #chrome-signin&email=<email> for auto-fill
7. Build PS1 script:
   - Start-Sleep -Seconds 2
   - taskkill /F /IM chrome.exe 2>$null
   - Start-Sleep -Seconds 2
   - Start-Process "chrome.exe" -ArgumentList "--remote-debugging-port=9222",
     "--user-data-dir=<debug_dir>", "--no-first-run", "<landing_url>"
8. Write PS1 to temp file, convert path via wslpath -w
9. Run via subprocess.Popen (fire-and-forget, no PID capture)
10. Return {success, launch_scheduled, email}
```

Problems for multi-instance:
- Step 7 kills ALL Chrome (`taskkill /IM`)
- Step 9 doesn't capture Chrome PID (gets PowerShell PID, not Chrome PID)
- Step 5 uses a single shared debug dir (can't have two instances)
- No port conflict detection
- No ready-state check

### 1.2 `kill_chrome()` route (tab_mesh lines 73-99)

Current flow:
```
1. Check _is_wsl()
2. Run taskkill.exe /F /IM chrome.exe
3. Return {killed, message}
```

Problem: kills ALL Chrome processes, not a specific instance.

### 1.3 CDP networking in WSL2 (cdp_client.py)

Critical constraint traced from `_get_json()` (lines 130-150):
- In WSL2, Python CANNOT reach `localhost:<port>` on Windows directly
- cdp_client uses `curl.exe` (Windows binary) as a bridge
- `curl.exe` runs in the Windows network namespace → CAN reach Chrome's localhost
- This means ready-state polling must ALSO use `curl.exe` in WSL2

The `try_discover_endpoint()` function handles WSL2 by trying:
1. localhost (works if mirrored networking)
2. resolv.conf nameserver IP
3. Default gateway IP

For a specific port, the launcher needs the same fallback logic.

### 1.4 Chrome 136+ constraint (cdp_client.py lines 1372-1389)

`requires_user_data_dir()` checks if Chrome >= 136. If so,
`--user-data-dir` MUST point to a non-default directory or
`--remote-debugging-port` is silently ignored.

The current `restart_chrome()` always passes `--user-data-dir=<debug_dir>`,
so this is handled. The launcher must do the same.

### 1.5 Port 9222 (cdp_client.py line 29)

`_DEFAULT_PORT = 9222` — hardcoded. The cdp_client module has a global
`_endpoint` singleton. The launcher doesn't change this — it manages
independent instances that callers connect to via their own endpoints.

---

## 2. Data Model

### 2.1 ChromeLaunchConfig

```python
@dataclass
class ChromeLaunchConfig:
    """Configuration for launching a Chrome instance."""

    port: int = 0
    # 0 = auto-allocate via find_free_debug_port()
    # >0 = use this specific port (fail if busy)

    profile_type: str = "temp"
    # "temp" = fresh debug dir, no sign-in (GoogleAccountless)
    # "email" = fresh debug dir, but read user's email for sign-in auto-fill

    email: str = ""
    # When profile_type="email", the email to pre-fill in the sign-in flow.
    # If empty and profile_type="email", caller must provide it
    # (from read_chrome_profiles + user selection).

    headless: bool = False
    # True = add --headless flag. Required when WSL has no X11/display.

    kill_existing: bool = False
    # True = taskkill /F /IM chrome.exe before launching (restart mode).
    # False = launch alongside existing Chrome (multi-instance mode).

    landing_url: str = ""
    # URL to open on launch. When email is provided, the launcher appends
    # #chrome-signin&email=<email> for auto-fill.
    # When empty, Chrome opens its default new tab page.

    no_first_run: bool = True
    # True = add --no-first-run flag (skip Chrome welcome wizard).

    chrome_exe: str = ""
    # Override Chrome executable path. Empty = default:
    # "C:\Program Files\Google\Chrome\Application\chrome.exe"
```

### 2.2 ChromeInstance

```python
@dataclass
class ChromeInstance:
    """A running Chrome instance managed by the launcher."""

    pid: int = 0
    # Windows PID of the Chrome browser process.
    # Used for targeted kill (taskkill /F /PID <pid>).

    port: int = 0
    # Debug port this instance is listening on.

    profile_dir: str = ""
    # Windows path to the --user-data-dir used.
    # e.g. "C:\Users\Jean\AppData\Local\Google\ChromeDebug-9223"

    headless: bool = False
    # Whether this instance was launched in headless mode.

    endpoint: str = ""
    # Full CDP endpoint URL, e.g. "http://localhost:9223"
    # This is what callers pass to cdp_client.set_endpoint() or
    # use to construct ws:// URLs for CdpSession.

    email: str = ""
    # The email used for sign-in auto-fill, if applicable.
    # Empty for temp/GoogleAccountless instances.

    started_at: str = ""
    # ISO timestamp of launch.

    ready: bool = False
    # True when CDP endpoint responded to /json/version.
    # Set by _wait_for_ready().
```

---

## 3. ChromeLauncher Class — Method by Method

### 3.1 Class Structure

```python
class ChromeLauncher:
    """Manages Chrome instances in WSL→Windows environment.

    Thread-safe. Tracks all launched instances. Handles port allocation,
    PID capture, CDP ready-state polling, and targeted/bulk kill.
    """

    def __init__(self):
        self._instances: dict[int, ChromeInstance] = {}  # port → instance
        self._reserved_ports: set[int] = set()           # claimed, not yet launched
        self._lock: threading.Lock = threading.Lock()
```

### 3.2 `find_free_debug_port(start, max_tries)` → int

**Purpose**: Find a TCP port not in use, starting from `start`.

**Mechanism**: In WSL2, Chrome binds on the WINDOWS network. Two options:
- A) Python socket from WSL — works if mirrored networking enabled
- B) `curl.exe http://localhost:<port>/json` — works always because curl.exe
  runs in Windows namespace

We use BOTH: try socket first (fast), fall back to curl.exe check (reliable).
Also check against `_reserved_ports` to avoid races.

**WSL2 Port Check via curl.exe**:
The same `curl.exe` approach from cdp_client. If `curl.exe` returns data
from `http://localhost:<port>/json`, the port is in use by a Chrome instance.
If it gets connection refused, the port is free.

But the port could be in use by a NON-Chrome process. So we also do a
socket check. If socket connect succeeds → port is busy (something is
listening). If it fails → port is free.

**Logic**:
```
for port in range(start, start + max_tries):
    if port in self._reserved_ports:
        continue
    if port in self._instances:
        continue
    if _port_in_use(port):
        continue
    self._reserved_ports.add(port)
    return port
raise RuntimeError("No free debug port found")
```

Port-in-use check for WSL:
```
def _port_in_use(port: int) -> bool:
    """Check via curl.exe if anything is listening on this Windows port."""
    # curl.exe runs in Windows namespace — most reliable for WSL2
    if _detect_wsl2():
        curl_exe = _get_curl_exe()  # from cdp_client's pattern
        if curl_exe:
            try:
                r = subprocess.run(
                    [curl_exe, "-s", "--connect-timeout", "1",
                     f"http://localhost:{port}/"],
                    capture_output=True, text=True, timeout=3,
                )
                # connectionRefused = nothing listening = port free
                return r.returncode == 0
            except (subprocess.TimeoutExpired, OSError):
                return False

    # Fallback: Python socket (works for native, may work for WSL2 mirrored)
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.settimeout(1)
        sock.connect(("localhost", port))
        sock.close()
        return True  # something is listening
    except (ConnectionRefusedError, OSError):
        return False
```

### 3.3 `launch(config)` → ChromeInstance

**Purpose**: Launch a Chrome instance and return the tracked instance.

**Flow**:
```
1. Validate config
2. Get windows_user (from detection.get_windows_user())
3. If config.kill_existing:
   → kill_all()  (taskkill /F /IM chrome.exe)
   → wait 2 seconds
4. Allocate port:
   → config.port > 0 → check it's free, reserve it
   → config.port == 0 → find_free_debug_port(), reserves it
5. Prepare profile dir:
   → _make_instance_debug_dir(windows_user, port)
   → Returns e.g. "C:\Users\Jean\AppData\Local\Google\ChromeDebug-9223"
6. Build landing URL:
   → If config.email: append #chrome-signin&email=<email>
7. Build Chrome arguments list:
   → --remote-debugging-port=<port>
   → --user-data-dir=<profile_dir>
   → --no-first-run (if config.no_first_run)
   → --headless (if config.headless)
   → <landing_url> (if config.landing_url)
8. Build PS1 script:
   → $proc = Start-Process "<chrome_exe>" -ArgumentList "<args>" -PassThru
   → Write-Host "PID:$($proc.Id)"
   → (NO taskkill — that was step 3 only if kill_existing)
   → (NO Start-Sleep — not needed when not killing first)
9. Write PS1 to temp file on C:\ (Windows-accessible)
10. Execute PS1 via subprocess.run (NOT Popen — we need to read stdout for PID)
    → Read stdout → parse "PID:<number>"
11. Construct ChromeInstance with pid, port, profile_dir, email, etc.
12. Wait for ready: _wait_for_ready(instance)
13. Release port reservation, register instance
14. Return instance
```

**PID Capture — PS1 Script**:
```powershell
$proc = Start-Process "C:\Program Files\Google\Chrome\Application\chrome.exe" `
    -ArgumentList "--remote-debugging-port=9223","--user-data-dir=C:\Users\Jean\AppData\Local\Google\ChromeDebug-9223","--no-first-run" `
    -PassThru
Write-Host "PID:$($proc.Id)"
```

Using `subprocess.run()` (not Popen) with `capture_output=True` to read stdout.
The PS1 script terminates immediately after Start-Process returns (Chrome runs
independently). So subprocess.run() completes quickly.

**Profile Directory Naming**:
Each instance gets its own dir: `ChromeDebug-{port}`
- Port 9222 → `C:\Users\Jean\AppData\Local\Google\ChromeDebug-9222`
- Port 9223 → `C:\Users\Jean\AppData\Local\Google\ChromeDebug-9223`
- Etc.

This avoids conflicts between simultaneous instances.

### 3.4 `_wait_for_ready(instance, timeout, poll_interval)` → bool

**Purpose**: Poll the CDP endpoint until Chrome responds to `/json/version`.

**Mechanism**: Same as cdp_client's approach, but targeting a specific port.
Must handle WSL2 networking (curl.exe bridge).

```
endpoint = f"http://localhost:{instance.port}"
deadline = time.time() + timeout  (default 15 seconds)

while time.time() < deadline:
    if _cdp_check(instance.port):
        instance.endpoint = endpoint
        instance.ready = True
        return True
    time.sleep(poll_interval)  (default 0.5 seconds)

return False
```

**_cdp_check(port)**: Uses the same curl.exe bridge pattern from cdp_client:
```python
def _cdp_check(port: int) -> bool:
    """Check if CDP is responding on the given port."""
    url = f"http://localhost:{port}/json/version"

    if _detect_wsl2():
        curl_exe = _get_curl_exe()
        if curl_exe:
            try:
                r = subprocess.run(
                    [curl_exe, "-s", "--connect-timeout", "2", url],
                    capture_output=True, text=True, timeout=4,
                )
                if r.returncode == 0 and r.stdout.strip():
                    return True
            except (subprocess.TimeoutExpired, OSError):
                pass
        return False

    # Fallback for non-WSL2
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError):
        return False
```

**Why not reuse cdp_client.is_available()?**: Because `is_available()` uses
the global `_endpoint` singleton. We need to check a SPECIFIC port. We don't
want to mutate the global endpoint just to check. The launcher has its own
port-specific check.

**WSL2 endpoint discovery complication**: Chrome binds to `127.0.0.1` on
Windows. From WSL2, this may be reachable via:
- `localhost` (if mirrored networking)
- The gateway IP (NAT mode)
- resolv.conf nameserver IP

For the endpoint stored in `ChromeInstance.endpoint`, we need the HOST that
WSL Python can actually reach. The curl.exe check confirms Chrome is running,
but the `ws://` URLs in Chrome's `/json` response will say `ws://127.0.0.1:port/...`
— which may not be directly reachable from WSL2.

**Solution**: After Chrome is ready, do what `try_discover_endpoint()` does —
try localhost, then resolv.conf IP, then gateway IP — but for our specific port.
Store whichever host works in `instance.endpoint`.

### 3.5 `kill_instance(instance)` → bool

**Purpose**: Kill a specific Chrome instance by PID.

```python
def kill_instance(self, instance: ChromeInstance) -> bool:
    """Kill a specific Chrome instance by its Windows PID."""
    if not instance.pid:
        return False
    try:
        r = subprocess.run(
            ["taskkill.exe", "/F", "/PID", str(instance.pid)],
            capture_output=True, text=True, timeout=10,
        )
        killed = r.returncode == 0
        if killed:
            with self._lock:
                self._instances.pop(instance.port, None)
            logger.info("Killed Chrome instance PID %d on port %d",
                        instance.pid, instance.port)
        return killed
    except Exception as exc:
        logger.warning("Failed to kill Chrome PID %d: %s", instance.pid, exc)
        return False
```

### 3.6 `kill_all()` → bool

**Purpose**: Kill ALL Chrome processes (nuclear option). Same as current `kill_chrome()`.

```python
def kill_all(self) -> bool:
    """Kill all Chrome processes via taskkill /IM."""
    try:
        r = subprocess.run(
            ["taskkill.exe", "/F", "/IM", "chrome.exe"],
            capture_output=True, text=True, timeout=10,
        )
        with self._lock:
            self._instances.clear()
            self._reserved_ports.clear()
        killed = r.returncode == 0 or "not found" in r.stderr.lower()
        return killed
    except Exception as exc:
        logger.warning("Failed to kill all Chrome: %s", exc)
        return False
```

### 3.7 `list_instances()` → list[ChromeInstance]

Returns all tracked instances.

### 3.8 `get_instance(port)` → ChromeInstance | None

Returns the instance on a given port, or None.

### 3.9 `cleanup()`

Called on server shutdown. Kills all managed instances.
Can be registered as an atexit handler.

---

## 4. Helper Functions (module-level)

### 4.1 `_detect_wsl2()` — WSL2 detection

**Decision**: Reuse from cdp_client? Or use `detection.is_wsl()`?

`detection.is_wsl()` (extracted from tab_mesh) checks `/proc/version` for
"microsoft" — same test as cdp_client's `_detect_wsl2()`. Use `detection.is_wsl()`
since it's in the chrome domain now.

### 4.2 `_get_curl_exe()` — Find Windows curl.exe

Currently in cdp_client. We need the same for the launcher's port check
and ready-state polling. Options:
- A) Import from cdp_client (creates a dependency on the UI layer from core — BAD)
- B) Duplicate the function in launcher.py
- C) Move it to detection.py as a shared utility

**Decision**: Option C — `detection.get_curl_exe()`. It's an environment
detection function. Both cdp_client and launcher need it. cdp_client can
import from detection in the future, but for now we add it to detection.py
as new code.

Let me check what `_get_curl_exe()` does:

From cdp_client.py (need to trace):
- Likely uses `shutil.which("curl.exe")` or checks known Windows paths

### 4.3 `_make_instance_debug_dir(windows_user, port)` → str

Returns the Windows path for this instance's debug dir:
```python
def _make_instance_debug_dir(windows_user: str, port: int) -> str:
    """Return a per-instance debug dir path (Windows format).

    Each port gets its own directory to avoid profile locking conflicts.
    """
    return f"C:\\Users\\{windows_user}\\AppData\\Local\\Google\\ChromeDebug-{port}"
```

---

## 5. Integration — Tab_mesh Route Delegation

### 5.1 `restart_chrome()` route

After Chunk 2a, this route delegates to the launcher:

```python
@tab_mesh_bp.route("/tab-mesh/restart-chrome", methods=["POST"])
def restart_chrome():
    # ... same validation ...
    config = ChromeLaunchConfig(
        port=data.get("port", 9222),
        profile_type="email" if email else "temp",
        email=email,
        kill_existing=True,  # restart = kill first
        landing_url=return_url,
    )
    instance = chrome_launcher.launch(config)
    return jsonify({
        "success": instance.ready,
        "launch_scheduled": True,
        "email": instance.email,
    })
```

**Behavior change**: The current route is fire-and-forget (doesn't wait for
Chrome to start). With the launcher, it WAITS for CDP ready state. This is
strictly better — the frontend knows Chrome is actually running when it gets
the response.

But we need to be careful: the current PS1 script sleeps 2 seconds before
killing Chrome. This is because the HTTP response needs to reach the browser
before Chrome dies. If we make restart_chrome() synchronous and it kills
Chrome immediately, the response may never reach the frontend.

**Solution**: The `kill_existing=True` path in `launch()` still uses the
same deferred approach: write the PS1 script with `Start-Sleep` before
`taskkill`, and `Start-Sleep` after `taskkill` before launching. The
`_wait_for_ready()` poll absorbs the total startup time. The HTTP response
returns AFTER Chrome is confirmed running.

The frontend ALREADY handles this — it expects to be killed and has
retry/reconnect logic via the sign-in flow.

### 5.2 `kill_chrome()` route

```python
@tab_mesh_bp.route("/tab-mesh/kill-chrome", methods=["POST"])
def kill_chrome():
    if not _is_wsl():
        return jsonify({"killed": False, "message": "Not running under WSL"}), 400
    killed = chrome_launcher.kill_all()
    return jsonify({
        "killed": killed,
        "message": (
            "All Chrome processes terminated." if killed
            else "Chrome was not running."
        ),
    })
```

---

## 6. Module-Level Singleton

The launcher should be a module-level singleton (like cdp_client's global
endpoint). Multiple callers (tab_mesh routes, execution plans, CDP test)
all share the same instance registry.

```python
# src/core/services/chrome/launcher.py — module level

_launcher: ChromeLauncher | None = None

def get_launcher() -> ChromeLauncher:
    """Get or create the module-level launcher singleton."""
    global _launcher
    if _launcher is None:
        _launcher = ChromeLauncher()
    return _launcher
```

---

## 7. Dependencies to Add to detection.py

### 7.1 `get_curl_exe()` — Find curl.exe for WSL2 bridge

Need to trace cdp_client's `_get_curl_exe()` to copy the exact logic.

### 7.2 `detect_environment()` → dict

Consolidated one-call diagnostic:
```python
def detect_environment() -> dict:
    """Return a dict describing the current environment."""
    return {
        "wsl": is_wsl(),
        "windows_user": get_windows_user(),
        "chrome_version": get_chrome_version(),
        "powershell_available": bool(shutil.which("powershell.exe")),
        "curl_exe": get_curl_exe(),
    }
```

---

## 8. Files Modified/Created

| File | Action | What Changes |
|------|--------|-------------|
| `src/core/services/chrome/launcher.py` | **CREATE** | ChromeLauncher class, ChromeLaunchConfig, ChromeInstance, port allocation, launch, kill, ready-state polling |
| `src/core/services/chrome/detection.py` | **MODIFY** | Add `get_curl_exe()`, `detect_environment()` |
| `src/ui/web/routes/tab_mesh/__init__.py` | **MODIFY** | `restart_chrome()` and `kill_chrome()` delegate to launcher |

---

## 9. Risk Analysis

| Risk | Mitigation |
|------|-----------|
| PID capture via PowerShell `-PassThru` may not work as expected | Test with actual Chrome launch on target system |
| `subprocess.run()` for PS1 blocks the Flask request thread | Acceptable — launch + ready check takes ~5-10 seconds max. Consider threading later if needed. |
| `curl.exe` bridge for port check adds latency | Each check is ~1 second. Port scan of 8 ports = ~8 seconds worst case. Acceptable. |
| Chrome may spawn multiple processes, killing parent PID may leave orphans | Chrome's parent process manages children. Killing parent should cascade. Verify on Windows. |
| `restart_chrome()` behavior change (now synchronous) | Frontend already handles reconnect. Actually better UX — response confirms Chrome is ready. |
| Profile dir `ChromeDebug-{port}` accumulates on disk | Not addressed in this chunk. Cleanup strategy needed later. |

---

## 10. Verification Plan

### 10.1 Module imports
```python
from src.core.services.chrome.launcher import (
    ChromeLauncher, ChromeLaunchConfig, ChromeInstance, get_launcher,
)
```

### 10.2 Port allocation (unit-testable)
```python
launcher = ChromeLauncher()
port = launcher.find_free_debug_port()
assert 9222 <= port <= 9230
assert port in launcher._reserved_ports
```

### 10.3 Tab_mesh routes still work
- `/tab-mesh/kill-chrome` → returns same response shape
- `/tab-mesh/restart-chrome` → returns same response shape (now also waits for ready)
- `/tab-mesh/cdp-status` → unchanged
- All other tab_mesh routes → unchanged

### 10.4 Multi-instance (manual test)
- Launch instance on auto-allocated port
- Verify CDP responds on that port
- Launch second instance on different port
- Verify both respond
- Kill instance 1 by PID → instance 2 still alive
- Kill all → both dead

---

## 11. Implementation Order

1. Add `get_curl_exe()` to `detection.py` (trace from cdp_client first)
2. Create `launcher.py` with dataclasses (`ChromeLaunchConfig`, `ChromeInstance`)
3. Add `ChromeLauncher.__init__()` and `find_free_debug_port()`
4. Add `_port_in_use()` and `_cdp_check()` helper functions
5. Add `launch()` — the PS1 script builder + PID capture
6. Add `_wait_for_ready()` — CDP polling with WSL2 bridge
7. Add `kill_instance()`, `kill_all()`, `list_instances()`, `get_instance()`, `cleanup()`
8. Add `get_launcher()` singleton
9. Update tab_mesh `kill_chrome()` to delegate
10. Update tab_mesh `restart_chrome()` to delegate
11. Verify all routes

Each step is one change, verified before moving to the next.
