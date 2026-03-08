# CDP Port Awareness — Implementation Plan

## Problem Statement

When DCP falls back to a different port because the preferred port
is occupied, the user might not know DCP is running — especially
if they have a browser tab open on the occupied port looking at
whatever foreign app is there.

**Two-sided solution:**

1. **Our side** (DCP on fallback port): Enrich the existing fallback
   banner with **port intelligence** — tell the user exactly WHAT
   process is blocking the port (name, PID, type).
2. **Their side** (foreign process's browser tabs): Use CDP to
   **inject a notification** into any Chrome tab pointing at the
   occupied port — regardless of what Chrome is rendering (HTML app,
   JSON API response, error page — they all have a DOM in Chrome).

**Scope boundary:** This only applies to foreign (non-DCP) processes.
`_probe_our_server()` in `server_lifecycle.py` already detects our
own instances and handles them via PID takeover. CDP injection is
for everything else.

---

## Design Principles

1. **Use what exists.** `cdp_client` already has `get_targets()`,
   `evaluate_js()`, `find_target_by_url()`. Don't reinvent.
2. **Chrome renders everything as a page.** JSON responses, error
   pages, HTML apps — they all have `document.body` in Chrome.
   CDP can inject into all of them. No need to classify content type.
3. **Process identification is OS-level.** Use `ss`/`lsof` to get
   PID and process name — this enriches our own fallback banner.
4. **One-shot per tab, not polling.** Inject once per target ID.
   New tab = new target = new injection. Dismissed = respected.
5. **Non-destructive.** Banner is dismissible, doesn't break
   the foreign page.

---

## Architecture

### Two Independent Layers

```
┌─────────────────────────────────────────────────────────┐
│  LAYER 1: Port Intelligence                             │
│  (runs at startup during resolve_port fallback)         │
│                                                         │
│  Input:  preferred port (8000), host                    │
│  Action: ss/lsof → get PID, process name, cmdline      │
│  Output: enriched PORT_FALLBACK config dict             │
│                                                         │
│  Example: "Port 8000 held by node (PID 4521)            │
│            cmd: node ./server.js"                       │
│                                                         │
│  Feeds → our fallback banner (richer info for user)     │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  LAYER 2: CDP Tab Injection                             │
│  (background daemon thread, started after startup)      │
│                                                         │
│  Input:  preferred port, actual port, host              │
│  Loop:                                                  │
│    1. cdp_client.get_targets()                          │
│    2. Filter tabs on localhost:{preferred_port}          │
│    3. For each un-injected tab:                         │
│       evaluate_js() → inject DCP banner                 │
│    4. Track injected target IDs (one-shot per tab)      │
│    5. Sleep 10s                                         │
│                                                         │
│  Works on: HTML pages, JSON viewer, error pages,        │
│            anything Chrome renders as a tab              │
└─────────────────────────────────────────────────────────┘
```

### Why a Background Thread (not one-shot)

The user might not have a tab on port 8000 at DCP startup.
They might open one later. The thread catches new tabs as
they appear. It's lightweight — one `get_targets()` call
every 10 seconds, no injection if no new tabs.

### New Files

| File | Purpose |
|------|---------|
| `src/core/services/cdp_port_injector.py` | Layer 2: background thread + injection logic |

### Modified Files

| File | Change |
|------|--------|
| `src/core/services/server_lifecycle.py` | Layer 1: add `identify_port_occupant()` function |
| `src/ui/web/server.py` | Call both layers during fallback detection |

### No Changes Needed

| File | Why |
|------|-----|
| `src/ui/web/cdp_client.py` | Existing API is sufficient |

---

## Layer 1: Port Intelligence

### `identify_port_occupant(host, port)` in `server_lifecycle.py`

```python
def identify_port_occupant(host: str, port: int) -> dict[str, Any]:
    """Identify what process is holding a TCP port.

    Uses `ss -tlnp` (no root needed for own-user processes)
    with fallback to `lsof -i`.

    Returns:
        {
            "pid": 4521,           # or None
            "name": "node",        # or None
            "cmdline": "node ./server.js",  # or None
        }

    All fields may be None if detection fails (not an error —
    the port is still occupied, we just can't identify who).
    """
    import subprocess
    import re

    result = {"pid": None, "name": None, "cmdline": None}

    # Try ss first (available on most Linux)
    try:
        out = subprocess.run(
            ["ss", "-tlnp", f"sport = :{port}"],
            capture_output=True, text=True, timeout=3,
        )
        # Parse: users:(("node",pid=4521,fd=19))
        match = re.search(
            r'users:\(\("([^"]+)",pid=(\d+)',
            out.stdout,
        )
        if match:
            result["name"] = match.group(1)
            result["pid"] = int(match.group(2))
    except Exception:
        pass

    # Try lsof as fallback
    if result["pid"] is None:
        try:
            out = subprocess.run(
                ["lsof", "-i", f":{port}", "-sTCP:LISTEN", "-t"],
                capture_output=True, text=True, timeout=3,
            )
            pid_str = out.stdout.strip().split("\n")[0]
            if pid_str.isdigit():
                result["pid"] = int(pid_str)
        except Exception:
            pass

    # Get cmdline from /proc if we have PID
    if result["pid"]:
        try:
            cmdline_path = f"/proc/{result['pid']}/cmdline"
            raw = Path(cmdline_path).read_bytes()
            result["cmdline"] = raw.replace(b"\x00", b" ").decode(
                "utf-8", errors="replace"
            ).strip()
            if not result["name"]:
                result["name"] = result["cmdline"].split()[0].rsplit("/", 1)[-1]
        except Exception:
            pass

    return result
```

### Integration in `server.py`

The existing `PORT_FALLBACK` dict gets enriched:

```python
# Current (already in server.py):
app.config["PORT_FALLBACK"] = {
    "active": True,
    "preferred_port": web_cfg.port,
    "actual_port": resolved_port,
    "host": host,
    "config_path": "project.yml",
}

# Enhanced (add occupant info):
from src.core.services.server_lifecycle import identify_port_occupant
occupant = identify_port_occupant(host, web_cfg.port)

app.config["PORT_FALLBACK"] = {
    "active": True,
    "preferred_port": web_cfg.port,
    "actual_port": resolved_port,
    "host": host,
    "config_path": "project.yml",
    "occupant_pid": occupant["pid"],
    "occupant_name": occupant["name"],
    "occupant_cmd": occupant["cmdline"],
}
```

### Frontend Enhancement (fallback banner)

The existing banner text changes from:

> Port 8000 was occupied — running on port 8001.

To:

> Port 8000 held by **node** (PID 4521) — DCP running on port 8001.

If process info is unavailable:

> Port 8000 occupied by another process — DCP running on port 8001.

---

## Layer 2: CDP Tab Injection

### The Injected Banner (JavaScript)

Injected via `cdp_client.evaluate_js()` into ANY Chrome tab
pointing at `localhost:{preferred_port}`:

```javascript
(function() {
    if (document.getElementById('__dcp_port_banner')) return 'already_injected';
    if (!document.body) return 'no_body';

    var banner = document.createElement('div');
    banner.id = '__dcp_port_banner';
    banner.style.cssText = [
        'position:fixed',
        'top:0',
        'left:0',
        'right:0',
        'z-index:2147483647',
        'background:linear-gradient(135deg, #1e1b4b 0%, #312e81 100%)',
        'color:#e0e7ff',
        'font-family:system-ui,-apple-system,sans-serif',
        'font-size:13px',
        'padding:10px 16px',
        'display:flex',
        'align-items:center',
        'justify-content:space-between',
        'gap:12px',
        'box-shadow:0 2px 12px rgba(0,0,0,0.4)',
        'border-bottom:2px solid rgba(129,140,248,0.4)',
    ].join(';');

    banner.innerHTML =
        '<div style="display:flex;align-items:center;gap:10px">' +
            '<span style="font-size:18px">⚡</span>' +
            '<div>' +
                '<div style="font-weight:600;font-size:13px">' +
                    'DevOps Control Plane' +
                '</div>' +
                '<div style="font-size:12px;opacity:0.85;margin-top:2px">' +
                    'Admin panel is running on ' +
                    '<a href="http://${HOST}:${PORT}" ' +
                       'style="color:#a5b4fc;text-decoration:underline;' +
                       'font-weight:600" target="_self">' +
                        'localhost:${PORT}' +
                    '</a>' +
                '</div>' +
            '</div>' +
        '</div>' +
        '<button onclick="this.parentElement.remove()" ' +
            'style="background:rgba(255,255,255,0.1);border:1px solid ' +
            'rgba(255,255,255,0.2);color:#c7d2fe;cursor:pointer;' +
            'font-size:12px;padding:4px 10px;border-radius:4px">' +
            'Dismiss' +
        '</button>';

    document.body.insertBefore(banner, document.body.firstChild);
    return 'injected';
})()
```

This works on:
- **HTML pages** — normal injection
- **JSON API responses** — Chrome wraps JSON in a `<pre>` inside `<body>`, banner appears above
- **Error pages** — Chrome's "site can't be reached" has a body, banner appears
- **Blank pages** — `about:blank` has a body too

### The Injector Module (`cdp_port_injector.py`)

```python
"""
CDP Port Injector — injects a DCP notification banner into
Chrome tabs pointing at a port occupied by a foreign process.

Only active during fallback mode. Only targets non-DCP processes
(DCP instances are handled by the internal notification system
and PID takeover in server_lifecycle.py).

Chrome renders everything as a page — HTML, JSON, error pages
all have document.body. CDP can inject into all of them.
"""

import logging
import threading

logger = logging.getLogger(__name__)

POLL_INTERVAL    = 10   # seconds between scans
MAX_CDP_FAILURES = 5    # consecutive failures before backing off
BACKOFF_INTERVAL = 60   # seconds after backing off

_stop_event: threading.Event | None = None
_thread: threading.Thread | None = None


def _build_injection_js(host: str, port: int) -> str:
    """Build the JS payload with actual host:port values."""
    # Template is defined in-module (see banner JS above)
    return _JS_TEMPLATE.replace("${HOST}", host).replace(
        "${PORT}", str(port)
    )


def _injector_loop(
    host: str,
    preferred_port: int,
    actual_port: int,
    stop_event: threading.Event,
) -> None:
    """Background loop: find tabs on preferred port, inject banner."""
    consecutive_failures = 0
    injected_targets: set[str] = set()

    while not stop_event.is_set():
        interval = (
            BACKOFF_INTERVAL
            if consecutive_failures >= MAX_CDP_FAILURES
            else POLL_INTERVAL
        )

        try:
            from src.ui.web import cdp_client

            if not cdp_client.is_available():
                consecutive_failures += 1
                stop_event.wait(interval)
                continue

            targets = cdp_client.get_targets()
            port_pattern = f"localhost:{preferred_port}"

            candidates = [
                t for t in targets
                if t.get("type") == "page"
                and port_pattern in (t.get("url") or "")
                and t["id"] not in injected_targets
            ]

            for target in candidates:
                ws_url = target.get("webSocketDebuggerUrl")
                if not ws_url:
                    continue

                js = _build_injection_js(host, actual_port)
                result = cdp_client.evaluate_js(ws_url, js, timeout=3.0)

                if result:
                    value = (
                        result.get("result", {})
                              .get("result", {})
                              .get("value")
                    )
                    if value in ("injected", "already_injected"):
                        injected_targets.add(target["id"])
                        logger.info(
                            "CDP: injected DCP banner → %s",
                            target.get("url", "?")[:80],
                        )

            consecutive_failures = 0

            # Prune closed tabs
            current_ids = {t["id"] for t in targets}
            injected_targets &= current_ids

        except Exception as exc:
            consecutive_failures += 1
            logger.debug("CDP injector error: %s", exc)

        stop_event.wait(interval)


def start_injector(
    host: str,
    preferred_port: int,
    actual_port: int,
) -> None:
    """Start the CDP port injector as a daemon thread.

    Safe to call even if CDP is not available — the thread
    will back off and retry periodically.
    """
    global _stop_event, _thread

    if _thread and _thread.is_alive():
        logger.debug("CDP injector already running")
        return

    _stop_event = threading.Event()
    _thread = threading.Thread(
        target=_injector_loop,
        args=(host, preferred_port, actual_port, _stop_event),
        daemon=True,
        name="cdp-port-injector",
    )
    _thread.start()
    logger.info(
        "CDP port injector started (watching tabs on :%d, "
        "redirecting to :%d)",
        preferred_port, actual_port,
    )


def stop_injector() -> None:
    """Stop the injector thread (if running)."""
    global _stop_event
    if _stop_event:
        _stop_event.set()
```

### Integration in `server.py`

After the existing fallback detection block:

```python
if is_fallback:
    # ... existing notification code ...

    # Layer 2: CDP injection into foreign tabs
    try:
        from src.core.services.cdp_port_injector import start_injector
        start_injector(
            host=host,
            preferred_port=web_cfg.port,
            actual_port=resolved_port,
        )
    except Exception as exc:
        logger.debug("CDP port injector: %s", exc)
```

---

## Scenarios

| Scenario | Layer 1 (Our Banner) | Layer 2 (CDP Injection) |
|----------|---------------------|------------------------|
| Port 8000 = React dev, tabs open | "Port 8000 held by **node** (PID 4521)" | Banner injected into React page |
| Port 8000 = Django, tabs open | "Port 8000 held by **python** (PID 3201)" | Banner injected into Django page |
| Port 8000 = API, user viewing JSON in tab | "Port 8000 held by **uvicorn** (PID 5001)" | Banner injected above JSON viewer |
| Port 8000 = API, no tabs | "Port 8000 held by **uvicorn** (PID 5001)" | Nothing to inject — no tabs |
| Port 8000 = non-HTTP (postgres) | "Port 8000 held by **postgres** (PID 2001)" | Nothing to inject — no tabs |
| Port 8000 = process, tabs open showing error | "Port 8000 held by **???**" | Banner injected into Chrome error page |
| CDP not available | Full info still shown | Thread backs off, retries every 60s |
| Another DCP instance | Handled by `_try_takeover()` — never reaches this code | N/A |
| User opens tab on :8000 after DCP start | Already enriched from startup | Thread catches new tab within 10s |
| User dismisses CDP banner | N/A | One-shot: not re-injected for same tab |

---

## Dismissal: One-Shot Per Target ID (Option C)

- Track injected tab IDs in a `set()`
- Never re-inject into the same target (even if banner was dismissed)
- New navigation on same port = new Chrome target ID = new injection
- No persistent window flags needed
- Simplest, most respectful approach

---

## Implementation Steps

1. **Add `identify_port_occupant()` to `server_lifecycle.py`**
   - `ss -tlnp` with `lsof` fallback
   - Returns `{pid, name, cmdline}`

2. **Enrich `PORT_FALLBACK` in `server.py`**
   - Call `identify_port_occupant()` during fallback detection
   - Add `occupant_pid`, `occupant_name`, `occupant_cmd` to config dict

3. **Update fallback banner in `_notifications.html`**
   - Show process name and PID when available

4. **Create `src/core/services/cdp_port_injector.py`**
   - `_build_injection_js(host, port)`
   - `_injector_loop(host, preferred_port, actual_port, stop_event)`
   - `start_injector()` / `stop_injector()`

5. **Start injector in `server.py`**
   - After fallback detection, call `start_injector()`

6. **Test manually**
   - `python -m http.server 8000` → start DCP → falls back to 8001
   - Open `localhost:8000` → see DCP banner injected
   - Open `localhost:8000/some-api` → see banner above JSON
   - Check our panel → see "Port 8000 held by python (PID XXXX)"

---

## Future Parking Lot

- Settings toggle: "CDP port injection" on/off
- Desktop notification via OS for non-browser scenarios
- Banner style customization
