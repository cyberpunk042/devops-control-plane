# Git Auth Routes — Authentication Status, SSH Passphrase & HTTPS Token API

> **3 files · 162 lines · 3 endpoints + 1 decorator · Blueprint: `git_auth_bp` · Prefix: `/api`**
>
> Authentication management for git network operations. These routes
> detect the remote type (SSH vs HTTPS), check authentication status,
> accept SSH passphrases (to add keys to ssh-agent), and store HTTPS
> tokens (via git credential helper). Both credential endpoints verify
> end-to-end auth after storing. The package also exports the
> `requires_git_auth` decorator, used by chat sync, pages publish,
> and git operations routes to gate network calls behind auth checks.
> All delegate to `src.core.services.git.auth` (511 lines).

---

## How It Works

### Request Flow

```
Frontend
│
├── auth/_git_auth.html ──────────── Auth panel
│   ├── GET  /api/git/auth-status    (check auth state)
│   ├── POST /api/git/auth-ssh       (provide passphrase)
│   └── POST /api/git/auth-https     (provide token)
│
├── globals/_auth_modal.html ─────── Auth modal (passphrase prompt)
│   └── POST /api/git/auth-ssh       (submit passphrase)
│
└── Other routes using @requires_git_auth:
    ├── chat/sync.py     — chat git sync, chat push
    ├── integrations/git.py — git push, git pull
    └── pages/api.py     — pages publish
     │
     ▼
routes/git_auth/                       ← HTTP layer (this package)
├── __init__.py      — blueprint definition
├── helpers.py       — @requires_git_auth decorator
└── credentials.py   — 3 credential endpoints
     │
     ▼
core/services/git/auth.py (511 lines) ← Business logic
├── detect_remote_type()     — SSH vs HTTPS from remote URL
├── get_remote_url()         — read origin remote URL  
├── find_ssh_key()           — find ~/.ssh/id_* key
├── key_has_passphrase()     — check if key is encrypted
├── check_auth()             — full auth status check
├── add_ssh_key()            — add key to ssh-agent
├── add_https_credentials()  — store token via git credential
├── git_env()                — env dict for subprocess calls
├── is_auth_ok()             — session auth state
└── is_auth_tested()         — whether auth was tested
```

### Auth Check Pipeline (SSH Remote)

```
GET /api/git/auth-status
     │
     ▼
git_auth.check_auth(root)
     │
     ├── 1. detect_remote_type(root)
     │   git remote get-url origin → "git@github.com:user/repo.git"
     │   → "ssh"
     │
     ├── 2. find_ssh_key()
     │   ~/.ssh/ → id_ed25519, id_rsa, id_ecdsa, id_dsa
     │   (first found)
     │
     ├── 3. Check ssh-agent:
     │   _agent_has_keys()
     │   ├── Check managed agent (_ssh_agent_env)
     │   │   ssh-add -l → "2048 SHA256:... key (RSA)"
     │   │   → keys loaded → { ok: true }
     │   │
     │   └── Check inherited agent (SSH_AUTH_SOCK env)
     │       ssh-add -l → check if keys listed
     │
     ├── 4. If no agent keys, check if key needs passphrase:
     │   key_has_passphrase(key_path)
     │   ssh-keygen -y -P "" -f ~/.ssh/id_ed25519
     │   ├── Succeeds (exit 0) → key has no passphrase → ok
     │   └── Fails (exit 1)    → key is encrypted → needs passphrase
     │
     └── 5. Result:
         ├── Agent has keys                → { ok: true, needs: null }
         ├── Key has no passphrase         → { ok: true, needs: null }
         └── Key encrypted, no agent keys  → { ok: false, needs: "ssh_passphrase" }
```

### Auth Check Pipeline (HTTPS Remote)

```
GET /api/git/auth-status
     │
     ▼
git_auth.check_auth(root)
     │
     ├── 1. detect_remote_type(root)
     │   git remote get-url origin → "https://github.com/user/repo.git"
     │   → "https"
     │
     ├── 2. Network test:
     │   git ls-remote --exit-code origin HEAD
     │   env=git_env()  (includes stored credentials)
     │   timeout=8s
     │
     └── 3. Result:
         ├── Exit 0               → { ok: true, needs: null }
         ├── 401/403/credential   → { ok: false, needs: "https_credentials" }
         └── Timeout              → { ok: false, needs: "https_credentials" }
                                    "Connection timed out (credential prompt likely hanging)"
```

### SSH Passphrase Submission Pipeline

```
POST /api/git/auth-ssh  { passphrase: "my-secret" }
     │
     ▼
git_auth.add_ssh_key(root, "my-secret")
     │
     ├── 1. find_ssh_key() → ~/.ssh/id_ed25519
     │
     ├── 2. Ensure ssh-agent is running:
     │   ├── _detect_existing_agent()
     │   │   Check SSH_AUTH_SOCK → ssh-add -l → keys loaded?
     │   │
     │   └── _start_ssh_agent()  (if no existing agent)
     │       ssh-agent -s → parse SSH_AUTH_SOCK, SSH_AGENT_PID
     │
     ├── 3. Create temporary askpass script:
     │   /tmp/scp_askpass_XXXXX.sh
     │   #!/bin/sh
     │   echo 'my-secret'
     │   chmod 700
     │
     ├── 4. Add key via SSH_ASKPASS:
     │   env = { ...os.environ, ...agent_env,
     │           SSH_ASKPASS: /tmp/scp_askpass_XXXXX.sh,
     │           SSH_ASKPASS_REQUIRE: force,
     │           DISPLAY: :0 }
     │   ssh-add ~/.ssh/id_ed25519
     │   stdin=DEVNULL  (forces SSH_ASKPASS usage)
     │   timeout=10s
     │
     ├── 5. Cleanup: delete askpass script (finally block)
     │
     └── 6. On success → set _auth_ok = True
     │
     ▼
Route layer: verify end-to-end
     │
     └── check_auth(root)
         ├── OK → return { ok: true }
         └── FAIL → return { ok: false, error: "Key added but auth still failing: ..." }
```

### HTTPS Token Submission Pipeline

```
POST /api/git/auth-https  { token: "ghp_abc123..." }
     │
     ▼
git_auth.add_https_credentials(root, "ghp_abc123...")
     │
     ├── 1. get_remote_url(root)
     │   → "https://github.com/user/repo.git"
     │
     ├── 2. Parse host from URL:
     │   urlparse() → hostname → "github.com"
     │
     ├── 3. Configure credential helper:
     │   git config credential.helper store
     │
     ├── 4. Store credential:
     │   git credential approve
     │   stdin: protocol=https\nhost=github.com\n
     │          username=x-access-token\npassword=ghp_abc123...\n
     │
     └── 5. On success → set _auth_ok = True
     │
     ▼
Route layer: verify end-to-end
     │
     └── check_auth(root)
         ├── OK → return { ok: true }
         └── FAIL → return { ok: false, error: "Credentials stored but auth still failing: ..." }
```

### requires_git_auth Decorator Flow

```
Any route decorated with @requires_git_auth:

    @bp.route("/git/push", methods=["POST"])
    @requires_git_auth
    @run_tracked("git", "git:push")
    def git_push():
        ...

Request arrives:
     │
     ├── is_auth_ok()?
     │   ├── YES → proceed to handler → normal response
     │   │
     │   └── NO → gate the request:
     │       ├── check_auth(root) → get detailed status
     │       ├── bus.publish("auth:needed", key="git", data=status)
     │       │   (SSE event → triggers auth modal in browser)
     │       └── return 401 with status JSON
```

---

## File Map

```
routes/git_auth/
├── __init__.py       18 lines — blueprint definition + sub-module imports
├── helpers.py        56 lines — @requires_git_auth decorator
├── credentials.py    88 lines — 3 credential endpoints
└── README.md                  — this file
```

Core business logic: `core/services/git/auth.py` (511 lines).
Backward-compat shim: `core/services/git_auth.py` (21 lines, re-exports).

---

## Per-File Documentation

### `__init__.py` — Blueprint Definition (18 lines)

```python
git_auth_bp = Blueprint("git_auth", __name__)

from . import helpers, credentials  # register routes + decorator
```

### `helpers.py` — @requires_git_auth Decorator (56 lines)

| Export | Type | What It Does |
|--------|------|-------------|
| `requires_git_auth` | Decorator | Gates routes that hit git remotes |

```python
def requires_git_auth(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if is_auth_ok():
            return fn(*args, **kwargs)

        # Auth not ready — gather details & notify client via SSE
        try:
            root = Path(current_app.config["PROJECT_ROOT"])
            status = check_auth(root)
        except Exception:
            status = {"ok": False, "needs": "ssh_passphrase"}

        try:
            from src.core.services.event_bus import bus
            bus.publish("auth:needed", key="git", data=status)
        except Exception:
            logger.debug("EventBus publish failed (non-fatal)")

        return jsonify(status), 401
    return wrapper
```

**Three-step gate:**
1. Fast path: `is_auth_ok()` checks cached session state (no I/O)
2. Slow path: `check_auth()` runs detection (agent check or network test)
3. SSE notification: `bus.publish("auth:needed")` triggers the auth modal

**Routes using this decorator:**

| Route Module | Endpoint | Why It Needs Auth |
|-------------|----------|-------------------|
| `chat/sync.py` | `POST /chat/sync`, `POST /chat/push` | Git push/pull for chat sync |
| `integrations/git.py` | `POST /git/push`, `POST /git/pull` | Git operations |
| `pages/api.py` | `POST /pages/publish` | Git push for site deployment |

### `credentials.py` — Credential Endpoints (88 lines)

| Function | Method | Route | What It Does |
|----------|--------|-------|-------------|
| `auth_status()` | GET | `/git/auth-status` | Check git auth state |
| `auth_ssh()` | POST | `/git/auth-ssh` | Provide SSH passphrase |
| `auth_https()` | POST | `/git/auth-https` | Provide HTTPS token |

**Auth status — simple delegation:**

```python
@git_auth_bp.route("/git/auth-status")
def auth_status():
    try:
        root = _project_root()
        result = check_auth(root)
        return jsonify(result)
    except Exception as e:
        logger.exception("Failed to check git auth")
        return jsonify({"ok": False, "error": str(e)}), 500
```

**SSH passphrase — submit + verify pattern:**

```python
result = add_ssh_key(root, passphrase)

# If successful, verify it actually works end-to-end
if result.get("ok"):
    verify = check_auth(root)
    if not verify.get("ok"):
        result = {
            "ok": False,
            "error": "Key added but auth still failing: " + (verify.get("error") or "")
        }
```

The verify step catches cases where the key was successfully added
to ssh-agent but the remote still rejects it (wrong key for the repo).

**HTTPS token — same submit + verify pattern:**

```python
result = add_https_credentials(root, token)

if result.get("ok"):
    verify = check_auth(root)
    if not verify.get("ok"):
        result = {
            "ok": False,
            "error": "Credentials stored but auth still failing: " + (verify.get("error") or "")
        }
```

---

## Dependency Graph

```
__init__.py
└── Imports: helpers, credentials

helpers.py
├── git.auth          ← check_auth, is_auth_ok (eager)
├── event_bus         ← bus.publish (lazy, inside wrapper)
└── flask             ← current_app, jsonify

credentials.py
├── git.auth          ← check_auth, add_ssh_key, add_https_credentials (eager)
└── helpers           ← project_root
```

**Core service internals (git/auth.py, 511 lines):**

```
git/auth.py
├── Module-level state (cached for server lifetime):
│   ├── _ssh_agent_env: dict     — managed agent env vars
│   ├── _auth_tested: bool       — whether check_auth was called
│   └── _auth_ok: bool           — whether auth is working
│
├── Detection:
│   ├── detect_remote_type()     — SSH/HTTPS/unknown (line 42-53)
│   ├── get_remote_url()         — git remote get-url origin (line 56-65)
│   ├── find_ssh_key()           — ~/.ssh/id_* search (line 68-75)
│   └── key_has_passphrase()     — ssh-keygen -y -P "" test (line 78-91)
│
├── Auth check:
│   ├── check_auth()             — full status (line 99-221)
│   ├── _agent_has_keys()        — ssh-add -l check (line 224-254)
│   └── _classify_error()        — error → needs mapping (line 257-303)
│
├── SSH agent management:
│   ├── _detect_existing_agent() — find running agent (line 311-333)
│   ├── _start_ssh_agent()       — ssh-agent -s (line 336-361)
│   └── add_ssh_key()            — SSH_ASKPASS method (line 364-428)
│
├── HTTPS credentials:
│   └── add_https_credentials()  — git credential approve (line 436-482)
│
└── Env + state:
    ├── git_env()                — env dict for subprocess (line 490-500)
    ├── is_auth_ok()             — cached state (line 503-505)
    └── is_auth_tested()         — checked state (line 508-510)
```

---

## Consumers

| Layer | Module | What It Uses |
|-------|--------|-------------|
| Server | `ui/web/server.py` | Imports `git_auth_bp`, registers at `/api` prefix |
| Auth panel | `scripts/auth/_git_auth.html` | `/git/auth-status`, `/git/auth-ssh`, `/git/auth-https` |
| Auth modal | `scripts/globals/_auth_modal.html` | `/git/auth-ssh` (passphrase submission) |
| Chat sync | `routes/chat/sync.py` | `@requires_git_auth` decorator |
| Git ops | `routes/integrations/git.py` | `@requires_git_auth` decorator |
| Pages publish | `routes/pages/api.py` | `@requires_git_auth` decorator |
| Helpers | `ui/web/helpers.py` | Re-exports `requires_git_auth` for convenience |

---

## Service Delegation Map

```
Route Handler            →   Core Service Function
──────────────────────────────────────────────────────────────────
auth_status()            →   git.auth.check_auth(root)
                               ├→ detect_remote_type()
                               ├→ get_remote_url()
                               ├→ find_ssh_key()
                               ├→ _agent_has_keys() or git ls-remote
                               └→ _classify_error() (if failure)

auth_ssh()               →   git.auth.add_ssh_key(root, passphrase)
                               ├→ find_ssh_key()
                               ├→ _detect_existing_agent() or _start_ssh_agent()
                               ├→ create temp askpass script
                               ├→ ssh-add (with SSH_ASKPASS)
                               └→ cleanup askpass script

                         →   git.auth.check_auth(root)  (verify)

auth_https()             →   git.auth.add_https_credentials(root, token)
                               ├→ get_remote_url()
                               ├→ urlparse() → hostname
                               ├→ git config credential.helper store
                               └→ git credential approve

                         →   git.auth.check_auth(root)  (verify)

@requires_git_auth       →   git.auth.is_auth_ok()     (fast path)
                         →   git.auth.check_auth(root)  (slow path)
                         →   event_bus.publish("auth:needed")  (SSE notify)
```

---

## Data Shapes

### `GET /api/git/auth-status` response (SSH — keys loaded)

```json
{
    "ok": true,
    "remote_type": "ssh",
    "remote_url": "git@github.com:user/repo.git",
    "ssh_key": "id_ed25519",
    "needs": null,
    "error": null
}
```

### `GET /api/git/auth-status` response (SSH — needs passphrase)

```json
{
    "ok": false,
    "remote_type": "ssh",
    "remote_url": "git@github.com:user/repo.git",
    "ssh_key": "id_ed25519",
    "needs": "ssh_passphrase",
    "error": "SSH key requires passphrase (no loaded agent key found)"
}
```

### `GET /api/git/auth-status` response (HTTPS — needs token)

```json
{
    "ok": false,
    "remote_type": "https",
    "remote_url": "https://github.com/user/repo.git",
    "ssh_key": null,
    "needs": "https_credentials",
    "error": "Authentication failed for 'https://github.com/user/repo.git'"
}
```

### `GET /api/git/auth-status` response (HTTPS — timeout)

```json
{
    "ok": false,
    "remote_type": "https",
    "remote_url": "https://github.com/user/repo.git",
    "ssh_key": null,
    "needs": "https_credentials",
    "error": "Connection timed out (credential prompt likely hanging)"
}
```

### `GET /api/git/auth-status` response (unknown remote)

```json
{
    "ok": false,
    "remote_type": "unknown",
    "remote_url": "",
    "ssh_key": null,
    "needs": null,
    "error": "Unknown remote type"
}
```

### `POST /api/git/auth-ssh` request + response (success)

```json
// Request:
{ "passphrase": "my-ssh-key-passphrase" }

// Response:
{ "ok": true }
```

### `POST /api/git/auth-ssh` response (wrong passphrase)

```json
{ "ok": false, "error": "Wrong passphrase" }
```

### `POST /api/git/auth-ssh` response (key added but auth fails)

```json
{
    "ok": false,
    "error": "Key added but auth still failing: Permission denied (publickey)"
}
```

### `POST /api/git/auth-ssh` response (no key found)

```json
{ "ok": false, "error": "No SSH key found in ~/.ssh/" }
```

### `POST /api/git/auth-https` request + response (success)

```json
// Request:
{ "token": "ghp_abc123def456..." }

// Response:
{ "ok": true }
```

### `POST /api/git/auth-https` response (credentials stored but failing)

```json
{
    "ok": false,
    "error": "Credentials stored but auth still failing: Authentication failed"
}
```

### `requires_git_auth` — 401 response

```json
{
    "ok": false,
    "remote_type": "ssh",
    "remote_url": "git@github.com:user/repo.git",
    "ssh_key": "id_ed25519",
    "needs": "ssh_passphrase",
    "error": "SSH key requires passphrase (no loaded agent key found)"
}
```

Plus SSE side-effect: `event: auth:needed` published on the bus.

---

## Advanced Feature Showcase

### 1. SSH_ASKPASS Non-Interactive Passphrase

The SSH passphrase is provided without a terminal prompt using the
`SSH_ASKPASS` mechanism:

```python
# Create temporary script that echoes the passphrase
askpass_fd, askpass_path = tempfile.mkstemp(suffix=".sh", prefix="scp_askpass_")
with os.fdopen(askpass_fd, "w") as f:
    safe_pp = passphrase.replace("'", "'\\''")  # escape single quotes
    f.write(f"#!/bin/sh\necho '{safe_pp}'\n")
os.chmod(askpass_path, 0o700)

env["SSH_ASKPASS"] = askpass_path
env["SSH_ASKPASS_REQUIRE"] = "force"  # force even when terminal exists
env["DISPLAY"] = ":0"                # required by SSH_ASKPASS

subprocess.run(
    ["ssh-add", str(key_path)],
    stdin=subprocess.DEVNULL,  # force SSH_ASKPASS usage (no terminal)
    env=env, ...
)
```

The script is deleted in a `finally` block — passphrase never persists
on disk beyond the `ssh-add` call.

### 2. Submit + Verify Pattern

Both credential endpoints verify end-to-end after storing:

```python
result = add_ssh_key(root, passphrase)    # store credential
if result.get("ok"):
    verify = check_auth(root)             # verify it works
    if not verify.get("ok"):
        result = {"ok": False, "error": "Key added but auth still failing: ..."}
```

This catches mismatches: key successfully added to agent but
rejected by the remote (wrong key pair, access revoked, etc.).

### 3. SSE-Driven Auth Modal

The decorator publishes `auth:needed` events via the EventBus:

```python
from src.core.services.event_bus import bus
bus.publish("auth:needed", key="git", data=status)
```

The frontend listens for this event on the SSE stream and
reactively shows the passphrase modal. This means any route
that needs auth (chat sync, git push, pages publish) can trigger
the auth prompt without each route having to implement it.

### 4. Agent Reuse

Before starting a new agent, the system checks for an existing one:

```python
# Try existing agent first
if not _ssh_agent_env:
    _ssh_agent_env = _detect_existing_agent()

# Start a new agent if needed
if not _ssh_agent_env:
    _ssh_agent_env = _start_ssh_agent()
```

This avoids spawning multiple agents and reuses any agent the
user started before launching the control plane.

### 5. Error Classification

Git network errors are classified to determine what the user needs:

```python
def _classify_error(stderr, remote_type, remote_url, ssh_key):
    lower = stderr.lower()

    if remote_type == "ssh":
        if any(s in lower for s in (
            "permission denied", "publickey", "host key",
            "could not read", "no such identity",
        )):
            return {"needs": "ssh_passphrase", ...}

    elif remote_type == "https":
        if any(s in lower for s in (
            "authentication", "403", "401", "credential",
            "could not read username",
        )):
            return {"needs": "https_credentials", ...}
```

### 6. Session-Lifetime Caching

Auth state is cached at module level for the server's lifetime:

```python
_ssh_agent_env: dict[str, str] = {}  # agent env vars
_auth_tested: bool = False           # check_auth was called
_auth_ok: bool = False               # auth is working
```

The `is_auth_ok()` fast path in `@requires_git_auth` avoids
running subprocess checks on every protected request.

---

## Design Decisions

### Why submit + verify instead of just submit

Storing a credential can succeed while authentication still fails.
Cases include: wrong key pair, expired token, revoked access,
misconfigured remote. The verify step catches these immediately
instead of letting the user discover them during a push/pull.

### Why the decorator publishes on the EventBus

Using SSE for auth notifications decouples the auth prompt from
individual routes. Any route can trigger auth without knowing
how the frontend displays the prompt. The frontend subscribes
once and handles all `auth:needed` events uniformly.

### Why SSH detection avoids network calls

SSH auth check uses only local operations (ssh-add -l, ssh-keygen -y).
Network-based checks (`git ls-remote`) would hang if the SSH key
needs a passphrase — the git process waits for terminal input that
never comes in a headless web server context.

### Why HTTPS detection uses git ls-remote

HTTPS credentials can't be verified locally. The only way to confirm
they work is to make a real network request. `git ls-remote --exit-code
origin HEAD` is the lightest possible git network operation (fetches
only one ref).

### Why askpass script is a tempfile, not in-memory

`ssh-add` reads the passphrase via the `SSH_ASKPASS` program, which
must be an executable file path. There's no API to pass a passphrase
directly. The tempfile pattern (create → chmod 700 → use → delete)
is the standard secure approach.

### Why x-access-token is the HTTPS username

```python
f"username=x-access-token\n"
f"password={token}\n"
```

GitHub (and other providers) expect `x-access-token` as the
username when using a Personal Access Token (PAT) instead of
a password. This is the documented GitHub authentication format.

---

## Coverage Summary

| Capability | Endpoint | Method | Auth Required |
|-----------|----------|--------|---------------|
| Auth status check | `/git/auth-status` | GET | No |
| SSH passphrase | `/git/auth-ssh` | POST | No |
| HTTPS token | `/git/auth-https` | POST | No |
| Auth gate (decorator) | N/A | N/A | N/A (provides auth for others) |
