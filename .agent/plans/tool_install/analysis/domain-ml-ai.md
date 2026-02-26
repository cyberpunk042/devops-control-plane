# Domain: ML/AI Frameworks

> ⚠️ **PHASE LABELS MAY BE STALE** — As of 2026-02-25, code has evolved far beyond
> what the phase roadmaps suggest. Many features labeled "Phase 4-8 future" are
> ALREADY IMPLEMENTED. See `audit-domain-docs.md` and `audit-missing-pieces.md`
> for the verified truth. Code is the source of truth, not these phase labels.


> This document catalogs machine learning and AI framework
> installation: PyTorch, TensorFlow, JAX, spaCy, Hugging Face.
> GPU variant selection, pip index switching per CUDA version,
> and post-install data/model downloads.
>
> SOURCE DOCS: scope-expansion §2.10 (NLP/ML frameworks),
>              scope-expansion §2.11 (data packs),
>              domain-gpu §PyTorch variant selection,
>              domain-language-pms §pip (private indexes)

---

## Overview

ML/AI frameworks are the MOST COMPLEX tool installations because
they combine EVERY complexity dimension at once:

1. **GPU variant selection** — different packages per GPU vendor/version
2. **Custom pip indexes** — different download URLs per variant
3. **Large downloads** — gigabytes of wheels, models, data
4. **Hardware constraints** — compute capability minimums
5. **Post-install steps** — model downloads, data packs
6. **Version coupling** — CUDA version ↔ framework version ↔ driver version

### Phase 2 vs Phase 7

| Phase | ML/AI capability |
|-------|-----------------|
| Phase 2 | NOT in scope. None of the 30 tools are ML frameworks. pip/venv infrastructure exists but is used for DevOps tools only. |
| Phase 4 | Decision tree architecture enables variant selection (CPU vs CUDA). |
| Phase 6 | GPU detection enables hardware constraint evaluation. |
| Phase 7 | Data pack downloads (spaCy models, HF models). |

---

## PyTorch

### The variant problem

PyTorch installs COMPLETELY DIFFERENT packages depending on the
compute backend. The pip `--index-url` flag selects which set of
pre-built wheels to download:

| Variant | pip index URL | Requires |
|---------|-------------|----------|
| CPU only | `https://download.pytorch.org/whl/cpu` | Nothing |
| CUDA 11.8 | `https://download.pytorch.org/whl/cu118` | NVIDIA GPU + CUDA 11.8 driver |
| CUDA 12.1 | `https://download.pytorch.org/whl/cu121` | NVIDIA GPU + CUDA 12.1 driver |
| CUDA 12.4 | `https://download.pytorch.org/whl/cu124` | NVIDIA GPU + CUDA 12.4 driver |
| ROCm 5.7 | `https://download.pytorch.org/whl/rocm5.7` | AMD GPU + ROCm 5.7 |
| ROCm 6.0 | `https://download.pytorch.org/whl/rocm6.0` | AMD GPU + ROCm 6.0 |

### Recipe format

```python
"pytorch": {
    "label": "PyTorch",
    "choices": [
        {
            "id": "compute",
            "label": "Compute Platform",
            "options": [
                {"id": "cpu", "label": "CPU only",
                 "pip_index": "https://download.pytorch.org/whl/cpu"},
                {"id": "cuda118", "label": "CUDA 11.8",
                 "pip_index": "https://download.pytorch.org/whl/cu118",
                 "requires": {"hardware": {"gpu.nvidia.present": True}}},
                {"id": "cuda121", "label": "CUDA 12.1",
                 "pip_index": "https://download.pytorch.org/whl/cu121",
                 "requires": {"hardware": {"gpu.nvidia.present": True}}},
                {"id": "cuda124", "label": "CUDA 12.4",
                 "pip_index": "https://download.pytorch.org/whl/cu124",
                 "requires": {"hardware": {"gpu.nvidia.present": True,
                              "gpu.nvidia.compute_capability": ">=7.0"}}},
                {"id": "rocm57", "label": "ROCm 5.7",
                 "pip_index": "https://download.pytorch.org/whl/rocm5.7",
                 "requires": {"hardware": {"gpu.amd.present": True}}},
            ],
        },
    ],
    "install_variants": {
        "cpu":      {"command": _PIP + ["install", "torch", "torchvision",
                                         "--index-url", "{pip_index}"]},
        "cuda118":  {"command": _PIP + ["install", "torch", "torchvision",
                                         "--index-url", "{pip_index}"]},
        "cuda121":  {"command": _PIP + ["install", "torch", "torchvision",
                                         "--index-url", "{pip_index}"]},
        "cuda124":  {"command": _PIP + ["install", "torch", "torchvision",
                                         "--index-url", "{pip_index}"]},
        "rocm57":   {"command": _PIP + ["install", "torch", "torchvision",
                                         "--index-url", "{pip_index}"]},
    },
    "verify": [sys.executable, "-c",
               "import torch; print(f'PyTorch {torch.__version__}, "
               "CUDA: {torch.cuda.is_available()}')"],
    "requires": {"binaries": ["python3"]},
    "needs_sudo": {"_default": False},
}
```

### Download sizes

| Variant | Wheel size | Notes |
|---------|-----------|-------|
| CPU | ~200 MB | Smallest |
| CUDA 11.8 | ~800 MB | Bundles CUDA libs |
| CUDA 12.1 | ~900 MB | Bundles CUDA libs |
| ROCm | ~1.2 GB | Bundles ROCm libs |

### Version coupling

```
PyTorch 2.2 ← supports → CUDA 11.8, 12.1
PyTorch 2.3 ← supports → CUDA 11.8, 12.1, 12.4
PyTorch 2.4 ← supports → CUDA 12.1, 12.4
```

Each PyTorch release drops and adds CUDA version support.
The recipe must track which versions are compatible.

---

## TensorFlow

### Variant model

TensorFlow simplified in TF 2.x: ONE package auto-detects GPU.

```python
# CPU-only install
pip install tensorflow

# GPU install (same package! auto-detects CUDA)
pip install tensorflow
# If CUDA is available: uses GPU
# If CUDA is not available: falls back to CPU
```

### Older TensorFlow (pre-2.x)

```python
# Separate packages (DEPRECATED)
pip install tensorflow       # CPU only
pip install tensorflow-gpu   # GPU version
```

### Recipe format

```python
"tensorflow": {
    "label": "TensorFlow",
    "install": {"_default": _PIP + ["install", "tensorflow"]},
    "verify": [sys.executable, "-c",
               "import tensorflow as tf; print(tf.__version__); "
               "print('GPU:', len(tf.config.list_physical_devices('GPU')))"],
    "requires": {"binaries": ["python3"]},
    "needs_sudo": {"_default": False},
    # GPU automatically detected — no variant selection needed
}
```

### TensorFlow GPU requirements

| Component | Required |
|-----------|----------|
| NVIDIA GPU | Compute capability ≥ 3.5 |
| NVIDIA driver | ≥ 525.60.13 |
| CUDA toolkit | 12.x (TF 2.15+) |
| cuDNN | 8.x |

**Key difference from PyTorch:** TensorFlow bundles its own
CUDA libraries since TF 2.15. No separate CUDA install needed
for basic GPU use.

---

## JAX

### Variant model

JAX uses SEPARATE packages per backend:

```bash
# CPU
pip install jax

# CUDA (pre-built)
pip install jax[cuda12]

# TPU
pip install jax[tpu]

# ROCm (experimental)
pip install jax[rocm]
```

### Recipe format

```python
"jax": {
    "label": "JAX",
    "choices": [
        {
            "id": "backend",
            "label": "Accelerator",
            "options": [
                {"id": "cpu", "label": "CPU only"},
                {"id": "cuda", "label": "CUDA 12",
                 "requires": {"hardware": {"gpu.nvidia.present": True}}},
            ],
        },
    ],
    "install_variants": {
        "cpu":  {"command": _PIP + ["install", "jax"]},
        "cuda": {"command": _PIP + ["install", "jax[cuda12]"]},
    },
    "verify": [sys.executable, "-c",
               "import jax; print(jax.devices())"],
}
```

---

## spaCy

### Install + data pack pattern

spaCy is unique because installation has TWO phases:
1. Install the library (pip)
2. Download language models (separate downloads)

```python
"spacy": {
    "label": "spaCy",
    "install": {"_default": _PIP + ["install", "spacy"]},
    "data_packs": [
        {
            "id": "en_core_web_sm",
            "label": "English (small)",
            "size": "13 MB",
            "command": [sys.executable, "-m", "spacy",
                        "download", "en_core_web_sm"],
        },
        {
            "id": "en_core_web_md",
            "label": "English (medium)",
            "size": "43 MB",
            "command": [sys.executable, "-m", "spacy",
                        "download", "en_core_web_md"],
        },
        {
            "id": "en_core_web_lg",
            "label": "English (large, most accurate)",
            "size": "741 MB",
            "command": [sys.executable, "-m", "spacy",
                        "download", "en_core_web_lg"],
        },
        {
            "id": "en_core_web_trf",
            "label": "English (transformer, GPU recommended)",
            "size": "438 MB",
            "command": [sys.executable, "-m", "spacy",
                        "download", "en_core_web_trf"],
            "requires": {"hardware": {"gpu.nvidia.present": True}},
        },
    ],
    "data_pack_choice": {
        "type": "multi",   # can select multiple
        "label": "Language Models",
        "description": "Select models to download after installation",
    },
    "verify": [sys.executable, "-c", "import spacy; print(spacy.__version__)"],
}
```

### Other languages

spaCy supports 70+ languages. Common models:

| Language | Model | Size |
|----------|-------|------|
| English | en_core_web_sm | 13 MB |
| English | en_core_web_lg | 741 MB |
| German | de_core_news_sm | 13 MB |
| French | fr_core_news_sm | 15 MB |
| Spanish | es_core_news_sm | 12 MB |
| Chinese | zh_core_web_sm | 46 MB |
| Multi-language | xx_ent_wiki_sm | 12 MB |

---

## Hugging Face

### Transformers library + model downloads

```python
"huggingface": {
    "label": "Hugging Face Transformers",
    "install": {"_default": _PIP + ["install", "transformers", "torch"]},
    "data_packs": [
        {
            "id": "bert-base",
            "label": "BERT (base, uncased)",
            "size": "440 MB",
            "command": ["huggingface-cli", "download",
                        "bert-base-uncased"],
        },
        {
            "id": "gpt2",
            "label": "GPT-2 (small)",
            "size": "548 MB",
            "command": ["huggingface-cli", "download", "gpt2"],
        },
        {
            "id": "llama2-7b",
            "label": "LLaMA 2 (7B, requires access)",
            "size": "13 GB",
            "command": ["huggingface-cli", "download",
                        "meta-llama/Llama-2-7b-hf"],
            "requires": {"auth": "hf_token"},
        },
    ],
}
```

### Model download sizes

| Model | Size | Use case |
|-------|------|---------|
| bert-base-uncased | 440 MB | Text classification, NER |
| gpt2 | 548 MB | Text generation |
| whisper-base | 290 MB | Speech-to-text |
| stable-diffusion-v1-5 | 4 GB | Image generation |
| llama-2-7b | 13 GB | LLM |
| llama-2-70b | 130 GB | Large LLM |

**Disk space is the primary constraint** for HF models.

### Authentication

Some models require a Hugging Face access token:
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

---

## NLTK

### Post-install data downloads

```python
"nltk": {
    "label": "NLTK",
    "install": {"_default": _PIP + ["install", "nltk"]},
    "data_packs": [
        {
            "id": "punkt",
            "label": "Punkt tokenizer",
            "size": "1.2 MB",
            "command": [sys.executable, "-c",
                        "import nltk; nltk.download('punkt')"],
        },
        {
            "id": "wordnet",
            "label": "WordNet vocabulary database",
            "size": "10 MB",
            "command": [sys.executable, "-c",
                        "import nltk; nltk.download('wordnet')"],
        },
        {
            "id": "all",
            "label": "All NLTK data (everything)",
            "size": "3.2 GB",
            "command": [sys.executable, "-c",
                        "import nltk; nltk.download('all')"],
        },
    ],
}
```

---

## Common Patterns

### GPU variant selection flow

```
1. Detect GPU (domain-gpu)
   ├── NVIDIA detected
   │   ├── Driver version → determines max CUDA version
   │   ├── Compute capability → filters compatible frameworks
   │   └── Options: CPU, CUDA 11.8, CUDA 12.1, CUDA 12.4
   ├── AMD detected
   │   ├── ROCm version → determines compatibility
   │   └── Options: CPU, ROCm 5.7, ROCm 6.0
   └── No GPU
       └── Options: CPU only (others grayed out)

2. User selects variant
   └── Choice determines pip index URL

3. pip install with --index-url
   └── Downloads GPU-specific wheels

4. Verify GPU access
   └── torch.cuda.is_available() or equivalent
```

### Install + data pack flow

```
1. pip install FRAMEWORK
2. Verify import works
3. Present data pack menu (multi-select UI)
4. Download selected packs
5. Verify each pack loaded (import test)
```

### Download size estimation

```python
"data_packs": [
    {
        "id": "model_a",
        "size": "741 MB",           # displayed to user
        "size_bytes": 776994816,    # for disk space check
    },
],
```

Before downloading, check:
```python
total_bytes = sum(p["size_bytes"] for p in selected_packs)
if total_bytes > available_disk_bytes * 0.9:  # 90% safety margin
    warn("Insufficient disk space for selected models")
```

---

## Comparison Table

| Framework | Variant model | GPU selection | Post-install data | Wheel size |
|-----------|-------------|---------------|-------------------|-----------|
| PyTorch | --index-url per variant | Per-variant pip index | ❌ | 200 MB - 1.2 GB |
| TensorFlow | Single package | Auto-detects GPU | ❌ | ~500 MB |
| JAX | pip extras `[cuda12]` | pip extra per backend | ❌ | 200-500 MB |
| spaCy | Single package | N/A (CPU efficient) | ✅ Models (13 MB - 741 MB) |  ~10 MB |
| Hugging Face | Single package | Via PyTorch/TF backend | ✅ Models (440 MB - 130 GB) | ~5 MB |
| NLTK | Single package | N/A | ✅ Data (1 MB - 3.2 GB) | ~1 MB |

---

## Edge Cases

| Case | Impact | Handling |
|------|--------|---------|
| CUDA version mismatch | PyTorch won't use GPU | Detect CUDA version, match to pip index |
| Old GPU (low compute cap) | Framework crashes on import | Pre-flight compute cap check |
| No pip/venv | Can't install anything | Detect Python first, install pip |
| Disk full during model download | Partial download | Size check before download, resume support |
| Corporate proxy | pip index unreachable | Proxy config (domain-repos) |
| Air-gapped environment | No download possible | Pre-download wheels, offline model cache |
| Multiple CUDA versions | Toolkit vs driver mismatch | Check both nvcc and nvidia-smi |
| HF token missing | Gated model download fails | Prompt for token, link to settings |
| macOS + CUDA | CUDA not available on macOS | Disable CUDA options on Darwin |
| WSL + CUDA | Works if Windows driver supports it | nvidia-smi test in WSL |

---

## Phase Roadmap

| Phase | ML/AI capability |
|-------|-----------------|
| Phase 2 | pip infrastructure exists. No ML frameworks in tool list. |
| Phase 4 | Decision tree allows GPU variant choices. |
| Phase 6 | GPU detection enables hardware constraints. |
| Phase 7 | Data pack UI (multi-select, size display, progress). Model downloads. |

---

## Traceability

| Topic | Source |
|-------|--------|
| PyTorch variant recipe | scope-expansion §2.10 |
| Data pack recipe schema | scope-expansion §2.11 |
| GPU detection | domain-gpu (full document) |
| Compute capability constraints | domain-gpu §NVIDIA compute capability |
| pip --index-url | domain-language-pms §pip (private indexes) |
| _PIP constant | domain-language-pms §pip (venv model) |
| Download size + disk check | domain-hardware-detect §disk space |
| Decision tree architecture | scope-expansion §2.14 |
| Phase roadmap | scope-expansion §Phase 6 + Phase 7 |
