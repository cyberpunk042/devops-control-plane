# M8 — Events & Lifecycle: State Machine Into EventBus + SSE

> The compat state machine (PENDING/RUNNING/PASSED/FAILED/NEEDS_ATTENTION/BLOCKED) is
> good design but it's standalone — no integration with the program's EventBus, SSE
> bridge, or mediator subscribe. This milestone wires it in so the frontend gets
> real-time updates without polling.

---

## What Exists Now (broken)

### State machine is isolated
`lifecycle/state_machine.py` tracks step states but doesn't publish events.
State transitions happen silently. The frontend has to poll or wait for the
HTTP response to know what happened.

### Batch runner has its own SSE
`lifecycle/batch_runner.py` implements its own SSE event streaming, parallel to
the existing wizard.py SSE system and the EventBus → SSE bridge.

### No mediator subscribe integration
The program has `mediator.subscribe("pattern.*", callback)` which publishes to
the EventBus. The EventBus feeds SSE to the frontend. The compat system doesn't
use any of this.

---

## What M8 Delivers

### 1. State transitions publish to EventBus

When a step state changes, publish an event:

```python
# In state_machine.py:
def transition(self, step_id, new_state):
    old_state = self._states[step_id]
    self._states[step_id] = new_state

    # Publish via EventBus for SSE
    try:
        from src.core.services.event_bus import bus
        bus.publish("compat:step:transition", key=step_id, data={
            "module": self._module_name,
            "step_id": step_id,
            "old_state": old_state.value,
            "new_state": new_state.value,
            "timestamp": time.time(),
        })
    except Exception:
        pass  # events are supplementary
```

The SSE bridge picks this up. The frontend receives real-time step state updates.

### 2. Batch runner uses existing SSE pattern

Instead of its own SSE implementation, the batch runner publishes events that the
existing SSE system delivers:

```python
# In batch_runner.py:
def _on_step_complete(self, step_id, result):
    from src.core.services.event_bus import bus
    bus.publish("compat:batch:step_done", key=step_id, data={
        "step_id": step_id,
        "elapsed_ms": result.duration_ms,
        "findings": result.total_findings,
    })
```

### 3. Fix engine publishes events

When fixes are applied:

```python
# In fix/engine.py:
def _on_fix_applied(self, finding, success):
    from src.core.services.event_bus import bus
    bus.publish("compat:fix:applied", key=finding.feature_id, data={
        "feature": finding.feature_name,
        "file": finding.file,
        "success": success,
    })
```

### 4. Frontend subscribes to compat events

The frontend's SSE handler already listens for events. Add handlers for compat events:

```javascript
// Already have SSE subscription infrastructure — just add compat handlers
if (typeof storeRegister === 'function') {
    storeRegister('compat:step:transition', function(data) {
        // Update step state in the plan modal without polling
        _updateStepState(data.step_id, data.new_state);
    });
    storeRegister('compat:fix:applied', function(data) {
        toast('🔧 Fixed: ' + data.feature + ' in ' + data.file, 'success');
    });
}
```

---

## Files Changed

| File | Action |
|------|--------|
| `src/core/services/compat/lifecycle/state_machine.py` | Add EventBus publishing on transitions |
| `src/core/services/compat/lifecycle/batch_runner.py` | Use EventBus instead of custom SSE |
| `src/core/services/compat/fix/engine.py` | Publish fix events |
| `src/ui/web/templates/scripts/globals/_system_posture.html` | Add SSE handlers for compat events |

---

## Verification

1. Step state transition fires an SSE event to the frontend
2. Fix application fires an SSE event
3. Batch completion fires an SSE event
4. Frontend updates step states in real-time without polling
5. No custom SSE implementation in compat code — uses program's EventBus
