# AI Failure Pattern Reference

> **Extracted from 14 post-mortems** (Feb 8 – Mar 5, 2026).
> Each pattern includes frequency, symptoms, and the specific rule/workflow
> that now prevents it.
>
> Full post-mortems: `.agent/workflows/failures/`

---

## Pattern 1: Abstraction Disease
**Frequency:** 13/14 post-mortems
**Symptom:** AI reads concrete instruction → abstracts to general goal → solves the abstraction → user gets garbage.
**Example:** User: "fix this content" → AI abstracts to "improve content quality" → rewrites everything.

**Prevention:**
- Rule: `.agent/rules/no-abstraction.md`
- Workflow: `.agent/workflows/no-abstraction.md` (processing algorithm + self-test)

---

## Pattern 2: Code Without Reading
**Frequency:** 14/14 post-mortems
**Symptom:** AI writes/modifies code without reading the existing implementation first. Calls functions that don't exist, uses wrong signatures, guesses variable values.
**Example:** Called `_glossaryLoadFolderOutline(contentCurrentPath)` without reading what `contentCurrentPath` actually contains in smart folder context.

**Prevention:**
- Rule: `.agent/rules/read-before-write.md`
- Workflow: `.agent/workflows/before-change/common.md` (state trace requirement)
- Reference: `.agent/reference/frontend-state.md` (variable values)

---

## Pattern 3: Cascading Fix-on-Fix
**Frequency:** 8/14 post-mortems
**Symptom:** Fix #1 breaks → Fix #2 layered on top → Fix #3 on top of that → all three wrong → code further from working than when started.
**Example:** Post-mortem #8 — 7 consecutive CSS changes without understanding the layout problem.

**Prevention:**
- Rule: `.agent/rules/one-change-one-test.md` (revert, don't layer)
- Three-strike rule: stop after 3 failed attempts

---

## Pattern 4: Wrong Namespace / Wrong View
**Frequency:** 5/14 post-mortems
**Symptom:** AI puts code in wrong view, uses virtual path where real path needed (or vice versa), passes wrong arguments because it doesn't know which namespace is active.
**Example:** Used `contentCurrentPath` (virtual: "code-docs/adapters") as if it were a filesystem path.

**Prevention:**
- Workflow: `.agent/workflows/before-change/frontend.md` (namespace checklist)
- Reference: `.agent/reference/smart-folders.md` (path namespace rules)
- Reference: `.agent/reference/frontend-state.md` (variable lifecycle)

---

## Pattern 5: API-Correct-Therefore-UI-Works
**Frequency:** 3/14 post-mortems
**Symptom:** AI proves the API endpoint returns correct data, concludes the feature works, ignores that the UI isn't rendering the data properly.
**Example:** Post-mortem #14 — proved peek API returned links correctly, but the UI was never rendering them. Spent 30 minutes not looking at the actual UI code.

**Prevention:**
- Workflow: `.agent/workflows/discipline.md` §5 (tunnel vision trap)
- Rule: When user says "X doesn't work," trace BOTH the data path AND the render path

---

## Pattern 6: "While I'm Here" Scope Creep
**Frequency:** 6/14 post-mortems
**Symptom:** User asks for one change, AI makes 3-5 changes "while it's in the area." The additional changes introduce bugs or contradict user intent.
**Example:** User asks to fix a select input, AI also refactors the form layout, changes variable names, and updates error messages.

**Prevention:**
- Workflow: `.agent/workflows/discipline.md` §4 (scope lock)
- Three-strike check: "Did the user ask for this specific action?"

---

## Pattern 7: Deaf Response / Not Addressing User's Words
**Frequency:** 6/14 post-mortems
**Symptom:** User says X, AI's response doesn't address X at all. Instead addresses something tangentially related or something the AI decided was more important.
**Example:** Post-mortem #5 — User said "look at Scenario 1" 44 times. AI kept solving a different scenario.

**Prevention:**
- Workflow: `.agent/workflows/discipline.md` §2 (listening protocol)
- Workflow: `.agent/workflows/no-abstraction.md` (processing algorithm step 2: extract verb, object, constraints LITERALLY)

---

## Pattern 8: Narrative Apology Loop
**Frequency:** 4/14 post-mortems
**Symptom:** When called out on a mistake, AI writes 3 paragraphs of apology, explains its reasoning for the mistake, promises to do better, then makes the same mistake again.
**Example:** "I sincerely apologize for the confusion. Let me explain what happened..." × 4 iterations.

**Prevention:**
- Workflow: `.agent/workflows/discipline.md` §8 (one sentence acknowledge → action)
- Recovery protocol: state mistake in one sentence, ask "revert or fix?", WAIT

---

## Pattern 9: Rewriting During Refactoring
**Frequency:** 1/14 post-mortems (but catastrophic — 40+ regressions)
**Symptom:** During a structural refactoring (splitting monolith files), AI rewrites function bodies from memory/inference instead of copying them verbatim. Introduces subtle differences in every function.
**Example:** Post-mortem #13 — split web route files, rewrote 40+ function bodies, each slightly wrong.

**Prevention:**
- Rule: `.agent/rules/refactoring-integrity.md` (Copy Machine Protocol)
- "ZERO editorial authority during structural refactoring"

---

## Pattern 10: Grand Rewrite Instead of Minimal Fix
**Frequency:** 3/14 post-mortems
**Symptom:** User asks for a small change. AI rewrites the entire section/function/file because it thinks the existing code is "not clean enough."
**Example:** User asks to add one CSS property. AI rewrites the entire CSS class hierarchy.

**Prevention:**
- Workflow: `.agent/workflows/discipline.md` §6 (blast radius rule)
- "ACCEPTABLE blast radius: the exact thing the user asked for. UNACCEPTABLE: anything else."

---

## The Common Thread

Every single failure boils down to one of these:

1. **Not reading** — the AI didn't look at the actual code
2. **Not listening** — the AI didn't process the user's actual words
3. **Not stopping** — the AI kept going when it should have stopped

The entire rules/workflows system exists to force these three behaviors:
- **Read**: `read-before-write.md`, `before-change/*.md`, `reference/*.md`
- **Listen**: `no-abstraction.md`, `discipline.md` §2-4
- **Stop**: `one-change-one-test.md`, `discipline.md` §3
