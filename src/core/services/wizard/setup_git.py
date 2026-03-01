"""
Wizard setup — Git and GitHub configuration generation.

Handles git init, branch rename, .gitignore, remote setup,
hooks, initial commit, and GitHub environments / secrets / CODEOWNERS.

Channel-independent: no Flask or HTTP dependency.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def setup_git(root: Path, data: dict) -> dict:
    """Configure git: init, branch, .gitignore, remote, hooks, commit."""
    from src.core.services.devops import cache as devops_cache

    results: list[str] = []
    files_created: list[str] = []

    # 1. git init (if needed)
    if not (root / ".git").is_dir():
        subprocess.run(
            ["git", "init"], cwd=str(root),
            check=True, capture_output=True, timeout=10,
        )
        files_created.append(".git/")
        results.append("Repository initialized")

    # 2. Default branch rename (if requested and different)
    default_branch = data.get("default_branch", "").strip()
    if default_branch:
        r_cur = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=str(root), capture_output=True, timeout=5,
        )
        current = r_cur.stdout.decode().strip() if r_cur.returncode == 0 else ""
        if current and current != default_branch:
            subprocess.run(
                ["git", "branch", "-m", current, default_branch],
                cwd=str(root), capture_output=True, timeout=5,
            )
            results.append(f"Branch renamed: {current} → {default_branch}")

    # 3. Write .gitignore (generate from stacks or use provided content)
    gitignore_content = data.get("gitignore_content", "").strip()
    if not gitignore_content and data.get("generate_gitignore"):
        # Auto-generate from detected stacks
        from src.core.services.security_scan import generate_gitignore as _gen_gi
        try:
            from src.core.config.loader import load_project
            from src.core.config.stack_loader import discover_stacks
            from src.core.services.detection import detect_modules

            project = load_project(root / "project.yml")
            stacks = discover_stacks(root / "stacks")
            detection = detect_modules(project, root, stacks)
            stack_names = sorted(
                {m.effective_stack for m in detection.modules if m.effective_stack}
            )
        except Exception:
            stack_names = []
        if stack_names:
            gi_result = _gen_gi(root, stack_names)
            if gi_result.get("ok"):
                gitignore_content = gi_result["file"].get("content", "").strip()
    if gitignore_content:
        gi_path = root / ".gitignore"
        gi_path.write_text(gitignore_content + "\n", encoding="utf-8")
        files_created.append(".gitignore")
        pattern_count = sum(
            1 for line in gitignore_content.splitlines()
            if line.strip() and not line.strip().startswith("#")
        )
        results.append(f".gitignore created ({pattern_count} patterns)")

    # 4. Remote setup
    remote = data.get("remote", "").strip()
    if remote:
        subprocess.run(
            ["git", "remote", "remove", "origin"],
            cwd=str(root), capture_output=True, timeout=5,
        )
        subprocess.run(
            ["git", "remote", "add", "origin", remote],
            cwd=str(root), check=True,
            capture_output=True, timeout=5,
        )
        results.append(f"Remote set: origin → {remote}")

    # 5. Pre-commit hook (if requested)
    if data.get("setup_hooks"):
        hooks_dir = root / ".git" / "hooks"
        hooks_dir.mkdir(parents=True, exist_ok=True)
        hook_path = hooks_dir / "pre-commit"
        hook_cmds = data.get("hook_commands", [])
        if hook_cmds:
            hook_content = "#!/bin/sh\n# Auto-generated pre-commit hook\nset -e\n\n"
            for cmd in hook_cmds:
                hook_content += f'echo "→ Running {cmd}..."\n{cmd}\n\n'
            hook_path.write_text(hook_content, encoding="utf-8")
            hook_path.chmod(0o755)
            results.append(f"Pre-commit hook installed ({len(hook_cmds)} checks)")

    # 6. Initial commit (if requested)
    if data.get("create_initial_commit"):
        commit_msg = data.get("commit_message", "Initial commit").strip()
        subprocess.run(
            ["git", "add", "."],
            cwd=str(root), capture_output=True, timeout=10,
        )
        r_commit = subprocess.run(
            ["git", "commit", "-m", commit_msg],
            cwd=str(root), capture_output=True, timeout=10,
        )
        if r_commit.returncode == 0:
            r_hash = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=str(root), capture_output=True, timeout=5,
            )
            short_hash = r_hash.stdout.decode().strip() if r_hash.returncode == 0 else "?"
            results.append(f"Initial commit: {short_hash}")
        else:
            results.append("Initial commit skipped (nothing to commit)")

    devops_cache.record_event(
        root,
        label="💻 Git Setup",
        summary=f"Git configured: {', '.join(results) or 'no changes'}",
        detail={"results": results, "files_created": files_created},
        card="wizard",
        action="configured",
        target="git",
    )

    return {
        "ok": True,
        "message": "Git repository configured",
        "files_created": files_created,
        "results": results,
    }


def setup_github(root: Path, data: dict) -> dict:
    """Configure GitHub: environments, secrets, CODEOWNERS."""
    from src.core.services.devops import cache as devops_cache, secrets_ops

    results: dict = {
        "environments_created": [],
        "environments_failed": [],
        "secrets_pushed": 0,
        "codeowners_written": False,
    }

    # 1. Create deployment environments
    env_names = data.get("create_environments", [])
    for env_name in env_names:
        try:
            r = secrets_ops.create_environment(root, env_name)
            if r.get("success"):
                results["environments_created"].append(env_name)
            else:
                results["environments_failed"].append(
                    {"name": env_name, "error": r.get("error", "unknown")}
                )
        except Exception as exc:
            results["environments_failed"].append(
                {"name": env_name, "error": str(exc)}
            )

    # 2. Push secrets to GitHub (bulk)
    if data.get("push_secrets"):
        try:
            push_result = secrets_ops.push_secrets(
                root,
                push_to_github=True,
                save_to_env=False,
            )
            results["secrets_pushed"] = len(push_result.get("pushed", []))
        except Exception as exc:
            results["secrets_push_error"] = str(exc)

    # 3. Write CODEOWNERS (optional)
    codeowners_content = data.get("codeowners_content", "").strip()
    if codeowners_content:
        try:
            co_path = root / ".github" / "CODEOWNERS"
            co_path.parent.mkdir(parents=True, exist_ok=True)
            co_path.write_text(codeowners_content + "\n", encoding="utf-8")
            results["codeowners_written"] = True
        except Exception as exc:
            results["codeowners_error"] = str(exc)

    devops_cache.record_event(
        root,
        label="🐙 GitHub Setup",
        summary=(
            f"GitHub configured: "
            f"{len(results.get('environments_created', []))} env(s), "
            f"{results.get('secrets_pushed', 0)} secret(s)"
        ),
        detail=results,
        card="wizard",
        action="configured",
        target="github",
    )

    return {
        "ok": True,
        "message": "GitHub configuration applied",
        "results": results,
    }
