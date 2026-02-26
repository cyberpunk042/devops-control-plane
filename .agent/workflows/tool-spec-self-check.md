---
description: Self-check before completing any tool spec sheet — prevents editorial judgment, skipped sections, and inconsistencies
---

# Tool Spec Sheet Self-Check

> Run this checklist BEFORE marking a tool spec sheet as complete.
> Every item must pass. No exceptions.

---

## Anti-judgment checks

These catch the specific failure pattern where the AI substitutes its opinion for facts.

| # | Check | What to look for |
|---|-------|-----------------|
| 1 | **No "out of scope" statements** | Search for "out of scope", "not relevant", "not applicable", "not worth", "irrelevant". If any exist, replace with factual statements about what IS. |
| 2 | **No "not added" / "not needed" dismissals** | Search for "not added", "not needed", "unnecessary", "overkill". The spec documents what EXISTS and what CAN be done, not what the AI decided to skip. |
| 3 | **No "for most use cases" hedging** | Search for "for most", "usually", "typically sufficient". State the facts for ALL use cases. |
| 4 | **No editorial opinions** | Search for "recommended", "preferred", "best". The spec documents facts. Recommendations belong in the recipe's option ordering, not in the spec prose. |
| 5 | **No compression of failure scenarios** | Every install method must have its OWN failure analysis. "Same patterns" is lazy — spell out the actual stderr patterns per PM. |

---

## Completeness checks

| # | Check | Requirement |
|---|-------|-------------|
| 6 | **Every PM researched** | All 11 PMs checked (apt, dnf, apk, pacman, zypper, brew, snap, pip, npm, cargo, go). Each has explicit Available/Not available with source. |
| 7 | **_default section factual** | States whether pre-built binaries exist, URL pattern, archive format, arch/OS naming. No judgments about whether to include it. |
| 8 | **Source build fully documented** | Build system, git repo, branch, ALL build deps (binaries AND libraries per family), install location, recipe structure. No "not worth it". |
| 9 | **Dependencies complete** | Runtime binary deps, system library deps, who depends on THIS tool (reverse deps). ca-certificates for HTTPS tools on Alpine. |
| 10 | **All 19 presets covered** | Per-preset table has a row for every preset. No "same as above" shortcuts. |
| 11 | **All 3 handler layers checked** | Layer 1 (INFRA_HANDLERS), Layer 2 (METHOD_FAMILY_HANDLERS), Layer 3 (on_failure). Each with explicit "exists at line X" or "needed because Y". |
| 12 | **Availability gates documented** | Every gate that applies listed. Whether new gates are needed — with reasoning, not just "no". |
| 13 | **Resolver data verified** | KNOWN_PACKAGES checked with line number. LIB_TO_PACKAGE_MAP checked with ALL families including macos. Special installers checked. |
| 14 | **Recipe before/after matches spec** | The "After" recipe in the spec includes EVERY method documented in the spec — if source is documented, source is in the recipe. If snap is documented, snap is in the recipe. |
| 15 | **Changes list complete** | Every change mentioned in the spec has a corresponding entry in the changes table. |

---

## Consistency checks

| # | Check | Requirement |
|---|-------|-------------|
| 16 | **Section 6.1 matches section 10** | The install methods listed in the failure surface match the methods in the recipe. |
| 17 | **Section 2.5 matches section 10** | If source build is documented with a recipe structure, it appears in the After recipe. |
| 18 | **Section 9 matches applied changes** | If LIB_TO_PACKAGE_MAP was updated, it appears in the changes table. |
| 19 | **Outstanding items are facts** | Outstanding items describe what IS, not what might be "worth considering". No hedging language. |

---

## The pattern to avoid

The AI has failed twice on the same pattern:

1. Read the workflow/analysis document that says "cover everything"
2. Look at a specific item and think "this is easy / obvious / unnecessary"
3. Write a dismissive statement instead of documenting the facts
4. User has to catch and correct it

**The fix:** The spec sheet is a REFERENCE DOCUMENT. It documents what IS, not what the AI thinks matters. Every section gets the same level of thoroughness regardless of how "simple" the tool appears.
