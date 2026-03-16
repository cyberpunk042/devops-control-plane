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

            # Resolve correlation: active chain > new correlation
            correlation_id = None
            if chain_domain:
                tracker = _get_tracker()
                if tracker:
                    correlation_id = tracker.get_chain(chain_domain)

            if not correlation_id:
                correlation_id = f"{event_type.split('.')[0]}:{uuid.uuid4().hex[:8]}"

            set_correlation(correlation_id)
            t0 = time.time()

            try:
                response = fn(*args, **kwargs)

                # Extract status and summary from response
                status = "ok"
                summary = event_type
                try:
                    resp_data = _extract_response(response)
                    if resp_data:
                        if not resp_data.get(ok_key, True):
                            status = "error"
                        if resp_data.get("error"):
                            status = "error"
                        s = resp_data.get(summary_key)
                        if isinstance(s, str) and s:
                            summary = s
                except Exception:
                    pass

                elapsed_ms = int((time.time() - t0) * 1000)

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
                        origin="user",
                        actor="user",
                    ))
                except Exception:
                    pass

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
                        summary=str(exc)[:200],
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
