"""
Package registry API clients — query version metadata from public registries.

Each function queries a single registry and returns structured metadata.
All queries use urllib (no external deps), 10s timeout, and graceful failure.

Registries:
  - npm (npmjs.org) — engines.node field
  - crates.io — rust_version (MSRV)
  - rubygems.org — required_ruby_version
  - packagist.org — require.php
  - hex.pm — elixir version requirements

Caching: results are cached in .state/registry_cache/ with 1-hour TTL
to avoid hammering APIs on repeated scans.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

_TIMEOUT = 10  # seconds per HTTP request
_CACHE_TTL = 3600  # 1 hour
_USER_AGENT = "devops-control-plane/1.0 (module-upgrade-checker)"


# ══════════════════════════════════════════════════════════════════
# NPM (Node.js)
# ══════════════════════════════════════════════════════════════════


def query_npm(package: str) -> dict | None:
    """Query npm registry for a package's engine requirements.

    Args:
        package: Package name (e.g. "express", "@scope/pkg").

    Returns:
        {name, version, engines_node, requires} or None on failure.
        engines_node is the engines.node constraint (e.g. ">=14.0.0").
    """
    # Handle scoped packages: @scope/pkg → @scope%2fpkg
    url_pkg = urllib.request.quote(package, safe="@")
    url = f"https://registry.npmjs.org/{url_pkg}/latest"

    data = _cached_get(url, f"npm_{package}")
    if not data:
        return None

    return {
        "name": data.get("name", package),
        "version": data.get("version", ""),
        "engines_node": (data.get("engines") or {}).get("node", ""),
    }


def query_npm_versions(package: str) -> list[dict]:
    """Query npm for all versions of a package with engine info.

    Returns list of {version, engines_node} sorted newest-first.
    """
    url_pkg = urllib.request.quote(package, safe="@")
    url = f"https://registry.npmjs.org/{url_pkg}"

    data = _cached_get(url, f"npm_all_{package}")
    if not data:
        return []

    versions_data = data.get("versions", {})
    results = []

    for ver, info in versions_data.items():
        # Skip pre-releases
        if any(c in ver for c in ("-alpha", "-beta", "-rc", "-dev", "-next", "-canary")):
            continue
        engines_node = (info.get("engines") or {}).get("node", "")
        if engines_node:
            results.append({"version": ver, "engines_node": engines_node})

    results.sort(
        key=lambda r: [int(x) for x in r["version"].split(".")[:3] if x.isdigit()],
        reverse=True,
    )
    return results


# ══════════════════════════════════════════════════════════════════
# CRATES.IO (Rust)
# ══════════════════════════════════════════════════════════════════


def query_crates(crate: str) -> dict | None:
    """Query crates.io for a crate's MSRV (rust_version).

    Args:
        crate: Crate name (e.g. "serde", "tokio").

    Returns:
        {name, version, rust_version} or None on failure.
    """
    url = f"https://crates.io/api/v1/crates/{crate}"

    data = _cached_get(url, f"crates_{crate}")
    if not data:
        return None

    crate_data = data.get("crate", {})
    # rust_version is on the latest version, not the crate root
    versions = data.get("versions", [])
    rust_version = ""
    latest_version = crate_data.get("newest_version", "")

    for v in versions:
        if v.get("num") == latest_version:
            rust_version = v.get("rust_version") or ""
            break

    return {
        "name": crate_data.get("name", crate),
        "version": latest_version,
        "rust_version": rust_version,
    }


def query_crates_versions(crate: str) -> list[dict]:
    """Query crates.io for all versions with MSRV info.

    Returns list of {version, rust_version} sorted newest-first.
    """
    url = f"https://crates.io/api/v1/crates/{crate}/versions"

    data = _cached_get(url, f"crates_all_{crate}")
    if not data:
        return []

    results = []
    for v in data.get("versions", []):
        ver = v.get("num", "")
        rv = v.get("rust_version") or ""
        if ver and rv and not v.get("yanked"):
            # Skip pre-releases
            if any(c in ver for c in ("-alpha", "-beta", "-rc", "-dev")):
                continue
            results.append({"version": ver, "rust_version": rv})

    results.sort(
        key=lambda r: [int(x) for x in r["version"].split(".")[:3] if x.isdigit()],
        reverse=True,
    )
    return results


# ══════════════════════════════════════════════════════════════════
# RUBYGEMS (Ruby)
# ══════════════════════════════════════════════════════════════════


def query_rubygems(gem: str) -> dict | None:
    """Query rubygems.org for a gem's required_ruby_version.

    Args:
        gem: Gem name (e.g. "rails", "sinatra").

    Returns:
        {name, version, required_ruby_version} or None on failure.
    """
    url = f"https://rubygems.org/api/v1/gems/{gem}.json"

    data = _cached_get(url, f"rubygems_{gem}")
    if not data:
        return None

    return {
        "name": data.get("name", gem),
        "version": data.get("version", ""),
        "required_ruby_version": data.get("required_ruby_version", ""),
    }


def query_rubygems_versions(gem: str) -> list[dict]:
    """Query rubygems.org for all versions with ruby version info.

    Returns list of {version, required_ruby_version} sorted newest-first.
    """
    url = f"https://rubygems.org/api/v1/versions/{gem}.json"

    data = _cached_get(url, f"rubygems_all_{gem}")
    if not data or not isinstance(data, list):
        return []

    results = []
    for v in data:
        ver = v.get("number", "")
        if not ver or v.get("prerelease"):
            continue
        # rubygems versions API doesn't include required_ruby_version directly
        # We'd need to query each version individually — too expensive
        # Just return versions for now, let the checker use the latest info
        results.append({"version": ver})

    results.sort(
        key=lambda r: [int(x) for x in r["version"].split(".")[:3] if x.isdigit()],
        reverse=True,
    )
    return results[:20]  # cap at 20


# ══════════════════════════════════════════════════════════════════
# PACKAGIST (PHP)
# ══════════════════════════════════════════════════════════════════


def query_packagist(package: str) -> dict | None:
    """Query packagist.org for a package's PHP version requirement.

    Args:
        package: Package name as vendor/pkg (e.g. "laravel/framework").

    Returns:
        {name, version, require_php} or None on failure.
    """
    url = f"https://repo.packagist.org/p2/{package}.json"

    data = _cached_get(url, f"packagist_{package.replace('/', '_')}")
    if not data:
        return None

    packages = data.get("packages", {}).get(package, [])
    if not packages:
        return None

    # First entry is latest version
    latest = packages[0] if packages else {}
    require_php = (latest.get("require") or {}).get("php", "")

    return {
        "name": latest.get("name", package),
        "version": latest.get("version", ""),
        "require_php": require_php,
    }


def query_packagist_versions(package: str) -> list[dict]:
    """Query packagist for all versions with PHP requirement.

    Returns list of {version, require_php} sorted newest-first.
    """
    url = f"https://repo.packagist.org/p2/{package}.json"

    data = _cached_get(url, f"packagist_all_{package.replace('/', '_')}")
    if not data:
        return []

    packages = data.get("packages", {}).get(package, [])
    results = []

    for p in packages:
        ver = p.get("version", "")
        if not ver or ver.startswith("dev-"):
            continue
        req_php = (p.get("require") or {}).get("php", "")
        if req_php:
            results.append({"version": ver, "require_php": req_php})

    # Already sorted newest-first from packagist
    return results[:20]


# ══════════════════════════════════════════════════════════════════
# HEX.PM (Elixir)
# ══════════════════════════════════════════════════════════════════


def query_hex(package: str) -> dict | None:
    """Query hex.pm for a package's elixir version requirement.

    Args:
        package: Package name (e.g. "phoenix", "ecto").

    Returns:
        {name, version, elixir_requirement} or None on failure.
    """
    url = f"https://hex.pm/api/packages/{package}"

    data = _cached_get(url, f"hex_{package}")
    if not data:
        return None

    releases = data.get("releases", [])
    if not releases:
        return None

    latest = releases[0]  # sorted newest-first by hex.pm
    # Elixir requirement is in the release's requirements
    elixir_req = ""
    for req in latest.get("requirements", {}).values():
        if req.get("app") == "elixir":
            elixir_req = req.get("requirement", "")
            break

    # If not in requirements, check meta
    if not elixir_req:
        meta = data.get("meta", {})
        elixir_req = (meta.get("elixir") or "")

    return {
        "name": data.get("name", package),
        "version": latest.get("version", ""),
        "elixir_requirement": elixir_req,
    }


# ══════════════════════════════════════════════════════════════════
# CACHING — avoids hammering registries on repeated scans
# ══════════════════════════════════════════════════════════════════


def _cached_get(url: str, cache_key: str) -> dict | list | None:
    """HTTP GET with file-based caching.

    Caches responses in .state/registry_cache/ for _CACHE_TTL seconds.
    Returns parsed JSON (dict or list) or None on failure.
    """
    # Try cache first
    cache_dir = Path(".state/registry_cache")
    safe_key = hashlib.md5(cache_key.encode()).hexdigest()
    cache_file = cache_dir / f"{safe_key}.json"

    if cache_file.is_file():
        try:
            stat = cache_file.stat()
            age = time.time() - stat.st_mtime
            if age < _CACHE_TTL:
                return json.loads(cache_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass

    # Fetch from registry
    try:
        req = urllib.request.Request(url, headers={
            "Accept": "application/json",
            "User-Agent": _USER_AGENT,
        })
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8")
            data = json.loads(raw)
    except Exception as exc:
        logger.debug("Registry query failed: %s → %s", url, exc)
        return None

    # Cache the result
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        pass  # caching is best-effort

    return data
