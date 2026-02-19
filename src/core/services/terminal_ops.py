"""
Terminal operations — spawn interactive terminal sessions from the web UI.

Provides utilities to:
- Detect available terminal emulators on the host (with smoke-test)
- Report which terminals are available, broken, or installable
- Spawn a terminal with a given command or script
- Multi-path fallback: terminal → install → command for manual copy

Channel-independent: no Flask or HTTP dependency.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from pathlib import Path

logger = logging.getLogger(__name__)


# ── Terminal emulator registry ──────────────────────────────────────

# Each entry: (binary, label, args_template, apt_package)
# The args_template uses {cmd} as placeholder for the shell command.
# The smoke_args runs a no-op command to verify the terminal actually works.
_TERMINAL_REGISTRY: list[dict] = [
    {
        "name": "gnome-terminal",
        "label": "GNOME Terminal",
        "description": "Default GNOME desktop terminal",
        "apt_package": "gnome-terminal",
        "args": ["gnome-terminal", "--", "bash", "-c", "{cmd}"],
        "smoke_args": ["gnome-terminal", "--", "bash", "-c", "exit 0"],
    },
    {
        "name": "xterm",
        "label": "XTerm",
        "description": "Lightweight, reliable — no GPU needed",
        "apt_package": "xterm",
        "args": ["xterm", "-e", "bash", "-c", "{cmd}"],
        "smoke_args": ["xterm", "-e", "bash", "-c", "exit 0"],
    },
    {
        "name": "xfce4-terminal",
        "label": "XFCE Terminal",
        "description": "Lightweight XFCE desktop terminal",
        "apt_package": "xfce4-terminal",
        "args": ["xfce4-terminal", "-e", "bash -c '{cmd}'"],
        "smoke_args": ["xfce4-terminal", "-e", "bash -c 'exit 0'"],
    },
    {
        "name": "konsole",
        "label": "Konsole",
        "description": "KDE desktop terminal",
        "apt_package": "konsole",
        "args": ["konsole", "-e", "bash", "-c", "{cmd}"],
        "smoke_args": ["konsole", "-e", "bash", "-c", "exit 0"],
    },
    {
        "name": "kitty",
        "label": "Kitty",
        "description": "Modern GPU-accelerated terminal",
        "apt_package": "kitty",
        "args": ["kitty", "bash", "-c", "{cmd}"],
        "smoke_args": ["kitty", "bash", "-c", "exit 0"],
    },
    {
        "name": "x-terminal-emulator",
        "label": "System Default",
        "description": "OS-configured default terminal",
        "apt_package": None,  # Can't install this directly
        "args": ["x-terminal-emulator", "-e", "bash -c '{cmd}'"],
        "smoke_args": ["x-terminal-emulator", "-e", "bash -c 'exit 0'"],
    },
]

# Terminals worth offering to install (excludes x-terminal-emulator which is meta)
INSTALLABLE_TERMINALS = [
    t for t in _TERMINAL_REGISTRY if t["apt_package"] is not None
]


# ── Smoke-test detection ───────────────────────────────────────────

def _smoke_test_terminal(entry: dict, timeout: float = 2.0) -> bool:
    """Actually try to launch a terminal and check it doesn't crash.

    Spawns the terminal with a quick 'exit 0' command, waits *timeout*
    seconds, then checks if the process is still alive (good) or has
    already exited with a non-zero code (broken).

    Returns True if the terminal appears to work.
    """
    try:
        proc = subprocess.Popen(
            entry["smoke_args"],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        # Wait a bit and check if it crashed immediately
        time.sleep(min(timeout, 1.5))
        rc = proc.poll()

        if rc is None:
            # Still running — that's good, terminal opened successfully
            # Clean up: the "exit 0" will close it naturally
            return True
        elif rc == 0:
            # Exited cleanly (some terminals exit fast after "exit 0")
            return True
        else:
            # Crashed (negative = signal, positive = error)
            stderr_out = ""
            try:
                stderr_out = proc.stderr.read().decode(errors="replace")[:200]
            except Exception:
                pass
            logger.warning(
                "Terminal '%s' crashed (rc=%d): %s",
                entry["name"], rc, stderr_out.strip(),
            )
            return False
    except FileNotFoundError:
        return False
    except OSError as exc:
        logger.debug("Terminal '%s' smoke test error: %s", entry["name"], exc)
        return False


def detect_terminal() -> str | None:
    """Return the name of the first available AND working terminal, or None."""
    for entry in _TERMINAL_REGISTRY:
        if not shutil.which(entry["name"]):
            continue
        if _smoke_test_terminal(entry):
            return entry["name"]
    return None


def terminal_status() -> dict:
    """Full terminal status report for the frontend.

    Returns:
        {
            "has_working": bool,
            "working": [{"name": ..., "label": ...}, ...],
            "broken":  [{"name": ..., "label": ..., "reason": ...}, ...],
            "installable": [{"name": ..., "label": ..., "description": ..., "apt_package": ...}, ...],
        }
    """
    working = []
    broken = []
    installed_names = set()

    for entry in _TERMINAL_REGISTRY:
        if not shutil.which(entry["name"]):
            continue

        installed_names.add(entry["name"])

        if _smoke_test_terminal(entry):
            working.append({
                "name": entry["name"],
                "label": entry["label"],
            })
        else:
            # Resolve symlinks to show the real binary
            real_path = ""
            try:
                real_path = os.path.realpath(shutil.which(entry["name"]) or "")
            except Exception:
                pass
            broken.append({
                "name": entry["name"],
                "label": entry["label"],
                "real_binary": os.path.basename(real_path) if real_path else "",
                "reason": "crashes on startup",
            })

    # Installable = those not installed (and have an apt package)
    installable = []
    for entry in INSTALLABLE_TERMINALS:
        if entry["name"] not in installed_names:
            installable.append({
                "name": entry["name"],
                "label": entry["label"],
                "description": entry["description"],
                "apt_package": entry["apt_package"],
            })

    return {
        "has_working": len(working) > 0,
        "working": working,
        "broken": broken,
        "installable": installable,
    }


# ── Build terminal command ──────────────────────────────────────────

def _build_terminal_cmd(terminal_name: str, shell_cmd: str) -> list[str] | None:
    """Build the full argv list for spawning a terminal with *shell_cmd*."""
    for entry in _TERMINAL_REGISTRY:
        if entry["name"] == terminal_name:
            return [arg.replace("{cmd}", shell_cmd) for arg in entry["args"]]
    return None


# ── Spawn terminal ──────────────────────────────────────────────────

def spawn_terminal(
    command: str,
    *,
    cwd: Path | None = None,
    title: str = "",
    wait_after: bool = True,
) -> dict:
    """Spawn an interactive terminal running *command*.

    Args:
        command: Shell command to execute inside the terminal.
        cwd: Working directory for the spawned process.
        title: Optional window title (not all emulators support this).
        wait_after: If True, append 'read -p "Press Enter…"' so terminal
                    stays open for the user to see the result.

    Returns:
        {"ok": True, "terminal": "<name>", "message": "…"}       on success
        {"ok": False, "no_terminal": True, ...}                   when no working terminal
        {"ok": False, "fallback": True, "command": "…"}           explicit fallback
    """
    # Optionally append a pause so the terminal doesn't close immediately
    if wait_after:
        full_cmd = f'{command}; echo ""; read -p "Press Enter to close…"'
    else:
        full_cmd = command

    work_dir = str(cwd) if cwd else None

    # Try each terminal emulator in order
    for entry in _TERMINAL_REGISTRY:
        if not shutil.which(entry["name"]):
            continue

        argv = _build_terminal_cmd(entry["name"], full_cmd)
        if not argv:
            continue

        try:
            proc = subprocess.Popen(
                argv,
                cwd=work_dir,
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )

            # ── Crash detection: wait briefly and check ──
            time.sleep(1.5)
            rc = proc.poll()

            if rc is not None and rc != 0:
                # Process already died — this terminal is broken
                stderr_out = ""
                try:
                    stderr_out = proc.stderr.read().decode(errors="replace")[:300]
                except Exception:
                    pass
                logger.warning(
                    "Terminal '%s' crashed immediately (rc=%d): %s",
                    entry["name"], rc, stderr_out.strip(),
                )
                continue  # Try next terminal

            # Process is alive or exited cleanly — success
            logger.info(
                "Spawned terminal '%s' for command: %s",
                entry["name"], command[:80],
            )
            return {
                "ok": True,
                "terminal": entry["name"],
                "message": f"Terminal opened ({entry['label']}). Complete the operation there.",
            }

        except (FileNotFoundError, OSError) as exc:
            logger.debug("Terminal '%s' failed to launch: %s", entry["name"], exc)
            continue

    # ── No working terminal found ──
    # Get status to provide info to the frontend
    status = terminal_status()
    logger.warning(
        "No working terminal emulator — broken: %s, installable: %s",
        [b["name"] for b in status["broken"]],
        [i["name"] for i in status["installable"]],
    )

    return {
        "ok": False,
        "no_terminal": True,
        "command": command,
        "broken": status["broken"],
        "installable": status["installable"],
        "message": "No working terminal emulator found.",
    }


# ── Script-based terminal spawn ────────────────────────────────────

def spawn_terminal_script(
    script_content: str,
    *,
    cwd: Path | None = None,
    script_name: str = ".ops_script.sh",
    title: str = "",
) -> dict:
    """Write a bash script to a temp file and spawn a terminal to run it.

    This is for multi-step operations that are more complex than a single
    command line. The script is written under *cwd*/state/ by default.

    Returns the same dict shape as spawn_terminal().
    """
    if cwd is None:
        cwd = Path.cwd()

    import tempfile

    script_dir = Path(tempfile.gettempdir())
    script_path = script_dir / script_name

    script_path.write_text(script_content)
    script_path.chmod(0o755)

    result = spawn_terminal(
        f"bash {script_path}",
        cwd=cwd,
        title=title,
        wait_after=True,
    )

    # Include script path in result for cleanup
    result["script_path"] = str(script_path)
    return result
