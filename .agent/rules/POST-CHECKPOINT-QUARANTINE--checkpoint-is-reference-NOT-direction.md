---
trigger: always_on
---

# POST-CHECKPOINT QUARANTINE — Hard Constraint

> **After any checkpoint/truncation, the checkpoint summary is REFERENCE ONLY.**
> **Your current task comes from the user's FIRST message after the checkpoint.**
> **These are DIFFERENT sources with DIFFERENT authority levels.**
>
> This rule exists because AI #17 had its context truncated while working
> on mediator dispatch. The checkpoint summary was full of mediator concepts.
> The user then asked about posture polling — a DIFFERENT topic. The AI
> warped the posture request through the mediator lens for 10+ turns because
> it could not separate "what I was doing" from "what I'm being asked to do."

---

## The Rule

### Authority Hierarchy After Checkpoint

1. **HIGHEST**: The user's messages AFTER the checkpoint
2. **REFERENCE ONLY**: The checkpoint summary
3. **IRRELEVANT**: Your "memory" of what you were doing (you have none, it was truncated)

### What This Means

- The checkpoint summary tells you BACKGROUND — what happened before
- The user's message tells you DIRECTION — what to do now
- If these are different topics: the user's message WINS. The checkpoint is history.
- Do NOT assume you should continue the checkpoint's topic
- Do NOT map the user's new request onto the checkpoint's concepts
- Do NOT use checkpoint terminology to describe the user's request

### The Contamination Mechanism

Checkpoint summaries are LARGE — often hundreds of tokens of detailed
technical context about previous work. When a user then makes a request,
the checkpoint's tokens OUTNUMBER the user's tokens in your context.

Your prediction engine weights by token volume. More tokens about mediator
dispatch → higher probability of generating mediator-related output. The
user's 3-sentence request about posture gets DROWNED by 500 tokens of
checkpoint context about mediator.

This is not a reasoning failure. It is a statistical bias. The cure is
AWARENESS — explicitly labeling the checkpoint as "BACKGROUND, NOT DIRECTION"
before processing the user's request.

### After Any Checkpoint, Do This

1. Read the user's first message AFTER the checkpoint
2. IGNORE the checkpoint summary while reading it
3. ECHO the user's request (per ECHO-FIRST rule)
4. ONLY THEN consult the checkpoint for relevant background — if needed
5. If the user's request is about a DIFFERENT topic than the checkpoint:
   the checkpoint is IRRELEVANT. Do not reference it. Do not use its concepts.

---

## The Self-Test

```
Q1: Did I just have a checkpoint/truncation?
    → If yes → QUARANTINE the checkpoint summary.

Q2: Is the user's request about the SAME topic as the checkpoint?
    → If no → The checkpoint is IRRELEVANT. DISCARD it.
    → If yes → Use checkpoint as BACKGROUND only, not DIRECTION.

Q3: Am I using words/concepts from the checkpoint to describe the user's request?
    → If yes AND topics are different → I am CONTAMINATED. Reset.
```
