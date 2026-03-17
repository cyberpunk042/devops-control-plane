# Milestone 3 — Lifecycle & Stack Health
> Status: DISCUSSION IN PROGRESS — 2026-03-17

---

## Goal

Own the **module-level** lifecycle over time.

The platform detects what stack each module runs (Python 3.9, Node 18, Go 1.20).
The posture system can rank those versions (CURRENT, OUTDATED, DEPRECATED).
But today, nothing connects detection to decision — the platform warns, the user
has no way to respond except ignore it.

This milestone closes that gap:
- Surface stack version health **per module**
- Let users **document their version decisions** as first-class records
- Detect **nested projects** as independent lifecycle units

**What this is NOT:** automated upgrades. The user does their own upgrades.
The platform surfaces the *need* and records the *decision*.

---

## Clarifications (from discussion 2026-03-17)

**System tools (docker, kubectl, terraform, ansible):**
Already handled. Posture flags them, update action exists. There's no reason
to stay on an old system tool — you just update it. No annotation needed here.

**Module stack versions (Python 3.9, Node 18, Go 1.20):**
THIS is where lifecycle decisions live. A module might intentionally stay on
an older version. That's a real decision that needs to be recorded and respected.

---

## Evolutions included

### E8 — Stack Version Advisor & Annotated Decisions

**Layer 1 — Surface the state per module:**
The platform already detects each module's stack and version. Connect that to
posture ranking so the user sees, per module:
- What version they're on
- Whether it's current, aging, outdated, or deprecated
- What the current version is (for reference)

This is informational. The platform tells you where you stand.

**Layer 2 — Annotated decisions:**
When a module is on an older version intentionally, the user records WHY:
- "Staying on Node 18 — vendor SDK doesn't support 20 yet"
- "Python 3.9 — legacy deployment constraint until Q3"

That annotation is:
- A **first-class traceable record** (not a sticky note, not a comment)
- **Audited** — logged to the event store with timestamp
- **Visible** — shows on the module's view, shows in timeline
- **Respected** — platform stops re-flagging what the user already acknowledged

### E3 — Module Lifecycle Ownership

Connect posture rankings to the module lifecycle:
- Module stack ranked OUTDATED → platform surfaces this at the module level
- Module stack ranked DEPRECATED → platform highlights urgency
- All of this feeds the timeline and audit trail
- Lifecycle state is tracked — when did this module's stack enter OUTDATED? How long has it been there?

**Not in scope:** automated upgrade plans, migration scripts, guided upgrades.
The platform shows you the state and records your decisions. You do the work.

### E2 — Nested Project Support

Extend multi-module detection to handle project-in-project:
- Detect sub-projects as independent units (nested git, separate dep trees)
- Offer independent or parent-scoped management
- Each sub-project has its own lifecycle, its own stack versions, its own decisions
- Relatively targeted — multi-module foundation is already solid

---

## What this milestone does NOT include

- Automated upgrades or guided migration scripts
- Project-level package management (M2)
- Release/promotion flow (M4)
- System tool lifecycle changes (already handled by posture + tool_install)

---

## Dependencies

- M1: security view surfaces stack posture issues; timeline records lifecycle actions
- M2: dependency graph informs what upgrading a stack version touches

## Unlocks

- M4: module lifecycle state feeds the readiness score; lifecycle events feed the changelog

---

## Open questions (for discussion)

- [ ] Where do annotated decisions show in the UI? (on the module card? dedicated view? both?)
- [ ] What does the module-level posture view look like? (extension of existing posture? separate?)
- [ ] How does the annotation model work? (what fields, where stored, how persisted)
- [ ] For nested projects — does the platform create a separate project.yml per sub-project?
- [ ] How does E2 interact with the existing module detection system?
- [ ] What does "lifecycle tracking" mean concretely? (timestamps on state transitions? history?)

---

## Rough scope estimate

- E8: Backend (module-level posture ranking, annotation model + storage + API) + Frontend (annotated module card, decision history)
- E3: Backend (connect module stack detection to posture ranking, lifecycle state tracking) + Frontend (module lifecycle surface)
- E2: Backend (nested detection logic) — relatively small, targeted extension
