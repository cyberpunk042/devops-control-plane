# WSL↔Windows Interop Channel — Detection, Remediation, Operability

## Status: DRAFT — Awaiting Review

---

## Problem Statement

The system currently uses `curl.exe` (Windows-side binary) as a **workaround** to bridge
the WSL2↔Windows network gap for CDP communication. This workaround is:

1. **Silent when it fails** — if `curl.exe` is missing, CDP silently returns `None` everywhere
2. **Not the real fix** — the proper solution is making the WSL↔Windows channel
   speak correctly even without `networkingMode=mirrored`
3. **Monolithic** — all failures are lumped under "CDP unavailable" with no granularity

The user's request is to decompose this into **independent failure points**, each with its
own detection, notification (deduplicated), remediation steps, and validation — and to
report operability levels so the user knows what works NOW and what COULD work.

---

## Architecture: Independent Failure Layers

These are NOT one big umbrella — each is a **separate concern** that can fail independently,
be detected independently, and be remediated independently.

### Layer 0: WSL Detection (Foundation)
- **What:** Is this even a WSL environment?
- **Current state:** ✅ Detected (`is_wsl()` in `detection.py`, `_detect_wsl_interop()` in `l0_hw_detectors.py`)
- **What exists:** `/proc/version` check, `powershell.exe` availability, `binfmt_misc`, Windows username, `.wslconfig` path
- **Gap:** `.wslconfig` **contents** are not parsed — we don't know if `networkingMode=mirrored` is set

### Layer 1: Networking Mode Detection
- **What:** What WSL2 networking mode is active? (NAT vs mirrored)
- **Current state:** ❌ Not detected
- **Why it matters:**
  - `networkingMode=mirrored` → localhost works natively → NO curl.exe needed, NO hostname.local needed, NO firewall rule needed
  - NAT mode (default) → localhost in WSL ≠ localhost on Windows → need bridge
- **Detection method:** Parse `.wslconfig` for `[wsl2]` → `networkingMode=mirrored`
  - Also: test if `localhost:9222` is reachable directly via Python socket (if it is, mirrored is likely active even without explicit config)
- **⚠️ IMPORTANT: `networkingMode=mirrored` is a RISKY ALTERNATIVE, not the recommended fix.**
  It can break VS Code Remote-WSL, IDE networking, and other WSL2 integrations.
  The recommended path is **hostname.local + firewall rule** (Layer 2 + Layer 3).
  Mirrored mode should be presented as an option with clear warnings about the side effects.
- **Remediation:** Present as alternative with explicit risk warnings — "may break VS Code, IDE networking"
- **Severity:** Normal notification (informational, NOT recommended — just detected)
- **Notification type:** `wsl_networking_mode` (dedup=True)

### Layer 2: Hostname mDNS Resolution (`$(hostname).local`)
- **What:** Can WSL2 resolve the Windows host via `$(hostname).local`?
- **Current state:** ❌ Not detected, not used
- **Why it matters:** This is the PROPER alternative to curl.exe in NAT mode. If hostname.local
  resolves correctly, Python in WSL can directly reach Chrome's debug port on Windows
  WITHOUT curl.exe — just use `http://HOSTNAME.local:9222/json/version`
- **Detection method:**
  1. `hostname` command → capture hostname (e.g. "DESKTOP-ABC123")
  2. Test: `socket.getaddrinfo("DESKTOP-ABC123.local", 9222)` — does it resolve?
  3. Test: actual HTTP GET to `http://DESKTOP-ABC123.local:9222/json/version`
- **Remediation (if resolution fails):**
  - Check if mDNS responder is running on Windows (Bonjour / mDNS service)
  - Usually works out of the box on modern Windows 10/11
  - If not: guide user to enable mDNS or use the gateway IP approach
- **Severity:** Normal notification if unused but fixable
- **Notification type:** `wsl_hostname_resolution` (dedup=True)

### Layer 3: Windows Firewall Rule (Port Access)
- **What:** Is there a Windows firewall rule allowing inbound TCP to the CDP port from WSL?
- **Current state:** ❌ Not detected, not managed
- **Why it matters:** Even if hostname.local resolves, the Windows firewall may BLOCK
  connections from the WSL2 virtual network interface to Chrome's debug port
- **Detection method:**
  - `powershell.exe -Command "Get-NetFirewallRule -DisplayName 'WSL_CDP_Access' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Enabled"`
  - Or: attempt a TCP connect to confirm it's not blocked
- **Remediation:**
  ```powershell
  New-NetFirewallRule -DisplayName "WSL_CDP_Access" -Direction Inbound `
    -InterfaceAlias "vEthernet (WSL)" -Action Allow `
    -Protocol TCP -LocalPort 9222
  ```
  - Requires elevated PowerShell
  - Use existing `modify_shortcut_elevated()` pattern from `shortcuts.py`
- **Severity:** Normal notification (one-time, deduped)
- **Notification type:** `wsl_firewall_rule` (dedup=True)

### Layer 4: Chrome Binding Address
- **What:** Is Chrome bound to `0.0.0.0` or just `127.0.0.1`?
- **Current state:** ⚠️ Partially handled — Chrome is launched with `--remote-debugging-port=9222`
  which binds to `127.0.0.1` by default
- **Why it matters:** If we fix layers 2+3 (hostname + firewall), Chrome still needs to bind
  to `0.0.0.0` or the specific vEthernet interface to accept connections from WSL
- **Note:** For `$(hostname).local` to work, Chrome may need `--remote-debugging-address=0.0.0.0`
  (security consideration — only on trusted networks)
- **Detection method:** Part of the end-to-end validation
- **Remediation:** Add `--remote-debugging-address=0.0.0.0` to the Chrome shortcut args
  (same infrastructure as existing shortcut remediation in `cdp-remediate`)
- **Severity:** Handled as part of the shortcut remediation flow

### Layer 5: curl.exe Availability (FALLBACK — Current Workaround)
- **What:** Is `curl.exe` available as a fallback bridge?
- **Current state:** ⚠️ Detected (`get_curl_exe()`) but SILENT when missing
- **Why it matters:** If layers 2–4 are not resolved, curl.exe is the ONLY way CDP works.
  If it's also missing → CDP is completely broken with NO explanation
- **Detection method:** `shutil.which("curl.exe")` (already exists)
- **Remediation: see §Robust Fallback Chain below** — must survive any single failure
- **Severity:**
  - **Imminent/instant** IF layers 2–4 are not resolved (it's the only working path)
  - **Normal** if layers 2+3 are resolved (curl.exe is just a nice-to-have at that point)
- **Notification type:** `wsl_curl_exe_missing` (dedup=True)

### Layer 6: End-to-End Validation
- **What:** Does the full CDP channel work?
- **Current state:** ✅ Exists (`try_discover_endpoint()` in `cdp_client.py`)
- **What exists:** Tries localhost → resolv.conf nameserver → default gateway
- **Gap:** Does NOT try `$(hostname).local`, does NOT report WHY it failed

---

## Operability Levels (User-Facing)

The system should report the current operability level and what's needed to reach the next:

| Level | Name | Requirements | Capabilities |
|-------|------|-------------|--------------|
| 0 | **No CDP** | No Chrome or no debug flags | URL-only navigation, no tab focus |
| 1 | **curl.exe Bridge** | Chrome w/ debug + curl.exe available | Full CDP via curl.exe (slower, ~100ms per call) |
| 2 | **Direct Channel** ✅ recommended | Chrome w/ debug + hostname.local + firewall rule | Full CDP via direct socket (fast, ~5ms per call) |
| 3 | **Mirrored Network** ⚠️ risky | `networkingMode=mirrored` in .wslconfig | Native localhost (zero overhead, but may break VS Code/IDE networking) |
| N/A | **Native Linux** | Not WSL (direct Chrome on Linux) | Full CDP natively |

**Level 2 (Direct Channel) is the recommended target.** It works with the default WSL2 NAT
networking and doesn't break any IDE integrations. Level 3 (mirrored) is faster but carries
real risk of breaking VS Code Remote-WSL and other tools that depend on WSL's default
networking behavior.

These are **NOT mutually exclusive steps to implement** — they're reporting levels.
The system detects which level is currently active and surfaces what's available.

---

## curl.exe Remediation — Robust Fallback Chain

curl.exe is the fallback bridge. If layers 2–4 aren't resolved, it's the ONLY path.
So if we need to install it, we **must** have multiple fallback strategies.
If one method fails, the next must be tried. No single point of failure.

### Step 0: Verify It's Not a PowerShell Alias

PowerShell aliases `curl` to `Invoke-WebRequest`. This is NOT the same as `curl.exe`.
```powershell
# Check if curl.exe is a real binary or an alias
Get-Command curl.exe -ErrorAction SilentlyContinue | Select-Object Source, CommandType
```
- If `CommandType` is `Application` and `Source` points to a real `.exe` → curl.exe exists
- If it doesn't exist or is an alias → proceed to install

Note: `curl.exe` has been included in Windows 10 since build 17063 (January 2018).
It should be present at `C:\Windows\System32\curl.exe` on any remotely modern Windows.
If it's missing, the system install may be damaged or it was manually removed.

### Step 1: winget (Preferred — Built into Windows 11 / Windows 10 1709+)
```powershell
winget install --id curl.curl --accept-source-agreements --accept-package-agreements
```
- **Detection:** `powershell.exe -Command "Get-Command winget -ErrorAction SilentlyContinue"`
- **Pros:** Built into modern Windows, no prerequisites
- **Cons:** Not available on older Windows 10, may require Microsoft Store update
- **If this fails → Step 2**

### Step 2: scoop (Lightweight — No Elevation Required)
```powershell
# Check if scoop is installed
Get-Command scoop -ErrorAction SilentlyContinue
# If not installed, install scoop first (no admin needed):
irm get.scoop.sh | iex
# Then install curl:
scoop install curl
```
- **Detection:** `powershell.exe -Command "Get-Command scoop -ErrorAction SilentlyContinue"`
- **Pros:** No admin elevation needed, portable
- **Cons:** Requires PowerShell execution policy to allow scripts
- **If this fails → Step 3**

### Step 3: chocolatey (Requires Elevation)
```powershell
# Check if choco is installed
Get-Command choco -ErrorAction SilentlyContinue
# If available:
choco install curl -y
```
- **Detection:** `powershell.exe -Command "Get-Command choco -ErrorAction SilentlyContinue"`
- **Pros:** Very widely installed in enterprise/dev environments
- **Cons:** Requires admin elevation for install
- **If this fails → Step 4**

### Step 4: Direct Binary Download (No Package Manager)
```powershell
# Download curl binary directly from the official site
$url = "https://curl.se/windows/latest.cgi?p=win64-mingw.zip"
$zip = "$env:TEMP\curl.zip"
$dest = "$env:LOCALAPPDATA\curl"
Invoke-WebRequest -Uri $url -OutFile $zip
Expand-Archive -Path $zip -DestinationPath $dest -Force
# Add to user PATH (non-elevated)
$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if ($userPath -notlike "*$dest*") {
    [Environment]::SetEnvironmentVariable('Path', "$userPath;$dest\curl*\bin", 'User')
}
```
- **Detection:** Always available if PowerShell works (uses `Invoke-WebRequest`)
- **Pros:** Zero prerequisites beyond PowerShell, no elevation needed for user-level install
- **Cons:** Download from internet, user PATH modification
- **If this fails → Step 5**

### Step 5: Manual Guidance (Last Resort)
If all automated methods fail, provide clear manual instructions:
- "Download curl from https://curl.se/windows/"
- "Extract to C:\Program Files\curl\"
- "Add ... to your system PATH"
- "Restart WSL and verify with `curl.exe --version`"

### Validation (After Any Successful Step)
```bash
# From WSL:
curl.exe --version
# Expected: curl X.Y.Z (Windows) ...
```
If validation passes → dismiss the notification, update operability level.
If validation fails → log the failure, try next step in the chain.

### Data Model for curl.exe Install Plan

Follows the existing `install_plan` pattern from `_build_chrome_install_plan()`
but with robust per-step availability detection:

```python
{
    "tool": "curl.exe",
    "context": "wsl_interop",
    "steps": [
        {
            "id": "check_existing",
            "label": "Verify curl.exe is not a PowerShell alias",
            "type": "auto",
            "command": 'powershell.exe -Command "(Get-Command curl.exe -EA SilentlyContinue).Source"',
            "availability": "ready",  # always available if powershell works
        },
        {
            "id": "winget_install",
            "label": "Install via winget (recommended)",
            "type": "semi-auto",
            "command": "powershell.exe -Command \"winget install --id curl.curl ...\"",
            "availability": "ready" | "locked",  # locked if winget not found
            "lock_reason": "winget not available on this Windows version",
            "needs_elevation": False,
        },
        {
            "id": "scoop_install",
            "label": "Install via scoop (no elevation needed)",
            "type": "semi-auto",
            "command": "powershell.exe -Command \"scoop install curl\"",
            "availability": "ready" | "locked",  # locked if scoop not found
            "lock_reason": "scoop not installed",
            "unlock_command": 'powershell.exe -Command "irm get.scoop.sh | iex"',
            "needs_elevation": False,
        },
        {
            "id": "choco_install",
            "label": "Install via Chocolatey",
            "type": "semi-auto",
            "command": "powershell.exe -Command \"choco install curl -y\"",
            "availability": "ready" | "locked",  # locked if choco not found
            "lock_reason": "Chocolatey not installed",
            "needs_elevation": True,
        },
        {
            "id": "direct_download",
            "label": "Download binary from curl.se (always available)",
            "type": "semi-auto",
            "command": "powershell.exe -File <generated_download_script>",
            "availability": "ready",  # always available
            "needs_elevation": False,
        },
        {
            "id": "manual",
            "label": "Manual installation",
            "type": "manual",
            "instructions": "Download from https://curl.se/windows/ ...",
            "availability": "ready",  # always available
        },
    ],
    "can_auto_install": True,
    "validate": "curl.exe --version",
}
```

Each step's `availability` is computed at detection time by checking if the
relevant package manager exists on the Windows side via PowerShell.

---

## Detection Data Model (Enriched WSL Interop)

Current `_detect_wsl_interop()` returns:
```python
{
    "available": bool,       # powershell.exe found
    "binfmt_registered": bool,
    "windows_user": str | None,
    "wslconfig_path": str | None,
}
```

Proposed enrichment (new fields):
```python
{
    # ... existing fields ...

    # Layer 1: Networking mode
    "networking_mode": "nat" | "mirrored" | "unknown",
    "wslconfig_parsed": {
        "networkingMode": "mirrored" | None,
        # other relevant .wslconfig keys as discovered
    } | None,

    # Layer 2: Hostname resolution
    "hostname": str | None,              # e.g. "DESKTOP-ABC123"
    "hostname_local_resolves": bool,     # does DESKTOP-ABC123.local resolve?
    "hostname_local_ip": str | None,     # resolved IP if it works

    # Layer 3: Firewall  (expensive — only run on demand)
    # Not in the deep detector — this would be in the diagnose endpoint

    # Layer 5: curl.exe
    "curl_exe_available": bool,
    "curl_exe_path": str | None,

    # Computed operability level
    "cdp_operability_level": 0 | 1 | 2 | 3,
}
```

**Note:** Firewall detection requires `powershell.exe` and is slow (~1s).
It belongs in the **diagnose endpoint** (`cdp_diagnose()`), NOT in the deep detector
that runs in the background.

---

## Notification Strategy

Each independent concern gets its own notification type with `dedup=True`:

| Notification Type | Title | Severity | When Created |
|---|---|---|---|
| `wsl_networking_mode` | "WSL Networking: Mirrored Mode Detected" or "NAT Mode Active" | Informational | When mode is detected — informational only, NOT a suggestion to change (risky) |
| `wsl_hostname_resolution` | "hostname.local Not Resolving" | Normal | When hostname.local is expected to work but doesn't |
| `wsl_firewall_rule` | "Windows Firewall Blocking CDP" | Normal | When hostname.local works but connection is refused |
| `wsl_curl_exe_missing` | "CDP Bridge Unavailable" | **Imminent** | When curl.exe is missing AND no direct channel works |
| `chrome_missing` | "Chrome Not Installed" | Imminent | Already exists (L117–149 in tab_mesh) |
| `cdp_suggestion` | "Enable Tab Focus" | Normal | Already exists (L727–757 in tab_mesh) |

**Rules:**
- `dedup=True` for all — notify once, not twice
- Each notification includes its own `meta.remediation_steps` for UI to render
- Each notification includes `meta.layer` so the UI can group/prioritize
- Imminent notifications get `meta.priority = "imminent"` for different UI treatment
- The `wsl_networking_mode` notification is informational — it does NOT suggest switching to mirrored
  (unlike the others which offer actionable remediation). Mirrored is a risky alternative.

---

## Implementation Phases

### Phase 1: Detection Enrichment (Non-Breaking)

**Files:**
- `src/core/services/audit/l0_hw_detectors.py` — enrich `_detect_wsl_interop()`
- `src/core/services/chrome/detection.py` — add hostname resolution detection

**Changes:**
1. Parse `.wslconfig` contents (if path exists) — extract `networkingMode`
2. Detect hostname: `subprocess.run(["hostname"], capture_output=True)`
3. Test `hostname.local` resolution: `socket.getaddrinfo(hostname + ".local", None)`
4. Add `curl_exe_available` + `curl_exe_path` to interop result
5. Compute `cdp_operability_level`

**No behavior change** — just richer detection data.

### Phase 2: Diagnostic Endpoint Enrichment

**Files:**
- `src/ui/web/routes/tab_mesh/__init__.py` — enrich `cdp_diagnose()`

**Changes:**
1. Add `curl_exe_available` to diagnostic output
2. Add `hostname_local` detection to diagnostic output
3. Add `networking_mode` to diagnostic output
4. Add firewall rule check (PowerShell, slow — only in this endpoint)
5. Add `operability_level` to diagnostic output
6. Add per-layer `remediation` dicts in the response

### Phase 3: Independent Notifications

**Files:**
- `src/ui/web/routes/tab_mesh/__init__.py` — new or enhanced endpoints

**Changes:**
1. When `cdp_diagnose()` runs, create independent notifications for each detected gap
2. Each notification has its own `notif_type` (dedup prevents duplicates)
3. Notifications include remediation steps specific to their concern
4. Priority: imminent for blocking failures, normal for upgrade opportunities

### Phase 4: Remediation Actions

**Files:**
- `src/core/services/chrome/detection.py` — hostname.local testing
- `src/ui/web/routes/tab_mesh/__init__.py` — new remediation endpoints

**New endpoints:**
1. `POST /tab-mesh/wsl-fix-firewall` — Create/verify firewall rule via elevated PowerShell
2. `POST /tab-mesh/wsl-test-hostname` — Test hostname.local resolution + connectivity
3. `POST /tab-mesh/wsl-set-mirrored` — Modify .wslconfig to add mirrored networking
4. `POST /tab-mesh/wsl-install-curl` — Install curl.exe via winget (fallback)
5. `POST /tab-mesh/wsl-validate` — End-to-end validation: test all layers, report status

### Phase 5: CDP Client Channel Enhancement

**Files:**
- `src/ui/web/cdp_client.py` — `try_discover_endpoint()`

**Changes:**
1. Add `$(hostname).local` as a discovery step (between resolv.conf and gateway)
2. When hostname.local works → use it as the primary endpoint (faster than curl.exe)
3. Log which channel was used for transparency
4. Fall back to curl.exe ONLY when direct channels fail

### Phase 6: Launcher Integration

**Files:**
- `src/core/services/chrome/launcher.py`

**Changes:**
1. `_port_in_use()` — try hostname.local before falling back to curl.exe
2. `_cdp_responding()` — same
3. Log warnings when falling back to curl.exe (instead of silently using it)
4. Surface the active channel in `ChromeInstance` metadata

---

## Existing Infrastructure to Leverage

| What | Where | How |
|---|---|---|
| WSL detection | `detection.py:is_wsl()` | Foundation — reuse |
| Windows user | `detection.py:get_windows_user()` | Reuse for .wslconfig path |
| curl.exe cache | `detection.py:get_curl_exe()` | Enhance, add logging |
| WSL interop detection | `l0_hw_detectors.py:_detect_wsl_interop()` | Enrich with new fields |
| .wslconfig path | `l0_hw_detectors.py` L329–338 | Enhance to parse contents |
| Notification system | `notifications.py:create_notification()` | Use with `dedup=True` per type |
| Notification dedup | `notifications.py` L175–183 | Already handles same-type dedup |
| Elevated PowerShell | `shortcuts.py:modify_shortcut_elevated()` | Reuse pattern for firewall |
| CDP discovery | `cdp_client.py:try_discover_endpoint()` | Enhance with hostname.local |
| Chrome shortcut args | `cdp_remediate()` in tab_mesh | Extend for `--remote-debugging-address` |
| Install plan pattern | `launcher.py:require_chrome()` | Follow same structure |

---

## Risk Assessment

| Risk | Mitigation |
|---|---|
| Firewall rule modification needs elevation | Use existing elevated PS pattern (`modify_shortcut_elevated`) |
| `--remote-debugging-address=0.0.0.0` security | Only set when user explicitly remediates from the UI, document the tradeoff |
| **`networkingMode=mirrored` breaks VS Code / IDE networking** | **Do NOT recommend.** Present as alternative with explicit warnings. Detection only — not remediation. |
| `.wslconfig` modification requires WSL restart | Detect and warn user, offer to do it or defer |
| hostname.local may not work on all Windows configs | Graceful fallback — just don't upgrade the level, curl.exe stays active |
| curl.exe install via winget may not be available | Robust fallback chain: winget → scoop → choco → direct download → manual |
| curl.exe install via scoop/choco may not be available | Each step checks its own prerequisite; direct download (Step 4) always works |
| Multiple notifications could feel spammy | Each is independent, deduped, and only created when relevant |

---

## What This Is NOT

- NOT a refactor of the existing curl.exe bridge (it stays as a working fallback)
- NOT a removal of any existing functionality
- NOT a single umbrella notification — each failure is independent
- NOT blocking the user — everything is informational or offers remediation
