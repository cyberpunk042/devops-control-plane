"""
Integration routes — Git, GitHub, and CI/CD endpoints.

Blueprint: integrations_bp
Prefix: /api

Thin HTTP wrappers over ``src.core.services.git_ops``.

Endpoints:
    GET  /git/status          — branch, dirty state, ahead/behind
    GET  /git/log             — recent commit history
    POST /git/commit          — stage + commit
    POST /git/pull            — pull from remote
    POST /git/push            — push to remote
    GET  /gh/pulls            — open pull requests
    GET  /gh/actions/runs     — recent workflow runs
    POST /gh/actions/dispatch — trigger a workflow
"""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

from src.core.services import git_ops
from src.core.services.devops_cache import get_cached
from src.core.services.run_tracker import run_tracked

integrations_bp = Blueprint("integrations", __name__)


def _project_root() -> Path:
    return Path(current_app.config["PROJECT_ROOT"])


# ── Git Status ──────────────────────────────────────────────────────


@integrations_bp.route("/git/status")
def git_status():  # type: ignore[no-untyped-def]
    """Git repository status: branch, dirty files, ahead/behind tracking."""
    root = _project_root()
    force = request.args.get("bust", "") == "1"
    return jsonify(get_cached(
        root, "git",
        lambda: git_ops.git_status(root),
        force=force,
    ))


# ── Git Log ─────────────────────────────────────────────────────────


@integrations_bp.route("/git/log")
def git_log():  # type: ignore[no-untyped-def]
    """Recent commit history."""
    n = request.args.get("n", 10, type=int)
    return jsonify(git_ops.git_log(_project_root(), n=n))


# ── Git Commit ──────────────────────────────────────────────────────


@integrations_bp.route("/git/commit", methods=["POST"])
@run_tracked("git", "git:commit")
def git_commit():  # type: ignore[no-untyped-def]
    """Stage and commit changes.

    JSON body:
        message: commit message (required)
        files: optional list of files to stage (default: all)
    """
    data = request.get_json(silent=True) or {}
    message = data.get("message", "").strip()
    if not message:
        return jsonify({"error": "Commit message is required"}), 400

    files = data.get("files")
    result = git_ops.git_commit(_project_root(), message, files=files)

    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


# ── Git Pull ────────────────────────────────────────────────────────


@integrations_bp.route("/git/pull", methods=["POST"])
@run_tracked("git", "git:pull")
def git_pull():  # type: ignore[no-untyped-def]
    """Pull from remote."""
    data = request.get_json(silent=True) or {}
    rebase = data.get("rebase", False)

    result = git_ops.git_pull(_project_root(), rebase=rebase)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


# ── Git Push ────────────────────────────────────────────────────────


@integrations_bp.route("/git/push", methods=["POST"])
@run_tracked("git", "git:push")
def git_push():  # type: ignore[no-untyped-def]
    """Push to remote."""
    data = request.get_json(silent=True) or {}
    force = data.get("force", False)

    result = git_ops.git_push(_project_root(), force=force)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


# ── GitHub: Status ──────────────────────────────────────────────────


# ── Terminal Emulator Status ────────────────────────────────────────


@integrations_bp.route("/ops/terminal/status")
def ops_terminal_status():  # type: ignore[no-untyped-def]
    """Terminal emulator availability — working, broken, installable."""
    from src.core.services.terminal_ops import terminal_status
    return jsonify(terminal_status())


@integrations_bp.route("/integrations/gh/status")
def gh_status_extended():  # type: ignore[no-untyped-def]
    """Extended GitHub status — version, repo, auth details."""
    root = _project_root()
    force = request.args.get("bust", "") == "1"
    return jsonify(get_cached(
        root, "github",
        lambda: git_ops.gh_status(root),
        force=force,
    ))


# ── GitHub: Pull Requests ───────────────────────────────────────────


@integrations_bp.route("/gh/pulls")
def gh_pulls():  # type: ignore[no-untyped-def]
    """List open pull requests."""
    root = _project_root()
    force = request.args.get("bust", "") == "1"
    return jsonify(get_cached(
        root, "gh-pulls",
        lambda: git_ops.gh_pulls(root),
        force=force,
    ))


# ── GitHub: Actions ─────────────────────────────────────────────────


@integrations_bp.route("/gh/actions/runs")
def gh_actions_runs():  # type: ignore[no-untyped-def]
    """Recent workflow run history."""
    root = _project_root()
    n = request.args.get("n", 10, type=int)
    force = request.args.get("bust", "") == "1"
    return jsonify(get_cached(
        root, "gh-runs",
        lambda: git_ops.gh_actions_runs(root, n=n),
        force=force,
    ))


@integrations_bp.route("/gh/actions/dispatch", methods=["POST"])
@run_tracked("ci", "ci:gh_dispatch")
def gh_actions_dispatch():  # type: ignore[no-untyped-def]
    """Trigger a workflow via repository dispatch."""
    data = request.get_json(silent=True) or {}
    workflow = data.get("workflow", "")
    if not workflow:
        return jsonify({"error": "Missing 'workflow' field"}), 400

    ref = data.get("ref")
    result = git_ops.gh_actions_dispatch(_project_root(), workflow, ref=ref)

    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


# ── GitHub: Workflows list ──────────────────────────────────────────


@integrations_bp.route("/gh/actions/workflows")
def gh_actions_workflows():  # type: ignore[no-untyped-def]
    """List available workflows."""
    root = _project_root()
    force = request.args.get("bust", "") == "1"
    return jsonify(get_cached(
        root, "gh-workflows",
        lambda: git_ops.gh_actions_workflows(root),
        force=force,
    ))


# ── GitHub: User ────────────────────────────────────────────────────


@integrations_bp.route("/gh/user")
def gh_user():  # type: ignore[no-untyped-def]
    """Currently authenticated GitHub user."""
    return jsonify(git_ops.gh_user(_project_root()))


# ── GitHub: Repo Info ───────────────────────────────────────────────


@integrations_bp.route("/gh/repo/info")
def gh_repo_info():  # type: ignore[no-untyped-def]
    """Detailed repository information (visibility, description, etc)."""
    return jsonify(git_ops.gh_repo_info(_project_root()))


# ── GitHub: Auth Logout ─────────────────────────────────────────────


@integrations_bp.route("/gh/auth/logout", methods=["POST"])
@run_tracked("setup", "setup:gh_logout")
def gh_auth_logout():  # type: ignore[no-untyped-def]
    """Logout from GitHub CLI."""
    result = git_ops.gh_auth_logout(_project_root())
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


# ── GitHub: Auth Login ──────────────────────────────────────────────


@integrations_bp.route("/gh/auth/login", methods=["POST"])
@run_tracked("setup", "setup:gh_login")
def gh_auth_login():  # type: ignore[no-untyped-def]
    """Authenticate with GitHub CLI.

    Body (JSON):
        {"token": "ghp_…"}          → token mode (non-interactive)
        {"mode": "interactive"}     → spawn terminal for OAuth
        {} (empty)                  → spawn terminal for OAuth
    """
    data = request.get_json(silent=True) or {}
    token = data.get("token", "").strip()
    auto_drive = bool(data.get("auto_drive", False))

    result = git_ops.gh_auth_login(
        _project_root(),
        token=token,
        auto_drive=auto_drive,
    )

    # Cache-bust on successful token auth so status is fresh
    if result.get("ok") and result.get("authenticated"):
        try:
            from src.core.services import devops_cache
            root = _project_root()
            devops_cache.invalidate(root, "github")
            devops_cache.invalidate(root, "wiz:detect")
        except Exception:
            pass

    # Determine HTTP status:
    #  - 200 for success, terminal spawned, no_terminal (actionable), or fallback
    #  - 400 for actual errors (bad token, gh not installed, etc.)
    if result.get("ok") or result.get("no_terminal") or result.get("fallback"):
        status = 200
    else:
        status = 400
    return jsonify(result), status


# ── GitHub: Auth Token (auto-detect) ────────────────────────────────


@integrations_bp.route("/gh/auth/token")
def gh_auth_token_route():  # type: ignore[no-untyped-def]
    """Extract current auth token from gh CLI (for auto-detection)."""
    result = git_ops.gh_auth_token(_project_root())
    status = 200 if result.get("ok") else 400
    return jsonify(result), status


# ── GitHub: Device Flow Auth (browser-based) ────────────────────────


@integrations_bp.route("/gh/auth/device", methods=["POST"])
@run_tracked("setup", "setup:gh_device_flow")
def gh_auth_device_start_route():  # type: ignore[no-untyped-def]
    """Start a GitHub device flow — returns one-time code + URL."""
    result = git_ops.gh_auth_device_start(_project_root())
    status = 200 if result.get("ok") else 400
    return jsonify(result), status


@integrations_bp.route("/gh/auth/device/poll")
def gh_auth_device_poll_route():  # type: ignore[no-untyped-def]
    """Poll a device flow session for completion."""
    session_id = request.args.get("session", "").strip()
    if not session_id:
        return jsonify({"error": "session parameter required"}), 400

    root = _project_root()
    result = git_ops.gh_auth_device_poll(session_id, root)

    # Cache-bust on successful auth — only the github card
    if result.get("complete") and result.get("authenticated"):
        try:
            from src.core.services import devops_cache
            devops_cache.invalidate(root, "github")
            devops_cache.invalidate(root, "wiz:detect")
        except Exception:
            pass

    return jsonify(result)


@integrations_bp.route("/gh/auth/terminal/poll")
def gh_auth_terminal_poll_route():  # type: ignore[no-untyped-def]
    """Poll signal file for terminal auth progress.

    Reads ``.state/.gh-auth-result`` written by the auto-drive bash
    script.  Returns the JSON from the file, which contains:

    - ``{"status": "running"}``  — script started
    - ``{"status": "code_ready", "code": "XXXX-XXXX", "url": "..."}``
    - ``{"status": "success"}``  — auth completed
    - ``{"status": "failed"}``   — auth failed
    """
    import json as _json

    import tempfile

    signal_file = Path(tempfile.gettempdir()) / ".gh-auth-result"

    if not signal_file.exists():
        return jsonify({"status": "unknown"})

    try:
        data = _json.loads(signal_file.read_text())

        # If success, bust cache
        if data.get("status") == "success":
            try:
                from src.core.services import devops_cache
                devops_cache.invalidate(root, "github")
                devops_cache.invalidate(root, "wiz:detect")
            except Exception:
                pass
            return jsonify(data)

        # If stuck at code_ready, check live gh auth status
        if data.get("status") == "code_ready":
            import subprocess
            gh_rc = -999
            gh_err = ""
            try:
                result = subprocess.run(
                    ["gh", "auth", "status"],
                    capture_output=True, text=True, timeout=5,
                )
                gh_rc = result.returncode
                gh_err = result.stderr[:200] if result.stderr else ""
                if gh_rc == 0:
                    # Auth succeeded! Update signal file + bust cache
                    data = {"status": "success", "ts": data.get("ts", "")}
                    signal_file.write_text(_json.dumps(data))
                    try:
                        from src.core.services import devops_cache
                        devops_cache.invalidate(root, "github")
                        devops_cache.invalidate(root, "wiz:detect")
                    except Exception:
                        pass
                    return jsonify(data)
            except Exception as exc:
                gh_err = str(exc)
            # Include debug info so we can see in network tab
            data["_debug_gh_rc"] = gh_rc
            data["_debug_gh_err"] = gh_err

        return jsonify(data)
    except Exception:
        return jsonify({"status": "unknown"})


# ── GitHub: Create Repository ───────────────────────────────────────


@integrations_bp.route("/gh/repo/create", methods=["POST"])
@run_tracked("setup", "setup:gh_repo")
def gh_repo_create():  # type: ignore[no-untyped-def]
    """Create a new GitHub repository."""
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "Repository name is required"}), 400

    result = git_ops.gh_repo_create(
        _project_root(),
        name,
        private=data.get("private", True),
        description=data.get("description", ""),
        add_remote=data.get("add_remote", True),
    )
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


# ── GitHub: Set Visibility ──────────────────────────────────────────


@integrations_bp.route("/gh/repo/visibility", methods=["POST"])
@run_tracked("setup", "setup:gh_visibility")
def gh_repo_set_visibility():  # type: ignore[no-untyped-def]
    """Change repository visibility (public/private)."""
    data = request.get_json(silent=True) or {}
    visibility = data.get("visibility", "").strip()
    if not visibility:
        return jsonify({"error": "Missing 'visibility' field"}), 400

    result = git_ops.gh_repo_set_visibility(_project_root(), visibility)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


# ── Git: Remotes Management ─────────────────────────────────────────


@integrations_bp.route("/git/remotes")
def git_remotes():  # type: ignore[no-untyped-def]
    """List all git remotes with their URLs."""
    return jsonify(git_ops.git_remotes(_project_root()))


@integrations_bp.route("/git/remote/add", methods=["POST"])
@run_tracked("setup", "setup:git_remote")
def git_remote_add():  # type: ignore[no-untyped-def]
    """Add a new git remote."""
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    url = data.get("url", "").strip()
    if not name or not url:
        return jsonify({"error": "Both 'name' and 'url' are required"}), 400
    result = git_ops.git_remote_add(_project_root(), name, url)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@integrations_bp.route("/git/remote/remove", methods=["POST"])
@run_tracked("destroy", "destroy:git_remote")
def git_remote_remove():  # type: ignore[no-untyped-def]
    """Remove a git remote by name (defaults to origin)."""
    data = request.get_json(silent=True) or {}
    name = data.get("name", "origin").strip()
    result = git_ops.git_remote_remove(_project_root(), name)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@integrations_bp.route("/git/remote/rename", methods=["POST"])
@run_tracked("setup", "setup:git_remote_rename")
def git_remote_rename():  # type: ignore[no-untyped-def]
    """Rename a git remote."""
    data = request.get_json(silent=True) or {}
    old = data.get("old_name", "").strip()
    new = data.get("new_name", "").strip()
    if not old or not new:
        return jsonify({"error": "Both 'old_name' and 'new_name' are required"}), 400
    result = git_ops.git_remote_rename(_project_root(), old, new)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@integrations_bp.route("/git/remote/set-url", methods=["POST"])
@run_tracked("setup", "setup:git_remote_url")
def git_remote_set_url():  # type: ignore[no-untyped-def]
    """Change the URL of a git remote."""
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    url = data.get("url", "").strip()
    if not name or not url:
        return jsonify({"error": "Both 'name' and 'url' are required"}), 400
    result = git_ops.git_remote_set_url(_project_root(), name, url)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


# ── GitHub: Default Branch ──────────────────────────────────────────


@integrations_bp.route("/gh/repo/default-branch", methods=["POST"])
@run_tracked("setup", "setup:gh_default_branch")
def gh_repo_set_default_branch():  # type: ignore[no-untyped-def]
    """Change the default branch on GitHub."""
    data = request.get_json(silent=True) or {}
    branch = data.get("branch", "").strip()
    if not branch:
        return jsonify({"error": "Missing 'branch' field"}), 400
    result = git_ops.gh_repo_set_default_branch(_project_root(), branch)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)

