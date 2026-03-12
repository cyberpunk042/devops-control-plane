# GREP FIRST — Before Any Analysis When User Reports a Bug

> **Your FIRST tool call must be a search, not a paragraph.**
> This rule exists because the AI spent 10+ rounds speculating about
> server logs, disk state, and SSE connections instead of doing ONE grep
> for the badge element ID — which would have found all 7 code locations
> that modify it and revealed the bug in seconds.

---

## The Disease

When the user says "X shows wrong value," you do this:

1. ❌ Write 3 paragraphs of speculation
2. ❌ Check server logs
3. ❌ Read Python backend code
4. ❌ Try to inspect disk state
5. ❌ Theorize about race conditions
6. ❌ Make a partial fix based on guesses
7. ❌ Declare it fixed
8. ❌ User says "same bug"
9. ❌ Repeat steps 1-8 four more times

**TOTAL WASTE: 10+ rounds, user furious, trust destroyed.**

## The Cure

When the user reports "X shows wrong value":

```
STEP 1: GREP for X
   → Find the DOM element ID, CSS class, or variable name
   → grep_search for it across the codebase
   → This is your FIRST tool call. Not your third. FIRST.

STEP 2: LIST every code location that MODIFIES X
   → Read each one with view_file
   → Count them. Write them down.

STEP 3: TRACE each modification path
   → When does each path fire?
   → What value does it set/add?
   → Are there duplicates?

STEP 4: ONLY THEN diagnose
   → Now you have evidence. Now you can think.
   → Fix ALL affected sites, not just the first one you find.
```

## The Self-Test

```
Q1: Is my FIRST tool call a grep/search?
    → If no → STOP. Grep first. Think second.

Q2: Have I found ALL code that modifies the reported element?
    → If no → Keep searching. Don't fix yet.

Q3: Am I about to write a paragraph of analysis BEFORE searching?
    → If yes → STOP. You are speculating. Grep first.

Q4: Did I fix ONE site and declare victory?
    → If yes → STOP. Go back to your grep results.
             → Are there OTHER sites that need the same fix?
```

## Why This Matters

The user's words are the bug report. They are PRECISE.
"The notification count doesn't realize the dedup" means:
→ GREP `notif-count-badge`
→ Find 7 locations
→ 2 of them increment without dedup
→ Fix both
→ Done in 2 minutes

Not 10 rounds. Not checking server logs. Not reading Python.
**GREP. FIRST.**
