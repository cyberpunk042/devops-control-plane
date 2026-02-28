"""
L0 Data — Elixir & Erlang tools.

Categories: elixir
Pure data, no logic.
"""

from __future__ import annotations


_ELIXIR_RECIPES: dict[str, dict] = {

    "erlang": {
        "label": "Erlang/OTP",
        "category": "elixir",
        "cli": "erl",
        "install": {
            "apt": ["apt-get", "install", "-y", "erlang"],
            "dnf": ["dnf", "install", "-y", "erlang"],
            "apk": ["apk", "add", "erlang"],
            "pacman": ["pacman", "-S", "--noconfirm", "erlang"],
            "zypper": ["zypper", "install", "-y", "erlang"],
            "brew": ["brew", "install", "erlang"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "verify": ["erl", "-eval",
                   "io:format(\"~s~n\", [erlang:system_info(otp_release)]), halt().",
                   "-noshell"],
    },
    "elixir": {
        "label": "Elixir",
        "category": "elixir",
        "install": {
            "apt": ["apt-get", "install", "-y", "elixir"],
            "dnf": ["dnf", "install", "-y", "elixir"],
            "apk": ["apk", "add", "elixir"],
            "pacman": ["pacman", "-S", "--noconfirm", "elixir"],
            "brew": ["brew", "install", "elixir"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "brew": False},
        "requires": {"binaries": ["erl"]},
        "verify": ["elixir", "--version"],
    },
    "mix": {
        "label": "Mix (Elixir build tool)",
        "category": "elixir",
        "install": {
            # Mix comes with Elixir — this just verifies it
            "_default": ["elixir", "-e", "IO.puts Mix.env()"],
        },
        "needs_sudo": {"_default": False},
        "requires": {"binaries": ["elixir"]},
        "verify": ["mix", "--version"],
    },
}
