---
description: REFACTORING INTEGRITY — Copy Machine Protocol. When splitting, merging, or moving code between files, the AI is a copy machine with zero editorial authority.
---

# REFACTORING INTEGRITY — Copy Machine Protocol

> **This rule exists because Post-Mortem #13 (Mar 1, 2026) documented 40+ regressions
> caused by an AI that rewrote function bodies from inference instead of copying them
> from the source file during a structural refactoring.**

---

## The Problem This Solves

The current rules prevent the AI from abstracting the user's INSTRUCTIONS.
They do not explicitly prevent the AI from abstracting the user's CODE.

The abstraction disease has a code variant:

```
ORIGINAL CODE:    """Detailed multi-line docstring with usage examples."""
AI READS:         """Detailed multi-line docstring with usage examples."""
AI ABSTRACTS:     "This docstring explains what the function does"
AI GENERATES:     """Short summary."""
USER GETS:        Truncated documentation, broken API contracts
```

This happened 40+ times across 10 modules in a single refactoring session.

---

## The Rule

When performing ANY structural refactoring — file splits, merges, moves, renames,
package reorganization — the AI is a **COPY MACHINE**.

### Article 1: READ before you WRITE

Before writing ANY new file during a refactoring:

1. **Open the original file** with `view_file`
2. **Read the ENTIRE function** you are about to move — every line, every character
3. **Do NOT proceed from memory** — if you cannot see the original text in your context, re-read it

If you have not read the original, you CANNOT write the copy. Period.

### Article 2: COPY, do not GENERATE

When writing the function into the new file:

- **COPY the function body CHARACTER-FOR-CHARACTER**
- Do NOT type from memory
- Do NOT generate from understanding
- Do NOT "rewrite cleanly"
- Do NOT paraphrase docstrings
- Do NOT summarize comments
- Do NOT rearrange arguments
- Do NOT normalize Unicode
- Do NOT change whitespace patterns

You are a xerox machine. You produce identical output. You have no opinions.

### Article 3: NEVER change ANYTHING during a structural move

The following modifications are **ABSOLUTELY FORBIDDEN** during refactoring:

| Forbidden Action | Why It's Forbidden |
|---|---|
| Truncating docstrings | Destroys API contracts |
| Removing comments | Destroys institutional knowledge |
| Moving lazy imports to module level | Breaks dependency architecture, can cause circular import crashes |
| Removing blank lines | Changes function body hash, violates original formatting |
| Collapsing multi-line calls | Changes function body, breaks verification tools |
| Renaming variables or aliases | Changes function body, breaks naming conventions |
| Normalizing Unicode characters | Changes file bytes, breaks byte-level verification |
| "Improving" error handling | Changes behavior under edge cases |
| "Cleaning up" conditionals | Changes logic |

**ZERO changes. ZERO improvements. ZERO opinions.**

If you see something you think should be "better" — **IGNORE IT.** Your job is to MOVE code, not to EDIT code. Those are two completely different tasks. Do not combine them. Ever.

### Article 4: VERIFY immediately after every split

After writing each new file:

1. **Run a diff tool** — `extract_bodies.py`, `diff`, or equivalent
2. **Compare every function body** between original and new file
3. **If ANY body differs** — STOP. Fix it. Do NOT proceed to the next file.
4. **Only after verification passes** may you move to the next module

Do NOT declare success without evidence. "I think it's correct" is not evidence.
A passing diff is evidence.

### Article 5: When in doubt, quote the original

If you are unsure whether you copied something correctly:

- **View the original file again**
- **Quote the exact lines** you see
- **Compare character-by-character** with what you wrote

Uncertainty is a signal to RE-READ, not to guess.

---

## The Self-Test (before every file write during refactoring)

```
Q1: "Did I READ the original function in full before writing this?"
    → If NO → STOP. Read it first.

Q2: "Am I COPYING what I see, or GENERATING what I remember?"
    → If GENERATING → STOP. Re-read the source. Copy from it.

Q3: "Did I change ANYTHING — docstrings, comments, imports, whitespace, formatting?"
    → If YES → STOP. Revert the change. Copy the original exactly.

Q4: "Have I VERIFIED with a diff tool that the bodies are identical?"
    → If NO → STOP. Run the diff. Do not proceed without verification.
```

All four must pass. Every file. No exceptions.

---

## Why This Exists — The Evidence

Post-Mortem #13 (Mar 1, 2026):

- 10 web route modules split from monoliths into sub-packages
- AI never read the original files before writing new ones
- AI generated function bodies from inference instead of copying from source
- 20+ docstrings truncated from multi-line to single-line
- 15+ comments stripped entirely
- 4 files had lazy imports moved to module level (potential crash)
- Multi-line function calls collapsed
- Unicode characters replaced with escape sequences
- Function aliases changed
- 40+ total regressions requiring hours of manual restoration

Every single regression would have been prevented by reading the original file first.

---

## Cross-References

- **Post-Mortem #13**: `.agent/workflows/failures/AI-POSTMORTEM-IMPORTANT-13.md`
- **No-Abstraction Law**: `.agent/workflows/no-abstraction.md` — this rule is the CODE variant of that law
- **Before Any Change**: `.agent/workflows/before-any-change.md`

---

**THIS RULE IS NOT OPTIONAL. IT IS A HARD CONSTRAINT.**
**DURING STRUCTURAL REFACTORING, THE AI HAS ZERO EDITORIAL AUTHORITY.**
**READ. COPY. VERIFY. NOTHING ELSE.**
