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
                     "commit", "visibility", "scenario_id", "step_id"):
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


def _build_summary(
    event_type: str, ctx: dict, status: str, detail: dict | None = None,
) -> str:
    """Build a human-readable summary from event type + context + detail."""
    detail = detail or {}

    _LABELS = {
        "tools.plan.executed": "Install plan",
        "tools.installed": "Tool install",
        "tools.updated": "Tool update",
        "tools.removed": "Tool remove",
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
        "pages.built": "Pages build",
        "pages.deployed": "Pages deploy",
        "audit.run": "Audit run",
        "git.committed": "Git commit",
        "git.pulled": "Git pull",
        "git.pushed": "Git push",
        "git.stashed": "Git stash",
        "git.stash.popped": "Git stash pop",
        "git.merge.aborted": "Git merge abort",
        "git.file.checked_out": "Git checkout",
        "github.repo.created": "Repo created",
        "github.visibility.changed": "Visibility changed",
        "github.branch.set": "Default branch set",
        "github.repo.renamed": "Repo renamed",
        "github.logged_in": "GitHub login",
        "github.logged_out": "GitHub logout",
        "github.device_flow": "GitHub device auth",
        "terraform.validated": "Terraform validate",
        "terraform.planned": "Terraform plan",
        "terraform.initialized": "Terraform init",
        "terraform.applied": "Terraform apply",
        "terraform.destroyed": "Terraform destroy",
        "terraform.generated": "Terraform generate",
        "cdp_test.replay.started": "Test replay",
        "cdp_test.replay.completed": "Test replay done",
    }
    label = _LABELS.get(event_type, "")

    if not label:
        # Fallback: humanize the event type
        parts = event_type.split(".")
        if len(parts) >= 2:
            label = " ".join(parts[-2:]).replace("_", " ").title()
        else:
            label = event_type.replace(".", " ").replace("_", " ").title()

    # Add target from context
    target = (ctx.get("tool") or ctx.get("tool_id") or ctx.get("name")
              or ctx.get("target") or detail.get("tool") or "")
    if target:
        label = f"{label}: {target}"

    # Add branch for git ops
    branch = ctx.get("branch") or detail.get("branch") or ""
    if branch and "git" in event_type.lower():
        label += f" ({branch})"

    # Add commit message for git commit
    msg = ctx.get("message") or detail.get("message") or ""
    if msg and event_type == "git.committed":
        label = f"Git commit: {msg[:60]}"

    # Add env for vault ops
    env = ctx.get("env") or detail.get("env") or ""
    if env and "vault" in event_type:
        label += f" [{env}]"

    # Add key name for vault key ops
    key = ctx.get("key") or ""
    if key and "vault.key" in event_type:
        label += f": {key}"

    # Steps completed for install plans
    steps = detail.get("steps_completed")
    if steps and "plan" in event_type:
        label += f" ({steps} steps)"

    if status == "error":
        err = detail.get("error", "")
        if err:
            label += f" — {err[:60]}"
        else:
            label += " — failed"

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
