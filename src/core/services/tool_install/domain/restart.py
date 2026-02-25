"""
L1 Domain — Restart detection and batching (pure).

Analyzes completed plan steps to detect restart requirements
and converts them into actionable steps or notifications.
No I/O, no subprocess.
"""

from __future__ import annotations


def detect_restart_needs(
    plan: dict,
    completed_steps: list[dict],
) -> dict:
    """Analyze completed plan steps to detect restart requirements.

    Returns::

        {
            "shell_restart": True/False,
            "service_restart": ["docker", "nginx"],
            "reboot_required": True/False,
            "reasons": ["PATH was modified — restart shell", ...],
        }
    """
    needs: dict = {
        "shell_restart": False,
        "service_restart": [],
        "reboot_required": False,
        "reasons": [],
    }

    # post_env means PATH changed → shell restart
    if plan.get("post_env"):
        needs["shell_restart"] = True
        needs["reasons"].append(
            "PATH was modified — restart shell to use new tools"
        )

    for step in completed_steps:
        # Config file change → service restart
        if step.get("type") == "config":
            service = step.get("restart_service")
            if service and service not in needs["service_restart"]:
                needs["service_restart"].append(service)
                needs["reasons"].append(
                    f"Config changed — restart {service}"
                )

        # Kernel module load → may need reboot
        if step.get("type") == "post_install":
            cmd = step.get("command", [])
            if cmd and cmd[0] == "modprobe":
                needs["reasons"].append(
                    f"Kernel module '{cmd[1] if len(cmd) > 1 else '?'}' loaded — reboot recommended"
                )

        # GPU driver → reboot
        if step.get("gpu_driver"):
            needs["reboot_required"] = True
            needs["reasons"].append(
                "GPU driver installed — reboot required"
            )

    return needs


def _batch_restarts(restart_needs: dict) -> list[dict]:
    """Convert restart_needs into minimal plan steps + notifications.

    Service restarts become service steps.
    Shell/reboot restarts become notification steps (never auto-executed).
    """
    steps: list[dict] = []

    # Deduplicate service restarts
    services = list(set(restart_needs.get("service_restart", [])))
    for svc in services:
        steps.append({
            "type": "service",
            "action": "restart",
            "service": svc,
            "needs_sudo": True,
            "label": f"Restart {svc}",
        })

    # Shell restart → notification (user must act)
    if restart_needs.get("shell_restart"):
        steps.append({
            "type": "notification",
            "message": "Restart your shell or run: source ~/.bashrc",
            "severity": "info",
        })

    # Reboot → notification (never auto-executed!)
    if restart_needs.get("reboot_required"):
        steps.append({
            "type": "notification",
            "message": "A system reboot is required for changes to take effect",
            "severity": "warning",
        })

    return steps
