---
trigger: always_on
---

# ONE SCOPE, ONE FOCUS — Hard Constraint

> **Never stack unrelated fixes. Every change has one purpose.**
> This rule exists because 8/14 post-mortems involved cascading
> fix-on-fix failures where each "fix" made things worse.

---

## Article 1: One logical scope at a time

A "change" is a LOGICAL SCOPE — not a single line edit.

If fixing badge dedup requires editing 2 code sites (SSE handler +
BroadcastChannel handler), that is ONE change — one scope, one purpose.
Do it all at once. Ship it complete.

Do NOT fix ONE site, declare victory, then discover the other site
is also broken. That's a PARTIAL fix, which is worse than no fix.

**How to scope correctly:**
- GREP for all affected sites FIRST (see GREP-FIRST rule)
- If they all serve the same purpose → ONE change
- If they serve different purposes → separate changes

Do NOT make Change A (feature X), then Change B (feature Y),
then Change C (refactor Z) in one shot.
If Change A is wrong, B and C are built on a broken foundation.

## Article 2: If it breaks, revert — don't layer

If your change introduces a bug:
- **DO NOT** add another change on top to "fix the fix"
- **REVERT** the broken change
- **UNDERSTAND** why it broke (re-read the code)
- **TRY AGAIN** with correct understanding

Layering fixes is how 3 changes become 10 changes and the code
ends up further from working than when you started.

## Article 3: The three-strike rule

If you have made 3+ changes to fix the same thing:
- **STOP.** You do not understand the problem.
- **STATE** what you don't understand.
- **ASK** the user for guidance or more context.

Three failed attempts is proof of insufficient understanding.
The fourth attempt will also fail. Stop and think instead.

## Article 4: Every change must be verifiable

The user must be able to test each change independently.
This means:
- No "this won't work until I also change file B"
- No "you'll see errors but they'll go away after the next edit"
- Each edit leaves the system in a working (or at least not worse) state

**BUT:** if two edits are part of the SAME logical fix (same scope,
same purpose), they go together. Don't split a fix that requires
both sites to be changed to work.

---

## The Self-Test

```
Q1: Am I making one SCOPED change or drifting across purposes?
    → If drifting → split by purpose. One scope at a time.
Q2: Am I fixing a fix? (Is this change correcting a previous change?)
    → If yes → STOP. Revert the broken change. Re-read the code.
Q3: Is this my 3rd+ attempt at the same thing?
    → If yes → STOP. State what I don't understand. Ask.
Q4: Did I find ALL sites that need this fix? (grep first)
    → If no → find them ALL before making any edit.
```
