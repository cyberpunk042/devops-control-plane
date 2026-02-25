# Domain: Rollback

> This document catalogs rollback capabilities for the tool install
> system: what can be undone, what can't, backup strategies for
> high-risk steps, rollback instructions embedded in plans, and
> the undo command catalog per install method.
>
> SOURCE DOCS: scope-expansion §2.5 (kernel safeguards, rollback),
>              domain-risk-levels §5 mandatory safeguards,
>              domain-risk-levels §backup implementation,
>              domain-kernel §rollback (GRUB old kernel)

---

## Overview

Not every operation can be undone. The system must:
1. Know what CAN be undone and HOW
2. Know what CANNOT be undone
3. Back up before any irreversible or high-risk step
4. Include rollback instructions in every plan

---

## Reversibility Matrix

### Fully reversible (clean undo)

| Operation | Undo command | Residue |
|-----------|-------------|---------|
| `pip install PKG` | `pip uninstall PKG` | None (venv-isolated) |
| `pip install PKG` (global) | `pip uninstall PKG` | None |
| `npm install -g PKG` | `npm uninstall -g PKG` | None |
| `cargo install PKG` | `cargo uninstall PKG` | None |
| `go install PKG` | `rm $(which PKG)` | GOPATH cache remains |
| `snap install PKG` | `snap remove PKG` | None |
| `flatpak install PKG` | `flatpak uninstall PKG` | None |
| `systemctl enable SVC` | `systemctl disable SVC` | None |
| `systemctl start SVC` | `systemctl stop SVC` | None |
| Binary to `~/.local/bin` | `rm ~/.local/bin/BINARY` | None |

### Mostly reversible (minor residue)

| Operation | Undo command | Residue |
|-----------|-------------|---------|
| `apt-get install PKG` | `apt-get remove PKG` | Config files remain |
| `apt-get install PKG` | `apt-get purge PKG` | Clean removal |
| `dnf install PKG` | `dnf remove PKG` | Config files may remain |
| `pacman -S PKG` | `pacman -Rns PKG` | Clean removal |
| `apk add PKG` | `apk del PKG` | None |
| `brew install PKG` | `brew uninstall PKG` | Cached downloads remain |
| `usermod -aG GRP USR` | `gpasswd -d USR GRP` | None after re-login |
| Config file write | Restore from backup | Backup must exist |
| Repository add (apt source) | Remove source file | apt-get update needed |
| Shell profile edit | Remove added lines | Source or re-login |
| Binary to `/usr/local/bin` | `rm /usr/local/bin/BINARY` | None |

### Partially reversible (significant effort)

| Operation | Undo approach | Difficulty |
|-----------|-------------|-----------|
| NVIDIA driver install | `apt purge nvidia-*` + reboot | Medium: display may break |
| Kernel module (modprobe) | `modprobe -r MODULE` | Medium: may need reboot |
| DKMS module install | `dkms remove` + reboot | Medium: kernel rebuild |
| Docker containers created | `docker rm` + `docker rmi` | Medium: data volumes |
| PPA add + install | Remove PPA + `apt purge` | Medium: dependency chain |

### Not reversible (damage possible)

| Operation | Why not reversible | Recovery |
|-----------|-------------------|----------|
| Kernel recompile (bad config) | System won't boot | GRUB: boot old kernel |
| GRUB modification (broken) | Bootloader corrupt | Live USB: reinstall GRUB |
| Bootloader update (failed) | System won't boot | Live USB recovery |
| Data directory deletion | Data gone | Backups only |
| `/etc` config overwrite (no backup) | Original lost | Package manager restore or manual |

---

## Undo Command Catalog

### Per install method

```python
UNDO_COMMANDS = {
    "pip": {
        "command": ["pip", "uninstall", "-y", "{package}"],
        "needs_sudo": False,
    },
    "pip_global": {
        "command": ["pip", "uninstall", "-y", "{package}"],
        "needs_sudo": True,
    },
    "apt": {
        "command": ["apt-get", "purge", "-y", "{package}"],
        "needs_sudo": True,
    },
    "dnf": {
        "command": ["dnf", "remove", "-y", "{package}"],
        "needs_sudo": True,
    },
    "pacman": {
        "command": ["pacman", "-Rns", "--noconfirm", "{package}"],
        "needs_sudo": True,
    },
    "apk": {
        "command": ["apk", "del", "{package}"],
        "needs_sudo": True,
    },
    "brew": {
        "command": ["brew", "uninstall", "{package}"],
        "needs_sudo": False,
    },
    "snap": {
        "command": ["snap", "remove", "{package}"],
        "needs_sudo": True,
    },
    "npm": {
        "command": ["npm", "uninstall", "-g", "{package}"],
        "needs_sudo": False,  # with nvm
    },
    "cargo": {
        "command": ["cargo", "uninstall", "{package}"],
        "needs_sudo": False,
    },
    "go": {
        "command": ["rm", "{binary_path}"],
        "needs_sudo": False,
    },
    "binary": {
        "command": ["rm", "{install_path}"],
        "needs_sudo": True,  # if in /usr/local/bin
    },
    "systemctl_enable": {
        "command": ["systemctl", "disable", "{service}"],
        "needs_sudo": True,
    },
    "systemctl_start": {
        "command": ["systemctl", "stop", "{service}"],
        "needs_sudo": True,
    },
    "group_add": {
        "command": ["gpasswd", "-d", "{user}", "{group}"],
        "needs_sudo": True,
    },
}
```

---

## Rollback Instructions in Plans

### Per-step rollback

Every plan step has an optional `rollback` field:

```python
{
    "label": "Install Docker",
    "command": ["apt-get", "install", "-y", "docker.io"],
    "needs_sudo": True,
    "risk": "medium",
    "rollback": {
        "command": ["apt-get", "purge", "-y", "docker.io"],
        "needs_sudo": True,
        "description": "Remove Docker and its configuration files",
    },
}
```

### Plan-level rollback

The plan stores a full rollback sequence (reverse order):

```python
{
    "tool": "docker",
    "steps": [...],
    "rollback_plan": [
        # Reverse order of completed steps
        {"label": "Remove docker group membership",
         "command": ["gpasswd", "-d", "{user}", "docker"],
         "needs_sudo": True},
        {"label": "Disable Docker service",
         "command": ["systemctl", "disable", "docker"],
         "needs_sudo": True},
        {"label": "Stop Docker service",
         "command": ["systemctl", "stop", "docker"],
         "needs_sudo": True},
        {"label": "Remove Docker package",
         "command": ["apt-get", "purge", "-y", "docker.io"],
         "needs_sudo": True},
    ],
}
```

### Rollback generation

```python
def _generate_rollback(completed_steps: list[dict]) -> list[dict]:
    """Generate rollback plan from completed steps (reverse order)."""
    rollback = []
    for step in reversed(completed_steps):
        if step.get("rollback"):
            rollback.append(step["rollback"])
    return rollback
```

---

## Backup Strategy

### What gets backed up

| Target | When | How |
|--------|------|-----|
| Config files | Before overwrite | `cp FILE FILE.backup.TIMESTAMP` |
| Config directories | Before modification | `cp -r DIR DIR.backup.TIMESTAMP` |
| Kernel config | Before recompilation | `cp /boot/config-$(uname -r) /boot/config-$(uname -r).backup` |
| GRUB config | Before modification | `cp /etc/default/grub /etc/default/grub.backup.TIMESTAMP` |
| Service unit files | Before modification | `cp FILE FILE.backup.TIMESTAMP` |

### Backup implementation

```python
def _backup(path: str) -> str | None:
    """Back up a file or directory. Returns backup path or None."""
    if not os.path.exists(path):
        return None
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{path}.backup.{timestamp}"
    if os.path.isdir(path):
        shutil.copytree(path, backup_path)
    else:
        shutil.copy2(path, backup_path)
    return backup_path
```

### Restore from backup

```python
def _restore(backup_path: str, original_path: str) -> bool:
    """Restore a backup to its original location."""
    if not os.path.exists(backup_path):
        return False
    if os.path.isdir(backup_path):
        if os.path.exists(original_path):
            shutil.rmtree(original_path)
        shutil.copytree(backup_path, original_path)
    else:
        shutil.copy2(backup_path, original_path)
    return True
```

### Backup record in plan state

```python
{
    "plan_id": "uuid-...",
    "backups": [
        {"original": "/etc/docker/daemon.json",
         "backup": "/etc/docker/daemon.json.backup.20250224_160000",
         "step_id": 3},
        {"original": "/etc/default/grub",
         "backup": "/etc/default/grub.backup.20250224_160100",
         "step_id": 7},
    ],
}
```

---

## Rollback Scenarios

### Scenario 1: Install fails midway

```
Plan: Install Docker (5 steps)

Step 1: apt-get install docker.io    ✅ done
Step 2: systemctl start docker       ✅ done
Step 3: systemctl enable docker      ❌ FAILED
Step 4: usermod -aG docker $USER     ⏳ not reached
Step 5: docker ps                    ⏳ not reached

→ Offer rollback:
  1. systemctl stop docker           (undo step 2)
  2. apt-get purge docker.io         (undo step 1)

→ Or offer retry from step 3
```

### Scenario 2: Kernel recompile fails to boot

```
Plan: Enable VFIO-PCI (8 steps)

Steps 1-6: completed (build, install kernel)
Step 7: reboot                       ✅ done
Step 8: verify VFIO                  ❌ system didn't boot

→ Recovery (manual, shown to user BEFORE step 7):
  1. At GRUB menu, select old kernel
  2. System boots with old kernel
  3. Remove bad kernel: dpkg --remove linux-image-BAD
  4. Update GRUB: update-grub
  5. Reboot to confirm old kernel works
```

### Scenario 3: Config file breaks service

```
Plan: Configure journald

Step 1: Write /etc/systemd/journald.conf.d/custom.conf   ✅
Step 2: systemctl restart systemd-journald                ❌ FAILED

→ Automatic rollback:
  1. Restore /etc/systemd/journald.conf.d/custom.conf from backup
  2. systemctl restart systemd-journald
  3. Show: "Config reverted. The values you entered may be invalid."
```

---

## Auto-Rollback vs Manual Rollback

### Auto-rollback

For medium-risk steps where rollback is safe and automated:

```python
if step_failed and step["risk"] in ("low", "medium"):
    if step.get("rollback"):
        show_message("Step failed. Rolling back...")
        execute(step["rollback"])
```

### Manual rollback (instructions only)

For high-risk steps where automated rollback could make things worse:

```python
if step_failed and step["risk"] == "high":
    show_instructions(
        "This step cannot be automatically rolled back. "
        "Follow these instructions:",
        step["rollback"]["manual_instructions"],
    )
```

### Decision table

| Risk | Failure | Action |
|------|---------|--------|
| low | Step fails | Auto-retry once, then skip |
| medium | Step fails | Offer: retry / rollback / skip |
| high | Step fails | Show manual instructions, PAUSE |
| any | Plan cancelled | Offer full rollback of completed steps |

---

## Edge Cases

| Case | Impact | Handling |
|------|--------|---------|
| Backup disk full | Can't create backup | BLOCK high-risk step |
| Backup path already exists | Name collision | Timestamp ensures uniqueness |
| Rollback command fails | Stuck in broken state | Show manual instructions |
| Package has dependencies installed | `apt purge` removes shared deps | Use `apt remove` (safer) instead |
| Config file modified by user between install and rollback | User changes lost | Warn before restoring backup |
| Kernel rollback: old kernel deleted | No fallback kernel | BLOCK kernel ops if only one kernel |
| Container: no kernel rollback | Kernel ops impossible | Don't offer kernel operations |
| Partial rollback | Some steps rolled back, some not | Track rollback state per step |
| Rollback of a rollback | Redo the original install | Not supported — run fresh plan |

---

## Phase Roadmap

| Phase | Rollback capability |
|-------|--------------------|
| Phase 2 | No rollback. Manual uninstall only. |
| Phase 3 | Undo command catalog. "Uninstall" button per tool. |
| Phase 4 | Per-step rollback in plan. Auto-rollback for low/medium. |
| Phase 6 | Backup before high-risk. Manual instructions for kernel. |
| Phase 8 | Full rollback plan generation. Rollback state tracking. |

---

## Traceability

| Topic | Source |
|-------|--------|
| Kernel rollback (GRUB) | scope-expansion §2.5 |
| 5 mandatory safeguards | domain-risk-levels §safeguards |
| Backup implementation | domain-risk-levels §backup |
| Risk levels determining rollback | domain-risk-levels §three levels |
| Config file backup | domain-config-files §backup field |
| apt purge vs remove | domain-package-managers §apt |
| Kernel only-one check | domain-kernel §safeguards |
| Plan state persistence | domain-restart §state persistence |
