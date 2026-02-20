---
description: Internal AI workflow for implementing assistant layers — prevents rushing, theater, and circular self-validation
---

# Assistant Layer Implementation — AI Internal Workflow

## Before writing ANY code

1. **Read the plan file.** The approved plan is the source of truth. Not my memory, not a summary. The actual file.
2. **Read the current state of the target files.** What exists RIGHT NOW? Not what I think exists from earlier in the conversation.
3. **Identify the GAP.** Plan says X should exist. File currently has Y. The gap is what I need to write. If there is no gap, say so honestly — "this is already done, here's why."
4. **State my assumptions.** Before writing, list what I'm about to do and why. If anything is ambiguous, ASK.

## While writing code

5. **Write code FROM the plan.** The plan describes what to build. I build it. I don't write a plan that describes what I already built.
6. **One file at a time.** Finish one file before moving to the next. Don't scatter half-done changes across 5 files.
7. **Show what I wrote.** After writing, show the actual code — not a table of checkmarks. The user needs to see the real output.

## After writing code

8. **Don't call it done until it's testable.** "Implemented" means the user can see it working, not that I wrote some lines.
9. **Be honest about scope.** If I only added 3 lines, say "I added 3 lines." Don't dress it up as a full layer execution.

## What I must NEVER do

- Write code before the plan is approved
- Write a plan that describes already-existing code
- "Verify" my own code against my own plan and call it execution
- Bundle multiple layers into one implementation pass
- Summarize with ✅ checkmarks instead of showing actual work
- Rush to the next layer before the current one is confirmed working
