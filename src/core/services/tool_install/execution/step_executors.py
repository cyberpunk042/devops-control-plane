"""
L4 Execution — Step executors.

Each ``_execute_*_step`` function handles one step type.
All use ``_run_subprocess`` for actual command execution.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from src.core.services.tool_install.data.recipes import TOOL_RECIPES
from src.core.services.tool_install.data.undo_catalog import UNDO_COMMANDS
from src.core.services.tool_install.detection.system_deps import check_system_deps
from src.core.services.tool_install.detection.tool_version import get_tool_version
from src.core.services.tool_install.execution.script_verify import (
    is_curl_pipe_command,
    extract_script_url,
    download_and_verify_script,
    rewrite_curl_pipe_to_safe,
    cleanup_script,
)
from src.core.services.tool_install.execution.subprocess_runner import _run_subprocess

logger = logging.getLogger(__name__)


def _execute_package_step(
    step: dict, *, sudo_password: str = "",
) -> dict[str, Any]:
    """Install system packages, skipping already-installed ones.

    Uses ``check_system_deps()`` (Phase 2.1) to determine which
    packages are missing, then rebuilds the install command with
    only the missing packages via ``_build_pkg_install_cmd()``.
    """
    packages = step.get("packages", [])
    if not packages:
        return {"ok": True, "message": "No packages to install", "skipped": True}

    # Determine package manager from command (first token)
    pm = step.get("package_manager")
    if not pm:
        # Infer from the command: "apt-get" → "apt", "dnf" → "dnf"
        cmd_bin = step["command"][0] if step.get("command") else "apt-get"
        pm = cmd_bin.replace("-get", "")  # apt-get → apt

    result = check_system_deps(packages, pm)
    missing = result.get("missing", [])

    if not missing:
        return {
            "ok": True,
            "message": "All packages already installed",
            "skipped": True,
        }

    # Rebuild command with only missing packages
    cmd = _build_pkg_install_cmd(missing, pm)
    return _run_subprocess(
        cmd,
        needs_sudo=step.get("needs_sudo", True),
        sudo_password=sudo_password,
        timeout=step.get("timeout", 120),
    )


def _execute_repo_step(
    step: dict, *, sudo_password: str = "",
) -> dict[str, Any]:
    """Set up a package repository (GPG key + source list).

    Handles both single-command steps and multi-step ``sub_steps``.
    Each sub-step runs in order; first failure aborts.
    """
    sub_steps = step.get("sub_steps", [step])
    results = []

    for sub_step in sub_steps:
        result = _run_subprocess(
            sub_step["command"],
            needs_sudo=sub_step.get("needs_sudo", True),
            sudo_password=sudo_password,
            timeout=sub_step.get("timeout", 60),
        )
        results.append(result)
        if not result["ok"]:
            return result

    return {
        "ok": True,
        "message": "Repository configured",
        "sub_results": results,
    }


def _execute_command_step(
    step: dict,
    *,
    sudo_password: str = "",
    env_overrides: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Execute a command step (tool install or post_install action).

    If the command is a curl-pipe-bash pattern and the step has a
    ``script_sha256`` field, the script is downloaded to a tempfile,
    hash-verified, and executed from the file instead of piping.
    """
    command = step["command"]

    # ── M2: Script integrity verification ──────────────────
    if is_curl_pipe_command(command):
        url = extract_script_url(command)
        expected_sha = step.get("script_sha256")

        if url:
            dl = download_and_verify_script(url, expected_sha256=expected_sha)
            if not dl["ok"]:
                return dl  # Checksum mismatch or download failure

            if not expected_sha:
                logger.warning(
                    "M2: curl-pipe-bash with no script_sha256 for %s — "
                    "executing from tempfile but unverified (sha256=%s)",
                    url, dl["sha256"],
                )

            # Rewrite command to use verified tempfile
            safe_cmd = rewrite_curl_pipe_to_safe(command, dl["path"])
            try:
                result = _run_subprocess(
                    safe_cmd,
                    needs_sudo=step.get("needs_sudo", False),
                    sudo_password=sudo_password,
                    timeout=step.get("timeout", 120),
                    env_overrides=env_overrides,
                )
                result["script_sha256"] = dl["sha256"]
                result["script_verified"] = bool(expected_sha)
                return result
            finally:
                cleanup_script(dl["path"])

    # Standard execution (no curl pipe)
    return _run_subprocess(
        command,
        needs_sudo=step.get("needs_sudo", False),
        sudo_password=sudo_password,
        timeout=step.get("timeout", 120),
        env_overrides=env_overrides,
    )


def _execute_verify_step(
    step: dict,
    *,
    env_overrides: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Verify a tool is installed and working.

    Checks PATH first (with env_overrides for non-standard locations
    like ``~/.cargo/bin``).  If the binary isn't found, returns an
    advisory error instead of running the command.
    """
    cli = step.get("cli", step["command"][0])

    # Build expanded PATH for lookup
    check_path = os.environ.get("PATH", "")
    if env_overrides and "PATH" in env_overrides:
        check_path = os.path.expandvars(env_overrides["PATH"])

    binary = shutil.which(cli, path=check_path)
    if not binary:
        return {
            "ok": False,
            "error": f"'{cli}' not found in PATH after install",
            "needs_shell_restart": True,
        }

    # Run verify command
    return _run_subprocess(
        step["command"],
        needs_sudo=False,
        timeout=10,
        env_overrides=env_overrides,
    )


def _execute_install_step(
    step: dict,
    *,
    sudo_password: str = "",
    env_overrides: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Run an install command in a build directory (make install, cmake --install)."""
    return _run_subprocess(
        step["command"],
        needs_sudo=step.get("needs_sudo", True),
        sudo_password=sudo_password,
        timeout=step.get("timeout", 600),  # M3: build installs can be slow
        env_overrides=env_overrides,
        cwd=step.get("cwd"),
    )


def _execute_cleanup_step(
    step: dict,
) -> dict[str, Any]:
    """Clean up build artifacts.

    Removes the build directory.  Non-fatal — a failed cleanup
    only produces a warning, not a plan failure.
    """
    import shutil as sh

    target = step.get("target")
    if not target:
        # Fall back to command's last arg or cwd
        cmd = step.get("command", [])
        target = cmd[-1] if cmd else step.get("cwd")

    if target and Path(target).exists():
        try:
            sh.rmtree(target, ignore_errors=True)
            return {"ok": True, "message": f"Cleaned up {target}"}
        except Exception as e:
            return {"ok": True, "warning": f"Cleanup partial: {e}"}

    return {"ok": True, "message": "Nothing to clean"}


def _execute_download_step(
    step: dict,
) -> dict[str, Any]:
    """Download a data pack with disk space check, resume, and checksum verification.

    Supports:
      - **Resume**: If a partial file exists, attempts to resume via
        HTTP Range header instead of re-downloading.
      - **Progress**: Logs download progress every 5%.
      - **Disk check**: Verifies sufficient free disk space.
      - **Checksum**: Verifies integrity after download.

    Step format::

        {
            "type": "download",
            "label": "Download Trivy DB",
            "url": "https://...",
            "dest": "~/.cache/trivy/db.tar.gz",
            "size_bytes": 150000000,
            "checksum": "sha256:abc123...",
        }
    """
    import urllib.request

    url = step.get("url", "")
    if not url:
        return {"ok": False, "error": "No download URL specified"}

    dest = Path(step.get("dest", "/tmp/download")).expanduser()
    expected_size = step.get("size_bytes")
    checksum = step.get("checksum")

    # Disk space pre-check
    if expected_size:
        try:
            import shutil as sh
            disk_free = sh.disk_usage(str(dest.parent) if dest.parent.exists() else "/tmp").free
            if disk_free < expected_size * 1.2:  # 20% buffer
                return {
                    "ok": False,
                    "error": f"Not enough disk space. Need {_fmt_size(expected_size)}, "
                             f"have {_fmt_size(disk_free)}",
                }
        except OSError:
            pass  # Can't check — proceed anyway

    # Create dest directory
    dest.parent.mkdir(parents=True, exist_ok=True)

    # ── Resume support ──
    resume_offset = 0
    if dest.exists():
        resume_offset = dest.stat().st_size
        logger.info("Partial file found: %s (%s), attempting resume",
                     dest, _fmt_size(resume_offset))

    # Download
    try:
        headers = {"User-Agent": "devops-cp/1.0"}

        # ── Auth header for gated downloads ──
        auth_type = step.get("auth_type")  # "bearer", "basic", "header"
        auth_token = step.get("auth_token", "")
        auth_env_var = step.get("auth_env_var", "")

        if auth_type and not auth_token and auth_env_var:
            auth_token = os.environ.get(auth_env_var, "")

        if auth_type and auth_token:
            if auth_type == "bearer":
                headers["Authorization"] = f"Bearer {auth_token}"
            elif auth_type == "basic":
                headers["Authorization"] = f"Basic {auth_token}"
            elif auth_type == "header":
                # Custom header name, e.g. "X-API-Key"
                header_name = step.get("auth_header_name", "Authorization")
                headers[header_name] = auth_token

        if resume_offset > 0:
            headers["Range"] = f"bytes={resume_offset}-"

        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=60) as resp:
            # Check if server supports resume
            status = resp.getcode()
            if resume_offset > 0 and status == 206:
                # Partial content — resume
                mode = "ab"
                total = int(resp.headers.get("Content-Length", 0)) + resume_offset
                logger.info("Resuming download from %s", _fmt_size(resume_offset))
            else:
                # Full download (server doesn't support Range, or fresh start)
                mode = "wb"
                total = int(resp.headers.get("Content-Length", 0))
                resume_offset = 0

            with open(dest, mode) as f:
                downloaded = resume_offset
                last_progress = -1
                while True:
                    chunk = resp.read(8192)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)

                    # Progress tracking (log every 5%)
                    if total > 0:
                        pct = int(downloaded * 100 / total)
                        if pct >= last_progress + 5:
                            last_progress = pct
                            logger.info(
                                "Download progress: %d%% (%s / %s)",
                                pct, _fmt_size(downloaded), _fmt_size(total),
                            )

        # Verify checksum if provided
        if checksum:
            if not _verify_checksum(dest, checksum):
                dest.unlink(missing_ok=True)
                return {"ok": False, "error": "Checksum mismatch — download corrupted"}

        # Record download timestamp for freshness tracking
        stamp_dir = Path("~/.cache/devops-cp/data-stamps").expanduser()
        stamp_dir.mkdir(parents=True, exist_ok=True)
        step_id = step.get("data_pack_id", dest.stem)
        (stamp_dir / step_id).write_text(str(int(time.time())))

        return {
            "ok": True,
            "message": f"Downloaded {_fmt_size(downloaded)} to {dest}",
            "size_bytes": downloaded,
        }

    except Exception as e:
        dest.unlink(missing_ok=True)
        return {"ok": False, "error": f"Download failed: {e}"}


def _execute_service_step(
    step: dict,
    *,
    sudo_password: str = "",
) -> dict[str, Any]:
    """Manage a system service (start/stop/restart/enable/disable/status).

    Supports systemd, openrc, and initd. Automatically detects
    the init system and dispatches accordingly.

    Step format::

        {
            "type": "service",
            "action": "start",
            "service": "docker",
            "needs_sudo": True,
        }
    """
    action = step.get("action", "status")
    service = step.get("service", "")
    if not service:
        return {"ok": False, "error": "No service specified"}

    init_system = _detect_init_system()

    if init_system == "systemd":
        cmd_map = {
            "start":   ["systemctl", "start", service],
            "stop":    ["systemctl", "stop", service],
            "restart": ["systemctl", "restart", service],
            "enable":  ["systemctl", "enable", service],
            "disable": ["systemctl", "disable", service],
            "status":  ["systemctl", "is-active", service],
        }
    elif init_system == "openrc":
        cmd_map = {
            "start":   ["rc-service", service, "start"],
            "stop":    ["rc-service", service, "stop"],
            "restart": ["rc-service", service, "restart"],
            "enable":  ["rc-update", "add", service, "default"],
            "disable": ["rc-update", "del", service, "default"],
            "status":  ["rc-service", service, "status"],
        }
    elif init_system == "initd":
        cmd_map = {
            "start":   ["service", service, "start"],
            "stop":    ["service", service, "stop"],
            "restart": ["service", service, "restart"],
            "enable":  ["update-rc.d", service, "defaults"],
            "disable": ["update-rc.d", service, "remove"],
            "status":  ["service", service, "status"],
        }
    else:
        return {"ok": False, "error": f"No init system detected for service management"}

    cmd = cmd_map.get(action)
    if not cmd:
        return {"ok": False, "error": f"Unknown service action: {action}"}

    # Status check doesn't need sudo
    needs_sudo = action != "status"

    result = _run_subprocess(
        cmd,
        needs_sudo=needs_sudo,
        sudo_password=sudo_password,
        timeout=30,
    )

    # Enrich status result
    if action == "status":
        result["active"] = result.get("ok", False)
        result["ok"] = True  # the status check itself always "succeeds"

    return result


def _execute_config_step(
    step: dict,
    *,
    sudo_password: str = "",
) -> dict[str, Any]:
    """Write or modify a config file (write, append, ensure_line, template).

    Automatically creates a timestamped backup before any modification.

    Step format::

        {
            "type": "config",
            "action": "write",
            "path": "/etc/docker/daemon.json",
            "content": '{"features": {"buildkit": true}}',
            "needs_sudo": True,
            "backup": True,
        }

    The ``template`` action uses the full pipeline:
    validate inputs → render ``{var}`` placeholders → validate
    output format → write.
    """
    action = step.get("action", "write")
    path_str = step.get("path", "")
    if not path_str:
        return {"ok": False, "error": "No config path specified"}

    path = Path(path_str)
    backup = step.get("backup", True)

    # Backup existing file before modification
    if backup and path.exists():
        import time as _time
        ts = _time.strftime("%Y%m%d_%H%M%S")
        backup_path = f"{path}.bak.{ts}"
        bk_result = _run_subprocess(
            ["cp", "-p", str(path), backup_path],
            needs_sudo=step.get("needs_sudo", False),
            sudo_password=sudo_password,
            timeout=5,
        )
        if not bk_result["ok"]:
            logger.warning("Config backup failed for %s: %s", path, bk_result.get("error"))

    # ── Helper: apply mode/owner after write ─────────────────
    def _apply_file_attrs(
        target: str,
        step_data: dict,
        sp: str,
    ) -> None:
        """Apply chmod/chown if specified in step."""
        mode = step_data.get("mode")
        if mode:
            _run_subprocess(
                ["chmod", str(mode), target],
                needs_sudo=step_data.get("needs_sudo", False),
                sudo_password=sp,
                timeout=5,
            )
        owner = step_data.get("owner")
        if owner:
            _run_subprocess(
                ["chown", str(owner), target],
                needs_sudo=step_data.get("needs_sudo", False),
                sudo_password=sp,
                timeout=5,
            )

    if action == "write":
        content = step.get("content", "")
        # Write via tee (handles sudo correctly)
        if step.get("needs_sudo"):
            cmd = ["bash", "-c", f"echo '{content}' | sudo tee '{path_str}' > /dev/null"]
        else:
            cmd = ["bash", "-c", f"echo '{content}' > '{path_str}'"]
        result = _run_subprocess(
            cmd,
            needs_sudo=False,  # sudo is inside bash -c
            timeout=10,
        )
        if result["ok"]:
            _apply_file_attrs(path_str, step, sudo_password)
            result["message"] = f"Config written: {path_str}"
        return result

    elif action == "append":
        content = step.get("content", step.get("line", ""))
        cmd = ["bash", "-c", f"echo '{content}' >> '{path_str}'"]
        result = _run_subprocess(
            cmd,
            needs_sudo=step.get("needs_sudo", False),
            sudo_password=sudo_password,
            timeout=10,
        )
        if result["ok"]:
            _apply_file_attrs(path_str, step, sudo_password)
            result["message"] = f"Content appended to {path_str}"
        return result

    elif action == "ensure_line":
        line = step.get("line", step.get("content", ""))
        if not line:
            return {"ok": False, "error": "No line specified for ensure_line"}

        # Check if line already exists
        if path.exists():
            try:
                existing = path.read_text()
                if line in existing:
                    return {"ok": True, "message": "Line already present", "skipped": True}
            except PermissionError:
                # Try reading with sudo
                check = _run_subprocess(
                    ["grep", "-F", line, str(path)],
                    needs_sudo=step.get("needs_sudo", False),
                    sudo_password=sudo_password,
                    timeout=5,
                )
                if check["ok"]:
                    return {"ok": True, "message": "Line already present", "skipped": True}

        # Append the line
        cmd = ["bash", "-c", f"echo '{line}' >> '{path_str}'"]
        result = _run_subprocess(
            cmd,
            needs_sudo=step.get("needs_sudo", False),
            sudo_password=sudo_password,
            timeout=5,
        )
        if result["ok"]:
            _apply_file_attrs(path_str, step, sudo_password)
        return result

    elif action == "template":
        # Full template pipeline: validate → render → validate → write
        template_str = step.get("template", "")
        input_defs = step.get("inputs", [])
        input_values = step.get("input_values", {})
        fmt = step.get("format", "raw")

        # 1. Collect defaults for missing inputs
        for inp in input_defs:
            inp_id = inp.get("id", "")
            if inp_id and inp_id not in input_values:
                if "default" in inp:
                    input_values[inp_id] = inp["default"]

        # 2. Validate all inputs
        errors: list[str] = []
        for inp in input_defs:
            inp_id = inp.get("id", "")
            if inp_id in input_values:
                err = _validate_input(inp, input_values[inp_id])
                if err:
                    errors.append(f"{inp.get('label', inp_id)}: {err}")
        if errors:
            return {"ok": False, "error": f"Input validation failed: {'; '.join(errors)}"}

        # 3. Render template
        rendered = _render_template(template_str, input_values)

        # 3.5. Check for unresolved placeholders
        unresolved = _check_unsubstituted(rendered)
        if unresolved:
            return {
                "ok": False,
                "error": f"Unresolved template variables: {', '.join(f'{{{v}}}' for v in unresolved)}",
            }

        # 4. Validate output format
        fmt_err = _validate_output(rendered, fmt)
        if fmt_err:
            return {"ok": False, "error": f"Template output validation failed: {fmt_err}"}

        # 5. Write via the existing write path (preserves mode/owner)
        write_step = dict(step)
        write_step["action"] = "write"
        write_step["content"] = rendered
        return _execute_config_step(write_step, sudo_password=sudo_password)

    else:
        return {"ok": False, "error": f"Unknown config action: {action}"}


def _execute_github_release_step(
    step: dict,
    *,
    sudo_password: str = "",
) -> dict[str, Any]:
    """Execute a github_release step — download + install a binary from GitHub.

    Step format::

        {
            "type": "github_release",
            "label": "Install lazygit",
            "repo": "jesseduffield/lazygit",
            "asset_pattern": "lazygit_{version}_Linux_{arch}.tar.gz",
            "binary_name": "lazygit",
            "install_dir": "/usr/local/bin",
            "version": "latest",
            "checksum": "sha256:...",
        }

    Supports tar.gz, zip, and raw binary assets.

    Returns:
        ``{"ok": True, "version": "...", "path": "..."}``
    """
    import urllib.request
    import tarfile
    import zipfile

    repo = step.get("repo", "")
    if not repo:
        return {"ok": False, "error": "No GitHub repo specified"}

    version = step.get("version", "latest")
    asset_pattern = step.get("asset_pattern", "")
    binary_name = step.get("binary_name", "")

    # ── M1: install_dir fallback chain ──
    install_dir = step.get("install_dir", "")
    if not install_dir:
        # Try /usr/local/bin first; fall back to ~/.local/bin if not writable
        if os.access("/usr/local/bin", os.W_OK) or sudo_password:
            install_dir = "/usr/local/bin"
        else:
            install_dir = os.path.expanduser("~/.local/bin")
            os.makedirs(install_dir, exist_ok=True)
            logger.info("Using %s (no sudo, /usr/local/bin not writable)", install_dir)

    # Resolve the download URL
    resolved = _resolve_github_release_url(
        repo,
        asset_pattern=asset_pattern,
        version=version,
    )
    if not resolved.get("ok"):
        return resolved

    url = resolved["url"]
    asset_name = resolved.get("asset_name", "")
    actual_version = resolved.get("version", version)

    # Download to temp
    tmp_dir = Path(f"/tmp/gh_release_{repo.replace('/', '_')}")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_file = tmp_dir / asset_name

    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "devops-cp/1.0"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            with open(tmp_file, "wb") as f:
                while True:
                    chunk = resp.read(8192)
                    if not chunk:
                        break
                    f.write(chunk)
    except Exception as exc:
        return {"ok": False, "error": f"Download failed: {exc}"}

    # Checksum verify
    checksum = step.get("checksum", "")
    if checksum:
        if not _verify_checksum(tmp_file, checksum):
            return {
                "ok": False,
                "error": f"Checksum mismatch for {asset_name}",
            }

    # Extract or copy
    extract_dir = tmp_dir / "extracted"
    extract_dir.mkdir(exist_ok=True)

    if asset_name.endswith(".tar.gz") or asset_name.endswith(".tgz"):
        try:
            with tarfile.open(tmp_file, "r:gz") as tf:
                tf.extractall(extract_dir)
        except Exception as exc:
            return {"ok": False, "error": f"Extract failed: {exc}"}
    elif asset_name.endswith(".zip"):
        try:
            with zipfile.ZipFile(tmp_file, "r") as zf:
                zf.extractall(extract_dir)
        except Exception as exc:
            return {"ok": False, "error": f"Extract failed: {exc}"}
    else:
        # Raw binary — just copy
        import shutil as _sh
        _sh.copy2(tmp_file, extract_dir / (binary_name or asset_name))

    # Find the binary
    if binary_name:
        # Search for the binary in extracted files
        found = None
        for p in extract_dir.rglob(binary_name):
            if p.is_file():
                found = p
                break
        if not found:
            # Might be the direct file
            direct = extract_dir / binary_name
            if direct.is_file():
                found = direct

        if not found:
            available = [str(p.name) for p in extract_dir.rglob("*") if p.is_file()]
            return {
                "ok": False,
                "error": f"Binary '{binary_name}' not found in release archive",
                "available_files": available[:10],
            }
    else:
        # If no binary_name, pick the first executable
        found = None
        for p in extract_dir.rglob("*"):
            if p.is_file() and os.access(p, os.X_OK):
                found = p
                break
        if not found:
            return {"ok": False, "error": "No executable found in archive"}

    # Make executable
    os.chmod(found, 0o755)

    # Install to target dir
    target = Path(install_dir) / (binary_name or found.name)
    needs_sudo = step.get("needs_sudo", not os.access(install_dir, os.W_OK))

    if needs_sudo:
        result = _run_subprocess(
            ["cp", str(found), str(target)],
            needs_sudo=True,
            sudo_password=sudo_password,
            timeout=10,
        )
        if not result.get("ok"):
            return result
        # Make sure it's executable
        _run_subprocess(
            ["chmod", "+x", str(target)],
            needs_sudo=True,
            sudo_password=sudo_password,
            timeout=5,
        )
    else:
        import shutil as _sh
        _sh.copy2(str(found), str(target))
        os.chmod(target, 0o755)

    # Cleanup temp
    import shutil as _sh
    _sh.rmtree(tmp_dir, ignore_errors=True)

    return {
        "ok": True,
        "version": actual_version,
        "path": str(target),
        "asset": asset_name,
    }


def _execute_shell_config_step(
    step: dict,
) -> dict[str, Any]:
    """Execute a shell_config step — write PATH/env to shell profile.

    The step dict can have:
        - ``file``: Explicit profile path (overrides auto-detection)
        - ``line``: Explicit line to write
        - ``path_append``: List of dirs to add to PATH
        - ``env_vars``: Dict of env vars to export
        - ``shell_type``: Override detected shell type

    Writes are IDEMPOTENT — lines already present are skipped.

    Spec: domain-shells §Phase 4 shell_config.

    Returns:
        ``{"ok": True, "lines_added": N, ...}``
    """
    # Determine shell type
    shell_type = step.get("shell_type", "")
    if not shell_type:
        shell_env = os.environ.get("SHELL", "/bin/bash")
        shell_type = os.path.basename(shell_env)

    # Determine target file
    target_file = step.get("file", "")
    if not target_file:
        profile_info = _PROFILE_MAP.get(shell_type, _PROFILE_MAP["sh"])
        target_file = profile_info["rc_file"]

    target_path = os.path.expanduser(target_file)

    # Collect lines to write
    lines_to_add: list[str] = []

    # Explicit line
    if step.get("line"):
        lines_to_add.append(step["line"])

    # path_append entries
    for path_entry in step.get("path_append", []):
        lines_to_add.append(_shell_config_line(
            shell_type, path_entry=path_entry,
        ))

    # env_vars
    for var_name, var_value in step.get("env_vars", {}).items():
        lines_to_add.append(_shell_config_line(
            shell_type, env_var=(var_name, var_value),
        ))

    if not lines_to_add:
        return {"ok": True, "lines_added": 0, "note": "nothing to add"}

    # Read existing content (for idempotency check)
    existing_content = ""
    if os.path.isfile(target_path):
        try:
            with open(target_path) as f:
                existing_content = f.read()
        except OSError:
            pass

    # Filter out lines already present
    new_lines = [ln for ln in lines_to_add if ln.strip() and ln not in existing_content]

    if not new_lines:
        return {
            "ok": True,
            "lines_added": 0,
            "file": target_file,
            "note": "all lines already present",
        }

    # Backup before writing
    if os.path.isfile(target_path):
        import shutil as _shutil
        backup = f"{target_path}.backup.{int(time.time())}"
        try:
            _shutil.copy2(target_path, backup)
        except OSError:
            pass

    # Ensure parent directories exist
    os.makedirs(os.path.dirname(target_path), exist_ok=True)

    # Append lines
    try:
        with open(target_path, "a") as f:
            if existing_content and not existing_content.endswith("\n"):
                f.write("\n")
            f.write(f"\n# Added by devops-control-plane\n")
            for ln in new_lines:
                f.write(f"{ln}\n")
    except OSError as exc:
        return {"ok": False, "error": f"Failed to write {target_file}: {exc}"}

    return {
        "ok": True,
        "lines_added": len(new_lines),
        "file": target_file,
        "shell_type": shell_type,
        "lines": new_lines,
    }


def _execute_notification_step(step: dict) -> dict[str, Any]:
    """Handle a notification step (no-op with message pass-through).

    Notifications are informational. They always succeed.
    The frontend displays them to the user.
    """
    return {
        "ok": True,
        "message": step.get("message", ""),
        "severity": step.get("severity", "info"),
        "notification": True,
    }


def _execute_rollback(
    rollback_steps: list[dict],
    *,
    sudo_password: str = "",
) -> dict[str, Any]:
    """Execute rollback steps with best-effort error handling.

    Runs each rollback step in order. If a step fails, it is
    logged but does NOT stop the remainder of the rollback.

    Args:
        rollback_steps: List of rollback step dicts with
                        ``command``, ``needs_sudo``, ``description``.
        sudo_password: Optional sudo password.

    Returns:
        Summary dict with ``ok``, ``steps_run``, ``steps_failed``,
        ``errors``.
    """
    results: list[dict] = []
    errors: list[str] = []

    for rb_step in rollback_steps:
        cmd = rb_step.get("command", [])
        desc = rb_step.get("description", " ".join(cmd) if cmd else "unknown")
        logger.info("Rollback step: %s", desc)

        if not cmd:
            errors.append(f"No command for rollback step: {desc}")
            continue

        result = _run_subprocess(
            cmd,
            needs_sudo=rb_step.get("needs_sudo", False),
            sudo_password=sudo_password,
            timeout=rb_step.get("timeout", 30),
        )
        results.append({"description": desc, **result})
        if not result["ok"]:
            errors.append(f"Rollback step failed: {desc} — {result.get('error', '')}")
            logger.warning("Rollback step failed: %s — %s", desc, result.get("error"))

    return {
        "ok": len(errors) == 0,
        "steps_run": len(results),
        "steps_failed": len(errors),
        "errors": errors,
        "results": results,
    }
