# Domain: Restart

> This document catalogs restart requirements in the tool install
> system: session restart (logout/login), service restart
> (systemctl restart), and system restart (reboot). Covers
> resumable plans, state persistence across restarts, and the
> plan engine pause/resume mechanism.
>
> SOURCE DOCS: scope-expansion §2.8 (restart requirements),
>              scope-expansion §2.5 (kernel reboot + rollback),
>              domain-services §restart levels,
>              domain-kernel §rollback (GRUB boot old kernel)

---

## Overview

Some install steps require a restart before later steps can
proceed. The system must handle three restart levels, each with
different disruption and different resume mechanisms.

### Why restart matters

Without restart handling, the plan engine would:
1. Add user to docker group
2. Immediately try `docker ps` — FAILS (group not active)
3. Report installation failure — even though install succeeded

The fix: the plan PAUSES, tells the user to restart, then
RESUMES from the next step after the restart.

---

## Restart Levels

### Three levels

| Level | What | Disruption | Duration | Example |
|-------|------|-----------|----------|---------|
| `session` | Logout + login (or `newgrp`) | Current shell/session ends | Seconds | Docker group membership |
| `service` | `systemctl restart SERVICE` | Service briefly unavailable | Seconds | Config file change |
| `system` | Full reboot | All processes stop | 30s-2min | Kernel module, driver install |

### Recipe format

```python
{
    "label": "Add user to docker group",
    "command": ["usermod", "-aG", "docker", "{user}"],
    "needs_sudo": True,
    "restart_required": "session",
    "restart_message": "Log out and back in for docker group to take effect. "
                       "Or run: newgrp docker",
}
```

### Fields

| Field | Type | Required | Purpose |
|-------|------|----------|---------|
| `restart_required` | str | ❌ | `"session"`, `"service"`, `"system"`, or absent |
| `restart_message` | str | ❌ | Human-readable explanation |
| `restart_service` | str | ❌ | Service name for `service` level |

---

## Session Restart

### When needed

| Scenario | Why | Alternative |
|----------|-----|-------------|
| Group membership change | `usermod -aG` only active on new session | `newgrp GROUP` |
| Shell profile change | `.bashrc`/`.zshrc` changes not loaded | `source ~/.bashrc` |
| Environment variable set | System-wide env in `/etc/environment` | `export VAR=val` |

### The Docker group problem

```bash
# Step 1: Add to group
sudo usermod -aG docker $USER

# Step 2: Without logout/login:
docker ps
# Got permission denied while trying to connect to the Docker daemon socket

# Step 3a: Logout + login → works
# Step 3b: Or use newgrp (same session):
newgrp docker
docker ps  # works now
```

### Plan engine behavior

```
1. Execute: usermod -aG docker $USER       ✅
2. Detect: restart_required == "session"
3. PAUSE execution
4. Show message:
   ┌────────────────────────────────────────────┐
   │ ⚠️  Session restart needed                  │
   │                                             │
   │ Log out and back in for docker group         │
   │ to take effect.                              │
   │                                             │
   │ Quick alternative: run `newgrp docker`       │
   │ in your terminal.                            │
   │                                             │
   │ [Resume after restart] [Skip remaining]      │
   └────────────────────────────────────────────┘
5. Save plan state to disk
6. (user restarts session)
7. On next run: detect saved state → resume from step 3
```

---

## Service Restart

### When needed

| Scenario | Service | Command |
|----------|---------|---------|
| Docker config change | docker | `systemctl restart docker` |
| journald config change | systemd-journald | `systemctl restart systemd-journald` |
| nginx config change | nginx | `systemctl reload nginx` |
| sshd config change | sshd | `systemctl restart sshd` |
| systemd unit file change | any | `systemctl daemon-reload` first |

### Restart vs reload

| Action | Effect | When to use |
|--------|--------|-------------|
| `restart` | Stop + start | Config changes that need full restart |
| `reload` | Re-read config, no stop | nginx, Apache (graceful) |
| `daemon-reload` | Re-read unit files | After changing `.service` files |

### Plan engine behavior

Service restarts are AUTOMATIC — no pause needed:
```
1. Write config file: /etc/docker/daemon.json    ✅
2. Execute: systemctl restart docker              ✅
3. Verify: docker ps                              ✅
4. Continue to next step
```

No user interaction needed unless restart fails.

---

## System Restart

### When needed

| Scenario | Why | Can avoid? |
|----------|-----|-----------|
| Kernel module install (NVIDIA driver) | Module loads at boot | ❌ Must reboot |
| Kernel recompilation | New kernel loads at boot | ❌ Must reboot |
| DKMS rebuild after kernel update | Module for new kernel | ❌ Must reboot into new kernel |
| GRUB/bootloader change | New boot entry | ❌ Must reboot |
| Major OS upgrade | Libraries replaced | Usually required |

### Plan engine behavior

```
1. Execute: make install (kernel)               ✅
2. Execute: update-grub                          ✅
3. Detect: restart_required == "system"
4. PAUSE execution
5. Save FULL plan state to disk:
   - Which steps completed
   - Which steps remain
   - User input values
   - Current system profile
6. Show message:
   ┌────────────────────────────────────────────┐
   │ 🔄 System reboot required                  │
   │                                             │
   │ Reboot to load the new kernel.              │
   │ If boot fails, select the old kernel        │
   │ in the GRUB menu.                           │
   │                                             │
   │ After reboot, the install plan will          │
   │ resume automatically.                       │
   │                                             │
   │ [Reboot now] [Reboot later] [Cancel plan]   │
   └────────────────────────────────────────────┘
7. (user reboots)
8. On next run: detect saved state → resume from step after reboot
```

---

## State Persistence

### What gets saved

```python
{
    "plan_id": "uuid-...",
    "tool": "vfio_pci",
    "started_at": "2025-02-24T15:00:00Z",
    "paused_at": "2025-02-24T15:30:00Z",
    "pause_reason": "system_restart",
    "steps": [
        {"id": 0, "label": "Install kernel build deps", "status": "done"},
        {"id": 1, "label": "Download kernel source", "status": "done"},
        {"id": 2, "label": "Backup config", "status": "done"},
        {"id": 3, "label": "Enable CONFIG_VFIO_PCI", "status": "done"},
        {"id": 4, "label": "Build kernel", "status": "done"},
        {"id": 5, "label": "Install kernel", "status": "done"},
        {"id": 6, "label": "Update bootloader", "status": "done"},
        {"id": 7, "label": "Reboot", "status": "paused"},
        {"id": 8, "label": "Verify CONFIG_VFIO_PCI", "status": "pending"},
        {"id": 9, "label": "Load vfio-pci module", "status": "pending"},
    ],
    "inputs": {
        "config_option": "CONFIG_VFIO_PCI",
    },
    "system_profile_snapshot": { ... },
}
```

### Storage location

```python
PLAN_STATE_DIR = "~/.local/share/devops-control-plane/plans/"
# or
PLAN_STATE_DIR = "/var/lib/devops-control-plane/plans/"
```

File format: JSON, one file per plan.

### Resume detection

```python
def _check_pending_plans() -> list[dict]:
    """Check for paused plans that need resuming."""
    plans = []
    state_dir = Path(PLAN_STATE_DIR).expanduser()
    if state_dir.is_dir():
        for f in state_dir.glob("*.json"):
            plan = json.loads(f.read_text())
            if plan.get("pause_reason"):
                plans.append(plan)
    return plans
```

On startup or page load:
```
1. Check for pending plans
2. If found: show "Resume paused plan?" prompt
3. User confirms → resume from paused step
4. User cancels → mark plan as cancelled, archive
```

---

## Plan Engine State Machine

```
          ┌──────────┐
          │ CREATED  │
          └────┬─────┘
               │ start
          ┌────▼─────┐
     ┌───►│ RUNNING  │◄───┐
     │    └────┬─────┘    │
     │         │          │ resume
     │    ┌────▼─────┐    │
     │    │  PAUSED   │───┘
     │    └────┬─────┘
     │         │ cancel
     │    ┌────▼─────┐
     │    │CANCELLED │
     │    └──────────┘
     │
     │ all steps done
     │    ┌──────────┐
     └───►│  DONE    │
          └──────────┘
```

### State transitions

| From | To | Trigger |
|------|----|---------|
| CREATED | RUNNING | User starts plan |
| RUNNING | PAUSED | Step has `restart_required` |
| RUNNING | DONE | All steps completed |
| RUNNING | FAILED | Step failed, no recovery |
| PAUSED | RUNNING | User resumes after restart |
| PAUSED | CANCELLED | User cancels paused plan |

---

## UI Treatment

### Per restart level

| Level | Icon | Color | User action |
|-------|------|-------|-------------|
| session | ⚠️ | Yellow | Logout/login or `newgrp` |
| service | 🔄 | Blue | Automatic (no user action) |
| system | 🔴 | Red | Full reboot required |

### Pre-display (before execution)

The plan preview should show restart points:

```
Install Plan: Docker
──────────────────────────
  1. ☐ Install docker.io                      
  2. ☐ Start Docker service                   🔄 service restart
  3. ☐ Enable Docker at boot                  
  4. ☐ Add user to docker group               ⚠️ session restart
  5. ☐ Verify: docker ps                      
```

User sees the restart requirements BEFORE starting.

---

## Edge Cases

| Case | Impact | Handling |
|------|--------|---------|
| User never resumes | Plan stays paused forever | Expiry: warn after 7 days, archive after 30 |
| System changes between pause and resume | Profile may be different | Re-detect system profile on resume |
| Plan file corrupted | Can't resume | Validate JSON on load, offer restart-from-scratch |
| Multiple paused plans | Confusing | Show list, let user choose or cancel |
| Container: no reboot possible | system restart impossible | Don't offer system restart in containers |
| WSL: restart means different thing | `wsl --shutdown` from Windows | Detect WSL, adjust restart message |
| Service restart fails | Plan can't continue | Show error, offer retry or skip |
| newgrp not available | Can't use quick workaround | Only offer logout/login |
| Kernel boot fails after reboot | System stuck | Rollback instructions (GRUB old kernel) |

---

## Phase Roadmap

| Phase | Restart capability |
|-------|-------------------|
| Phase 2 | No restart handling. Docker group message shows but plan doesn't pause. |
| Phase 3 | `restart_required: "service"` — automatic service restart. |
| Phase 8 | Full restart system: all 3 levels, state persistence, resume, UI. |

---

## Traceability

| Topic | Source |
|-------|--------|
| Three restart levels | scope-expansion §2.8 |
| restart_required in recipe | scope-expansion §2.8 (post_install) |
| Resumable plans | scope-expansion §2.8 ("plan needs to be RESUMABLE") |
| State persistence | scope-expansion §2.8 ("persist across sessions") |
| Kernel reboot + rollback | scope-expansion §2.5 (GRUB old kernel) |
| Docker group problem | domain-devops-tools §Docker post-install |
| Service restart commands | domain-services §systemd commands |
| Kernel reboot safeguards | domain-kernel §safeguards |
| WSL restart | domain-wsl §restart |
| Phase 8 roadmap | scope-expansion §Phase 8 |
