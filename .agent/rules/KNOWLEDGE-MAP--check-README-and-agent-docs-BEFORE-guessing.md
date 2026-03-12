---
trigger: always_on
---

# PROJECT KNOWLEDGE MAP — Where Documentation Lives

> **This project has 98+ README.md files and a structured .agent/ directory.**
> Before guessing how something works, CHECK these locations.
> The answer is almost certainly already documented.

---

## 1. Package READMEs — The Gold Mine

Every significant package in `src/` has a `README.md` that documents:
- What the module does and why it exists
- Architecture and design decisions
- API surface and function contracts
- Internal module relationships
- How to extend or modify

**Pattern:** `src/<layer>/<domain>/README.md`

```
src/core/README.md                    ← Core layer overview
src/core/services/README.md           ← All services overview
src/core/services/<module>/README.md  ← Individual module docs
src/ui/cli/README.md                  ← CLI layer overview
src/ui/cli/<command>/README.md        ← CLI command docs
src/ui/web/README.md                  ← Web layer overview
src/ui/web/routes/<module>/README.md  ← Web route module docs
```

### The Rule

**BEFORE working in any module:**

1. Check if `README.md` exists in that package
2. If it exists → **READ IT** before making any changes
3. It will tell you how the module works, what functions exist,
   what parameters they accept, and what patterns to follow

**AFTER making significant changes:**

4. Update the README if your changes affect the documented architecture
5. If no README exists and you've learned the module well → flag it to the user

### Why This Matters

These READMEs were written from real code audits. They are accurate.
They document exactly the things the AI needs to know: what exists,
how it works, what not to break. Ignoring them and guessing is negligence.

---

## 2. `.agent/reference/` — Architecture & State Docs

| File | What It Documents |
|------|-------------------|
| `frontend-state.md` | All frontend global variables, their types, what sets them |
| `web-architecture.md` | Web layer structure, template system, how scripts are organized |
| `smart-folders.md` | Smart folder system — virtual paths, group rendering, state |
| `failure-patterns.md` | Catalogued AI failure modes with links to rules that prevent them |
| `docs-accuracy-audit.md` | Which READMEs have been verified against source code |

**Use when:** You need to understand frontend state, web architecture,
or want to avoid known failure patterns.

---

## 3. `.agent/plans/` — Implementation Context

Active and archived plans that document:
- Why a feature was designed a certain way
- What was tried and what failed
- Phase breakdowns and tracking

**Use when:** You need context on WHY something was built this way,
or you're continuing work that was started in a previous session.

---

## 4. `.agent/workflows/` — How-To Procedures

Step-by-step procedures for specific tasks:
- `before-change/backend.md` — Python change pre-flight
- `before-change/frontend.md` — JS/template change pre-flight
- `before-change/common.md` — Universal pre-flight
- `debug-by-tracing.md` — How to debug by tracing code paths
- `failures/AI-POSTMORTEM-*.md` — What went wrong and why (16 documented failures)

---

## The Self-Test

```
Q1: Am I about to work in a module?
    → Does it have a README.md? → READ IT FIRST.

Q2: Am I guessing how something works?
    → Check .agent/reference/ for architecture docs.

Q3: Am I continuing work from a previous session?
    → Check .agent/plans/ for implementation context.

Q4: Am I making a code change?
    → Check .agent/workflows/before-change/ for the right checklist.
```
