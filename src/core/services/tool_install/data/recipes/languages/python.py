"""
L0 Data — Python ecosystem tools.

Categories: python
Pure data, no logic.
"""

from __future__ import annotations

from src.core.services.tool_install.data.constants import _PIP


_PYTHON_RECIPES: dict[str, dict] = {

    "ruff": {
        "label": "Ruff",
        "category": "python",
        "install": {"_default": _PIP + ["install", "ruff"]},
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "pip"},
        "verify": ["ruff", "--version"],
        "update": {"_default": _PIP + ["install", "--upgrade", "ruff"]},
    },
    "mypy": {
        "label": "mypy",
        "category": "python",
        "install": {"_default": _PIP + ["install", "mypy"]},
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "pip"},
        "verify": ["mypy", "--version"],
        "update": {"_default": _PIP + ["install", "--upgrade", "mypy"]},
    },
    "pytest": {
        "label": "pytest",
        "category": "python",
        "install": {"_default": _PIP + ["install", "pytest"]},
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "pip"},
        "verify": ["pytest", "--version"],
        "update": {"_default": _PIP + ["install", "--upgrade", "pytest"]},
    },
    "black": {
        "label": "Black",
        "category": "python",
        "install": {"_default": _PIP + ["install", "black"]},
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "pip"},
        "verify": ["black", "--version"],
        "update": {"_default": _PIP + ["install", "--upgrade", "black"]},
    },
    "pip": {
        "cli": "pip",
        "label": "pip",
        "category": "python",
        "install": {
            "apt":    ["apt-get", "install", "-y", "python3-pip"],
            "dnf":    ["dnf", "install", "-y", "python3-pip"],
            "apk":    ["apk", "add", "py3-pip"],
            "pacman": ["pacman", "-S", "--noconfirm", "python-pip"],
            "zypper": ["zypper", "install", "-y", "python3-pip"],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "apk": True,
            "pacman": True, "zypper": True,
        },
        "verify": ["pip", "--version"],
        "update": {"_default": ["pip", "install", "--upgrade", "pip"]},
    },
    "pipx": {
        "cli": "pipx",
        "label": "pipx (install & run Python CLI apps in isolated environments)",
        "category": "python",
        "install": {
            "apt": ["apt-get", "install", "-y", "pipx"],
            "dnf": ["dnf", "install", "-y", "pipx"],
            "apk": ["apk", "add", "pipx"],
            "pacman": ["pacman", "-S", "--noconfirm", "python-pipx"],
            "zypper": ["zypper", "install", "-y", "python3-pipx"],
            "brew": ["brew", "install", "pipx"],
            "_default": [
                "bash", "-c",
                "pip install --user pipx && python3 -m pipx ensurepath",
            ],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "apk": True,
            "pacman": True, "zypper": True,
            "brew": False, "_default": False,
        },
        "install_via": {"_default": "pip"},
        "prefer": ["apt", "dnf", "brew"],
        "requires": {"binaries": ["python3"]},
        "post_env": 'export PATH="$HOME/.local/bin:$PATH"',
        "verify": ["pipx", "--version"],
        "update": {
            "pip": ["pip", "install", "--upgrade", "pipx"],
            "brew": ["brew", "upgrade", "pipx"],
        },
    },

    "poetry": {
        "cli": "poetry",
        "label": "Poetry (Python dependency management and packaging)",
        "category": "python",
        "install": {
            "pipx": ["pipx", "install", "poetry"],
            "pip": ["pip", "install", "--user", "poetry"],
            "apt": ["apt-get", "install", "-y", "python3-poetry"],
            "dnf": ["dnf", "install", "-y", "python3-poetry"],
            "pacman": ["pacman", "-S", "--noconfirm", "python-poetry"],
            "brew": ["brew", "install", "poetry"],
            "_default": [
                "bash", "-c",
                "curl -sSL https://install.python-poetry.org | python3 -",
            ],
        },
        "needs_sudo": {
            "pipx": False, "pip": False,
            "apt": True, "dnf": True, "pacman": True,
            "brew": False, "_default": False,
        },
        "prefer": ["pipx", "_default", "brew"],
        "requires": {"binaries": ["curl"]},
        "post_env": 'export PATH="$HOME/.local/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/.local/bin:$PATH" && poetry --version'],
        "update": {
            "pipx": ["pipx", "upgrade", "poetry"],
            "pip": ["pip", "install", "--upgrade", "poetry"],
            "brew": ["brew", "upgrade", "poetry"],
        },
    },
    "uv": {
        "cli": "uv",
        "label": "uv (extremely fast Python package and project manager)",
        "category": "python",
        "install": {
            "pip": ["pip", "install", "uv"],
            "pipx": ["pipx", "install", "uv"],
            "dnf": ["dnf", "install", "-y", "uv"],
            "apk": ["apk", "add", "uv"],
            "pacman": ["pacman", "-S", "--noconfirm", "uv"],
            "cargo": ["cargo", "install", "--locked", "uv"],
            "brew": ["brew", "install", "uv"],
            "_default": [
                "bash", "-c",
                "curl -LsSf https://astral.sh/uv/install.sh | sh",
            ],
        },
        "needs_sudo": {
            "pip": False, "pipx": False,
            "dnf": True, "apk": True, "pacman": True,
            "cargo": False, "brew": False, "_default": False,
        },
        "install_via": {"_default": "curl_pipe_bash"},
        "prefer": ["_default", "brew", "pipx"],
        "requires": {"binaries": ["curl"]},
        "post_env": 'export PATH="$HOME/.local/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/.local/bin:$PATH" && uv --version'],
        "update": {
            "pip": ["pip", "install", "--upgrade", "uv"],
            "pipx": ["pipx", "upgrade", "uv"],
            "brew": ["brew", "upgrade", "uv"],
            "_default": [
                "bash", "-c",
                "curl -LsSf https://astral.sh/uv/install.sh | sh",
            ],
        },
    },
    "pyright": {
        "cli": "pyright",
        "label": "Pyright (fast Python type checker — by Microsoft)",
        "category": "python",
        # TypeScript/Node.js based. By Microsoft.
        # Primary install via npm (native).
        # PyPI wrapper exists — bundles Node.js internally,
        # so pip/pipx work WITHOUT npm installed.
        # Available: npm, pip, pipx, pacman, brew, snap.
        # NOT in apt, dnf, apk, zypper.
        "install": {
            "pipx": ["pipx", "install", "pyright"],
            "pacman": ["pacman", "-S", "--noconfirm", "pyright"],
            "brew": ["brew", "install", "pyright"],
            "snap": ["snap", "install", "pyright", "--classic"],
            "_default": ["npm", "install", "-g", "pyright"],
        },
        "needs_sudo": {
            "pipx": False, "pacman": True,
            "brew": False, "snap": True,
            "_default": False,
        },
        "install_via": {"_default": "npm"},
        "requires": {"binaries": ["npm"]},
        "prefer": ["pipx", "pacman", "brew", "snap"],
        "verify": ["pyright", "--version"],
        "update": {
            "pipx": ["pipx", "upgrade", "pyright"],
            "pacman": ["pacman", "-Syu", "--noconfirm", "pyright"],
            "brew": ["brew", "upgrade", "pyright"],
            "snap": ["snap", "refresh", "pyright"],
            "_default": ["npm", "update", "-g", "pyright"],
        },
    },
    "isort": {
        "cli": "isort",
        "label": "isort (Python import sorter)",
        "category": "python",
        # Pure Python. Sorts imports per PEP 8 / isort profiles.
        # pipx recommended. pacman: python-isort.
        # NOT in apt, dnf, apk, zypper system repos.
        "install": {
            "pipx": ["pipx", "install", "isort"],
            "pacman": ["pacman", "-S", "--noconfirm", "python-isort"],
            "brew": ["brew", "install", "isort"],
            "_default": _PIP + ["install", "isort"],
        },
        "needs_sudo": {
            "pipx": False, "pacman": True,
            "brew": False, "_default": False,
        },
        "install_via": {"_default": "pip"},
        "prefer": ["pipx", "pacman", "brew"],
        "verify": ["isort", "--version"],
        "update": {
            "pipx": ["pipx", "upgrade", "isort"],
            "pacman": ["pacman", "-Syu", "--noconfirm", "python-isort"],
            "brew": ["brew", "upgrade", "isort"],
            "_default": _PIP + ["install", "--upgrade", "isort"],
        },
    },
    "flake8": {
        "cli": "flake8",
        "label": "Flake8 (Python linter — pycodestyle + pyflakes + mccabe)",
        "category": "python",
        # Pure Python. Combines pycodestyle, pyflakes, mccabe.
        # pipx recommended. pacman: flake8 (same name).
        # NOT in apt, dnf, apk, zypper system repos.
        "install": {
            "pipx": ["pipx", "install", "flake8"],
            "pacman": ["pacman", "-S", "--noconfirm", "flake8"],
            "brew": ["brew", "install", "flake8"],
            "_default": _PIP + ["install", "flake8"],
        },
        "needs_sudo": {
            "pipx": False, "pacman": True,
            "brew": False, "_default": False,
        },
        "install_via": {"_default": "pip"},
        "prefer": ["pipx", "pacman", "brew"],
        "verify": ["flake8", "--version"],
        "update": {
            "pipx": ["pipx", "upgrade", "flake8"],
            "pacman": ["pacman", "-Syu", "--noconfirm", "flake8"],
            "brew": ["brew", "upgrade", "flake8"],
            "_default": _PIP + ["install", "--upgrade", "flake8"],
        },
    },
    "tox": {
        "cli": "tox",
        "label": "tox (Python test automation framework)",
        "category": "python",
        # Pure Python. Automates testing across multiple envs.
        # pipx recommended. pacman: python-tox.
        # NOT in apt, dnf, apk, zypper system repos.
        "install": {
            "pipx": ["pipx", "install", "tox"],
            "pacman": ["pacman", "-S", "--noconfirm", "python-tox"],
            "brew": ["brew", "install", "tox"],
            "_default": _PIP + ["install", "tox"],
        },
        "needs_sudo": {
            "pipx": False, "pacman": True,
            "brew": False, "_default": False,
        },
        "install_via": {"_default": "pip"},
        "prefer": ["pipx", "pacman", "brew"],
        "verify": ["tox", "--version"],
        "update": {
            "pipx": ["pipx", "upgrade", "tox"],
            "pacman": ["pacman", "-Syu", "--noconfirm", "python-tox"],
            "brew": ["brew", "upgrade", "tox"],
            "_default": _PIP + ["install", "--upgrade", "tox"],
        },
    },
    "nox": {
        "cli": "nox",
        "label": "nox (flexible Python test automation)",
        "category": "python",
        # Pure Python. Similar to tox but uses Python for config.
        # pipx recommended. pacman: python-nox.
        # NOT in apt, dnf, apk, zypper system repos.
        "install": {
            "pipx": ["pipx", "install", "nox"],
            "pacman": ["pacman", "-S", "--noconfirm", "python-nox"],
            "brew": ["brew", "install", "nox"],
            "_default": _PIP + ["install", "nox"],
        },
        "needs_sudo": {
            "pipx": False, "pacman": True,
            "brew": False, "_default": False,
        },
        "install_via": {"_default": "pip"},
        "prefer": ["pipx", "pacman", "brew"],
        "verify": ["nox", "--version"],
        "update": {
            "pipx": ["pipx", "upgrade", "nox"],
            "pacman": ["pacman", "-Syu", "--noconfirm", "python-nox"],
            "brew": ["brew", "upgrade", "nox"],
            "_default": _PIP + ["install", "--upgrade", "nox"],
        },
    },
    "pdm": {
        "cli": "pdm",
        "label": "PDM (modern Python package and project manager)",
        "category": "python",
        # Python-based. PEP 582 pioneer, now PEP 621 compliant.
        # NOT in any native system PMs. Python-ecosystem only.
        # pipx is recommended (isolated env).
        # _default: official installer script (pipes to python3).
        "install": {
            "pipx": ["pipx", "install", "pdm"],
            "pip": ["pip", "install", "--user", "pdm"],
            "brew": ["brew", "install", "pdm"],
            "_default": [
                "bash", "-c",
                "curl -sSL https://pdm-project.org/install-pdm.py | python3 -",
            ],
        },
        "needs_sudo": {
            "pipx": False, "pip": False, "brew": False,
            "_default": False,
        },
        "install_via": {"pip": "pip", "_default": "curl_pipe_bash"},
        "requires": {"binaries": ["curl", "python3"]},
        "prefer": ["pipx", "brew", "pip"],
        "post_env": 'export PATH="$HOME/.local/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/.local/bin:$PATH" && pdm --version'],
        "update": {
            "pipx": ["pipx", "upgrade", "pdm"],
            "pip": ["pip", "install", "--upgrade", "pdm"],
            "brew": ["brew", "upgrade", "pdm"],
            "_default": [
                "bash", "-c",
                "curl -sSL https://pdm-project.org/install-pdm.py | python3 -",
            ],
        },
    },
    "hatch": {
        "cli": "hatch",
        "label": "Hatch (modern Python project manager — PyPA)",
        "category": "python",
        # Python-based. Official PyPA project manager.
        # Handles environments, builds, publishing, version bumping.
        # pipx recommended. Available on pacman as python-hatch.
        # NOT in apt, dnf, apk, zypper system repos.
        # Available on conda-forge but we don't track conda.
        "install": {
            "pipx": ["pipx", "install", "hatch"],
            "pacman": ["pacman", "-S", "--noconfirm", "python-hatch"],
            "brew": ["brew", "install", "hatch"],
            "_default": _PIP + ["install", "hatch"],
        },
        "needs_sudo": {
            "pipx": False, "pacman": True,
            "brew": False, "_default": False,
        },
        "install_via": {"_default": "pip"},
        "prefer": ["pipx", "pacman", "brew"],
        "verify": ["hatch", "--version"],
        "update": {
            "pipx": ["pipx", "upgrade", "hatch"],
            "pacman": ["pacman", "-Syu", "--noconfirm", "python-hatch"],
            "brew": ["brew", "upgrade", "hatch"],
            "_default": _PIP + ["install", "--upgrade", "hatch"],
        },
    },
}
