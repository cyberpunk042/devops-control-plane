"""
L0 Data — ML & AI tools.

Categories: ml
Pure data, no logic.
"""

from __future__ import annotations

import sys

from src.core.services.tool_install.data.constants import _PIP


_ML_RECIPES: dict[str, dict] = {
    #
    # Spec: domain-ml-ai §Recipes.
    # These use choice-based GPU/CPU variant selection.

    "pytorch": {
        "label": "PyTorch",
        "cli_verify_args": ["-c", "import torch; print(torch.__version__)"],
        "category": "ml",
        "risk": "low",
        "choices": [{
            "id": "variant",
            "label": "PyTorch variant",
            "type": "single",
            "options": [
                {
                    "id": "cpu",
                    "label": "CPU only",
                    "description": "Installs PyTorch with CPU-only support. "
                        "Suitable for development, testing, and inference on "
                        "machines without a dedicated GPU.",
                    "risk": "low",
                    "estimated_time": "2-5 minutes",
                    "default": True,
                },
                {
                    "id": "cuda",
                    "label": "NVIDIA CUDA (GPU accelerated)",
                    "description": "Installs PyTorch with NVIDIA CUDA support "
                        "for GPU-accelerated training and inference. Requires "
                        "a compatible NVIDIA GPU and CUDA drivers.",
                    "risk": "low",
                    "warning": "Requires NVIDIA drivers and CUDA toolkit. "
                        "Package is significantly larger (~2 GB).",
                    "estimated_time": "5-15 minutes",
                    "requires": {"hardware": ["nvidia"]},
                },
                {
                    "id": "rocm",
                    "label": "AMD ROCm (GPU accelerated)",
                    "description": "Installs PyTorch with AMD ROCm support "
                        "for GPU-accelerated training on AMD Radeon GPUs. "
                        "Requires ROCm drivers installed.",
                    "risk": "low",
                    "warning": "Requires ROCm stack installed. Limited "
                        "platform support compared to CUDA.",
                    "estimated_time": "5-15 minutes",
                    "requires": {"hardware": ["amd"]},
                },
            ],
        }],
        "install_variants": {
            "cpu": {
                "command": [
                    "pip3", "install", "torch", "torchvision",
                    "torchaudio", "--index-url",
                    "https://download.pytorch.org/whl/cpu",
                ],
            },
            "cuda": {
                "command": [
                    "pip3", "install", "torch", "torchvision",
                    "torchaudio",
                ],
            },
            "rocm": {
                "command": [
                    "pip3", "install", "torch", "torchvision",
                    "torchaudio", "--index-url",
                    "https://download.pytorch.org/whl/rocm6.2",
                ],
            },
        },
        "install": {
            "pip": ["pip3", "install", "torch"],
        },
        "needs_sudo": {"pip": False},
        "verify": [sys.executable, "-c", "import torch; print(torch.__version__)"],
    },
    "opencv": {
        "label": "OpenCV",
        "cli_verify_args": ["-c", "import cv2; print(cv2.__version__)"],
        "category": "ml",
        "risk": "low",
        "choices": [{
            "id": "variant",
            "label": "OpenCV variant",
            "type": "single",
            "options": [
                {
                    "id": "headless",
                    "label": "Headless (no GUI, pip install)",
                    "description": "Minimal OpenCV without GUI dependencies. "
                        "Ideal for servers, containers, and headless "
                        "image/video processing pipelines.",
                    "risk": "low",
                    "estimated_time": "1-3 minutes",
                    "default": True,
                },
                {
                    "id": "full",
                    "label": "Full (GUI support, pip install)",
                    "description": "OpenCV with GUI support (highgui, imshow). "
                        "Requires X11 or Wayland display server for window "
                        "display functions.",
                    "risk": "low",
                    "warning": "Requires display server (X11/Wayland). "
                        "Will not work in headless environments.",
                    "estimated_time": "1-3 minutes",
                },
                {
                    "id": "contrib",
                    "label": "Full + contrib modules (pip install)",
                    "description": "Full OpenCV plus community-contributed "
                        "modules (face detection, tracking, SIFT, etc.). "
                        "Largest package but most feature-complete.",
                    "risk": "low",
                    "estimated_time": "2-5 minutes",
                },
            ],
        }],
        "install_variants": {
            "headless": {
                "command": ["pip3", "install", "opencv-python-headless"],
            },
            "full": {
                "command": ["pip3", "install", "opencv-python"],
            },
            "contrib": {
                "command": ["pip3", "install", "opencv-contrib-python"],
            },
        },
        "install": {
            "pip": ["pip3", "install", "opencv-python-headless"],
        },
        "needs_sudo": {"pip": False},
        "verify": [sys.executable, "-c", "import cv2; print(cv2.__version__)"],
    },

    "jupyter": {
        "label": "Jupyter Notebook",
        "category": "ml",
        "install": {"_default": _PIP + ["install", "jupyter"]},
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "pip"},
        "verify": ["jupyter", "--version"],
        "update": {"_default": _PIP + ["install", "--upgrade", "jupyter"]},
    },
    "numpy": {
        "label": "NumPy",
        "category": "ml",
        "install": {"_default": _PIP + ["install", "numpy"]},
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "pip"},
        "verify": [sys.executable, "-c", "import numpy; print(numpy.__version__)"],
    },
    "pandas": {
        "label": "Pandas",
        "category": "ml",
        "install": {"_default": _PIP + ["install", "pandas"]},
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "pip"},
        "verify": [sys.executable, "-c", "import pandas; print(pandas.__version__)"],
    },
    "tensorflow": {
        "label": "TensorFlow",
        "category": "ml",
        "install": {"_default": _PIP + ["install", "tensorflow"]},
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "pip"},
        "verify": [sys.executable, "-c",
                   "import tensorflow; print(tensorflow.__version__)"],
    },

    # ── OCR ───────────────────────────────────────────────────
    "tesseract": {
        "label": "Tesseract OCR",
        "cli": "tesseract",
        "category": "ml",
        "risk": "low",
        "install": {
            "apt": ["apt-get", "install", "-y", "tesseract-ocr"],
            "dnf": ["dnf", "install", "-y", "tesseract"],
            "brew": ["brew", "install", "tesseract"],
            "apk": ["apk", "add", "tesseract-ocr"],
            "pacman": ["pacman", "-S", "--noconfirm", "tesseract"],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "brew": False,
            "apk": True, "pacman": True,
        },
        "requires": {
            "packages": {
                "debian": ["tesseract-ocr-eng", "libtesseract-dev"],
                "rhel": ["tesseract-langpack-eng"],
                "alpine": ["tesseract-ocr-data-eng"],
                "arch": ["tesseract-data-eng"],
                "macos": [],  # brew formula includes eng data
            },
        },
        "verify": ["tesseract", "--version"],
        "rollback": {
            "apt": ["apt-get", "remove", "-y", "tesseract-ocr"],
            "dnf": ["dnf", "remove", "-y", "tesseract"],
            "brew": ["brew", "uninstall", "tesseract"],
        },
    },
    "pytesseract": {
        "label": "pytesseract (Python OCR wrapper)",
        "cli": sys.executable,  # verify via Python import, not PATH lookup
        "cli_verify_args": ["-c", "import pytesseract; from PIL import Image; print('OCR deps OK')"],
        "category": "ml",
        "risk": "low",
        "install": {
            "_default": _PIP + ["install", "pytesseract", "Pillow"],
        },
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "pip"},
        "requires": {
            "binaries": ["tesseract"],  # Resolver recurses → installs system tesseract first
        },
        "verify": [sys.executable, "-c",
                    "import pytesseract; from PIL import Image; print('OCR deps OK')"],
    },
}
