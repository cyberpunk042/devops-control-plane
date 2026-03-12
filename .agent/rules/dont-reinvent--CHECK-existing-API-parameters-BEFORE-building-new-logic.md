---
trigger: always_on
---

# DON'T REINVENT — Check What Exists Before Building

## The Trigger

You are about to write new code. **STOP.** Answer these FIRST:

### 1. Am I calling an API or function?

Open its source. **LIST its parameters out loud:**

```
The function accepts: param1, param2, recursive=False, format='json'
```

If you can't list them → you haven't read it → READ IT NOW.

### 2. Do those parameters already solve my problem?

Compare what the API offers with what you're about to build.
If `?recursive=true` exists → you don't need a directory-walking loop.
If `format='tree'` exists → you don't need a tree-builder.

**Write zero code. Pass the parameter. You are done.**

### 3. Am I writing a loop that makes API calls?

**STOP.** You are almost certainly doing it wrong.
Check for batch, recursive, or bulk modes first.
If none exist → ask the user if we should add it server-side.

50 sequential HTTP requests to walk a tree that the server can
flatten in one call is not a "different approach." It is negligence.

## Why This Exists

An AI wrote a 50-request directory-walking loop.
The API it was calling had `?recursive=true` the entire time.
The AI had READ that API earlier in the same session.
It still built the loop because it never asked: "does this already exist?"

**Reading an API and then ignoring its capabilities is WORSE than not reading it.**
