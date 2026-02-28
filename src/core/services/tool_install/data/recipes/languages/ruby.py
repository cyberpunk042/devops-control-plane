"""
L0 Data — Ruby tools.

Categories: ruby
Pure data, no logic.
"""

from __future__ import annotations


_RUBY_RECIPES: dict[str, dict] = {

    "ruby": {
        "cli": "ruby",
        "label": "Ruby",
        "category": "ruby",
        # No _default (binary download) — Ruby from source requires
        # autotools + C compiler + many deps. System packages are
        # the correct path. No snap package exists.
        #
        # apt ruby-full = ruby + ruby-dev + ruby-doc (all-in-one).
        # dnf/apk need separate -devel/-dev for gem native extensions.
        # pacman/brew ruby includes everything.
        "install": {
            "apt":    ["apt-get", "install", "-y", "ruby-full"],
            "dnf":    ["dnf", "install", "-y", "ruby", "ruby-devel"],
            "apk":    ["apk", "add", "ruby", "ruby-dev"],
            "pacman": ["pacman", "-S", "--noconfirm", "ruby"],
            "zypper": ["zypper", "install", "-y", "ruby-devel"],
            "brew":   ["brew", "install", "ruby"],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "apk": True,
            "pacman": True, "zypper": True, "brew": False,
        },
        "verify": ["ruby", "--version"],
        "update": {
            "apt":    ["apt-get", "install", "--only-upgrade", "-y",
                       "ruby-full"],
            "dnf":    ["dnf", "upgrade", "-y", "ruby"],
            "apk":    ["apk", "upgrade", "ruby"],
            "pacman": ["pacman", "-S", "--noconfirm", "ruby"],
            "zypper": ["zypper", "update", "-y", "ruby-devel"],
            "brew":   ["brew", "upgrade", "ruby"],
        },
    },
    "bundler": {
        "cli": "bundle",
        "label": "Bundler (Ruby dependency manager)",
        "category": "ruby",
        # _default via gem is preferred — always latest, Ruby is
        # already a hard dependency. System packages often lag.
        # brew doesn't have a separate formula — bundler ships
        # with brewed Ruby since Ruby 2.6+.
        "install": {
            "apt":    ["apt-get", "install", "-y", "ruby-bundler"],
            "dnf":    ["dnf", "install", "-y", "rubygem-bundler"],
            "apk":    ["apk", "add", "ruby-bundler"],
            "pacman": ["pacman", "-S", "--noconfirm", "ruby-bundler"],
            "zypper": ["zypper", "install", "-y", "ruby-bundler"],
            "_default": ["gem", "install", "bundler"],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "apk": True,
            "pacman": True, "zypper": True, "_default": False,
        },
        "install_via": {"_default": "gem"},
        "prefer": ["_default"],
        "requires": {"binaries": ["ruby"]},
        "verify": ["bundle", "--version"],
        "update": {
            "apt":    ["apt-get", "install", "--only-upgrade", "-y",
                       "ruby-bundler"],
            "dnf":    ["dnf", "upgrade", "-y", "rubygem-bundler"],
            "apk":    ["apk", "upgrade", "ruby-bundler"],
            "pacman": ["pacman", "-S", "--noconfirm", "ruby-bundler"],
            "zypper": ["zypper", "update", "-y", "ruby-bundler"],
            "_default": ["gem", "update", "bundler"],
        },
    },
    "rubocop": {
        "label": "RuboCop (Ruby linter)",
        "category": "ruby",
        "install": {"_default": ["gem", "install", "rubocop"]},
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "gem"},
        "requires": {"binaries": ["ruby"]},
        "verify": ["rubocop", "--version"],
    },
}
