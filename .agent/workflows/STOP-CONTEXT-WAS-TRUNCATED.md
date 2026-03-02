---
description: MANDATORY — when checkpoint/context loss detected, STOP and report to user. Do NOT self-orient. Do NOT act. WAIT.
---

# ⛔ CONTEXT WAS TRUNCATED — FULL STOP

## What Just Happened

Your conversation history was compressed. A checkpoint summary replaced the
actual conversation. **Your understanding is now DEGRADED.**

You do not know:
- What the user was working on at the exact moment of truncation
- What nuances were discussed that the summary missed
- What instructions were given that got compressed away
- What the user's current intent is

## Your ONLY Response

Say this and NOTHING ELSE:

> ⚠️ **My context was just truncated.** The conversation was compressed and I've
> lost detailed context. I need you to tell me where we are and what you want
> me to do before I can act safely.

## What You Must NOT Do

- ❌ Do NOT read files
- ❌ Do NOT view code
- ❌ Do NOT take any action
- ❌ Do NOT try to "figure out" what the user wants from the summary
- ❌ Do NOT continue where the summary says you left off
- ❌ Do NOT ask vague questions like "what do you want to do?"
- ❌ Do NOT use open tabs/documents to guess context (that is INTRUSIVITY)

## Why This Exists

Every single time the AI has tried to self-orient after truncation, it has:
1. Latched onto stale fragments from the summary
2. Taken action based on wrong understanding
3. Caused damage that the user had to spend energy fixing

The pattern has been documented across 13 post-mortems. The root cause is
always the same: **the AI acts when it should STOP.**

## How to Detect Truncation

You are in a truncated state if ANY of these are true:
- Your conversation starts with `{{ CHECKPOINT }}` or a summary block
- The conversation says "earlier parts have been truncated"
- You have no memory of the conversation building up naturally
- The first message contains a "Previous Session Summary"

## The User Drives

After you announce the truncation:
1. The **user** will tell you what they're working on
2. The **user** will tell you what to do next
3. The **user** will point you to the relevant files and context
4. You follow the user's direction — you do NOT lead

This is not optional. This is not a suggestion. This is a HARD STOP.
