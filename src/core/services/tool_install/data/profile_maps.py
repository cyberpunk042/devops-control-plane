"""
L0 Data — Shell profile/rc file mappings.

Maps shell types to their configuration file paths.
"""

from __future__ import annotations

_PROFILE_MAP: dict[str, dict[str, str]] = {
    "bash": {"rc_file": "~/.bashrc", "login_profile": "~/.bash_profile"},
    "zsh": {"rc_file": "~/.zshrc", "login_profile": "~/.zprofile"},
    "fish": {
        "rc_file": "~/.config/fish/config.fish",
        "login_profile": "~/.config/fish/config.fish",
    },
    "sh": {"rc_file": "~/.profile", "login_profile": "~/.profile"},
    "dash": {"rc_file": "~/.profile", "login_profile": "~/.profile"},
    "ash": {"rc_file": "~/.profile", "login_profile": "~/.profile"},
}
