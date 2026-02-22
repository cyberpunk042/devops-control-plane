# Assistant — Content Principles

> Three core concepts that guide every piece of assistant panel content.
> These layer on top of each other: program-awareness decides **what** to
> talk about, state-awareness decides **which variant** to show, and feel
> decides **how** to say it.

---

## 1. Feel — How the assistant talks

The assistant's feel is its tone and personality. It speaks like a helpful
colleague standing next to you, narrating what you're looking at — not a
tooltip, not a reference manual, not a chatbot.

### Rules

- **Conversational** — "Good to have", "Think of them as", "You've got 2
  set up so far", "Take your time — this is the heart of your config."
- **Never restate the visible** — don't echo field values, badge text, or
  status labels. The user can already read those. Explain what they MEAN.
- **Explain consequences** — "If it exceeds memory limit, it gets
  OOM-killed", "3 × 15s = 45 seconds of failures before action."
- **Cross-reference** — link related elements. kubectl missing explains
  why K8s shows "not installed". A branch name connects to what you'll
  push to GitHub later.
- **Teach** — explain concepts, security implications, operational
  tradeoffs. The user may not know what a QoS class is, or why coverage
  percentage matters for a .gitignore.
- **Never lie or generalize** — development ≠ local. Docker daemon
  offline ≠ blocker. Only say things that are true.
- **Silence over noise** — if there's nothing useful to add for an
  element, say nothing. Forced filler content destroys trust.

### Anti-patterns

- ❌ "This is the Git CLI row" (restating the label)
- ❌ "Status: Installed" (restating the badge)
- ❌ "Click here to configure" (generic instruction)
- ✅ "Git is the foundation — remotes, .gitignore, hooks, and CI/CD all
  depend on it being present."

---

## 2. State-awareness — What the assistant knows about current state

State-awareness is the assistant's ability to know the **current state of
detected data** and adjust its content accordingly. The assistant doesn't
give generic advice — it gives advice specific to this project's current
situation.

### Mechanism

The engine resolves state through the `variants` system in the catalogue.
Each node (or `childTemplate`) can carry a `variants` array. Each variant
has a `when` condition checked against the DOM element at render time:

- `textContains` — matches if the element's text includes a substring
- `hasSelector` — matches if a CSS selector finds a match within the element
- Checkbox state — checked vs unchecked
- Fallback — the base `content`/`expanded` fields when no variant matches

### Examples

| State detected | What the assistant says |
|----------------|------------------------|
| Git CLI: Installed (v2.43) | "Git is the foundation — everything below depends on it." |
| Git CLI: Not found | "Git isn't installed. Without it, nothing else in this wizard can work — no repository, no remotes, no .gitignore." |
| .gitignore: 100% coverage | "Your .gitignore looks solid — all recommended patterns are present." |
| .gitignore: missing 3 patterns | "These gaps could leak secrets or build artifacts into your repository." |
| Hooks: 2 active (pre-commit, pre-push) | "You've already got quality gates — these run automatically before code leaves your machine." |
| Hooks: None configured | "No automated checks before commits. You can add a pre-commit hook in the Configure step." |

### Key principle

The assistant text changes based on what the scan actually found. Generic
content ("This row shows your Git CLI status") is a failure mode.

---

## 3. Program-awareness — Where things fit in the bigger picture

Program-awareness is the assistant's understanding of where the current
element fits in the **larger program** — the wizard flow, the modal
hierarchy, the relationship between different setup wizards, and what
comes before and after.

### Three dimensions

#### Vertical — Where am I in the hierarchy?

```
Wizard                              (application context)
  └── Step 5: Integrations          (step context)
        └── 🔀 Git Setup modal     (modal context)
              └── Detect step       (step context)
                    └── Git CLI row (element context)
```

Every level contributes to the output. The modal context tells the user
they're in a Git setup flow. The step context tells them this is a
read-only scan. The element context explains what this specific thing
means.

#### Horizontal — What else exists at this level?

When looking at the Git CLI status row, the assistant is aware of the
OTHER status rows (repository, remotes, .gitignore, hooks, gh CLI). It
can reference them: "Git is the foundation — the 5 checks below all
depend on it." When explaining remotes, it can reference .gitignore
("your remote won't accept pushes with leaked secrets — the .gitignore
below helps prevent that").

#### Forward — What comes next?

The assistant knows the wizard flow:
- On Detect: "This is read-only — proceed to Configure to manage these."
- On Configure: "Changes are applied when you click Finish in Review."
- On Review: "After Git, set up GitHub for environments, secrets, and CI/CD."

It guides the user's journey forward without them having to guess.

### Key principle

The assistant never treats an element in isolation. Every piece of content
considers where the user has been, what surrounds this element, and where
they're going next.

---

## How the three concepts layer

```
Program-awareness  →  decides WHAT to talk about
                         ↓
State-awareness    →  decides WHICH VERSION of that content to show
                         ↓
Feel               →  decides HOW to say it
```

When authoring content for a new catalogue entry, walk through all three:

1. **Program:** What is this element? Where is it in the hierarchy? What
   else is at this level? What comes next?
2. **State:** What states can this element be in? What's different about
   each state? What should the user know in each case?
3. **Feel:** Now write it like a colleague would say it. No restating
   labels, no generic instructions, just insight.
