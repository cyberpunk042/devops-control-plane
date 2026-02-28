"""
L0 Data — OCaml tools.

Categories: ocaml
Pure data, no logic.
"""

from __future__ import annotations


_OCAML_RECIPES: dict[str, dict] = {

    "ocaml": {
        "label": "OCaml",
        "category": "ocaml",
        "install": {
            "apt": ["apt-get", "install", "-y", "ocaml"],
            "dnf": ["dnf", "install", "-y", "ocaml"],
            "apk": ["apk", "add", "ocaml"],
            "pacman": ["pacman", "-S", "--noconfirm", "ocaml"],
            "brew": ["brew", "install", "ocaml"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "brew": False},
        "verify": ["ocaml", "--version"],
    },
    "opam": {
        "label": "opam (OCaml package manager)",
        "category": "ocaml",
        "install": {
            "apt": ["apt-get", "install", "-y", "opam"],
            "dnf": ["dnf", "install", "-y", "opam"],
            "pacman": ["pacman", "-S", "--noconfirm", "opam"],
            "brew": ["brew", "install", "opam"],
        },
        "needs_sudo": {"apt": True, "dnf": True,
                       "pacman": True, "brew": False},
        "verify": ["opam", "--version"],
    },
    "dune": {
        "label": "Dune (OCaml build system)",
        "category": "ocaml",
        "install": {
            "apt": ["apt-get", "install", "-y", "ocaml-dune"],
            "brew": ["brew", "install", "dune"],
            "_default": ["opam", "install", "-y", "dune"],
        },
        "needs_sudo": {"apt": True, "brew": False, "_default": False},
        "verify": ["dune", "--version"],
    },
}
