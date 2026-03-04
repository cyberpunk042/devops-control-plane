"""Git operations — status, log, diff, commit, pull, push, stash, merge."""

from __future__ import annotations

from flask import jsonify, request

from src.core.services import git_ops
from src.core.services.devops.cache import get_cached
from src.core.services.run_tracker import run_tracked
from src.ui.web.helpers import requires_git_auth, project_root as _project_root

from . import integrations_bp


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


@integrations_bp.route("/git/log")
def git_log():  # type: ignore[no-untyped-def]
    """Recent commit history."""
    n = request.args.get("n", 10, type=int)
    return jsonify(git_ops.git_log(_project_root(), n=n))


@integrations_bp.route("/git/commit", methods=["POST"])
@run_tracked("git", "git:commit")
def git_commit():  # type: ignore[no-untyped-def]
    """Stage and commit changes.

    JSON body:
        message: commit message (required)
        files: optional list of files to stage (default: all)
        changelog_entry: optional custom changelog entry text
        skip_changelog: optional bool to skip changelog update
    """
    data = request.get_json(silent=True) or {}
    message = data.get("message", "").strip()
    if not message:
        return jsonify({"error": "Commit message is required"}), 400

    files = data.get("files")
    skip_changelog = data.get("skip_changelog", False)
    custom_entry = data.get("changelog_entry", "").strip()

    root = _project_root()
    changelog_updated = False

    # ── Changelog integration ──────────────────────────────────
    if not skip_changelog:
        try:
            from src.core.services.changelog.engine import (
                add_entry,
                load_changelog,
                save_changelog,
            )

            changelog = load_changelog(root)
            add_entry(changelog, message, custom_text=custom_entry)
            save_changelog(root, changelog)
            changelog_updated = True

            # Include CHANGELOG.md in the staged files
            if files is not None:
                if "CHANGELOG.md" not in files:
                    files = list(files) + ["CHANGELOG.md"]
            # If files is None (stage all), CHANGELOG.md is picked up by git add -A

        except Exception:
            import logging
            logging.getLogger(__name__).warning(
                "Changelog update failed — committing without changelog",
                exc_info=True,
            )

    result = git_ops.git_commit(root, message, files=files)

    if "error" in result:
        return jsonify(result), 400

    result["changelog_updated"] = changelog_updated
    return jsonify(result)


@integrations_bp.route("/git/pull", methods=["POST"])
@requires_git_auth
@run_tracked("git", "git:pull")
def git_pull():  # type: ignore[no-untyped-def]
    """Pull from remote."""
    data = request.get_json(silent=True) or {}
    rebase = data.get("rebase", False)

    result = git_ops.git_pull(_project_root(), rebase=rebase)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@integrations_bp.route("/git/push", methods=["POST"])
@requires_git_auth
@run_tracked("git", "git:push")
def git_push():  # type: ignore[no-untyped-def]
    """Push to remote."""
    data = request.get_json(silent=True) or {}
    force = data.get("force", False)

    result = git_ops.git_push(_project_root(), force=force)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@integrations_bp.route("/git/diff")
def git_diff_route():  # type: ignore[no-untyped-def]
    """Per-file diff summary for staged + unstaged + untracked changes."""
    return jsonify(git_ops.git_diff(_project_root()))


@integrations_bp.route("/git/diff/file")
def git_diff_file_route():  # type: ignore[no-untyped-def]
    """Full diff content for a single file."""
    path = request.args.get("path", "")
    staged = request.args.get("staged", "") == "1"
    if not path:
        return jsonify({"error": "path is required"}), 400
    return jsonify(git_ops.git_diff_file(_project_root(), path, staged=staged))


@integrations_bp.route("/git/stash", methods=["POST"])
@run_tracked("git", "git:stash")
def git_stash_route():  # type: ignore[no-untyped-def]
    """Stash working directory changes."""
    data = request.get_json(silent=True) or {}
    message = data.get("message")
    result = git_ops.git_stash(_project_root(), message=message)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@integrations_bp.route("/git/stash/pop", methods=["POST"])
@run_tracked("git", "git:stash-pop")
def git_stash_pop_route():  # type: ignore[no-untyped-def]
    """Pop the most recent stash."""
    result = git_ops.git_stash_pop(_project_root())
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@integrations_bp.route("/git/stash/list")
def git_stash_list_route():  # type: ignore[no-untyped-def]
    """List stash entries."""
    return jsonify(git_ops.git_stash_list(_project_root()))


@integrations_bp.route("/git/merge-status")
def git_merge_status_route():  # type: ignore[no-untyped-def]
    """Detect ongoing merge/rebase and list conflicted files."""
    return jsonify(git_ops.git_merge_status(_project_root()))


@integrations_bp.route("/git/merge/abort", methods=["POST"])
@run_tracked("git", "git:merge-abort")
def git_merge_abort_route():  # type: ignore[no-untyped-def]
    """Abort a merge or rebase in progress."""
    result = git_ops.git_merge_abort(_project_root())
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@integrations_bp.route("/git/checkout-file", methods=["POST"])
@run_tracked("git", "git:checkout-file")
def git_checkout_file_route():  # type: ignore[no-untyped-def]
    """Resolve a single conflicted file.

    JSON body:
        path: file path (required)
        strategy: "ours" | "theirs" (required)
    """
    data = request.get_json(silent=True) or {}
    path = data.get("path", "").strip()
    strategy = data.get("strategy", "").strip()
    if not path or strategy not in ("ours", "theirs"):
        return jsonify({"error": "path and strategy (ours|theirs) required"}), 400
    result = git_ops.git_checkout_file(_project_root(), path, strategy)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@integrations_bp.route("/ledger/resolve-conflict", methods=["POST"])
def ledger_resolve_conflict_route():  # type: ignore[no-untyped-def]
    """Resolve a ledger rebase conflict.

    JSON body:
        action: "retry" | "skip" | "reset" | "content_merge" | "force_push"
    """
    data = request.get_json(silent=True) or {}
    action = data.get("action", "").strip()
    valid = ("retry", "skip", "reset", "content_merge", "force_push")
    if action not in valid:
        return jsonify({"ok": False, "error": f"action must be one of {valid}"}), 400

    from src.core.services.ledger.worktree import ledger_resolve_conflict
    result = ledger_resolve_conflict(_project_root(), action)
    status = 200 if result.get("ok") else 400
    return jsonify(result), status


@integrations_bp.route("/ledger/sync-status")
def ledger_sync_status_route():  # type: ignore[no-untyped-def]
    """Inspect ledger branch divergence between local and remote.

    Returns commit-level and message-level diff so the user can see
    exactly what would be lost with each resolution option.
    """
    from src.core.services.ledger.worktree import ledger_sync_status
    return jsonify(ledger_sync_status(_project_root()))

