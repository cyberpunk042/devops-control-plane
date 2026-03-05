---
trigger: always_on
---

# ONE CHANGE, ONE TEST — Hard Constraint

> **Never stack fixes. Every change stands alone.**
> This rule exists because 8/14 post-mortems involved cascading
> fix-on-fix failures where each "fix" made things worse.

---

## Article 1: One change at a time

Make ONE change. Tell the user. Wait for confirmation it works.
Only then consider the next change.

Do NOT make Change A, then Change B, then Change C in one shot.
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

---

## The Self-Test

```
Q1: Am I making ONE change or multiple changes?
    → If multiple → split them. Do one at a time.
Q2: Am I fixing a fix? (Is this change correcting a previous change?)
    → If yes → STOP. Revert the broken change. Re-read the code.
Q3: Is this my 3rd+ attempt at the same thing?
    → If yes → STOP. State what I don't understand. Ask.
```
