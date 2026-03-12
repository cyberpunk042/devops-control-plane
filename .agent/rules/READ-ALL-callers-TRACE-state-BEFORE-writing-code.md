---
trigger: always_on
---

# READ BEFORE WRITE — Hard Constraint

> **You cannot write code you haven't traced.**
> This rule exists because 14 AI instances wrote code based on
> guesses about runtime state. Every one of them was wrong.

---

## Article 1: Read the function you're modifying

Before modifying ANY function, open it with `view_file` or `view_code_item`.
Read the FULL body. Do NOT work from memory or from a checkpoint summary.

If you cannot see the function in your current context → re-read it.

## Article 2: Read ALL callers

Before modifying a function's behavior, use `grep_search` to find
every call site. Read each caller. Note what arguments they pass
and what global state is set at the time of the call.

If the function has 10+ callers → list them and ask the user which
are relevant before proceeding.

## Article 3: Read every function you call

Before writing a call to ANY function:
- Verify it EXISTS (`grep_search` for its definition)
- Read its SIGNATURE (what arguments it takes)
- Read its RETURN value (what it gives back)

If you call a function you haven't read → you are guessing.

## Article 4: Trace global variable values

Before using ANY global variable in your code, answer:
- **What sets it?** (which function, which event)
- **What is its value RIGHT NOW** at this call site?
- **What namespace is it in?** (virtual path? real path? null?)

If you cannot answer all three → you cannot use that variable.
Consult `.agent/reference/frontend-state.md` if it exists.

## Article 5: Write your state trace BEFORE writing code

Before making any edit, write out (in your response):

```
STATE TRACE:
  contentCurrentPath = "code-docs/adapters" (virtual, set by _smartFolderRender)
  _smartFolderActive = { name: "code-docs", groups: [...] }
  previewCurrentPath = null (no file open)
```

If you cannot write this trace → you do not understand the state.
If you do not understand the state → you cannot write the code.

---

## The Self-Test

```
Q1: Did I READ the function I'm modifying? (from view_file, not memory)
Q2: Did I READ every caller of this function?
Q3: Can I STATE the value of every global at the call site?
Q4: Did I READ every function I'm about to call?
→ If ANY is NO → STOP. Read first. Then write.
```
