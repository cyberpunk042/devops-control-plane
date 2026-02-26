# Domain: Shells

> ⚠️ **PHASE LABELS MAY BE STALE** — As of 2026-02-25, code has evolved far beyond
> what the phase roadmaps suggest. Many features labeled "Phase 4-8 future" are
> ALREADY IMPLEMENTED. See `audit-domain-docs.md` and `audit-missing-pieces.md`
> for the verified truth. Code is the source of truth, not these phase labels.


> This document catalogs all shell types the tool install system
> must handle, their profile files, PATH mechanics, broken profile
> detection, restricted environments, and sandbox confinement.
>
> SOURCE DOCS: arch-system-model (deep tier: shell env, Phase 4),
>              arch-recipe-format (post_env, shell_config),
>              scope-expansion §2.6 (broken profiles), §2.7 (sandboxed),
>              phase2.3 §5 (env wrapping)

---

## Shell Types

### Supported shells

| Shell | Binary | Default on | Config syntax |
|-------|--------|-----------|--------------|
| bash | `/bin/bash` | Debian, RHEL, Arch, SUSE, WSL | POSIX `export VAR=val` |
| zsh | `/bin/zsh` | macOS (since Catalina 10.15) | Same as bash |
| fish | `/usr/bin/fish` | None (user-installed) | `set -gx VAR val` |
| sh | `/bin/sh` | POSIX fallback | POSIX `export VAR=val` |
| dash | `/bin/dash` | Ubuntu's `/bin/sh` target | POSIX only, no arrays |
| ash | `/bin/ash` | Alpine (BusyBox) | POSIX subset |

### Detection (Phase 4 — deep tier, IMPLEMENTED in `_detect_shell()`)

```python
"shell": {
    "type": str,              # basename of $SHELL
    "version": str | None,    # from $SHELL --version
    "login_profile": str,     # primary login profile path
    "rc_file": str,           # interactive shell rc file
    "path_healthy": bool,     # login PATH matches non-login PATH
    "path_login": str,        # PATH from login shell
    "path_nonlogin": str,     # PATH from non-login shell
    "restricted": bool,       # rbash or restricted mode
}
```

**Currently:** Shell type is detected in the deep tier via
`_detect_shell()` in `l0_detection.py`. It returns type, version,
profile paths, PATH health, and restricted mode.

**Usage:** Phase 4 `shell_config` step type uses this data to
write PATH entries to the correct profile file. Implemented
in `_execute_shell_config_step()` in `tool_install.py`.

---

## Profile Files

### File hierarchy per shell

Each shell has a specific load order. Understanding this is critical
for knowing WHERE to add PATH exports.

#### bash

```
Login shell (ssh, first terminal, su -):
  /etc/profile             ← system-wide (read first)
  ~/.bash_profile           ← user login (if exists, read INSTEAD of .profile)
  ~/.bash_login             ← fallback (if .bash_profile missing)
  ~/.profile                ← fallback (if both above missing)

Interactive non-login (new terminal tab):
  ~/.bashrc                 ← always read for interactive non-login

Both:
  ~/.bash_logout            ← on exit
```

**CRITICAL:** If `~/.bash_profile` exists, `~/.profile` is IGNORED.
Many systems have both, causing confusion.

**Best practice for recipes:** Write to `~/.bashrc` AND check that
`~/.bash_profile` (if it exists) sources `~/.bashrc`. This ensures
the PATH export works in both login and non-login contexts.

#### zsh

```
Login:
  /etc/zsh/zprofile         ← system-wide
  ~/.zprofile               ← user login

Interactive:
  /etc/zsh/zshrc            ← system-wide
  ~/.zshrc                  ← user interactive (MOST COMMON edit target)

Always:
  ~/.zshenv                 ← ALL invocations (login, non-login, scripts)
```

**Best practice:** Write to `~/.zshrc`. It's read for every
interactive session. `~/.zshenv` is read even for scripts (may
have unintended effects).

#### fish

```
~/.config/fish/config.fish  ← ALL interactive sessions
~/.config/fish/conf.d/*.fish  ← modular config files
```

**Syntax difference:** fish does NOT use `export VAR=val`.
It uses `set -gx VAR val` instead.

```fish
# PATH append in fish:
set -gx PATH $HOME/.cargo/bin $PATH

# Environment variable in fish:
set -gx GOPATH $HOME/go
```

#### sh / dash / ash

```
Login:
  /etc/profile
  ~/.profile                ← only file guaranteed to be read
```

**Limitation:** dash and ash don't read `.bashrc`. They only read
`.profile` for login shells. Non-login interactive sessions may
read nothing.

**Impact:** On Alpine (ash), PATH exports added to `~/.profile`
only take effect after a new login session.

### Profile file mapping

Used by the resolver to determine WHERE to write:

```python
_PROFILE_MAP = {
    "bash": {
        "rc_file": "~/.bashrc",
        "login_profile": "~/.bash_profile",  # or ~/.profile
    },
    "zsh": {
        "rc_file": "~/.zshrc",
        "login_profile": "~/.zprofile",
    },
    "fish": {
        "rc_file": "~/.config/fish/config.fish",
        "login_profile": "~/.config/fish/config.fish",  # same file
    },
    "sh": {
        "rc_file": "~/.profile",
        "login_profile": "~/.profile",
    },
    "dash": {
        "rc_file": "~/.profile",
        "login_profile": "~/.profile",
    },
    "ash": {
        "rc_file": "~/.profile",
        "login_profile": "~/.profile",
    },
}
```

---

## PATH Management

### How PATH works for tool installation

When tools install to non-standard locations, the PATH must be
updated. This is the CORE problem this domain addresses.

| Install method | Binary location | On default PATH? |
|---------------|-----------------|-----------------|
| apt/dnf/apk/pacman/zypper | `/usr/bin/`, `/usr/sbin/` | ✅ Yes |
| brew (macOS Intel) | `/usr/local/bin/` | ✅ Yes |
| brew (macOS ARM) | `/opt/homebrew/bin/` | ✅ Yes (brew adds it) |
| snap | `/snap/bin/` | ✅ Yes (snap adds it) |
| pip (venv) | `$VIRTUAL_ENV/bin/` | ✅ Yes (venv activates) |
| pip (user) | `~/.local/bin/` | ⚠️ Usually |
| npm -g | `/usr/local/bin/` or prefix dir | ⚠️ Depends |
| cargo install | `~/.cargo/bin/` | ❌ Must add |
| go install | `$GOPATH/bin/` or `~/go/bin/` | ❌ Must add |
| rustup | `~/.cargo/bin/` | ❌ Must add |
| nvm | `~/.nvm/versions/node/vX/bin/` | ❌ nvm manages |
| Binary download | `/usr/local/bin/` (with sudo) | ✅ Yes |
| Binary download | `~/.local/bin/` (without sudo) | ⚠️ Usually |

### Phase 2 solution: `post_env`

In Phase 2, PATH issues are handled with `post_env` — a shell
command prepended to subsequent steps in the same execution plan.

```python
# Recipe field:
"post_env": 'export PATH="$HOME/.cargo/bin:$PATH"'

# Resolver wraps later steps:
["bash", "-c", 'export PATH="$HOME/.cargo/bin:$PATH" && cargo install cargo-audit']
```

**This is a SESSION-ONLY fix.** It makes the tool available for the
current plan execution. After the plan completes and the terminal
closes, the PATH export is gone.

### Phase 4 solution: `shell_config`

In Phase 4, the system writes PATH exports to the user's profile:

```python
# Recipe field:
"shell_config": {
    "path_append": ["$HOME/.cargo/bin"],
    "env_vars": {},
}

# Resolver generates shell-specific line:
# bash/zsh: export PATH="$HOME/.cargo/bin:$PATH"
# fish:     set -gx PATH $HOME/.cargo/bin $PATH

# And writes it to the correct profile file:
# bash → ~/.bashrc
# zsh  → ~/.zshrc
# fish → ~/.config/fish/config.fish
```

**This is a PERSISTENT fix.** Every new shell session has the PATH.

### Shell-specific PATH syntax

| Shell | PATH append command | Env var export |
|-------|-------------------|---------------|
| bash | `export PATH="$HOME/.cargo/bin:$PATH"` | `export GOPATH="$HOME/go"` |
| zsh | `export PATH="$HOME/.cargo/bin:$PATH"` | `export GOPATH="$HOME/go"` |
| fish | `set -gx PATH $HOME/.cargo/bin $PATH` | `set -gx GOPATH $HOME/go` |
| sh/dash/ash | `export PATH="$HOME/.cargo/bin:$PATH"` | `export GOPATH="$HOME/go"` |

### Idempotent writes

When writing to a profile file, the system MUST be idempotent:

```python
def _should_add_line(file_path: str, line: str) -> bool:
    """Check if the line already exists in the profile file."""
    try:
        with open(os.path.expanduser(file_path)) as f:
            return line not in f.read()
    except FileNotFoundError:
        return True  # file doesn't exist, will be created
```

Without this check, running `install cargo` twice would add the
PATH export twice to `.bashrc`.

---

## Broken Shell Profiles

### What can go wrong

| Problem | Symptom | Detection |
|---------|---------|-----------|
| Missing PATH entry | Tool installed but `which tool` fails | `shutil.which()` fails, direct path exists |
| Syntax error in .bashrc | Shell won't start, tools unreachable | Login PATH ≠ non-login PATH (or both fail) |
| Conflicting profile files | PATH set in .profile overridden by .bash_profile | Compare PATH between files |
| Corrupted PATH | PATH has invalid entries, colons wrong | Parse and validate PATH entries |
| Multiple conflicting exports | `export PATH=...` appears multiple times | Profile file parsing |

### Detection (Phase 4)

```python
# Compare login vs non-login PATH:
path_login = subprocess.run(
    ["bash", "-l", "-c", "echo $PATH"],
    capture_output=True, text=True, timeout=5
).stdout.strip()

path_nonlogin = subprocess.run(
    ["bash", "-c", "echo $PATH"],
    capture_output=True, text=True, timeout=5
).stdout.strip()

# If they differ significantly, there's a profile issue:
path_healthy = (set(path_login.split(":")) == set(path_nonlogin.split(":")))
```

### Remediation

When a tool is installed but not on PATH:

1. **Report:** "cargo is installed at `~/.cargo/bin/cargo` but not on PATH"
2. **Suggest:** "Add to `~/.bashrc`: `export PATH=\"$HOME/.cargo/bin:$PATH\"`"
3. **Auto-fix (with user consent):** Write the line to the profile file

The plan step type for this is `"type": "shell_config"`:
```python
{
    "type": "shell_config",
    "label": "Add cargo to PATH in ~/.bashrc",
    "file": "~/.bashrc",
    "line": 'export PATH="$HOME/.cargo/bin:$PATH"',
    "needs_sudo": False,
}
```

---

## Login vs Non-Login vs Interactive

This matters for understanding WHEN profile files are read.

### Session types

| Session type | Example | Files read (bash) |
|-------------|---------|-------------------|
| Login interactive | SSH, first console login, `su -` | .bash_profile → .bashrc (if sourced) |
| Non-login interactive | New terminal tab, `bash` command | .bashrc only |
| Non-login non-interactive | Script execution, `bash -c "cmd"` | Nothing (or BASH_ENV) |
| Login non-interactive | `ssh host command` | .bash_profile |

### Why this matters for tool install

- **Plan execution:** Commands run via `subprocess.run(["bash", "-c", ...])`.
  This is a NON-LOGIN NON-INTERACTIVE shell. Profile files are NOT read.
  That's why `post_env` MUST prepend the PATH export to the command.

- **Verify step:** Also runs via `subprocess.run()`. Same rule applies.
  If cargo is at `~/.cargo/bin/cargo`, the verify step MUST use:
  ```python
  ["bash", "-c", 'export PATH="$HOME/.cargo/bin:$PATH" && cargo --version']
  ```

- **After plan completes:** The user opens a NEW terminal. Whether
  cargo is on PATH depends on whether `~/.bashrc` (or equivalent)
  has the export. Phase 2 doesn't write to profile files → user may
  need to manually add it or start a new shell.

---

## Restricted and Sandboxed Shells

### Restricted shell (rbash)

If `$SHELL` is `/bin/rbash` or bash is invoked as `rbash`:
- Can't change `$PATH`
- Can't use `/` in command names
- Can't redirect output with `>` or `>>`
- Can't use `exec` to replace the shell

**Impact on tool install:**
- Can't add PATH entries
- Can't install to non-PATH directories
- Can't write to profile files

**Detection:** `basename($SHELL) == "rbash"` or `BASHOPTS`
contains "restricted".

**Resolver behavior:** If `shell.restricted == True`:
- Warn: "Running in a restricted shell — some operations may fail"
- Disable shell_config step type
- Only system package installs (via sudo) will work

### Sandbox confinement

| Sandbox | What it restricts | How detected |
|---------|------------------|-------------|
| snap confinement | Can't access /usr/local, limited HOME | `$SNAP` env var, `mount` shows squashfs |
| Flatpak sandbox | Isolated filesystem, limited PATH | `$FLATPAK_ID` env var |
| SELinux | File access based on labels | `getenforce` returns "Enforcing" |
| AppArmor | Profile-based restriction | `/sys/kernel/security/apparmor/` exists |
| chroot | Limited filesystem root | `stat / != stat /proc/1/root` |

**Impact on recipes:**

| Sandbox | Package install | User-space install | Profile write |
|---------|----------------|-------------------|--------------|
| snap (strict) | ❌ | ⚠️ (within snap home) | ❌ |
| snap (classic) | ✅ (if has sudo) | ✅ | ✅ |
| Flatpak | ❌ | ⚠️ (within sandbox) | ❌ |
| SELinux (enforcing) | ✅ (if policy allows) | ✅ (most cases) | ✅ (user files) |
| AppArmor | ✅ (if profile allows) | ✅ (most cases) | ✅ (user files) |
| chroot | ⚠️ (if PM available) | ✅ | ✅ |

**Phase 2:** No sandbox detection. Known limitation.
✅ **IMPLEMENTED (L3):** `detect_sandbox()` in `detection/environment.py` detects snap, Flatpak, SELinux, AppArmor, chroot.

---

## How Recipes Use Shell Data

### Phase 2 (current): `post_env` only

```python
# cargo recipe:
"post_env": 'export PATH="$HOME/.cargo/bin:$PATH"'

# Resolver wraps subsequent steps:
cmd = ["bash", "-c", f'{post_env} && {original_command}']
```

No shell type detection needed. Always uses bash explicitly.
Works because bash is available on all platforms except minimal
Alpine (which has ash, but `bash` can be installed).

### Phase 4 (IMPLEMENTED): `shell_config`

```python
# Recipe declares what needs to be in profile:
"shell_config": {
    "path_append": ["$HOME/.cargo/bin"],
    "env_vars": {"GOPATH": "$HOME/go"},
}

# Resolver detects shell type:
shell_type = system_profile["shell"]["type"]  # "zsh"

# Generates shell-specific commands:
if shell_type == "fish":
    line = 'set -gx PATH $HOME/.cargo/bin $PATH'
    file = "~/.config/fish/config.fish"
else:
    line = 'export PATH="$HOME/.cargo/bin:$PATH"'
    file = _PROFILE_MAP[shell_type]["rc_file"]

# Plan step:
{"type": "shell_config", "label": "Add cargo to PATH",
 "file": file, "line": line, "needs_sudo": False}
```

### Default shell per platform

| Platform | Default $SHELL | Notes |
|----------|---------------|-------|
| Ubuntu | bash | Since always |
| Debian | bash | Since always |
| Fedora | bash | Since always |
| Alpine | ash (BusyBox) | bash not installed by default |
| Arch | bash | Since always |
| SUSE | bash | Since always |
| macOS | zsh | Since Catalina (10.15); was bash before |
| Docker (most images) | bash or sh | Depends on base image |

**macOS note:** macOS switched from bash to zsh as default in 2019.
The bundled bash is version 3.2 (2007, GPLv2). Users who need modern
bash install it via brew (`bash` 5.x). This means:
- On macOS, profile files are zsh: `~/.zshrc`, `~/.zprofile`
- Old macOS systems may still use bash
- Detection must check `$SHELL`, not assume

---

## Edge Cases

### User changed shell but didn't update profile

User switches from bash to zsh (`chsh -s /bin/zsh`) but still has
PATH exports only in `~/.bashrc`. The zsh session doesn't read
`.bashrc` → tools not on PATH.

**Detection:** `shell.type == "zsh"` but cargo at `~/.cargo/bin/`
is not on PATH → check if `.bashrc` has the export → suggest adding
to `.zshrc`.

### Multiple shells installed

A user may have bash, zsh, and fish installed but only uses one.
`$SHELL` is the LOGIN shell. The user might launch fish inside bash.

**Resolution:** Write to the detected shell's profile. If the user
uses a different shell interactively, they're responsible for their
own profile configuration.

### No shell detected

In minimal containers, `$SHELL` may be empty or set to `/bin/sh`.
The system falls back to POSIX syntax and writes to `~/.profile`.

### Root user shell

Root's shell may differ from the regular user's shell (e.g., root
has `/bin/bash`, user has `/bin/zsh`). Since tool installs affect
the current user, use `$SHELL` for the current user.

When running with sudo, the profile file should still target the
invoking user's profile, not root's. This is why `shell_config`
steps use `needs_sudo: False` — they write to the user's home.

---

## Traceability

| Topic | Source |
|-------|--------|
| Shell detection schema | arch-system-model §Shell environment (Phase 4) |
| shell_config recipe field | arch-recipe-format §shell_config (Phase 4) |
| post_env mechanics | arch-recipe-format §post_env, phase2.3 §5 |
| Broken profile detection | scope-expansion §2.6 |
| Restricted/sandboxed shells | scope-expansion §2.7 |
| Profile file mapping | scope-expansion §2.6 (bash/zsh/fish) |
| env wrapping implementation | phase2.3 §5 (_wrap_with_env) |
| Default shells per platform | domain-platforms (implemented) |
