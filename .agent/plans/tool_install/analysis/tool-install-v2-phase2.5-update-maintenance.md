# Tool Install v2 — Phase 2.5: Update & Maintenance

## Context

Phase 2.4 installs tools via plan execution. Phase 2.5 adds the
ability to UPDATE installed tools, detect outdated versions, and
offer maintenance operations (uninstall, reinstall).

### Dependencies

```
Phase 2.2 (recipes)    ── provides: TOOL_RECIPES with `update` field
Phase 2.3 (resolver)   ── provides: resolve_install_plan()
Phase 2.4 (execution)  ── provides: execute_plan(), _run_subprocess()
Phase 2.5 (THIS)       ── provides: update_tool(), check_version(), uninstall_tool()
```

---

## Update Commands Per Install Method

### From domain-package-managers and domain-language-pms

| Install method | Update command | Notes |
|---------------|---------------|-------|
| pip | `pip install --upgrade PKG` | Upgrades in-place |
| pip (venv) | `{venv_pip} install --upgrade PKG` | Uses venv pip |
| npm -g | `npm update -g PKG` | Updates global package |
| cargo | `cargo install PKG` | Re-downloads + recompiles |
| apt | `apt-get install --only-upgrade PKG` | Upgrades single package |
| dnf | `dnf upgrade PKG` | Upgrades single package |
| apk | `apk upgrade PKG` | Upgrades single package |
| pacman | `pacman -S PKG` | Reinstalls latest |
| zypper | `zypper update PKG` | Upgrades single package |
| brew | `brew upgrade PKG` | Upgrades formula |
| snap | `snap refresh PKG` | Upgrades snap |
| rustup | `rustup update` | Updates entire Rust toolchain |
| binary download | Re-run install plan | Re-download from URL |
| bash-curl script | Re-run install script | Scripts usually handle it |

### In TOOL_RECIPES

```python
"ruff": {
    "install": {"_default": [sys.executable, "-m", "pip", "install", "ruff"]},
    "update":  {"_default": [sys.executable, "-m", "pip", "install", "--upgrade", "ruff"]},
    "verify":  ["ruff", "--version"],
    ...
},
"docker": {
    "install": {"debian": ["apt-get", "install", "-y", "docker.io"]},
    "update":  {"debian": ["apt-get", "install", "--only-upgrade", "-y", "docker.io"]},
    "verify":  ["docker", "--version"],
    ...
},
"kubectl": {
    "install": {"snap": ["snap", "install", "kubectl", "--classic"]},
    "update":  {"snap": ["snap", "refresh", "kubectl"]},
    "verify":  ["kubectl", "version", "--client=true"],
    ...
},
"cargo-audit": {
    "install": {"_default": ["cargo", "install", "cargo-audit"]},
    "update":  {"_default": ["cargo", "install", "cargo-audit"]},
    # cargo install with same name = update to latest
    ...
},
```

---

## Version Detection

### How to get the current installed version

```python
VERSION_COMMANDS = {
    # tool_id: (command, regex_to_extract_version)
    "ruff":           (["ruff", "--version"],         r"ruff (\d+\.\d+\.\d+)"),
    "black":          (["black", "--version"],         r"black.*?(\d+\.\d+\.\d+)"),
    "mypy":           (["mypy", "--version"],          r"mypy (\d+\.\d+(?:\.\d+)?)"),
    "pytest":         (["pytest", "--version"],        r"pytest (\d+\.\d+\.\d+)"),
    "docker":         (["docker", "--version"],        r"Docker version (\d+\.\d+\.\d+)"),
    "kubectl":        (["kubectl", "version", "--client=true"],
                                                       r"Client Version:.*?v(\d+\.\d+\.\d+)"),
    "helm":           (["helm", "version", "--short"], r"v(\d+\.\d+\.\d+)"),
    "terraform":      (["terraform", "version"],       r"Terraform v(\d+\.\d+\.\d+)"),
    "git":            (["git", "--version"],            r"git version (\d+\.\d+\.\d+)"),
    "go":             (["go", "version"],               r"go(\d+\.\d+\.\d+)"),
    "node":           (["node", "--version"],            r"v(\d+\.\d+\.\d+)"),
    "cargo":          (["cargo", "--version"],           r"cargo (\d+\.\d+\.\d+)"),
    "rustc":          (["rustc", "--version"],           r"rustc (\d+\.\d+\.\d+)"),
    "gh":             (["gh", "--version"],              r"gh version (\d+\.\d+\.\d+)"),
    "trivy":          (["trivy", "version"],             r"Version: (\d+\.\d+\.\d+)"),
    "hugo":           (["hugo", "version"],              r"v(\d+\.\d+\.\d+)"),
}
```

### get_tool_version()

```python
import re
import shutil
import subprocess

def get_tool_version(tool: str) -> str | None:
    """Get the installed version of a tool. Returns None if not installed."""
    entry = VERSION_COMMANDS.get(tool)
    if not entry:
        return None

    cmd, pattern = entry
    cli = cmd[0]
    if not shutil.which(cli):
        return None

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return None

        output = result.stdout + result.stderr  # some tools write to stderr
        match = re.search(pattern, output)
        if match:
            return match.group(1)
    except (subprocess.TimeoutExpired, Exception):
        pass

    return None
```

---

## Latest Version Detection

### Per install method

| Method | How to get latest | Complexity |
|--------|------------------|-----------|
| pip | `pip index versions PKG` or PyPI JSON API | Easy |
| npm | `npm view PKG version` | Easy |
| apt | `apt-cache policy PKG` | Easy |
| snap | `snap info PKG` | Easy |
| brew | `brew info PKG --json` | Easy |
| cargo | crates.io API | Medium |
| GitHub binary | GitHub Releases API | Medium |
| bash-curl script | No standard way | Hard — skip for now |

### get_latest_version() — pip example

```python
def _pip_latest(package: str) -> str | None:
    """Get latest version from PyPI."""
    try:
        import urllib.request, json
        url = f"https://pypi.org/pypi/{package}/json"
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read())
        return data["info"]["version"]
    except Exception:
        return None
```

### get_latest_version() — apt example

```python
def _apt_latest(package: str) -> str | None:
    """Get latest available version from apt cache."""
    try:
        result = subprocess.run(
            ["apt-cache", "policy", package],
            capture_output=True, text=True, timeout=5,
        )
        match = re.search(r"Candidate:\s+(\S+)", result.stdout)
        if match:
            return match.group(1)
    except Exception:
        pass
    return None
```

### Dispatcher

```python
def get_latest_version(tool: str, install_method: str) -> str | None:
    """Get the latest available version for a tool."""
    LATEST_FETCHERS = {
        "pip": _pip_latest,
        "apt": _apt_latest,
        "snap": _snap_latest,
        "brew": _brew_latest,
        "npm": _npm_latest,
    }
    fetcher = LATEST_FETCHERS.get(install_method)
    if fetcher:
        package = TOOL_RECIPES[tool].get("package_name", tool)
        return fetcher(package)
    return None
```

---

## Version Comparison

### is_outdated()

```python
from packaging.version import Version, InvalidVersion

def is_outdated(current: str, latest: str) -> bool | None:
    """Compare versions. Returns None if comparison not possible."""
    if not current or not latest:
        return None
    try:
        return Version(current) < Version(latest)
    except InvalidVersion:
        # Fall back to string comparison
        return current != latest
```

### Tool status enrichment

```python
def get_tool_status(tool: str) -> dict:
    """Get comprehensive status of an installed tool."""
    cli = TOOL_RECIPES.get(tool, {}).get("cli", tool)
    installed = shutil.which(cli) is not None

    if not installed:
        return {"installed": False, "tool": tool}

    current = get_tool_version(tool)
    install_method = _get_install_method(tool)
    latest = get_latest_version(tool, install_method)
    outdated = is_outdated(current, latest)

    return {
        "installed": True,
        "tool": tool,
        "version": current,
        "latest": latest,
        "outdated": outdated,
        "install_method": install_method,
        "update_available": outdated is True,
    }
```

---

## New Public API

### update_tool()

```python
def update_tool(
    tool: str,
    *,
    sudo_password: str = "",
) -> dict[str, Any]:
    """Update an installed tool to the latest version.

    Args:
        tool: Tool name.
        sudo_password: Sudo password if update needs sudo.

    Returns:
        {"ok": True, "from_version": "...", "to_version": "..."} on success.
    """
    recipe = TOOL_RECIPES.get(tool)
    if not recipe:
        return {"ok": False, "error": f"No recipe for '{tool}'"}

    cli = recipe.get("cli", tool)
    if not shutil.which(cli):
        return {"ok": False, "error": f"{tool} is not installed. Install it first."}

    update_cmd = recipe.get("update")
    if not update_cmd:
        return {"ok": False, "error": f"No update command defined for {tool}"}

    # Get current version before update
    version_before = get_tool_version(tool)

    # Resolve update command for current platform
    cmd = _pick_command(update_cmd, get_system_profile())
    needs_sudo = _pick_sudo(recipe.get("needs_sudo", {}), get_system_profile())

    result = _run_subprocess(
        cmd,
        needs_sudo=needs_sudo,
        sudo_password=sudo_password,
        timeout=300,  # updates can be slow (cargo recompile)
    )

    if not result["ok"]:
        return result

    # Get version after update
    version_after = get_tool_version(tool)

    if version_before == version_after:
        return {
            "ok": True,
            "message": f"{tool} is already at the latest version ({version_after})",
            "already_latest": True,
        }

    _audit(
        "⬆️ Tool Updated",
        f"{tool}: {version_before} → {version_after}",
        action="updated",
        target=tool,
    )

    return {
        "ok": True,
        "message": f"{tool} updated: {version_before} → {version_after}",
        "from_version": version_before,
        "to_version": version_after,
    }
```

### uninstall_tool()

```python
def uninstall_tool(
    tool: str,
    *,
    sudo_password: str = "",
) -> dict[str, Any]:
    """Uninstall a tool.

    Uses the undo command catalog from domain-rollback.
    """
    recipe = TOOL_RECIPES.get(tool)
    if not recipe:
        return {"ok": False, "error": f"No recipe for '{tool}'"}

    uninstall_cmd = recipe.get("uninstall")
    if not uninstall_cmd:
        return {"ok": False, "error": f"No uninstall command defined for {tool}"}

    cmd = _pick_command(uninstall_cmd, get_system_profile())
    needs_sudo = _pick_sudo(recipe.get("needs_sudo", {}), get_system_profile())

    result = _run_subprocess(
        cmd,
        needs_sudo=needs_sudo,
        sudo_password=sudo_password,
        timeout=60,
    )

    if result["ok"]:
        _audit(
            "🗑️ Tool Uninstalled",
            f"{tool} removed",
            action="uninstalled",
            target=tool,
        )

    return result
```

### check_updates() — bulk version check

```python
def check_updates(tools: list[str] | None = None) -> list[dict]:
    """Check all installed tools for available updates.

    Args:
        tools: List of tools to check. If None, checks all TOOL_RECIPES.

    Returns:
        List of tool status dicts with update_available flag.
    """
    if tools is None:
        tools = list(TOOL_RECIPES.keys())

    results = []
    for tool in tools:
        status = get_tool_status(tool)
        if status["installed"]:
            results.append(status)

    return results
```

---

## Recipe Format Addition

### uninstall field

```python
"ruff": {
    "install":   {"_default": [sys.executable, "-m", "pip", "install", "ruff"]},
    "update":    {"_default": [sys.executable, "-m", "pip", "install", "--upgrade", "ruff"]},
    "uninstall": {"_default": [sys.executable, "-m", "pip", "uninstall", "-y", "ruff"]},
    "verify":    ["ruff", "--version"],
},
"docker": {
    "install":   {"debian": ["apt-get", "install", "-y", "docker.io"]},
    "update":    {"debian": ["apt-get", "install", "--only-upgrade", "-y", "docker.io"]},
    "uninstall": {"debian": ["apt-get", "purge", "-y", "docker.io"]},
    "verify":    ["docker", "--version"],
},
```

### version_command field (optional override)

```python
"trivy": {
    ...,
    "version_command": ["trivy", "version"],
    "version_pattern": r"Version: (\d+\.\d+\.\d+)",
    # When not specified, uses VERSION_COMMANDS lookup
},
```

---

## New Routes

### POST /audit/tool-status

```python
@app.post("/audit/tool-status")
def tool_status():
    """Get status of a specific tool (installed, version, update available)."""
    tool = request.json.get("tool")
    return jsonify(get_tool_status(tool))
```

### POST /audit/check-updates

```python
@app.post("/audit/check-updates")
def check_all_updates():
    """Check all tools for available updates."""
    tools = request.json.get("tools")  # optional filter
    return jsonify({"updates": check_updates(tools)})
```

### POST /audit/update-tool

```python
@app.post("/audit/update-tool")
def do_update_tool():
    """Update a tool to its latest version."""
    tool = request.json.get("tool")
    sudo_password = request.json.get("sudo_password", "")
    return jsonify(update_tool(tool, sudo_password=sudo_password))
```

### POST /audit/uninstall-tool

```python
@app.post("/audit/uninstall-tool")
def do_uninstall_tool():
    """Uninstall a tool."""
    tool = request.json.get("tool")
    sudo_password = request.json.get("sudo_password", "")
    return jsonify(uninstall_tool(tool, sudo_password=sudo_password))
```

---

## UI Integration (Audit Panel)

### Tool row enrichment

```
┌─ Installed Tools ────────────────────────────────────┐
│                                                        │
│ ✅ ruff      0.4.8   → 0.5.1 available   [Update]    │
│ ✅ black     24.4.2  (latest)                          │
│ ✅ docker    26.1.3  → 27.0.1 available   [Update]    │
│ ✅ kubectl   1.29.3  (latest)                          │
│ ✅ helm      3.15.1  (latest)                          │
│                                                        │
│ 2 updates available        [Update All]                │
└────────────────────────────────────────────────────────┘
```

### Update All

```javascript
async function updateAll() {
    const updates = toolStatuses.filter(t => t.update_available);
    for (const tool of updates) {
        const resp = await fetch('/audit/update-tool', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                tool: tool.tool,
                sudo_password: getSudoPassword(),
            }),
        });
        const result = await resp.json();
        updateToolRow(tool.tool, result);
    }
}
```

---

## Performance Considerations

### Version check cost

| Operation | Time | When |
|-----------|------|------|
| `tool --version` | ~10ms | Per tool, subprocess |
| PyPI API call | ~100ms | Per pip tool, network |
| apt-cache policy | ~20ms | Per apt tool, local |
| snap info | ~50ms | Per snap tool, local |

### Optimization

```python
# Don't check latest on every page load
# Cache with TTL
VERSION_CHECK_CACHE = {}
VERSION_CACHE_TTL = 3600  # 1 hour

def check_updates_cached(tools):
    now = time.time()
    cached = VERSION_CHECK_CACHE.get("all")
    if cached and (now - cached["checked_at"]) < VERSION_CACHE_TTL:
        return cached["results"]
    results = check_updates(tools)
    VERSION_CHECK_CACHE["all"] = {"results": results, "checked_at": now}
    return results
```

### Lazy loading

```
Page load: show installed/not-installed (from l0_detection cache)
Background: check versions (async, non-blocking)
Badge: "2 updates" appears when background check completes
```

---

## Edge Cases

| Case | Impact | Handling |
|------|--------|---------|
| Tool has no version command | Can't detect version | Return `version: None`, skip update check |
| Latest version API unreachable | Can't compare | Return `outdated: None`, show "unknown" |
| Version format non-standard | Comparison fails | Fall back to string != comparison |
| Update breaks tool | Tool stops working | Verify after update, report failure |
| Cargo update takes 10+ min | Timeout | Extended timeout (300s) for cargo |
| pip update in venv vs global | Wrong pip | Use venv pip (sys.executable -m pip) |
| Snap auto-updates | Snap updates itself | Detect snap auto-refresh, skip manual |
| Bulk update: first fails | What about rest? | Continue remaining, report per-tool |
| Uninstall removes shared deps | apt removes too much | Use `apt remove` (not `purge --auto-remove`) |

---

## Phase Roadmap

| Step | What | Complexity |
|------|------|-----------|
| 1 | Add `update` + `uninstall` fields to TOOL_RECIPES | Low |
| 2 | Implement `get_tool_version()` + VERSION_COMMANDS | Low |
| 3 | Implement `get_latest_version()` (pip, apt, snap) | Medium |
| 4 | Implement `update_tool()` | Low (uses existing _run_subprocess) |
| 5 | Implement `check_updates()` with caching | Medium |
| 6 | Add routes (tool-status, check-updates, update-tool) | Low |
| 7 | Frontend: version badges + update buttons | Medium (Phase 3) |

---

## Files Touched

| File | Changes |
|------|---------|
| `tool_install.py` | Add VERSION_COMMANDS, get_tool_version(), get_latest_version(), update_tool(), uninstall_tool(), check_updates(). Add update/uninstall to TOOL_RECIPES. |
| `routes_audit.py` | Add POST /audit/tool-status, /audit/check-updates, /audit/update-tool, /audit/uninstall-tool. |

---

## Traceability

| Topic | Source |
|-------|--------|
| Update commands per PM | Phase 2 index §Update: How to Upgrade |
| Update commands (12 methods) | domain-package-managers, domain-language-pms |
| Uninstall / undo commands | domain-rollback §undo command catalog |
| _run_subprocess() | Phase 2.4 execution engine |
| Recipe format (update field) | Phase 2.2 recipe format |
| Version caching | domain-version-selection §caching |
| l0_detection cache | domain-devops-tools |
| Sudo handling for updates | domain-sudo-security |
