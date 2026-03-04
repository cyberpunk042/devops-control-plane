"""
Pipeline scanner — detect existing build infrastructure in a project.

When the control plane is installed into a project (``devops init``),
this module scans for existing build scripts, CI workflows, and
static site generators. The results pre-fill the Pages setup wizard.

Detection is local — the scanner reads the project's own files,
not remote repositories.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


# ── Data Models ─────────────────────────────────────────────────────


@dataclass
class DetectedScript:
    """A build script found in the project."""

    path: str                            # Relative to project root
    type: str                            # "shell", "python", "makefile", "npm"
    description: str = ""                # What we inferred it does
    flags: list[str] = field(default_factory=list)       # Parsed flags
    stages: list[dict] = field(default_factory=list)     # Detected stages
    operability: str = "unknown"         # "full", "partial", "unknown"
    operability_notes: list[str] = field(default_factory=list)
    remediation: dict = field(default_factory=dict)      # Auto-fix info


@dataclass
class DetectedFramework:
    """A static site framework found in the project."""

    name: str                            # "docusaurus", "hugo", "mkdocs", etc.
    config_path: str                     # Path to config file
    output_dir: str = ""                 # Build output directory
    build_cmd: str = ""                  # Build command
    preview_cmd: str = ""                # Dev server command
    preview_port: int = 0                # Dev server port
    version: str = ""                    # Framework version if detectable


@dataclass
class DetectedCI:
    """A CI workflow found in the project."""

    path: str                            # Relative path
    name: str                            # Workflow name
    provider: str = ""                   # "github-actions", "gitlab-ci", etc.
    build_script: str = ""               # The build command used
    env_vars: dict = field(default_factory=dict)  # Env vars found
    deploy_target: str = ""              # "github-pages", "s3", etc.


@dataclass
class PipelineScanResult:
    """Complete scan result for a project."""

    scripts: list[DetectedScript] = field(default_factory=list)
    frameworks: list[DetectedFramework] = field(default_factory=list)
    ci_workflows: list[DetectedCI] = field(default_factory=list)
    suggested_config: dict = field(default_factory=dict)
    compatibility: str = "unknown"       # "full", "partial", "manual"
    compatibility_notes: list[str] = field(default_factory=list)


# ── Scanner Entry Point ────────────────────────────────────────────


def scan_project_pipelines(project_root: Path) -> PipelineScanResult:
    """Scan a project for existing build pipelines.

    Args:
        project_root: The project root directory.

    Returns:
        PipelineScanResult with detected scripts, frameworks, CI,
        and suggested segment configuration.
    """
    result = PipelineScanResult()

    _scan_build_scripts(project_root, result)
    _scan_frameworks(project_root, result)
    _scan_ci_workflows(project_root, result)
    _build_suggestion(project_root, result)

    return result


# ── Build Script Detection ─────────────────────────────────────────


_SCRIPT_PATTERNS = [
    ("scripts/build_site.sh", "shell"),
    ("scripts/build.sh", "shell"),
    ("build.sh", "shell"),
    ("build_site.sh", "shell"),
    ("Makefile", "makefile"),
    ("makefile", "makefile"),
]


def _scan_build_scripts(root: Path, result: PipelineScanResult) -> None:
    """Detect build scripts in the project."""

    # Known script patterns
    for pattern, script_type in _SCRIPT_PATTERNS:
        path = root / pattern
        if path.is_file():
            script = _analyze_script(root, path, script_type)
            result.scripts.append(script)

    # Also scan for executable .sh files in scripts/
    scripts_dir = root / "scripts"
    if scripts_dir.is_dir():
        for sh_file in scripts_dir.glob("*.sh"):
            rel = str(sh_file.relative_to(root))
            # Skip if already found
            if any(s.path == rel for s in result.scripts):
                continue
            if sh_file.stat().st_mode & 0o111:  # Executable
                script = _analyze_script(root, sh_file, "shell")
                result.scripts.append(script)


def _analyze_script(
    root: Path, script_path: Path, script_type: str,
) -> DetectedScript:
    """Analyze a build script to understand its capabilities."""
    rel_path = str(script_path.relative_to(root))
    script = DetectedScript(path=rel_path, type=script_type)

    try:
        content = script_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return script

    if script_type == "shell":
        _analyze_shell_script(content, script)
    elif script_type == "makefile":
        _analyze_makefile(content, script)

    return script


def _analyze_shell_script(content: str, script: DetectedScript) -> None:
    """Parse a shell script for flags, stages, and operability signals."""

    # Extract description from header comments
    header_lines = []
    for line in content.splitlines()[:20]:
        if line.startswith("#") and not line.startswith("#!"):
            header_lines.append(line.lstrip("# ").strip())
    if header_lines:
        script.description = " ".join(
            l for l in header_lines[:3] if l
        )

    # Detect flags from case/getopts/argparse patterns
    flag_pattern = re.compile(r'--(\w[\w-]*)\)')
    for m in flag_pattern.finditer(content):
        flag = f"--{m.group(1)}"
        if flag not in script.flags:
            script.flags.append(flag)

    # Detect stages from step_start/step_end calls (high confidence)
    # These are real pipeline stages defined by the script author.
    step_start_pattern = re.compile(
        r'step_start\s+["\'](\w+)["\']'
    )
    seen_stages: set[str] = set()
    for m in step_start_pattern.finditer(content):
        stage_name = m.group(1)
        key = stage_name.lower()
        if key not in seen_stages:
            seen_stages.add(key)
            script.stages.append({
                "name": key,
                "label": stage_name,
                "detected": True,
            })

    # Only fall back to section headers if no step_start stages found.
    # Section headers (# === SECTION ===) are code organization, not
    # pipeline stages. Mixing them in produces noise.
    if not script.stages:
        section_pattern = re.compile(
            r'^#\s*Step\s*\d+\s*[:#]\s*(.+?)$', re.MULTILINE
        )
        for m in section_pattern.finditer(content):
            label = m.group(1).strip().strip("=").strip()
            if label and len(label) < 60:
                name = re.sub(r'[^a-z0-9]+', '_', label.lower()).strip('_')
                if name not in seen_stages:
                    seen_stages.add(name)
                    script.stages.append({
                        "name": name,
                        "label": label,
                        "detected": True,
                    })

    # Operability analysis
    notes = []
    remediation: dict = {}

    # Find the exact OUTPUT_DIR assignment line for remediation
    output_dir_line = None
    output_dir_lineno = 0
    output_dir_value = ""
    lines = content.splitlines()
    output_dir_re = re.compile(
        r'^\s*OUTPUT_DIR\s*=\s*["\']?(.+?)["\']?\s*$'
    )
    for i, line in enumerate(lines, 1):
        m = output_dir_re.match(line)
        if m:
            output_dir_line = line
            output_dir_lineno = i
            output_dir_value = m.group(1)
            break

    if "DEVOPS_OUTPUT_DIR" in content or "DEVOPS_" in content:
        script.operability = "full"
        notes.append("✅ Script reads DEVOPS_* environment variables")
        notes.append(
            "The control plane can pass DEVOPS_OUTPUT_DIR to redirect "
            "build output directly into the .pages/ workspace."
        )
    elif output_dir_line and (
        '${OUTPUT_DIR:-' in content or '${OUTPUT_DIR:=' in content
    ):
        # Uses OUTPUT_DIR with bash default — overridable but not DEVOPS-aware
        script.operability = "partial"
        notes.append(
            "⚠️ Script sets OUTPUT_DIR with a bash default — "
            "it can be overridden via environment, but the control "
            "plane needs DEVOPS_OUTPUT_DIR to be recognized."
        )
        proposed = f'OUTPUT_DIR="${{DEVOPS_OUTPUT_DIR:-{output_dir_value}}}"'
        notes.append(
            f"Fix: Change line {output_dir_lineno} to:\n"
            f"  {proposed}"
        )
        remediation = {
            "type": "replace_line",
            "line_number": output_dir_lineno,
            "current_line": output_dir_line,
            "proposed_line": proposed,
            "explanation": (
                f"Wraps the OUTPUT_DIR assignment with DEVOPS_OUTPUT_DIR. "
                f"When the control plane runs this script, it passes "
                f"DEVOPS_OUTPUT_DIR=.pages/<segment>/build so the output "
                f"goes directly into the workspace. When run standalone, "
                f"it falls back to the original value: {output_dir_value}"
            ),
        }
    elif output_dir_line:
        # Has OUTPUT_DIR= but hardcoded, no default syntax
        script.operability = "partial"
        proposed = f'OUTPUT_DIR="${{DEVOPS_OUTPUT_DIR:-{output_dir_value}}}"'
        notes.append(
            f"⚠️ Script sets OUTPUT_DIR on line {output_dir_lineno} "
            f"but it's hardcoded to: {output_dir_value}"
        )
        notes.append(
            f"The control plane can auto-patch this line to make it "
            f"accept DEVOPS_OUTPUT_DIR while keeping the current "
            f"default for standalone use."
        )
        remediation = {
            "type": "replace_line",
            "line_number": output_dir_lineno,
            "current_line": output_dir_line.rstrip(),
            "proposed_line": proposed,
            "explanation": (
                f"Wraps the existing OUTPUT_DIR assignment with "
                f"DEVOPS_OUTPUT_DIR. When the control plane runs "
                f"this script, it sets DEVOPS_OUTPUT_DIR=.pages/"
                f"<segment>/build so output goes directly into the "
                f"Pages workspace. When you run the script manually, "
                f"it falls back to the original: {output_dir_value}"
            ),
        }
    else:
        # No OUTPUT_DIR at all
        script.operability = "partial"
        notes.append(
            "⚠️ Script does not set OUTPUT_DIR. The control plane "
            "cannot redirect build output. It will run the script "
            "and then read from the configured source output directory."
        )

    if "set -e" in content:
        notes.append("✅ Script uses strict error handling (set -e)")
    if "set -o pipefail" in content:
        notes.append("✅ Script uses pipefail")

    script.operability_notes = notes
    script.remediation = remediation


def _analyze_makefile(content: str, script: DetectedScript) -> None:
    """Parse a Makefile for targets, operability, and output info."""
    target_pattern = re.compile(r'^(\w[\w-]*):', re.MULTILINE)
    targets = []
    for m in target_pattern.finditer(content):
        target = m.group(1)
        if target not in ('all', '.PHONY') and not target.startswith('.'):
            targets.append(target)

    if targets:
        script.description = f"Makefile with targets: {', '.join(targets[:10])}"
        # Present targets as invocable commands
        script.flags = [f"make {t}" for t in targets[:10]]
    else:
        script.description = "Makefile (no targets detected)"

    # Build-related targets become stages
    build_targets = [t for t in targets if t in (
        'build', 'install', 'clean', 'test', 'lint',
        'deploy', 'serve', 'dev', 'dist', 'package',
    )]
    for t in build_targets:
        script.stages.append({
            "name": t,
            "label": t.capitalize(),
            "detected": True,
        })

    # Operability analysis
    notes = []
    if "DEVOPS_OUTPUT_DIR" in content or "DEVOPS_" in content:
        script.operability = "full"
        notes.append("✅ Makefile reads DEVOPS_* environment variables")
    elif "OUTPUT_DIR" in content or "DESTDIR" in content:
        script.operability = "partial"
        notes.append(
            "⚠️ Makefile uses OUTPUT_DIR/DESTDIR — may be overridable "
            "via env. To be fully operable, add: "
            "OUTPUT_DIR ?= ${DEVOPS_OUTPUT_DIR}"
        )
    else:
        script.operability = "partial"
        notes.append(
            "⚠️ Makefile does not reference DEVOPS_* env vars. "
            "It will run, but output directory is not redirectable. "
            "Add: OUTPUT_DIR ?= ${DEVOPS_OUTPUT_DIR} to enable "
            "control-plane output redirection."
        )

    script.operability_notes = notes


# ── Framework Detection ─────────────────────────────────────────────


def _scan_frameworks(root: Path, result: PipelineScanResult) -> None:
    """Detect static site frameworks in the project."""

    # Docusaurus
    for config_name in ("docusaurus.config.ts", "docusaurus.config.js"):
        for candidate in _find_config(root, config_name):
            fw = _detect_docusaurus(root, candidate)
            if fw:
                result.frameworks.append(fw)

    # MkDocs
    mkdocs_yml = root / "mkdocs.yml"
    if mkdocs_yml.is_file():
        result.frameworks.append(DetectedFramework(
            name="mkdocs",
            config_path=str(mkdocs_yml.relative_to(root)),
            output_dir="site",
            build_cmd="mkdocs build",
            preview_cmd="mkdocs serve",
            preview_port=8000,
        ))

    # Hugo
    for hugo_config in ("hugo.toml", "hugo.yaml", "config.toml"):
        if (root / hugo_config).is_file():
            result.frameworks.append(DetectedFramework(
                name="hugo",
                config_path=hugo_config,
                output_dir="public",
                build_cmd="hugo",
                preview_cmd="hugo serve",
                preview_port=1313,
            ))
            break

    # Next.js
    next_config = root / "next.config.js"
    next_config_ts = root / "next.config.ts"
    next_config_mjs = root / "next.config.mjs"
    for nc in (next_config, next_config_ts, next_config_mjs):
        if nc.is_file():
            result.frameworks.append(DetectedFramework(
                name="nextjs",
                config_path=str(nc.relative_to(root)),
                output_dir="out" if _nextjs_is_static(nc) else ".next",
                build_cmd="npm run build",
                preview_cmd="npm run dev",
                preview_port=3000,
            ))
            break

    # Astro
    for astro_config in ("astro.config.mjs", "astro.config.ts"):
        if (root / astro_config).is_file():
            result.frameworks.append(DetectedFramework(
                name="astro",
                config_path=astro_config,
                output_dir="dist",
                build_cmd="npm run build",
                preview_cmd="npm run dev",
                preview_port=4321,
            ))
            break

    # Sphinx (conf.py in docs/)
    for conf_candidate in [root / "docs" / "conf.py", root / "conf.py"]:
        if conf_candidate.is_file():
            result.frameworks.append(DetectedFramework(
                name="sphinx",
                config_path=str(conf_candidate.relative_to(root)),
                output_dir="docs/_build/html",
                build_cmd="sphinx-build -b html docs docs/_build/html",
                preview_cmd="python -m http.server -d docs/_build/html",
                preview_port=8000,
            ))
            break

    # Jekyll (Gemfile with jekyll)
    gemfile = root / "Gemfile"
    if gemfile.is_file():
        try:
            content = gemfile.read_text(encoding="utf-8", errors="replace")
            if "jekyll" in content.lower():
                result.frameworks.append(DetectedFramework(
                    name="jekyll",
                    config_path="_config.yml",
                    output_dir="_site",
                    build_cmd="bundle exec jekyll build",
                    preview_cmd="bundle exec jekyll serve",
                    preview_port=4000,
                ))
        except Exception:
            pass


def _find_config(root: Path, name: str, max_depth: int = 2) -> list[Path]:
    """Find config files up to max_depth levels deep."""
    found = []
    if (root / name).is_file():
        found.append(root / name)
    for sub in root.iterdir():
        if sub.is_dir() and not sub.name.startswith(".") and sub.name != "node_modules":
            candidate = sub / name
            if candidate.is_file():
                found.append(candidate)
    return found


def _detect_docusaurus(root: Path, config_path: Path) -> DetectedFramework | None:
    """Detect Docusaurus from config file."""
    site_dir = config_path.parent
    rel = str(config_path.relative_to(root))

    # Check for package.json with docusaurus
    pkg_json = site_dir / "package.json"
    version = ""
    if pkg_json.is_file():
        try:
            pkg = json.loads(pkg_json.read_text(encoding="utf-8"))
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            if "@docusaurus/core" in deps:
                version = deps["@docusaurus/core"]
            elif "docusaurus" not in str(deps):
                return None  # Not a Docusaurus project
        except Exception:
            pass

    site_rel = str(site_dir.relative_to(root)) if site_dir != root else ""
    output_dir = f"{site_rel}/build" if site_rel else "build"
    build_cmd = f"cd {site_rel} && npm run build" if site_rel else "npm run build"
    preview_cmd = f"cd {site_rel} && npm run start" if site_rel else "npm run start"

    return DetectedFramework(
        name="docusaurus",
        config_path=rel,
        output_dir=output_dir,
        build_cmd=build_cmd,
        preview_cmd=preview_cmd,
        preview_port=3000,
        version=version,
    )


def _nextjs_is_static(config_path: Path) -> bool:
    """Check if Next.js is configured for static export."""
    try:
        content = config_path.read_text(encoding="utf-8", errors="replace")
        return "output:" in content and "'export'" in content
    except Exception:
        return False


# ── CI Workflow Detection ───────────────────────────────────────────


def _scan_ci_workflows(root: Path, result: PipelineScanResult) -> None:
    """Detect CI workflows."""

    # GitHub Actions
    gh_dir = root / ".github" / "workflows"
    if gh_dir.is_dir():
        for yml_file in gh_dir.glob("*.yml"):
            ci = _analyze_github_workflow(root, yml_file)
            if ci:
                result.ci_workflows.append(ci)
        for yaml_file in gh_dir.glob("*.yaml"):
            ci = _analyze_github_workflow(root, yaml_file)
            if ci:
                result.ci_workflows.append(ci)

    # GitLab CI
    gitlab_ci = root / ".gitlab-ci.yml"
    if gitlab_ci.is_file():
        result.ci_workflows.append(DetectedCI(
            path=".gitlab-ci.yml",
            name="GitLab CI",
            provider="gitlab-ci",
        ))


def _analyze_github_workflow(
    root: Path, yml_path: Path,
) -> DetectedCI | None:
    """Analyze a GitHub Actions workflow file."""
    try:
        content = yml_path.read_text(encoding="utf-8")
        data = yaml.safe_load(content)
        if not isinstance(data, dict):
            return None
    except Exception:
        return None

    name = data.get("name", yml_path.stem)
    rel = str(yml_path.relative_to(root))
    ci = DetectedCI(path=rel, name=name, provider="github-actions")

    # Find build commands and env vars in jobs
    jobs = data.get("jobs", {})
    for job_name, job_data in jobs.items():
        if not isinstance(job_data, dict):
            continue
        steps = job_data.get("steps", [])
        for step in steps:
            if not isinstance(step, dict):
                continue
            run_cmd = step.get("run", "")
            if isinstance(run_cmd, str) and (
                "build" in run_cmd.lower()
                or "deploy" in run_cmd.lower()
            ):
                if not ci.build_script:
                    ci.build_script = run_cmd.strip()

            # Collect env vars
            step_env = step.get("env", {})
            if isinstance(step_env, dict):
                ci.env_vars.update(step_env)

    # Detect deploy target
    for job_name, job_data in jobs.items():
        if not isinstance(job_data, dict):
            continue
        env_config = job_data.get("environment", {})
        if isinstance(env_config, dict) and "github-pages" in str(env_config):
            ci.deploy_target = "github-pages"

    return ci


# ── Suggestion Builder ──────────────────────────────────────────────


def _build_suggestion(root: Path, result: PipelineScanResult) -> None:
    """Build a suggested segment config from scan results."""

    if not result.scripts and not result.frameworks:
        return

    config: dict = {}
    notes: list[str] = []

    # Prefer a build script over raw framework commands
    # (the script likely wraps the framework with extra steps)
    primary_script = None
    for s in result.scripts:
        if "build" in s.path.lower():
            primary_script = s
            break
    if not primary_script and result.scripts:
        primary_script = result.scripts[0]

    primary_framework = result.frameworks[0] if result.frameworks else None

    if primary_script:
        if primary_script.type == "makefile":
            # Makefiles are invoked with make, not as executables
            build_target = "build" if any(
                s["name"] == "build" for s in primary_script.stages
            ) else ""
            config["build_cmd"] = f"make {build_target}".strip()
        else:
            config["build_cmd"] = f"./{primary_script.path}"
        config["build_cwd"] = "project_root"

        # Use framework output_dir if available
        if primary_framework:
            config["output_dir"] = primary_framework.output_dir
            config["framework"] = primary_framework.name
        else:
            config["output_dir"] = "build"

        # Pre-fill stages from script analysis
        if primary_script.stages:
            config["stages"] = primary_script.stages

        # Operability assessment
        if primary_script.operability == "full":
            result.compatibility = "full"
            notes.append(
                "✅ Build script is fully control-plane-operable. "
                "It reads DEVOPS_* environment variables."
            )
        elif primary_script.operability == "partial":
            result.compatibility = "partial"
            notes.append(
                "⚠️ Build script will run but cannot redirect output. "
                "The control plane will read from the configured output_dir."
            )
            notes.append(
                "💡 To make it fully operable, add to your script: "
                "OUTPUT_DIR=\"${DEVOPS_OUTPUT_DIR:-<current_default>}\""
            )
        else:
            result.compatibility = "manual"
            notes.append(
                f"⚠️ Could not determine operability of "
                f"{primary_script.path}. The script can still be "
                f"plugged, but output directory management requires "
                f"manual review. Check the script for OUTPUT_DIR or "
                f"DESTDIR variables."
            )

        # Preview from script flags or framework
        if primary_script.flags:
            serve_flags = [f for f in primary_script.flags
                           if "serve" in f or "dev" in f]
            if serve_flags:
                config["preview_cmd"] = (
                    f"./{primary_script.path} {serve_flags[0]}"
                )
        if not config.get("preview_cmd") and primary_framework:
            config["preview_cmd"] = primary_framework.preview_cmd
            config["preview_port"] = primary_framework.preview_port

    elif primary_framework:
        # No build script — use framework commands directly
        config["build_cmd"] = primary_framework.build_cmd
        config["output_dir"] = primary_framework.output_dir
        config["build_cwd"] = "project_root"
        config["preview_cmd"] = primary_framework.preview_cmd
        config["preview_port"] = primary_framework.preview_port
        config["framework"] = primary_framework.name
        result.compatibility = "full"
        notes.append(
            f"✅ Detected {primary_framework.name} — "
            f"using framework build commands directly."
        )

    # CI env vars
    for ci in result.ci_workflows:
        if ci.env_vars:
            env_lines = []
            for k, v in ci.env_vars.items():
                if isinstance(v, str) and not v.startswith("$"):
                    env_lines.append(f"{k}={v}")
            if env_lines:
                config["env_vars"] = "\n".join(env_lines)

    result.suggested_config = config
    result.compatibility_notes = notes
