# Domain: Risk Levels

> This document catalogs risk tagging for the tool install system:
> low (pip install), medium (apt install), high (kernel rebuild).
> UI treatment per level, confirmation gates, double-confirm for
> high-risk operations, and how risk propagates through plans.
>
> SOURCE DOCS: domain-kernel §risk classification (7 ops × 3 levels),
>              domain-disabled-options §risk levels,
>              scope-expansion §2.5 (kernel safeguards),
>              scope-expansion §2.8 (restart requirements)

---

## Overview

Every installation step has a risk level. Risk determines:
1. What the user sees (UI indicators)
2. What confirmation is required (none, confirm, double-confirm)
3. What safeguards are enforced (backup, rollback instructions)
4. Whether the step can auto-execute or must be manual

### Three levels

| Level | Color | Icon | Meaning |
|-------|-------|------|---------|
| **low** | Green | ✅ | User-space, easily reversible |
| **medium** | Yellow | ⚠️ | System-level, needs sudo, reversible |
| **high** | Red | 🔴 | May affect boot/stability, hard to reverse |

---

## Risk Classification

### Operations by risk level

#### Low risk

| Operation | Why low | Reversibility |
|-----------|---------|---------------|
| pip install | User-space, venv isolated | `pip uninstall` |
| npm install -g | User-space (with nvm) | `npm uninstall -g` |
| cargo install | `~/.cargo/bin`, user-space | `cargo uninstall` |
| pip install --upgrade | Replaces previous version | `pip install OLD_VERSION` |
| Download data pack | Disk space only | Delete files |
| Shell profile edit (.bashrc) | Single file, user-owned | Remove added lines |

#### Medium risk

| Operation | Why medium | Reversibility |
|-----------|-----------|---------------|
| apt-get install | System-level, needs sudo | `apt-get remove` |
| dnf install | System-level, needs sudo | `dnf remove` |
| snap install | System-level, needs sudo | `snap remove` |
| systemctl enable | Changes boot behavior | `systemctl disable` |
| systemctl restart | Service briefly unavailable | Service restarts itself |
| usermod -aG | Group membership change | `gpasswd -d user group` |
| Config file write | Overwrites existing config | Backup restore |
| Repository add (apt source) | Changes package sources | Remove source file |
| Binary download to /usr/local | System-level path | Delete binary |

#### High risk

| Operation | Why high | Reversibility |
|-----------|---------|---------------|
| Kernel module load (modprobe) | Kernel-level | `modprobe -r` (sometimes) |
| Kernel recompilation | May prevent boot | GRUB old kernel (if it still works) |
| NVIDIA driver install | May break display | Boot to recovery, purge driver |
| GRUB modification | May prevent boot | GRUB recovery or live USB |
| VFIO passthrough | GPU becomes unusable for host | Undo kernel params + reboot |
| DKMS module install | Kernel-level, persists across updates | DKMS remove |
| Bootloader update | May prevent boot | Live USB recovery |

---

## UI Treatment

### Per level

```
LOW RISK (no special treatment):
┌──────────────────────────────────────┐
│ ☐ Install ruff (pip)          ✅ low │
│ ☐ Install black (pip)         ✅ low │
│ ☐ Install pytest (pip)        ✅ low │
└──────────────────────────────────────┘

MEDIUM RISK (yellow indicator):
┌──────────────────────────────────────┐
│ ☐ Install docker (apt)        ⚠️ med │
│   Requires sudo password              │
│ ☐ Enable Docker at boot       ⚠️ med │
│ ☐ Add user to docker group    ⚠️ med │
│   Session restart needed              │
└──────────────────────────────────────┘

HIGH RISK (red indicator + warning):
┌──────────────────────────────────────┐
│ ☐ Install NVIDIA driver       🔴 high│
│   ⚠️ May affect display output       │
│   Reboot required after install      │
│                                      │
│ ☐ Rebuild kernel with VFIO    🔴 high│
│   ⚠️ May prevent system boot         │
│   Backup current kernel first        │
│   GRUB will have old kernel entry    │
└──────────────────────────────────────┘
```

### Summary bar

```
Plan Summary:
  6 steps total │ 3 low │ 2 medium │ 1 high
  ⚠️ This plan contains high-risk operations
```

---

## Confirmation Gates

### No confirmation (low risk)

```python
# Auto-execute without asking
if step["risk"] == "low":
    execute(step)
```

Low-risk steps run as part of the plan flow. The user already
confirmed the overall plan — no per-step confirmation needed.

### Single confirmation (medium risk)

```python
# Confirm before first medium-risk step
if step["risk"] == "medium" and not medium_confirmed:
    confirmed = show_confirm(
        "This plan requires administrator access (sudo). "
        "Continue?"
    )
    if not confirmed:
        pause_plan()
```

Medium-risk steps need ONE confirmation at the start of the
medium-risk section. Not per-step (too annoying).

### Double confirmation (high risk)

```python
# Each high-risk step requires individual confirmation
if step["risk"] == "high":
    # Gate 1: Warning + details
    show_warning(
        title="High-risk operation",
        message=step["warning"],
        details=[
            f"Operation: {step['label']}",
            f"Risk: {step['risk_description']}",
            f"Rollback: {step.get('rollback', 'See instructions below')}",
        ],
    )

    # Gate 2: Type confirmation
    confirmed = show_type_confirm(
        prompt="Type 'I understand' to proceed:",
        expected="I understand",
    )
    if not confirmed:
        pause_plan()
```

High-risk steps need:
1. **Warning dialog** with full risk description
2. **Type-to-confirm** (not just a button click)

---

## Risk in Recipe Format

### Step-level risk

```python
{
    "label": "Install NVIDIA driver",
    "command": ["apt-get", "install", "-y", "nvidia-driver-535"],
    "needs_sudo": True,
    "risk": "high",
    "risk_description": "NVIDIA driver installation may temporarily "
                        "disrupt display output. A system reboot is "
                        "required after installation.",
    "rollback": "sudo apt-get purge nvidia-driver-535 && sudo reboot",
    "backup_before": ["/etc/modprobe.d/"],
    "restart_required": "system",
}
```

### Risk fields

| Field | Type | Required | Purpose |
|-------|------|----------|---------|
| `risk` | str | ❌ | `"low"` (default), `"medium"`, `"high"` |
| `risk_description` | str | When high | Human-readable explanation |
| `rollback` | str | When high | Command or instructions to undo |
| `backup_before` | list[str] | When high | Paths to back up before step |
| `warning` | str | When medium+ | Short warning text for UI |

### Default risk inference

If `risk` is not specified, infer from context:

```python
def _infer_risk(step: dict) -> str:
    if step.get("restart_required") == "system":
        return "high"
    if "kernel" in step.get("label", "").lower():
        return "high"
    if "driver" in step.get("label", "").lower():
        return "high"
    if step.get("needs_sudo"):
        return "medium"
    return "low"
```

---

## Plan-Level Risk

### Highest step determines plan risk

```python
def _plan_risk(steps: list[dict]) -> str:
    risks = [s.get("risk", "low") for s in steps]
    if "high" in risks:
        return "high"
    if "medium" in risks:
        return "medium"
    return "low"
```

### Plan preview shows aggregate

```
┌─ Install Plan: GPU Passthrough ───────────────────┐
│                                                    │
│ ⚠️ PLAN RISK: HIGH                                │
│                                                    │
│ This plan contains operations that may affect      │
│ system boot. Ensure you have:                      │
│ • A backup of your current kernel config           │
│ • Access to GRUB boot menu for recovery            │
│ • A live USB for emergency recovery                │
│                                                    │
│ Steps:                                             │
│  1. ✅ Install build deps            low           │
│  2. ⚠️ Load vfio-pci module         medium        │
│  3. ⚠️ Persist module on boot       medium        │
│  4. 🔴 Update GRUB                  high          │
│  5. 🔴 Reboot                       high          │
│  6. ✅ Verify VFIO                   low           │
│                                                    │
│ [Cancel]                    [I understand, proceed] │
└────────────────────────────────────────────────────┘
```

---

## Mandatory Safeguards (High Risk)

### 5 rules for high-risk steps

From domain-kernel §safeguards:

| # | Safeguard | Implementation |
|---|-----------|---------------|
| 1 | Never auto-execute | `risk: "high"` → always double-confirm |
| 2 | Backup before | `backup_before` paths copied with timestamp |
| 3 | Rollback instructions | `rollback` field in step, shown in UI |
| 4 | Restart awareness | `restart_required` field, plan pauses |
| 5 | Risk tag visible | 🔴 indicator in every UI where step appears |

### Backup implementation

```python
def _backup_before_step(step: dict) -> list[str]:
    """Back up paths listed in backup_before."""
    backed_up = []
    for path in step.get("backup_before", []):
        if os.path.exists(path):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = f"{path}.backup.{timestamp}"
            if os.path.isdir(path):
                shutil.copytree(path, backup_path)
            else:
                shutil.copy2(path, backup_path)
            backed_up.append(backup_path)
    return backed_up
```

---

## Assistant Panel Integration

### Risk-aware guidance

The assistant panel adjusts its tone based on risk:

| Risk | Tone | Content |
|------|------|---------|
| low | Informational | "This installs ruff, a fast Python linter." |
| medium | Advisory | "This requires administrator access. The package can be removed later with apt-get remove." |
| high | Warning | "⚠️ This operation modifies the kernel configuration. If misconfigured, the system may not boot. A backup of your current config will be created automatically." |

### High-risk assistant content

```
┌─ Assistant ──────────────────────────────────────┐
│                                                    │
│ 🔴 High-Risk Operation                            │
│                                                    │
│ You are about to modify the GRUB bootloader        │
│ configuration. This controls which kernel boots.   │
│                                                    │
│ What happens:                                      │
│ • Current kernel config is backed up               │
│ • GRUB is updated with the new kernel entry        │
│ • A reboot is required                             │
│                                                    │
│ If something goes wrong:                           │
│ • At the GRUB menu, select the old kernel          │
│ • If GRUB doesn't appear, hold Shift during boot   │
│ • Last resort: boot from USB, restore backup       │
│                                                    │
│ Your backup: /boot/grub/grub.cfg.backup.20250224   │
│                                                    │
└────────────────────────────────────────────────────┘
```

---

## Risk Escalation

### When risk increases during execution

```python
# Original plan had medium risk
# During execution, an error suggests kernel module needed
# → Risk escalates to high

def _escalate_risk(plan: dict, new_risk: str, reason: str):
    plan["risk"] = new_risk
    plan["risk_escalation"] = {
        "original": plan.get("original_risk", plan["risk"]),
        "escalated_to": new_risk,
        "reason": reason,
    }
    # PAUSE and re-confirm
    pause_plan("Risk level has changed. Review and confirm.")
```

### Example

```
Original plan: Install Docker (medium risk)
→ Step 3 fails: kernel module not loaded
→ Resolver suggests: modprobe overlay
→ Risk escalates: medium → high
→ Plan PAUSES: "This plan now requires kernel module loading.
   Risk has increased. Review and confirm."
```

---

## Edge Cases

| Case | Impact | Handling |
|------|--------|---------|
| User skips confirmation | Step not executed | Plan pauses at that step |
| Backup fails (no space) | Can't create safety net | BLOCK high-risk step, show error |
| Rollback instructions unclear | User stuck | Provide specific commands, not vague text |
| Risk inferred wrong | Too cautious or too lax | Explicit `risk` field overrides inference |
| Container: high-risk impossible | Kernel ops can't work | Disable high-risk options |
| Multiple high-risk steps | Confirm fatigue | Group into one confirmation if related |
| Plan changes after confirmation | Stale confirmation | Re-confirm if steps change |
| Risk escalation mid-plan | User didn't expect this | Pause, explain, re-confirm |

---

## Phase Roadmap

| Phase | Risk capability |
|-------|----------------|
| Phase 2 | Implicit: sudo steps need password. No explicit risk tagging. |
| Phase 3 | Risk labels on steps. Warning text for medium+. |
| Phase 4 | Confirmation gates. Double-confirm for high. |
| Phase 6 | High-risk kernel/GPU operations with full safeguards. |
| Phase 8 | Risk escalation. Dynamic risk assessment. |

---

## Traceability

| Topic | Source |
|-------|--------|
| 7 kernel ops × 3 risk levels | domain-kernel §risk classification |
| 5 mandatory safeguards | domain-kernel §safeguards |
| Risk in option schema | domain-disabled-options §risk levels |
| 9 operation risk mappings | domain-disabled-options §mapping ops to risk |
| Restart requirements | domain-restart §restart levels |
| Kernel rollback (GRUB) | domain-kernel §rollback |
| Backup before step | scope-expansion §2.5 (safeguards) |
| Type-to-confirm pattern | scope-expansion §2.5 (confirmation gates) |
| Assistant risk-aware tone | assistant-content-principles |
