"""
Artifact discovery — auto-detect buildable targets from project structure.

Scans the project for:
  - Makefile with known targets (install, build, check, clean, dist)
  - pyproject.toml / setup.py → pip-package candidate
  - Dockerfile → container candidate
  - scripts/ with release/bundle scripts → bundle candidate
  - manage.sh → local entry point

Each detected candidate includes:
  - name: suggested target name
  - kind: local | package | bundle | container
  - builder: makefile | pip | script | docker
  - confidence: high | medium | low
  - description: what it does
  - detected_from: what file/pattern triggered detection
"""

from __future__ import annotations

import re
from pathlib import Path


def detect_artifact_targets(project_root: Path) -> list[dict]:
    """Scan project for buildable artifact targets.

    Returns a list of candidate dicts, each with:
      name, kind, builder, build_target, description,
      detected_from, confidence
    """
    candidates = []

    # ── Makefile targets ─────────────────────────────────────────
    makefile = project_root / "Makefile"
    if makefile.exists():
        candidates.extend(_detect_makefile_targets(makefile))

    # ── pyproject.toml / setup.py → pip package ──────────────────
    pyproject = project_root / "pyproject.toml"
    setup_py = project_root / "setup.py"
    if pyproject.exists() or setup_py.exists():
        source = "pyproject.toml" if pyproject.exists() else "setup.py"
        # Check if it has a build-system
        has_build_system = False
        if pyproject.exists():
            try:
                content = pyproject.read_text()
                has_build_system = "[build-system]" in content
            except OSError:
                pass

        if has_build_system or setup_py.exists():
            candidates.append({
                "name": "pip-package",
                "kind": "package",
                "builder": "pip",
                "build_target": "",
                "build_cmd": "python -m build",
                "description": f"Build pip wheel/sdist from {source}",
                "detected_from": source,
                "confidence": "high" if has_build_system else "medium",
                "output_dir": "dist/",
            })

    # ── Dockerfile → container ───────────────────────────────────
    dockerfile = project_root / "Dockerfile"
    if dockerfile.exists():
        # Try to extract the image name from the Dockerfile or project
        project_name = project_root.name
        candidates.append({
            "name": "container",
            "kind": "container",
            "builder": "docker",
            "build_target": "",
            "build_cmd": f"docker build -t {project_name} .",
            "description": "Build Docker container image",
            "detected_from": "Dockerfile",
            "confidence": "high",
            "output_dir": "",
        })

    # ── Release/bundle scripts ───────────────────────────────────
    scripts_dir = project_root / "scripts"
    if scripts_dir.is_dir():
        for script in scripts_dir.iterdir():
            if not script.is_file():
                continue
            if not script.name.endswith(".sh"):
                continue

            name_lower = script.name.lower()
            # Detect release/bundle/package scripts
            if any(kw in name_lower for kw in [
                "release", "bundle", "package", "dist", "deploy", "publish"
            ]):
                desc = _extract_script_description(script)
                candidates.append({
                    "name": script.stem,
                    "kind": "bundle",
                    "builder": "script",
                    "build_target": "",
                    "build_cmd": f"./scripts/{script.name}",
                    "description": desc or f"Run {script.name}",
                    "detected_from": f"scripts/{script.name}",
                    "confidence": "medium",
                    "output_dir": "dist/",
                })

    return candidates


def _detect_makefile_targets(makefile: Path) -> list[dict]:
    """Parse Makefile and return artifact candidates for known targets."""
    try:
        content = makefile.read_text()
    except OSError:
        return []

    targets = {}
    for line in content.splitlines():
        # Match: target: [deps] ## description
        m = re.match(r'^([a-zA-Z_-]+):\s*(.*?)\s*(?:##\s*(.*))?$', line)
        if m:
            name = m.group(1)
            deps = m.group(2).strip()
            desc = (m.group(3) or "").strip()
            if not name.startswith("."):
                targets[name] = {"deps": deps, "description": desc}

    candidates = []

    # install → local-install
    if "install" in targets:
        candidates.append({
            "name": "local-install",
            "kind": "local",
            "builder": "makefile",
            "build_target": "install",
            "build_cmd": "",
            "description": targets["install"]["description"]
                or "Install package locally",
            "detected_from": "Makefile:install",
            "confidence": "high",
            "output_dir": "",
        })

    # check → quality-check
    if "check" in targets:
        candidates.append({
            "name": "quality-check",
            "kind": "local",
            "builder": "makefile",
            "build_target": "check",
            "build_cmd": "",
            "description": targets["check"]["description"]
                or "Run all quality checks",
            "detected_from": "Makefile:check",
            "confidence": "high",
            "output_dir": "",
        })

    # test → test
    if "test" in targets and "check" not in targets:
        # Only suggest standalone test if check doesn't exist
        candidates.append({
            "name": "test",
            "kind": "local",
            "builder": "makefile",
            "build_target": "test",
            "build_cmd": "",
            "description": targets["test"]["description"]
                or "Run tests",
            "detected_from": "Makefile:test",
            "confidence": "medium",
            "output_dir": "",
        })

    # clean → clean
    if "clean" in targets:
        candidates.append({
            "name": "clean",
            "kind": "local",
            "builder": "makefile",
            "build_target": "clean",
            "build_cmd": "",
            "description": targets["clean"]["description"]
                or "Clean build artifacts",
            "detected_from": "Makefile:clean",
            "confidence": "high",
            "output_dir": "",
        })

    return candidates


def _extract_script_description(script: Path) -> str:
    """Extract description from script header comments."""
    try:
        lines = script.read_text().splitlines()[:10]
        for line in lines:
            # Skip shebang and empty lines
            if line.startswith("#!") or not line.strip():
                continue
            # Take the first comment line as description
            if line.startswith("#"):
                desc = line.lstrip("# ").strip()
                if desc:
                    return desc
    except OSError:
        pass
    return ""
