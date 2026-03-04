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

    Stack-aware — scans for ALL supported project types.
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

    # ── package.json → npm package ───────────────────────────────
    package_json = project_root / "package.json"
    if package_json.exists():
        npm_candidate = _detect_npm_package(package_json, project_root)
        if npm_candidate:
            candidates.append(npm_candidate)

    # ── Cargo.toml → Rust crate ──────────────────────────────────
    cargo_toml = project_root / "Cargo.toml"
    if cargo_toml.exists():
        cargo_candidate = _detect_cargo_package(cargo_toml, project_root)
        if cargo_candidate:
            candidates.append(cargo_candidate)

    # ── go.mod → Go module ───────────────────────────────────────
    go_mod = project_root / "go.mod"
    if go_mod.exists():
        go_candidate = _detect_go_module(go_mod, project_root)
        if go_candidate:
            candidates.append(go_candidate)

    # ── *.gemspec → Ruby gem ─────────────────────────────────────
    gemspecs = list(project_root.glob("*.gemspec"))
    if gemspecs:
        gem_candidate = _detect_ruby_gem(gemspecs[0], project_root)
        if gem_candidate:
            candidates.append(gem_candidate)

    # ── pom.xml / build.gradle → Java package ────────────────────
    pom = project_root / "pom.xml"
    build_gradle = project_root / "build.gradle"
    build_gradle_kts = project_root / "build.gradle.kts"
    if pom.exists() or build_gradle.exists() or build_gradle_kts.exists():
        java_candidate = _detect_java_package(pom, build_gradle, build_gradle_kts, project_root)
        if java_candidate:
            candidates.append(java_candidate)

    # ── *.csproj → .NET package ──────────────────────────────────
    csprojs = list(project_root.glob("*.csproj")) + list(project_root.glob("**/*.csproj"))
    if csprojs:
        dotnet_candidate = _detect_dotnet_package(csprojs[0], project_root)
        if dotnet_candidate:
            candidates.append(dotnet_candidate)

    # ── mix.exs → Elixir package ─────────────────────────────────
    mix_exs = project_root / "mix.exs"
    if mix_exs.exists():
        elixir_candidate = _detect_elixir_package(mix_exs, project_root)
        if elixir_candidate:
            candidates.append(elixir_candidate)

    # ── composer.json → PHP package ──────────────────────────────
    composer_json = project_root / "composer.json"
    if composer_json.exists():
        candidates.append({
            "name": f"php-{project_root.name}",
            "kind": "package",
            "builder": "script",
            "build_target": "",
            "build_cmd": "composer install --no-dev --optimize-autoloader",
            "output_dir": "vendor/",
            "description": f"PHP package: {project_root.name}",
            "detected_from": "composer.json",
            "confidence": 0.7,
            "operability": "full" if shutil.which("composer") or shutil.which("php") else "blocked",
            "operability_notes": ["composer available"] if shutil.which("composer") else ["composer not found"],
            "remediation": "Install Composer" if not shutil.which("composer") else None,
        })

    # ── CMakeLists.txt → C/C++ binary ────────────────────────────
    cmake_lists = project_root / "CMakeLists.txt"
    if cmake_lists.exists():
        candidates.append({
            "name": f"cmake-{project_root.name}",
            "kind": "bundle",
            "builder": "script",
            "build_target": "build",
            "build_cmd": "cmake -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build",
            "output_dir": "build/",
            "description": f"C/C++ binary (CMake): {project_root.name}",
            "detected_from": "CMakeLists.txt",
            "confidence": 0.85,
            "operability": "full" if shutil.which("cmake") else "blocked",
            "operability_notes": ["cmake available"] if shutil.which("cmake") else ["cmake not found"],
            "remediation": "Install CMake" if not shutil.which("cmake") else None,
        })

    # ── build.zig → Zig binary ───────────────────────────────────
    build_zig = project_root / "build.zig"
    if build_zig.exists():
        candidates.append({
            "name": f"zig-{project_root.name}",
            "kind": "bundle",
            "builder": "script",
            "build_target": "build",
            "build_cmd": "zig build -Doptimize=ReleaseSafe",
            "output_dir": "zig-out/",
            "description": f"Zig binary: {project_root.name}",
            "detected_from": "build.zig",
            "confidence": 0.85,
            "operability": "full" if shutil.which("zig") else "blocked",
            "operability_notes": ["zig available"] if shutil.which("zig") else ["zig not found"],
            "remediation": "Install Zig" if not shutil.which("zig") else None,
        })

    # ── Package.swift → Swift package ────────────────────────────
    package_swift = project_root / "Package.swift"
    if package_swift.exists():
        candidates.append({
            "name": f"swift-{project_root.name}",
            "kind": "package",
            "builder": "script",
            "build_target": "build",
            "build_cmd": "swift build -c release",
            "output_dir": ".build/release/",
            "description": f"Swift package: {project_root.name}",
            "detected_from": "Package.swift",
            "confidence": 0.85,
            "operability": "full" if shutil.which("swift") else "blocked",
            "operability_notes": ["swift available"] if shutil.which("swift") else ["swift not found"],
            "remediation": "Install Swift" if not shutil.which("swift") else None,
        })

    # ── docker-compose.yml / compose.yml → compose stack ─────────
    compose_file = None
    if (project_root / "docker-compose.yml").exists():
        compose_file = "docker-compose.yml"
    elif (project_root / "compose.yml").exists():
        compose_file = "compose.yml"
    if compose_file:
        candidates.append({
            "name": "compose-stack",
            "kind": "container",
            "builder": "script",
            "build_target": "build",
            "build_cmd": f"docker compose -f {compose_file} build",
            "output_dir": "",
            "description": f"Docker Compose stack ({compose_file})",
            "detected_from": compose_file,
            "confidence": 0.8,
            "operability": "full" if shutil.which("docker") else "blocked",
            "operability_notes": ["docker available"] if shutil.which("docker") else ["docker not found"],
            "remediation": "Install Docker" if not shutil.which("docker") else None,
        })

    # ── Chart.yaml → Helm chart ──────────────────────────────────
    chart_yaml = project_root / "Chart.yaml"
    if chart_yaml.exists():
        candidates.append({
            "name": f"helm-{project_root.name}",
            "kind": "package",
            "builder": "script",
            "build_target": "package",
            "build_cmd": "helm package . -d dist/",
            "output_dir": "dist/",
            "description": f"Helm chart: {project_root.name}",
            "detected_from": "Chart.yaml",
            "confidence": 0.85,
            "operability": "full" if shutil.which("helm") else "blocked",
            "operability_notes": ["helm available"] if shutil.which("helm") else ["helm not found"],
            "remediation": "Install Helm" if not shutil.which("helm") else None,
        })

    # ── *.tf → Terraform module ──────────────────────────────────
    tf_files = list(project_root.glob("*.tf"))
    if tf_files:
        candidates.append({
            "name": f"terraform-{project_root.name}",
            "kind": "bundle",
            "builder": "script",
            "build_target": "plan",
            "build_cmd": "terraform init && terraform plan -out=tfplan",
            "output_dir": "",
            "description": f"Terraform module: {project_root.name}",
            "detected_from": "*.tf",
            "confidence": 0.7,
            "operability": "full" if shutil.which("terraform") else "blocked",
            "operability_notes": ["terraform available"] if shutil.which("terraform") else ["terraform not found"],
            "remediation": "Install Terraform" if not shutil.which("terraform") else None,
        })

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

    # ── Node.js (package.json) ──
    has_package_json = (project_root / "package.json").exists()
    if has_package_json:
        import json as _json
        try:
            pkg_data = _json.loads((project_root / "package.json").read_text())
            pkg_scripts = pkg_data.get("scripts", {})
        except (OSError, _json.JSONDecodeError):
            pkg_scripts = {}

        if "install" not in existing_targets and "node-install" not in existing_targets:
            proposed.append({
                "target": "install",
                "recipe": "npm ci",
                "deps": "",
                "description": "Install npm dependencies (clean install)",
                "reason": "package.json found — npm ci ensures reproducible installs",
            })

        if "build" not in existing_targets and "build" in pkg_scripts:
            proposed.append({
                "target": "build",
                "recipe": "npm run build",
                "deps": "install",
                "description": "Build the project",
                "reason": "package.json has a 'build' script",
            })

        if "test" not in existing_targets and "test" in pkg_scripts:
            proposed.append({
                "target": "test",
                "recipe": "npm test",
                "deps": "",
                "description": "Run tests",
                "reason": "package.json has a 'test' script",
            })

        if "lint" not in existing_targets and "lint" in pkg_scripts:
            proposed.append({
                "target": "lint",
                "recipe": "npm run lint",
                "deps": "",
                "description": "Run linter",
                "reason": "package.json has a 'lint' script",
            })

        if "clean" not in existing_targets:
            proposed.append({
                "target": "clean",
                "recipe": "rm -rf node_modules dist build .cache .next",
                "deps": "",
                "description": "Remove build artifacts and node_modules",
                "reason": "Standard cleanup for Node.js projects",
            })

    # ── Go (go.mod) ──
    has_go_mod = (project_root / "go.mod").exists()
    if has_go_mod:
        if "build" not in existing_targets:
            name = project_root.name
            proposed.append({
                "target": "build",
                "recipe": f"go build -o dist/{name} ./...",
                "deps": "",
                "description": "Build Go binary",
                "reason": "go.mod found — standard Go build",
            })

        if "test" not in existing_targets:
            proposed.append({
                "target": "test",
                "recipe": "go test ./...",
                "deps": "",
                "description": "Run Go tests",
                "reason": "go.mod found — standard Go test",
            })

        if "lint" not in existing_targets:
            has_golint = shutil.which("golangci-lint") is not None
            if has_golint:
                proposed.append({
                    "target": "lint",
                    "recipe": "golangci-lint run ./...",
                    "deps": "",
                    "description": "Run golangci-lint",
                    "reason": "golangci-lint is available",
                })
            else:
                proposed.append({
                    "target": "lint",
                    "recipe": "go vet ./...",
                    "deps": "",
                    "description": "Run go vet",
                    "reason": "go.mod found — go vet is the built-in linter",
                })

        if "clean" not in existing_targets:
            proposed.append({
                "target": "clean",
                "recipe": "rm -rf dist/ && go clean",
                "deps": "",
                "description": "Clean build artifacts",
                "reason": "Standard cleanup for Go projects",
            })

    # ── Rust (Cargo.toml) ──
    has_cargo_toml = (project_root / "Cargo.toml").exists()
    if has_cargo_toml:
        if "build" not in existing_targets:
            proposed.append({
                "target": "build",
                "recipe": "cargo build --release",
                "deps": "",
                "description": "Build release binary",
                "reason": "Cargo.toml found — standard Rust release build",
            })

        if "test" not in existing_targets:
            proposed.append({
                "target": "test",
                "recipe": "cargo test",
                "deps": "",
                "description": "Run Rust tests",
                "reason": "Cargo.toml found — standard Rust test",
            })

        if "lint" not in existing_targets:
            proposed.append({
                "target": "lint",
                "recipe": "cargo clippy -- -D warnings",
                "deps": "",
                "description": "Run Clippy linter",
                "reason": "Cargo.toml found — clippy is the standard Rust linter",
            })

        if "format" not in existing_targets:
            proposed.append({
                "target": "format",
                "recipe": "cargo fmt",
                "deps": "",
                "description": "Format Rust code",
                "reason": "Cargo.toml found — rustfmt is the standard formatter",
            })

        if "clean" not in existing_targets:
            proposed.append({
                "target": "clean",
                "recipe": "cargo clean",
                "deps": "",
                "description": "Clean build artifacts",
                "reason": "Standard cleanup for Rust projects",
            })

    # ── Ruby (Gemfile / *.gemspec) ──
    has_gemfile = (project_root / "Gemfile").exists()
    has_gemspec = bool(list(project_root.glob("*.gemspec")))
    if has_gemfile or has_gemspec:
        if "install" not in existing_targets and has_gemfile:
            proposed.append({
                "target": "install",
                "recipe": "bundle install",
                "deps": "",
                "description": "Install gem dependencies",
                "reason": "Gemfile found",
            })

        has_rakefile = (project_root / "Rakefile").exists()
        if "test" not in existing_targets:
            if has_rakefile:
                proposed.append({
                    "target": "test",
                    "recipe": "bundle exec rake test",
                    "deps": "",
                    "description": "Run tests via Rake",
                    "reason": "Rakefile found",
                })
            else:
                proposed.append({
                    "target": "test",
                    "recipe": "bundle exec rspec",
                    "deps": "",
                    "description": "Run RSpec tests",
                    "reason": "Gemfile found — using RSpec as default",
                })

        if "build" not in existing_targets and has_gemspec:
            gemspec_name = list(project_root.glob("*.gemspec"))[0].name
            proposed.append({
                "target": "build",
                "recipe": f"gem build {gemspec_name}",
                "deps": "",
                "description": "Build gem package",
                "reason": f"{gemspec_name} found",
            })

        if "lint" not in existing_targets:
            proposed.append({
                "target": "lint",
                "recipe": "bundle exec rubocop",
                "deps": "",
                "description": "Run RuboCop linter",
                "reason": "Standard Ruby linter",
            })

    # ── Java Maven (pom.xml) ──
    has_pom = (project_root / "pom.xml").exists()
    if has_pom:
        if "build" not in existing_targets:
            proposed.append({
                "target": "build",
                "recipe": "mvn package -DskipTests",
                "deps": "",
                "description": "Build Maven package",
                "reason": "pom.xml found",
            })

        if "test" not in existing_targets:
            proposed.append({
                "target": "test",
                "recipe": "mvn test",
                "deps": "",
                "description": "Run Maven tests",
                "reason": "pom.xml found",
            })

        if "clean" not in existing_targets:
            proposed.append({
                "target": "clean",
                "recipe": "mvn clean",
                "deps": "",
                "description": "Clean Maven build artifacts",
                "reason": "pom.xml found",
            })

    # ── Java Gradle (build.gradle / build.gradle.kts) ──
    has_build_gradle = (project_root / "build.gradle").exists() or (project_root / "build.gradle.kts").exists()
    if has_build_gradle and not has_pom:
        gradlew = project_root / "gradlew"
        gradle_cmd = "./gradlew" if gradlew.exists() else "gradle"

        if "build" not in existing_targets:
            proposed.append({
                "target": "build",
                "recipe": f"{gradle_cmd} build -x test",
                "deps": "",
                "description": "Build Gradle project",
                "reason": "build.gradle found",
            })

        if "test" not in existing_targets:
            proposed.append({
                "target": "test",
                "recipe": f"{gradle_cmd} test",
                "deps": "",
                "description": "Run Gradle tests",
                "reason": "build.gradle found",
            })

        if "clean" not in existing_targets:
            proposed.append({
                "target": "clean",
                "recipe": f"{gradle_cmd} clean",
                "deps": "",
                "description": "Clean Gradle build artifacts",
                "reason": "build.gradle found",
            })

    # ── .NET (*.csproj / *.sln) ──
    has_csproj = bool(list(project_root.glob("*.csproj")) + list(project_root.glob("*.sln")))
    if has_csproj:
        if "build" not in existing_targets:
            proposed.append({
                "target": "build",
                "recipe": "dotnet build -c Release",
                "deps": "",
                "description": "Build .NET project",
                "reason": ".csproj or .sln found",
            })

        if "test" not in existing_targets:
            proposed.append({
                "target": "test",
                "recipe": "dotnet test",
                "deps": "",
                "description": "Run .NET tests",
                "reason": ".csproj or .sln found",
            })

        if "publish" not in existing_targets:
            proposed.append({
                "target": "publish",
                "recipe": "dotnet publish -c Release -o dist/",
                "deps": "build",
                "description": "Publish .NET application",
                "reason": ".csproj or .sln found",
            })

        if "clean" not in existing_targets:
            proposed.append({
                "target": "clean",
                "recipe": "dotnet clean && rm -rf dist/",
                "deps": "",
                "description": "Clean .NET build artifacts",
                "reason": ".csproj or .sln found",
            })

    # ── Elixir (mix.exs) ──
    has_mix_exs = (project_root / "mix.exs").exists()
    if has_mix_exs:
        if "install" not in existing_targets:
            proposed.append({
                "target": "install",
                "recipe": "mix deps.get",
                "deps": "",
                "description": "Install Elixir dependencies",
                "reason": "mix.exs found",
            })

        if "build" not in existing_targets:
            proposed.append({
                "target": "build",
                "recipe": "mix compile",
                "deps": "install",
                "description": "Compile Elixir project",
                "reason": "mix.exs found",
            })

        if "test" not in existing_targets:
            proposed.append({
                "target": "test",
                "recipe": "mix test",
                "deps": "",
                "description": "Run Elixir tests",
                "reason": "mix.exs found",
            })

        if "release" not in existing_targets:
            proposed.append({
                "target": "release",
                "recipe": "MIX_ENV=prod mix release",
                "deps": "build",
                "description": "Build Elixir release",
                "reason": "mix.exs found — OTP release",
            })

        if "clean" not in existing_targets:
            proposed.append({
                "target": "clean",
                "recipe": "mix clean && rm -rf _build/",
                "deps": "",
                "description": "Clean Elixir build artifacts",
                "reason": "mix.exs found",
            })

    # ── PHP (composer.json) ──
    has_composer = (project_root / "composer.json").exists()
    if has_composer:
        if "install" not in existing_targets:
            proposed.append({
                "target": "install",
                "recipe": "composer install",
                "deps": "",
                "description": "Install PHP dependencies",
                "reason": "composer.json found",
            })

        if "test" not in existing_targets:
            proposed.append({
                "target": "test",
                "recipe": "vendor/bin/phpunit",
                "deps": "",
                "description": "Run PHPUnit tests",
                "reason": "composer.json found",
            })

        if "lint" not in existing_targets:
            proposed.append({
                "target": "lint",
                "recipe": "vendor/bin/phpstan analyse",
                "deps": "",
                "description": "Run PHPStan static analysis",
                "reason": "composer.json found",
            })

    # ── C / C++ (CMakeLists.txt or Makefile already handled) ──
    has_cmake = (project_root / "CMakeLists.txt").exists()
    if has_cmake:
        if "build" not in existing_targets:
            proposed.append({
                "target": "build",
                "recipe": "cmake -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build",
                "deps": "",
                "description": "Build with CMake (Release)",
                "reason": "CMakeLists.txt found",
            })

        if "test" not in existing_targets:
            proposed.append({
                "target": "test",
                "recipe": "cd build && ctest --output-on-failure",
                "deps": "build",
                "description": "Run CTest",
                "reason": "CMakeLists.txt found",
            })

        if "clean" not in existing_targets:
            proposed.append({
                "target": "clean",
                "recipe": "rm -rf build/",
                "deps": "",
                "description": "Clean CMake build directory",
                "reason": "CMakeLists.txt found",
            })

    # ── Zig (build.zig) ──
    has_zig = (project_root / "build.zig").exists()
    if has_zig:
        if "build" not in existing_targets:
            proposed.append({
                "target": "build",
                "recipe": "zig build -Doptimize=ReleaseSafe",
                "deps": "",
                "description": "Build Zig project (ReleaseSafe)",
                "reason": "build.zig found",
            })

        if "test" not in existing_targets:
            proposed.append({
                "target": "test",
                "recipe": "zig build test",
                "deps": "",
                "description": "Run Zig tests",
                "reason": "build.zig found",
            })

        if "clean" not in existing_targets:
            proposed.append({
                "target": "clean",
                "recipe": "rm -rf zig-out/ zig-cache/",
                "deps": "",
                "description": "Clean Zig build artifacts",
                "reason": "build.zig found",
            })

    # ── Swift (Package.swift) ──
    has_swift = (project_root / "Package.swift").exists()
    if has_swift:
        if "build" not in existing_targets:
            proposed.append({
                "target": "build",
                "recipe": "swift build -c release",
                "deps": "",
                "description": "Build Swift package (release)",
                "reason": "Package.swift found",
            })

        if "test" not in existing_targets:
            proposed.append({
                "target": "test",
                "recipe": "swift test",
                "deps": "",
                "description": "Run Swift tests",
                "reason": "Package.swift found",
            })

        if "clean" not in existing_targets:
            proposed.append({
                "target": "clean",
                "recipe": "swift package clean",
                "deps": "",
                "description": "Clean Swift build artifacts",
                "reason": "Package.swift found",
            })

    # ── Docker Compose (docker-compose.yml / compose.yml) ──
    has_compose = (project_root / "docker-compose.yml").exists() or (project_root / "compose.yml").exists()
    if has_compose:
        compose_file = "docker-compose.yml" if (project_root / "docker-compose.yml").exists() else "compose.yml"

        if "up" not in existing_targets:
            proposed.append({
                "target": "up",
                "recipe": f"docker compose -f {compose_file} up -d",
                "deps": "",
                "description": "Start services (detached)",
                "reason": f"{compose_file} found",
            })

        if "down" not in existing_targets:
            proposed.append({
                "target": "down",
                "recipe": f"docker compose -f {compose_file} down",
                "deps": "",
                "description": "Stop services",
                "reason": f"{compose_file} found",
            })

        if "docker-build" not in existing_targets and "build" not in existing_targets:
            proposed.append({
                "target": "docker-build",
                "recipe": f"docker compose -f {compose_file} build",
                "deps": "",
                "description": "Build all compose services",
                "reason": f"{compose_file} found",
            })

    # ── Helm (Chart.yaml) ──
    has_chart = (project_root / "Chart.yaml").exists()
    if has_chart:
        if "lint" not in existing_targets:
            proposed.append({
                "target": "lint",
                "recipe": "helm lint .",
                "deps": "",
                "description": "Lint Helm chart",
                "reason": "Chart.yaml found",
            })

        if "package" not in existing_targets:
            proposed.append({
                "target": "package",
                "recipe": "helm package . -d dist/",
                "deps": "lint",
                "description": "Package Helm chart",
                "reason": "Chart.yaml found",
            })

        if "template" not in existing_targets:
            proposed.append({
                "target": "template",
                "recipe": "helm template . > dist/rendered.yaml",
                "deps": "",
                "description": "Render Helm templates",
                "reason": "Chart.yaml found",
            })

    # ── Terraform ──
    has_tf = bool(list(project_root.glob("*.tf")))
    if has_tf:
        if "init" not in existing_targets:
            proposed.append({
                "target": "init",
                "recipe": "terraform init",
                "deps": "",
                "description": "Initialize Terraform",
                "reason": ".tf files found",
            })

        if "plan" not in existing_targets:
            proposed.append({
                "target": "plan",
                "recipe": "terraform plan -out=tfplan",
                "deps": "init",
                "description": "Generate Terraform plan",
                "reason": ".tf files found",
            })

        if "apply" not in existing_targets:
            proposed.append({
                "target": "apply",
                "recipe": "terraform apply tfplan",
                "deps": "plan",
                "description": "Apply Terraform plan",
                "reason": ".tf files found",
            })

        if "destroy" not in existing_targets:
            proposed.append({
                "target": "destroy",
                "recipe": "terraform destroy",
                "deps": "",
                "description": "Destroy Terraform resources",
                "reason": ".tf files found",
            })

    # ── Protobuf (*.proto) ──
    has_proto = bool(list(project_root.glob("**/*.proto")))
    if has_proto:
        if "proto" not in existing_targets:
            proposed.append({
                "target": "proto",
                "recipe": "protoc --go_out=. --go-grpc_out=. proto/*.proto",
                "deps": "",
                "description": "Compile protobuf definitions",
                "reason": ".proto files found",
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
            })

    return candidates


# ── npm Package Detection ─────────────────────────────────────────


def _detect_npm_package(package_json: Path, project_root: Path) -> dict | None:
    """Detect npm package candidate from package.json."""
    import json as _json

    try:
        data = _json.loads(package_json.read_text())
    except (OSError, _json.JSONDecodeError):
        return None

    name = data.get("name", project_root.name)
    version = data.get("version", "0.0.0")
    private = data.get("private", False)
    scripts = data.get("scripts", {})

    has_build = "build" in scripts
    has_npm = shutil.which("npm") is not None

    notes = []
    if not has_npm:
        notes.append("npm not found in PATH")
    if private:
        notes.append("Package is marked private — not publishable to npm registry")

    return {
        "name": f"npm-{name}",
        "kind": "package",
        "builder": "npm",
        "build_target": "build" if has_build else "",
        "build_cmd": "npm run build" if has_build else "npm pack",
        "output_dir": "dist/" if has_build else ".",
        "description": f"npm package: {name}@{version}",
        "detected_from": "package.json",
        "confidence": 0.9 if has_build else 0.7,
        "operability": "full" if has_npm else "blocked",
        "operability_notes": notes or ["npm available"],
        "remediation": "Install Node.js" if not has_npm else None,
    }


# ── Cargo / Rust Detection ────────────────────────────────────────


def _detect_cargo_package(cargo_toml: Path, project_root: Path) -> dict | None:
    """Detect Rust crate from Cargo.toml."""
    try:
        content = cargo_toml.read_text()
    except OSError:
        return None

    name = project_root.name
    version = "0.0.0"
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("name") and "=" in stripped:
            name = stripped.split("=", 1)[1].strip().strip('"\'')
        elif stripped.startswith("version") and "=" in stripped:
            version = stripped.split("=", 1)[1].strip().strip('"\'')

    has_cargo = shutil.which("cargo") is not None
    notes = []
    if not has_cargo:
        notes.append("cargo not found in PATH")

    return {
        "name": f"cargo-{name}",
        "kind": "package",
        "builder": "cargo",
        "build_target": "build",
        "build_cmd": "cargo build --release",
        "output_dir": "target/release/",
        "description": f"Rust crate: {name}@{version}",
        "detected_from": "Cargo.toml",
        "confidence": 0.9,
        "operability": "full" if has_cargo else "blocked",
        "operability_notes": notes or ["cargo available"],
        "remediation": "Install Rust toolchain (rustup)" if not has_cargo else None,
    }


# ── Go Module Detection ───────────────────────────────────────────


def _detect_go_module(go_mod: Path, project_root: Path) -> dict | None:
    """Detect Go module from go.mod."""
    try:
        content = go_mod.read_text()
    except OSError:
        return None

    module_path = project_root.name
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("module "):
            module_path = stripped.split(None, 1)[1].strip()
            break

    has_go = shutil.which("go") is not None
    # Check if there's a main package
    main_files = list(project_root.glob("cmd/**/main.go")) + list(project_root.glob("main.go"))
    has_main = len(main_files) > 0

    notes = []
    if not has_go:
        notes.append("go not found in PATH")
    if not has_main:
        notes.append("No main.go found — library module (publishes via git tags)")

    name = module_path.split("/")[-1] if "/" in module_path else module_path

    return {
        "name": f"go-{name}",
        "kind": "bundle" if has_main else "package",
        "builder": "go",
        "build_target": "build",
        "build_cmd": f"go build -o dist/{name} ./..." if has_main else "go build ./...",
        "output_dir": "dist/",
        "description": f"Go module: {module_path}",
        "detected_from": "go.mod",
        "confidence": 0.85 if has_main else 0.7,
        "operability": "full" if has_go else "blocked",
        "operability_notes": notes or ["go available"],
        "remediation": "Install Go" if not has_go else None,
    }


# ── Ruby Gem Detection ────────────────────────────────────────────


def _detect_ruby_gem(gemspec: Path, project_root: Path) -> dict | None:
    """Detect Ruby gem from *.gemspec."""
    try:
        content = gemspec.read_text()
    except OSError:
        return None

    name = gemspec.stem
    version = "0.0.0"
    # Basic gemspec parsing
    for line in content.splitlines():
        stripped = line.strip()
        if ".name" in stripped and "=" in stripped:
            parts = stripped.split("=", 1)[1].strip().strip('"\'')
            if parts:
                name = parts
        elif ".version" in stripped and "=" in stripped:
            val = stripped.split("=", 1)[1].strip().strip('"\'')
            if val and not val.startswith("$") and not val.startswith("("):
                version = val

    has_gem = shutil.which("gem") is not None
    notes = []
    if not has_gem:
        notes.append("gem not found in PATH")

    return {
        "name": f"gem-{name}",
        "kind": "package",
        "builder": "gem",
        "build_target": "build",
        "build_cmd": f"gem build {gemspec.name}",
        "output_dir": ".",
        "description": f"Ruby gem: {name}@{version}",
        "detected_from": gemspec.name,
        "confidence": 0.85,
        "operability": "full" if has_gem else "blocked",
        "operability_notes": notes or ["gem available"],
        "remediation": "Install Ruby" if not has_gem else None,
    }


# ── Java Package Detection ───────────────────────────────────────


def _detect_java_package(
    pom: Path, build_gradle: Path, build_gradle_kts: Path,
    project_root: Path,
) -> dict | None:
    """Detect Java package from pom.xml or build.gradle."""
    has_maven = shutil.which("mvn") is not None
    has_gradle = shutil.which("gradle") is not None

    if pom.exists():
        builder = "maven"
        build_cmd = "mvn package -DskipTests"
        output_dir = "target/"
        detected = "pom.xml"
    elif build_gradle.exists() or build_gradle_kts.exists():
        builder = "gradle"
        build_cmd = "gradle build -x test" if has_gradle else "./gradlew build -x test"
        output_dir = "build/libs/"
        detected = "build.gradle" + (".kts" if build_gradle_kts.exists() else "")
    else:
        return None

    name = project_root.name
    notes = []
    if builder == "maven" and not has_maven:
        notes.append("mvn not found in PATH")
    elif builder == "gradle" and not has_gradle:
        gradlew = project_root / "gradlew"
        if gradlew.exists():
            notes.append("Using gradle wrapper (./gradlew)")
        else:
            notes.append("gradle not found and no gradlew wrapper")

    operability = "full"
    if builder == "maven" and not has_maven:
        operability = "blocked"
    elif builder == "gradle" and not has_gradle and not (project_root / "gradlew").exists():
        operability = "blocked"

    return {
        "name": f"java-{name}",
        "kind": "package",
        "builder": builder,
        "build_target": "package" if builder == "maven" else "build",
        "build_cmd": build_cmd,
        "output_dir": output_dir,
        "description": f"Java package ({builder}): {name}",
        "detected_from": detected,
        "confidence": 0.85,
        "operability": operability,
        "operability_notes": notes or [f"{builder} available"],
        "remediation": f"Install {builder}" if operability == "blocked" else None,
    }


# ── .NET Package Detection ───────────────────────────────────────


def _detect_dotnet_package(csproj: Path, project_root: Path) -> dict | None:
    """Detect .NET package from *.csproj."""
    has_dotnet = shutil.which("dotnet") is not None
    name = csproj.stem

    notes = []
    if not has_dotnet:
        notes.append("dotnet not found in PATH")

    return {
        "name": f"dotnet-{name}",
        "kind": "package",
        "builder": "dotnet",
        "build_target": "publish",
        "build_cmd": f"dotnet publish -c Release -o dist/",
        "output_dir": "dist/",
        "description": f".NET package: {name}",
        "detected_from": csproj.name,
        "confidence": 0.85,
        "operability": "full" if has_dotnet else "blocked",
        "operability_notes": notes or ["dotnet available"],
        "remediation": "Install .NET SDK" if not has_dotnet else None,
    }


# ── Elixir Package Detection ─────────────────────────────────────


def _detect_elixir_package(mix_exs: Path, project_root: Path) -> dict | None:
    """Detect Elixir package from mix.exs."""
    has_mix = shutil.which("mix") is not None
    name = project_root.name

    try:
        content = mix_exs.read_text()
        for line in content.splitlines():
            if "app:" in line and ":" in line:
                parts = line.split(":", 2)
                if len(parts) >= 2:
                    val = parts[-1].strip().strip(",").strip(":").strip()
                    if val:
                        name = val
    except OSError:
        pass

    notes = []
    if not has_mix:
        notes.append("mix not found in PATH")

    return {
        "name": f"elixir-{name}",
        "kind": "package",
        "builder": "mix",
        "build_target": "compile",
        "build_cmd": "mix compile && mix release",
        "output_dir": "_build/prod/rel/",
        "description": f"Elixir package: {name}",
        "detected_from": "mix.exs",
        "confidence": 0.8,
        "operability": "full" if has_mix else "blocked",
        "operability_notes": notes or ["mix available"],
        "remediation": "Install Elixir" if not has_mix else None,
    }


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
