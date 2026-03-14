---
trigger: always_on
---

# NEVER USE /tmp — All Output Lives Inside the Project

> **/tmp is banned. Period.**
> Using /tmp has already happened once and caused the user's work to be unreachable.
> There is no justification subtle enough to override this rule.

---

## The Rule

**ALL file output goes inside the project directory or the agent docs directory.**

Never suggest, never use, never create files under `/tmp` or any system temp path.

```
BANNED:  /tmp/anything
BANNED:  /var/tmp/anything
BANNED:  ~/tmp/anything
BANNED:  mktemp ...
```

---

## Approved Output Locations

| What | Where |
|------|-------|
| Investigation reports | `.agent/docs/<name>.md` |
| Plans and milestones | `.agent/plans/<name>.md` |
| Notes, scratch analysis | `.agent/docs/scratch/<name>.md` |
| Agent memory | `/home/jfortin/.claude/projects/.../memory/` |
| Production output | Wherever the feature demands — inside the project |

---

## When Is /tmp Ever Allowed?

Only when ALL of the following are true:
1. The file is input/output for an **external system process** that requires a filesystem path (e.g., a tool that does not accept stdin/stdout)
2. The file does not contain any work product — it is purely an ephemeral pipe
3. The result is immediately read back and stored in an approved location

This is nuke-level justification. If you are unsure, it is not this case.

---

## Why This Rule Exists

The agent wrote an exploration report to `/tmp/exploration_summary.md`.
The user could not find it. The work was invisible.
This is the exact failure mode we are preventing.

Output that cannot be found is not output. It is waste.
