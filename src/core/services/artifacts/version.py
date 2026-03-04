"""
Version resolution for artifact publishing.

Resolution order (stack-aware):
  1. pyproject.toml → version (Python)
  2. setup.py → version (Python legacy)
  3. package.json → version (Node/TypeScript)
  4. Cargo.toml → version (Rust)
  5. mix.exs → version (Elixir)
  6. *.gemspec → version (Ruby)
  7. pom.xml → version (Java Maven)
  8. build.gradle / build.gradle.kts → version (Java Gradle)
  9. *.csproj → Version (C# / .NET)
  10. git describe --tags
  11. git rev-parse --short HEAD
  12. Fallback: 0.0.0-dev
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


def resolve_version(project_root: Path) -> tuple[str, str]:
    """Resolve the current project version.

    Returns:
        (version, source) — e.g. ("0.1.0", "pyproject.toml")

    Checks ALL stack manifest files, not just Python.
    """
    # 1. pyproject.toml (Python)
    pyproject = project_root / "pyproject.toml"
    if pyproject.exists():
        try:
            content = pyproject.read_text()
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith("version") and "=" in stripped:
                    val = stripped.split("=", 1)[1].strip().strip("\"'")
                    if val and val != "0.0.0":
                        return (val, "pyproject.toml")
        except OSError:
            pass

    # 2. setup.py (Python legacy)
    setup_py = project_root / "setup.py"
    if setup_py.exists():
        try:
            content = setup_py.read_text()
            m = re.search(r'version\s*=\s*["\'](.[^"\']+)["\']', content)
            if m:
                return (m.group(1), "setup.py")
        except OSError:
            pass

    # 3. package.json (Node / TypeScript)
    package_json = project_root / "package.json"
    if package_json.exists():
        try:
            import json as _json
            data = _json.loads(package_json.read_text())
            ver = data.get("version", "")
            if ver and ver != "0.0.0":
                return (ver, "package.json")
        except (OSError, ValueError):
            pass

    # 4. Cargo.toml (Rust)
    cargo_toml = project_root / "Cargo.toml"
    if cargo_toml.exists():
        try:
            content = cargo_toml.read_text()
            in_package = False
            for line in content.splitlines():
                stripped = line.strip()
                if stripped == "[package]":
                    in_package = True
                elif stripped.startswith("[") and in_package:
                    break
                elif in_package and stripped.startswith("version") and "=" in stripped:
                    val = stripped.split("=", 1)[1].strip().strip("\"'")
                    if val and val != "0.0.0":
                        return (val, "Cargo.toml")
        except OSError:
            pass

    # 5. mix.exs (Elixir)
    mix_exs = project_root / "mix.exs"
    if mix_exs.exists():
        try:
            content = mix_exs.read_text()
            m = re.search(r'version:\s*"([^"]+)"', content)
            if m:
                return (m.group(1), "mix.exs")
        except OSError:
            pass

    # 6. *.gemspec (Ruby)
    gemspecs = list(project_root.glob("*.gemspec"))
    if gemspecs:
        try:
            content = gemspecs[0].read_text()
            m = re.search(r'\.version\s*=\s*["\']([^"\']+)["\']', content)
            if m:
                return (m.group(1), gemspecs[0].name)
        except OSError:
            pass

    # 7. pom.xml (Java Maven)
    pom = project_root / "pom.xml"
    if pom.exists():
        try:
            content = pom.read_text()
            # Match top-level <version> (not inside <parent> or <dependency>)
            m = re.search(r'<artifactId>[^<]+</artifactId>\s*<version>([^<]+)</version>', content)
            if m:
                return (m.group(1), "pom.xml")
        except OSError:
            pass

    # 8. build.gradle / build.gradle.kts (Java Gradle)
    for gradle_file in ["build.gradle", "build.gradle.kts"]:
        gradle = project_root / gradle_file
        if gradle.exists():
            try:
                content = gradle.read_text()
                m = re.search(r'version\s*=\s*["\']([^"\']+)["\']', content)
                if m:
                    return (m.group(1), gradle_file)
            except OSError:
                pass

    # 9. *.csproj (.NET / C#)
    csprojs = list(project_root.glob("*.csproj"))
    if csprojs:
        try:
            content = csprojs[0].read_text()
            m = re.search(r'<Version>([^<]+)</Version>', content)
            if m:
                return (m.group(1), csprojs[0].name)
        except OSError:
            pass

    # 10. Git tag
    try:
        r = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0"],
            cwd=str(project_root),
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            tag = r.stdout.strip()
            version = tag.lstrip("v")
            return (version, f"git tag ({tag})")
    except (OSError, subprocess.TimeoutExpired):
        pass

    # 11. Git short hash
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(project_root),
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            return (f"0.0.0-dev+{r.stdout.strip()}", "git hash")
    except (OSError, subprocess.TimeoutExpired):
        pass

    # 12. Fallback
    return ("0.0.0-dev", "fallback")


def bump_version(current: str, bump_type: str) -> str:
    """Bump a semver version string.

    Args:
        current: Current version (e.g. "0.1.0")
        bump_type: "patch", "minor", or "major"

    Returns:
        Bumped version string.
    """
    # Strip pre-release suffix for bumping
    base = current.split("-")[0].split("+")[0]
    parts = base.split(".")
    if len(parts) < 3:
        parts.extend(["0"] * (3 - len(parts)))

    try:
        major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
    except (ValueError, IndexError):
        return current

    if bump_type == "major":
        return f"{major + 1}.0.0"
    elif bump_type == "minor":
        return f"{major}.{minor + 1}.0"
    elif bump_type == "patch":
        return f"{major}.{minor}.{patch + 1}"
    return current


def get_last_tag(project_root: Path) -> str | None:
    """Get the most recent git tag, or None."""
    try:
        r = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0"],
            cwd=str(project_root),
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None
