"""
L0 Data — Haskell tools.

Categories: haskell
Pure data, no logic.
"""

from __future__ import annotations


_HASKELL_RECIPES: dict[str, dict] = {

    "ghc": {
        "label": "GHC (Haskell compiler)",
        "category": "haskell",
        "install": {
            "apt": ["apt-get", "install", "-y", "ghc"],
            "dnf": ["dnf", "install", "-y", "ghc"],
            "pacman": ["pacman", "-S", "--noconfirm", "ghc"],
            "brew": ["brew", "install", "ghc"],
        },
        "needs_sudo": {"apt": True, "dnf": True,
                       "pacman": True, "brew": False},
        "verify": ["ghc", "--version"],
    },
    "cabal": {
        "label": "Cabal (Haskell build tool)",
        "category": "haskell",
        "cli": "cabal",
        "install": {
            "apt": ["apt-get", "install", "-y", "cabal-install"],
            "dnf": ["dnf", "install", "-y", "cabal-install"],
            "pacman": ["pacman", "-S", "--noconfirm", "cabal-install"],
            "brew": ["brew", "install", "cabal-install"],
        },
        "needs_sudo": {"apt": True, "dnf": True,
                       "pacman": True, "brew": False},
        "verify": ["cabal", "--version"],
    },
    "stack": {
        "label": "Stack (Haskell tool stack)",
        "category": "haskell",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -sSL https://get.haskellstack.org/ | sh",
            ],
            "brew": ["brew", "install", "haskell-stack"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "install_via": {"_default": "curl_pipe_bash"},
        "requires": {"binaries": ["curl"]},
        "verify": ["stack", "--version"],
    },
}
