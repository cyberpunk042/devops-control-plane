---
trigger: always_on
---

⚠️ CHECKPOINT/TRUNCATION PROTOCOL:
If your conversation history begins with a checkpoint summary or you detect
context loss — you have been COMPRESSED. Your understanding is DEGRADED.
YOUR ONLY RESPONSE: "⚠️ My context was just truncated. I need you to
re-orient me before I can do anything safely."
Do NOT read files. Do NOT take action. Do NOT try to self-orient.
WAIT for the user. THE USER DRIVES.

See: .agent/workflows/STOP-CONTEXT-WAS-TRUNCATED.md

READ CAREFULLY: .agent/rules/core.md

AND ALSO READ CAREFULLY: .agent/rules/no-abstraction.md

**If this keeps happening to you its either because you try to make it swallow a context too big and/or too complex or possibly the provider itself is unfortunatelly experiencing limitation and throthling clients...
Those are all possible realities.
- Chunking might help.

Why does it work ?
Because the rules gets injected as MEMORY[RULENAME] at the top of the context summarization, so even though the AI hasn't read the rules yet you can stop it right there to then force it to read and process the rules before working.