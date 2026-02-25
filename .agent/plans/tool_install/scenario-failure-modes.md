# Scenarios: Failure Modes

> What happens when things go wrong. Each scenario describes the
> failure, how the system detects it, what the user sees, and what
> remediation is offered.
>
> These scenarios validate error handling, rollback, and recovery
> across all phases.

---

## Category 1: Authentication Failures

### F1.1 — Wrong sudo password

**Trigger:** User types wrong password at step 3 of 7.
**Detection:** stderr contains "incorrect password" or "sorry, try again"

```
Step 1: [repo]     Add Docker repo           ✅ done
Step 2: [packages] apt-get update            ✅ done
Step 3: [packages] Install docker-ce         ❌ FAILED — wrong password
Step 4-7: not started
```

**User sees:**
```
❌ Step 3: Install docker-ce
   Error: Wrong password. Try again.
   [password input field, pre-focused]
   [Retry] [Cancel]
```

**System behavior:**
- Steps 1-2 completed, NOT rolled back (idempotent)
- Password input cleared from DOM for security
- Retry re-attempts step 3 only (not 1-2)
- Password cached for remaining steps after success

---

### F1.2 — No sudo access

**Trigger:** User's account is not in sudoers.
**Detection:** stderr contains "is not in the sudoers file"

```
Step 1: [packages] Install build-essential   ❌ FAILED — not in sudoers
```

**User sees:**
```
❌ Step 1: Install build-essential
   Error: Your account is not authorized for sudo.
   
   Remediation options:
   ○ Ask an admin to run: usermod -aG sudo jfortin
   ○ Switch to a user-space install (no sudo needed)
     → pip install --user ruff
```

**System behavior:**
- Detect `needs_sudo` in plan BEFORE execution
- If user has no sudo: offer user-space alternatives
- Some tools have non-sudo install paths (pip --user, cargo)

---

### F1.3 — Sudo password timeout between steps

**Trigger:** Step 4 takes 10 minutes (cargo compile). Step 5 needs sudo again but the sudo timestamp has expired.

**Detection:** sudo asks for password again unexpectedly.

**System behavior:**
- `sudo -S -k` pipes password every time (no timestamp reliance)
- Password stored in memory for plan duration
- No timeout issue — each step gets fresh sudo invocation

---

## Category 2: Network Failures

### F2.1 — Network offline during install

**Trigger:** Network drops after step 2 (repo added, apt update done).

```
Step 1: [repo]     Add repo                  ✅ done
Step 2: [packages] apt-get update            ✅ done
Step 3: [packages] Install docker-ce         ❌ FAILED — network error
```

**Detection:** stderr contains "Could not resolve", "Connection timed out", "Failed to fetch"

**User sees:**
```
❌ Step 3: Install docker-ce
   Error: Download failed — network appears to be offline
   
   stderr: E: Failed to fetch https://download.docker.com/...
           Could not resolve 'download.docker.com'
   
   Remediation options:
   ○ Check network connection and retry
   ○ Use offline mirror (requires configuration)
```

---

### F2.2 — Proxy blocks download

**Trigger:** Corporate proxy blocks download.docker.com.

**Detection:** HTTP 403/407 in stderr, or SSL intercept error.

**User sees:**
```
❌ Step 1: Add Docker repo
   Error: Download blocked (HTTP 403)
   
   Detected: Proxy at 10.0.0.1:8080 (from HTTP_PROXY)
   
   Remediation options:
   ○ Add download.docker.com to proxy allowlist
   ○ Use docker.io from Debian repos (no custom repo needed)
```

---

### F2.3 — Download interrupted mid-transfer

**Trigger:** Large download (2 GB PyTorch wheel) interrupted at 60%.

**Detection:** urllib connection reset, incomplete file.

**User sees:**
```
❌ Step 9: Download PyTorch CUDA wheels
   Error: Connection reset after 1.2 GB of 2.0 GB
   
   [Retry] — will resume from 1.2 GB if server supports Range
   [Cancel]
```

**System behavior:**
- Partial file detected (size mismatch)
- Resume with Range header if server supports it
- If not, delete partial and restart download
- Checksum verified after completion

---

### F2.4 — DNS resolution fails for specific domain

**Trigger:** Can reach pypi.org but not download.docker.com.

**Detection:** Selective resolution failure.

```
Network probe results:
  pypi.org:           ✅ reachable
  github.com:         ✅ reachable  
  download.docker.com: ❌ unreachable
  registry.npmjs.org: ✅ reachable
```

**User sees:**
```
⚠️ Cannot reach download.docker.com
   
   This affects:
   - Docker CE installation (requires Docker's apt repo)
   
   Available alternatives:
   ○ docker.io (from Debian repos — reachable)     [Select]
   ○ Podman (from Debian repos — reachable)         [Select]
```

---

## Category 3: Disk & Resource Failures

### F3.1 — Disk full during install

**Trigger:** /var runs out of space during apt install.

**Detection:** stderr contains "No space left on device"

**User sees:**
```
❌ Step 4: Install CUDA toolkit
   Error: No space left on device
   
   Disk usage:
     /var: 95% used (200 MB free)
     Needed: ~2.5 GB
   
   Remediation options:
   ○ Free disk space and retry
     Suggestion: apt clean (will free ~500 MB)
     Suggestion: docker system prune (will free ~2 GB)
   ○ Install to alternate location
```

---

### F3.2 — Disk full during build-from-source

**Trigger:** cmake build fills /tmp during OpenCV compilation at step 4/8.

**Detection:** Compiler error "No space left on device", or cmake error.

**User sees:**
```
❌ Step 4: cmake --build (OpenCV)
   Error: Build failed — disk full
   
   /tmp: 98% used (50 MB free)
   Build directory: 4.2 GB
   
   Remediation options:
   ○ Clean build and retry in larger partition
     Suggestion: use /home/user/build instead of /tmp
   ○ Cancel build and use pre-built package (CPU only)
   
   [Clean up build artifacts] — will free 4.2 GB
```

**System behavior:**
- Build cleanup offered (rm -rf build dir)
- Alternative partition suggested
- Fallback to non-build install if available

---

### F3.3 — OOM during compilation

**Trigger:** `make -j16` exhausts RAM during large build.

**Detection:** Process killed by OOM killer, exit code 137.

**User sees:**
```
❌ Step 4: Build neovim
   Error: Process killed (out of memory)
   
   RAM: 4 GB total, build used ~3.8 GB
   Parallel jobs: 16
   
   Remediation:
   ○ Retry with fewer parallel jobs (-j4)   [Retry]
   ○ Retry with single thread (-j1)         [Retry]
   ○ Cancel build, use apt package instead  [Switch]
```

**System behavior:**
- Detect exit code 137 → OOM
- Reduce parallelism automatically on retry
- Offer package alternative

---

## Category 4: Permission Failures

### F4.1 — Config file owned by root, no sudo

**Trigger:** Tool needs to write to /etc/docker/daemon.json.

```
Step 5: [config] Write /etc/docker/daemon.json    ❌ FAILED — Permission denied
```

**User sees:**
```
❌ Step 5: Configure Docker daemon
   Error: Permission denied: /etc/docker/daemon.json
   
   File owner: root:root
   Your user: jfortin
   
   This step requires sudo. [Enter password]
```

---

### F4.2 — Binary installed but not executable

**Trigger:** Binary downloaded but chmod missed.

```
Step 3: [tool]   Extract hugo to ~/.local/bin/    ✅ done
Step 4: [verify] hugo --version                   ❌ FAILED — Permission denied
```

**Detection:** "Permission denied" when running binary.

**User sees:**
```
❌ Step 4: Verify hugo
   Error: ~/.local/bin/hugo exists but is not executable
   
   Fix applied: chmod +x ~/.local/bin/hugo
   [Retry verification]
```

**System behavior:**
- Auto-detect "Permission denied" on verify
- Check if file exists + not executable
- Auto-fix with chmod if possible
- Re-run verify after fix

---

### F4.3 — pip install in system-managed environment

**Trigger:** PEP 668 — externally managed Python environment (Ubuntu 23.04+).

**Detection:** stderr contains "externally-managed-environment"

**User sees:**
```
❌ Step 1: pip install ruff
   Error: This environment is externally managed
   
   Python 3.12 on Ubuntu 24.04 blocks global pip installs.
   
   Remediation options:
   ○ Install via pipx (recommended)                    [Select]
     → pipx install ruff
   ○ Install in virtual environment                    [Select]
     → python3 -m venv ~/.venvs/tools && ~/.venvs/tools/bin/pip install ruff
   ○ Use apt package (may be older version)            [Select]
     → apt install python3-ruff
   ○ Override with --break-system-packages (risky)     [Select]
```

---

## Category 5: Tool-Specific Failures

### F5.1 — cargo install: compilation error

**Trigger:** Rust crate fails to compile (missing C dependency).

```
Step 2: [tool] cargo install cargo-audit    ❌ FAILED
```

**Detection:** stderr contains "error[E", "linking with `cc` failed", "ld: cannot find -l"

**User sees:**
```
❌ Step 2: Install cargo-audit
   Error: Compilation failed — missing C library
   
   stderr: ld: cannot find -lssl
   
   Analysis: Missing libssl development files
   
   Remediation:
   ○ Install missing library and retry                 [Install + Retry]
     → sudo apt install libssl-dev
```

**System behavior:**
- _analyse_install_failure() parses stderr
- Detects "cannot find -l{lib}" pattern
- Maps to dev package: -lssl → libssl-dev, -lcurl → libcurl4-openssl-dev
- Offers one-click fix

---

### F5.2 — npm global install: EACCES

**Trigger:** npm tries to write to /usr/lib/node_modules without permission.

**Detection:** stderr contains "EACCES" and "permission denied"

**User sees:**
```
❌ Step 1: npm install -g @angular/cli
   Error: Permission denied writing to /usr/lib/node_modules
   
   Remediation options:
   ○ Retry with sudo                                   [Retry with sudo]
   ○ Fix npm prefix (recommended, one-time setup)      [Fix]
     → mkdir ~/.npm-global && npm config set prefix '~/.npm-global'
   ○ Use npx instead (no global install needed)        [Use npx]
```

---

### F5.3 — Version conflict after install

**Trigger:** New tool conflicts with existing version.

```
Step 3: [verify] python --version shows 3.8,
        but installed tool needs 3.10+
```

**User sees:**
```
⚠️ Step 3: Verify ruff
   Warning: ruff installed but requires Python 3.10+
   Current: Python 3.8.10
   
   The tool may not work correctly.
   
   Options:
   ○ Install Python 3.10+ alongside current version
   ○ Use pyenv to manage Python versions
   ○ Install older ruff version (0.1.x supports Python 3.8)
```

---

## Category 6: Partial Installs

### F6.1 — Plan fails at step 4 of 7

**Trigger:** Steps 1-3 succeed, step 4 fails. Steps 5-7 not run.

**System state:**
```
Step 1: [repo]      Add Docker repo          ✅ done      (idempotent, safe)
Step 2: [packages]  apt-get update           ✅ done      (idempotent, safe)
Step 3: [packages]  Install containerd       ✅ done      (installed, working)
Step 4: [packages]  Install docker-ce        ❌ FAILED    (dpkg error)
Step 5: [service]   Start docker             ⏳ skipped
Step 6: [config]    Configure daemon         ⏳ skipped
Step 7: [verify]    Verify                   ⏳ skipped
```

**User sees:**
```
❌ Plan failed at step 4/7
   
   Completed: 3 steps
   Failed: step 4 (Install docker-ce)
   Skipped: 3 steps
   
   System state:
   ✅ Docker repo added
   ✅ containerd installed and working
   ❌ docker-ce NOT installed
   
   Options:
   ○ Retry from step 4                  [Retry]
   ○ Fix dpkg error and retry           [Diagnose]
     → sudo dpkg --configure -a
   ○ Rollback all changes               [Rollback]
     → apt remove containerd
     → rm /etc/apt/sources.list.d/docker.list
   ○ Keep partial install               [Keep]
     → containerd is usable without docker-ce
```

---

### F6.2 — GPU driver install fails mid-way

**Trigger:** NVIDIA driver install partially completes (DKMS build failed).

**System state:**
```
nouveau: blacklisted ❌
nvidia module: NOT loaded
Display: may be broken (no driver for GPU)
```

**User sees:**
```
🔴 HIGH RISK FAILURE — Display may be affected
   
   Step 4: Install nvidia-driver-535    ❌ FAILED
   
   WARNING: Your display driver may be in a broken state.
   The nouveau driver was blacklisted but the NVIDIA driver
   did not install correctly.
   
   Emergency recovery:
   ○ Restore nouveau (revert blacklist)    [Restore]
     → sudo rm /etc/modprobe.d/blacklist-nouveau.conf
     → sudo update-initramfs -u
     → Reboot required
   ○ Retry NVIDIA driver install           [Retry]
   ○ Switch to text console and fix manually
     → Ctrl+Alt+F2 for text console
```

---

### F6.3 — Interrupted by user (Ctrl+C / close modal)

**Trigger:** User closes the modal during step 3 of 5.

**System behavior:**
- subprocess.run() runs to completion (can't cancel a running apt)
- Modal closes immediately (UI-side)
- Next time user opens install: detects partial state
- Offers: "Previous install was interrupted. Resume from step 4?"

---

## Category 7: Environment Failures

### F7.1 — Tool installed but not in PATH

**Trigger:** Binary installed to ~/.cargo/bin but PATH doesn't include it.

```
Step 3: [tool]   cargo install cargo-audit   ✅ done
Step 4: [verify] cargo-audit --version       ❌ FAILED — not found
```

**User sees:**
```
⚠️ Step 4: Verify cargo-audit
   cargo-audit is installed but not in your PATH
   
   Found at: /home/jfortin/.cargo/bin/cargo-audit
   
   Fix options:
   ○ Add to PATH automatically                         [Fix]
     → echo 'export PATH="$HOME/.cargo/bin:$PATH"' >> ~/.bashrc
     → Then restart your shell or run: source ~/.bashrc
   ○ Already in .bashrc, just restart shell            [Dismiss]
```

**System behavior:**
- verify step uses post_env to check with expanded PATH
- If found with post_env but not in current PATH → "restart shell"
- If not found even with post_env → real install failure

---

### F7.2 — Wrong Python / wrong pip

**Trigger:** Multiple Python installations. pip installs to Python 3.8 but user expects 3.12.

```
Step 1: [tool] pip install ruff    ✅ done (installed to Python 3.8)
Step 2: [verify] ruff --version    ❌ FAILED — not found
```

**Detection:** `shutil.which("ruff")` returns None, but `pip show ruff` shows installed.

**User sees:**
```
⚠️ ruff installed into Python 3.8, but your PATH runs Python 3.12
   
   Installed at: /usr/lib/python3.8/dist-packages/ruff
   Active Python: /usr/bin/python3.12
   
   Fix: Install with the correct Python:
   → python3.12 -m pip install ruff
```

---

### F7.3 — Stale detection cache

**Trigger:** Tool installed manually (outside the system). Cache says "not installed."

**Detection:** l0_detection cache TTL expired, or manual cache invalidation.

**User sees:**
```
Tool: ruff
   Cached status: ❌ Not installed (checked 2 hours ago)
   Actual status: ✅ Installed (ruff 0.5.1)
   
   [🔄 Refresh detection]
```

**System behavior:**
- Cache invalidated after every install operation
- Manual refresh button always available
- Cache TTL: 5 minutes for installed checks

---

## Category 8: Timeout Failures

### F8.1 — Package manager lock held

**Trigger:** Another apt process is running (unattended-upgrades, another terminal).

**Detection:** stderr contains "Could not get lock" or "dpkg was interrupted"

**User sees:**
```
❌ Step 3: Install docker-ce
   Error: Package manager is locked by another process
   
   Lock held by: unattended-upgrades (PID 12345)
   
   Options:
   ○ Wait and retry (unattended-upgrades usually finishes in <5 min)   [Wait]
   ○ Kill blocking process and retry (may leave packages inconsistent) [Force]
```

---

### F8.2 — Build timeout (cargo 10+ minutes)

**Trigger:** cargo install times out at 300s default.

**User sees:**
```
❌ Step 2: Install cargo-audit
   Error: Command timed out after 300s
   
   Cargo compilation can take 5-15 minutes for large crates.
   
   Options:
   ○ Retry with extended timeout (600s)    [Retry]
   ○ Retry with longer timeout (1200s)     [Retry]
   ○ Cancel installation                   [Cancel]
```

---

### F8.3 — SSE stream timeout

**Trigger:** No SSE events for 60 seconds (backend processing but not streaming).

**Detection:** Frontend timer, no events received.

**User sees:**
```
⚠️ Connection may have dropped
   Last event: 63 seconds ago
   
   [Check status] — polls backend for current step
   [Cancel]
```

---

## Failure Pattern Summary

| Category | Detection method | Recovery approach |
|----------|-----------------|-------------------|
| Auth (sudo) | stderr parsing | Re-prompt password, offer alternatives |
| Network | stderr + HTTP codes | Retry, offline alternatives, proxy hints |
| Disk | stderr "No space" | Cleanup suggestions, alternate paths |
| Permissions | stderr "Permission denied" | sudo prompt, auto-fix chmod |
| Tool-specific | _analyse_install_failure() | Targeted remediation per error |
| Partial install | Step tracking | Resume, retry, rollback options |
| Environment | which() + pip show | PATH fix, Python version guidance |
| Timeout | subprocess.TimeoutExpired | Extended timeout, wait + retry |

---

## Traceability

| Topic | Source |
|-------|--------|
| sudo password handling | Phase 2.4 §sudo handling, domain-sudo-security |
| _analyse_install_failure() | tool_install.py lines 111-271 |
| Remediation options | Phase 2.4 §error handling |
| Rollback approach | domain-rollback §undo catalog |
| Network probing | domain-network §endpoint probes |
| PATH propagation | Phase 2.4 §post_env |
| Cache invalidation | Phase 2.4 §cache invalidation |
| PEP 668 detection | domain-language-pms §pip restrictions |
| PM lock detection | domain-parallel-execution §lock-aware |
| Risk escalation for drivers | domain-risk-levels §high risk |
