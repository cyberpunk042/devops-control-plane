"""
L0 Data — R language tools.

Categories: rlang
Pure data, no logic.
"""

from __future__ import annotations


_RLANG_RECIPES: dict[str, dict] = {

    "r-base": {
        "label": "R (language)",
        "category": "rlang",
        "cli": "R",
        "install": {
            "apt": ["apt-get", "install", "-y", "r-base"],
            "dnf": ["dnf", "install", "-y", "R"],
            "brew": ["brew", "install", "r"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "brew": False},
        "verify": ["R", "--version"],
    },
    "rscript": {
        "label": "Rscript (R CLI)",
        "category": "rlang",
        "cli": "Rscript",
        "install": {
            "apt": ["apt-get", "install", "-y", "r-base"],
            "dnf": ["dnf", "install", "-y", "R"],
            "brew": ["brew", "install", "r"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "brew": False},
        "verify": ["Rscript", "--version"],
    },
}
