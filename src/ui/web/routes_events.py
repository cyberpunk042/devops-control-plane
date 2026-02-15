"""
SSE event stream endpoint.

Provides ``GET /api/events`` — a Server-Sent Events stream that
pushes cache lifecycle events, system status, and state snapshots
to the browser in real time.

Wire format (per SSE spec)::

    event: cache:done
    id: 47
    data: {"v":1,"ts":1739648400.123,"seq":47,"type":"cache:done","key":"docker","data":{...}}

The client connects with ``EventSource('/api/events')`` and receives
events as they happen.  On reconnect, ``Last-Event-Id`` is sent
automatically by the browser, enabling replay from the server's
ring buffer.
"""

from __future__ import annotations

import json

from flask import Blueprint, Response, request

from src.core.services.event_bus import bus

events_bp = Blueprint("events", __name__)


@events_bp.route("/events")
def event_stream():  # type: ignore[no-untyped-def]
    """SSE endpoint — streams events to the browser.

    Query params:
        since (int): Resume from this sequence number. Overridden
            by ``Last-Event-Id`` header if present (EventSource
            sends this automatically on reconnect).

    Returns:
        ``text/event-stream`` response with chunked transfer.
    """
    since = request.args.get("since", 0, type=int)

    # EventSource sends Last-Event-Id header on reconnect
    last_event_id = request.headers.get("Last-Event-Id")
    if last_event_id is not None:
        try:
            since = max(since, int(last_event_id))
        except (ValueError, TypeError):
            pass

    def generate():  # type: ignore[no-untyped-def]
        for event in bus.subscribe(since=since):
            yield (
                f"event: {event['type']}\n"
                f"id: {event['seq']}\n"
                f"data: {json.dumps(event, default=str)}\n\n"
            )

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "X-Accel-Buffering": "no",      # disable nginx/proxy buffering
            "Connection": "keep-alive",
        },
    )
