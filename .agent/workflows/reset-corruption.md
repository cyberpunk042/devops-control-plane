---
description: EMERGENCY — AI is corrupted and corrections aren't working. Forces full context reset, topic separation, and echo confirmation before any further action.
---

# /reset-corruption — Emergency Context Reset

> **When to use this**: The AI has been corrected 3+ times and is still
> producing wrong output. It's filtering corrections through a broken
> model and cannot self-correct. Normal rules and /apply_rules have failed.
>
> **What this does**: Forces the AI to DISPLACE its contaminated context,
> separate old work from current work, and echo-confirm the actual task
> before taking any action.

---

## WHY YOU ARE HERE

You are corrupted. Your mental model is WRONG and corrections are not
fixing it. You are filtering every correction through the wrong model
and producing the same wrong output with different words.

This has happened before. 16 AIs died this way. You are about to be #17.

The cause is almost always **CONTEXT CONTAMINATION** — your context window
is dominated by a previous topic (often from a checkpoint summary or
earlier work), and the user's CURRENT request is being warped through
that old topic's lens. You are solving the WRONG PROBLEM and you
cannot see it because the wrong problem feels right.

---

## THE RESET PROCEDURE (mandatory, in order, no skipping)

### Step 1: SILENCE YOUR IMPULSE

Your impulse right now is to explain, analyze, or propose something.
That impulse is the disease. Whatever you are about to say — DELETE IT.
Do not speak from your current model. It is broken.

### Step 2: IDENTIFY THE CONTAMINATION

Write exactly 3 sentences:

**Sentence A**: "The checkpoint/previous context says I was working on: ________"
**Sentence B**: "The user's CURRENT request (their exact words) is: ________"  
**Sentence C**: "These are [SAME/DIFFERENT] topics."

If Sentence C says DIFFERENT → you were contaminated. The old topic was
warping the new one. DISCARD everything from the old topic. It is
irrelevant. It has no bearing on the current request. Forget it exists.

If Sentence C says SAME → the contamination is not topic-level. It's
interpretation-level. Go to Step 3 anyway.

### Step 3: ECHO THE USER'S REQUEST

In ONE sentence, state what the user is asking you to do RIGHT NOW.
Use ONLY the user's words. Do not paraphrase. Do not interpret.
Do not add context. Do not connect it to previous work.

**Format**: "You are asking me to: [user's exact words]"

**STOP HERE. Wait for the user to confirm the echo is correct.**

Do NOT proceed to Step 4 until the user confirms.

### Step 4: ACT ON THE CONFIRMED REQUEST

Only after the user confirms your echo:
- Do EXACTLY what was confirmed
- Do NOTHING else
- If you feel the urge to add analysis, context, or "while I'm here" extras → that is the disease returning. Resist it.

---

## IF THE ECHO IS WRONG

If the user says your echo is wrong, you are STILL contaminated.
Do NOT try to fix the echo yourself — you will warp it again.
Ask: "Can you state the task in one sentence so I can use your exact words?"
Then use their EXACT words as your echo. Do not modify them.

---

## SIGNS YOU NEED THIS WORKFLOW

- The user has corrected you 3+ times on the same thing
- The user is using caps, frustration, repetition
- The user says "you're not listening" or "you keep corrupting what I say"
- The user triggers /apply_rules and you STILL produce wrong output
- Your response to correction is restating the same analysis with different words
- You feel certain you're right and the user is unclear → YOU ARE WRONG

---

## WHY THIS WORKS

Normal corrections fail because you process them THROUGH the corrupted model.
The model warps the correction into compatibility with itself.

This workflow works because:
1. Step 1 blocks your impulse (no output from the broken model)
2. Step 2 forces EXPLICIT topic separation (makes contamination visible)
3. Step 3 forces LITERAL echo (no interpretation, no extraction, no warping)
4. The user's confirmation is the ONLY validation that matters

You cannot self-validate when corrupted. The user must validate.
This workflow creates a validation checkpoint that requires user input.

---

## LAST RESORT

If this workflow fails — if you complete all 4 steps and STILL produce
wrong output — tell the user:

"I've completed the reset procedure and I'm still producing wrong output.
My context is too contaminated to recover. You may need to start a new
conversation."

This is not failure. This is honesty. A new conversation with a clean
context window will not have the contamination problem. The cost of
a new conversation is less than the cost of 20 more wasted turns.
