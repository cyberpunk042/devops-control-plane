# Scripts System — M7: Execution Plans + Browser-Driven Execution

> **Status**: Planning — Iteration 1
> **Created**: 2026-03-09
> **Parent**: `scripts-system.md` (Overview & Architecture)
> **Depends on**: M1 (Framework), CDP Test infrastructure

---

## 0. Source of Truth — Verbatim

> "The execution plan will be able to execute in a driven GoogleAccountless browser headless or not based on the desire or even in the default tests script execution tab driven mode background or not. (same browser vs another browser and I said browserless but you can actually re-use an existing profile as much as you can chose a temporary profile, see all the options, we need it all. the advantages is that it doesn't require to put your default browser for the base CDP mode, you can do it into a fresh chrome because we can easily add debug on such another browser even if it mean that we need to use a different port because it is still used by the other instance) obviously we cannot reuse profile that are already existing and created without debugging but we just need to tell the user this limitation with this alternate CDP, we can also choose to run it inside WSL or windows when we detect such a system if the wsl doesn't have a good Xterm or X11 / xserver or such to send to windows the chrome window then it only allow headless."

> "Given the nature of the program we will: Build an entire system / integration for scripts, automated tests and execution plans of multiple type, fully_automated, semi_automated, interactive, ..."

---

## 1. What M7 Actually Is

M7 has two parts:

1. **Infrastructure Evolution** — Extract Chrome management from tab_mesh into its own domain. This is NOT a rewrite — it's pulling out code that doesn't belong in tab_mesh and giving it a proper home. Tab_mesh stays as the tab focus/switching system. Chrome instance management becomes its own service.

2. **Execution Plan Model** — The composition layer that lets you chain scripts AND browser automation steps into ordered, repeatable plans.

The infrastructure evolution is PREREQUISITE to the execution plan model. You can't compose browser steps into plans if Chrome management is buried inside a Flask route file.

---

## 2. Infrastructure Evolution — The Chrome Domain

### 2.1 Why

`tab_mesh/__init__.py` is **1,172 lines** serving two unrelated domains:

| Responsibility | What | Lines (approx) |
|---------------|------|----------------|
| **Chrome Management** | Profile reading, profile cloning, Chrome version, Chrome launching, kill/restart, WSL detection, path helpers, shortcut management, diagnostics, remediation, sign-in trigger | ~700 lines |
| **Tab Meshing** | Tab focus, tab discovery, CDP status, notification suggestion | ~200 lines |
| Routes + glue | Blueprint, imports, shared helpers | ~270 lines |

Chrome management is 60% of the file but 0% of tab meshing's domain.

### 2.2 Current Inventory — What Exists in tab_mesh

Every function that deals with Chrome (not tabs):

| Function | What it does | Lines | Domain |
|----------|-------------|-------|--------|
| `_is_wsl()` | Detects WSL environment | 30–37 | Environment detection |
| `_get_windows_user()` | Gets Windows username from WSL | 40–54 | Environment detection |
| `_chrome_data_dir()` | WSL path to Chrome User Data | 57–59 | Path helpers |
| `_chrome_data_dir_win()` | Windows path to Chrome User Data | 62–64 | Path helpers |
| `_chrome_debug_data_dir_win()` | Separate user-data-dir for debugging (Chrome 136+ fix) | 67–75 | Path helpers |
| `_read_chrome_profiles()` | Reads `Local State` → `[{dir, name, email}]` | 78–101 | Profile management |
| `_shortcut_locations()` | Known Chrome shortcut WSL paths | 104–121 | Shortcut management |
| `_backup_shortcut_locations()` | "Chrome - OLD" backup paths | 129–139 | Shortcut management |
| `_wsl_to_win_path()` | `/mnt/c/...` → `C:\...` | 142–146 | Path helpers |
| `_read_shortcut()` | Read .lnk target, args, icon via PowerShell | 149–196 | Shortcut management |
| `_get_chrome_version()` | Chrome version from executable dir | 199–215 | Environment detection |
| `_modify_shortcut()` | Add debug flags to .lnk, with UAC retry | 218–315 | Shortcut management |
| `_modify_shortcut_elevated()` | UAC-elevated shortcut modification | 318–382 | Shortcut management |
| `_clone_shortcut()` | Clone .lnk to new path | 385–447 | Shortcut management |
| `_clone_profile_to_debug_dir()` | Copy profile essentials to debug dir | 453–535 | Profile management |
| `kill_chrome()` route | Force-kill Chrome via `taskkill.exe` | 538–564 | Chrome lifecycle |
| `restart_chrome()` route | Kill + relaunch Chrome with debug flags, read email, schedule PS1 | 567–655 | Chrome lifecycle |
| `trigger_chrome_signin()` route | Open Google sign-in, fill email via CDP | 1059–1137 | Chrome auth |

What stays in tab_mesh (tab-focused):

| Function | What it does | Domain |
|----------|-------------|--------|
| `cdp_status()` route | Is CDP available? | Connection status |
| `focus_tab()` route | Activate a tab by target ID or URL | Tab management |
| `discover_target()` route | Find Chrome target ID via meshTabId | Tab management |
| `cdp_diagnose()` route | Full diagnostic (calls Chrome domain) | Setup wizard |
| `cdp_remediate()` route | Apply shortcut flags (calls Chrome domain) | Setup wizard |
| `suggest_cdp()` route | Create notification suggesting CDP setup | UX |

### 2.3 What Already Exists in cdp_client.py

The CDP client (`src/ui/web/cdp_client.py`, 1,390 lines) is the transport layer:

| Capability | Detail |
|-----------|--------|
| `set_endpoint(host, port)` | **Already supports custom port** — not hardcoded to 9222 |
| `try_discover_endpoint()` | Auto-discovers Chrome in WSL2 (localhost → resolv.conf → gateway) |
| `_detect_wsl2()` | WSL2 detection with `curl.exe` bridge |
| `CdpSession(ws_url)` | Persistent WebSocket session — **already takes any ws_url, any port** |
| `get_targets()` | List all browser tabs |
| `evaluate_js(ws_url, expr)` | Execute JS on a tab |
| `activate_target(id)` | Bring tab to foreground |
| `create_tab(url)` | Open new tab |
| `requires_user_data_dir()` | Chrome 136+ compatibility check |
| `parse_chrome_major_version()` | Version parsing |
| PowerShell bridge | Pre-warmed PS process for WSL2 WebSocket relay |

**Key insight**: `CdpSession` and the transport functions already work with ANY port. The singleton `_endpoint` is module-level, but the session takes a full `ws_url`. This means multi-instance support is mostly about launch + routing, not transport changes.

### 2.4 The Chrome Domain — New Service

```
src/core/services/chrome/
├── __init__.py              ← NO logic, re-exports only
├── detection.py             ← Environment: WSL, Windows user, X11/display, Chrome version
├── profiles.py              ← Profile reading, profile cloning, path helpers
├── launcher.py              ← Launch Chrome instances, port allocation, lifecycle
└── shortcuts.py             ← Shortcut reading/modification (Windows .lnk management)
```

#### `detection.py` — Environment Detection

Extracted from tab_mesh:
- `is_wsl()` — WSL detection
- `get_windows_user()` — Windows username
- `get_chrome_version()` — Chrome version string
- `requires_user_data_dir()` — Chrome 136+ check (currently in cdp_client)

New:
- `has_display()` — Check if headed mode is available
  - Native Linux: check `$DISPLAY` env var
  - WSL: check for X11/XServer/Xterm availability
  - Windows: always True
- `detect_environment()` → dict — One-call diagnostic: WSL, Windows user, Chrome version, display available, PowerShell available

#### `profiles.py` — Profile Management

Extracted from tab_mesh:
- `chrome_data_dir(windows_user)` — WSL path to Chrome User Data
- `chrome_data_dir_win(windows_user)` — Windows path
- `chrome_debug_data_dir_win(windows_user)` — Debug dir path
- `read_chrome_profiles(data_dir)` → `[{dir, name, email}]`
- `clone_profile_to_debug_dir(windows_user, profile_dir)` → status dict

New:
- `create_temp_profile_dir()` → path — Create a temporary profile dir for GoogleAccountless mode
- `get_profile_email(windows_user, profile_dir)` → str — Quick email lookup (subset of read_chrome_profiles)

#### `launcher.py` — Chrome Instance Lifecycle

This is where the new capability lives. Currently `restart_chrome()` kills ALL Chrome and relaunches. The launcher needs to support MULTIPLE simultaneous instances.

Extracted from tab_mesh:
- Chrome launch logic from `restart_chrome()` (the PS1 script generation)
- Kill Chrome (`taskkill.exe`)

New:
- `find_free_debug_port(start=9222)` → int — Scan ports to find one not in use
- `launch_chrome(config: ChromeLaunchConfig)` → `ChromeInstance` — Launch a Chrome instance
- `kill_instance(instance: ChromeInstance)` — Kill a specific Chrome instance (by PID, not `taskkill /IM` which kills ALL)
- `ChromeLaunchConfig` dataclass:
  ```python
  @dataclass
  class ChromeLaunchConfig:
      port: int = 0                   # 0 = auto-allocate
      profile_dir: str = ""           # "" = temp profile (GoogleAccountless)
      clone_from_profile: str = ""    # "Default" = clone user's profile
      headless: bool = False
      no_first_run: bool = True
      landing_url: str = ""           # URL to open on launch
      kill_existing: bool = False     # True = kill Chrome first (restart mode)
  ```
- `ChromeInstance` dataclass:
  ```python
  @dataclass
  class ChromeInstance:
      pid: int | None = None
      port: int = 0
      profile_dir: str = ""
      headless: bool = False
      endpoint: str = ""              # "http://host:port" — ready that cdp_client can use
      email: str = ""                 # From profile, if cloned
      started_at: str = ""
  ```

#### `shortcuts.py` — Windows Shortcut Management

Extracted from tab_mesh (these stay close to tab_mesh's setup wizard, but belong in the Chrome domain since they're about Chrome's launch configuration):
- `shortcut_locations(windows_user)` — Known Chrome shortcut WSL paths
- `backup_shortcut_locations(windows_user)` — "Chrome - OLD" paths
- `wsl_to_win_path(wsl_path)` — Path conversion
- `read_shortcut(wsl_path)` → dict — Read .lnk file
- `modify_shortcut(wsl_path, port, user_data_dir, icon)` — Add debug flags
- `modify_shortcut_elevated(...)` — UAC retry
- `clone_shortcut(...)` — Clone to backup

### 2.5 What Changes in tab_mesh

After extraction, `tab_mesh/__init__.py` becomes ~400 lines:

```python
# tab_mesh/__init__.py — Tab Mesh CDP routes
# Now CALLS into src.core.services.chrome for Chrome management

from src.core.services.chrome import detection, profiles, launcher, shortcuts

# Routes that STAY (tab-focused):
# /tab-mesh/cdp-status          — is CDP available?
# /tab-mesh/focus               — activate a tab
# /tab-mesh/discover-target     — find Chrome target ID
# /tab-mesh/suggest-cdp         — suggest CDP setup notification

# Routes that STAY but now delegate:
# /tab-mesh/cdp-diagnose        — calls detection + profiles + shortcuts
# /tab-mesh/cdp-remediate       — calls shortcuts
# /tab-mesh/kill-chrome          — calls launcher.kill_all_chrome()
# /tab-mesh/restart-chrome       — calls launcher.launch_chrome() + profiles
# /tab-mesh/trigger-chrome-signin — stays (it's a tab_mesh UX flow)
```

### 2.6 What Changes in cdp_client.py

Minimal changes:
- `requires_user_data_dir()` moves to `chrome/detection.py` (or stays with a thin wrapper — TBD)
- `parse_chrome_major_version()` moves to `chrome/detection.py`
- Everything else stays — cdp_client is the **transport**, not management

### 2.7 What Changes in the Replayer

Currently the replayer does:
```python
from src.ui.web import cdp_client
session = cdp_client.CdpSession(ws_url)
```

The `ws_url` already comes from tab-specific target discovery. For a separate Chrome instance, the `ws_url` would come from the instance's port:
```
ws://host:9223/devtools/page/TARGET_ID
```

The replayer needs to accept an optional `cdp_endpoint` parameter so it can discover targets on a non-default Chrome instance. Currently:
```python
# replayer.py line 1976
from src.ui.web import cdp_client
# ... uses cdp_client.get_targets() — which hits the global endpoint
```

Change: Allow replayer to take a specific endpoint, or accept a pre-resolved `ws_url` directly (which it already supports, line 2668: `ws_url: str = ""`).

---

## 3. All Browser Execution Paths

Every word from the user's prompt, mapped to concrete behavior.

### 3.1 The Complete Decision Tree

```
User wants to execute a plan with browser steps:

Q1: Which browser?
├── A) SAME BROWSER (tab-driven)
│   │   Uses the already-connected CDP browser — the one the user set up
│   │   via tab_mesh setup wizard (shortcut flags, profile cloning, etc.)
│   │
│   │   No extra Chrome launch needed. Replay uses the existing connection.
│   │
│   ├── Q1a: Foreground or background?
│   │   ├── Foreground — takes over the tab, user sees steps executing
│   │   │   (current behavior — cdp_client.activate_target)
│   │   └── Background — creates new tab, doesn't activate it
│   │       (start_replay already supports keep_background=True)
│   │
│   └── CONSTRAINT: The main browser must already be running with debug flags.
│       If it's not → fall back to "suggest CDP setup" (existing flow).
│
├── B) SEPARATE CHROME INSTANCE
│   │   Launches a NEW Chrome process with its own debug port.
│   │   The user's default browser is NOT touched, NOT restarted, NOT killed.
│   │
│   ├── Q2: Which profile?
│   │   ├── TEMPORARY (GoogleAccountless)
│   │   │   • Creates a temp dir via create_temp_profile_dir()
│   │   │   • Chrome launches with --user-data-dir=<temp> --no-first-run
│   │   │   • Clean slate — no bookmarks, no cookies, no account
│   │   │   • Ideal for: testing anonymous flows, CI, isolation
│   │   │
│   │   └── CLONED from existing profile
│   │       • User picks email from profile list (_read_chrome_profiles)
│   │       • System clones profile via clone_profile_to_debug_dir()
│   │       • Chrome launches with cloned profile + landing URL with
│   │         #chrome-signin&email=<email> for auto-fill
│   │       • User signs in → gets their synced data
│   │       • Ideal for: testing authenticated flows with real user state
│   │       •
│   │       • ⚠️ CONSTRAINT: You cannot reuse a profile that is already
│   │         running in a non-debug Chrome. The profile must be CLONED.
│   │         "obviously we cannot reuse profile that are already existing
│   │          and created without debugging but we just need to tell the
│   │          user this limitation with this alternate CDP"
│   │
│   ├── Q3: Headed or headless?
│   │   ├── Headed (visible window)
│   │   │   • Chrome opens a window, user can watch execution
│   │   │   • Requires a display (see Q4)
│   │   │
│   │   └── Headless (--headless)
│   │       • No visible window
│   │       • Ideal for: CI, background runs, WSL without X11
│   │
│   ├── Q4: Environment (auto-detected)
│   │   ├── Native Linux with display → headed ✅, headless ✅
│   │   ├── Native Windows → headed ✅, headless ✅
│   │   ├── WSL with X11/XServer → headed ✅, headless ✅
│   │   └── WSL WITHOUT X11 → headless ONLY ✅
│   │       "if the wsl doesn't have a good Xterm or X11 / xserver or
│   │        such to send to windows the chrome window then it only
│   │        allow headless"
│   │
│   ├── Q5: Where to run Chrome? (WSL detected)
│   │   ├── Inside WSL (Chrome for Linux, if installed)
│   │   └── On Windows side (chrome.exe via interop)
│   │       "we can also choose to run it inside WSL or windows
│   │        when we detect such a system"
│   │       → Windows side is the current path (chrome.exe via PowerShell)
│   │       → WSL-native Chrome is future (needs Chrome for Linux installed)
│   │
│   └── PORT: auto-allocated
│       • find_free_debug_port() scans from 9222 up
│       • "even if it mean that we need to use a different port
│         because it is still used by the other instance"
│       • Both instances can run simultaneously
│
└── C) NO BROWSER
    └── Plan contains only script steps (non-CDP)
        → No Chrome management needed
```

### 3.2 What the User Already Has vs What's New

| Aspect | Already Exists | What's New |
|--------|----------------|-----------|
| Tab-driven same browser | ✅ replayer.start_replay() | Nothing — works today |
| Background mode | ✅ `keep_background=True` param | Nothing — works today |
| Profile list with emails | ✅ `_read_chrome_profiles()` | Move to chrome/profiles.py |
| Profile cloning | ✅ `_clone_profile_to_debug_dir()` | Move to chrome/profiles.py |
| Chrome launch with debug flags | ✅ `restart_chrome()` PS1 script | Refactor: don't kill existing, separate port |
| Email pre-fill sign-in | ✅ `trigger_chrome_signin()` CDP flow | Nothing — works today |
| WSL detection | ✅ `_detect_wsl2()`, `_is_wsl()` | Move to chrome/detection.py |
| Port allocation | ❌ | New: `find_free_debug_port()` |
| Temp profile (GoogleAccountless) | ❌ | New: `create_temp_profile_dir()` |
| Headless flag | ❌ | New: `--headless` in launch config |
| X11/display detection | ❌ | New: `has_display()` |
| Multi-instance (don't kill main) | ❌ | New: launch without `taskkill` |
| Kill specific instance (by PID) | ❌ | New: PID-based kill vs `taskkill /IM` |
| Execution plan model | ❌ | New: plan composition |

### 3.3 The "Can't Reuse Non-Debug Profile" Constraint

This is a Chrome limitation, not ours. Chrome must be started with `--remote-debugging-port=N` for CDP to work. A Chrome instance started without this flag does NOT expose the CDP endpoint. There is no way to retroactively enable it.

**What we tell the user:**
- If they pick "Cloned profile" → we clone the file data and launch a NEW Chrome with it + debug flags. This works.
- If they try to "attach to my running Chrome" → we explain: "Chrome must be started with debugging enabled. Your running Chrome wasn't. Either restart it with debug flags (tab_mesh setup) or use a separate instance."

This is already handled by the tab_mesh setup wizard. The separate Chrome path avoids the entire problem by launching fresh.

### 3.4 Default Modes — Context Matters

The user's exact clarification:

> "the default option for execution plans to be the secondary chrome instance mode"
> "tab is good for devs but QA might not want to setup their default browser into debugger mode and only want the external browser mode"
> "from the test scripts engine you will be able to chose an external browser too which will also require evolution and will be the secondary option in this case"

This means **both interfaces offer both modes**, but with **different defaults**:

| Interface | DEFAULT mode | SECONDARY option | Why |
|-----------|-------------|-----------------|-----|
| **Execution Plans** | Separate Chrome (external browser) | Tab-driven (same browser) | QA users don't want debug flags on their daily browser. The external browser "just works" — click and go. Setup wizard link offered for tab mode. |
| **CDP Test Scripts** (existing engine) | Tab-driven (same browser) | Separate Chrome (external browser) | Devs already set up CDP via tab_mesh wizard. Tab-driven is current behavior. External browser is the NEW option coming. |

**Bidirectional evolution**:
- Execution plans are the NEW system → default to the easiest path (separate Chrome, no setup needed)
- CDP test scripts are the EXISTING system → keep current default (tab-driven), ADD separate Chrome as option
- Both share the same Chrome domain infrastructure
- The replay config UI (`_cdpTestShowReplayConfig`) needs a browser mode selector
- The execution plan launch UI needs a browser mode selector (with separate Chrome pre-selected)

**UX implication**: When a user selects "Separate Chrome" as browser mode (whether from execution plans or CDP test scripts), and they haven't set one up before, the UI offers: *"We recommend setting up a dedicated test profile. Click here to configure."* This links to profile setup (pick email, clone profile) — one-time action.

---

## 4. The Execution Plan Model

### 4.1 What Is an Execution Plan

An execution plan is a composed sequence of steps. Steps can be:

1. **Script steps** — run a script from the registry (M1)
2. **CDP test steps** — run a test suite via the replayer
3. **Checkpoint steps** — pause for user input (semi-automated)
4. **Conditional steps** — run only if a previous step passed/failed

### 4.2 Execution Modes (from Message 1)

| Mode | Behavior |
|------|----------|
| `fully_automated` | Runs all steps without stopping. Reports at end. |
| `semi_automated` | Pauses at checkpoint steps. User reviews, resumes. |
| `interactive` | Pauses after EVERY step. User drives each transition. |

### 4.3 Data Model

```python
@dataclass
class ExecutionPlan:
    id: str
    name: str
    description: str = ""
    steps: list[PlanStep] = field(default_factory=list)
    mode: str = "fully_automated"      # fully_automated | semi_automated | interactive
    browser_config: BrowserConfig | None = None   # null = no browser needed
    variables: dict[str, str] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

@dataclass
class PlanStep:
    id: str
    sequence: int
    type: str                           # "script" | "cdp_test" | "checkpoint" | "conditional"
    name: str = ""
    
    # For type="script":
    script_id: str = ""                 # From M1 registry
    script_params: dict = field(default_factory=dict)
    
    # For type="cdp_test":
    suite_id: str = ""                  # CDP test suite to replay
    suite_variables: dict = field(default_factory=dict)
    
    # For type="checkpoint":
    checkpoint_message: str = ""        # What to show the user
    
    # For type="conditional":
    depends_on_step_id: str = ""        # Which step's result to check
    condition: str = "passed"           # "passed" | "failed"
    then_step: PlanStep | None = None   # Step to execute if condition met

    optional: bool = False              # Same as CDP test — fail doesn't fail plan
    timeout_seconds: int = 0            # 0 = no timeout

@dataclass
class BrowserConfig:
    """How the plan's browser steps should execute."""
    mode: str = "same_browser"          # "same_browser" | "separate_instance" | "none"
    
    # For separate_instance:
    profile_type: str = "temp"          # "temp" (GoogleAccountless) | "cloned"
    clone_from_profile: str = ""        # "Default" or specific profile dir
    headless: bool = False
    port: int = 0                       # 0 = auto-allocate
    
    # Resolved at runtime (not stored):
    # - display_available: bool
    # - environment: str ("wsl", "windows", "linux")
    # - actual_port: int
    # - instance: ChromeInstance

@dataclass  
class PlanRunResult:
    id: str
    plan_id: str
    plan_name: str
    status: str = "running"             # running | passed | failed | partial | cancelled
    step_results: list[dict] = field(default_factory=list)
    started_at: str = ""
    finished_at: str = ""
    chrome_instance: dict | None = None  # Instance info if separate Chrome was launched
    error: str = ""
```

### 4.4 Plan Execution Flow

```
Plan.execute():
│
├── 1. Validate plan (all scripts exist, all suites exist)
│
├── 2. Resolve browser config
│   ├── mode="same_browser" → verify CDP available, get endpoint
│   ├── mode="separate_instance" → launch Chrome via launcher
│   │   ├── Allocate port
│   │   ├── Create/clone profile
│   │   ├── Check display availability
│   │   ├── Launch Chrome process
│   │   └── Wait for CDP endpoint to become available
│   └── mode="none" → skip browser setup
│
├── 3. Execute steps in sequence
│   ├── For each step:
│   │   ├── type="script" → run via M1 Executor
│   │   ├── type="cdp_test" → run via replayer.start_replay()
│   │   │   └── Pass the resolved CDP endpoint (same or separate)
│   │   ├── type="checkpoint" → pause, emit event, wait for resume
│   │   └── type="conditional" → evaluate, skip or execute
│   │
│   ├── After each step:
│   │   ├── Record result
│   │   ├── If mode="interactive" → pause, wait for resume
│   │   ├── If step failed and not optional → abort (or continue based on plan config)
│   │   └── Emit SSE event with step status
│   │
│   └── Handle cancellation (stop_event)
│
├── 4. Finalize
│   ├── Calculate overall status
│   ├── If separate Chrome was launched → optionally kill it
│   ├── Emit completion event
│   └── Save result to storage
```

---

## 5. Constraints and Limitations

### 5.1 Hard Constraints

| # | Constraint | Source |
|---|-----------|--------|
| 1 | Cannot attach CDP to Chrome started without `--remote-debugging-port` | Chrome limitation |
| 2 | Chrome 136+ requires `--user-data-dir` pointing to a NON-default directory | Chrome 136 change |
| 3 | WSL without X11/display → headless only | Display forwarding requirement |
| 4 | Python scripts MUST run via project venv | User rule |
| 5 | No logic in `__init__.py` | Project rule |
| 6 | One replay at a time (current `_active_run` singleton) | Replayer architecture |
| 7 | Must communicate limitations to the user, not silently fail | User directive |

### 5.2 Constraint #6 Impact

The replayer currently allows only ONE active replay (`_active_run` global). This means:
- An execution plan with multiple CDP test steps runs them **sequentially**, not in parallel
- Two separate plans cannot run browser steps simultaneously
- This is acceptable for M7 — parallel replays would be M8+ territory

### 5.3 Things We Explicitly Do NOT Build in M7

| Not in scope | Why |
|-------------|-----|
| Parallel replays | Replayer singleton constraint |
| Chrome for Linux in WSL | Needs Chrome installed in WSL — rare setup. Windows-side chrome.exe is the proven path |
| Salt/Ansible export | That's M8 (Interop) |
| PowerShell script execution | That's also M8 |
| Plan YAML import/export | Future |

---

## 6. Delivery Chunks

### Chunk 1: Chrome Domain Extraction (Infrastructure)

**What**: Move Chrome management code from `tab_mesh/__init__.py` into `src/core/services/chrome/`.

**Files created**:
- `src/core/services/chrome/__init__.py`
- `src/core/services/chrome/detection.py`
- `src/core/services/chrome/profiles.py`
- `src/core/services/chrome/launcher.py`
- `src/core/services/chrome/shortcuts.py`

**Files modified**:
- `src/ui/web/routes/tab_mesh/__init__.py` — Replaces private functions with imports from `src.core.services.chrome`

**Risk**: This is a refactor. Every route in tab_mesh must work EXACTLY as before. Zero behavior change.

**Verification**: Every tab_mesh route (`cdp-status`, `focus`, `discover-target`, `cdp-diagnose`, `cdp-remediate`, `kill-chrome`, `restart-chrome`, `trigger-chrome-signin`) must return identical responses before and after.

**Dependencies**: None — this is pure extraction.

### Chunk 2: Multi-Instance Launch (New Capability)

**What**: Add the ability to launch a Chrome instance WITHOUT killing the existing one.

**Files modified**:
- `src/core/services/chrome/launcher.py` — Add `find_free_debug_port()`, modify launch to not kill by default, add PID tracking

**New behaviors**:
- `find_free_debug_port(start=9222)` — tries ports 9222, 9223, ... up to 9230
- `launch_chrome(config)` with `kill_existing=False` — launches without `taskkill`
- `kill_instance(instance)` — kills by PID, not by image name
- PID tracking: capture the process ID from the launched Chrome

**Dependencies**: Chunk 1

### Chunk 3: Temporary Profile + Display Detection (New Capability)

**What**: GoogleAccountless (temp profile) and headed/headless detection.

**Files modified**:
- `src/core/services/chrome/profiles.py` — Add `create_temp_profile_dir()`
- `src/core/services/chrome/detection.py` — Add `has_display()`

**New behaviors**:
- `create_temp_profile_dir()` — creates a temp dir with `--no-first-run` compatibility
- `has_display()` — checks `$DISPLAY` in WSL, always True on Windows/native Linux
- `ChromeLaunchConfig.headless` flag flows through to `--headless` in the PS1 script

**Dependencies**: Chunk 1

### Chunk 4: Replayer Multi-Endpoint + CDP Test UI Evolution (Integration)

**What**: Two things:
1. Allow the replayer to target a specific Chrome instance instead of the global cdp_client endpoint.
2. Add a browser mode selector to the CDP test scripts UI (`_cdpTestShowReplayConfig`).

**Files modified**:
- `src/core/services/cdp_test/replayer.py` — `replay_suite()` and `start_replay()` accept optional `cdp_endpoint` parameter. When provided, target discovery uses this endpoint instead of the global one.
- `src/ui/web/templates/scripts/integrations/_cdp_test.html` — `_cdpTestShowReplayConfig()` gains a browser mode selector. Default = tab-driven (current behavior). Secondary = separate Chrome (new).

**Key change**: The replayer already accepts `ws_url` directly (line 2668). The gap is in step routing and `_find_dcp_tab()` / `_verify_target_tab()` which call `cdp_client.get_targets()` using the global endpoint. These need a `port` override.

**UI change**: The replay config modal gets a "Browser" section:
- 🖥️ **Same Browser** (default, selected) — "Uses your current CDP browser"
- 🌐 **External Browser** — "Launches a separate Chrome instance"
  - If selected, shows profile choice (Temporary / Cloned from [dropdown]) and Headed/Headless toggle

**Dependencies**: Chunk 2 (need a launched instance to point at)

### Chunk 5: Execution Plan Model (Core M7)

**What**: The plan data model, executor, and storage.

**Files created**:
- `src/core/services/scripts/plans.py` — `ExecutionPlan`, `PlanStep`, `BrowserConfig`, `PlanRunResult` models
- `src/core/services/scripts/plan_executor.py` — Plan execution engine (orchestrates steps, manages Chrome lifecycle, emits events)

**Dependencies**: M1 (Script Registry + Executor), Chunk 4 (replayer multi-endpoint)

### Chunk 6: Plan Interfaces (CLI + API + UI)

**What**: How users create, view, run, and monitor execution plans.

**Files created/modified**:
- CLI commands (M4 scope)
- Web API routes (M4 scope)
- Admin panel UI (M4 scope)

**Dependencies**: Chunk 5, M4

### Execution Approach

Each chunk is taken in order. Before starting a chunk:
1. **Deep analysis** — read every file involved, trace every call site
2. **Individual plan** — write the specific implementation plan for that chunk
3. **Execute** — implement the chunk
4. **Verify** — confirm it works, existing behavior unchanged
5. **Move to next** — only after the current chunk is solid

We do NOT plan all chunks in detail upfront. Each chunk's implementation plan is written at execution time with full context from the code as it exists at that point.

---

## 7. Connection Map — How Everything Fits Together

```
                      ┌─────────────────────────────────────────────┐
                      │              EXECUTION PLAN                  │
                      │                                              │
                      │  Steps: [script, cdp_test, checkpoint, ...]  │
                      │  BrowserConfig: same_browser / separate /    │
                      │                 none                         │
                      └──────────┬──────────────────────────────────┘
                                 │
                    plan_executor.py
                                 │
              ┌──────────────────┼─────────────────────┐
              │                  │                     │
              ▼                  ▼                     ▼
     script steps         cdp_test steps        checkpoint steps
     (M1 executor)        (replayer)             (event + wait)
                                 │
                    ┌────────────┼────────────────┐
                    │                             │
                    ▼                             ▼
           same_browser                  separate_instance
           (existing CDP)                (chrome domain)
           cdp_client global             │
           endpoint                      ├── launcher.launch_chrome()
                                         ├── profiles.clone_... or .temp()
                                         ├── detection.has_display()
                                         └── find_free_debug_port()
                                                    │
                                                    ▼
                                           CdpSession(ws_url on port N)
                                           replayer targets this instance
```

### What calls what:

```
plan_executor.py
  ├── calls → src.core.services.scripts.executor (M1) for script steps
  ├── calls → src.core.services.cdp_test.replayer for CDP test steps
  ├── calls → src.core.services.chrome.launcher for browser lifecycle
  ├── calls → src.core.services.chrome.profiles for profile setup
  └── calls → src.core.services.chrome.detection for environment checks

tab_mesh routes (after extraction)
  ├── calls → src.core.services.chrome.detection
  ├── calls → src.core.services.chrome.profiles
  ├── calls → src.core.services.chrome.launcher
  └── calls → src.core.services.chrome.shortcuts

cdp_client.py — UNCHANGED
  └── transport layer: HTTP + WebSocket to Chrome
      (used by both replayer and tab_mesh directly)
```

---

## 8. File Layout — Full Tree After M7

```
src/core/services/
├── chrome/                          ← NEW DOMAIN (Chunk 1-3)
│   ├── __init__.py                  ← Re-exports only
│   ├── detection.py                 ← WSL, Windows user, Chrome version, X11 display
│   ├── profiles.py                  ← Profile read/clone/temp, path helpers
│   ├── launcher.py                  ← Launch instances, port allocation, PID lifecycle
│   └── shortcuts.py                 ← Windows .lnk management
│
├── cdp_test/                        ← MODIFIED (Chunk 4)
│   ├── models.py                    ← Unchanged
│   ├── recorder.py                  ← Unchanged
│   ├── replayer.py                  ← + cdp_endpoint parameter support
│   ├── session.py                   ← Unchanged
│   └── storage.py                   ← Unchanged
│
├── scripts/                         ← FROM M1 + NEW (Chunk 5)
│   ├── models.py                    ← From M1
│   ├── registry.py                  ← From M1
│   ├── executor.py                  ← From M1
│   ├── output_router.py             ← From M1
│   ├── plans.py                     ← Execution plan data models
│   └── plan_executor.py             ← Plan execution engine

src/ui/web/
├── cdp_client.py                    ← UNCHANGED (transport)
├── routes/
│   └── tab_mesh/
│       └── __init__.py              ← MODIFIED — delegates to chrome domain
```

---

## 9. Open Questions (Need User Input Before Implementation)

| # | Question | Options | Impact |
|---|---------|---------|--------|
| 1 | Should plans be stored as JSON files (like suites) or in a database? | JSON files in `data/plans/` vs SQLite | Storage architecture |
| 2 | Should the separate Chrome instance be auto-killed when the plan finishes, or kept alive for inspection? | Auto-kill / keep / ask user | UX decision |
| 3 | When a plan has both script steps and CDP test steps, should they share variables? | Shared namespace / separate / explicit mapping | Data flow |
| 4 | Should `cdp_diagnose` and `cdp_remediate` routes move entirely to a new chrome API, or stay as tab_mesh routes that delegate? | New `/chrome/...` routes vs delegate | API design |
| 5 | For WSL: should we support launching Chrome natively in WSL (Chrome for Linux) or only via Windows-side chrome.exe? | WSL-only / Windows-only / both | Scope |

---

## 10. Cross-References

| Reference | Location |
|-----------|----------|
| Tab Mesh routes (current) | `src/ui/web/routes/tab_mesh/__init__.py` (1,172 lines) |
| Tab Mesh panel (current) | `src/ui/web/templates/scripts/_tab_mesh_panel.html` (931 lines) |
| CDP client | `src/ui/web/cdp_client.py` (1,390 lines) |
| CDP port injector | `src/core/services/cdp_port_injector.py` (217 lines) |
| CDP test replayer | `src/core/services/cdp_test/replayer.py` (2,786 lines) |
| CDP test models | `src/core/services/cdp_test/models.py` |
| CDP test session | `src/core/services/cdp_test/session.py` |
| Scripts system overview | `.agent/plans/scripts-system/scripts-system.md` |
| M1 Framework plan | `.agent/plans/scripts-system/scripts-system-M1-framework.md` |
