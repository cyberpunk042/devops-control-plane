# Chunk 4: Replayer Multi-Endpoint + CDP Test UI Evolution

> **Status**: ✅ DONE
> **Created**: 2026-03-09
> **Completed**: 2026-03-09
> **Parent**: `scripts-system-M7-plans.md` → Chunk 4
> **Depends on**: Chunk 2a (ChromeLauncher WSL) ✅ DONE, Chunk 2b (Native Linux) ✅ DONE, Chunk 3 (Temp Profile) ✅ DONE

---

## 0. Why This Chunk Exists

Chunks 2a–3 built the ChromeLauncher: it can launch Chrome instances on both
WSL→Windows and native Linux, manage their lifecycle, detect when Chrome is
missing, and offer remediation. But nothing *uses* these instances yet.

The replayer (`replayer.py`) currently targets the user's existing Chrome via
the global `cdp_client` endpoint (port 9222). It cannot target a *separate*
Chrome instance launched by the ChromeLauncher on port 9223, 9224, etc.

This chunk connects the ChromeLauncher to the replayer, giving users the
choice: "replay in my current browser tab" OR "launch a fresh Chrome and
replay there." This is the integration point that makes multi-instance
Chrome useful.

---

## 1. What Exists Today — Traced from Source

### 1.1 CDP Client (`src/ui/web/cdp_client.py`)

The CDP client is a module-level singleton with a global endpoint:

```python
_DEFAULT_PORT = 9222
_endpoint: str | None = None

def _base_url() -> str:
    return _endpoint or f"http://localhost:{_DEFAULT_PORT}"
```

Every public function uses `_base_url()` implicitly:

| Function | Line | What it does | Uses global endpoint? |
|----------|------|-------------|----------------------|
| `get_targets()` | 195 | `_get_json("/json")` | ✅ Yes |
| `find_target_by_url()` | 218 | Searches targets list | No (operates on list) |
| `activate_target(id)` | 249 | `_get_raw(f"/json/activate/{id}")` | ✅ Yes |
| `create_tab(url)` | ~265 | `_get_json(f"/json/new?{url}")` | ✅ Yes |
| `is_available()` | 173 | `_get_json("/json/version")` | ✅ Yes |
| `get_version()` | 179 | `_get_json("/json/version")` | ✅ Yes |

The private transport functions are:
- `_get_json(path, timeout)` — resolves `_base_url() + path`, handles WSL2→curl.exe bridge
- `_get_raw(path, timeout)` — same but returns raw text
- `_curl_exe_get(url, timeout)` — WSL2 bridge via `curl.exe`

**Key insight**: `_get_json` and `_get_raw` take a *path* and prepend `_base_url()`.
To support multi-port, these need to accept an optional *full URL* or a port
override so they can be redirected to `http://localhost:9223/json` instead of
the global `http://localhost:9222/json`.

### 1.2 Replayer (`src/core/services/cdp_test/replayer.py`)

The replayer has two discovery functions that are hardcoded to the global endpoint:

```python
def _verify_target_tab(target_id: str) -> str | None:       # line 1852
    """Verify the target tab is alive and return its WS URL."""
    from src.ui.web import cdp_client
    targets = cdp_client.get_targets()    # ← GLOBAL port
    for t in targets:
        if t.get("id") == target_id:
            return t.get("webSocketDebuggerUrl")
    return None

def _find_dcp_tab() -> str | None:                          # line 1867
    """Find the DCP admin panel tab's target ID."""
    from src.ui.web import cdp_client
    targets = cdp_client.get_targets()    # ← GLOBAL port
    dcp = cdp_client.find_target_by_url(targets, "localhost:8000")
    if dcp:
        return dcp.get("id")
    return None
```

The main replay functions already accept `ws_url`:

```python
def replay_suite(suite, target_id, variables, callback, stop_event, *,
                 run_id="", ws_url="", dcp_tab_id=None, ...)   # line 1939

def start_replay(suite, target_id, variables=None, callback=None, *,
                 ws_url="", dcp_tab_id=None, ...)               # line 2662
```

**Once `ws_url` is provided**, `CdpSession(ws_url)` connects to that WebSocket
directly — this part already works for any port. The gap is only in *discovery*.

### 1.3 API Route (`src/ui/web/routes/cdp_test/replay.py`)

The route handler does discovery on the global endpoint:

```python
# Line 88 — target discovery
targets = cdp_client.get_targets()          # ← GLOBAL port

# Line 101 — URL matching
match = cdp_client.find_target_by_url(targets, url_pattern)

# Line 113 — tab creation
new_tab = cdp_client.create_tab(suite.target_url)   # ← GLOBAL port

# Line 134 — verification
targets = cdp_client.get_targets()          # ← GLOBAL port

# Line 148 — DCP tab for switch-back
dcp_match = cdp_client.find_target_by_url(targets, "localhost:8000")
```

All of these need a port override when replaying against a separate instance.

### 1.4 Frontend (`_cdp_test.html`)

`_cdpTestShowReplayConfig(suiteId, defaults)` at line 2103 renders a modal with:
- ⏱ Timing (visual delay, page change settle)
- 🧹 Session (clear site data)
- 🔄 Tab Focus (keep running in background)
- Tab status indicator

It does NOT have a browser mode selector. The modal currently fires
`_cdpTestExecuteFromConfig()` which POSTs to `/cdp-test/replay/start`.

### 1.5 ChromeLauncher — what we built

The launcher provides:
- `get_launcher().launch(config)` → `ChromeInstance` with `.port`, `.pid`, `.endpoint`
- `get_launcher().kill_instance(instance)` — environment-aware kill
- `require_chrome()` → availability check with install_plan
- `create_temp_profile_dir(port)` → isolated profile in `/tmp`

---

## 2. Scope — Every Component That Needs to Change

### 2.1 Modified: `cdp_client.py` — Port-parameterised discovery

Add an optional `port` parameter to the functions that hit Chrome's HTTP API.
When provided, use `http://localhost:{port}` instead of `_base_url()`.

**Functions to modify:**

| Function | Change |
|----------|--------|
| `_get_json(path, timeout)` | Add `port: int | None = None` — when set, override base URL |
| `_get_raw(path, timeout)` | Add `port: int | None = None` — same |
| `get_targets()` | Add `port: int | None = None` → pass to `_get_json` |
| `activate_target(target_id)` | Add `port: int | None = None` → pass to `_get_raw` |
| `create_tab(url)` | Add `port: int | None = None` → pass to `_get_json` |
| `is_available()` | Add `port: int | None = None` → pass to `_get_json` |

**Implementation pattern:**

```python
def _get_json(path: str, timeout: float = 1.0, *, port: int | None = None):
    if port is not None:
        url = f"http://localhost:{port}{path}"
    else:
        url = f"{_base_url()}{path}"
    # ... rest unchanged
```

This is the minimal, non-breaking change. Every existing caller passes no
`port` argument → behavior is identical to today.

### 2.2 Modified: `replayer.py` — Thread `cdp_port` through discovery

**Functions to modify:**

```python
def _verify_target_tab(target_id: str, *, cdp_port: int | None = None) -> str | None:
    targets = cdp_client.get_targets(port=cdp_port)
    ...

def _find_dcp_tab(*, cdp_port: int | None = None) -> str | None:
    targets = cdp_client.get_targets(port=cdp_port)
    ...

def replay_suite(suite, target_id, ..., *, cdp_port: int | None = None, ...):
    # Pass cdp_port to _verify_target_tab and _find_dcp_tab
    ...

def start_replay(suite, target_id, ..., *, cdp_port: int | None = None, ...):
    # Pass cdp_port to replay_suite
    ...
```

**DCP tab behavior when using separate browser:**

When `cdp_port` is not the default (9222), `_find_dcp_tab()` should return
`None` because the DCP admin panel tab exists in the user's browser, not in
the launched test browser. The "switch back to admin panel" behavior at the
end of replay should be skipped gracefully (it already handles `dcp_tab_id=None`).

### 2.3 Modified: `routes/cdp_test/replay.py` — Accept `cdp_port` in body

The POST body gains a new optional field:

```json
{
    "suite_id": "abc-123",
    "target_id": "CHROME-TARGET-ID",
    "variables": { ... },
    "cdp_port": 9223          // NEW — optional, defaults to global port
}
```

When `cdp_port` is provided:
- All `cdp_client.get_targets()` calls pass `port=cdp_port`
- All `cdp_client.find_target_by_url()` calls use the port-specific targets
- All `cdp_client.create_tab()` calls pass `port=cdp_port`
- `start_replay()` receives `cdp_port=cdp_port`

### 2.4 New Route: `POST /cdp-test/launch-browser`

A new endpoint that launches a separate Chrome instance for testing:

```python
@cdp_test_bp.route("/cdp-test/launch-browser", methods=["POST"])
def cdp_test_launch_browser():
    """Launch a separate Chrome instance for isolated test replay.

    Body (JSON)::

        {
            "headless": false,           // optional, default false
            "url": "http://example.com", // optional, opens this URL
        }

    Returns::

        {
            "ok": true,
            "port": 9223,
            "pid": 12345,
            "endpoint": "http://localhost:9223",
        }
    """
```

This calls `ChromeLauncher.launch()` with a `ChromeLaunchConfig` and returns
the instance details. The frontend saves the port and sends it with the
replay start request.

### 2.5 New Route: `POST /cdp-test/kill-browser`

Cleanup endpoint to kill a launched test browser:

```python
@cdp_test_bp.route("/cdp-test/kill-browser", methods=["POST"])
def cdp_test_kill_browser():
    """Kill a previously launched test Chrome instance.

    Body (JSON)::

        { "port": 9223 }

    Returns::

        { "ok": true, "killed": true }
    """
```

### 2.6 Modified: Frontend `_cdpTestShowReplayConfig()` — Browser mode selector

The replay config modal gains a new "🌐 Browser" section:

```
⚙ Replay Configuration
├── Suite info (existing)
├── ⏱ Timing (existing)
├── 🧹 Session (existing)
├── 🔄 Tab Focus (existing)
├── 🌐 Browser (NEW)
│   ├── ○ Same Browser (default) — "Replay in your current browser tab"
│   └── ○ Separate Browser — "Launch a fresh Chrome instance"
│       ├── [ ] Headless mode
│       └── Status: "Ready" / "Launching..." / "Chrome not installed"
├── Tab status (existing)
└── Buttons (existing)
```

**Behavior when "Separate Browser" is selected:**

1. Frontend calls `GET /tab-mesh/chrome-status` to check availability
2. If Chrome not available → show install guidance, disable Execute button
3. If Chrome available → show "Ready to launch"
4. On Execute click:
   a. `POST /cdp-test/launch-browser` → get `port`
   b. Wait for CDP to be available on that port
   c. `POST /cdp-test/replay/start` with `cdp_port: port`
   d. Standard replay flow proceeds

**Behavior when "Same Browser" is selected (default):**

Unchanged from today. No `cdp_port` sent. Global endpoint used.

---

## 3. Architecture — Full Flow

### 3.1 Same Browser (existing, unchanged)

```
User clicks Execute → _cdpTestExecuteFromConfig()
  → POST /cdp-test/replay/start { suite_id, target_id }
    → cdp_client.get_targets()  [port 9222]
    → find matching tab
    → start_replay(suite, target_id, ws_url)
      → CdpSession(ws_url)
      → replay steps
      → switch back to DCP tab
```

### 3.2 Separate Browser (new)

```
User selects "Separate Browser" in config modal
  → GET /tab-mesh/chrome-status
  → Chrome available? → show "Ready"

User clicks Execute → _cdpTestExecuteFromConfig()
  → POST /cdp-test/launch-browser { headless: false, url: suite.target_url }
    → ChromeLauncher.launch(config)
    → returns { port: 9223, pid: 45678 }
  → wait for CDP ready on port 9223
  → POST /cdp-test/replay/start { suite_id, cdp_port: 9223 }
    → cdp_client.get_targets(port=9223)
    → find matching tab (should be the only tab)
    → start_replay(suite, target_id, ws_url, cdp_port=9223)
      → CdpSession(ws_url)   [ws on port 9223]
      → replay steps
      → _find_dcp_tab(cdp_port=9223) → None (no DCP in test browser)
      → skip switch-back

Replay finishes → frontend decides:
  → keep browser alive for inspection, or
  → POST /cdp-test/kill-browser { port: 9223 }
```

### 3.3 Error Path: Chrome not installed

```
User selects "Separate Browser"
  → GET /tab-mesh/chrome-status → { available: false, install_plan: {...} }
  → UI shows: "Chrome not installed. Install via Audit → Tool Install."
  → Execute button disabled
  → Notification created (deduped)
```

---

## 4. Files Modified/Created

| File | Action | What Changes |
|------|--------|-------------|
| `src/ui/web/cdp_client.py` | **MODIFY** | Add `port` parameter to `_get_json`, `_get_raw`, `get_targets`, `activate_target`, `create_tab`, `is_available` |
| `src/core/services/cdp_test/replayer.py` | **MODIFY** | Add `cdp_port` parameter to `_verify_target_tab`, `_find_dcp_tab`, `replay_suite`, `start_replay` |
| `src/ui/web/routes/cdp_test/replay.py` | **MODIFY** | Accept `cdp_port` in POST body, pass through chain |
| `src/ui/web/routes/cdp_test/replay.py` | **ADD** | New routes: `POST /cdp-test/launch-browser`, `POST /cdp-test/kill-browser` |
| `src/ui/web/templates/scripts/integrations/_cdp_test.html` | **MODIFY** | Add browser mode selector to `_cdpTestShowReplayConfig()`, update `_cdpTestExecuteFromConfig()` |

---

## 5. Implementation Order

Each step is ONE change, verified before moving to the next.

### Step 1: `port` parameter in `cdp_client._get_json` and `_get_raw`

Add the `port` keyword argument to the two private transport functions.
When `port` is provided, construct URL as `http://localhost:{port}{path}`
instead of `{_base_url()}{path}`.

**Verify**: Import `cdp_client`, call `_get_json("/json/version", port=9222)` — 
should return version dict (same as today). Call with a bogus port → None.

### Step 2: `port` parameter in public `cdp_client` functions

Add `port: int | None = None` to `get_targets()`, `activate_target()`,
`create_tab()`, `is_available()`, `get_version()`. Each passes it through to
`_get_json` or `_get_raw`.

**Verify**: `cdp_client.get_targets(port=9222)` returns targets.
`cdp_client.is_available(port=9222)` returns True.

### Step 3: `cdp_port` parameter in replayer discovery functions

Add `cdp_port` to `_verify_target_tab()` and `_find_dcp_tab()`.
Pass it to `cdp_client.get_targets(port=cdp_port)`.

**Verify**: Call `_verify_target_tab(some_id, cdp_port=9222)` — should work
as before. Call with bogus port → returns None.

### Step 4: `cdp_port` parameter in `replay_suite` and `start_replay`

Thread `cdp_port` through the main replay functions. Pass it to
`_verify_target_tab()` and `_find_dcp_tab()`. When `cdp_port` is set
and `dcp_tab_id` would be looked up → skip the DCP tab lookup if it's
a different port than the global.

**Verify**: Import check. (Live test would need a running Chrome instance.)

### Step 5: Accept `cdp_port` in `routes/cdp_test/replay.py`

Read `cdp_port` from POST body. When present, use it for all
`cdp_client.get_targets()`, `cdp_client.create_tab()`, and
`cdp_client.find_target_by_url()` calls. Pass it to `start_replay()`.

**Verify**: Existing replay (no `cdp_port` in body) works unchanged.

### Step 6: New route `POST /cdp-test/launch-browser`

Add the launch-browser endpoint. Calls `ChromeLauncher.launch()` with:
- `headless` from body (default False)
- Auto-selected port via `find_free_debug_port()`
- `landing_url` from body's `url` field

Returns `{ ok, port, pid, endpoint }`.

**Verify**: POST to the endpoint → Chrome launches (WSL) or ChromeNotInstalled
(if no Chrome). Check response structure.

### Step 7: New route `POST /cdp-test/kill-browser`

Add the kill-browser endpoint. Looks up the instance by port in
`get_launcher()._instances`, calls `kill_instance()`.

**Verify**: Launch a browser, then kill it. Confirm PID gone.

### Step 8: Frontend — Browser mode selector UI

Add the "🌐 Browser" section to `_cdpTestShowReplayConfig()` with
radio buttons for Same Browser / Separate Browser.

When "Separate Browser" is selected, show headless checkbox and
call `GET /tab-mesh/chrome-status` to check availability.

**Verify**: Open replay config modal → see new Browser section.
Toggle between modes → UI updates.

### Step 9: Frontend — Separate browser launch flow

Update `_cdpTestExecuteFromConfig()` to:
1. Check browser mode
2. If "Separate Browser":
   a. POST `/cdp-test/launch-browser`
   b. Wait for CDP ready (poll `/json/version` on the new port)
   c. POST `/cdp-test/replay/start` with `cdp_port`
3. If "Same Browser": unchanged behavior

**Verify**: Full end-to-end test with a separate Chrome instance.

### Step 10: Frontend — Post-replay cleanup

After replay finishes (via SSE `cdp_test:replay_done`), if the replay used
a separate browser:
- Show "Keep browser open for inspection" / "Close browser" buttons
- "Close" calls `POST /cdp-test/kill-browser { port }`

**Verify**: Replay → done → click Close → browser killed.

---

## 6. Risk Analysis

| Risk | Impact | Mitigation |
|------|--------|------------|
| Adding `port` param to `cdp_client` breaks callers | High — cdp_client is used everywhere | Keyword-only arg with default None → zero impact on existing calls |
| Threading `cdp_port` through replayer touches hot code | Medium — replayer is complex | Only 4 function signatures change; bodies get 1–2 line changes each |
| Separate Chrome instance has no tabs matching suite URL | Replay can't find target | Route already auto-creates a tab via `create_tab()` — just need port override |
| WSL bridge: `curl.exe` may not handle non-default ports | Replay fails on WSL | `curl.exe` uses full URL, port is in the URL — should work. Verify in step 2. |
| Frontend launch flow: race condition between launch and CDP ready | Replay starts before Chrome is ready | Use polling loop with timeout (same pattern as `_wait_for_ready` in launcher) |
| ChromeNotInstalled during launch-browser | User confused | Frontend checks `/tab-mesh/chrome-status` BEFORE showing Execute button |
| Multiple separate instances accumulate | Resource leak | kill-browser endpoint + UI cleanup. Also: launcher has MAX_INSTANCES=5 cap. |
| Headless Chrome has different behaviour | Tests pass headed but fail headless | Document this. Not a code risk — user's choice. |

---

## 7. Verification Matrix

| Scenario | Expected Result | How to Verify |
|----------|-----------------|---------------|
| `cdp_client.get_targets(port=9222)` | Returns targets (same as today) | Direct call |
| `cdp_client.get_targets(port=9999)` | Returns `[]` (no Chrome on that port) | Direct call |
| `cdp_client.get_targets()` (no port) | Returns targets (unchanged behavior) | Direct call |
| Replay with `cdp_port=None` (default) | Existing behavior unchanged | Full replay test |
| Replay with `cdp_port=9223` (separate) | Uses port 9223 for discovery | Launch Chrome on 9223, replay |
| `POST /cdp-test/launch-browser` | Returns port + pid | Call endpoint |
| `POST /cdp-test/kill-browser { port }` | Kills the instance | Call after launch |
| `_find_dcp_tab(cdp_port=9223)` | Returns None (no DCP in test browser) | Direct call |
| Frontend: Same Browser mode | No changes to current flow | Open config modal |
| Frontend: Separate Browser mode | Shows headless option + Chrome status | Open config modal, select |
| Frontend: Chrome not installed | Execute disabled, install guidance shown | Mock Chrome missing |
| Post-replay cleanup | Kill-browser button works | Complete a replay |

---

## 8. Dependencies Between Steps

```
Step 1 ──→ Step 2 ──→ Step 3 ──→ Step 4 ──→ Step 5
  (transport)  (public API)  (discovery)  (replayer)  (route)
                                                        │
                                                        ├───→ Step 6 (launch route)
                                                        └───→ Step 7 (kill route)
                                                                │
                                                                ▼
                                                        Step 8 (UI selector)
                                                                │
                                                                ▼
                                                        Step 9 (UI launch flow)
                                                                │
                                                                ▼
                                                        Step 10 (UI cleanup)
```

Steps 1–5 are backend-only. Steps 6–7 are backend + integration.
Steps 8–10 are frontend. Each step is independently verifiable.

---

## 9. Out of Scope (Documented for Later)

- Profile cloning into separate Chrome instance (use temp profile for now)
- Browser extension preloading in separate instance
- Recording in separate browser (Chunk 5+ concern)
- Multiple concurrent separate instances (one at a time for now)
- Remote Chrome on a different machine/container
- Automatic headed→headless fallback
- Performance benchmarking headed vs headless

---

## 10. Cross-References

| Reference | Location |
|-----------|----------|
| ChromeLauncher | `src/core/services/chrome/launcher.py` |
| ChromeLaunchConfig | `src/core/services/chrome/launcher.py` |
| CDP client | `src/ui/web/cdp_client.py` |
| Replayer | `src/core/services/cdp_test/replayer.py` |
| Replay route | `src/ui/web/routes/cdp_test/replay.py` |
| CDP test frontend | `src/ui/web/templates/scripts/integrations/_cdp_test.html` |
| Chrome status check | `/tab-mesh/chrome-status` (from Chunk 2b) |
| Notification system | `src/core/services/notifications.py` |
| Chunk 2a plan | `.agent/plans/scripts-system/chunk-2a-chrome-launcher-wsl.md` |
| Chunk 2b plan | `.agent/plans/scripts-system/chunk-2b-native-linux-chrome.md` |
| M7 overview | `.agent/plans/scripts-system/scripts-system-M7-plans.md` |
