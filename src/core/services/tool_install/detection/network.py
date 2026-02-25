"""
L3 Detection — Network and registry probing.

Read-only network checks: registry reachability, proxy detection,
Alpine community repo status.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


# ── L6: Registry reachability ─────────────────────────────

_REGISTRY_ENDPOINTS: dict[str, str] = {
    "pypi": "https://pypi.org/simple/",
    "npm": "https://registry.npmjs.org/",
    "crates": "https://index.crates.io/",
    "github": "https://api.github.com/",
    "dockerhub": "https://registry-1.docker.io/v2/",
}


def check_registry_reachable(
    registry: str,
    timeout: int = 5,
) -> dict:
    """Probe a language PM registry for reachability.

    Args:
        registry: Registry key (pypi, npm, crates, github, dockerhub)
            or a full URL.
        timeout: HTTP timeout in seconds.

    Returns::

        {"reachable": True, "url": "https://...", "latency_ms": 42}
        or
        {"reachable": False, "url": "https://...", "error": "timeout"}
    """
    import urllib.request
    import time

    url = _REGISTRY_ENDPOINTS.get(registry, registry)
    start = time.monotonic()

    try:
        req = urllib.request.Request(
            url,
            method="HEAD",
            headers={"User-Agent": "devops-cp/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            elapsed = int((time.monotonic() - start) * 1000)
            return {
                "reachable": True,
                "url": url,
                "status": resp.getcode(),
                "latency_ms": elapsed,
            }
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        return {
            "reachable": False,
            "url": url,
            "error": str(exc)[:200],
            "latency_ms": elapsed,
        }


def check_all_registries(
    timeout: int = 5,
) -> dict[str, dict]:
    """Probe all known registries for reachability.

    Returns a dict of registry_name → reachability result.
    """
    results = {}
    for name in _REGISTRY_ENDPOINTS:
        results[name] = check_registry_reachable(name, timeout=timeout)
    return results


# ── L7: Alpine community repo ────────────────────────────

def check_alpine_community_repo() -> dict:
    """Detect Alpine community repository status.

    Checks /etc/apk/repositories for commented-out community repo
    lines. This matters in Alpine containers where community packages
    (like python3, build-base) may be unavailable.

    Returns::

        {"is_alpine": True, "community_enabled": False,
         "repo_line": "#http://...", "fix_hint": "..."}
    """
    repos_path = Path("/etc/apk/repositories")
    if not repos_path.exists():
        return {"is_alpine": False}

    try:
        content = repos_path.read_text()
    except (OSError, PermissionError):
        return {"is_alpine": True, "community_enabled": None, "error": "can't read"}

    lines = content.splitlines()
    community_active = False
    community_commented = None

    for line in lines:
        stripped = line.strip()
        if "/community" in stripped:
            if stripped.startswith("#"):
                community_commented = stripped
            else:
                community_active = True

    result: dict = {
        "is_alpine": True,
        "community_enabled": community_active,
    }

    if not community_active and community_commented:
        result["commented_line"] = community_commented
        result["fix_hint"] = (
            "Uncomment the community repo line in /etc/apk/repositories, "
            "then run 'apk update'."
        )

    return result


# ── L8: Proxy / corporate environment detection ──────────

def detect_proxy() -> dict:
    """Detect HTTP/HTTPS proxy configuration.

    Checks environment variables and common proxy config locations.

    Returns::

        {"has_proxy": True, "http_proxy": "http://...",
         "https_proxy": "http://...", "no_proxy": "localhost,..."}
    """
    http_proxy = os.environ.get("http_proxy") or os.environ.get("HTTP_PROXY", "")
    https_proxy = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY", "")
    no_proxy = os.environ.get("no_proxy") or os.environ.get("NO_PROXY", "")

    has_proxy = bool(http_proxy or https_proxy)

    result: dict = {
        "has_proxy": has_proxy,
    }

    if http_proxy:
        result["http_proxy"] = http_proxy
    if https_proxy:
        result["https_proxy"] = https_proxy
    if no_proxy:
        result["no_proxy"] = no_proxy

    # Check for corporate certificate bundles
    cert_file = os.environ.get("REQUESTS_CA_BUNDLE") or os.environ.get("SSL_CERT_FILE", "")
    if cert_file:
        result["custom_ca_bundle"] = cert_file

    return result
