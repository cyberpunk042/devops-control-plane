# Tool Install v2 — Phase 7: Data Packs & Downloads

## Context

Phases 2-6 install software (binaries, packages, drivers). Phase 7
handles NON-SOFTWARE artifacts — large data files that tools need
to function: vulnerability databases, ML models, language packs,
GeoIP databases, container images, etc.

### Dependencies

```
Phase 2.4 (execution)   ── provides: execute_plan(), _run_subprocess()
Phase 4 (choices)        ── provides: choice UI (which model, which DB)
Phase 6 (hardware)       ── provides: GPU detection (for ML model selection)
Phase 7 (THIS)           ── provides: data download steps, progress tracking
```

### Domains consumed

| Domain | What Phase 7 uses |
|--------|------------------|
| domain-data-packs | Download lifecycle, integrity, storage |
| domain-ml-ai | ML model downloads, GPU-specific variants |
| domain-network | Download size awareness, offline alternatives |

---

## What Are Data Packs

### Categories

| Category | Examples | Typical size |
|----------|---------|-------------|
| Vulnerability DBs | Trivy DB, pip-audit DB, Grype DB | 50-200 MB |
| ML models | Whisper, Llama, BERT | 100 MB - 70 GB |
| Language data | spaCy models, NLTK data | 10-500 MB |
| GeoIP databases | MaxMind GeoLite2 | 50-100 MB |
| Container images | Docker base images | 50-500 MB |
| Fonts & assets | Nerd Fonts, icon packs | 10-50 MB |
| Offline documentation | man pages, info pages | 10-100 MB |

### Why they need special handling

| Concern | Software installs | Data packs |
|---------|------------------|-----------|
| Size | 1-50 MB typically | 100 MB - 70 GB |
| Download time | Seconds | Minutes to hours |
| Progress tracking | Not critical | Essential |
| Disk space check | Nice to have | Mandatory |
| Integrity check | Package manager handles | Must verify (checksums) |
| Updates | Version bump | Periodic refresh (daily/weekly) |
| Partial download | Restart install | Resume download |
| Storage location | System paths | Configurable (data dir) |

---

## New Step Type: download

```python
def _execute_download_step(step):
    """Download a data pack with progress tracking."""
    url = step["url"]
    dest = Path(step["dest"]).expanduser()
    expected_size = step.get("size_bytes")
    checksum = step.get("checksum")  # "sha256:abc123..."

    # Disk space pre-check
    if expected_size:
        disk_free = shutil.disk_usage(dest.parent).free
        if disk_free < expected_size * 1.2:  # 20% buffer
            return {
                "ok": False,
                "error": f"Not enough disk space. Need {_fmt_size(expected_size)}, "
                         f"have {_fmt_size(disk_free)}",
            }

    # Create dest directory
    dest.parent.mkdir(parents=True, exist_ok=True)

    # Download with progress
    try:
        import urllib.request

        req = urllib.request.Request(url, headers={"User-Agent": "devops-cp"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            total = int(resp.headers.get("Content-Length", 0))

            with open(dest, "wb") as f:
                downloaded = 0
                while True:
                    chunk = resp.read(8192)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)

        # Verify checksum
        if checksum:
            ok = _verify_checksum(dest, checksum)
            if not ok:
                dest.unlink(missing_ok=True)
                return {"ok": False, "error": "Checksum mismatch — download corrupted"}

        return {"ok": True, "message": f"Downloaded {_fmt_size(downloaded)} to {dest}"}

    except Exception as e:
        dest.unlink(missing_ok=True)
        return {"ok": False, "error": f"Download failed: {e}"}


def _verify_checksum(path: Path, expected: str) -> bool:
    """Verify file checksum. Format: 'algo:hex'."""
    import hashlib

    algo, expected_hash = expected.split(":", 1)
    h = hashlib.new(algo)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest() == expected_hash


def _fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"
```

---

## SSE Progress for Downloads

### Streaming download with progress events

```python
def _execute_download_step_stream(step):
    """Download with SSE progress events."""
    url = step["url"]
    dest = Path(step["dest"]).expanduser()

    import urllib.request

    req = urllib.request.Request(url, headers={"User-Agent": "devops-cp"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        total = int(resp.headers.get("Content-Length", 0))
        dest.parent.mkdir(parents=True, exist_ok=True)

        with open(dest, "wb") as f:
            downloaded = 0
            last_pct = -1

            while True:
                chunk = resp.read(8192)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)

                if total > 0:
                    pct = int(downloaded * 100 / total)
                    if pct != last_pct:
                        last_pct = pct
                        yield {
                            "type": "progress",
                            "downloaded": downloaded,
                            "total": total,
                            "percent": pct,
                        }

    yield {"type": "download_done", "size": downloaded}
```

### Frontend progress bar

```javascript
// In step modal, download steps get a progress bar
callbacks.onProgress = (event) => {
    const row = document.getElementById(`step-row-${event.step}`);
    const bar = row.querySelector('.progress-bar');
    if (!bar) {
        row.innerHTML += `
            <div class="progress-track">
                <div class="progress-bar" style="width: 0%"></div>
                <span class="progress-label">0%</span>
            </div>`;
    }
    bar.style.width = event.percent + '%';
    row.querySelector('.progress-label').textContent =
        `${event.percent}% (${_fmtSize(event.downloaded)}/${_fmtSize(event.total)})`;
};
```

---

## Data Pack Recipes

### Trivy vulnerability DB

```python
"trivy-db": {
    "label": "Trivy Vulnerability DB",
    "category": "data",
    "data_type": "vulnerability_db",
    "install": {
        "_default": {
            "type": "tool_command",
            "command": ["trivy", "image", "--download-db-only"],
        },
    },
    "requires": {
        "tools": ["trivy"],
        "network": ["ghcr.io"],
    },
    "update_schedule": "daily",
    "size_estimate_mb": 150,
}
```

### spaCy language model

```python
"spacy-en": {
    "label": "spaCy English Model",
    "category": "data",
    "data_type": "language_model",
    "choices": [
        {
            "id": "model_size",
            "type": "select_one",
            "label": "Model Size",
            "options": [
                {"value": "sm", "label": "Small (12 MB)", "default": True},
                {"value": "md", "label": "Medium (40 MB)"},
                {"value": "lg", "label": "Large (560 MB)"},
                {"value": "trf", "label": "Transformer (400 MB)",
                 "requires": {"hardware": {"gpu_vendor": "nvidia"}}},
            ],
        },
    ],
    "install": {
        "sm": {"_default": ["python", "-m", "spacy", "download", "en_core_web_sm"]},
        "md": {"_default": ["python", "-m", "spacy", "download", "en_core_web_md"]},
        "lg": {"_default": ["python", "-m", "spacy", "download", "en_core_web_lg"]},
        "trf": {"_default": ["python", "-m", "spacy", "download", "en_core_web_trf"]},
    },
    "requires": {
        "tools": ["python"],
        "packages_pip": ["spacy"],
    },
}
```

### ML model (Whisper example)

```python
"whisper-model": {
    "label": "Whisper Speech Model",
    "category": "data",
    "data_type": "ml_model",
    "choices": [
        {
            "id": "model_size",
            "type": "select_one",
            "label": "Model Size",
            "options": [
                {"value": "tiny", "label": "Tiny (39 MB)", "default": True},
                {"value": "base", "label": "Base (74 MB)"},
                {"value": "small", "label": "Small (244 MB)"},
                {"value": "medium", "label": "Medium (769 MB)",
                 "description": "Requires ~5 GB VRAM"},
                {"value": "large", "label": "Large (1.5 GB)",
                 "description": "Requires ~10 GB VRAM",
                 "requires": {"hardware": {"gpu_vendor": "nvidia"}}},
            ],
        },
    ],
    "install": {
        "tiny": {
            "type": "download",
            "url": "https://openaipublic.azureedge.net/main/whisper/models/tiny.pt",
            "dest": "~/.cache/whisper/tiny.pt",
            "size_bytes": 40_894_692,
            "checksum": "sha256:...",
        },
    },
    "size_warning_mb": 500,  # Warn user above this size
}
```

---

## Storage Management

### Data directory conventions

```python
DATA_DIRS = {
    "vulnerability_db": "~/.cache/trivy",
    "language_model": "~/.cache/spacy",
    "ml_model": "~/.cache/whisper",
    "container_image": "/var/lib/docker",  # managed by Docker
    "geoip": "~/.local/share/geoip",
    "fonts": "~/.local/share/fonts",
}
```

### Disk usage tracking

```python
def get_data_pack_usage() -> list[dict]:
    """Report disk usage of installed data packs."""
    usage = []
    for pack_type, base_dir in DATA_DIRS.items():
        path = Path(base_dir).expanduser()
        if path.exists():
            size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
            usage.append({
                "type": pack_type,
                "path": str(path),
                "size_bytes": size,
                "size_human": _fmt_size(size),
            })
    return usage
```

---

## Size Warning & Confirmation

### Before large downloads

```python
def _check_download_size(step: dict) -> dict | None:
    """Return warning if download is large."""
    size = step.get("size_bytes", 0)
    warn_threshold = 500 * 1024 * 1024  # 500 MB

    if size > warn_threshold:
        return {
            "warning": True,
            "size_human": _fmt_size(size),
            "message": f"This download is {_fmt_size(size)}. "
                       f"It may take a while on slow connections.",
            "estimated_time": _estimate_download_time(size),
        }
    return None


def _estimate_download_time(size_bytes: int) -> dict:
    """Estimate download time at various speeds."""
    speeds = {
        "10 Mbps": 10 * 1024 * 1024 / 8,
        "50 Mbps": 50 * 1024 * 1024 / 8,
        "100 Mbps": 100 * 1024 * 1024 / 8,
    }
    return {label: f"{int(size_bytes / speed)}s" for label, speed in speeds.items()}
```

---

## Update Scheduling

### Data pack freshness

```python
DATA_UPDATE_SCHEDULES = {
    "daily": 86400,       # Vulnerability DBs
    "weekly": 604800,     # GeoIP
    "monthly": 2592000,   # ML models (re-download only on new versions)
    "manual": None,       # User-triggered only
}

def check_data_freshness(pack_id: str) -> dict:
    """Check if a data pack needs updating."""
    recipe = TOOL_RECIPES.get(pack_id)
    schedule = recipe.get("update_schedule", "manual")
    ttl = DATA_UPDATE_SCHEDULES.get(schedule)

    if ttl is None:
        return {"stale": False, "schedule": "manual"}

    # Check last download time
    marker = Path(f"~/.cache/devops-cp/data-stamps/{pack_id}").expanduser()
    if not marker.exists():
        return {"stale": True, "reason": "Never downloaded"}

    age = time.time() - marker.stat().st_mtime
    return {
        "stale": age > ttl,
        "age_seconds": int(age),
        "schedule": schedule,
        "next_update": int(ttl - age) if age < ttl else 0,
    }
```

---

## Offline / Air-Gapped Support

### Pre-downloaded data packs

```python
# Air-gapped: data packs provided on USB/network share
"trivy-db-offline": {
    "label": "Trivy DB (offline)",
    "data_type": "vulnerability_db",
    "install": {
        "_default": {
            "type": "local_copy",
            "source": "{offline_media}/data/trivy-db.tar.gz",
            "dest": "~/.cache/trivy/db",
            "extract": "tar.gz",
        },
    },
    "requires": {
        "network": False,  # explicitly does NOT need network
    },
}
```

### Download → sideload workflow

```
Online machine:
  1. Download data pack to USB
  2. Copy checksum file

Air-gapped machine:
  1. Mount USB
  2. Run: devops-cp data install trivy-db --source /mnt/usb/trivy-db.tar.gz
  3. System verifies checksum, installs locally
```

---

## Files Touched

| File | Changes |
|------|---------|
| `tool_install.py` | Add _execute_download_step(), data pack recipes, size checking, freshness tracking. |
| `routes_audit.py` | Add POST /audit/data-status, POST /audit/data-check-updates. |
| `_globals.html` | Progress bar rendering in step modal for download steps. |

---

## Edge Cases

| Case | Impact | Handling |
|------|--------|---------|
| Disk full mid-download | Partial file | Delete partial, report error |
| Network drops during download | Incomplete file | Resume support (Range header) if server supports |
| Checksum mismatch | Corrupted file | Delete and re-download |
| Download takes 30+ min | User thinks hung | Progress bar + ETA |
| Model too large for GPU VRAM | OOM at inference time | Warn based on GPU memory detection |
| Air-gapped, no data available | Tool partially functional | Warn: "trivy will not work without DB" |
| Multiple data packs in parallel | Bandwidth saturation | MAX_PARALLEL_DOWNLOADS = 2 |
| Storage location is read-only | Can't write data | Check write permission before download |
| Data needs periodic refresh | DB becomes stale | Freshness tracking + update notifications |

---

## Traceability

| Topic | Source |
|-------|--------|
| Data pack categories | domain-data-packs §categories |
| Download with integrity | domain-data-packs §integrity |
| Storage conventions | domain-data-packs §storage |
| ML model selection | domain-ml-ai §model sizes |
| GPU-gated model options | domain-ml-ai §GPU requirements |
| Offline alternatives | domain-network §air-gapped |
| Download size awareness | domain-network §download size |
| Progress tracking | domain-parallel-execution §multi-stream |
| Disk space checking | domain-hardware-detect §disk |
| Choice UI for model size | Phase 4 choice modal |
