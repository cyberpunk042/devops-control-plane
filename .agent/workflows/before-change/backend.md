---
description: Backend-specific pre-flight checklist for Python code changes
---

# Before Backend Python Changes

> **ALSO READ:** `before-change/common.md` (applies to ALL changes)
> This checklist covers backend-specific concerns.

---

## Architecture Reminder

```
.env (local) → Admin Panel Tiers → GitHub Secrets/Variables → cron.yml → CLI commands
```

**The Server Pattern (NO EXCEPTIONS):**
`server.py` is a thin HTTP wrapper over CLI commands. It NEVER imports domain logic.

```python
# ✅ CORRECT — subprocess to CLI
result = subprocess.run(["python", "-m", "src.main", "some-command", "--json"],
                        cwd=str(project_root), capture_output=True, text=True,
                        timeout=15, env=_fresh_env())

# ❌ WRONG — importing domain code into server
from ..some_module import SomeManager
```

**The GitHub Integration Pattern:**
Everything uses the `gh` CLI. NEVER use raw REST API with httpx/requests.

```python
# ✅ CORRECT
subprocess.run(["gh", "secret", "set", name, "-R", repo], input=value, ...)

# ❌ WRONG
httpx.put(f"https://api.github.com/repos/{repo}/actions/secrets/{name}", ...)
```

---

## Backend Checklist

### 1. Configuration Flow
- [ ] Is every new env var in the correct tier? (`GITHUB_SECRETS`, `GITHUB_VARS`, or `LOCAL_ONLY`)
- [ ] Is the env var injected in `cron.yml` if the pipeline needs it?
- [ ] Does the `SYNCABLE_SECRETS` list match what `cron.yml` actually injects?

### 2. Server Pattern
- [ ] Does `server.py` ONLY use subprocess calls? No domain imports?
- [ ] Does the CLI command exist in `main.py`?

### 3. Pipeline
- [ ] Does `cron.yml` have a step for this feature if it needs to run automatically?
- [ ] Are all required secrets/variables listed in that step's `env:` block?

---

## Key File Locations

| What | Where |
|------|-------|
| Secret tiers | `src/admin/static/index.html` ~line 1759 |
| Pipeline secrets injection | `.github/workflows/cron.yml` env blocks |
| Syncable secrets list | `src/mirror/github_sync.py` SYNCABLE_SECRETS |
| Server endpoints | `src/admin/server.py` |
| CLI commands | `src/main.py` |

## Backend-Specific Mistakes

1. **Adding a secret but not putting it in the right tier** → shows "Local only"
2. **Using httpx/REST API instead of gh CLI** → phantom dependencies
3. **Not adding a cron.yml step** → feature only works locally
4. **Not matching SYNCABLE_SECRETS to cron.yml** → mirror missing secrets
5. **Modifying vault without understanding session lifecycle** → see `src/admin/vault.py`
