"""
@tracked decorator — emits events to the event store for route operations.

Usage::

    @bp.route("/vault/unlock", methods=["POST"])
    @tracked("vault.unlocked")
    def vault_unlock():
        ...
        return jsonify(result)

The decorator:
  1. Gets the event store from the Flask app's mediator
  2. Creates a correlation_id (or reads from active chain)
  3. Sets the correlation context for the thread
  4. Calls the handler
  5. Appends the event to the store with status/summary from response
  6. Clears the correlation context

Fail-safe: tracking errors never break the handler.

For multi-request chains (vault session, pages pipeline), use chain_domain:

    @tracked("vault.key.added", chain_domain="vault")

This reads the active chain from the tracker's chain registry.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from functools import wraps
from typing import Any, Callable

logger = logging.getLogger(__name__)

# ── Event type → human label catalog ──────────────────────────────────
# Single source of truth for route event labels.
# Used by _build_summary() to produce timeline summaries.
# Add new entries here when adding @tracked routes.

_EVENT_LABELS: dict[str, str] = {
    # Tool install
    "tools.plan.executed": "Install plan",
    "tools.installed": "Tool install",
    "tools.updated": "Tool update",
    "tools.removed": "Tool remove",
    # Vault
    "vault.unlocked": "Vault unlock",
    "vault.locked": "Vault lock",
    "vault.key.added": "Key added",
    "vault.key.updated": "Key updated",
    "vault.key.deleted": "Key deleted",
    "vault.key.moved": "Key moved",
    "vault.section.renamed": "Section renamed",
    "vault.exported": "Vault export",
    "vault.imported": "Vault import",
    "vault.env.activated": "Env activated",
    # Pages
    "pages.built": "Pages build",
    "pages.deployed": "Pages deploy",
    "pages.segment.created": "Segment created",
    "pages.segment.updated": "Segment updated",
    "pages.segment.deleted": "Segment deleted",
    "pages.merged": "Pages merge",
    "pages.initialized": "Pages init",
    "pages.all.built": "Pages build all",
    "pages.ci.generated": "Pages CI generated",
    # Audit
    "audit.run": "Audit run",
    # Git
    "git.committed": "Git commit",
    "git.pulled": "Git pull",
    "git.pushed": "Git push",
    "git.stashed": "Git stash",
    "git.stash.popped": "Git stash pop",
    "git.merge.aborted": "Git merge abort",
    "git.file.checked_out": "Git checkout",
    # GitHub
    "github.repo.created": "Repo created",
    "github.visibility.changed": "Visibility changed",
    "github.branch.set": "Default branch set",
    "github.repo.renamed": "Repo renamed",
    "github.logged_in": "GitHub login",
    "github.logged_out": "GitHub logout",
    "github.device_flow": "GitHub device auth",
    # Terraform
    "terraform.validated": "Terraform validate",
    "terraform.planned": "Terraform plan",
    "terraform.initialized": "Terraform init",
    "terraform.applied": "Terraform apply",
    "terraform.destroyed": "Terraform destroy",
    "terraform.generated": "Terraform generate",
    # CDP Test
    "cdp_test.replay.started": "Test replay",
    "cdp_test.replay.completed": "Test replay done",
    "cdp_test.replay.cancelled": "Test replay cancelled",
    "cdp_test.suite.recovered": "Suite recovered",
    "cdp_test.git.synced": "Suite synced to git",
    "cdp_test.git.removed": "Suite removed from git",
    # Chat
    "chat.message.sent": "Chat message",
    "chat.message.deleted": "Chat message deleted",
    "chat.message.updated": "Chat message updated",
    "chat.message.moved": "Chat message moved",
    "chat.thread.created": "Thread created",
    "chat.thread.deleted": "Thread deleted",
    # Plans
    "plan.executed": "Plan executed",
    "plan.cancelled": "Plan cancelled",
    "plan.resumed": "Plan resumed",
    "plan.step.skipped": "Plan step skipped",
    "plan.git.synced": "Plan synced to git",
    # Scripts
    "script.executed": "Script run",
    "script.stream.started": "Script started",
    "script.stream.completed": "Script completed",
    "script.stream.failed": "Script failed",
    # Docker actions
    "docker.action.started": "Docker action",
    "docker.action.completed": "Docker action done",
    "docker.action.failed": "Docker action failed",
    # Artifacts
    "artifact.build.started": "Artifact build",
    "artifact.build.completed": "Artifact built",
    "artifact.build.failed": "Artifact build failed",
    # Builder install
    "pages.builder.install.started": "Builder install",
    "pages.builder.install.completed": "Builder installed",
    "pages.builder.install.failed": "Builder install failed",
    # Tool plan resume + remediation
    "tools.plan.resumed": "Install plan resumed",
    "tools.remediated": "Tool remediation",
    "tools.remediation.completed": "Remediation done",
    "tools.remediation.failed": "Remediation failed",
    # Artifact publish
    "artifact.publish.started": "Artifact publish",
    "artifact.publish.completed": "Artifact published",
    "artifact.publish.failed": "Artifact publish failed",
    # Ledger operations
    "ledger.committed": "Ledger commit",
    "ledger.commit.failed": "Ledger commit failed",
    "ledger.push.completed": "Ledger pushed",
    "ledger.push.failed": "Ledger push failed",
    "ledger.pushed": "Ledger push",
    "ledger.conflict.resolved": "Ledger conflict resolved",
    # Audit scan + staging
    "audit.scan.started": "Audit scan",
    "audit.scan.completed": "Audit scan done",
    "audit.scan.failed": "Audit scan failed",
    "audit.deep_detect": "Deep detection",
    "audit.snapshot.saved": "Audit saved",
    "audit.snapshot.discarded": "Audit discarded",
    "audit.snapshot.deleted": "Audit deleted",
    # Posture
    "posture.rescanned": "Posture rescan",
    "posture.tool.rescanned": "Posture tool rescan",
    # Content
    "content.saved.encrypted": "Encrypted content saved",
    # Dependencies
    "dependency.scan.completed": "Dependency scan",
    "dependency.install.started": "Dependency install",
    "dependency.install.completed": "Dependencies installed",
    "dependency.install.failed": "Dependency install failed",
    "dependency.update.started": "Dependency update",
    "dependency.update.completed": "Dependencies updated",
    "dependency.update.failed": "Dependency update failed",
    "dependency.rollback.started": "Dependency rollback",
    "dependency.rollback.completed": "Dependencies rolled back",
    "dependency.rollback.failed": "Dependency rollback failed",
    "dependency.note.added": "Dependency note added",
    "dependency.note.removed": "Dependency note removed",
}


def tracked(
    event_type: str,
    *,
    chain_domain: str | None = None,
    summary_key: str = "summary",
    ok_key: str = "ok",
):
    """Decorator for Flask route handlers that emit events to the store."""

    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            store = _get_store()
            if store is None:
                return fn(*args, **kwargs)

            from src.core.services.events.models import Event
            from src.core.services.events.correlation import (
                set_correlation, get_correlation, clear_correlation,
            )

            # Resolve correlation: header > active chain > new correlation
            correlation_id = None
            try:
                from flask import request as _req
                correlation_id = _req.headers.get("X-Correlation-ID")
            except Exception:
                pass
            if not correlation_id and chain_domain:
                tracker = _get_tracker()
                if tracker:
                    correlation_id = tracker.get_chain(chain_domain)

            if not correlation_id:
                correlation_id = f"{event_type.split('.')[0]}:{uuid.uuid4().hex[:8]}"

            set_correlation(correlation_id)
            t0 = time.time()

            # Extract context from request body for the summary
            req_context = _extract_request_context()

            try:
                response = fn(*args, **kwargs)

                # Extract status, summary, and detail from response
                status = "ok"
                summary = ""
                detail = dict(req_context) if req_context else {}
                elapsed_ms = int((time.time() - t0) * 1000)
                detail["elapsed_ms"] = elapsed_ms

                try:
                    resp_data = _extract_response(response)
                    if resp_data:
                        # Status
                        if not resp_data.get(ok_key, True):
                            status = "error"
                        if resp_data.get("error"):
                            status = "error"
                        # Summary: try multiple fields
                        for skey in (summary_key, "message", "label"):
                            s = resp_data.get(skey)
                            if isinstance(s, str) and s and s != "completed":
                                summary = s[:120]
                                break
                        # Pull useful fields into detail
                        _enrich_detail(detail, resp_data)
                except Exception:
                    pass

                # Build summary from request context if response didn't provide one
                if not summary:
                    summary = _build_summary(event_type, req_context, status, detail)

                try:
                    store.append(Event(
                        id="",
                        ts=time.time(),
                        type=event_type,
                        correlation_id=correlation_id,
                        source="route",
                        path=event_type,
                        status=status,
                        duration_ms=elapsed_ms,
                        summary=summary,
                        detail=detail,
                        origin="user",
                        actor="user",
                    ))
                except Exception:
                    pass

                # Clear correlation BEFORE forcing timeline recompute
                # so mediator events don't inherit the user chain
                clear_correlation()

                # Force timeline recompute so SSE pushes the update live
                try:
                    from src.core.services.mediator import get_mediator
                    m = get_mediator()
                    if m:
                        m.get("timeline.data", force=True)
                except Exception:
                    pass

                return response

            except Exception as exc:
                elapsed_ms = int((time.time() - t0) * 1000)
                err_summary = _build_summary(event_type, req_context, "error")
                err_detail = dict(req_context) if req_context else {}
                err_detail["error"] = str(exc)[:200]
                err_detail["elapsed_ms"] = elapsed_ms
                try:
                    store.append(Event(
                        id="",
                        ts=time.time(),
                        type=event_type,
                        correlation_id=correlation_id,
                        source="route",
                        path=event_type,
                        status="error",
                        duration_ms=elapsed_ms,
                        summary=err_summary,
                        detail=err_detail,
                        origin="user",
                        actor="user",
                    ))
                except Exception:
                    pass
                raise
            finally:
                clear_correlation()

        return wrapper
    return decorator


def _get_store():
    """Get event store from the mediator singleton."""
    try:
        from src.core.services.mediator import get_mediator
        mediator = get_mediator()
        if mediator and hasattr(mediator, "_event_store"):
            return mediator._event_store
    except Exception:
        pass
    return None


def _get_tracker():
    """Get operation tracker from the mediator singleton."""
    try:
        from src.core.services.mediator import get_mediator
        mediator = get_mediator()
        if mediator and hasattr(mediator, "_tracker"):
            return mediator._tracker
    except Exception:
        pass
    return None


def _extract_request_context() -> dict:
    """Extract useful context from the current Flask request body."""
    try:
        from flask import request
        body = request.get_json(silent=True) or {}
        ctx = {}
        for key in ("tool", "tool_id", "env", "recipe", "plan_id",
                     "mode", "target", "action", "path", "name",
                     "query", "key", "file", "branch", "message",
                     "commit", "visibility", "scenario_id", "step_id",
                     "text", "thread_id"):
            val = body.get(key)
            if isinstance(val, str) and val:
                ctx[key] = val
        # Also grab the endpoint path for context
        ctx["_endpoint"] = request.path
        return ctx
    except Exception:
        return {}


def _enrich_detail(detail: dict, resp_data: dict) -> None:
    """Pull useful fields from response JSON into the event detail."""
    for key in ("tool", "message", "error", "version", "version_installed",
                "new_version", "old_version", "steps_completed",
                "installed", "already_installed", "branch", "commit",
                "sha", "pr_url", "name", "env", "ok", "score",
                "total", "count", "status", "plan_id", "paused"):
        val = resp_data.get(key)
        if val is not None and key not in detail:
            if isinstance(val, (str, int, float, bool)):
                detail[key] = val
            elif isinstance(val, list) and len(val) < 20:
                detail[key] = len(val)


def _humanize_event_type(event_type: str) -> str:
    """Fallback: derive a human label from a dotted event type."""
    parts = event_type.split(".")
    if len(parts) >= 2:
        return " ".join(parts[-2:]).replace("_", " ").title()
    return event_type.replace(".", " ").replace("_", " ").title()


def _enrich_label(label: str, event_type: str, ctx: dict, detail: dict) -> str:
    """Add contextual details (target, branch, key, message) to a label."""
    # Target (tool, name, etc.)
    target = (ctx.get("tool") or ctx.get("tool_id") or ctx.get("name")
              or ctx.get("target") or detail.get("tool") or "")
    if target:
        label = f"{label}: {target}"

    # Git branch
    branch = ctx.get("branch") or detail.get("branch") or ""
    if branch and "git" in event_type.lower():
        label += f" ({branch})"

    # Git commit message (overrides label)
    msg = ctx.get("message") or detail.get("message") or ""
    if msg and event_type == "git.committed":
        return f"Git commit: {msg[:60]}"

    # Vault env
    env = ctx.get("env") or detail.get("env") or ""
    if env and "vault" in event_type:
        label += f" [{env}]"

    # Vault key name
    key = ctx.get("key") or ""
    if key and "vault.key" in event_type:
        label += f": {key}"

    # Chat message preview (overrides label)
    text = ctx.get("text") or ""
    if text and "chat.message" in event_type:
        preview = text[:60] + ("…" if len(text) > 60 else "")
        return f"Chat: {preview}"

    # Plan steps
    steps = detail.get("steps_completed")
    if steps and "plan" in event_type:
        label += f" ({steps} steps)"

    return label


def _append_error(label: str, detail: dict | None) -> str:
    """Append error info to a label."""
    err = (detail or {}).get("error", "")
    if err:
        return f"{label} — {err[:60]}"
    return f"{label} — failed"


def _build_summary(
    event_type: str, ctx: dict, status: str, detail: dict | None = None,
) -> str:
    """Build a human-readable summary from event type + context + detail."""
    detail = detail or {}
    label = _EVENT_LABELS.get(event_type) or _humanize_event_type(event_type)
    label = _enrich_label(label, event_type, ctx, detail)
    if status == "error":
        label = _append_error(label, detail)
    return label


def _extract_response(response) -> dict | None:
    """Extract JSON data from a Flask response."""
    if isinstance(response, tuple):
        response = response[0]
    if hasattr(response, "get_json"):
        return response.get_json(silent=True)
    if hasattr(response, "data"):
        try:
            return json.loads(response.data)
        except Exception:
            pass
    return None
