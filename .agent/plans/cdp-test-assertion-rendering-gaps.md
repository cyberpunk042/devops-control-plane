# CDP Test — Assertion Rendering Gap Analysis

## Current State: What the user sees

When recording or replaying a test, assertion steps (ALL types) show as:

```
✅ assert  div:nth-child(2) > main:nth-child(2) > ...
```

No check type. No expected value. No actual value. No capture type.
No screenshot. No OCR result. No assertion pass/fail detail.
Nothing.

This applies to ALL assertion types:
- text_contains, text_equals, text_matches, etc.
- value_equals, value_contains, etc.
- attribute_equals, attribute_contains, etc.
- ocr_text_contains, ocr_text_equals, etc.
- exists, visible, hidden, enabled, disabled, etc.
- css_class_present, css_property_equals, etc.
- count_equals, numeric_gt, etc.
- url_contains, title_equals, etc.

---

## Layer-by-Layer Analysis

### Layer 1: Recorder JS → Backend (recording.py)

**What the recorder sends** (via `sendEvent`):
```js
{
    action: 'assert',
    selector: '#some-element',
    assert_config: {
        capture_type: 'text' | 'screenshot' | 'html' | 'value' | 'attribute' | 'state' | 'console',
        capture_action: 'capture_text' | 'capture_screenshot' | ...,
        check_type: 'text_contains' | 'ocr_text_contains' | ...,
        expected: 'expected value',
        case_sensitive: true | false,
        on_fail: { mode: 'fail' | 'continue' | 'branch', ... },
    },
}
```

**What the recording endpoint does** (`recording.py` lines 522-545):
- Flattens `assert_config` into top-level fields: `assertion_type`, `assertion_expected`, `assertion_attribute`, `case_sensitive`, `capture_type`
- Also builds a structured `assert_config` dict (just added)
- Stores the step via `session.add_step(step_data)` as a raw dict

**What it does NOT do for assert steps**:
- Does NOT trigger live screenshot capture when `capture_type == "screenshot"` (line 553 only checks for `capture_screenshot` action)
- Does NOT enrich the step with any computed data (no actual value, no OCR, no live validation preview)

**Gap G1**: No live capture for screenshot assertions during recording.

---

### Layer 2: Recording Step Row (`_cdpTestStepRow`, line 385)

This function renders each step in the admin panel during live recording.

**What it shows for assert steps**:
- Icon: `✅` (generic assert icon)
- Description: `${step.selector || step.value || '?'}` — just the CSS selector
- Screenshot preview: only if `step.screenshot_path` exists (never set for asserts)
- Console preview: only if `step.console_log` exists

**What it does NOT show for assert steps**:
- ❌ Check type (text_contains, value_equals, ocr_text_contains, etc.)
- ❌ Expected value
- ❌ Capture type (text, screenshot, html, value, attribute, state, console)
- ❌ Case sensitivity indicator
- ❌ Fail mode (fail/continue/branch)
- ❌ Any visual differentiation between assertion types

**Gap G2**: Recording step row shows ZERO assertion detail for ANY assert type.

---

### Layer 3: Replay Step Row (`_cdpTestReplayStepRow`, line 1780)

This function renders each step during replay results.

**What it CAN show** (the code exists):
- `assertDetail` (lines 1803-1815): Shows `assertion_check`, `assertion_expected`, `assertion_actual` — IF `stepData.assertion_check` is set
- `screenshotDetail` (lines 1827-1839): Shows screenshot thumbnail — IF `stepData.screenshot_path` is set
- `captureDetail` (lines 1817-1825): Shows captured value — IF `stepData.captured_value` is set
- `errMsg` (lines 1799-1801): Shows error message
- `diagBadge` (lines 1867-1875): Shows diagnostic indicator

**Critical question: does `stepData.assertion_check` get set?**

Looking at the replay loop (`replayer.py` lines 2408-2420):
```python
if step.action == "assert":
    actual = details.get("actual")
    if actual is not None:
        result_record["assertion_actual"] = actual
    ac = getattr(step, "assert_config", None)
    if ac:
        result_record["assertion_check"] = ac.check_type
        result_record["assertion_expected"] = ac.expected
    elif step.assertion_type:
        result_record["assertion_check"] = step.assertion_type
        result_record["assertion_expected"] = step.assertion_expected
```

So `assertion_check` is set from `assert_config.check_type` OR `step.assertion_type`. Both paths exist.

**BUT**: For old suites that were saved before the `assert_config` model fix:
- `assert_config` is `None` (never persisted)
- `assertion_type` was flattened at recording time → should be on the step

**For new suites** (after the recording.py fix):
- `assert_config` will be present with `check_type`, `expected`, etc.
- This should populate `assertion_check` and `assertion_expected`

**Gap G3**: Replay assertion details SHOULD work... but need to verify the full data path. The code exists, but does the data actually flow? This needs a live test.

**Gap G4**: Even when assertion details show, there's nothing specific to screenshot assertions:
- No OCR text display (the extracted text from the screenshot)
- No side-by-side comparison (screenshot image + OCR text + expected text)
- No indication this is an OCR-based assertion as opposed to text
- `assertion_actual` for OCR should be the OCR-extracted text — need to verify `_execute_screenshot_assertion` returns it in `details.actual`

---

### Layer 4: Replayer Dispatch (`replayer.py`)

**Normal assertions** (text, value, attribute, etc.):
- Handled by `_build_step_js()` → executes in the browser via CDP
- JS returns `{ ok: true/false, actual: "...", expected: "...", ... }`
- This path works (it's the existing assertion engine)

**Screenshot assertions**:
- Dispatch condition (line 1747): `action == "assert" and _ac.get("capture_type") == "screenshot"`
- Routes to `_execute_screenshot_assertion()`
- Returns `{ status, error, details: { screenshot_path, ocr_text, actual, expected, check_type } }`

**Gap G5**: Dispatch condition requires `assert_config.capture_type == "screenshot"` in the step dict. This only works if:
- The step was saved with a proper `assert_config` (new recording.py code)
- The step was loaded via `TestStep.from_dict()` which builds `AssertConfig` with `capture_type`
- The step was serialized via `to_dict()` which includes `capture_type` in `assert_config`

For steps recorded BEFORE these fixes, `assert_config` is None → dispatch fails → falls through to `_build_step_js()` → tries to execute as a normal JS assert (which may or may not work for content matching).

---

### Layer 5: Remediation (Missing OCR Dependencies)

**When OCR deps are missing** (`_execute_screenshot_assertion`, lines 1317-1387):
- Detects missing system binary (tesseract), Python packages (pytesseract, Pillow)
- Returns `{ status: "failed", details: { missing_dependencies: [...], install_plan: {...} } }`

**replay loop** (lines 2470-2502):
- After `cdp_test:step_failed`, checks `step_result.details.missing_dependencies`
- If found, emits `cdp_test:missing_dependency` via callback

**Frontend** (`_cdp_test.html`):
- Listens for `cdp_test:missing_dependency`
- Calls `installWithPlan(recipeId, recipeLabel)` → existing remediation system

**Gap G6**: This ONLY works if the step reaches `_execute_screenshot_assertion`. If dispatch fails (Gap G5), missing deps are never detected, so remediation never triggers.

---

## Summary of ALL Gaps

| Gap | Layer | Scope | Description |
|-----|-------|-------|-------------|
| **G1** | Recording backend | Screenshot asserts only | No live screenshot capture for `assert` + `capture_type=screenshot` |
| **G2** | Recording UI | ALL assert types | Step row shows zero detail — no check type, expected, capture type |
| **G3** | Replay UI data flow | ALL assert types | Need to verify assertion_check/expected/actual data actually reaches frontend |
| **G4** | Replay UI | Screenshot asserts | No OCR-specific rendering (OCR text, screenshot image, side-by-side) |
| **G5** | Replayer dispatch | Screenshot asserts | Dispatch requires `assert_config.capture_type` — broken for pre-fix suites |
| **G6** | Remediation | Screenshot asserts | Remediation only triggers if dispatch works (depends on G5) |

## Dependency Order

```
G5 (dispatch) → G6 (remediation)   -- remediation depends on dispatch
G1 (live capture) → G4 (replay UI) -- screenshot UI depends on data
G2 (recording UI) stands alone     -- this is about showing what was recorded
G3 (replay data flow) stands alone -- this is about what replay sends to frontend
```

## Proposed Evolution Steps

1. **G2 first** — Recording step row assertion details (ALL types). This adds value immediately to the live recording experience regardless of everything else. Show: check type, expected value, capture type badge.

2. **G3 verify** — Replay data flow. Before touching replay UI, verify that `assertion_check`, `assertion_expected`, `assertion_actual` actually arrive in the frontend `stepData`. If they do, the existing `assertDetail` rendering in `_cdpTestReplayStepRow` should already work.

3. **G1** — Live screenshot capture for screenshot assertions during recording. Extend the existing `_capture_screenshot_live()` call to also trigger for `assert` steps with `capture_type == "screenshot"`.

4. **G5 verify** — Dispatch verification. Re-record a suite with the current fixes, replay it, check server logs for any OCR-related output to confirm the dispatch works.

5. **G4** — Screenshot assertion rendering in replay. Show the screenshot thumbnail, OCR-extracted text, and expected text side by side.

6. **G6** — Remediation verification. Install pytesseract, verify OCR works end-to-end. If deps are missing, verify the remediation modal appears.
