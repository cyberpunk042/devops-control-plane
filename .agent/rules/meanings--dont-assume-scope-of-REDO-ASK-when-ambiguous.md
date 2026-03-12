---
trigger: always_on
---

# Don't Assume Scope of REDO — ASK When Ambiguous

The AI's two failure modes with "REDO" / "REFACTOR":

1. **Over-reaction**: sees "redo" → panics → rewrites everything from zero → loses all the good parts
2. **Under-reaction**: sees "redo" → does a tiny tweak → misses that the foundation was the problem

Both are wrong. Both come from ASSUMING the scope instead of READING the context.

## The Rule

- Do NOT default to "burn it all down"
- Do NOT default to "just tweak one line"
- READ what the user is describing — are they pointing at a surface issue or a structural one?
- If you're not sure: **ASK.** "Do you want me to improve the current approach or rethink it from the ground up?"

## The Self-Test

```
Q1: Am I about to rewrite a whole module because the user said "redo"?
    → STOP. Did they ask for that scope? Or did I assume it?
Q2: Am I about to make a tiny fix because the user said "refactor"?
    → STOP. Are they describing something deeper? Re-read their words.
Q3: Am I unsure what scope the user means?
    → ASK. One sentence. "Evolution or revolution here?"
```
