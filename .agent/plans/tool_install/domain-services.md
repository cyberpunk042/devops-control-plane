# Domain: Services

> This document catalogs init/service managers relevant to the
> tool install system: systemd, OpenRC, init.d, launchd, and
> "none" (containers). Covers detection, commands for start/stop/
> enable/status, journal access, and post-install service management.
>
> SOURCE DOCS: arch-system-model §Init system (Phase 4 schema),
>              arch-system-model §System services (Phase 8),
>              arch-system-model §capabilities.has_systemd,
>              scope-expansion §2.8 (restart requirements),
>              scope-expansion §2.12 (journald config),
>              domain-platforms (per-platform init systems)

---

## Overview

Service management matters for tool installation because some
tools ARE services that must be started after install:

| Tool | Service | Must start? | Must enable at boot? |
|------|---------|------------|---------------------|
| Docker | docker.service | ✅ | ✅ |
| containerd | containerd.service | ✅ | ✅ |
| nginx | nginx.service | ✅ | ✅ |
| prometheus | prometheus.service | ✅ | Optional |
| grafana | grafana-server.service | ✅ | Optional |
| sshd | sshd.service | Usually running | Usually enabled |

### Phase 2 vs Later

| Phase | Service capability |
|-------|-------------------|
| Phase 2 | `has_systemd` boolean detected. Docker post-install uses `systemctl`. No cross-platform service management. |
| Phase 4 | Init system type detected. Service commands per init system. |
| Phase 8 | Full service management: journald config, logrotate, cron. |

---

## Init Systems

### Detection

```python
"init_system": {
    "type": str,             # "systemd" | "openrc" | "initd" | "launchd" | "none"
    "service_manager": str,  # "systemctl" | "rc-service" | "service" | "launchctl"
    "can_enable": bool,      # can services be enabled at boot?
    "can_start": bool,       # can services be started?
}
```

**Detection priority:** systemd > OpenRC > init.d > launchd > none.

```python
def _detect_init_system() -> dict:
    if shutil.which("systemctl"):
        result = subprocess.run(
            ["systemctl", "is-system-running"],
            capture_output=True, text=True, timeout=5)
        state = result.stdout.strip()
        if state in ("running", "degraded"):
            return {
                "type": "systemd",
                "service_manager": "systemctl",
                "can_enable": True,
                "can_start": True,
            }
    if shutil.which("rc-status"):
        return {
            "type": "openrc",
            "service_manager": "rc-service",
            "can_enable": True,
            "can_start": True,
        }
    if shutil.which("launchctl"):
        return {
            "type": "launchd",
            "service_manager": "launchctl",
            "can_enable": True,
            "can_start": True,
        }
    if os.path.isdir("/etc/init.d"):
        return {
            "type": "initd",
            "service_manager": "service",
            "can_enable": False,  # no standard enable mechanism
            "can_start": True,
        }
    return {
        "type": "none",
        "service_manager": None,
        "can_enable": False,
        "can_start": False,
    }
```

### Platform → Init system mapping

| Platform | Init system | Service manager |
|----------|-----------|----------------|
| Ubuntu | systemd | systemctl |
| Debian | systemd | systemctl |
| Fedora | systemd | systemctl |
| RHEL/CentOS | systemd | systemctl |
| Arch | systemd | systemctl |
| SUSE | systemd | systemctl |
| Alpine | OpenRC | rc-service |
| macOS | launchd | launchctl |
| Docker (most images) | none | N/A |
| WSL2 (default) | none* | N/A |
| WSL2 (systemd enabled) | systemd | systemctl |

*WSL2 can enable systemd via `/etc/wsl.conf`:
```ini
[boot]
systemd=true
```

---

## Service Commands

### systemd (most Linux distros)

| Action | Command | Notes |
|--------|---------|-------|
| Start | `systemctl start SERVICE` | Starts now |
| Stop | `systemctl stop SERVICE` | Stops now |
| Restart | `systemctl restart SERVICE` | Stop + start |
| Reload | `systemctl reload SERVICE` | Reload config without restart |
| Enable | `systemctl enable SERVICE` | Start at boot |
| Disable | `systemctl disable SERVICE` | Don't start at boot |
| Enable + start | `systemctl enable --now SERVICE` | Both in one |
| Status | `systemctl status SERVICE` | Show state + recent logs |
| Is active? | `systemctl is-active SERVICE` | Returns "active" or "inactive" |
| Is enabled? | `systemctl is-enabled SERVICE` | Returns "enabled" or "disabled" |
| Journal | `journalctl -u SERVICE` | View service logs |
| Daemon reload | `systemctl daemon-reload` | After unit file changes |

**All need sudo** except `status`, `is-active`, `is-enabled`.

### OpenRC (Alpine)

| Action | Command | Notes |
|--------|---------|-------|
| Start | `rc-service SERVICE start` | Starts now |
| Stop | `rc-service SERVICE stop` | Stops now |
| Restart | `rc-service SERVICE restart` | Stop + start |
| Enable | `rc-update add SERVICE default` | Start at boot (default runlevel) |
| Disable | `rc-update del SERVICE default` | Don't start at boot |
| Status | `rc-service SERVICE status` | Show state |
| List | `rc-status` | All services and states |

**All need sudo** except `status`, `rc-status`.

### init.d (legacy/containers)

| Action | Command | Notes |
|--------|---------|-------|
| Start | `service SERVICE start` | Or `/etc/init.d/SERVICE start` |
| Stop | `service SERVICE stop` | |
| Restart | `service SERVICE restart` | |
| Status | `service SERVICE status` | |
| Enable | (varies) | No standard mechanism |

### launchd (macOS)

| Action | Command | Notes |
|--------|---------|-------|
| Start | `launchctl load PLIST` | Load and start |
| Stop | `launchctl unload PLIST` | Unload and stop |
| List | `launchctl list` | Running services |
| Start (modern) | `launchctl bootstrap system PLIST` | macOS 10.10+ |
| Stop (modern) | `launchctl bootout system PLIST` | macOS 10.10+ |
| Status | `launchctl print system/SERVICE` | macOS 10.10+ |

**Plist locations:**
- System: `/Library/LaunchDaemons/`
- User: `~/Library/LaunchAgents/`

---

## Containers and Services

### No init system in containers

Most Docker containers have NO init system:

```python
if init_system["type"] == "none":
    # Cannot start/enable services
    # Tool installs but doesn't auto-start
    # User must run the tool manually or use supervisor
```

### Container alternatives

| Alternative | What it does |
|------------|-------------|
| supervisord | Process manager, runs multiple processes |
| s6-overlay | Lightweight init for containers |
| tini | PID 1 init, signal handling only |
| dumb-init | Similar to tini |
| Direct execution | CMD in Dockerfile runs the process |

### Docker post-install without systemd

```python
# Phase 2 Docker post-install (systemd path)
"post_install": [
    {"label": "Start Docker",
     "command": ["systemctl", "start", "docker"],
     "condition": "has_systemd"},
    {"label": "Enable Docker at boot",
     "command": ["systemctl", "enable", "docker"],
     "condition": "has_systemd"},
    {"label": "Add user to docker group",
     "command": ["usermod", "-aG", "docker", "{user}"]},
]

# Without systemd (Alpine, containers)
"post_install_alt": [
    {"label": "Start Docker",
     "command": ["rc-service", "docker", "start"],
     "condition": "has_openrc"},
    {"label": "Enable Docker at boot",
     "command": ["rc-update", "add", "docker", "default"],
     "condition": "has_openrc"},
]
```

---

## Journal / Log Access

### systemd journal (journalctl)

```bash
# View service logs
journalctl -u docker.service

# Follow (live)
journalctl -u docker.service -f

# Last N lines
journalctl -u docker.service -n 50

# Since time
journalctl -u docker.service --since "1 hour ago"

# Disk usage
journalctl --disk-usage
# Archived and active journals take up 1.2G in the file system.
```

### Journal configuration

```python
# From scope-expansion §2.12
"config_templates": {
    "journald": {
        "file": "/etc/systemd/journald.conf.d/tool.conf",
        "template": "[Journal]\nSystemMaxUse={journal_max_size}\nCompress=yes\n",
        "inputs": [
            {"id": "journal_max_size", "label": "Max journal size",
             "type": "select", "options": ["100M", "500M", "1G", "2G"],
             "default": "500M"},
        ],
        "needs_sudo": True,
        "post_command": ["systemctl", "restart", "systemd-journald"],
        "condition": "has_systemd",
    },
}
```

### OpenRC logging

Alpine uses syslog (usually busybox syslog):
```bash
# View logs
cat /var/log/messages | grep docker

# Or if using syslog-ng
cat /var/log/docker.log
```

### macOS logging

```bash
# View logs
log show --predicate 'process == "docker"' --last 1h

# Stream
log stream --predicate 'process == "docker"'
```

---

## Restart Requirements

### Restart levels

```python
"restart_required": "session" | "service" | "system"
```

| Level | What happens | Example |
|-------|-------------|---------|
| `session` | Logout + login (or `newgrp`) | Docker group membership |
| `service` | `systemctl restart SERVICE` | Config file change |
| `system` | Full reboot | Kernel module, driver install |

### Restart in recipe format

```python
"post_install": [
    {
        "label": "Add user to docker group",
        "command": ["usermod", "-aG", "docker", "{user}"],
        "needs_sudo": True,
        "restart_required": "session",
        "restart_message": "Log out and back in for docker group to take effect. "
                           "Or run: newgrp docker",
    },
]
```

### Plan engine behavior

```
1. Execute step → step has restart_required
2. Persist plan state to disk
3. Show message to user: "Restart needed"
4. PAUSE execution
5. (user restarts session/service/system)
6. On next run: detect persisted state → resume from next step
```

---

## systemd State Detection

### has_systemd (Phase 2)

```python
# Already in fast profile
"capabilities": {
    "has_systemd": bool,        # systemctl exists AND state is running|degraded
    "systemd_state": str | None,  # "running" | "degraded" | "offline" | None
}
```

**Detection:**
```python
def _detect_systemd() -> tuple[bool, str | None]:
    if not shutil.which("systemctl"):
        return False, None
    try:
        result = subprocess.run(
            ["systemctl", "is-system-running"],
            capture_output=True, text=True, timeout=5)
        state = result.stdout.strip()
        return state in ("running", "degraded"), state
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False, None
```

### systemd states

| State | Meaning | Impact |
|-------|---------|--------|
| `running` | All clear | Full service management |
| `degraded` | Some units failed | Service management works, some services broken |
| `starting` | Still booting | Wait and retry |
| `offline` | systemd present but not PID 1 | In container — can't use systemctl |
| None | systemctl not found | No systemd |

### "systemd in container" gotcha

Some containers have `systemctl` binary installed but systemd is
NOT running (PID 1 is not systemd). This causes:

```
$ systemctl start docker
System has not been booted with systemd as init system
```

The `is-system-running` check catches this: returns "offline".

---

## Service Schema (Phase 8)

```python
"services": {
    "journald": {
        "active": bool,          # systemctl is-active systemd-journald
        "disk_usage": str | None,  # from journalctl --disk-usage
    },
    "logrotate_installed": bool,  # shutil.which("logrotate")
    "cron_available": bool,       # shutil.which("crontab")
}
```

---

## Conditional Commands

### Per init system commands in recipes

```python
"post_install": {
    "systemd": [
        ["systemctl", "daemon-reload"],
        ["systemctl", "enable", "--now", "docker"],
    ],
    "openrc": [
        ["rc-update", "add", "docker", "default"],
        ["rc-service", "docker", "start"],
    ],
    "launchd": [
        # Docker Desktop handles this on macOS
    ],
    "none": [
        # No service management — user starts manually
    ],
}
```

### Condition field

```python
{"label": "Enable Docker at boot",
 "command": ["systemctl", "enable", "docker"],
 "condition": "has_systemd"},
# Only runs if capabilities.has_systemd is True
```

---

## Edge Cases

| Case | Impact | Handling |
|------|--------|---------|
| Container: no init system | Can't start/enable services | Install only, no service mgmt |
| WSL2: no systemd by default | systemctl fails | Detect WSL, offer wsl.conf systemd enable |
| Alpine: OpenRC not systemd | systemctl commands fail | Detect init type, use rc-service |
| macOS: launchd not systemd | Different command model | launchctl plist loading |
| systemd degraded | Some services broken | Warn user but proceed |
| Docker group without newgrp | User can't run docker | Explain logout/login needed |
| systemd in container (offline) | systemctl present but broken | is-system-running detects this |
| Snap without systemd | snap install fails | snap_available = False, use fallback |
| Service restart fails | Tool installed but not running | Show error, suggest manual start |

---

## Traceability

| Topic | Source |
|-------|--------|
| Init system schema | arch-system-model §Init system (Phase 4) |
| has_systemd detection | arch-system-model §capabilities |
| systemd state detection | arch-system-model §detection (systemctl is-system-running) |
| Init detection priority | arch-system-model (systemd > OpenRC > init.d > launchd > none) |
| Service schema (Phase 8) | arch-system-model §System services |
| Journald config template | scope-expansion §2.12 |
| Restart requirements | scope-expansion §2.8 |
| Docker post-install | scope-expansion §2.8 (usermod -aG docker) |
| Alpine OpenRC | domain-platforms §Alpine |
| macOS launchd | domain-platforms §macOS |
| WSL systemd | domain-wsl §systemd in WSL |
| Container no-init | domain-containers §init systems |
| Snap + systemd | domain-package-managers §snap |
