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
.agent/rules/MANDATORY_READING--ANTI-ROGUE-CONSTRAINT.md
.agent/rules/main--NO-silent-assumptions-NO-compression-NO-fast-over-right-NO-scope-drift.md
.agent/rules/meanings--REDO-can-mean-EVOLVE-or-REVOLVE-read-context-ASK-if-unsure.md
.agent/rules/meanings--dont-assume-scope-of-REDO-ASK-when-ambiguous.md
.agent/rules/important--no-abstraction--PROCESS-users-EXACT-words-NOT-your-interpretation.md
.agent/rules/READ-ALL-callers-TRACE-state-BEFORE-writing-code.md
.agent/rules/ONE-SCOPE-find-ALL-sites-before-fixing.md
.agent/rules/refactoring-integrity--NEVER-generate-from-memory-always-READ-then-EXECUTE.md
.agent/rules/scope--assistant--READ-content-principles-ENSURE-state-awareness-BEFORE-any-work.md
.agent/rules/APPLY-rules-to-THIS-prompt-not-just-acknowledge-them.md
.agent/rules/dont-reinvent--CHECK-existing-API-parameters-BEFORE-building-new-logic.md


## Workflow Routing — Read the RIGHT checklist for the task

- Modifying backend Python? → .agent/workflows/before-change/backend.md
- Modifying frontend JS templates? → .agent/workflows/before-change/frontend.md
- Refactoring / splitting files? → .agent/rules/refactoring-integrity--NEVER-generate-from-memory-always-READ-then-EXECUTE.md
- Debugging a comparison? → .agent/workflows/debug-by-tracing.md
- Any code change? → .agent/workflows/before-change/common.md