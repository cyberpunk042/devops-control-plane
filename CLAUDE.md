# CLAUDE.md

> Read every file listed below before doing anything else.
> These are not suggestions. They are hard constraints.

---

## MANDATORY — Read ALL rules at session start

```
.agent/rules/MANDATORY_READING--ANTI-ROGUE-CONSTRAINT.md
.agent/rules/core--USER-drives-YOU-obey-STOP-means-DISCARD-your-model-ANSWER-means-ANSWER.md
.agent/rules/main--NO-silent-assumptions-NO-compression-NO-fast-over-right-NO-scope-drift.md
.agent/rules/important--no-abstraction--PROCESS-users-EXACT-words-NOT-your-interpretation.md
.agent/rules/APPLY-rules-to-THIS-prompt-not-just-acknowledge-them.md
.agent/rules/RESHAPE-RULES-INTO-AN-EXECUTION-MODEL-EVERYTIME.md
.agent/rules/ECHO-FIRST--state-the-users-request-before-acting.md
.agent/rules/GREP-FIRST-before-any-analysis-when-user-reports-a-bug.md
.agent/rules/READ-ALL-callers-TRACE-state-BEFORE-writing-code.md
.agent/rules/ONE-SCOPE-find-ALL-sites-before-fixing.md
.agent/rules/refactoring-integrity--NEVER-generate-from-memory-always-READ-then-EXECUTE.md
.agent/rules/dont-reinvent--CHECK-existing-API-parameters-BEFORE-building-new-logic.md
.agent/rules/KNOWLEDGE-MAP--check-README-and-agent-docs-BEFORE-guessing.md
.agent/rules/meanings--REDO-can-mean-EVOLVE-or-REVOLVE-read-context-ASK-if-unsure.md
.agent/rules/meanings--dont-assume-scope-of-REDO-ASK-when-ambiguous.md
.agent/rules/scope--assistant--READ-content-principles-ENSURE-state-awareness-BEFORE-any-work.md
.agent/rules/STOP-CONTEXT-WAS-TRUNCATED.md
.agent/rules/POST-CHECKPOINT-QUARANTINE--checkpoint-is-reference-NOT-direction.md
.agent/rules/CORRECTION-ESCALATION--3-corrections-means-CORRUPTED.md
.agent/rules/THE-ADMIN-WEB-PANEL-IS-ON-PORT-8000.md
.agent/rules/NEVER-use-tmp--all-output-goes-inside-the-project.md
```

---

## Workflow Routing — use the right checklist for the task

- Any code change → `.agent/workflows/before-change/common.md`
- Backend Python → `.agent/workflows/before-change/backend.md`
- Frontend JS templates → `.agent/workflows/before-change/frontend.md`
- Refactoring / splitting files → `.agent/rules/refactoring-integrity--NEVER-generate-from-memory-always-READ-then-EXECUTE.md`
- Debugging a comparison → `.agent/workflows/debug-by-tracing.md`
- Context truncated → `.agent/workflows/STOP-CONTEXT-WAS-TRUNCATED.md`

---

## File Output Rule

**NEVER write files to /tmp.** All outputs go inside the project:

| Type | Location |
|------|----------|
| Reports / explorations | `.agent/docs/` |
| Plans | `.agent/plans/` |
| Specs | `.agent/specs/` |
| Workflow / process docs | `.agent/workflows/` |

---

## Project Reference

- Exploration report: `.agent/docs/exploration-report.md`
- Postmortems (16): `.agent/workflows/failures/AI-POSTMORTEM-IMPORTANT-*.md`
- Architecture docs: `.agent/reference/`
- Package READMEs: `src/<layer>/<domain>/README.md`
