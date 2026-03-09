"""
Chrome shortcut management — reading, modifying, and cloning Windows .lnk files.

Extracted from ``src.ui.web.routes.tab_mesh`` to serve as shared
infrastructure for both Tab Mesh and the Scripts System execution plans.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess

logger = logging.getLogger(__name__)


# Expected icon indices for Chrome shortcuts.
CHROME_ICON_DEBUG = "%ProgramFiles%\\Google\\Chrome\\Application\\chrome.exe,8"
CHROME_ICON_NORMAL = "%ProgramFiles%\\Google\\Chrome\\Application\\chrome.exe,4"


def shortcut_locations(windows_user: str) -> dict[str, str]:
    """Return all known Chrome shortcut paths (WSL paths)."""
    return {
        "taskbar": (
            f"/mnt/c/Users/{windows_user}/AppData/Roaming"
            f"/Microsoft/Internet Explorer/Quick Launch"
            f"/User Pinned/TaskBar/Google Chrome.lnk"
        ),
        "desktop": f"/mnt/c/Users/{windows_user}/Desktop/Google Chrome.lnk",
        "start_menu_global": (
            "/mnt/c/ProgramData/Microsoft/Windows"
            "/Start Menu/Programs/Google Chrome.lnk"
        ),
        "start_menu_user": (
            f"/mnt/c/Users/{windows_user}/AppData/Roaming"
            f"/Microsoft/Windows/Start Menu/Programs/Google Chrome.lnk"
        ),
    }


def backup_shortcut_locations(windows_user: str) -> dict[str, str]:
    """Return backup ("Chrome - OLD") paths alongside each main shortcut.

    Same keys as ``shortcut_locations``; replaces ``Google Chrome.lnk``
    with ``Chrome - OLD.lnk`` in each path.
    """
    main = shortcut_locations(windows_user)
    return {
        key: path.replace("Google Chrome.lnk", "Chrome - OLD.lnk")
        for key, path in main.items()
    }


def wsl_to_win_path(wsl_path: str) -> str:
    """Convert a WSL /mnt/c/... path to Windows C:\\... path."""
    if wsl_path.startswith("/mnt/c/"):
        return "C:\\" + wsl_path[7:].replace("/", "\\")
    return wsl_path


def read_shortcut(wsl_path: str) -> dict | None:
    """Read a .lnk shortcut's target, arguments, icon, and description.

    Returns dict with keys: target, args, icon, description — or None
    if unreadable.  ``icon`` is the raw ``IconLocation`` string from
    the shortcut (e.g. ``%ProgramFiles%\\...\\chrome.exe,8``).
    """
    if not os.path.exists(wsl_path):
        return None
    if not shutil.which("powershell.exe"):
        return None

    win_path = wsl_to_win_path(wsl_path)
    ps_cmd = (
        "$shell = New-Object -ComObject WScript.Shell; "
        f"$lnk = $shell.CreateShortcut('{win_path}'); "
        "Write-Host '::TARGET::' $lnk.TargetPath; "
        "Write-Host '::ARGS::' $lnk.Arguments; "
        "Write-Host '::ICON::' $lnk.IconLocation; "
        "Write-Host '::DESC::' $lnk.Description"
    )
    try:
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=10,
        )
        target = ""
        args = ""
        icon = ""
        description = ""
        for line in r.stdout.splitlines():
            if "::TARGET::" in line:
                target = line.split("::TARGET::", 1)[1].strip()
            elif "::ARGS::" in line:
                args = line.split("::ARGS::", 1)[1].strip()
            elif "::ICON::" in line:
                icon = line.split("::ICON::", 1)[1].strip()
            elif "::DESC::" in line:
                description = line.split("::DESC::", 1)[1].strip()
        return {
            "target": target,
            "args": args,
            "icon": icon,
            "description": description,
        }
    except Exception as exc:
        logger.warning("Failed to read shortcut %s: %s", win_path, exc)
        return None


def modify_shortcut(
    wsl_path: str,
    add_port: int,
    user_data_dir: str | None,
    icon_location: str = "",
) -> bool:
    """Modify a .lnk shortcut to add Chrome debugging flags.

    Reads current arguments, appends missing flags, writes back.
    Optionally sets ``IconLocation`` (e.g. ``chrome.exe,8``).
    If the write fails (e.g. system directory), retries with UAC
    elevation which pops a Windows confirmation dialog.
    """
    if not shutil.which("powershell.exe"):
        return False

    current = read_shortcut(wsl_path)
    if current is None:
        return False

    existing_args = current["args"]

    # Build new args — replace or add flags as needed
    new_args = existing_args
    if f"--remote-debugging-port={add_port}" not in existing_args:
        new_args = f"{new_args} --remote-debugging-port={add_port}".strip()

    if user_data_dir:
        target_arg = f'--user-data-dir="{user_data_dir}"'
        if "--user-data-dir=" not in existing_args:
            # No user-data-dir set — add it
            new_args = f'{new_args} {target_arg}'.strip()
        elif target_arg not in existing_args:
            # Remove the old --user-data-dir=... (with or without quotes)
            new_args = re.sub(
                r'--user-data-dir="[^"]*"',
                lambda _: target_arg,
                new_args,
            )
            # Also handle unquoted form
            if target_arg not in new_args:
                new_args = re.sub(
                    r'--user-data-dir=\S+',
                    lambda _: target_arg,
                    new_args,
                )

    # Check if icon also needs updating
    icon_needs_update = (
        icon_location
        and current.get("icon", "").strip() != icon_location.strip()
    )

    if new_args == existing_args and not icon_needs_update:
        logger.info("Shortcut already has required flags: %s", wsl_path)
        return True  # Already configured

    win_path = wsl_to_win_path(wsl_path)
    # Escape single quotes in the arguments for PowerShell
    safe_args = new_args.replace("'", "''")
    icon_line = ""
    if icon_location:
        safe_icon = icon_location.replace("'", "''")
        icon_line = f"$lnk.IconLocation = '{safe_icon}'; "
    ps_cmd = (
        "$shell = New-Object -ComObject WScript.Shell; "
        f"$lnk = $shell.CreateShortcut('{win_path}'); "
        f"$lnk.Arguments = '{safe_args}'; "
        f"{icon_line}"
        "$lnk.Save()"
    )
    try:
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            logger.info("Updated shortcut: %s → args: %s", win_path, new_args)
            return True

        # Check if it's a permissions issue — retry with UAC elevation
        if "UnauthorizedAccessException" in r.stderr:
            logger.info(
                "Permission denied for %s, retrying with elevation...",
                win_path,
            )
            return modify_shortcut_elevated(
                win_path, safe_args, icon_location=icon_location,
            )

        logger.warning(
            "PowerShell shortcut update failed (rc=%d): %s",
            r.returncode, r.stderr.strip(),
        )
        return False
    except Exception as exc:
        logger.warning("Failed to modify shortcut %s: %s", win_path, exc)
        return False


def modify_shortcut_elevated(
    win_path: str,
    safe_args: str,
    *,
    icon_location: str = "",
) -> bool:
    """Modify a shortcut using UAC-elevated PowerShell.

    Writes the modification script to a temp .ps1 file, then
    launches an elevated PowerShell process to execute it.
    This avoids all quoting issues with paths containing spaces.
    """
    import tempfile

    icon_line = ""
    if icon_location:
        safe_icon = icon_location.replace("'", "''")
        icon_line = f"$lnk.IconLocation = '{safe_icon}'\n"

    # Write the PS1 script to a temp file on the Windows filesystem
    # (elevated PowerShell needs to read it, so it must be on C:\)
    inner_script = (
        "$shell = New-Object -ComObject WScript.Shell\n"
        f"$lnk = $shell.CreateShortcut('{win_path}')\n"
        f"$lnk.Arguments = '{safe_args}'\n"
        f"{icon_line}"
        "$lnk.Save()\n"
    )
    try:
        # Write to Windows temp dir so the elevated process can access it
        tmp_dir = "/mnt/c/Windows/Temp"
        script_path_wsl = f"{tmp_dir}/cdp_shortcut_fix.ps1"
        script_path_win = "C:\\Windows\\Temp\\cdp_shortcut_fix.ps1"

        with open(script_path_wsl, "w", encoding="utf-8") as f:
            f.write(inner_script)

        # Run the script elevated — triggers UAC prompt
        elevated_cmd = (
            "Start-Process powershell -Verb RunAs -Wait "
            f"-ArgumentList '-NoProfile','-ExecutionPolicy','Bypass',"
            f"'-File','{script_path_win}'"
        )
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", elevated_cmd],
            capture_output=True, text=True, timeout=30,
        )

        # Clean up temp file
        try:
            os.remove(script_path_wsl)
        except OSError:
            pass

        if r.returncode == 0:
            logger.info("Elevated update succeeded: %s", win_path)
            return True
        logger.warning(
            "Elevated update failed (rc=%d): %s",
            r.returncode, r.stderr.strip(),
        )
        return False
    except Exception as exc:
        logger.warning("Elevated shortcut update failed: %s", exc)
        return False


def clone_shortcut(
    source_wsl_path: str,
    dest_wsl_path: str,
    *,
    clear_args: bool = True,
    icon_location: str = "",
) -> bool:
    """Clone a .lnk shortcut to a new path.

    Reads the source shortcut, creates a new shortcut at ``dest_wsl_path``
    with the same target.  If ``clear_args`` is True (default), the clone
    has no arguments — giving the user a clean Chrome launch.

    The ``icon_location`` is set if provided (e.g. ``chrome.exe,4``).

    Returns True on success, False on failure.
    """
    if not shutil.which("powershell.exe"):
        return False

    source = read_shortcut(source_wsl_path)
    if source is None:
        return False

    dest_win = wsl_to_win_path(dest_wsl_path)
    target = source["target"]
    args = "" if clear_args else source["args"]
    icon = icon_location or source.get("icon", "")
    desc = source.get("description", "")

    # Escape single quotes for PowerShell
    safe_args = args.replace("'", "''")
    safe_icon = icon.replace("'", "''")
    safe_desc = desc.replace("'", "''")

    ps_cmd = (
        "$shell = New-Object -ComObject WScript.Shell; "
        f"$lnk = $shell.CreateShortcut('{dest_win}'); "
        f"$lnk.TargetPath = '{target}'; "
        f"$lnk.Arguments = '{safe_args}'; "
        f"$lnk.IconLocation = '{safe_icon}'; "
        f"$lnk.Description = '{safe_desc}'; "
        "$lnk.Save()"
    )
    try:
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            logger.info(
                "Cloned shortcut: %s → %s (args cleared: %s)",
                source_wsl_path, dest_win, clear_args,
            )
            return True
        logger.warning(
            "Clone shortcut failed (rc=%d): %s",
            r.returncode, r.stderr.strip(),
        )
        return False
    except Exception as exc:
        logger.warning("Failed to clone shortcut to %s: %s", dest_win, exc)
        return False
