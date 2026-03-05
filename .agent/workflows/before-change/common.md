---
description: Shared pre-flight checklist before making ANY code change
---

# Before ANY Code Change — Common Checklist

> Applies to EVERY change: backend, frontend, refactoring.
> For scope-specific checklists, see also:
> - Backend Python: `before-change/backend.md`
> - Frontend JS templates: `before-change/frontend.md`
> - Refactoring: `.agent/rules/refactoring-integrity.md`

---

## 1. Code Discovery (from `rules/read-before-write.md`)

Before writing ANY code:

- [ ] **Read the function** you're modifying (view_file, not memory)
- [ ] **Read ALL callers** of that function (grep_search → read each)
- [ ] **Read every function** you're about to call (verify it EXISTS)
- [ ] **Trace global variables** — what sets them, what value at call site
- [ ] **Write a STATE TRACE** in your response before any edit

```
STATE TRACE (example):
  contentCurrentPath = "code-docs/adapters" (virtual)
  _smartFolderActive = { name: "code-docs", groups: [...] }
  previewCurrentPath = null
```

## 2. Scope Check

- [ ] The user explicitly asked for this change
- [ ] This change does ONLY what was requested
- [ ] I am NOT adding extras, improvements, or "while I'm here" fixes
- [ ] If multiple files need changing, I've listed them and gotten confirmation

## 3. Pattern Compliance

- [ ] I'm using the SAME patterns as existing code (not my preferred patterns)
- [ ] I'm matching existing naming conventions, indentation, style
- [ ] I verified every function I'm calling EXISTS in the codebase

## 4. Completeness

- [ ] Every file that needs to change is listed
- [ ] I've traced the full data flow through all layers touched
- [ ] The change leaves the system in a working state

## 5. One Change, One Test (from `rules/one-change-one-test.md`)

- [ ] I'm making ONE change, not multiple stacked changes
- [ ] The user can test this change independently
- [ ] If this is my 3rd+ attempt at the same fix → STOP and ask

---

## Common Mistakes (from all 14 post-mortems)

1. **Calling functions that don't exist** → verify with grep_search first
2. **Guessing global variable values** → read the code that sets them
3. **Adding `<script>` tags inside `scripts/*.html`** → these are raw JS
4. **Fixing one file but not related files** → trace the full flow
5. **Not matching path namespaces** → virtual ≠ real paths in smart folders
6. **Layering fix on fix on fix** → revert and understand instead
