# Milestone 5 — Proactive Intelligence
> Status: SCAFFOLDED — not yet discussed in detail

---

## Goal
The platform stops being purely reactive.
Connect the signals produced by M1-M4 to the existing notification system.
Let the platform reach out when things need attention — without being noise.

---

## Evolutions included

### E11 — Notification System — Signal Connection
The notification system already exists but is underutilized.
This milestone connects real signals to it — and makes it configurable.

**Track 1 — Connect existing signals:**
- Package CVEs detected (E1/E2)
- Vault not rotated in N days (existing vault)
- Stack entering EOL in N days (E8)
- Tool entering DEPRECATED state (E3)
- Health/readiness score drops below threshold (E9)
- Promotion pipeline gate failed (E5)
- Dependency graph blast radius warning triggered (E10)

**Track 2 — Configurable digest:**
- Daily / weekly digest option
- On-event for critical signals only
- Per-signal threshold configuration
- User controls what reaches them and at what level

---

## What this milestone does NOT include
- No new data collection — reads signals produced by M1-M4
- Not a new notification system — extends what already exists

---

## Dependencies
- M1: security posture signals (E7)
- M2: CVE and dependency signals (E1, E10)
- M3: tool/stack lifecycle signals (E3, E8)
- M4: readiness, promotion, and release signals (E9, E5, E4)

## Unlocks
- Nothing downstream — this is the final layer

---

## Open questions
- [ ] What notification channels does the existing system support? (web panel only? email? webhook?)
- [ ] Which signals are critical (always notify) vs. configurable?
- [ ] What does the digest UI look like in the web panel?
- [ ] Is there a signal priority/severity model?
- [ ] How does the user configure thresholds? (per project? per environment?)

---

## Rough scope estimate
- Primarily backend: signal routing layer connecting M1-M4 outputs to notification system
- Frontend: notification preferences UI + digest view
- Relatively contained — the hard work is in M1-M4 producing the signals
