# Tool Health & Dashboard Redesign — Plan

> Created: 2026-02-18  
> Status: **Parked — needs scoping session**  
> Triggered by: `pip` detection bug during audit data enrichment

---

## 1. Problem Statement

Tool availability detection is **unreliable and scattered**:

1. **Detection lies**: `shutil.which("pip")` returns True inside venv but
   `subprocess.run(["pip", ...])` fails because PATH isn't inherited
   properly.  This affects ALL cards using the `shutil.which → subprocess`
   pattern.

2. **No unified view**: Tool health is fragmented across `wiz:detect`,
   `audit:system`, and individual card silently failing.

3. **No actionability**: When a tool is missing, cards show empty data
   instead of saying "install X to enable this".  Some tools could even
   be installed via `sudo apt install` or `pip install` — the system
   already has some install capabilities but they aren't surfaced.

4. **Dashboard clutter**: Irrelevant cards take up space.  No clear
   division between "healthy", "needs attention", and "not available".

---

## 2. Issues to Address

### 2.1. Detection reliability

| Issue | Affected pattern | Fix needed |
|---|---|---|
| `shutil.which` lies in venv context | All `_detect_*` functions | Validate with actual `subprocess.run([cli, "--version"])` |
| No distinction between "installed" and "functional" | All CLI-dependent cards | Two-tier check: installed → can execute |
| PATH inheritance in subprocess | `package_actions.py`, `testing_ops.py`, etc. | Use `sys.executable` for Python tools, full paths for system tools |

### 2.2. Cards that need "tool missing" messaging

| Card | CLI needed | Current behavior when missing |
|---|---|---|
| packages | pip, npm, cargo, etc. | Shows manager detected, 0 packages |
| testing | pytest | Shows framework detected, can't run |
| quality | ruff, mypy, eslint, etc. | Shows tool not available (this one is OK) |
| docker | docker | Shows empty |
| k8s | kubectl, helm | Shows empty |
| terraform | terraform | Shows empty |
| dns | dig, nslookup | Shows empty |
| security | pip-audit, npm audit | Shows empty |
| git/github | git, gh | Partially handled |

### 2.3. Dashboard redesign needs

- [ ] "System Health" card at top: key tools status with install actions
- [ ] Better card grouping: Core (git, env, packages) → CI/CD → Infra → Audit
- [ ] Cards should show "requires: kubectl" when tool is missing
- [ ] Dismiss/hide irrelevant cards (no k8s? hide k8s card)
- [ ] Quick install actions for common tools

---

## 3. Scope Boundaries

This is **NOT** part of the current audit data enrichment task.
This needs its own scoping session to determine:

- What belongs on the dashboard vs. a dedicated "System Health" page
- Which tools should the app auto-install vs. just detect
- How to handle venv vs. system Python tools
- Priority vs. other work

---

## 4. Quick Fixes (can be done now if needed)

1. **Fix `pip` PATH**: Use `sys.executable -m pip` instead of bare `pip`
   for Python package operations.  This is the only reliable way.
2. **Fix subprocess PATH**: Pass `env={**os.environ, "PATH": ...}` to
   subprocess calls to ensure venv bin is included.

---

## 5. Dependencies

- Audit data enrichment (current task) — blocked for `packages` card
  enrichment until pip detection is fixed
- Dashboard UX redesign — separate initiative
- Tool install backend — partially exists, needs review
