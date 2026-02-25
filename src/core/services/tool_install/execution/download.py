"""
L4 Execution — Download and checksum verification.

File download support and integrity checking.
"""

from __future__ import annotations

import hashlib
import json
import logging
import platform
import re
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def _verify_checksum(path: Path, expected: str) -> bool:
    """Verify file checksum.  Format: ``algo:hex``.

    Supports sha256, sha1, md5.

    Args:
        path: Path to the downloaded file.
        expected: Checksum string like ``sha256:abc123...``.

    Returns:
        True if the file's computed digest matches ``expected``.
    """
    import hashlib

    algo, expected_hash = expected.split(":", 1)
    h = hashlib.new(algo)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest() == expected_hash


def _resolve_github_release_url(
    repo: str,
    *,
    asset_pattern: str = "",
    version: str = "latest",
    timeout: int = 15,
) -> dict[str, Any]:
    """Resolve a GitHub release URL for binary download.

    Fetches the release metadata from GitHub API and finds the
    matching asset based on the ``asset_pattern``.

    Args:
        repo: GitHub repo in ``owner/repo`` format.
        asset_pattern: Glob or substring to match asset filename.
            Supports ``{arch}`` and ``{os}`` placeholders, e.g.
            ``"tool-{arch}-{os}.tar.gz"``.
        version: Version tag to fetch, or ``"latest"``.
        timeout: HTTP request timeout in seconds.

    Returns:
        ``{"ok": True, "url": "...", "version": "...", "size_bytes": N}``
        or error dict.
    """
    import urllib.request
    import json as _json

    # Build API URL
    if version == "latest":
        api_url = f"https://api.github.com/repos/{repo}/releases/latest"
    else:
        tag = version if version.startswith("v") else f"v{version}"
        api_url = f"https://api.github.com/repos/{repo}/releases/tags/{tag}"

    try:
        req = urllib.request.Request(
            api_url,
            headers={
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "devops-cp/1.0",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = _json.loads(resp.read())
    except Exception as exc:
        return {"ok": False, "error": f"Failed to fetch release: {exc}"}

    release_tag = data.get("tag_name", "")
    assets = data.get("assets", [])

    if not assets:
        return {"ok": False, "error": f"No assets found for {repo} {release_tag}"}

    # Resolve arch/os in pattern
    machine = platform.machine().lower()
    arch = _IARCH_MAP.get(machine, machine)
    os_name = platform.system().lower()

    resolved_pattern = asset_pattern
    if resolved_pattern:
        resolved_pattern = resolved_pattern.replace("{arch}", arch)
        resolved_pattern = resolved_pattern.replace("{os}", os_name)

    # Find matching asset
    matched = None
    for asset in assets:
        name = asset.get("name", "")
        if resolved_pattern:
            if resolved_pattern in name:
                matched = asset
                break
        else:
            # Auto-match by arch + OS in filename
            name_lower = name.lower()
            if arch in name_lower and os_name in name_lower:
                matched = asset
                break

    if not matched:
        available = [a["name"] for a in assets[:10]]
        return {
            "ok": False,
            "error": f"No asset matching '{resolved_pattern}' in {repo} {release_tag}",
            "available_assets": available,
        }

    return {
        "ok": True,
        "url": matched["browser_download_url"],
        "version": release_tag.lstrip("v"),
        "size_bytes": matched.get("size", 0),
        "asset_name": matched["name"],
    }
