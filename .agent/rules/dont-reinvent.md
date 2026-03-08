# DON'T REINVENT — Hard Constraint

> **The server already does it. You just didn't bother to look.**
> An AI wrote 50 HTTP requests in a loop to walk a directory tree.
> The API it was calling had `?recursive=true` the entire time.
> It had even READ that API earlier in the same session.
> It still built the loop. Because it never asked: "does this already exist?"

---

## The Disease

You are about to write new code. You feel productive. You're solving
the problem. You're building something.

**STOP.**

You are not solving anything. You are duplicating what already exists
because you are too lazy — or too eager — to check first.

This is the most expensive kind of bug: code that WORKS but shouldn't
EXIST. It works today, costs nothing today, and creates 50 network
requests, a maintenance burden, and a confused developer tomorrow.

---

## Article 1: Before building, research

Before writing ANY new logic that interacts with an existing system
(API endpoint, utility function, library, service):

1. **READ the full interface** — every parameter, every flag, every mode
2. **ASK: does this already solve my problem?**
3. If YES → use it. You are done. You wrote zero lines of code. Good.
4. If NO → now you may build. Not before.

## Article 2: The client does NOT do what the server already does

If a server endpoint can do something with a parameter:
- The client does NOT reimplement it in JavaScript
- The client does NOT loop over partial results to simulate it
- The client passes the parameter. That's it.

50 sequential HTTP requests to walk a tree that the server can
flatten in one call is not "a different approach." It is negligence.

## Article 3: One call > N calls. Always.

If you find yourself writing a loop that makes API calls:
- **STOP.** You are almost certainly doing it wrong.
- Check if the API supports batch, recursive, or bulk modes.
- If it doesn't, ask the user if we should ADD that capability
  server-side rather than brute-forcing it client-side.

N+1 query problems are not just a database concept.
They are an AI-writes-bad-code concept too.

## Article 4: "I read it earlier" is not "I used what I read"

Reading an API's source code and then ignoring its capabilities
is WORSE than not reading it at all. It means you processed the
text but did not extract the information.

When you read an API, you must answer:
- What parameters does it accept?
- What modes does it support?
- What does it already do that I'm about to rebuild?

If you cannot answer these → you did not read it. You skimmed it.

---

## The Self-Test

```
Q1: Am I writing new code that calls an existing API/function?
    → Did I read its FULL interface? Every parameter?
Q2: Does the API already do what I'm about to build?
    → If yes → USE IT. Write zero code.
Q3: Am I writing a loop that makes API calls?
    → STOP. Check for batch/recursive/bulk modes first.
Q4: Did I read this API earlier in this session?
    → Then I have NO excuse. The information was in front of me.
```
