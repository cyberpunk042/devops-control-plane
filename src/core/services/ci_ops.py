"""
CI/CD operations — channel-independent service.

Provides CI provider detection, workflow file parsing, coverage
analysis (which modules have CI, which don't), and workflow
generation without any Flask or HTTP dependency.

Does NOT duplicate runtime GitHub Actions operations already in
``git_ops.py`` (runs, dispatch, workflows). This module focuses
on static analysis and generation of CI configuration.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


from src.core.services.audit_helpers import make_auditor

_audit = make_auditor("ci")


def _auto_detect_modules(project_root: Path) -> list[dict]:
    """Load project config and detect modules."""
    from src.core.config.loader import load_project
    from src.core.config.stack_loader import discover_stacks
    from src.core.services.detection import detect_modules

    project = load_project(project_root / "project.yml")
    stacks = discover_stacks(project_root / "stacks")
    detection = detect_modules(project, project_root, stacks)
    return [m.model_dump() for m in detection.modules]


def _auto_detect_stack_names(project_root: Path) -> tuple[list[str], str]:
    """Return (unique_stack_names, project_name) from auto-detected modules."""
    from src.core.config.loader import load_project

    modules = _auto_detect_modules(project_root)
    seen: set[str] = set()
    names: list[str] = []
    for m in modules:
        stack = m.get("effective_stack", m.get("stack_name", ""))
        if stack and stack not in seen:
            names.append(stack)
            seen.add(stack)

    project = load_project(project_root / "project.yml")
    return names, project.name


# CI providers we can detect
_CI_PROVIDERS = {
    "github_actions": {
        "name": "GitHub Actions",
        "paths": [".github/workflows"],
        "extensions": [".yml", ".yaml"],
    },
    "gitlab_ci": {
        "name": "GitLab CI",
        "files": [".gitlab-ci.yml", ".gitlab-ci.yaml"],
    },
    "jenkins": {
        "name": "Jenkins",
        "files": ["Jenkinsfile"],
    },
    "circleci": {
        "name": "CircleCI",
        "paths": [".circleci"],
    },
    "travis": {
        "name": "Travis CI",
        "files": [".travis.yml"],
    },
    "azure_pipelines": {
        "name": "Azure Pipelines",
        "files": ["azure-pipelines.yml", "azure-pipelines.yaml"],
    },
    "bitbucket_pipelines": {
        "name": "Bitbucket Pipelines",
        "files": ["bitbucket-pipelines.yml"],
    },
}


# ═══════════════════════════════════════════════════════════════════
#  Detect
# ═══════════════════════════════════════════════════════════════════


def ci_status(project_root: Path) -> dict:
    """CI/CD integration status: detected providers, workflow count.

    Returns:
        {
            "providers": [{"id": str, "name": str, "workflows": int}, ...],
            "total_workflows": int,
            "has_ci": bool,
        }
    """
    providers = []
    total = 0

    for provider_id, spec in _CI_PROVIDERS.items():
        detected = False
        workflow_count = 0

        # Check for specific files
        for f in spec.get("files", []):
            if (project_root / f).is_file():
                detected = True
                workflow_count += 1

        # Check for workflow directories
        for p in spec.get("paths", []):
            wf_dir = project_root / p
            if wf_dir.is_dir():
                detected = True
                exts = spec.get("extensions", [".yml", ".yaml"])
                for f in wf_dir.iterdir():
                    if f.is_file() and f.suffix in exts:
                        workflow_count += 1

        if detected:
            providers.append({
                "id": provider_id,
                "name": spec["name"],
                "workflows": workflow_count,
            })
            total += workflow_count

    return {
        "providers": providers,
        "total_workflows": total,
        "has_ci": len(providers) > 0,
    }


# ═══════════════════════════════════════════════════════════════════
#  Observe
# ═══════════════════════════════════════════════════════════════════


def _parse_yaml_safe(path: Path) -> dict | None:
    """Parse a YAML file, returning None on failure."""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        logger.debug("Failed to parse YAML: %s", path, exc_info=True)
        return None


def ci_workflows(project_root: Path) -> dict:
    """Parse and list all CI workflow files with their structure.

    Returns:
        {
            "workflows": [{
                "file": str,
                "provider": str,
                "name": str,
                "triggers": [str, ...],
                "jobs": [{name, steps_count, runs_on}, ...],
                "issues": [str, ...],
            }, ...],
        }
    """
    workflows: list[dict] = []

    # GitHub Actions
    gha_dir = project_root / ".github" / "workflows"
    if gha_dir.is_dir():
        for f in sorted(gha_dir.iterdir()):
            if not f.is_file() or f.suffix not in (".yml", ".yaml"):
                continue
            wf = _parse_github_workflow(f, project_root)
            if wf:
                workflows.append(wf)

    # GitLab CI
    for name in (".gitlab-ci.yml", ".gitlab-ci.yaml"):
        gl_file = project_root / name
        if gl_file.is_file():
            wf = _parse_gitlab_ci(gl_file, project_root)
            if wf:
                workflows.append(wf)

    # Jenkinsfile (limited parsing)
    jf = project_root / "Jenkinsfile"
    if jf.is_file():
        workflows.append({
            "file": "Jenkinsfile",
            "provider": "jenkins",
            "name": "Jenkinsfile",
            "triggers": ["push"],
            "jobs": [],
            "issues": [],
        })

    return {"workflows": workflows}


def _parse_github_workflow(path: Path, project_root: Path) -> dict | None:
    """Parse a single GitHub Actions workflow file."""
    data = _parse_yaml_safe(path)
    if not data:
        return {
            "file": str(path.relative_to(project_root)),
            "provider": "github_actions",
            "name": path.stem,
            "triggers": [],
            "jobs": [],
            "issues": ["Failed to parse YAML"],
        }

    name = data.get("name", path.stem)
    rel_path = str(path.relative_to(project_root))

    # Parse triggers
    triggers = []
    on_block = data.get("on", data.get(True, {}))  # YAML parses `on:` as True
    if isinstance(on_block, list):
        triggers = on_block
    elif isinstance(on_block, dict):
        triggers = list(on_block.keys())
    elif isinstance(on_block, str):
        triggers = [on_block]

    # Parse jobs
    jobs = []
    jobs_block = data.get("jobs", {})
    if isinstance(jobs_block, dict):
        for job_id, job_data in jobs_block.items():
            if not isinstance(job_data, dict):
                continue
            steps = job_data.get("steps", [])
            jobs.append({
                "id": job_id,
                "name": job_data.get("name", job_id),
                "runs_on": job_data.get("runs-on", "?"),
                "steps_count": len(steps) if isinstance(steps, list) else 0,
                "needs": job_data.get("needs", []),
            })

    # Detect issues
    issues = _audit_github_workflow(data, path)

    return {
        "file": rel_path,
        "provider": "github_actions",
        "name": name,
        "triggers": triggers,
        "jobs": jobs,
        "issues": issues,
    }


def _audit_github_workflow(data: dict, path: Path) -> list[str]:
    """Detect common issues in a GitHub Actions workflow."""
    issues: list[str] = []

    jobs_block = data.get("jobs", {})
    if not jobs_block:
        issues.append("No jobs defined")
        return issues

    for job_id, job_data in jobs_block.items():
        if not isinstance(job_data, dict):
            continue

        steps = job_data.get("steps", [])
        if not isinstance(steps, list) or not steps:
            issues.append(f"Job '{job_id}' has no steps")
            continue

        for i, step in enumerate(steps):
            if not isinstance(step, dict):
                continue

            # Empty run commands
            run_cmd = step.get("run", "")
            if isinstance(run_cmd, str):
                stripped = run_cmd.strip()
                # Remove comments
                lines = [ln for ln in stripped.splitlines()
                         if ln.strip() and not ln.strip().startswith("#")]
                if not lines and "run" in step:
                    issues.append(
                        f"Job '{job_id}', step {i + 1} "
                        f"('{step.get('name', '?')}'): empty run command"
                    )

            # Pinned actions check
            uses = step.get("uses", "")
            if isinstance(uses, str) and uses and "@" not in uses:
                issues.append(
                    f"Job '{job_id}', step {i + 1}: action '{uses}' not pinned to version"
                )

    return issues


def _parse_gitlab_ci(path: Path, project_root: Path) -> dict | None:
    """Parse a GitLab CI file."""
    data = _parse_yaml_safe(path)
    if not data:
        return {
            "file": str(path.relative_to(project_root)),
            "provider": "gitlab_ci",
            "name": ".gitlab-ci",
            "triggers": [],
            "jobs": [],
            "issues": ["Failed to parse YAML"],
        }

    jobs = []
    # In GitLab CI, top-level keys that don't start with . are jobs
    for key, val in data.items():
        if key.startswith(".") or key in (
            "stages", "variables", "include", "default", "image",
            "before_script", "after_script", "workflow", "cache", "services",
        ):
            continue
        if isinstance(val, dict):
            jobs.append({
                "id": key,
                "name": key,
                "stage": val.get("stage", "?"),
                "steps_count": len(val.get("script", [])),
            })

    return {
        "file": str(path.relative_to(project_root)),
        "provider": "gitlab_ci",
        "name": data.get("stages", [".gitlab-ci"])[0] if data.get("stages") else ".gitlab-ci",
        "triggers": ["push"],
        "jobs": jobs,
        "issues": [],
    }


def ci_coverage(project_root: Path, modules: list[dict] | None = None) -> dict:
    """Analyze which modules have CI coverage.

    Reads workflow files and checks if module paths or stack-related
    commands appear in CI steps.

    Args:
        modules: List of module dicts with 'name', 'path', 'stack_name'.

    Returns:
        {
            "covered": [module_name, ...],
            "uncovered": [module_name, ...],
            "coverage_pct": float,
            "details": {module_name: {covered: bool, reason: str}, ...},
        }
    """
    if modules is None:
        modules = _auto_detect_modules(project_root)

    # Gather all CI file content
    ci_content = _gather_ci_content(project_root)

    covered = []
    uncovered = []
    details: dict[str, dict] = {}

    for mod in modules:
        name = mod.get("name", "")
        path = mod.get("path", "")
        stack = mod.get("effective_stack", mod.get("stack_name", ""))

        if not name:
            continue

        # Check if module path or name appears in CI files
        is_covered = False
        reason = "Not referenced in any CI workflow"

        if ci_content:
            # Direct path reference
            if path and path in ci_content:
                is_covered = True
                reason = f"Path '{path}' referenced in CI"

            # Module name reference
            elif name in ci_content:
                is_covered = True
                reason = f"Module '{name}' referenced in CI"

            # Stack-based coverage (e.g. pytest covers all python modules)
            elif stack:
                stack_covered = _check_stack_coverage(stack, ci_content)
                if stack_covered:
                    is_covered = True
                    reason = f"Stack '{stack}' has CI coverage via {stack_covered}"

        if is_covered:
            covered.append(name)
        else:
            uncovered.append(name)

        details[name] = {"covered": is_covered, "reason": reason}

    total = len(covered) + len(uncovered)
    pct = (len(covered) / total * 100) if total > 0 else 0.0

    return {
        "covered": covered,
        "uncovered": uncovered,
        "coverage_pct": round(pct, 1),
        "details": details,
    }


def _gather_ci_content(project_root: Path) -> str:
    """Concatenate all CI file contents for simple text search."""
    parts: list[str] = []

    gha_dir = project_root / ".github" / "workflows"
    if gha_dir.is_dir():
        for f in gha_dir.iterdir():
            if f.is_file() and f.suffix in (".yml", ".yaml"):
                try:
                    parts.append(f.read_text(encoding="utf-8"))
                except OSError:
                    pass

    for name in (".gitlab-ci.yml", ".gitlab-ci.yaml"):
        p = project_root / name
        if p.is_file():
            try:
                parts.append(p.read_text(encoding="utf-8"))
            except OSError:
                pass

    jf = project_root / "Jenkinsfile"
    if jf.is_file():
        try:
            parts.append(jf.read_text(encoding="utf-8"))
        except OSError:
            pass

    return "\n".join(parts)


# Stack → CI tool mappings for coverage detection
_STACK_CI_MARKERS: dict[str, list[str]] = {
    "python": ["pytest", "ruff", "mypy", "pip install", "python -m"],
    "node": ["npm test", "npm run", "yarn test", "jest", "vitest"],
    "typescript": ["npm test", "tsc", "jest", "vitest"],
    "go": ["go test", "go vet", "golangci-lint"],
    "rust": ["cargo test", "cargo clippy", "cargo check"],
    "java": ["mvn test", "gradle test", "maven", "gradle"],
    "dotnet": ["dotnet test", "dotnet build"],
    "elixir": ["mix test"],
    "ruby": ["bundle exec", "rspec", "rake test"],
}


def _check_stack_coverage(stack_name: str, ci_content: str) -> str | None:
    """Check if CI content includes commands for a given stack."""
    # Exact match
    markers = _STACK_CI_MARKERS.get(stack_name, [])
    for marker in markers:
        if marker in ci_content:
            return marker

    # Prefix match
    for prefix, markers in _STACK_CI_MARKERS.items():
        if stack_name.startswith(prefix + "-") or stack_name.startswith(prefix):
            for marker in markers:
                if marker in ci_content:
                    return marker

    return None


# ═══════════════════════════════════════════════════════════════════
#  Facilitate (generate)
# ═══════════════════════════════════════════════════════════════════


def generate_ci_workflow(
    project_root: Path,
    stack_names: list[str] | None = None,
    *,
    project_name: str = "",
) -> dict:
    """Generate a GitHub Actions CI workflow from detected stacks.

    If *stack_names* is not provided, auto-detects from project config.

    Returns:
        {"ok": True, "file": {...}} or {"error": "..."}
    """
    if stack_names is None or not project_name:
        detected_names, detected_project = _auto_detect_stack_names(project_root)
        if stack_names is None:
            stack_names = detected_names
        if not project_name:
            project_name = detected_project

    from src.core.services.generators.github_workflow import generate_ci

    result = generate_ci(project_root, stack_names, project_name=project_name)
    if result is None:
        return {"error": "No CI template available for detected stacks"}

    _audit(
        "⚙️ CI Workflow Generated",
        f"CI workflow generated ({len(stack_names)} stack(s))",
        action="generated",
        target="ci-workflow",
        detail={"stacks": stack_names, "project": project_name},
    )
    return {"ok": True, "file": result.model_dump()}


def generate_lint_workflow(
    project_root: Path,
    stack_names: list[str] | None = None,
) -> dict:
    """Generate a GitHub Actions lint workflow.

    If *stack_names* is not provided, auto-detects from project config.

    Returns:
        {"ok": True, "file": {...}} or {"error": "..."}
    """
    if stack_names is None:
        stack_names, _ = _auto_detect_stack_names(project_root)

    from src.core.services.generators.github_workflow import generate_lint

    result = generate_lint(project_root, stack_names)
    if result is None:
        return {"error": "No lint template for detected stacks"}

    _audit(
        "⚙️ Lint Workflow Generated",
        f"Lint workflow generated ({len(stack_names)} stack(s))",
        action="generated",
        target="lint-workflow",
        detail={"stacks": stack_names},
    )
    return {"ok": True, "file": result.model_dump()}


def generate_terraform_workflow(
    terraform_config: dict,
    *,
    project_name: str = "",
) -> dict:
    """Generate a GitHub Actions Terraform CI workflow.

    Args:
        terraform_config: Dict with provider, working_directory,
            workspaces, project_name.
        project_name: Optional project name for workflow naming.

    Returns:
        {"ok": True, "file": {...}} or {"error": "..."}
    """
    from src.core.services.generators.github_workflow import generate_terraform_ci

    result = generate_terraform_ci(terraform_config, project_name=project_name)
    if result is None:
        return {"error": "Failed to generate Terraform CI workflow"}

    provider = terraform_config.get("provider", "unknown")
    _audit(
        "⚙️ Terraform CI Workflow Generated",
        f"Terraform CI workflow generated (provider={provider})",
        action="generated",
        target="terraform-ci-workflow",
        detail={"provider": provider, "project": project_name},
    )
    return {"ok": True, "file": result.model_dump()}

