# Domain: Binary Installers

> ⚠️ **PHASE LABELS MAY BE STALE** — As of 2026-02-25, code has evolved far beyond
> what the phase roadmaps suggest. Many features labeled "Phase 4-8 future" are
> ALREADY IMPLEMENTED. See `audit-domain-docs.md` and `audit-missing-pieces.md`
> for the verified truth. Code is the source of truth, not these phase labels.


> This document catalogs all binary installation methods that bypass
> system and language package managers: curl-pipe-bash scripts, direct
> binary downloads from GitHub releases and vendor CDNs, and the
> architecture detection, permissions, and security implications.
>
> SOURCE DOCS: phase2.2 §Category 4-6 (curl scripts, binary downloads,
>              snap+brew+_default variants),
>              scope-expansion §2.16 (network), §2.5 (security/risk),
>              arch-recipe-format §post_env, §install_variants

---

## Overview

Binary installers are the FALLBACK when system PMs (apt, dnf) and
language PMs (pip, npm) aren't available. They're used in two forms:

| Type | Example | How it works |
|------|---------|-------------|
| **curl-pipe-bash** | rustup, helm, trivy | Download a shell script, pipe to bash |
| **Direct binary download** | kubectl, skaffold | Download a compiled binary, chmod +x, move to PATH |

In the recipe system, binary installs use the `"_default"` method key.
They're the last resort in the resolver's method selection:

```
1. Recipe's "prefer" list
2. System's primary PM (apt, dnf, etc.)
3. snap (if available)
4. "_default" fallback  ← binary installers live here
```

---

## curl-pipe-bash Scripts

### What they are

A remote shell script is downloaded and piped to bash:

```bash
curl -fsSL https://example.com/install.sh | bash
```

The script handles OS/arch detection, downloading the correct binary,
and placing it in the right location.

### Current tools using curl-pipe-bash

| Tool | Script URL | Installs to | Needs sudo | Requires |
|------|-----------|------------|-----------|----------|
| cargo/rustc | `https://sh.rustup.rs` | `~/.cargo/bin/` | **No** | curl |
| helm | `https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3` | `/usr/local/bin/` | **Yes** | curl |
| trivy | `https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh` | `/usr/local/bin/` | **Yes** | curl |

### Script patterns

#### User-space scripts (no sudo)

```python
# rustup — installs to $HOME/.cargo
"cargo": {
    "install": {
        "_default": [
            "bash", "-c",
            "curl --proto '=https' --tlsv1.2 -sSf "
            "https://sh.rustup.rs | sh -s -- -y",
        ],
    },
    "needs_sudo": {"_default": False},
    "post_env": 'export PATH="$HOME/.cargo/bin:$PATH"',
},
```

**Characteristics:**
- Installs to user's home directory → no sudo
- Needs `post_env` to make binaries available in current session
- Script is idempotent (safe to re-run)
- `--proto '=https' --tlsv1.2` forces secure connection
- `-sSf` = silent, show errors, fail on HTTP errors
- `-y` flag = non-interactive (accept defaults)

#### System-space scripts (needs sudo)

```python
# helm — installs to /usr/local/bin
"helm": {
    "install": {
        "_default": [
            "bash", "-c",
            "curl -fsSL https://raw.githubusercontent.com/helm/helm"
            "/main/scripts/get-helm-3 | bash",
        ],
    },
    "needs_sudo": {"_default": True},
},
```

**Characteristics:**
- Installs to `/usr/local/bin/` → needs sudo
- Script handles architecture detection internally
- No `post_env` needed (`/usr/local/bin` is on PATH)
- Re-running updates to latest version

### curl flags used

| Flag | Meaning | Why we use it |
|------|---------|-------------|
| `-f` | Fail silently on HTTP errors | Don't pipe error HTML to bash |
| `-s` | Silent mode | No progress meter |
| `-S` | Show errors (with -s) | Still show errors when silent |
| `-L` | Follow redirects | GitHub redirects to CDN |
| `-O` | Save as remote filename | For direct downloads |
| `--proto '=https'` | Force HTTPS only | Security: never HTTP |
| `--tlsv1.2` | Minimum TLS 1.2 | Security: no weak TLS |

### Security considerations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Malicious script | Arbitrary code execution as current user | Use official URLs only |
| MITM attack | Script replaced in transit | HTTPS + TLS 1.2 minimum |
| Script URL changes | Install breaks | Pin to known-good URL |
| Script needs internet | Fails in airgapped environments | Not mitigated in Phase 2 |
| Wide permissions | Script may modify unexpected files | User-space preferred |

**Phase 2 stance:** We accept the risk of curl-pipe-bash because:
1. We only use OFFICIAL project URLs (sh.rustup.rs, helm GitHub)
2. Every URL uses HTTPS
3. These are the vendor-recommended install methods
4. Alternatives (building from source) are more complex

**Phase 6+:** NOT IMPLEMENTED. May add checksum verification for downloaded scripts.

---

## Direct Binary Downloads

### What they are

A pre-compiled binary is downloaded, made executable, and moved to PATH:

```bash
curl -LO "https://example.com/binary-linux-amd64" && \
chmod +x binary && \
sudo mv binary /usr/local/bin/
```

### Current tools using direct binary download

| Tool | Download URL pattern | Installs to | Needs sudo |
|------|---------------------|------------|-----------|
| kubectl | `https://dl.k8s.io/release/{version}/bin/linux/amd64/kubectl` | `/usr/local/bin/` | Yes |
| skaffold | `https://storage.googleapis.com/skaffold/releases/latest/skaffold-linux-amd64` | `/usr/local/bin/` | Yes |

### Download pattern

```python
# kubectl — direct binary download
"kubectl": {
    "install": {
        "_default": [
            "bash", "-c",
            'curl -LO "https://dl.k8s.io/release/'
            '$(curl -L -s https://dl.k8s.io/release/stable.txt)'
            '/bin/linux/amd64/kubectl" '
            '&& chmod +x kubectl && sudo mv kubectl /usr/local/bin/',
        ],
    },
    "needs_sudo": {"_default": True},
    "requires": {"binaries": ["curl"]},
},
```

### Steps in a binary download

1. **Download:** `curl -LO <url>` downloads to current directory
2. **Set executable:** `chmod +x <binary>` makes it runnable
3. **Move to PATH:** `sudo mv <binary> /usr/local/bin/` (needs sudo)

### Why `/usr/local/bin/`?

| Location | On PATH? | Needs sudo? | Survives updates? |
|----------|---------|------------|-------------------|
| `/usr/bin/` | ✅ | Yes | ❌ PM may overwrite |
| `/usr/local/bin/` | ✅ | Yes | ✅ PM won't touch |
| `~/.local/bin/` | ⚠️ Usually | No | ✅ User owns it |
| `~/bin/` | ⚠️ Maybe | No | ✅ User owns it |

`/usr/local/bin/` is the standard location for manually installed
binaries. It's on PATH everywhere, it's not managed by system PMs,
and it won't be overwritten by package updates.

**Alternative without sudo:** Install to `~/.local/bin/`. This
avoids sudo but requires that `~/.local/bin` is on PATH (it is on
most modern distros but not all).

---

## Architecture Detection

### The problem

Binary downloads are architecture-specific. The URL must match the
system's architecture:

```
https://dl.k8s.io/.../bin/linux/amd64/kubectl   ← x86_64
https://dl.k8s.io/.../bin/linux/arm64/kubectl   ← aarch64
```

### Current state (Phase 2)

**KNOWN LIMITATION:** Several binary download URLs are HARDCODED
to `amd64`:

| Tool | Hardcoded arch in URL | Impact |
|------|----------------------|--------|
| kubectl | `linux/amd64/kubectl` | Fails on arm64 |
| skaffold | `skaffold-linux-amd64` | Fails on arm64 |

This is acceptable because:
1. These tools have snap and brew alternatives that handle arch correctly
2. The `_default` method is the LAST fallback
3. Most servers are amd64

### Architecture normalization (implemented)

```python
_ARCH_MAP = {
    "x86_64": "amd64", "amd64": "amd64",
    "aarch64": "arm64", "arm64": "arm64",
    "armv7l": "armv7",
}
```

`platform.machine()` → normalized arch string.

### Naming conventions per vendor

Vendors use DIFFERENT naming for the same architecture:

| Arch | Go-style | Linux-style | Rust-style |
|------|----------|-------------|------------|
| x86_64 | `amd64` | `x86_64` | `x86_64-unknown-linux-gnu` |
| ARM 64 | `arm64` | `aarch64` | `aarch64-unknown-linux-gnu` |
| ARM 32 | `armv7` | `armv7l` | `armv7-unknown-linux-gnueabihf` |

| Vendor | Naming style | Example URL pattern |
|--------|-------------|-------------------|
| Kubernetes | Go-style | `linux/amd64/kubectl` |
| GitHub Releases | Varies | `tool-linux-amd64.tar.gz` |
| HashiCorp | Go-style | `terraform_1.5.0_linux_amd64.zip` |
| Helm | Go-style | `helm-v3.12.0-linux-amd64.tar.gz` |
| Rust/cargo | Rust triple | `x86_64-unknown-linux-gnu` |

### Architecture interpolation (IMPLEMENTED — Phase 5)

```python
# Recipe with arch template:
"_default": [
    "bash", "-c",
    'curl -LO "https://dl.k8s.io/release/'
    '$(curl -L -s https://dl.k8s.io/release/stable.txt)'
    '/bin/linux/{arch}/kubectl" '
    '&& chmod +x kubectl && sudo mv kubectl /usr/local/bin/',
],

# Resolver substitutes {arch} with system_profile["arch"]["normalized"]
```

---

## OS Detection in Binary Downloads

### The problem

Binary downloads are also OS-specific:

```
https://dl.k8s.io/.../bin/linux/amd64/kubectl   ← Linux
https://dl.k8s.io/.../bin/darwin/amd64/kubectl   ← macOS
```

### Current state

Binary download recipes only provide Linux URLs. macOS uses brew.
This is by design — the resolver picks brew on macOS, so the
`_default` Linux URL is never reached on macOS.

### OS naming per vendor

| Vendor | Linux | macOS | Windows |
|--------|-------|-------|---------|
| Kubernetes | `linux` | `darwin` | `windows` |
| GitHub Releases | `linux` | `darwin` / `macos` | `windows` |
| HashiCorp | `linux` | `darwin` | `windows` |
| Helm | `linux` | `darwin` | `windows` |

---

## Version Management

### Current approach (Phase 2): always latest

All binary download URLs point to "latest" or "stable":

| Tool | Version strategy |
|------|-----------------|
| kubectl | `$(curl -L -s https://dl.k8s.io/release/stable.txt)` — fetches latest stable version |
| skaffold | `/releases/latest/skaffold-linux-amd64` — "latest" in URL |
| helm | Install script downloads latest by default |
| trivy | Install script downloads latest by default |

### Update = re-install

For binary downloads, update is the SAME command as install:

```python
"update": {
    "_default": [
        "bash", "-c",
        'curl -LO "https://dl.k8s.io/release/...' ,  # same as install
    ],
},
```

The new binary overwrites the old one. No version tracking.

### Version pinning (IMPLEMENTED via `install_variants` — Phase 4)

```python
"inputs": [
    {"id": "version", "type": "text", "default": "latest",
     "label": "Version to install"},
],
"install_variants": {
    "from_url": {
        "command": ["bash", "-c",
            'curl -LO "https://dl.k8s.io/release/{version}/bin/linux/{arch}/kubectl"'
            ' && chmod +x kubectl && sudo mv kubectl /usr/local/bin/'],
    },
},
```

---

## Resolver Method Selection for Binary Installers

The resolver picks how to install a tool based on what's available:

```python
def _pick_install_method(recipe, system_profile):
    # 1. Try recipe's prefer list
    for method in recipe.get("prefer", []):
        if _method_available(method, system_profile):
            return method

    # 2. Try system's primary PM
    pm = system_profile["package_manager"]["primary"]
    if pm in recipe["install"]:
        return pm

    # 3. Try snap
    if "snap" in recipe["install"] and system_profile["package_manager"]["snap_available"]:
        return "snap"

    # 4. Fall back to _default (binary installer)
    if "_default" in recipe["install"]:
        return "_default"

    return None  # no method available
```

### When does `_default` win?

| Scenario | PM | snap | brew | Method selected |
|----------|-----|------|------|----------------|
| Ubuntu desktop | apt | ✅ | ❌ | snap (prefer list) |
| macOS | brew | ❌ | ✅ | brew (prefer list) |
| Alpine container | apk | ❌ | ❌ | **_default** |
| Fedora minimal | dnf | ❌ | ❌ | **_default** |
| Docker (Debian base) | apt | ❌ | ❌ | **_default** |

Binary download is the method of LAST resort. It's used when:
- No snap (no systemd, or snap not installed)
- No brew (not macOS, Linuxbrew not installed)
- No system PM recipe for this tool (kubectl doesn't have apt/dnf)

---

## Dependency: curl

ALL binary installers require `curl` on PATH:

```python
"requires": {"binaries": ["curl"]}
```

If curl is not installed, the resolver inserts a curl install step
BEFORE the binary download step:

```
1. apt-get install -y curl          ← system PM install
2. curl -fsSL ... | bash            ← binary installer
```

curl is a Category 7 system package (same name everywhere):

| Family | Package | Command |
|--------|---------|---------|
| debian | curl | `apt-get install -y curl` |
| rhel | curl | `dnf install -y curl` |
| alpine | curl | `apk add curl` |
| arch | curl | `pacman -S --noconfirm curl` |
| suse | curl | `zypper install -y curl` |
| macos | curl | Pre-installed (or `brew install curl`) |

---

## Install Locations Summary

| Tool | Install method | Location | On PATH? | Sudo? |
|------|---------------|----------|---------|-------|
| cargo/rustc | curl-pipe-bash (rustup) | `~/.cargo/bin/` | ❌ Needs post_env | No |
| helm | curl-pipe-bash (script) | `/usr/local/bin/` | ✅ | Yes |
| trivy | curl-pipe-bash (script) | `/usr/local/bin/` | ✅ | Yes |
| kubectl | Direct binary | `/usr/local/bin/` | ✅ | Yes |
| skaffold | Direct binary | `/usr/local/bin/` | ✅ | Yes |

### Two patterns

| Pattern | Install to | Sudo? | post_env? | Example |
|---------|-----------|-------|-----------|---------|
| User-space script | `~/.tool/bin/` | No | Yes | rustup |
| System-space script/binary | `/usr/local/bin/` | Yes | No | helm, kubectl |

---

## Comparison with Other Methods

When the SAME tool can be installed multiple ways, here's the tradeoff:

| Factor | System PM (apt) | snap | brew | curl-pipe-bash | Direct binary |
|--------|----------------|------|------|---------------|--------------|
| Speed | Fast | Medium | Slow | Medium | Fast |
| Needs internet | Depends | Yes | Yes | Yes | Yes |
| Needs sudo | Yes | Yes | No | Depends | Yes (for /usr/local/) |
| Auto-updates | Via apt upgrade | Automatic | Manual | Manual (re-run) | Manual (re-run) |
| Dependencies | Managed | Bundled | Managed | Script handles | None |
| Arch handling | Automatic | Automatic | Automatic | Script handles | **Hardcoded** |
| Isolation | Shared system | Sandboxed | User-space | Varies | Shared system |
| Rollback | PM manages | snap revert | brew switch | Overwrite only | Overwrite only |

---

## Edge Cases

### Container environments

- Containers often lack curl → resolver must install curl first
- Containers may be read-only → `/usr/local/bin/` write fails
- Containers may lack sudo → system-space installs fail
- Alpine containers run as root → sudo not needed

### Airgapped / restricted networks

- All binary installers need internet access
- No offline fallback in Phase 2
- NOT IMPLEMENTED: pre-download binaries and install from local path

### Architecture mismatch

- Downloading amd64 binary on arm64 → binary won't execute
- Error: `exec format error`
- Mitigation: use snap or brew which handle arch correctly

### Partial downloads

- curl fails mid-download → corrupted binary
- `-f` flag makes curl return non-zero on error → step fails
- Re-running download overwrites partial file

### Permission denied on /usr/local/bin/

- snap strict confinement blocks writes to `/usr/local/bin/`
- Some containers mount `/usr/local/` as read-only
- ✅ IMPLEMENTED (M1): falls back to `~/.local/bin/` when /usr/local/bin not writable

---

## Traceability

| Topic | Source |
|-------|--------|
| curl-pipe-bash recipes | phase2.2 §Category 4 (cargo/rustup) |
| curl+brew recipes | phase2.2 §Category 5 (helm, trivy, skaffold) |
| Snap+binary recipes | phase2.2 §Category 6 (kubectl, terraform, node, go, gh) |
| Architecture map | l0_detection.py `_ARCH_MAP` (implemented) |
| Method selection logic | phase2.3 §3 `_pick_install_method()` |
| post_env mechanics | arch-recipe-format §post_env |
| Security/risk tags | scope-expansion §2.5 |
| Network requirements | scope-expansion §2.16 |
| skaffold arch limitation | phase2.2 §Category 5 (noted) |
| kubectl arch limitation | phase2.2 §Category 6 (noted) |
