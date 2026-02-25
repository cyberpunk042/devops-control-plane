# Domain: Data Packs

> This document catalogs post-install data downloads: spaCy
> language models, NLTK corpora, Hugging Face models, Tesseract
> OCR language data, and system locale packs. Covers the data pack
> schema, size estimation, multi-select UI, download progress,
> and storage locations.
>
> SOURCE DOCS: scope-expansion §2.11 (language/data packs),
>              scope-expansion §Phase 7 roadmap,
>              domain-ml-ai §spaCy, §HuggingFace, §NLTK

---

## Overview

Data packs are OPTIONAL downloads that happen AFTER a tool is
installed. Unlike the tool itself, data packs:

- Are NOT required for the tool to function (tool works without them)
- Can be large (MB to hundreds of GB)
- Allow multi-select (user picks which ones)
- Can be downloaded later (not part of initial install)

### When data packs exist

| Pattern | Example |
|---------|---------|
| NLP model after framework install | spaCy → en_core_web_sm |
| Data corpus after library install | NLTK → punkt tokenizer |
| Pre-trained model for inference | HuggingFace → bert-base |
| OCR language data | Tesseract → eng.traineddata |
| System locale data | locale-gen → en_US.UTF-8 |

### Phase 2 vs Phase 7

| Phase | Data pack capability |
|-------|---------------------|
| Phase 2 | No data packs. No ML frameworks. No post-install downloads. |
| Phase 7 | Full data pack UI: multi-select, size display, download progress, disk check. |

---

## Data Pack Schema

### Recipe format

```python
"data_packs": [
    {
        "id": "en_core_web_sm",          # unique identifier
        "label": "English (small)",       # human-readable name
        "description": "Small English model for basic NLP tasks",
        "size": "13 MB",                  # human-readable display
        "size_bytes": 13631488,           # for disk space check
        "command": [sys.executable, "-m", "spacy",
                    "download", "en_core_web_sm"],
        "verify": [sys.executable, "-c",
                   "import spacy; spacy.load('en_core_web_sm')"],
        "category": "language_model",     # for grouping in UI
        "requires": {},                   # optional hardware/auth
        "default": True,                  # pre-selected in UI
    },
],
"data_pack_choice": {
    "type": "multi",          # "multi" (checkboxes) or "single" (radio)
    "label": "Language Models",
    "description": "Select models to download after installation",
    "min_select": 0,          # 0 = all optional
    "max_select": None,       # None = unlimited
},
```

### Schema fields

| Field | Type | Required | Purpose |
|-------|------|----------|---------|
| `id` | str | ✅ | Unique identifier within recipe |
| `label` | str | ✅ | Display name in UI |
| `description` | str | ❌ | Longer explanation |
| `size` | str | ✅ | Human-readable size for display |
| `size_bytes` | int | ✅ | Exact bytes for disk check |
| `command` | list[str] | ✅ | Download command |
| `verify` | list[str] | ❌ | Verification after download |
| `category` | str | ❌ | Group label in UI |
| `requires` | dict | ❌ | Hardware/auth prerequisites |
| `default` | bool | ❌ | Pre-selected in multi-select |
| `needs_sudo` | bool | ❌ | Defaults to False |

---

## Data Pack Types

### 1. NLP Language Models (spaCy)

```python
"spacy_data": [
    {"id": "en_core_web_sm", "label": "English (small)",
     "size": "13 MB", "size_bytes": 13_631_488,
     "command": [sys.executable, "-m", "spacy", "download", "en_core_web_sm"],
     "default": True},
    {"id": "en_core_web_md", "label": "English (medium)",
     "size": "43 MB", "size_bytes": 45_088_768},
    {"id": "en_core_web_lg", "label": "English (large)",
     "size": "741 MB", "size_bytes": 776_994_816},
    {"id": "en_core_web_trf", "label": "English (transformer)",
     "size": "438 MB", "size_bytes": 459_276_288,
     "requires": {"hardware": {"gpu.nvidia.present": True}}},
    {"id": "de_core_news_sm", "label": "German (small)",
     "size": "13 MB", "size_bytes": 13_631_488},
    {"id": "fr_core_news_sm", "label": "French (small)",
     "size": "15 MB", "size_bytes": 15_728_640},
    {"id": "es_core_news_sm", "label": "Spanish (small)",
     "size": "12 MB", "size_bytes": 12_582_912},
    {"id": "zh_core_web_sm", "label": "Chinese (small)",
     "size": "46 MB", "size_bytes": 48_234_496},
    {"id": "xx_ent_wiki_sm", "label": "Multi-language (small)",
     "size": "12 MB", "size_bytes": 12_582_912},
]
```

**Storage:** `~/.local/lib/pythonX.Y/site-packages/MODELNAME/`
(inside the venv or user site-packages).

**Download mechanism:** `spacy download` is pip install under the
hood — it downloads a pip package from PyPI.

### 2. NLP Data Corpora (NLTK)

```python
"nltk_data": [
    {"id": "punkt", "label": "Punkt sentence tokenizer",
     "size": "1.2 MB", "size_bytes": 1_258_291,
     "command": [sys.executable, "-c",
                 "import nltk; nltk.download('punkt')"],
     "default": True},
    {"id": "punkt_tab", "label": "Punkt (tabular format)",
     "size": "2.8 MB", "size_bytes": 2_936_012,
     "command": [sys.executable, "-c",
                 "import nltk; nltk.download('punkt_tab')"]},
    {"id": "wordnet", "label": "WordNet vocabulary database",
     "size": "10 MB", "size_bytes": 10_485_760,
     "command": [sys.executable, "-c",
                 "import nltk; nltk.download('wordnet')"]},
    {"id": "stopwords", "label": "Stopword lists (16 languages)",
     "size": "32 KB", "size_bytes": 32_768,
     "command": [sys.executable, "-c",
                 "import nltk; nltk.download('stopwords')"]},
    {"id": "averaged_perceptron_tagger", "label": "POS tagger",
     "size": "6.8 MB", "size_bytes": 7_130_317,
     "command": [sys.executable, "-c",
                 "import nltk; nltk.download('averaged_perceptron_tagger')"]},
    {"id": "all", "label": "All NLTK data (everything)",
     "size": "3.2 GB", "size_bytes": 3_435_973_837,
     "category": "bundle"},
]
```

**Storage:** `~/nltk_data/` by default, or `$NLTK_DATA` env var.

**Download mechanism:** NLTK's built-in downloader fetches from
`https://raw.githubusercontent.com/nltk/nltk_data/`.

### 3. Pre-trained Models (Hugging Face)

```python
"hf_models": [
    {"id": "bert-base-uncased", "label": "BERT (base)",
     "size": "440 MB", "size_bytes": 461_373_440,
     "command": ["huggingface-cli", "download", "bert-base-uncased"]},
    {"id": "gpt2", "label": "GPT-2 (small)",
     "size": "548 MB", "size_bytes": 574_619_648,
     "command": ["huggingface-cli", "download", "gpt2"]},
    {"id": "whisper-base", "label": "Whisper (base, speech-to-text)",
     "size": "290 MB", "size_bytes": 304_087_040,
     "command": ["huggingface-cli", "download",
                 "openai/whisper-base"]},
    {"id": "sd-v1-5", "label": "Stable Diffusion v1.5",
     "size": "4 GB", "size_bytes": 4_294_967_296,
     "requires": {"hardware": {"gpu.nvidia.present": True,
                                "disk_free_gb": ">=10.0"}}},
    {"id": "llama2-7b", "label": "LLaMA 2 (7B)",
     "size": "13 GB", "size_bytes": 13_958_643_712,
     "requires": {"auth": "hf_token",
                  "hardware": {"disk_free_gb": ">=20.0"}}},
]
```

**Storage:** `~/.cache/huggingface/hub/` by default, or
`$HF_HOME/hub/` or `$HUGGINGFACE_HUB_CACHE`.

**Download mechanism:** `huggingface-cli` or Python API. Supports
resume on interrupted downloads.

**Authentication:** Gated models (LLaMA, etc.) require a token:
```python
"requires": {
    "auth": {
        "type": "token",
        "env_var": "HF_TOKEN",
        "prompt": "Enter your Hugging Face access token",
        "url": "https://huggingface.co/settings/tokens",
    },
},
```

### 4. OCR Language Data (Tesseract)

```python
"tesseract_data": [
    {"id": "eng", "label": "English",
     "size": "4.2 MB", "size_bytes": 4_404_019,
     "command": ["apt-get", "install", "-y", "tesseract-ocr-eng"],
     "needs_sudo": True},
    {"id": "fra", "label": "French",
     "size": "3.8 MB", "size_bytes": 3_984_588,
     "command": ["apt-get", "install", "-y", "tesseract-ocr-fra"],
     "needs_sudo": True},
    {"id": "deu", "label": "German",
     "size": "4.0 MB", "size_bytes": 4_194_304,
     "command": ["apt-get", "install", "-y", "tesseract-ocr-deu"],
     "needs_sudo": True},
    {"id": "chi-sim", "label": "Chinese (Simplified)",
     "size": "2.5 MB", "size_bytes": 2_621_440,
     "command": ["apt-get", "install", "-y", "tesseract-ocr-chi-sim"],
     "needs_sudo": True},
    {"id": "all", "label": "All languages (~100)",
     "size": "650 MB", "size_bytes": 681_574_400,
     "command": ["apt-get", "install", "-y", "tesseract-ocr-all"],
     "needs_sudo": True, "category": "bundle"},
]
```

**Storage:** `/usr/share/tesseract-ocr/4.00/tessdata/` (system).

**Download mechanism:** System packages (apt/dnf). Each language
is a separate package.

**Platform variance:** Package names differ:
| Family | Package pattern |
|--------|----------------|
| debian | `tesseract-ocr-LANG` |
| rhel | `tesseract-langpack-LANG` |
| alpine | `tesseract-ocr-data-LANG` |

### 5. System Locale Packs

```python
"locale_packs": [
    {"id": "en_US", "label": "English (US)",
     "size": "1 MB", "size_bytes": 1_048_576,
     "command": ["bash", "-c",
                 "locale-gen en_US.UTF-8 && update-locale"],
     "needs_sudo": True},
    {"id": "fr_FR", "label": "French (France)",
     "size": "1 MB", "size_bytes": 1_048_576,
     "command": ["bash", "-c",
                 "locale-gen fr_FR.UTF-8 && update-locale"],
     "needs_sudo": True},
    {"id": "de_DE", "label": "German (Germany)",
     "size": "1 MB", "size_bytes": 1_048_576,
     "command": ["bash", "-c",
                 "locale-gen de_DE.UTF-8 && update-locale"],
     "needs_sudo": True},
]
```

**Storage:** `/usr/lib/locale/` (compiled locale data).

**Platform variance:**
| Family | Method |
|--------|--------|
| debian | `locale-gen LOCALE && update-locale` |
| rhel | `localedef -i LANG -f UTF-8 LOCALE` |
| alpine | Install `musl-locales` package |

---

## Size Estimation

### Pre-download disk check

```python
def _check_data_pack_space(selected_packs: list[dict],
                            install_path: str = "/") -> dict:
    """Check if sufficient disk space for selected data packs."""
    total_bytes = sum(p["size_bytes"] for p in selected_packs)
    usage = shutil.disk_usage(install_path)
    free_bytes = usage.free

    # 10% safety margin
    required_bytes = int(total_bytes * 1.1)

    return {
        "total_download": _human_size(total_bytes),
        "disk_free": _human_size(free_bytes),
        "sufficient": free_bytes >= required_bytes,
        "shortfall": _human_size(required_bytes - free_bytes)
                     if free_bytes < required_bytes else None,
    }

def _human_size(bytes_val: int) -> str:
    """Format bytes as human-readable string."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes_val < 1024:
            return f"{bytes_val:.1f} {unit}"
        bytes_val /= 1024
```

### Display in UI

```
Selected data packs:
  ☑ English (small)         13 MB
  ☑ English (large)        741 MB
  ☐ German (small)          13 MB
  ☑ Punkt tokenizer        1.2 MB
  ────────────────────────────────
  Total download:          755 MB
  Disk free:              42.3 GB   ✅
```

---

## Multi-Select UI

### UI components (Phase 7)

```
┌─ Language Models ─────────────────────────────────┐
│                                                    │
│  ☑ English (small)              13 MB   [default] │
│    Basic NLP: tokenization, NER, POS tagging       │
│                                                    │
│  ☐ English (medium)             43 MB              │
│    Better accuracy, word vectors included           │
│                                                    │
│  ☐ English (large)             741 MB              │
│    Best accuracy, large word vectors                │
│                                                    │
│  ☐ English (transformer)       438 MB   [GPU ⚡]   │
│    Transformer-based, requires GPU                  │
│                                                    │
│  ☑ Punkt tokenizer             1.2 MB  [default]  │
│    Sentence boundary detection                      │
│                                                    │
│  ─────────────────────────────────────────────     │
│  Selected: 2 packs │ Total: 14.2 MB │ Free: 42 GB │
└────────────────────────────────────────────────────┘
```

### Multi-select behavior

| Behavior | Value |
|----------|-------|
| Default selection | Items with `"default": True` are pre-checked |
| GPU items | Show ⚡ icon, disabled if no GPU detected |
| Auth items | Show 🔑 icon, prompt for token if selected |
| Bundle items | "All" option overrides individual selections |
| Size display | Live total updates as items are checked/unchecked |
| Disk check | Real-time comparison against free disk space |

---

## Download Progress

### Progress sources

| Data pack type | Progress available? | How |
|---------------|-------------------|-----|
| spaCy models | ⚠️ pip progress | pip download progress (line-by-line) |
| NLTK data | ❌ Minimal | NLTK shows file names only |
| HF models | ✅ Good | `huggingface-cli` shows progress bar with % |
| Tesseract | ⚠️ apt progress | apt-get shows download progress |
| Locale | ❌ Fast | Completes instantly, no progress needed |

### Progress display (Phase 7)

```
Downloading data packs...

  ✅ Punkt tokenizer          1.2 MB    done (0.3s)
  ⏳ English (small)          13 MB     [████████░░░░░░░░] 52%
  ⏸ English (large)          741 MB    waiting...

  Overall: 1/3 complete │ 7.2 MB / 755 MB
```

---

## Storage Locations

| Data pack type | Default location | Env override |
|---------------|-----------------|-------------|
| spaCy models | Inside venv site-packages | `SPACY_DATA` |
| NLTK data | `~/nltk_data/` | `NLTK_DATA` |
| HF models | `~/.cache/huggingface/hub/` | `HF_HOME`, `HUGGINGFACE_HUB_CACHE` |
| Tesseract | `/usr/share/tesseract-ocr/` | `TESSDATA_PREFIX` |
| Locales | `/usr/lib/locale/` | N/A |

### Disk usage awareness

Downloads go to different locations. The disk check must verify
the correct filesystem:

```python
# spaCy/pip → wherever the venv is
check_space(venv_path, selected_spacy_packs)

# NLTK → home directory
check_space(os.path.expanduser("~/nltk_data"), selected_nltk_packs)

# HF → home cache
check_space(os.path.expanduser("~/.cache/huggingface"), selected_hf_packs)

# Tesseract → root filesystem
check_space("/usr/share", selected_tesseract_packs)
```

---

## Edge Cases

| Case | Impact | Handling |
|------|--------|---------|
| Disk full mid-download | Partial/corrupt data | Pre-check space, cleanup on failure |
| Network timeout | Incomplete download | Retry with backoff, resume if supported |
| Gated model (no token) | Download denied (403) | Prompt for token before download |
| Wrong Python version | spaCy model incompatible | Model version matches spaCy version |
| Proxy/firewall | Download blocked | Proxy config (domain-repos) |
| Air-gapped | No download possible | Pre-download, offline cache |
| Multiple venvs | Models in wrong venv | Download into active venv |
| Large model (100+ GB) | Hours of download | Progress display, resume support |
| spaCy model already installed | Reinstall wastes bandwidth | Check before download (`spacy.load()`) |
| NLTK already has data | Reinstall wastes bandwidth | Check `~/nltk_data/` before download |

---

## Phase Roadmap

| Phase | Data pack capability |
|-------|---------------------|
| Phase 2 | No data packs. |
| Phase 7 | Full implementation: schema, multi-select UI, size estimation, download progress, disk check, auth prompts. |
| Phase 8+ | Resume interrupted downloads. Parallel downloads. Offline cache. |

---

## Traceability

| Topic | Source |
|-------|--------|
| Data pack schema | scope-expansion §2.11 |
| spaCy models | scope-expansion §2.11 (spacy download) |
| NLTK data | scope-expansion §2.11 (nltk.download) |
| HF model downloads | scope-expansion §2.11 (huggingface-cli) |
| Tesseract language data | scope-expansion §2.11 |
| Locale packs | scope-expansion §2.11 (locale-gen) |
| Multi-select UI | scope-expansion §Phase 7 (multi-select UI) |
| Size estimation | scope-expansion §Phase 7 (size estimation) |
| Phase 7 roadmap | scope-expansion §Phase 7 |
| ML framework context | domain-ml-ai (spaCy, HF, NLTK sections) |
| Disk space checking | domain-hardware-detect §disk space |
| Auth/tokens | domain-ml-ai §Hugging Face authentication |
