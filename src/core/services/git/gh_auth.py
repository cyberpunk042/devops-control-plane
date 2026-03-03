"""
GitHub CLI authentication — login, logout, token, device flow.

Channel-independent: no Flask or HTTP dependency.
Handles token-based auth, interactive terminal auth, and
browser-based device flow auth.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from src.core.services.git.ops import run_gh

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
#  Login / Logout / Token
# ═══════════════════════════════════════════════════════════════════


def gh_auth_logout(project_root: Path) -> dict:
    """Logout from GitHub CLI."""
    if not shutil.which("gh"):
        return {"error": "gh CLI not installed"}

    # Determine current hostname
    r_host = run_gh("auth", "status", cwd=project_root)
    # Default to github.com
    hostname = "github.com"

    r = run_gh(
        "auth", "logout", "--hostname", hostname,
        cwd=project_root, timeout=10,
        stdin="Y\n",  # confirm logout
    )
    if r.returncode != 0:
        err = r.stderr.strip()
        # "not logged in" is success for us
        if "not logged in" in err.lower():
            return {"ok": True, "message": "Already logged out"}
        return {"error": f"Logout failed: {err}"}

    return {"ok": True, "message": f"Logged out from {hostname}"}


def gh_auth_login(
    project_root: Path,
    *,
    token: str = "",
    hostname: str = "github.com",
    auto_drive: bool = False,
) -> dict:
    """Authenticate with GitHub CLI.

    Three modes:
    1. **Token mode** (token="ghp_…"): Pipes the token to
       ``gh auth login --with-token`` — non-interactive, works from web UI.
    2. **Interactive mode** (token="", auto_drive=False): Spawns a terminal
       running ``gh auth login`` for manual interaction.
    3. **Auto-drive mode** (token="", auto_drive=True): Spawns a terminal
       running a script that auto-answers gh prompts, detects the auth URL
       and opens it in the browser. Terminal stays open on errors.

    Returns:
        {"ok": True, …}                       on success (token mode)
        {"ok": True, "terminal": "…", …}      on terminal spawn (interactive)
        {"ok": False, "fallback": True, …}     when no terminal found
        {"ok": False, "error": "…"}            on failure
    """
    if not shutil.which("gh"):
        return {"ok": False, "error": "gh CLI not installed"}

    # ── Token mode: non-interactive ──
    if token:
        token = token.strip()
        if not token:
            return {"ok": False, "error": "Empty token provided"}

        r = run_gh(
            "auth", "login",
            "--hostname", hostname,
            "--with-token",
            cwd=project_root,
            timeout=15,
            stdin=token + "\n",
        )
        if r.returncode != 0:
            err = r.stderr.strip()
            return {"ok": False, "error": f"Token auth failed: {err}"}

        # Verify it worked
        r_check = run_gh("auth", "status", cwd=project_root, timeout=10)
        authenticated = r_check.returncode == 0

        return {
            "ok": authenticated,
            "message": "Authenticated via token" if authenticated else "Token accepted but auth check failed",
            "authenticated": authenticated,
        }

    # ── Interactive / Auto-drive mode: spawn terminal ──
    from src.core.services.terminal_ops import spawn_terminal, spawn_terminal_script

    if auto_drive:
        # Generate a driven script following the sentinel pattern:
        # signal file + pre-selected flags + direct terminal execution
        script = _build_auto_drive_script(project_root, hostname)
        result = spawn_terminal_script(
            script,
            cwd=project_root,
            script_name=".gh_auth_auto.sh",
            title="GitHub Authentication (auto)",
        )
    else:
        # Plain interactive — just open gh auth login with error trapping
        script = """#!/usr/bin/env bash
set -euo pipefail
echo "══════════════════════════════════════════════"
echo "  GitHub CLI Authentication"
echo "══════════════════════════════════════════════"
echo ""
gh auth login || {
    echo ""
    echo "❌ gh auth login failed (exit code $?)"
    echo "Press Enter to close…"
    read -r
    exit 1
}
echo ""
echo "✅ Authentication complete!"
echo "Press Enter to close…"
read -r
"""
        result = spawn_terminal_script(
            script,
            cwd=project_root,
            script_name=".gh_auth_manual.sh",
            title="GitHub Authentication",
        )

    return result


def _build_auto_drive_script(project_root: Path,
                             hostname: str = "github.com") -> str:
    """Build a bash script that drives ``gh auth login``.

    Follows the continuity-orchestrator sentinel pattern:

    1. **Signal file** (``.gh-auth-result``) — written to ``state/``
       so the web UI can poll completion via the integrations status
       endpoint.
    2. **Pre-selected flags** — ``-h``, ``-p https``, ``-w`` skip all
       menu prompts, leaving only the Y/n git-credentials question.
    3. **Direct execution** — ``gh`` runs in the real terminal TTY,
       no PTY wrapper needed. The user answers the one remaining
       prompt naturally.
    4. **Signal file watcher** — background process extracts the
       device code + URL from captured output and writes to signal
       file so the web modal can display it.
    5. **Error trap** — terminal stays open on failure.
    """
    import tempfile
    tmp = Path(tempfile.gettempdir())
    signal_file = tmp / ".gh-auth-result"
    capture_file = tmp / ".gh-auth-capture"
    return f'''#!/usr/bin/env bash
# ── Signal file for web UI polling ──
SIGNAL_FILE="{signal_file}"
CAPTURE_FILE="{capture_file}"
rm -f "$SIGNAL_FILE" "$CAPTURE_FILE"
touch "$CAPTURE_FILE"
echo '{{"status":"running","ts":"'"$(date -Iseconds)"'"}}' > "$SIGNAL_FILE"

# Trap errors → signal failure + keep terminal open
trap 'echo "{{\\"status\\":\\"failed\\",\\"ts\\":\\"'"$(date -Iseconds)"'\\"}}" > "$SIGNAL_FILE"; kill %2 2>/dev/null; echo ""; echo "❌ Setup failed. See error above."; echo ""; read -p "Press Enter to close…"' ERR

echo "══════════════════════════════════════════════"
echo "  GitHub CLI Authentication (auto-driven)"
echo "══════════════════════════════════════════════"
echo ""
echo "🤖 Pre-selected: {hostname} / HTTPS / Web browser"
echo "   Just answer Y when prompted and press Enter."
echo ""

# ── Background watcher: extract device code + URL from captured output ──
(
    for _i in $(seq 1 60); do
        sleep 1
        CODE=$(grep -oP '[A-Z0-9]{{4}}-[A-Z0-9]{{4}}' "$CAPTURE_FILE" 2>/dev/null | head -1)
        URL=$(grep -oP 'https://github\\.com/login/device' "$CAPTURE_FILE" 2>/dev/null | head -1)
        if [ -n "$CODE" ]; then
            URL="${{URL:-https://github.com/login/device}}"
            echo "{{\\"status\\":\\"code_ready\\",\\"code\\":\\"$CODE\\",\\"url\\":\\"$URL\\",\\"ts\\":\\"$(date -Iseconds)\\"}}" > "$SIGNAL_FILE"
            break
        fi
    done
) &
WATCHER_PID=$!

# ── Run gh auth login ──
# printf auto-answers the "Press Enter to open..." prompt.
# GH_BROWSER=true suppresses the browser-open error.
# tee captures clean output (no PTY escape sequences).
printf '\\n' | GH_BROWSER=true gh auth login -h {hostname} -p https -w 2>&1 | tee "$CAPTURE_FILE"
RC=${{PIPESTATUS[1]}}

# Disable ERR trap before cleanup — kill/wait may fail harmlessly
trap - ERR
kill $WATCHER_PID 2>/dev/null || true
wait $WATCHER_PID 2>/dev/null || true

echo ""
if [ $RC -eq 0 ]; then
    echo '{{"status":"success","ts":"'"$(date -Iseconds)"'"}}' > "$SIGNAL_FILE"
    echo "✅ Authentication complete!"
    echo ""
    gh auth status 2>&1 || true
    echo ""
    echo "This window will close in 5 seconds…"
    sleep 5
else
    echo '{{"status":"failed","rc":'$RC',"ts":"'"$(date -Iseconds)"'"}}' > "$SIGNAL_FILE"
    echo "❌ gh auth login exited with code $RC"
    echo "Press Enter to close…"
    read -r
    exit $RC
fi
'''


def gh_auth_token(project_root: Path) -> dict:
    """Extract current GitHub auth token from gh CLI.

    Useful for auto-detecting credentials when gh is already authed.

    Returns:
        {"ok": True, "token": "ghp_…"}  on success
        {"ok": False, "error": "…"}      on failure
    """
    if not shutil.which("gh"):
        return {"ok": False, "error": "gh CLI not installed"}

    r = run_gh("auth", "token", cwd=project_root, timeout=10)
    if r.returncode != 0 or not r.stdout.strip():
        return {"ok": False, "error": "Not authenticated or token unavailable"}

    return {"ok": True, "token": r.stdout.strip()}


# ═══════════════════════════════════════════════════════════════════
#  Device Flow Auth (browser-based, no terminal needed)
# ═══════════════════════════════════════════════════════════════════

# Module-level store for active device flow sessions
_device_sessions: dict[str, dict] = {}


def gh_auth_device_start(project_root: Path) -> dict:
    """Start a gh auth login device flow via PTY.

    Spawns ``gh auth login -h github.com -p https -w`` inside a
    pseudo-terminal, captures the one-time code and verification URL
    from its output, then returns them to the caller.

    The gh process stays alive in the background, waiting for the user
    to complete the browser flow.  Use ``gh_auth_device_poll()`` to
    check for completion.

    Returns:
        {"ok": True, "session_id": "…", "user_code": "XXXX-XXXX",
         "verification_url": "https://github.com/login/device"}
        {"ok": False, "error": "…"}
    """
    import os
    import pty
    import re
    import select
    import time
    import uuid

    if not shutil.which("gh"):
        return {"ok": False, "error": "gh CLI not installed"}

    # Clean up any stale sessions (> 10 min old)
    _cleanup_stale_sessions()

    # Create PTY so gh thinks it has a real terminal
    master_fd, slave_fd = pty.openpty()

    # Prevent gh from trying to open the browser itself — we handle
    # that from the frontend via window.open().  Without this, gh calls
    # xdg-open inside the PTY context which can fail and cause rc=1.
    env = os.environ.copy()
    env["GH_BROWSER"] = "true"  # 'true' is a noop that exits 0

    try:
        proc = __import__("subprocess").Popen(
            ["gh", "auth", "login", "-h", "github.com",
             "-p", "https", "-w"],
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            cwd=str(project_root),
            env=env,
            close_fds=True,
            start_new_session=True,
        )
    except Exception as exc:
        os.close(master_fd)
        os.close(slave_fd)
        return {"ok": False, "error": f"Failed to start gh: {exc}"}

    # Close slave FD in parent process (child has its own copy)
    os.close(slave_fd)

    # Read output non-blockingly, answering prompts along the way
    output = ""
    deadline = time.time() + 25  # Allow time for prompts + API call
    user_code = None
    answered_yn = False
    answered_enter = False
    yn_answered_at = 0.0  # timestamp when Y/n was answered

    while time.time() < deadline:
        # Check if process died early
        rc = proc.poll()
        if rc is not None:
            # Drain remaining output
            try:
                while True:
                    ready, _, _ = select.select([master_fd], [], [], 0)
                    if not ready:
                        break
                    chunk = os.read(master_fd, 4096).decode(errors="replace")
                    if not chunk:
                        break
                    output += chunk
            except OSError:
                pass
            logger.warning("gh process exited early with rc=%d", rc)
            break

        ready, _, _ = select.select([master_fd], [], [], 0.5)
        if ready:
            try:
                chunk = os.read(master_fd, 4096).decode(errors="replace")
                output += chunk
                logger.info("Device flow chunk (%d bytes): %s",
                            len(chunk), repr(chunk[:200]))
            except OSError:
                break

        # Strip ANSI escape codes for parsing
        clean = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", output)
        clean = re.sub(r"\x1b\][^\x07]*\x07", "", clean)  # OSC sequences
        clean = re.sub(r"\x1b7", "", clean)  # Save cursor
        clean = re.sub(r"\x1b\[\?25[lh]", "", clean)  # Show/hide cursor
        clean = re.sub(r"\x1b\[999;999f", "", clean)  # Move to end

        # Answer "Authenticate Git with your GitHub credentials? (Y/n)"
        if not answered_yn and "(Y/n)" in clean:
            try:
                os.write(master_fd, b"Y\n")
                answered_yn = True
                yn_answered_at = time.time()
                logger.info("Device flow: answered Y/n prompt")
            except OSError:
                pass

        # After Y/n, gh may show a survey-style menu for auth method
        # (arrow-key selection).  Even with -w flag, some gh versions
        # render this and wait for Enter.  Send Enter periodically
        # to advance past menu confirmation and "Press Enter to open".
        if answered_yn:
            elapsed_since_yn = time.time() - yn_answered_at
            if elapsed_since_yn > 1.0 and (not answered_enter
                    or time.time() - yn_answered_at > answered_enter + 2.0):
                try:
                    os.write(master_fd, b"\n")
                    answered_enter = time.time() - yn_answered_at
                    logger.info("Device flow: sent Enter (%.1fs after Y/n)",
                                elapsed_since_yn)
                except OSError:
                    pass

        # Answer terminal size query (\x1b[6n) if present
        if "\x1b[6n" in output:
            try:
                os.write(master_fd, b"\x1b[24;80R")  # Report 24 rows, 80 cols
            except OSError:
                pass
            output = output.replace("\x1b[6n", "")

        # Look for the one-time code (format: XXXX-XXXX)
        code_match = re.search(
            r"one-time code:\s*([A-Z0-9]{4}-[A-Z0-9]{4})", clean
        )
        if code_match:
            user_code = code_match.group(1)
            break

    if not user_code:
        # Failed to extract code — kill the process
        exit_code = proc.poll()
        if exit_code is None:
            proc.terminate()
            exit_code = "timeout"
        try:
            os.close(master_fd)
        except OSError:
            pass
        clean = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", output)
        logger.warning("Could not extract device code from gh output "
                       "(exit=%s): %s", exit_code, clean[:500])
        return {
            "ok": False,
            "error": "Could not start device flow",
            "raw_output": clean[:500],
            "exit_code": str(exit_code),
        }

    # Extract verification URL (default to known URL)
    url_match = re.search(
        r"(https://github\.com/login/device)", output
    )
    verification_url = (
        url_match.group(1) if url_match
        else "https://github.com/login/device"
    )

    # Send Enter to proceed past the "Press Enter" prompt
    try:
        os.write(master_fd, b"\n")
    except OSError:
        pass

    # Store session for polling
    session_id = str(uuid.uuid4())[:8]
    _device_sessions[session_id] = {
        "proc": proc,
        "master_fd": master_fd,
        "user_code": user_code,
        "started": time.time(),
        "output": "",  # Accumulated output for diagnostics
    }

    logger.info("Device flow started — session=%s code=%s",
                session_id, user_code)

    return {
        "ok": True,
        "session_id": session_id,
        "user_code": user_code,
        "verification_url": verification_url,
    }


def gh_auth_device_poll(session_id: str, project_root: Path) -> dict:
    """Check if a device flow session has completed.

    IMPORTANT: must drain the PTY buffer each time, otherwise gh blocks
    trying to write its success/failure output and never exits.

    Returns:
        {"ok": True, "complete": True, "authenticated": True}   — done
        {"ok": True, "complete": False}                         — still waiting
        {"ok": False, "error": "…"}                             — error/timeout
    """
    import os
    import select
    import time

    session = _device_sessions.get(session_id)
    if not session:
        # Session unknown — maybe already completed? Check auth status
        r = run_gh("auth", "status", cwd=project_root, timeout=10)
        if r.returncode == 0:
            return {"ok": True, "complete": True, "authenticated": True}
        return {"ok": False, "error": "Unknown session (may have expired)"}

    proc = session["proc"]
    master_fd = session["master_fd"]

    # ── Drain PTY buffer (critical — prevents gh from blocking) ──
    try:
        while True:
            ready, _, _ = select.select([master_fd], [], [], 0)
            if not ready:
                break
            chunk = os.read(master_fd, 4096).decode(errors="replace")
            if not chunk:
                break
            session["output"] = session.get("output", "") + chunk

            # Respond to terminal size queries so gh doesn't hang
            if "\x1b[6n" in chunk:
                try:
                    os.write(master_fd, b"\x1b[24;80R")
                except OSError:
                    pass
    except OSError:
        pass  # FD closed or process died — that's fine

    rc = proc.poll()

    if rc is not None:
        # Process finished — clean up
        try:
            os.close(master_fd)
        except OSError:
            pass
        accumulated = session.get("output", "")
        del _device_sessions[session_id]

        if rc == 0:
            # Verify auth
            r = run_gh("auth", "status", cwd=project_root, timeout=10)
            authenticated = r.returncode == 0
            logger.info("Device flow complete — session=%s auth=%s",
                        session_id, authenticated)
            return {
                "ok": True,
                "complete": True,
                "authenticated": authenticated,
            }
        else:
            import re as _re
            clean_out = _re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "",
                                accumulated)[:300]
            logger.warning("Device flow failed — session=%s rc=%d output=%s",
                           session_id, rc, clean_out)
            return {
                "ok": False,
                "complete": True,
                "error": f"gh auth login exited with code {rc}",
                "output": clean_out,
            }

    # Still running — check timeout (5 minutes)
    if time.time() - session["started"] > 300:
        proc.terminate()
        try:
            os.close(master_fd)
        except OSError:
            pass
        del _device_sessions[session_id]
        return {
            "ok": False,
            "complete": True,
            "error": "Authentication timed out (5 min)",
        }

    return {"ok": True, "complete": False}


def _cleanup_stale_sessions() -> None:
    """Remove device flow sessions older than 10 minutes."""
    import os
    import time

    stale = [
        sid for sid, s in _device_sessions.items()
        if time.time() - s["started"] > 600
    ]
    for sid in stale:
        session = _device_sessions.pop(sid, None)
        if session:
            try:
                session["proc"].terminate()
                os.close(session["master_fd"])
            except Exception:
                pass
            logger.info("Cleaned up stale device flow session: %s", sid)
