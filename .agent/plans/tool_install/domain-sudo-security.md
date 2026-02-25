# Domain: Sudo & Security

> This document catalogs the sudo and security model for the tool
> install system: password handling, root detection, capability
> detection, the needs_sudo flag, sudo -S -k piping, password
> caching rules, and the security invariants.
>
> SOURCE DOCS: tool_install.py (current sudo implementation),
>              scope-expansion §needs_sudo across recipes,
>              domain-risk-levels §confirmation gates,
>              domain-containers §privilege detection

---

## Overview

Many installation steps need root privileges (`sudo`). The system
must handle sudo passwords securely, detect when root is available,
and never store passwords on disk.

### Current implementation (Phase 2)

```python
# tool_install.py line 339
cmd = ["sudo", "-S", "-k"] + _SUDO_RECIPES[tool]
# -S: read password from stdin
# -k: invalidate cached credentials (force re-auth)
stdin_data = (sudo_password + "\n") if needs_sudo else None
```

This is the foundation. Phase 4+ refines it.

---

## Privilege Detection

### 4 privilege states

| State | Detection | Meaning |
|-------|----------|---------|
| **root** | `os.geteuid() == 0` | Running as root. No sudo needed. |
| **sudo available** | `shutil.which("sudo")` | sudo binary exists. Password may be required. |
| **sudoers member** | `sudo -n true` (exit 0) | User can sudo without password (NOPASSWD) |
| **no privilege** | None of above | User can't elevate. Only user-space installs. |

### Detection function

```python
def detect_privilege() -> dict:
    """Detect current privilege level."""
    import os, shutil, subprocess

    result = {
        "is_root": os.geteuid() == 0,
        "has_sudo": shutil.which("sudo") is not None,
        "has_nopasswd": False,
        "user": os.getenv("USER", "unknown"),
        "uid": os.getuid(),
        "euid": os.geteuid(),
    }

    if result["has_sudo"] and not result["is_root"]:
        try:
            proc = subprocess.run(
                ["sudo", "-n", "true"],
                capture_output=True, timeout=5,
            )
            result["has_nopasswd"] = proc.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    return result
```

### Impact on install flow

| State | System packages | User-space packages | Config files |
|-------|----------------|--------------------|----|
| root | ✅ Direct (no sudo) | ✅ | ✅ Direct |
| sudo + password | ✅ After password prompt | ✅ | ✅ With sudo |
| sudo NOPASSWD | ✅ Automatic | ✅ | ✅ Automatic |
| no privilege | ❌ Disabled | ✅ Only | ❌ System configs disabled |

---

## needs_sudo Flag

### In recipes

```python
TOOL_RECIPES = {
    "ruff": {
        "install": {"_default": ["pip", "install", "ruff"]},
        "needs_sudo": {"_default": False},
    },
    "docker": {
        "install": {"debian": ["apt-get", "install", "-y", "docker.io"]},
        "needs_sudo": {"debian": True},
    },
}
```

### In plan steps

```python
{
    "label": "Install docker.io",
    "command": ["apt-get", "install", "-y", "docker.io"],
    "needs_sudo": True,
}
```

### needs_sudo determination

```python
def _needs_sudo(step: dict, privilege: dict) -> bool:
    """Determine if step actually needs sudo invocation."""
    if not step.get("needs_sudo"):
        return False             # Step doesn't need privileges
    if privilege["is_root"]:
        return False             # Already root, no sudo needed
    return True                  # Need sudo
```

---

## Password Handling

### Security invariants (NEVER VIOLATED)

| Rule | Implementation |
|------|---------------|
| **Never store password on disk** | Password only in memory, never written to file |
| **Never log password** | Password excluded from all log output |
| **Never send password in URL** | Password sent in POST body only |
| **Never echo password** | stdin pipe, no command-line argument |
| **Never persist across server restart** | In-memory only |
| **Clear after use** | Python GC handles; no explicit retention |
| **Force re-auth per session** | `sudo -k` invalidates cached credentials |

### Password flow

```
1. Frontend: User enters password in masked input
   └── <input type="password">

2. Frontend → Backend: POST /api/tool/install
   └── Body: {"tool": "docker", "sudo_password": "***"}
   └── HTTPS only (if deployed)

3. Backend: Receive password in request body
   └── Never logged
   └── Never written to disk

4. Backend: Pipe to sudo via stdin
   └── cmd = ["sudo", "-S", "-k"] + install_cmd
   └── stdin_data = password + "\n"
   └── subprocess.run(input=stdin_data)

5. Backend: Clear password reference
   └── sudo_password goes out of scope
   └── Python GC collects

6. Backend → Frontend: Return result
   └── Never include password in response
```

### sudo -S -k explained

| Flag | Purpose |
|------|---------|
| `-S` | Read password from stdin (not terminal). Required for programmatic use. |
| `-k` | Invalidate cached credentials. Forces re-authentication. Ensures the password we provide is actually verified. |

### Wrong password handling

```python
# Current implementation (tool_install.py ~line 420)
if "incorrect password" in stderr.lower() or returncode == 1:
    return {
        "ok": False,
        "error": "Wrong sudo password",
        "needs_sudo": True,
        # Frontend shows password prompt again
    }
```

---

## Sudo Session Caching

### Current behavior: NO caching

Each `sudo -k` invalidates the timestamp. Every sudo call
requires the password again. This is the SAFEST approach.

### Future option: Session-scoped caching (Phase 4+)

```python
# Option 1: Use sudo timestamp (natural caching)
# First call: sudo -S (with password)
# Subsequent calls within ~15 min: sudo (no password needed)
# Problem: sudo -k kills this

# Option 2: Keep password in memory for the plan duration
class PlanExecution:
    def __init__(self, plan, sudo_password=None):
        self._sudo_password = sudo_password  # in-memory only
        # Cleared when PlanExecution is garbage collected

    def _run_step(self, step):
        if self._needs_sudo(step):
            cmd = ["sudo", "-S"] + step["command"]
            # Note: no -k here, allow sudo timestamp caching
            stdin_data = self._sudo_password + "\n"
```

### Caching rules

| Rule | Value |
|------|-------|
| Cache scope | Single plan execution only |
| Cache location | In-memory (PlanExecution object) |
| Cache lifetime | Until plan completes or fails |
| Cache invalidation | Plan done, plan cancelled, server restart |
| Never persist | Never written to disk, session storage, or DB |

---

## Root Detection Nuances

### Already root (skip sudo)

```python
if os.geteuid() == 0:
    # Already root — run command directly, no sudo needed
    cmd = step["command"]  # no sudo prefix
    stdin_data = None      # no password
```

### Root in container

```python
# Most containers run as root by default
# euid == 0, but capabilities may be limited
if os.geteuid() == 0 and in_container:
    # Root but limited:
    # - Can't load kernel modules
    # - Can't change sysctl (usually)
    # - Can't modify /proc, /sys (usually)
    # - CAN install packages (apt, pip)
    # - CAN write config files
```

### Fake root (fakeroot, user namespaces)

```python
# Some build systems use fakeroot
# euid == 0 but not real root
if os.geteuid() == 0:
    # Verify real root with a privileged operation
    try:
        subprocess.run(["id", "-u"], capture_output=True)
        # Check if we can actually do root things
    except:
        pass
```

---

## Capability-Based Access (Future)

### Linux capabilities

Instead of full root, specific capabilities:

| Capability | What it allows | Example use |
|-----------|---------------|-------------|
| `CAP_NET_ADMIN` | Network configuration | Setting up firewall rules |
| `CAP_SYS_ADMIN` | System administration | Mounting filesystems |
| `CAP_DAC_OVERRIDE` | Bypass file permissions | Writing to /etc |
| `CAP_SYS_MODULE` | Load kernel modules | modprobe |
| `CAP_CHOWN` | Change file ownership | chown on config files |

### Detection

```python
def _get_capabilities() -> list[str]:
    """Get current process capabilities."""
    try:
        proc = subprocess.run(
            ["capsh", "--print"],
            capture_output=True, text=True,
        )
        # Parse "Current: = cap_net_admin,...+ep"
        for line in proc.stdout.splitlines():
            if line.startswith("Current:"):
                return _parse_caps(line)
    except FileNotFoundError:
        pass
    return []
```

### Phase 8+ use

```python
# Instead of needs_sudo: True
# Use needs_capability: ["CAP_DAC_OVERRIDE"]
# If container has the capability, no sudo needed
```

---

## Frontend Security

### Password input

```html
<input type="password"
       id="sudo-password"
       autocomplete="off"
       placeholder="Enter sudo password">
```

### Submission

```javascript
async function installWithSudo(tool) {
    const password = document.getElementById('sudo-password').value;

    const resp = await fetch('/api/tool/install', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            tool: tool,
            sudo_password: password,
        }),
    });

    // Clear password from DOM immediately
    document.getElementById('sudo-password').value = '';

    return await resp.json();
}
```

### Rules

| Rule | Implementation |
|------|---------------|
| Clear after submit | `input.value = ''` immediately |
| No browser storage | `autocomplete="off"` |
| No console logging | Never `console.log(password)` |
| Masked display | `type="password"` |

---

## Error Handling

### Sudo-related errors

| Error | Detection | Response |
|-------|----------|----------|
| Wrong password | stderr "incorrect password" | Re-prompt |
| sudo not found | `shutil.which("sudo")` is None | "sudo not available" |
| User not in sudoers | stderr "is not in the sudoers file" | "Your user cannot sudo" |
| sudo timeout | subprocess.TimeoutExpired | "sudo timed out" |
| NOPASSWD but command fails | returncode != 0, no password error | Normal error handling |

### Retry flow

```
1. Frontend sends install request (no password)
2. Backend detects needs_sudo, no password
3. Backend returns: {"ok": false, "needs_sudo": true}
4. Frontend shows password prompt
5. Frontend re-sends with password
6. If wrong password: goto 4
7. If correct: install proceeds
```

---

## Edge Cases

| Case | Impact | Handling |
|------|--------|---------|
| sudo password cached by OS | `-k` invalidates, forces re-auth | Expected behavior |
| User has NOPASSWD in sudoers | No password needed | Detect with `sudo -n true` |
| Multiple sudo calls in plan | Password prompted each time | Session-scoped caching (Phase 4) |
| Password contains special chars | Pipe might misinterpret | stdin pipe handles all bytes |
| SSH session: no terminal | `sudo -S` works without terminal | By design |
| Container: root but limited | Some ops still fail | Check capabilities |
| macOS: different sudo | Keychain integration | `sudo -S` still works |
| Password prompt timeout (sudo) | sudo asks interactively | `-S` prevents interactive prompt |
| Server runs as root | All sudo flags irrelevant | Skip sudo entirely |

---

## Phase Roadmap

| Phase | Sudo capability |
|-------|----------------|
| Phase 2 | `sudo -S -k` per call. Password from frontend. No caching. |
| Phase 3 | Privilege detection (root, sudo, NOPASSWD, none). |
| Phase 4 | Session-scoped password caching for multi-step plans. |
| Phase 8 | Capability-based access. Fine-grained permission model. |

---

## Traceability

| Topic | Source |
|-------|--------|
| sudo -S -k implementation | tool_install.py lines 339, 387 |
| needs_sudo per recipe | tool_install.py (\_SUDO\_RECIPES, \_NO\_SUDO\_RECIPES) |
| Wrong password handling | tool_install.py lines 420-430 |
| Password in POST body | tool_install.py line 281 (sudo_password param) |
| Container root limitation | domain-containers §privilege |
| Risk confirmation before sudo | domain-risk-levels §confirmation gates |
| needs_sudo in plan steps | scope-expansion §needs_sudo |
| NOPASSWD in sudoers | arch-system-model §capabilities |
