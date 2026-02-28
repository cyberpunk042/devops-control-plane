"""
L0 Data — Lua tools.

Categories: lua
Pure data, no logic.
"""

from __future__ import annotations


_LUA_RECIPES: dict[str, dict] = {

    "lua": {
        "label": "Lua",
        "category": "lua",
        "install": {
            "apt": ["apt-get", "install", "-y", "lua5.4"],
            "dnf": ["dnf", "install", "-y", "lua"],
            "apk": ["apk", "add", "lua5.4"],
            "pacman": ["pacman", "-S", "--noconfirm", "lua"],
            "zypper": ["zypper", "install", "-y", "lua54"],
            "brew": ["brew", "install", "lua"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "verify": ["lua", "-v"],
    },
    "luarocks": {
        "label": "LuaRocks (Lua package manager)",
        "category": "lua",
        "install": {
            "apt": ["apt-get", "install", "-y", "luarocks"],
            "dnf": ["dnf", "install", "-y", "luarocks"],
            "apk": ["apk", "add", "luarocks"],
            "pacman": ["pacman", "-S", "--noconfirm", "luarocks"],
            "brew": ["brew", "install", "luarocks"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "brew": False},
        "requires": {"binaries": ["lua"]},
        "verify": ["luarocks", "--version"],
    },
    "stylua": {
        "label": "StyLua (Lua formatter)",
        "category": "lua",
        "install": {
            "_default": ["cargo", "install", "stylua"],
            "brew": ["brew", "install", "stylua"],
        },
        "needs_sudo": {"_default": False, "brew": False},
        "install_via": {"_default": "cargo"},
        "verify": ["stylua", "--version"],
    },
}
