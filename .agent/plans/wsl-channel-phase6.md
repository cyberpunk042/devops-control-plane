# Phase 6: curl.exe Install Plan (Fallback Chain)

## Status: ANALYSIS — Awaiting Review

## Implementation Priority: 7 of 7 (last — least urgent)

---

## What This Phase Delivers

A robust curl.exe installation system with a multi-method fallback chain
and a UI to trigger it. curl.exe is the FALLBACK — Level 1 (slow but
works when nothing else does).

---

## What Already Exists — ALMOST EVERYTHING

### Backend: `POST /tab-mesh/wsl-install-curl` ✅

Full 118-line implementation at `tab_mesh/__init__.py:1277-1395`:

1. **Step 0:** Check if already installed → return early with path + version
2. **Chain execution:** Try each method in order, skip unavailable ones
3. **Per-step tracking:** Records available/attempted/success/error for each
4. **Post-install validation:** `shutil.which("curl.exe")` to confirm
5. **Full response:** Returns the chain with all attempt results

### Backend: `_build_curl_install_chain()` ✅

Four methods already defined at `tab_mesh/__init__.py:1398-1456`:

| # | Method | Detection | Install | Elevation |
|---|--------|-----------|---------|-----------|
| 1 | **winget** | `Get-Command winget` | `winget install --id curl.curl` | No |
| 2 | **scoop** | `Get-Command scoop` | `scoop install curl` | No |
| 3 | **choco** | `Get-Command choco` | `choco install curl -y` | Yes (UAC) |
| 4 | **direct download** | Always available | Download from curl.se, extract, add to PATH | No |

### Detection: `shutil.which("curl.exe")` ✅

Already used in `detection.py:get_curl_exe()` and in
`l0_hw_detectors.py:_detect_wsl_interop()`.

---

## What's Missing

### 6.1: Frontend UI Trigger

No button in the UI calls `POST /tab-mesh/wsl-install-curl`. The endpoint
exists but is unreachable from the user's perspective.

**Fix:** Phase 4 UI adds an [Install curl.exe] button in the prerequisite
section of the WSL Channel setup:

```html
<!-- In _meshRenderWslChannel() -->
<div class="prereq-item" data-prereq="curl_exe">
    <span class="prereq fail">❌ curl.exe not found</span>
    <button class="btn btn-sm" onclick="_wslInstallCurl()">Install</button>
</div>
```

### 6.2: Progress Feedback

The install chain can take 30-120 seconds (especially winget or direct
download). The UI needs progress feedback:

```javascript
function _wslInstallCurl() {
    var btn = event.target;
    btn.disabled = true;
    btn.textContent = 'Installing...';
    
    var statusEl = document.getElementById('curl-install-status');
    statusEl.innerHTML = '<div class="spinner-sm"></div> Trying installation methods...';
    
    fetch('/tab-mesh/wsl-install-curl', { method: 'POST' })
        .then(r => r.json())
        .then(data => {
            if (data.ok) {
                statusEl.innerHTML = 
                    '✅ Installed via ' + data.method + 
                    '<br>Path: ' + data.path;
                // Refresh the channel status
                _wslRescan();
            } else {
                statusEl.innerHTML = 
                    '❌ ' + data.message +
                    _renderAttemptDetails(data.attempts);
            }
        });
}

function _renderAttemptDetails(attempts) {
    // Show which methods were tried, which failed, why
    var html = '<div class="install-attempts">';
    for (var i = 0; i < attempts.length; i++) {
        var a = attempts[i];
        var icon = a.success ? '✅' : a.attempted ? '❌' : '⏭️';
        html += '<div class="attempt-item">' + icon + ' ' + a.label;
        if (a.error) html += ' — ' + a.error;
        html += '</div>';
    }
    return html + '</div>';
}
```

### 6.3: Manual Install Guidance

If all automated methods fail, the UI should show manual install steps:

```html
<div class="manual-install-guide">
    <div class="guide-title">Manual Installation</div>
    <ol>
        <li>Download curl from <a href="https://curl.se/windows/" target="_blank">curl.se/windows/</a></li>
        <li>Extract to a folder (e.g. C:\Users\YOU\curl)</li>
        <li>Add the bin folder to your Windows PATH</li>
        <li>Restart WSL: <code>wsl --shutdown</code> then reopen</li>
    </ol>
    <button class="btn btn-sm" onclick="_wslRescan()">Re-scan after install</button>
</div>
```

### 6.4: Integration with Existing Install Plan System

The project already has an install plan system (`installWithPlan()` in
the frontend, recipe-based with progress modal). We could integrate
curl.exe as a recipe, OR keep the standalone endpoint.

**Decision: Keep standalone.** The existing install plan system is
designed for Python/pip packages inside the project. curl.exe is a
Windows binary — different lifecycle, different install methods.
The standalone endpoint with its own fallback chain is the right design.

---

## Interconnection with Other Phases

| Phase | How Phase 6 Connects |
|-------|--------------------|
| Phase 1 | If tunnel fails and curl.exe is missing → Level 0 (no CDP at all) |
| Phase 4 | [Install curl.exe] button in WSL Channel section calls the endpoint |
| Phase 5 | `wsl_curl_exe_missing` notification has imminent severity when no fallback |
| Phase 7 | Validation re-checks curl.exe after install |

**curl.exe is the SAFETY NET.** Even if the tunnel isn't set up, curl.exe
at Level 1 lets CDP work. Losing both means Level 0 — no CDP at all.

---

## Files Modified

| File | Action | What |
|------|--------|------|
| `src/ui/web/templates/scripts/_tab_mesh_panel.html` | **MODIFY** | Add `_wslInstallCurl()`, `_renderAttemptDetails()` in Phase 4 code |

No backend changes needed — the endpoint and chain are complete.

---

## Testing Plan

| # | Test | What It Verifies |
|---|------|-----------------|
| 1 | `test_curl_already_installed` | Returns early with path + version |
| 2 | `test_winget_available` | Winget detection and install attempt |
| 3 | `test_scoop_available` | Scoop detection and install attempt |
| 4 | `test_choco_elevated` | Chocolatey with UAC elevation |
| 5 | `test_direct_download` | Download from curl.se, extract, PATH |
| 6 | `test_all_methods_fail` | Returns all_failed with attempt details |
| 7 | `test_post_install_validation` | shutil.which confirms install worked |
| 8 | Manual: UI button | Click [Install] → spinner → result |
| 9 | Manual: full failure | All automated fail → manual guide shown |

**Note:** Tests 2-5 are integration tests requiring Windows. Unit tests
mock the subprocess calls.

---

## Why This Is Priority 7

curl.exe is already installed on most modern Windows systems (Win10 17063+).
The user already has it working (they're at Level 1). This phase is only
needed when:
1. A fresh Windows install without curl.exe
2. curl.exe was removed or corrupted
3. Building the safety net for other users who clone this project

The tunnel (Phase 1) is far more impactful — turning ~2000ms into ~5ms.
