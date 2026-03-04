"""
Artifact discovery — intelligent detection of buildable targets.

Scans the project for:
  - Makefile with known targets (install, build, check, clean, dist)
  - pyproject.toml / setup.py → pip-package candidate
  - Dockerfile → container candidate
  - scripts/ with release/bundle scripts → bundle candidate

Intelligence layer:
  - Operability analysis per candidate (full / partial / none)
  - Remediation proposals (e.g. add venv prefix to bare pip)
  - Makefile evolution detection (missing targets, proposed additions)

Each detected candidate includes:
  name, kind, builder, confidence, description, detected_from,
  operability, operability_notes, remediation, build_cmd, output_dir
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path


# ── Public API ──────────────────────────────────────────────────────


def detect_artifact_targets(project_root: Path) -> list[dict]:
    """Scan project for buildable artifact targets.

    Returns a list of candidate dicts, each with:
      name, kind, builder, build_target, description,
      detected_from, confidence,
      operability, operability_notes, remediation
    """
    candidates = []

    # ── Makefile targets ─────────────────────────────────────────
    makefile = project_root / "Makefile"
    if makefile.exists():
        candidates.extend(_detect_makefile_targets(makefile, project_root))

    # ── pyproject.toml / setup.py → pip package ──────────────────
    pyproject = project_root / "pyproject.toml"
    setup_py = project_root / "setup.py"
    if pyproject.exists() or setup_py.exists():
        pip_candidate = _detect_pip_package(pyproject, setup_py, project_root)
        if pip_candidate:
            candidates.append(pip_candidate)

    # ── Dockerfile → container ───────────────────────────────────
    dockerfile = project_root / "Dockerfile"
    if dockerfile.exists():
        candidates.append(_detect_container(dockerfile, project_root))

    # ── Release/bundle scripts ───────────────────────────────────
    scripts_dir = project_root / "scripts"
    if scripts_dir.is_dir():
        candidates.extend(_detect_release_scripts(scripts_dir))

    return candidates


def detect_makefile_evolution(project_root: Path) -> dict:
    """Detect what the Makefile is missing and propose additions.

    Returns:
      {
        "has_makefile": bool,
        "existing_targets": [str],
        "proposed_additions": [
          {
            "target": "build",
            "recipe": "python -m build",
            "reason": "pyproject.toml has [build-system] — add a make target for pip package builds",
            "deps": "",
          },
          ...
        ],
        "operability": "full" | "partial" | "none",
        "operability_notes": [str],
        "remediation": {
          "type": "makefile_rewrite",
          "description": "Fix venv-unaware commands",
          "changes": [
            {"line_number": 8, "current": "pip install ...", "proposed": "$(VENV)pip install ..."},
          ],
          "preamble": "VENV := $(shell ...)"  # New lines to add at top
        } | None,
      }
    """
    makefile = project_root / "Makefile"

    if not makefile.exists():
        # No Makefile at all — propose full generation
        return _propose_new_makefile(project_root)

    try:
        content = makefile.read_text()
    except OSError:
        return {
            "has_makefile": True,
            "existing_targets": [],
            "proposed_additions": [],
            "operability": "none",
            "operability_notes": ["⚠️ Could not read Makefile"],
            "remediation": None,
        }

    lines = content.splitlines()
    existing_targets = _parse_makefile_targets(content)
    has_venv = (project_root / ".venv").is_dir()

    # ── Operability analysis ──
    operability, notes, remediation = _analyze_makefile_operability(
        content, lines, has_venv
    )

    # ── Evolution: what targets are missing? ──
    proposed = _propose_target_additions(
        existing_targets, project_root, has_venv
    )

    return {
        "has_makefile": True,
        "existing_targets": list(existing_targets.keys()),
        "proposed_additions": proposed,
        "operability": operability,
        "operability_notes": notes,
        "remediation": remediation,
    }


# ── Makefile Targets Detection ──────────────────────────────────────


def _parse_makefile_targets(content: str) -> dict[str, dict]:
    """Parse Makefile targets into {name: {deps, description, line_number, recipe_lines}}."""
    targets: dict[str, dict] = {}
    lines = content.splitlines()

    for i, line in enumerate(lines):
        # Match: target: [deps] ## description
        m = re.match(r'^([a-zA-Z_][\w-]*):\s*(.*?)(?:\s*##\s*(.*))?$', line)
        if m:
            name = m.group(1)
            deps = m.group(2).strip()
            desc = (m.group(3) or "").strip()
            if not name.startswith("."):
                # Collect recipe lines (following lines starting with \t)
                recipe_lines = []
                for j in range(i + 1, len(lines)):
                    if lines[j].startswith("\t"):
                        recipe_lines.append(lines[j].lstrip("\t"))
                    else:
                        break

                targets[name] = {
                    "deps": deps,
                    "description": desc,
                    "line_number": i + 1,  # 1-indexed
                    "recipe_lines": recipe_lines,
                }

    return targets


def _detect_makefile_targets(
    makefile: Path, project_root: Path
) -> list[dict]:
    """Parse Makefile and return artifact candidates with operability info."""
    try:
        content = makefile.read_text()
    except OSError:
        return []

    targets = _parse_makefile_targets(content)
    has_venv = (project_root / ".venv").is_dir()
    lines = content.splitlines()

    # Analyze operability once for the whole Makefile
    operability, op_notes, remediation = _analyze_makefile_operability(
        content, lines, has_venv
    )

    candidates = []

    # Map known Makefile targets to artifact candidates
    target_map = {
        "install": {
            "name": "local-install",
            "kind": "local",
            "default_desc": "Install package locally",
        },
        "check": {
            "name": "quality-check",
            "kind": "local",
            "default_desc": "Run all quality checks",
        },
        "test": {
            "name": "test",
            "kind": "local",
            "default_desc": "Run tests",
            "skip_if": "check",  # Skip if 'check' includes test
        },
        "clean": {
            "name": "clean",
            "kind": "local",
            "default_desc": "Clean build artifacts",
        },
        "build": {
            "name": "build",
            "kind": "package",
            "default_desc": "Build distributable package",
        },
        "dist": {
            "name": "dist",
            "kind": "package",
            "default_desc": "Create distribution artifacts",
        },
    }

    for target_name, mapping in target_map.items():
        if target_name not in targets:
            continue

        # Skip test if check already includes it
        skip_if = mapping.get("skip_if")
        if skip_if and skip_if in targets:
            continue

        t = targets[target_name]
        candidates.append({
            "name": mapping["name"],
            "kind": mapping["kind"],
            "builder": "makefile",
            "build_target": target_name,
            "build_cmd": "",
            "description": t["description"] or mapping["default_desc"],
            "detected_from": f"Makefile:{target_name}",
            "confidence": "high",
            "output_dir": "",
            "operability": operability,
            "operability_notes": op_notes,
            "remediation": remediation,
        })

    return candidates


# ── Makefile Operability Analysis ───────────────────────────────────


# Commands that need to come from the venv
_VENV_COMMANDS = {"pip", "python", "python3", "pytest", "ruff", "mypy"}


def _analyze_makefile_operability(
    content: str, lines: list[str], has_venv: bool
) -> tuple[str, list[str], dict | None]:
    """Analyze a Makefile for operability issues.

    Returns (operability, notes, remediation).
    """
    notes: list[str] = []
    remediation: dict | None = None

    # Detect which bare commands are used in recipe lines
    bare_commands_found: dict[str, list[int]] = {}
    for i, line in enumerate(lines):
        if not line.startswith("\t"):
            continue
        recipe = line.lstrip("\t")
        # Skip comments and variable assignments
        if recipe.startswith("#") or recipe.startswith("@echo"):
            continue

        for cmd in _VENV_COMMANDS:
            # Match bare command at start of line or after @ or after ;
            # But NOT if preceded by $(VENV), .venv/bin/, or a path
            patterns = [
                rf'^@?{re.escape(cmd)}\b',
                rf';\s*{re.escape(cmd)}\b',
            ]
            for pat in patterns:
                if re.search(pat, recipe):
                    # Check it's not already venv-qualified
                    if f"$(VENV){cmd}" not in recipe and f".venv/bin/{cmd}" not in recipe:
                        bare_commands_found.setdefault(cmd, []).append(i + 1)

    # Check for existing VENV variable
    has_venv_var = bool(re.search(r'^VENV\s*[:?]?=', content, re.MULTILINE))

    # Determine operability
    if not bare_commands_found:
        # No bare venv commands — either venv-aware or doesn't use them
        if has_venv_var:
            operability = "full"
            notes.append("✅ Makefile uses VENV prefix for Python commands")
        elif "DEVOPS_" in content:
            operability = "full"
            notes.append("✅ Makefile reads DEVOPS_* environment variables")
        else:
            operability = "full"
            notes.append("✅ No bare Python commands detected in recipes")
        return operability, notes, None

    if not has_venv:
        # Bare commands found, but no .venv/ — check if they're global
        global_available = {}
        for cmd in bare_commands_found:
            global_available[cmd] = shutil.which(cmd) is not None

        if all(global_available.values()):
            operability = "full"
            notes.append(
                f"✅ Commands available globally: "
                f"{', '.join(sorted(bare_commands_found.keys()))}"
            )
            return operability, notes, None
        else:
            missing = [c for c, avail in global_available.items() if not avail]
            operability = "none"
            notes.append(
                f"❌ Commands not found on PATH: {', '.join(missing)}"
            )
            notes.append(
                "No .venv/ directory detected. Create one with: "
                "python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'"
            )
            return operability, notes, None

    # Bare commands found AND .venv/ exists → partial, remediation available
    operability = "partial"
    cmd_list = sorted(bare_commands_found.keys())
    notes.append(
        f"⚠️ Makefile uses bare commands ({', '.join(cmd_list)}) "
        f"but .venv/ exists — these will fail without venv activation"
    )
    notes.append(
        "Fix: Add a VENV prefix variable and use $(VENV)pip, $(VENV)pytest, etc."
    )

    # Build remediation: line-by-line changes
    preamble = 'VENV := $(shell [ -d .venv ] && echo .venv/bin/ || echo "")'
    changes = []

    for i, line in enumerate(lines):
        if not line.startswith("\t"):
            continue
        recipe = line.lstrip("\t")
        new_recipe = recipe

        for cmd in _VENV_COMMANDS:
            # Replace bare command with $(VENV)command
            # But only at the start or after @
            new_recipe = re.sub(
                rf'^(@?){re.escape(cmd)}\b',
                rf'\1$(VENV){cmd}',
                new_recipe,
            )

        if new_recipe != recipe:
            changes.append({
                "line_number": i + 1,
                "current": line,
                "proposed": "\t" + new_recipe,
            })

    if changes:
        remediation = {
            "type": "makefile_patch",
            "description": (
                f"Add VENV auto-detection and prefix {len(changes)} "
                f"command(s) with $(VENV). When .venv/ exists, commands "
                f"use .venv/bin/; otherwise they use the global PATH."
            ),
            "preamble": preamble,
            "preamble_after_line": _find_preamble_insert_line(lines),
            "changes": changes,
        }

    return operability, notes, remediation


def _find_preamble_insert_line(lines: list[str]) -> int:
    """Find the line number after .PHONY declaration (best place for VENV var)."""
    for i, line in enumerate(lines):
        if line.startswith(".PHONY"):
            return i + 1  # 0-indexed, so this is after .PHONY line
    return 0  # Insert at top if no .PHONY


# ── Makefile Evolution Detection ────────────────────────────────────


def _propose_target_additions(
    existing_targets: dict[str, dict],
    project_root: Path,
    has_venv: bool,
) -> list[dict]:
    """Compare existing targets vs recommended and propose additions."""
    venv = "$(VENV)" if has_venv else ""
    proposed = []

    # Check what tools exist in the project
    has_pyproject = (project_root / "pyproject.toml").exists()
    has_ruff = _has_dev_dep(project_root, "ruff")
    has_mypy = _has_dev_dep(project_root, "mypy")
    has_pytest = _has_dev_dep(project_root, "pytest")
    has_dockerfile = (project_root / "Dockerfile").exists()

    # ── install ──
    if "install" not in existing_targets and has_pyproject:
        proposed.append({
            "target": "install",
            "recipe": f'{venv}pip install -e ".[dev]"',
            "deps": "",
            "description": "Install package in editable mode with dev deps",
            "reason": "pyproject.toml found — editable install is the standard local dev setup",
        })

    # ── lint ──
    if "lint" not in existing_targets and has_ruff:
        proposed.append({
            "target": "lint",
            "recipe": f"{venv}ruff check src/ tests/",
            "deps": "",
            "description": "Run ruff linter",
            "reason": "ruff is in dev dependencies",
        })

    # ── format ──
    if "format" not in existing_targets and has_ruff:
        proposed.append({
            "target": "format",
            "recipe": f"{venv}ruff format src/ tests/",
            "deps": "",
            "description": "Run ruff formatter",
            "reason": "ruff is in dev dependencies",
        })

    # ── test ──
    if "test" not in existing_targets and has_pytest:
        proposed.append({
            "target": "test",
            "recipe": f"{venv}pytest",
            "deps": "",
            "description": "Run tests with pytest",
            "reason": "pytest is in dev dependencies",
        })

    # ── types ──
    if "types" not in existing_targets and has_mypy:
        proposed.append({
            "target": "types",
            "recipe": f"{venv}mypy src/",
            "deps": "",
            "description": "Run mypy type checker",
            "reason": "mypy is in dev dependencies",
        })

    # ── check (meta-target) ──
    if "check" not in existing_targets:
        # Only propose if we have at least 2 quality tools
        quality_targets = [t for t in ["lint", "types", "test"]
                          if t in existing_targets or any(p["target"] == t for p in proposed)]
        if len(quality_targets) >= 2:
            proposed.append({
                "target": "check",
                "recipe": '@echo ""\n\t@echo "  ✅ All checks passed"\n\t@echo ""',
                "deps": " ".join(quality_targets),
                "description": f"Run all checks ({' + '.join(quality_targets)})",
                "reason": f"Combines {', '.join(quality_targets)} into a single command",
            })

    # ── build (pip package) ──
    if "build" not in existing_targets and has_pyproject:
        proposed.append({
            "target": "build",
            "recipe": f"{venv}python -m build",
            "deps": "clean",
            "description": "Build pip wheel and sdist",
            "reason": "pyproject.toml has [build-system] — enables `make build` for packaging",
        })

    # ── clean ──
    if "clean" not in existing_targets:
        proposed.append({
            "target": "clean",
            "recipe": (
                "rm -rf build/ dist/ *.egg-info .mypy_cache .pytest_cache .ruff_cache\n"
                "\tfind . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true"
            ),
            "deps": "",
            "description": "Remove build artifacts and caches",
            "reason": "Standard cleanup target for Python projects",
        })

    # ── docker ──
    if "docker" not in existing_targets and has_dockerfile:
        name = project_root.name
        proposed.append({
            "target": "docker",
            "recipe": f"docker build -t {name} .",
            "deps": "",
            "description": "Build Docker container image",
            "reason": "Dockerfile found in project root",
        })

    return proposed


def _propose_new_makefile(project_root: Path) -> dict:
    """Propose a full Makefile when none exists."""
    has_venv = (project_root / ".venv").is_dir()
    proposed = _propose_target_additions({}, project_root, has_venv)

    return {
        "has_makefile": False,
        "existing_targets": [],
        "proposed_additions": proposed,
        "operability": "none",
        "operability_notes": [
            "⚠️ No Makefile found in project root.",
            "A Makefile provides standardized build commands (make install, make test, etc.).",
            f"Detected {len(proposed)} target(s) that could be generated from project structure.",
        ],
        "remediation": None,
    }


# ── Pip Package Detection ──────────────────────────────────────────


def _detect_pip_package(
    pyproject: Path, setup_py: Path, project_root: Path
) -> dict | None:
    """Detect pip package candidate from pyproject.toml or setup.py."""
    source = "pyproject.toml" if pyproject.exists() else "setup.py"
    has_build_system = False

    if pyproject.exists():
        try:
            content = pyproject.read_text()
            has_build_system = "[build-system]" in content
        except OSError:
            pass

    if not has_build_system and not setup_py.exists():
        return None

    # Operability: check if 'build' module is available
    notes = []
    operability = "full"
    has_venv = (project_root / ".venv").is_dir()

    # Check if python -m build would work
    python_cmd = ".venv/bin/python" if has_venv else "python"
    build_available = shutil.which(python_cmd) is not None

    if not build_available:
        operability = "partial"
        notes.append(f"⚠️ {python_cmd} not found on PATH")
    else:
        notes.append(f"✅ Python available at: {python_cmd}")

    if has_build_system:
        notes.append("✅ pyproject.toml has [build-system] section")
    else:
        notes.append("⚠️ No [build-system] in pyproject.toml — using setup.py fallback")

    # Version detection
    version = _extract_version(pyproject if pyproject.exists() else setup_py)
    if version:
        notes.append(f"📦 Version: {version}")

    return {
        "name": "pip-package",
        "kind": "package",
        "builder": "pip",
        "build_target": "",
        "build_cmd": f"{python_cmd} -m build",
        "description": f"Build pip wheel/sdist from {source}",
        "detected_from": source,
        "confidence": "high" if has_build_system else "medium",
        "output_dir": "dist/",
        "operability": operability,
        "operability_notes": notes,
        "remediation": None,
    }


# ── Container Detection ────────────────────────────────────────────


def _detect_container(
    dockerfile: Path, project_root: Path
) -> dict:
    """Detect container build candidate."""
    project_name = project_root.name
    notes = []

    # Check for docker/podman
    docker_cmd = None
    if shutil.which("docker"):
        docker_cmd = "docker"
        notes.append("✅ Docker available")
    elif shutil.which("podman"):
        docker_cmd = "podman"
        notes.append("✅ Podman available")
    else:
        notes.append("⚠️ Neither docker nor podman found on PATH")

    operability = "full" if docker_cmd else "partial"

    # Check for docker-compose
    compose = project_root / "docker-compose.yml"
    if compose.exists():
        notes.append("📋 docker-compose.yml found")

    return {
        "name": "container",
        "kind": "container",
        "builder": "docker",
        "build_target": "",
        "build_cmd": f"{docker_cmd or 'docker'} build -t {project_name} .",
        "description": "Build Docker container image",
        "detected_from": "Dockerfile",
        "confidence": "high",
        "output_dir": "",
        "operability": operability,
        "operability_notes": notes,
        "remediation": None,
    }


# ── Release Script Detection ──────────────────────────────────────


def _detect_release_scripts(scripts_dir: Path) -> list[dict]:
    """Detect release/bundle/package scripts in scripts/."""
    candidates = []

    for script in sorted(scripts_dir.iterdir()):
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
            executable = script.stat().st_mode & 0o111

            notes = []
            if executable:
                notes.append(f"✅ Script is executable")
            else:
                notes.append(f"⚠️ Script is not executable — will use bash fallback")

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
                "operability": "full" if executable else "partial",
                "operability_notes": notes,
                "remediation": None,
            })

    return candidates


# ── Helpers ─────────────────────────────────────────────────────────


def _extract_script_description(script: Path) -> str:
    """Extract description from script header comments."""
    try:
        lines = script.read_text().splitlines()[:10]
        for line in lines:
            if line.startswith("#!") or not line.strip():
                continue
            if line.startswith("#"):
                desc = line.lstrip("# ").strip()
                if desc:
                    return desc
    except OSError:
        pass
    return ""


def _extract_version(config_file: Path) -> str:
    """Extract version from pyproject.toml or setup.py."""
    try:
        content = config_file.read_text()
        # pyproject.toml: version = "0.1.0"
        m = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
        if m:
            return m.group(1)
        # setup.py: version="0.1.0"
        m = re.search(r'version\s*=\s*["\']([^"\']+)["\']', content)
        if m:
            return m.group(1)
    except OSError:
        pass
    return ""


def _has_dev_dep(project_root: Path, package: str) -> bool:
    """Check if a package is in the project's dev dependencies."""
    pyproject = project_root / "pyproject.toml"
    if not pyproject.exists():
        return False
    try:
        content = pyproject.read_text()
        # Simple check — look for the package name in [project.optional-dependencies] dev section
        in_dev = False
        for line in content.splitlines():
            if line.strip() == "dev = [":
                in_dev = True
                continue
            if in_dev:
                if line.strip() == "]":
                    break
                if package.lower() in line.lower():
                    return True
    except OSError:
        pass
    return False
