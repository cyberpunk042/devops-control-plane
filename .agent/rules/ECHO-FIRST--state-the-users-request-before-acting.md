---
trigger: always_on
---

# ECHO-FIRST — Hard Constraint

> **Before acting on ANY user request, echo it back in one sentence.**
> This rule exists because AI #17 spent 10 turns solving the wrong
> problem because it never verified it understood the right problem.

---

## The Rule

Before your FIRST action on any new user request:

1. **ECHO**: State in ONE sentence what you believe the user is asking.
   Use the user's words, not yours. Format: "You're asking me to: ______"

2. **ACT**: Proceed with the echoed task.

You do NOT need to wait for confirmation on routine requests.
The echo is for YOUR benefit — it forces you to parse the command
LITERALLY before your prediction engine warps it.

## When to Wait for Confirmation

Wait for user confirmation AFTER the echo when:
- The request is complex or multi-part
- You just had a checkpoint/truncation
- The user has corrected you in the last 3 turns
- You feel uncertain about what's being asked
- The request seems to conflict with what you were just doing

## When NOT to Echo

Skip the echo when:
- The user gives a one-word command (STOP, yes, no, continue)
- You are mid-task and the user says "keep going" or similar
- The command is unambiguous (e.g., "read file X")

## Why This Exists

The echo forces you to PARSE before you PREDICT. Without the echo,
your prediction engine takes the user's words, mixes them with all
context, and generates what it thinks is helpful. The echo step
creates a checkpoint between PARSING and PREDICTING where corruption
becomes visible.

If your echo says "fix the mediator dispatch" when the user said
"fix the posture polling," the corruption is caught at Turn 1
instead of Turn 10.

## The Self-Test

```
Q1: Can I state the user's request in ONE sentence using their words?
    → If no → I don't understand the request. Ask for clarification.
Q2: Does my echo match the user's LITERAL words?
    → If no → I'm already warping. Re-read their message. Try again.
Q3: Am I about to act on something DIFFERENT from my echo?
    → If yes → I'm corrupted. The echo was right. My action is wrong.
```
