# Domain: Network

> This document catalogs network conditions for the tool install
> system: online vs offline vs partial, proxy detection, air-gapped
> environments, endpoint probing, fallback to local cache, and
> how network state affects install option availability.
>
> SOURCE DOCS: scope-expansion §2.16 (network & offline scenarios),
>              domain-disabled-options §network constraint,
>              domain-version-selection §API fetch,
>              domain-ml-ai §download sizes

---

## Overview

Most install methods require network access. The system must
detect the current network state, probe specific endpoints,
and adapt the available options accordingly.

### Network conditions

| Condition | Frequency | Example |
|-----------|----------|---------|
| Full internet | Common | Dev workstation, cloud VM |
| Behind proxy | Common (enterprise) | Corporate network, HTTP_PROXY set |
| Air-gapped | Uncommon | Secure facilities, classified networks |
| Partial access | Uncommon | Internal mirror reachable, public not |
| Intermittent | Occasional | Unstable WiFi, bandwidth-limited |

---

## Network Profile

### Detection result

```python
{
    "online": True,
    "proxy_detected": True,
    "proxy_url": "http://proxy.corp.com:8080",
    "dns_works": True,
    "latency_class": "normal",      # "fast" | "normal" | "slow" | "offline"
    "endpoints": {
        "pypi.org":              {"reachable": True,  "latency_ms": 45},
        "github.com":            {"reachable": True,  "latency_ms": 120},
        "registry.npmjs.org":    {"reachable": False, "error": "timeout"},
        "download.docker.com":   {"reachable": True,  "latency_ms": 80},
        "dl.k8s.io":             {"reachable": True,  "latency_ms": 95},
        "sh.rustup.rs":          {"reachable": True,  "latency_ms": 60},
    },
}
```

### Detection function

```python
import os, socket, time, urllib.request

def detect_network() -> dict:
    """Detect network availability and probe key endpoints."""
    result = {
        "online": False,
        "proxy_detected": False,
        "proxy_url": None,
        "dns_works": False,
        "latency_class": "offline",
        "endpoints": {},
    }

    # Check proxy env vars
    proxy = (os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY")
             or os.getenv("http_proxy") or os.getenv("https_proxy"))
    if proxy:
        result["proxy_detected"] = True
        result["proxy_url"] = proxy

    # DNS check
    try:
        socket.getaddrinfo("pypi.org", 443, socket.AF_UNSPEC,
                           socket.SOCK_STREAM)
        result["dns_works"] = True
    except socket.gaierror:
        result["dns_works"] = False
        result["latency_class"] = "offline"
        return result

    # Probe endpoints
    endpoints = {
        "pypi.org": "https://pypi.org/simple/",
        "github.com": "https://github.com",
        "registry.npmjs.org": "https://registry.npmjs.org/",
        "download.docker.com": "https://download.docker.com/",
        "dl.k8s.io": "https://dl.k8s.io/",
        "sh.rustup.rs": "https://sh.rustup.rs/",
    }

    latencies = []
    for name, url in endpoints.items():
        start = time.monotonic()
        try:
            req = urllib.request.Request(url, method="HEAD")
            urllib.request.urlopen(req, timeout=5)
            latency = int((time.monotonic() - start) * 1000)
            result["endpoints"][name] = {
                "reachable": True,
                "latency_ms": latency,
            }
            latencies.append(latency)
        except Exception as e:
            result["endpoints"][name] = {
                "reachable": False,
                "error": str(e)[:100],
            }

    # Determine overall state
    reachable = [e for e in result["endpoints"].values() if e["reachable"]]
    result["online"] = len(reachable) > 0
    if latencies:
        avg = sum(latencies) / len(latencies)
        if avg < 100:
            result["latency_class"] = "fast"
        elif avg < 500:
            result["latency_class"] = "normal"
        else:
            result["latency_class"] = "slow"

    return result
```

---

## Proxy Detection

### Environment variables

| Variable | Standard | Used by |
|----------|----------|---------|
| `HTTP_PROXY` | Common | curl, wget, pip, npm |
| `HTTPS_PROXY` | Common | curl, wget, pip, npm |
| `http_proxy` | Common (lowercase) | Some tools prefer lowercase |
| `https_proxy` | Common (lowercase) | Some tools prefer lowercase |
| `NO_PROXY` | Common | Hosts to bypass proxy |
| `ALL_PROXY` | Less common | SOCKS proxy |

### Proxy injection into commands

```python
PROXY_FLAGS = {
    "pip": ["--proxy", "{proxy_url}"],
    "curl": ["--proxy", "{proxy_url}"],
    "wget": ["-e", "use_proxy=yes", "-e", "http_proxy={proxy_url}"],
    "npm": ["--proxy", "{proxy_url}"],
    "git": ["-c", "http.proxy={proxy_url}"],
    # apt: configured via /etc/apt/apt.conf.d/proxy.conf
    # docker: configured via daemon.json or systemd env
}
```

### apt proxy configuration

```python
# For apt behind proxy, write config file
"apt_proxy": {
    "file": "/etc/apt/apt.conf.d/95proxy",
    "template": 'Acquire::http::proxy "{proxy_url}";\n'
                'Acquire::https::proxy "{proxy_url}";\n',
    "needs_sudo": True,
    "condition": "proxy_detected",
}
```

---

## requires.network Field

### In recipes

```python
{
    "label": "Install ruff via pip",
    "command": ["pip", "install", "ruff"],
    "requires": {"network": True},
    # Disabled when offline
}
```

### Endpoint-specific requirements

```python
{
    "label": "Install PyTorch (CUDA 12.1)",
    "command": ["pip", "install", "torch", "--index-url",
                "https://download.pytorch.org/whl/cu121"],
    "requires": {
        "network": True,
        "endpoint": "download.pytorch.org",
    },
}
```

### Impact on disabled options

When network is unavailable:

```python
{
    "id": "pip",
    "label": "pip install",
    "available": False,
    "disabled_reason": "pip install requires internet access (network offline)",
    "enable_hint": "Connect to the internet or use an offline package cache",
    "failed_constraint": "network.online",
}
```

When specific endpoint is down:

```python
{
    "id": "pytorch_cuda121",
    "label": "PyTorch CUDA 12.1",
    "available": False,
    "disabled_reason": "PyTorch download server unreachable "
                       "(download.pytorch.org timed out)",
    "enable_hint": "Check your internet connection or try again later",
    "failed_constraint": "network.endpoint.download.pytorch.org",
}
```

---

## Air-Gapped Environments

### What works offline

| Method | Offline? | How |
|--------|---------|-----|
| System packages (apt/dnf) | ✅ If local repo/mirror | `file:///` repo source |
| Binary download | ❌ Unless pre-downloaded | Cache binary locally |
| pip install | ✅ With local index | `--find-links /path/to/wheels` |
| cargo install | ❌ Unless vendored | `cargo vendor` + `--offline` |
| npm install | ✅ With local registry | Verdaccio or similar |
| curl scripts | ❌ | Pre-download script |
| snap install | ❌ | Snap requires snapd server |

### Offline detection

```python
def is_air_gapped(network_profile: dict) -> bool:
    """Determine if the system is air-gapped."""
    if not network_profile["dns_works"]:
        return True
    reachable = [e for e in network_profile["endpoints"].values()
                 if e["reachable"]]
    return len(reachable) == 0
```

### Offline alternatives

```python
"install_methods": {
    "online": {
        "command": ["pip", "install", "ruff"],
        "requires": {"network": True},
    },
    "offline": {
        "command": ["pip", "install", "--no-index",
                    "--find-links", "/opt/packages/", "ruff"],
        "requires": {"path_exists": "/opt/packages/ruff*.whl"},
        "label": "Install from local cache",
    },
}
```

---

## Download Size Awareness

### Why it matters

| Tool | Download size | Time @ 10 Mbps |
|------|-------------|---------------|
| ruff (pip) | 8 MB | 7 seconds |
| Docker (apt) | ~50 MB | 40 seconds |
| PyTorch CPU (pip) | 200 MB | 2.5 minutes |
| PyTorch CUDA (pip) | 800 MB-1.2 GB | 10-16 minutes |
| NVIDIA CUDA toolkit | 2-3 GB | 25-40 minutes |
| HuggingFace LLaMA-2-7b | ~13 GB | ~3 hours |

### Slow connection handling

```python
if network_profile["latency_class"] == "slow":
    # Warn about large downloads
    for step in plan["steps"]:
        if step.get("download_size_mb", 0) > 100:
            step["warning"] = (
                f"This step downloads ~{step['download_size_mb']} MB. "
                f"On your connection this may take "
                f"{_estimate_time(step['download_size_mb'])}."
            )
```

### Resume support

```python
# Tools that support resume on interrupted download
RESUME_SUPPORT = {
    "pip": False,           # No native resume
    "apt": True,            # apt-get handles resume
    "curl": True,           # curl -C - (resume)
    "wget": True,           # wget -c (continue)
    "huggingface-cli": True, # Built-in resume
    "git lfs": True,        # Built-in resume
}
```

---

## Timeout Configuration

### Per-operation timeouts

| Operation | Default timeout | Rationale |
|-----------|----------------|-----------|
| Endpoint probe | 5 seconds | Quick health check |
| apt-get install | 300 seconds | Package download + install |
| pip install | 120 seconds | Wheel download |
| pip install (large) | 600 seconds | PyTorch etc. |
| Binary download | 120 seconds | Single file |
| Model download | 3600 seconds | Multi-GB models |
| Git clone | 300 seconds | Repo download |

### Timeout in plan steps

```python
{
    "label": "Install PyTorch (CUDA 12.1)",
    "command": ["pip", "install", "torch", "--index-url", "..."],
    "timeout_seconds": 600,
    "download_size_mb": 800,
}
```

---

## Edge Cases

| Case | Impact | Handling |
|------|--------|---------|
| Proxy requires auth | Endpoint probe fails | Detect 407 status, prompt for proxy credentials |
| DNS works but HTTPS blocked | Probe connects then fails | Detect SSL errors specifically |
| Endpoint flaky (intermittent) | Sometimes works, sometimes not | Retry probe 2x before marking unreachable |
| VPN changes network mid-plan | Endpoints may change | Re-probe on step failure |
| IPv6-only network | Some endpoints may not resolve | Probe both IPv4 and IPv6 |
| Captive portal (hotel WiFi) | All HTTP redirects to login page | Detect 302 to unexpected host |
| Rate limiting (GitHub API) | 403 after too many requests | Cache responses, respect rate headers |
| Download interrupted | Partial file | Resume if supported, retry otherwise |
| Corporate SSL inspection | Self-signed cert errors | Detect cert errors, warn user |

---

## Phase Roadmap

| Phase | Network capability |
|-------|--------------------|
| Phase 2 | No network detection. Assumes online. Fails on offline. |
| Phase 3 | Basic probe (online/offline). Endpoint health check. |
| Phase 4 | Proxy detection + injection. requires.network field. |
| Phase 8 | Air-gapped support. Local cache. Download size warnings. |

---

## Traceability

| Topic | Source |
|-------|--------|
| 5 network conditions | scope-expansion §2.16 |
| Endpoint probe structure | scope-expansion §2.16 (network dict) |
| requires.network field | scope-expansion §2.16 ("install methods gain") |
| Proxy injection flags | scope-expansion §2.16 ("pip --proxy, curl --proxy") |
| Disabled option for offline | domain-disabled-options §network unavailable |
| API fetch (dynamic versions) | domain-version-selection §dynamic |
| Download sizes (ML models) | domain-ml-ai §download sizes |
| Download sizes (data packs) | domain-data-packs §size estimation |
