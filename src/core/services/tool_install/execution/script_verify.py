"""
L4 Execution — Curl script integrity verification.

M2: Downloads scripts to tempfiles and verifies SHA256 checksums
before execution, replacing the unsafe `curl | bash` pattern.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Regex to detect curl-pipe-bash patterns in commands
_CURL_PIPE_RE = re.compile(
    r"""curl\s+[^|]+\|\s*(?:ba)?sh""",
    re.IGNORECASE,
)

# Regex to extract URL from curl command
_CURL_URL_RE = re.compile(
    r"""curl\s+(?:(?:--proto|--tlsv|--location|-[fsSLo])\s*'?[^']*'?\s+)*"""
    r"""(?:-[fsSLo]\s+)?"""
    r"""['"]?(https?://[^\s'"]+)['"]?""",
    re.IGNORECASE,
)


def is_curl_pipe_command(command: list[str]) -> bool:
    """Check if a command list represents a curl-pipe-bash pattern.

    Examples that match::

        ["bash", "-c", "curl -fsSL https://... | bash"]
        ["bash", "-c", "curl ... | sh -s -- -y"]

    Returns:
        True if the command pipes curl output to a shell.
    """
    if len(command) < 3:
        return False
    if command[0] not in ("bash", "sh"):
        return False
    if command[1] != "-c":
        return False
    return bool(_CURL_PIPE_RE.search(command[2]))


def extract_script_url(command: list[str]) -> str | None:
    """Extract the download URL from a curl-pipe-bash command.

    Args:
        command: Command list like ``["bash", "-c", "curl ... | bash"]``.

    Returns:
        The URL being curled, or None if not extractable.
    """
    if len(command) < 3:
        return None
    script = command[2]
    # Split at the pipe — we want the curl part
    pipe_idx = script.find("|")
    if pipe_idx < 0:
        return None
    curl_part = script[:pipe_idx].strip()

    m = _CURL_URL_RE.search(curl_part)
    if m:
        return m.group(1)

    # Fallback: find anything that looks like a URL
    url_match = re.search(r"https?://\S+", curl_part)
    return url_match.group(0).rstrip("'\"") if url_match else None


def download_and_verify_script(
    url: str,
    expected_sha256: str | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    """Download a script to a tempfile and optionally verify its SHA256.

    Args:
        url: URL to download.
        expected_sha256: Expected SHA256 hex digest. If provided and
            the hash doesn't match, returns ``ok: False``.
        timeout: Download timeout in seconds.

    Returns::

        {
            "ok": True,
            "path": "/tmp/xxx.sh",
            "sha256": "abc123...",
            "size_bytes": 1234,
        }
        or
        {
            "ok": False,
            "error": "SHA256 mismatch: expected abc, got def",
        }
    """
    try:
        result = subprocess.run(
            ["curl", "-fsSL", "--max-time", str(timeout), url],
            capture_output=True, timeout=timeout + 5,
        )
        if result.returncode != 0:
            return {
                "ok": False,
                "error": f"Download failed (exit {result.returncode}): "
                         f"{result.stderr.decode('utf-8', errors='replace')[:200]}",
            }

        content = result.stdout
        actual_sha256 = hashlib.sha256(content).hexdigest()

        # Verify checksum if provided
        if expected_sha256:
            # Normalize — strip "sha256:" prefix if present
            expected = expected_sha256.removeprefix("sha256:").lower()
            if actual_sha256 != expected:
                return {
                    "ok": False,
                    "error": (
                        f"SHA256 mismatch for {url}\n"
                        f"Expected: {expected}\n"
                        f"Got:      {actual_sha256}\n"
                        f"The script may have been tampered with."
                    ),
                    "expected_sha256": expected,
                    "actual_sha256": actual_sha256,
                }

        # Write to tempfile
        fd, path = tempfile.mkstemp(suffix=".sh", prefix="devops_cp_script_")
        try:
            os.write(fd, content)
        finally:
            os.close(fd)
        os.chmod(path, 0o700)

        return {
            "ok": True,
            "path": path,
            "sha256": actual_sha256,
            "size_bytes": len(content),
        }

    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"Download timed out after {timeout}s"}
    except Exception as exc:
        return {"ok": False, "error": f"Download error: {exc}"}


def rewrite_curl_pipe_to_safe(
    command: list[str],
    script_path: str,
) -> list[str]:
    """Rewrite a curl-pipe-bash command to execute from a verified file.

    Takes the original command like::

        ["bash", "-c", "curl ... | sh -s -- -y"]

    And the path to the verified script, and produces::

        ["bash", "/tmp/xxx.sh", "-s", "--", "-y"]

    Preserves any arguments passed to the shell after the pipe.

    Args:
        command: Original curl-pipe-bash command.
        script_path: Path to the verified script file.

    Returns:
        Rewritten command that executes the local file.
    """
    script = command[2] if len(command) >= 3 else ""
    pipe_idx = script.find("|")
    if pipe_idx < 0:
        # No pipe found — just run the script directly
        return ["bash", script_path]

    # Get the shell part after the pipe
    shell_part = script[pipe_idx + 1:].strip()

    # Parse arguments from the shell invocation
    # e.g. "sh -s -- -y"  → ["-s", "--", "-y"]
    # e.g. "bash"         → []
    shell_tokens = shell_part.split()
    shell_args = []
    if len(shell_tokens) > 1:
        # Skip the shell binary name (sh/bash)
        shell_args = shell_tokens[1:]

    if shell_args:
        return ["bash", script_path] + shell_args
    else:
        return ["bash", script_path]


def cleanup_script(path: str) -> None:
    """Remove a temporary script file."""
    try:
        os.unlink(path)
    except OSError:
        pass
