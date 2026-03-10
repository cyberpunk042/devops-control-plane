"""
CDP Test I/O configuration endpoint.

Unified endpoint for configuring INPUT and OUTPUT bindings on steps.
Replaces the fragmented ``io_bind`` action handler in recording.py
and the ``modify-step`` workaround used by the admin panel.

Routes registered on ``cdp_test_bp`` from the parent package.

Endpoints:
    POST /cdp-test/io/configure  — configure I/O on a step
"""

from __future__ import annotations

import logging

from flask import jsonify, request

from . import cdp_test_bp

logger = logging.getLogger(__name__)

# Actions whose value field is consumed at runtime (candidates for INPUT)
_VALUE_ACTIONS = {"navigate", "type", "select", "keypress", "inject_js"}


@cdp_test_bp.route("/cdp-test/io/configure", methods=["POST"])
def cdp_test_io_configure():
    """Configure I/O binding on a step.

    Handles both INPUT (parameterize a step's value) and OUTPUT
    (export a captured value).  Works in both recording context
    (session_id) and validation context (suite_id).

    For OUTPUT on a non-capture step (e.g. click), the endpoint
    creates a new capture step after the original step targeting
    the same element.

    Body (JSON)::

        {
            "step_id": "uuid",                  // REQUIRED
            "session_id": "uuid",               // Recording context
            "suite_id": "uuid",                 // Validation context (mutually exclusive)
            "io_type": "input" | "output" | "remove",  // REQUIRED
            "name": "LOGIN_EMAIL",              // REQUIRED for input/output
            "default_value": "admin@test.com",  // INPUT only — user-chosen default
            "capture_type": "capture_text",     // OUTPUT on non-capture step — user-chosen
            "attribute_name": "href",           // When capture_type is capture_attribute
            "css_property": "color"             // When capture_type is capture_computed_style
        }

    Returns::

        {
            "ok": true,
            "step": { ... },           // Updated step (or new capture step)
            "suite_io": {              // Updated suite-level I/O summary
                "inputs": [...],
                "outputs": [...]
            }
        }
    """
    from src.core.services.cdp_test.session import get_active_session
    from src.core.services.event_bus import bus

    data = request.get_json(silent=True) or {}

    step_id = data.get("step_id", "")
    session_id = data.get("session_id", "")
    suite_id = data.get("suite_id", "")
    io_type = data.get("io_type", "")
    name = data.get("name", "").strip()
    default_value = data.get("default_value", "")
    capture_type = data.get("capture_type", "")
    attribute_name = data.get("attribute_name", "")
    css_property = data.get("css_property", "")
    remove = io_type == "remove" or data.get("remove", False)

    # ── Validation ────────────────────────────────────────────
    if not step_id:
        return jsonify({"ok": False, "error": "step_id is required"}), 400
    if not io_type and not remove:
        return jsonify({"ok": False, "error": "io_type is required"}), 400
    if io_type not in ("input", "output", "remove", "") and not remove:
        return jsonify({"ok": False, "error": "io_type must be 'input', 'output', or 'remove'"}), 400
    if not name and not remove:
        return jsonify({"ok": False, "error": "name is required"}), 400

    # ── Recording context (session_id) ────────────────────────
    if session_id or not suite_id:
        return _configure_recording_io(
            step_id=step_id,
            io_type=io_type,
            name=name,
            default_value=default_value,
            capture_type=capture_type,
            attribute_name=attribute_name,
            css_property=css_property,
            remove=remove,
            bus_ref=bus,
        )

    # ── Validation context (suite_id) ─────────────────────────
    return _configure_suite_io(
        suite_id=suite_id,
        step_id=step_id,
        io_type=io_type,
        name=name,
        default_value=default_value,
        capture_type=capture_type,
        attribute_name=attribute_name,
        css_property=css_property,
        remove=remove,
    )


def _configure_recording_io(
    *,
    step_id: str,
    io_type: str,
    name: str,
    default_value: str,
    capture_type: str,
    attribute_name: str,
    css_property: str,
    remove: bool,
    bus_ref,
) -> tuple:
    """Configure I/O on a step in the active recording session."""
    from src.core.services.cdp_test.session import get_active_session

    session = get_active_session()
    if session is None:
        return jsonify({"ok": False, "error": "No active recording session"}), 404

    # Find the target step
    steps = session.get_steps()
    target_step = None
    for s in steps:
        if s.get("id") == step_id:
            target_step = s
            break

    if target_step is None:
        return jsonify({"ok": False, "error": f"Step '{step_id}' not found"}), 404

    # ── REMOVE I/O ────────────────────────────────────────────
    if remove:
        updates = {}
        # Restore original value if INPUT was configured
        original = target_step.get("original_value", "")
        if target_step.get("value", "").startswith("${") and original:
            updates["value"] = original
            updates["original_value"] = ""
        # Clear export
        if target_step.get("export_as"):
            updates["export_as"] = ""
        if updates:
            step = session.modify_step(step_id, updates)
            _broadcast_io_change(bus_ref, session, step)
        return jsonify({"ok": True, "step": target_step, "removed": True})

    # ── INPUT ─────────────────────────────────────────────────
    if io_type == "input":
        action = target_step.get("action", "")
        if action not in _VALUE_ACTIONS:
            return jsonify({
                "ok": False,
                "error": f"Step action '{action}' does not consume a value — cannot be INPUT",
            }), 400

        # Preserve the recorded value before overwriting
        current_value = target_step.get("value", "")
        updates = {}
        if not current_value.startswith("${"):
            updates["original_value"] = current_value

        updates["value"] = "${" + name + "}"
        updates["export_as"] = ""  # Mutual exclusivity

        step = session.modify_step(step_id, updates)
        _broadcast_io_change(bus_ref, session, step)

        return jsonify({"ok": True, "step": step})

    # ── OUTPUT ────────────────────────────────────────────────
    if io_type == "output":
        action = target_step.get("action", "")

        if action.startswith("capture_"):
            # Already a capture step — just set export_as
            updates = {"export_as": name}
            step = session.modify_step(step_id, updates)
            _broadcast_io_change(bus_ref, session, step)
            return jsonify({"ok": True, "step": step})

        # Non-capture step (click, hover, type, etc.) — create a capture step
        # Use capture_type from user if provided, fall back to guess
        if capture_type:
            capture_action = capture_type
        else:
            element_tag = target_step.get("element_tag", "").lower()
            is_form = element_tag in ("input", "textarea", "select")
            capture_action = "capture_value" if is_form else "capture_text"

        capture_step_data = {
            "action": capture_action,
            "selector": target_step.get("selector", ""),
            "xpath": target_step.get("xpath", ""),
            "export_as": name,
            "page_url": target_step.get("page_url", ""),
            "element_tag": target_step.get("element_tag", ""),
            "element_text": target_step.get("element_text", ""),
        }
        # For capture_attribute / capture_computed_style, set assertion_attribute
        if capture_action == "capture_attribute" and attribute_name:
            capture_step_data["assertion_attribute"] = attribute_name
        elif capture_action == "capture_computed_style" and css_property:
            capture_step_data["assertion_attribute"] = css_property

        new_step = session.insert_step_after(step_id, capture_step_data)

        # Broadcast the new capture step
        bus_ref.publish(
            "cdp_test:step_captured",
            key=session.id,
            data={
                "session_id": session.id,
                "step": new_step,
                "inserted": True,
                "io_generated": True,
            },
        )

        logger.info(
            "OUTPUT on non-capture step: created %s after step %s",
            capture_action, step_id,
        )

        return jsonify({"ok": True, "step": new_step, "created_capture": True})

    return jsonify({"ok": False, "error": "Invalid io_type"}), 400


def _configure_suite_io(
    *,
    suite_id: str,
    step_id: str,
    io_type: str,
    name: str,
    default_value: str,
    capture_type: str,
    attribute_name: str,
    css_property: str,
    remove: bool,
) -> tuple:
    """Configure I/O on a step in a saved suite (validation context).

    Loads the suite from storage, modifies the step, runs sync_suite_io,
    and saves the suite back.
    """
    from src.core.services.cdp_test.io_sync import sync_suite_io
    from src.core.services.cdp_test.storage import get_suite, save_suite
    from src.ui.web.helpers import project_root as _project_root

    root = _project_root()
    suite = get_suite(root, suite_id)
    if suite is None:
        return jsonify({"ok": False, "error": f"Suite '{suite_id}' not found"}), 404

    # Find the target step
    target_step = None
    target_idx = None
    for i, step in enumerate(suite.steps):
        if step.id == step_id:
            target_step = step
            target_idx = i
            break

    if target_step is None:
        return jsonify({"ok": False, "error": f"Step '{step_id}' not found in suite"}), 404

    # ── REMOVE I/O ────────────────────────────────────────────
    if remove:
        if target_step.value.startswith("${") and target_step.original_value:
            target_step.value = target_step.original_value
            target_step.original_value = ""
        target_step.export_as = ""
        io_summary = sync_suite_io(suite)
        save_suite(root, suite)
        return jsonify({
            "ok": True,
            "step": target_step.to_dict(),
            "suite_io": io_summary,
            "removed": True,
        })

    # ── INPUT ─────────────────────────────────────────────────
    if io_type == "input":
        if target_step.action not in _VALUE_ACTIONS:
            return jsonify({
                "ok": False,
                "error": f"Step action '{target_step.action}' cannot be INPUT",
            }), 400

        if not target_step.value.startswith("${"):
            target_step.original_value = target_step.value
        target_step.value = "${" + name + "}"
        target_step.export_as = ""  # Mutual exclusivity

        io_summary = sync_suite_io(suite)
        # Override the default with user's chosen value
        suite.variables[name] = default_value
        save_suite(root, suite)

        return jsonify({
            "ok": True,
            "step": target_step.to_dict(),
            "suite_io": io_summary,
        })

    # ── OUTPUT ────────────────────────────────────────────────
    if io_type == "output":
        if target_step.action.startswith("capture_"):
            target_step.export_as = name
            io_summary = sync_suite_io(suite)
            save_suite(root, suite)
            return jsonify({
                "ok": True,
                "step": target_step.to_dict(),
                "suite_io": io_summary,
            })

        # Non-capture step — create a capture step after it
        from src.core.services.cdp_test.models import TestStep

        # Use capture_type from user if provided, fall back to guess
        if capture_type:
            capture_action = capture_type
        else:
            is_form = target_step.element_tag.lower() in ("input", "textarea", "select")
            capture_action = "capture_value" if is_form else "capture_text"

        step_kwargs = dict(
            action=capture_action,
            selector=target_step.selector,
            xpath=target_step.xpath,
            export_as=name,
            page_url=target_step.page_url,
            element_tag=target_step.element_tag,
            element_text=target_step.element_text,
        )
        # For capture_attribute / capture_computed_style, set assertion_attribute
        if capture_action == "capture_attribute" and attribute_name:
            step_kwargs["assertion_attribute"] = attribute_name
        elif capture_action == "capture_computed_style" and css_property:
            step_kwargs["assertion_attribute"] = css_property

        new_step = TestStep(**step_kwargs)

        # Insert after the target step and re-sequence
        suite.steps.insert(target_idx + 1, new_step)
        for j, s in enumerate(suite.steps):
            s.sequence = j

        io_summary = sync_suite_io(suite)
        save_suite(root, suite)

        return jsonify({
            "ok": True,
            "step": new_step.to_dict(),
            "suite_io": io_summary,
            "created_capture": True,
        })

    return jsonify({"ok": False, "error": "Invalid io_type"}), 400


def _broadcast_io_change(bus_ref, session, step: dict) -> None:
    """Broadcast an I/O configuration change via SSE."""
    bus_ref.publish(
        "cdp_test:io_configured",
        key=session.id,
        data={
            "session_id": session.id,
            "step": step,
        },
    )
