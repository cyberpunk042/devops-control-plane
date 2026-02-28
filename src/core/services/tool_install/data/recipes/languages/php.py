"""
L0 Data — PHP tools.

Categories: php
Pure data, no logic.
"""

from __future__ import annotations


_PHP_RECIPES: dict[str, dict] = {

    "php": {
        "label": "PHP",
        "category": "php",
        "install": {
            "apt": ["apt-get", "install", "-y", "php-cli"],
            "dnf": ["dnf", "install", "-y", "php-cli"],
            "apk": ["apk", "add", "php83"],
            "pacman": ["pacman", "-S", "--noconfirm", "php"],
            "zypper": ["zypper", "install", "-y", "php8"],
            "brew": ["brew", "install", "php"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "verify": ["php", "--version"],
    },
    "composer": {
        "cli": "composer",
        "label": "Composer (PHP dependency manager)",
        "category": "php",
        # Available in all major PMs. zypper uses php-composer (not
        # composer). No snap package. _default uses the official
        # installer from getcomposer.org which requires php + curl.
        #
        # The installer is smarter than manual mv: it verifies the
        # download hash, places the binary directly, and supports
        # --install-dir and --filename flags.
        "install": {
            "apt":    ["apt-get", "install", "-y", "composer"],
            "dnf":    ["dnf", "install", "-y", "composer"],
            "apk":    ["apk", "add", "composer"],
            "pacman": ["pacman", "-S", "--noconfirm", "composer"],
            "zypper": ["zypper", "install", "-y", "php-composer"],
            "brew":   ["brew", "install", "composer"],
            "_default": [
                "bash", "-c",
                "curl -sS https://getcomposer.org/installer"
                " | php -- --install-dir=/usr/local/bin"
                " --filename=composer",
            ],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "apk": True,
            "pacman": True, "zypper": True,
            "brew": False, "_default": True,
        },
        "prefer": ["_default", "brew"],
        "requires": {"binaries": ["php", "curl"]},
        "verify": ["composer", "--version"],
        "update": {
            "apt":    ["apt-get", "install", "--only-upgrade", "-y",
                       "composer"],
            "dnf":    ["dnf", "upgrade", "-y", "composer"],
            "apk":    ["apk", "upgrade", "composer"],
            "pacman": ["pacman", "-S", "--noconfirm", "composer"],
            "zypper": ["zypper", "update", "-y", "php-composer"],
            "brew":   ["brew", "upgrade", "composer"],
            "_default": ["composer", "self-update"],
        },
    },
    "phpstan": {
        "cli": "phpstan",
        "label": "PHPStan (PHP static analysis)",
        "category": "php",
        # Not in apt/dnf/apk/pacman/zypper repos.
        # Available via composer (recommended) and brew.
        # Arch has AUR phpstan-bin but not official repos.
        "install": {
            "_default": [
                "bash", "-c",
                "composer global require phpstan/phpstan",
            ],
            "brew": ["brew", "install", "phpstan"],
        },
        "needs_sudo": {"_default": False, "brew": False},
        "install_via": {"_default": "composer_global"},
        "requires": {"binaries": ["composer"]},
        "post_env": 'export PATH="$HOME/.config/composer/vendor/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/.config/composer/vendor/bin:$PATH"'
                   ' && phpstan --version'],
        "update": {
            "_default": [
                "bash", "-c",
                "composer global update phpstan/phpstan",
            ],
            "brew": ["brew", "upgrade", "phpstan"],
        },
    },
    "phpunit": {
        "cli": "phpunit",
        "label": "PHPUnit (PHP testing)",
        "category": "php",
        # Not in apt/dnf/apk/pacman/zypper repos.
        # Available via composer (recommended) and brew.
        # PHPUnit 11 requires PHP 8.2+, PHPUnit 12 requires PHP 8.3+.
        "install": {
            "_default": [
                "bash", "-c",
                "composer global require phpunit/phpunit",
            ],
            "brew": ["brew", "install", "phpunit"],
        },
        "needs_sudo": {"_default": False, "brew": False},
        "install_via": {"_default": "composer_global"},
        "requires": {"binaries": ["composer"]},
        "post_env": 'export PATH="$HOME/.config/composer/vendor/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/.config/composer/vendor/bin:$PATH"'
                   ' && phpunit --version'],
        "update": {
            "_default": [
                "bash", "-c",
                "composer global update phpunit/phpunit",
            ],
            "brew": ["brew", "upgrade", "phpunit"],
        },
    },
}
