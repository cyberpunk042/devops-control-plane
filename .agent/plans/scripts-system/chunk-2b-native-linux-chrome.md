# Chunk 2b: Native Linux Chrome Path + Install Plan Integration

> **Status**: Planning
> **Created**: 2026-03-09
> **Parent**: `scripts-system-M7-plans.md` → Chunk 2
> **Depends on**: Chunk 2a (ChromeLauncher WSL→Win) ✅ DONE

---

## 0. Why This Chunk Exists

Chunk 2a built the ChromeLauncher for the WSL→Windows path — which is the current
production path. But the app is always Linux-based: it may run in WSL, a native
Linux desktop, a Docker container, or a headless CI server. In all these cases,
Chrome for Linux (or Chromium) is the target, not Windows Chrome.

This chunk needs to handle the full lifecycle:
1. **Detecting** whether Chrome/Chromium is installed on native Linux
2. **Offering to install** Chrome via the existing `install_plan` pattern if missing
3. **Detecting launch failures** at runtime and surfacing remediation notices
4. **Streaming messages** to the frontend when Chrome is needed but unavailable
5. **Creating notifications** via the notification system with actionable remediation
6. **Actually launching** Chrome on native Linux when it IS available

This is NOT just "add an else branch for Linux launch." This is the install
detection → remediation → notification → launch pipeline done right.

---

## 1. What Exists Today — Traced from Source

### 1.1 Current launcher.py (Chunk 2a)

The launcher currently has:
- `launch()` — raises `RuntimeError("ChromeLauncher: WSL environment required")`
  when `not is_wsl()`. THIS IS THE GATE we need to open for native Linux.
- `_port_in_use(port)` — has a Python socket fallback for non-WSL. This already
  works for native Linux.
- `_cdp_responding(port)` — has a urllib fallback for non-WSL. This already works
  for native Linux.
- `kill_instance()` — uses `taskkill.exe`. MUST switch to `kill -9 <pid>` on Linux.
- `kill_all()` — uses `taskkill.exe /IM chrome.exe`. MUST switch to
  `pkill -9 chrome` or `killall chrome` on Linux.

### 1.2 Tool Install System (install_plan pattern)

The tool_install system provides:

**L0 Data**: Recipe dicts in `data/recipes/` — define how to install tools per
package manager (apt, dnf, brew, etc.). Each recipe has `install`, `needs_sudo`,
`verify`, and `update` keys. Example: `git`, `curl` in `core/system.py`.

**L2 Resolver**: `resolve_install_plan(tool, system_profile)` — takes a tool ID
and OS profile, walks the dependency tree, selects install method based on
available package manager, produces an ordered step list.

**L3 Execution**: `stream_step_execution()` — runs plan steps, yields SSE events
(`step_start`, `log`, `step_done`, `step_failed`, `done`), handles remediation
analysis on failure.

**L3 Detection**: `_analyse_install_failure()` — when a step fails, analyzes stderr
and produces remediation options (`retry`, `remediate`, `use_source`, etc.).

**Orchestrator**: `install_and_verify()` — convenience function that generates
a plan and executes it.

There is NO Chrome recipe today. We need to create one.

### 1.3 Notification System

`src/core/services/notifications.py` provides:
- `create_notification(project_root, notif_type=..., title=..., message=...,
  meta=..., dedup=True)` — persists to `.state/notifications.json`, publishes
  SSE event `notification:new` via event bus.
- Deduplication by `notif_type` — prevents spamming.
- Meta dict for action routing (e.g. `{"action_tab": "debugging"}`).

The frontend already handles:
- SSE event `notification:new` → renders notification in real-time
- Notification badge counter update
- Click-to-navigate via meta `action_tab` / `action_hash`

The existing `suggest_cdp()` route is the exact pattern we should follow:
it creates a notification when a capability is missing, with a meta dict
pointing the user to the right tab/panel for remediation.

### 1.4 CDP Test Replayer's install_plan

`replayer.py` line 1385 shows how a runtime dependency check produces an
`install_plan` response embedded in the error details:
```python
"install_plan": {
    "tool": "pytesseract",
    "steps": [d for d in missing_deps],
    "can_auto_install": all(d["type"] == "pip" for d in missing_deps),
}
```
This is the pattern for runtime dep detection — check if the tool is present,
and if not, return structured install guidance.

### 1.5 Core recipes `__init__.py`

The recipe registry pattern: each category has a `_FOO_RECIPES` dict merged
into `_CORE_RECIPES`. To add Chrome, we need a Chrome-specific recipe (or
add it to the `specialized/` or create a new `browser/` category).

---

## 2. Scope — Every Component That Needs to Change

### 2.1 New: Chrome/Chromium Recipe (`data/recipes/specialized/browser.py`)

A proper install recipe for Chrome and Chromium, following the exact pattern of
existing recipes:

```python
_BROWSER_RECIPES: dict[str, dict] = {
    "google-chrome": {
        "label": "Google Chrome",
        "category": "browser",
        "cli": "google-chrome-stable",
        "install": {
            "apt": [
                "bash", "-c",
                "wget -q -O /tmp/google-chrome.deb "
                "https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb "
                "&& apt-get install -y /tmp/google-chrome.deb "
                "&& rm /tmp/google-chrome.deb",
            ],
            "dnf": [
                "bash", "-c",
                "dnf install -y "
                "https://dl.google.com/linux/direct/google-chrome-stable_current_x86_64.rpm",
            ],
            "_default": [
                "bash", "-c",
                "wget -q -O /tmp/google-chrome.deb "
                "https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb "
                "&& dpkg -i /tmp/google-chrome.deb "
                "&& apt-get -f install -y "
                "&& rm /tmp/google-chrome.deb",
            ],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "_default": True,
        },
        "requires": {
            "binaries": ["wget"],
        },
        "verify": ["google-chrome-stable", "--version"],
        "update": {
            "apt": ["apt-get", "install", "--only-upgrade", "-y", "google-chrome-stable"],
            "dnf": ["dnf", "upgrade", "-y", "google-chrome-stable"],
        },
    },
    "chromium": {
        "label": "Chromium (open-source)",
        "category": "browser",
        "cli": "chromium-browser",
        "install": {
            "apt":    ["apt-get", "install", "-y", "chromium-browser"],
            "dnf":    ["dnf", "install", "-y", "chromium"],
            "apk":    ["apk", "add", "chromium"],
            "pacman": ["pacman", "-S", "--noconfirm", "chromium"],
            "zypper": ["zypper", "install", "-y", "chromium"],
            "brew":   ["brew", "install", "--cask", "chromium"],
            "snap":   ["snap", "install", "chromium"],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "apk": True,
            "pacman": True, "zypper": True, "brew": False,
            "snap": True,
        },
        "verify": ["chromium-browser", "--version"],
        "update": {
            "apt": ["apt-get", "install", "--only-upgrade", "-y", "chromium-browser"],
            "dnf": ["dnf", "upgrade", "-y", "chromium"],
            "apk": ["apk", "upgrade", "chromium"],
            "pacman": ["pacman", "-S", "--noconfirm", "chromium"],
            "zypper": ["zypper", "update", "-y", "chromium"],
        },
    },
}
```

This recipe needs to be registered in the specialized `__init__.py` and merged
into `TOOL_RECIPES`.

### 2.2 New: Chrome availability detection in `detection.py`

```python
def find_chrome_linux() -> str | None:
    """Find Chrome or Chromium binary on native Linux.

    Search order (same priority as most tools):
    1. google-chrome-stable  (Google Chrome official)
    2. google-chrome         (some distros use this name)
    3. chromium-browser      (Ubuntu/Debian Chromium)
    4. chromium              (Fedora/Arch Chromium)

    Returns the full path to the first found binary, or None.
    """

def get_chrome_version_linux(chrome_path: str) -> str | None:
    """Get Chrome/Chromium version by running it with --version."""
```

### 2.3 Modified: `launcher.py` — Native Linux launch path

The `launch()` method must support native Linux:

**Environment routing in `launch()`**:
```
if is_wsl():
    → existing WSL→Windows path (PS1 + Start-Process)
else:
    → new native Linux path (subprocess.Popen + direct launch)
```

**Native Linux launch**:
- No PowerShell — direct subprocess call
- Chrome binary from `find_chrome_linux()` or config.chrome_exe
- PID capture via `subprocess.Popen()` → `.pid`
- Profile dir: `~/.config/google-chrome-debug-{port}/` or
  `/tmp/chrome-debug-{port}/`
- Kill via `os.kill(pid, signal.SIGTERM)` then `SIGKILL` fallback
- Port check via Python socket (native, no curl.exe bridge needed)
- CDP check via urllib (native, no curl.exe bridge needed)

**kill_instance() and kill_all() must be environment-aware**:
- WSL: `taskkill.exe /F /PID <pid>` and `taskkill.exe /F /IM chrome.exe`
- Linux: `os.kill(pid, signal.SIGTERM)` and
  `subprocess.run(["pkill", "-9", "-f", "chrome"])` or
  `subprocess.run(["killall", "-9", "google-chrome-stable"])`

### 2.4 New: Chrome availability gate — `require_chrome()`

A function that acts as a precheck before any operation that needs Chrome.
This integrates with the install_plan pattern:

```python
def require_chrome() -> ChromeAvailability:
    """Check if Chrome is available and return availability details.

    Returns a structured response with:
    - available: bool
    - chrome_path: str | None  (path to binary)
    - chrome_version: str | None
    - environment: "wsl" | "linux" | "unknown"
    - install_plan: dict | None  (if not available, how to install)
    - error: str | None
    """
```

When Chrome is NOT available:
1. Generate an install plan via `resolve_install_plan("google-chrome", system_profile)`
2. Return it in the response so the frontend can offer installation
3. Create a notification with remediation guidance

### 2.5 New: Launch failure handler — notification pipeline

When `launch()` fails because Chrome isn't found:
1. Detect the specific failure (binary not found vs. display not available
   vs. port conflict vs. crash)
2. Produce a structured error with remediation options
3. Create a persistent notification via `create_notification()`
4. Return the error upstream so the route handler can stream it to the frontend

**Failure taxonomy**:

| Failure | Detection | Remediation |
|---------|-----------|-------------|
| Chrome not installed | `find_chrome_linux()` returns None | install_plan for "google-chrome" |
| Chrome binary found but wrong arch | `--version` fails with exec format error | install_plan for correct arch |
| No display available (`$DISPLAY` unset) | check `DISPLAY` env var, `WAYLAND_DISPLAY`, or `--headless` override | suggest `--headless` or install xvfb |
| Port already in use | `_port_in_use()` returns True | suggest different port or kill existing |
| Chrome crashes on launch | process exits immediately (exit code > 0) | check Chrome stderr, suggest `--no-sandbox` for Docker |
| CDP doesn't respond after timeout | `_wait_for_ready()` returns False | check firewall, port binding, Chrome logs |

### 2.6 Modified: Tab mesh routes — notification integration

When `restart_chrome()` or `kill_chrome()` fails due to Chrome not being
available, the route should:
1. Create a notification with the install plan
2. Return a response that includes the failure reason AND the install guidance

The `suggest_cdp()` pattern shows exactly how to do this:
```python
from src.core.services.notifications import create_notification

result = create_notification(
    project_root,
    notif_type="chrome_missing",
    title="Chrome Not Installed",
    message=(
        "Chrome is required for browser automation features. "
        "You can install it from the audit panel → Tool Install."
    ),
    meta={
        "action_tab": "audit",
        "action_hash": "#audit/tool-install/google-chrome",
        "install_plan": {"tool": "google-chrome"},
    },
    dedup=True,
)
```

### 2.7 New/Modified: Display detection in `detection.py`

```python
def has_display() -> bool:
    """Check if a graphical display is available.

    Checks DISPLAY (X11), WAYLAND_DISPLAY (Wayland), and
    MIR_SOCKET (Mir) environment variables.

    Returns False in headless/Docker/CI environments.
    """

def is_docker() -> bool:
    """Check if running inside a Docker container.

    Chrome in Docker often needs --no-sandbox in addition to
    --headless due to seccomp restrictions.
    """
```

---

## 3. Architecture — Full Flow

### 3.1 Happy Path: Chrome is installed

```
User action → launcher.launch(config)
  → detect environment: native Linux
  → find_chrome_linux() → "/usr/bin/google-chrome-stable"
  → has_display()? → yes
  → allocate port (9222 or auto)
  → build Chrome args: --remote-debugging-port, --user-data-dir, etc.
  → subprocess.Popen([chrome_path] + args)
  → capture pid from Popen.pid
  → _wait_for_ready(instance) → polls /json/version via urllib
  → return ChromeInstance(ready=True, pid=..., port=..., endpoint=...)
```

### 3.2 Unhappy Path: Chrome is NOT installed

```
User action → launcher.launch(config)
  → detect environment: native Linux
  → find_chrome_linux() → None (not installed)
  → raise ChromeNotInstalled(
        message="Chrome is not installed",
        install_plan={
            "tool": "google-chrome",
            "available_methods": ["apt", "_default"],
            "can_auto_install": False,  (needs sudo)
        },
    )

Route handler catches ChromeNotInstalled:
  → create_notification(
        notif_type="chrome_missing",
        title="Chrome Required",
        message="...",
        meta={"install_plan": {...}},
    )
  → return JSON response with error + install_plan
  → SSE event "notification:new" fires → frontend shows notification

User clicks notification → navigates to audit panel → tool install → "google-chrome"
  → resolve_install_plan("google-chrome", system_profile) → step list
  → execute plan via streaming SSE → Chrome installed
  → retry original action → success
```

### 3.3 Bypass Path: User tries to use a feature requiring Chrome without installing

This is the "detect failure and lift/stream a message" scenario:

```
User clicks "Record Test" in CDP Test panel
  → POST /api/cdp-test/record → handler needs Chrome
  → calls require_chrome() → returns ChromeAvailability(available=False)
  → create_notification(...)  (deduped — only first time)
  → return 503 JSON:
      {
        "error": "Chrome is not installed",
        "remediation": {
            "type": "tool_missing",
            "tool": "google-chrome",
            "install_plan": {...},
            "notification_id": "notif-abc123",
            "action": "Navigate to Audit → Tool Install"
        }
      }
  → Frontend: shows toast/banner with install action
  → SSE: notification:new event updates the notification bell

User installs Chrome → retries → works.
```

---

## 4. Error Types — Custom Exceptions

The launcher needs dedicated exception types so callers can distinguish
failure modes and provide appropriate remediation:

```python
class ChromeLaunchError(RuntimeError):
    """Base error for Chrome launch failures."""
    def __init__(self, message: str, *, remediation: dict | None = None):
        super().__init__(message)
        self.remediation = remediation or {}


class ChromeNotInstalled(ChromeLaunchError):
    """Chrome binary not found on this system."""
    def __init__(self, *, install_plan: dict | None = None):
        super().__init__(
            "Chrome is not installed. Install Google Chrome or Chromium to continue.",
            remediation={
                "type": "tool_missing",
                "tool": "google-chrome",
                "install_plan": install_plan,
                "suggestion": "Install via: sudo apt install google-chrome-stable",
            },
        )
        self.install_plan = install_plan


class ChromeNoDisplay(ChromeLaunchError):
    """No graphical display available for headed Chrome."""
    def __init__(self):
        super().__init__(
            "No display available. Set headless=True or configure a display.",
            remediation={
                "type": "missing_resource",
                "resource": "display",
                "suggestions": [
                    "Use headless mode (config.headless=True)",
                    "Install xvfb: sudo apt install xvfb",
                    "Run with: xvfb-run <command>",
                    "Set DISPLAY environment variable",
                ],
            },
        )


class ChromePortConflict(ChromeLaunchError):
    """All ports in the debug range are occupied."""
    pass


class ChromeStartupFailed(ChromeLaunchError):
    """Chrome process started but exited or CDP never responded."""
    def __init__(self, message: str, *, stderr: str = "", exit_code: int = 0):
        super().__init__(message)
        self.stderr = stderr
        self.exit_code = exit_code
```

---

## 5. Files Modified/Created

| File | Action | What Changes |
|------|--------|-------------|
| `src/core/services/chrome/detection.py` | **MODIFY** | Add `find_chrome_linux()`, `get_chrome_version_linux()`, `has_display()`, `is_docker()`, `detect_environment()` |
| `src/core/services/chrome/launcher.py` | **MODIFY** | Add native Linux launch path in `launch()`, environment-aware `kill_instance()`/`kill_all()`, custom exceptions, `require_chrome()` |
| `src/core/services/tool_install/data/recipes/specialized/browser.py` | **CREATE** | Chrome and Chromium install recipes |
| `src/core/services/tool_install/data/recipes/specialized/__init__.py` | **MODIFY** | Register browser recipes |
| `src/ui/web/routes/tab_mesh/__init__.py` | **MODIFY** | Add ChromeNotInstalled handling + notification in `restart_chrome()` |

---

## 6. Implementation Order

Each step is ONE change, verified before moving to the next.

### Step 1: `find_chrome_linux()` in detection.py

Add the function that searches for Chrome/Chromium binaries on native Linux.
Verify: import and call it.

### Step 2: `get_chrome_version_linux()` in detection.py

Add the function that runs `<chrome> --version` and parses the output.
Verify: call with the found binary.

### Step 3: `has_display()` in detection.py

Add display availability check (DISPLAY, WAYLAND_DISPLAY).
Verify: call it — should return True if X11/Wayland is running.

### Step 4: `is_docker()` in detection.py

Add Docker container detection.
Verify: call it — should return False in WSL.

### Step 5: `detect_environment()` in detection.py

Consolidated environment diagnostic that combines all detection functions.
Verify: call it, inspect the full dict.

### Step 6: Custom exceptions in launcher.py

Add `ChromeLaunchError`, `ChromeNotInstalled`, `ChromeNoDisplay`,
`ChromePortConflict`, `ChromeStartupFailed`.
Verify: import all exceptions.

### Step 7: Environment-aware `kill_instance()` and `kill_all()`

Modify the methods to use `os.kill()` / `pkill` on Linux vs `taskkill.exe` on WSL.
Verify: import and check methods exist. (Not live-testable without running Chrome.)

### Step 8: Native Linux `launch()` path

Add the `else` branch in `launch()` for `not is_wsl()`:
- Find Chrome binary via `find_chrome_linux()` or config.chrome_exe
- Check display availability (unless headless)
- Build profile dir for Linux
- Launch via `subprocess.Popen()`
- Capture PID directly from Popen
- Wait for CDP ready via urllib
Verify: import and check method. (Live test if Chrome is available.)

### Step 9: `require_chrome()` function

Add the precheck function that returns structured availability info with
install plan integration.
Verify: call it and inspect response.

### Step 10: Chrome install recipe

Create `browser.py` with google-chrome and chromium recipes.
Register in `specialized/__init__.py`.
Verify: `resolve_install_plan("google-chrome", system_profile)` produces a plan.

### Step 11: Notification integration in tab_mesh

Update `restart_chrome()` to catch `ChromeNotInstalled` and create a
notification with install guidance.
Verify: route still works in WSL mode (no change). Error handling verified
with simulated failure.

---

## 7. Risk Analysis

| Risk | Impact | Mitigation |
|------|--------|------------|
| Chrome binary names vary across distros | Launch fails on uncommon distros | Search 4 common names, allow override via config.chrome_exe |
| No display in headless environments | Chrome crashes silently | Precheck `has_display()`, auto-suggest headless mode |
| Docker --no-sandbox requirement | Chrome refuses to start | Detect Docker, auto-add --no-sandbox |
| Chrome recipe needs testing on all PMs | Install may fail on some distros | Use `_default` fallback (wget .deb), test apt/dnf paths |
| Notification spam if Chrome is persistently missing | User annoyed | Use dedup=True (one active notification per type) |
| kill_all() with pkill may kill unrelated processes | Data loss in other Chrome windows | Use the exact process name from find_chrome_linux() |
| Profile dir cleanup in /tmp or ~/.config | Disk space accumulation | Document for Chunk 3 cleanup strategy |

---

## 8. Verification Matrix

| Scenario | Expected Result | How to Verify |
|----------|-----------------|---------------|
| WSL environment, Chrome on Windows | Existing behavior unchanged | `launcher.launch()` uses PS1 path |
| Native Linux, Chrome installed | Direct launch via subprocess | `launcher.launch()` returns ChromeInstance |
| Native Linux, Chrome NOT installed | ChromeNotInstalled exception with install_plan | `launcher.launch()` raises ChromeNotInstalled |
| Native Linux, no display, not headless | ChromeNoDisplay exception | `launcher.launch()` raises ChromeNoDisplay |
| Native Linux, no display, headless=True | Successful headless launch | `launcher.launch()` returns ChromeInstance |
| Docker, Chrome installed | Launch with --no-sandbox | Check Chrome args include --no-sandbox |
| `require_chrome()` when not installed | Returns install_plan | Call and inspect response |
| `resolve_install_plan("google-chrome", profile)` | Produces apt/dnf steps | Call and inspect plan |
| Notification on ChromeNotInstalled | notification:new SSE event | check .state/notifications.json |
| Notification dedup | Second failure doesn't create duplicate | Call twice, check count |
| `kill_instance()` on Linux | Uses SIGTERM/SIGKILL | Verify method routes to os.kill |
| `kill_all()` on Linux | Uses pkill | Verify method routes to pkill |

---

## 9. Out of Scope (Documented for Later)

- Profile cleanup strategy (Chunk 3)
- X11 forwarding setup for WSL (separate concern)
- Remote Chrome (connect to Chrome on a different machine)
- Puppeteer/Playwright integration
- Browser selection UI (choose between Chrome/Chromium)
- Chrome extension preloading
