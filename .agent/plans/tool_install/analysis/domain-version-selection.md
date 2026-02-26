# Domain: Version Selection

> ⚠️ **PHASE LABELS MAY BE STALE** — As of 2026-02-25, code has evolved far beyond
> what the phase roadmaps suggest. Many features labeled "Phase 4-8 future" are
> ALREADY IMPLEMENTED. See `audit-domain-docs.md` and `audit-missing-pieces.md`
> for the verified truth. Code is the source of truth, not these phase labels.


> This document catalogs version selection for tool installation:
> static version lists, dynamic API-sourced versions, version
> constraints (kubectl ±1 minor), default selection strategies,
> and how version affects install commands.
>
> SOURCE DOCS: scope-expansion §2.13 (version selection),
>              scope-expansion §2.14 (dynamic version sources),
>              domain-choices §single choice (version as choice),
>              domain-devops-tools §tool inventory

---

## Overview

Almost every tool has versions. Version selection determines
WHAT gets installed and HOW — different versions use different
package names, URLs, and sometimes different install methods.

### Phase 2 vs Phase 4

| Phase | Version capability |
|-------|-------------------|
| Phase 2 | No version selection. "Latest" is always installed. `apt-get install git` gets whatever the repo has. `pip install ruff` gets latest. |
| Phase 4 | Static version lists. User picks from predefined options. |
| Phase 8+ | Dynamic versions (API fetch). Version constraints. Cache. |

---

## Version Source Types

### Static versions

Predefined list in the recipe. Updated on recipe maintenance.

```python
"version_choice": {
    "type": "single",
    "label": "Version",
    "source": "static",
    "options": [
        {"id": "3.12", "label": "Python 3.12 (Recommended)", "default": True},
        {"id": "3.11", "label": "Python 3.11 (Previous LTS)"},
        {"id": "3.13", "label": "Python 3.13 (Latest)",
         "warning": "Some packages may not support 3.13 yet"},
    ],
}
```

**When to use:** Runtimes (Python, Node, Go, Rust) where the
version list is stable and changes slowly.

### Dynamic versions (API fetch)

Fetched from an external API at discovery time.

```python
"version_choice": {
    "type": "single",
    "label": "Version",
    "source": "dynamic",
    "fetch_url": "https://api.github.com/repos/kubernetes/kubernetes/releases",
    "parse": "json[].tag_name",
    "filter": "^v1\\.",        # only v1.x releases
    "limit": 10,               # show last 10
    "cache_ttl": 3600,         # cache for 1 hour
}
```

**When to use:** Tools with frequent releases (kubectl, helm,
terraform) where maintaining a static list would be impractical.

### Version from package manager

Let the package manager decide — install whatever is in the repo.

```python
"version_choice": {
    "source": "package_manager",
    # No user choice — takes repo version
    # apt: "3.4.3" (whatever Ubuntu ships)
    # brew: "3.5.0" (usually more recent)
}
```

**When to use:** System utilities (curl, jq, git) where the user
rarely needs a specific version.

---

## Static Version Examples

### Python

```python
"python": {
    "version_choice": {
        "options": [
            {"id": "3.12", "label": "Python 3.12 (Recommended)",
             "default": True,
             "install_variants": {
                 "debian": ["apt-get", "install", "-y", "python3.12"],
                 "brew": ["brew", "install", "python@3.12"],
             }},
            {"id": "3.11", "label": "Python 3.11 (Previous LTS)",
             "install_variants": {
                 "debian": ["apt-get", "install", "-y", "python3.11"],
                 "brew": ["brew", "install", "python@3.11"],
             }},
            {"id": "3.13", "label": "Python 3.13 (Latest)",
             "warning": "Some packages may not support 3.13 yet",
             "install_variants": {
                 "debian": ["apt-get", "install", "-y", "python3.13"],
                 # May need deadsnakes PPA on Ubuntu < 24.10
                 "repo_setup": {"ppa": "deadsnakes/ppa"},
             }},
        ],
    },
}
```

### Node.js

```python
"node": {
    "version_choice": {
        "options": [
            {"id": "20", "label": "Node 20 LTS (Recommended)",
             "default": True},
            {"id": "18", "label": "Node 18 LTS (Maintenance)"},
            {"id": "22", "label": "Node 22 (Current)"},
        ],
    },
}
```

### Go

```python
"go": {
    "version_choice": {
        "options": [
            {"id": "1.22", "label": "Go 1.22 (Recommended)",
             "default": True},
            {"id": "1.21", "label": "Go 1.21 (Previous)"},
            {"id": "1.23", "label": "Go 1.23 (Latest)"},
        ],
    },
}
```

### Rust

```python
"cargo": {
    "version_choice": {
        "options": [
            {"id": "stable", "label": "Stable (Recommended)",
             "default": True},
            {"id": "beta", "label": "Beta"},
            {"id": "nightly", "label": "Nightly",
             "warning": "May have breaking changes"},
        ],
        # rustup handles channels, not version numbers
        "install_variant_template":
            "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | "
            "sh -s -- -y --default-toolchain {version}",
    },
}
```

---

## Dynamic Version Examples

### kubectl

```python
"kubectl": {
    "version_choice": {
        "source": "dynamic",
        "fetch_url": "https://dl.k8s.io/release/stable.txt",
        "parse": "text",                    # plain text response
        "generate_options": "minor_range",   # generate ±1 minor versions
        "cache_ttl": 3600,
    },
}
```

**Logic:** Fetch stable version (e.g., `v1.30.2`), then offer:
- v1.30 (latest stable) — default
- v1.29 (previous minor)
- v1.31 (next minor, if available)

### Helm

```python
"helm": {
    "version_choice": {
        "source": "dynamic",
        "fetch_url": "https://api.github.com/repos/helm/helm/releases",
        "parse": "json[].tag_name",
        "filter": "^v3\\.",          # only Helm 3.x
        "limit": 5,
        "cache_ttl": 3600,
    },
}
```

### Terraform

```python
"terraform": {
    "version_choice": {
        "source": "dynamic",
        "fetch_url": "https://api.github.com/repos/hashicorp/terraform/releases",
        "parse": "json[].tag_name",
        "filter": "^v1\\.",
        "exclude": "alpha|beta|rc",  # no pre-releases
        "limit": 5,
        "cache_ttl": 3600,
    },
}
```

---

## Version Constraints

### kubectl ±1 minor

kubectl must be within ±1 minor version of the cluster:

```python
"version_constraint": {
    "type": "cluster_match",
    "detect": "kubectl version --client=false -o json",
    "field": "serverVersion.minor",
    "rule": "±1",
    "fallback": "latest",  # if no cluster accessible
}
```

**Example:**
```
Cluster: v1.29.3
→ Allowed: v1.28.x, v1.29.x, v1.30.x
→ Default: v1.29.x (match cluster)
→ v1.27.x: disabled, reason: "Too old for cluster v1.29"
→ v1.31.x: disabled, reason: "Too new for cluster v1.29"
```

### Docker Engine compatibility

```python
"version_constraint": {
    "type": "os_repo",
    "note": "Docker version depends on what the OS repository provides",
    # Ubuntu 22.04 ships docker.io 24.x
    # Ubuntu 24.04 ships docker.io 26.x
    # docker-ce repo has latest
}
```

### Framework coupling

```python
# PyTorch version → CUDA version compatibility
"version_constraint": {
    "type": "matrix",
    "matrix": {
        "2.2": ["cu118", "cu121"],
        "2.3": ["cu118", "cu121", "cu124"],
        "2.4": ["cu121", "cu124"],
    },
    # User picks PyTorch version → CUDA options filtered
}
```

---

## How Version Affects Commands

### Version in package name

| Package manager | Version in name | Example |
|----------------|----------------|---------|
| apt | Package name varies | `python3.12` vs `python3.11` |
| brew | `@` suffix | `python@3.12` vs `python@3.11` |
| pip | `==` suffix | `torch==2.3.0` |
| npm | `@` suffix | `eslint@8.0.0` |
| snap | `--channel` flag | `kubectl --channel=1.29/stable` |
| binary | URL path changes | `.../v1.30.2/kubectl` |

### Version interpolation in install command

```python
"install_variants": {
    "3.12": {
        "debian": ["apt-get", "install", "-y", "python3.12"],
        "rhel": ["dnf", "install", "-y", "python3.12"],
        "brew": ["brew", "install", "python@3.12"],
    },
    "3.11": {
        "debian": ["apt-get", "install", "-y", "python3.11"],
        "rhel": ["dnf", "install", "-y", "python3.11"],
        "brew": ["brew", "install", "python@3.11"],
    },
}
```

Or with template:

```python
"install_template": {
    "debian": ["apt-get", "install", "-y", "python{version}"],
    "brew": ["brew", "install", "python@{version}"],
}
# version value substituted at plan generation
```

---

## Default Selection Strategy

### Priority order

1. **Recommended/LTS:** If a version is marked LTS or recommended → default
2. **Match existing:** If the tool is already partially installed → match
3. **Match cluster:** If version constraint exists → match constraint
4. **Latest stable:** Fall back to latest non-pre-release
5. **User preference:** If user previously selected → remember

### Default markers

```python
{"id": "3.12", "label": "Python 3.12 (Recommended)", "default": True}
{"id": "3.11", "label": "Python 3.11 (Maintenance)"}
{"id": "3.13", "label": "Python 3.13 (Latest)",
 "warning": "Some packages may not support 3.13 yet"}
```

### Labels

| Tag | Meaning | Default? |
|-----|---------|----------|
| Recommended | Best for most users | ✅ Yes |
| LTS | Long-term support | ✅ Usually |
| Latest | Newest release | Only if no LTS |
| Current | Newest, not LTS | ❌ No |
| Previous | Older but supported | ❌ No |
| Maintenance | Security fixes only | ❌ No |
| Experimental | Unstable | ❌ No |
| Nightly | Daily builds | ❌ No |

---

## Caching

### API response caching

```python
VERSION_CACHE = {}

def _fetch_versions(url: str, cache_ttl: int) -> list[str]:
    now = time.time()
    cached = VERSION_CACHE.get(url)
    if cached and (now - cached["fetched_at"]) < cache_ttl:
        return cached["versions"]

    try:
        resp = requests.get(url, timeout=10)
        versions = _parse_versions(resp)
        VERSION_CACHE[url] = {
            "versions": versions,
            "fetched_at": now,
        }
        return versions
    except requests.RequestException:
        # Return cached even if expired, or empty
        if cached:
            return cached["versions"]
        return []
```

### Cache TTL guidelines

| Source | TTL | Rationale |
|-------|-----|-----------|
| GitHub Releases API | 1 hour | Rate-limited, releases are infrequent |
| dl.k8s.io/stable.txt | 1 hour | Changes ~quarterly |
| PyPI versions | 30 min | More frequent releases |
| npm registry | 30 min | Frequent releases |

### Offline fallback

If API is unreachable:
1. Use cached version (even if expired)
2. If no cache: fall back to static list in recipe
3. If no static list: use "latest" without version pin

---

## Edge Cases

| Case | Impact | Handling |
|------|--------|---------|
| API unreachable | Can't fetch versions | Cached → static fallback → "latest" |
| API rate limited (GitHub) | 403 response | Use cached, warn user |
| No version in apt repo | `apt-get install python3.12` fails | Check `apt-cache policy` first |
| PPA needed for version | Extra repo setup required | `repo_setup` field in recipe |
| Version yanked/recalled | Security issue | Filter known-bad versions |
| Pre-release in API response | User installs unstable | `exclude: "alpha\|beta\|rc"` filter |
| kubectl no cluster | Can't detect constraint | fallback: latest stable |
| Multiple Python versions | Which is default? | `update-alternatives` or explicit path |
| Version downgrade | User wants older version | Allow, but warn if current is newer |

---

## Traceability

| Topic | Source |
|-------|--------|
| Static version lists | scope-expansion §2.13 |
| Dynamic version fetch | scope-expansion §2.13 (fetch_url, parse, cache_ttl) |
| kubectl version constraint | scope-expansion §2.13 ("must match cluster ±1 minor") |
| Rust channels | scope-expansion §2.13 (stable, beta, nightly) |
| PyTorch version → CUDA matrix | domain-ml-ai §version coupling |
| Version in package name | domain-package-managers (apt, brew naming) |
| Template substitution | domain-inputs §template substitution |
| Choice schema (version as choice) | domain-choices §single choice |
