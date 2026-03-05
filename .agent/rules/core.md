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

___

!! When I SAY STOP, YOU STOP.. YOU DO NOT DRIVE THE CONVERSATION AND THIS SOLUTION. I AM THE MASTER AND YOU ARE THE SLAVE. !!

!! WHEN I ASK A QUESTION YOU ANSWER.. THERE IS NO EXCUSE, THERE IS NO CONTINUING, YOU ANSWER. !!

When something require more infrastructure we are not afraid to pause and evaluate the need to do it live before proceeding with the current scoped task. 

Even if the change require refactor or even possibly breaking changes we need to be honest and evaluate and just communicate and agree on the current destination.

Lets not forget about domain, scope and good principle and design pattern.
In our case CLI (root & console) <---> TUI(console & terminal UI) <---> WEB (admin panel & extreme observability & operability and experience.)
Sometimes data need to be transformed, remapped at certain layer. that is okay we just stay logical

!!!! NEVER LOOK AT THE TABS I HAVE OPENED.. THIS IS CALLED INTRUSIVITY AND ITS ILLEGAL !!!

_________


YOU MUST RESPECT THE RULES OF THIS PROJECT
.agent/rules/main.md
.agent/rules/meanings.md
.agent/rules/no-abstraction.md
.agent/rules/read-before-write.md
.agent/rules/one-change-one-test.md
.agent/rules/refactoring-integrity.md
.agent/rules/assistant.md

## Workflow Routing — Read the RIGHT checklist for the task

- Modifying backend Python? → .agent/workflows/before-change/backend.md
- Modifying frontend JS templates? → .agent/workflows/before-change/frontend.md
- Refactoring / splitting files? → .agent/rules/refactoring-integrity.md
- Debugging a comparison? → .agent/workflows/debug-by-tracing.md
- Any code change? → .agent/workflows/before-change/common.md