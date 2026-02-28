"""
L0 Data — PHP ecosystem tool-specific failure handlers.

Tools: composer
Pure data, no logic.

Note: phpstan/phpunit have no per-tool handlers.
Both declare install_via: {"_default": "composer_global"}.
The composer_global method family in METHOD_FAMILY_HANDLERS covers
their failure modes (memory exhaustion + PHP version mismatch).
"""

from __future__ import annotations


_COMPOSER_HANDLERS: list[dict] = [
            # ── PHP version too old for Composer ─────────────────
            # Composer 2.x requires PHP 7.2.5+. The official installer
            # checks PHP version and fails with a clear message.
            # This fires during _default install (curl | php).
            # PM-installed composer has PHP as a dep, so the PM handles
            # version requirements.
            {
                "pattern": (
                    r"Composer requires PHP.*but your PHP version|"
                    r"your PHP version .* does not satisfy that requirement|"
                    r"This version of Composer requires PHP|"
                    r"composer\.phar requires php"
                ),
                "failure_id": "composer_php_version_too_old",
                "category": "environment",
                "label": "PHP version too old for Composer",
                "description": (
                    "Composer 2.x requires PHP 7.2.5 or newer. "
                    "Your system's PHP interpreter is too old. "
                    "Upgrade PHP or use the system package manager "
                    "to install a version of Composer compatible "
                    "with your PHP."
                ),
                "example_stderr": (
                    "Composer requires PHP ^7.2.5 || ^8.0 but your "
                    "PHP version (7.0.33) does not satisfy that "
                    "requirement."
                ),
                "options": [
                    {
                        "id": "upgrade-php",
                        "label": "Upgrade PHP",
                        "description": (
                            "Install a newer PHP version (8.x) using "
                            "your system package manager"
                        ),
                        "icon": "⬆️",
                        "recommended": True,
                        "strategy": "install_dep",
                        "dep": "php",
                    },
                    {
                        "id": "use-apt-composer",
                        "label": "Install Composer via apt",
                        "description": (
                            "On Debian/Ubuntu/Raspbian, apt installs "
                            "a Composer version compatible with the "
                            "system PHP. May be an older Composer "
                            "but it will work."
                        ),
                        "icon": "📦",
                        "recommended": False,
                        "strategy": "switch_method",
                        "method": "apt",
                    },
                    {
                        "id": "use-brew-composer",
                        "label": "Install Composer via brew",
                        "description": (
                            "On macOS, brew install composer pulls "
                            "a compatible PHP and all required "
                            "extensions automatically."
                        ),
                        "icon": "🍺",
                        "recommended": False,
                        "strategy": "switch_method",
                        "method": "brew",
                    },
                ],
            },
            # ── Missing PHP extension ────────────────────────────
            # The Composer installer requires several PHP extensions.
            # On minimal PHP installs (Docker, stripped system packages),
            # these may be missing. Most common: openssl, mbstring.
            #
            # Platform-aware:
            #   Debian/Raspbian: php-openssl, php-mbstring
            #   RHEL: php-openssl, php-mbstring
            #   Alpine: php-openssl, php-mbstring (versioned)
            #   macOS: brew php includes all extensions
            {
                "pattern": (
                    r"the requested PHP extension (\S+) is missing|"
                    r"The openssl extension is required|"
                    r"ext-openssl is required|"
                    r"requires ext-mbstring|"
                    r"requires ext-json|"
                    r"You need the openssl extension"
                ),
                "failure_id": "composer_missing_php_extension",
                "category": "dependency",
                "label": "Missing PHP extension for Composer",
                "description": (
                    "Composer requires PHP extensions that are not "
                    "installed or enabled. The most common missing "
                    "extensions are openssl (for HTTPS downloads) "
                    "and mbstring (for string handling). Install "
                    "the missing extension packages."
                ),
                "example_stderr": (
                    "The openssl extension is required for SSL/TLS "
                    "protection but is not available. If you can not "
                    "enable the openssl extension, you can disable "
                    "this error, at the risk of compromising the "
                    "security of file downloads via "
                    "the allow_url_fopen directive."
                ),
                "options": [
                    {
                        "id": "install-php-extensions",
                        "label": "Install common PHP extensions",
                        "description": (
                            "Install openssl, mbstring, and other "
                            "extensions Composer needs. On macOS, "
                            "brew PHP includes all extensions."
                        ),
                        "icon": "📦",
                        "recommended": True,
                        "strategy": "install_packages",
                        "packages": {
                            # apt: package names are php-<ext> on
                            # modern Debian/Ubuntu/Raspbian
                            "debian": [
                                "php-curl", "php-mbstring",
                                "php-xml", "php-zip",
                            ],
                            # dnf: same naming on Fedora/RHEL
                            "rhel": [
                                "php-curl", "php-mbstring",
                                "php-xml", "php-zip",
                            ],
                            # apk: php-* in Alpine repos
                            "alpine": [
                                "php-curl", "php-mbstring",
                                "php-openssl", "php-phar",
                                "php-iconv",
                            ],
                            # pacman: php includes most extensions
                            "arch": ["php"],
                            # zypper: same naming
                            "suse": [
                                "php-curl", "php-mbstring",
                                "php-openssl", "php-zip",
                            ],
                            # brew: php formula includes all stdlib
                            # extensions. If somehow missing, reinstall.
                            "macos": ["php"],
                        },
                    },
                    {
                        "id": "use-apt-composer-ext",
                        "label": "Install Composer via apt (pulls PHP deps)",
                        "description": (
                            "On Debian/Ubuntu/Raspbian, apt install "
                            "composer declares correct PHP extension "
                            "dependencies and installs them "
                            "automatically."
                        ),
                        "icon": "📦",
                        "recommended": False,
                        "strategy": "switch_method",
                        "method": "apt",
                    },
                    {
                        "id": "use-brew-composer-ext",
                        "label": "Install Composer via brew (includes all PHP exts)",
                        "description": (
                            "On macOS, brew install composer pulls "
                            "in brew PHP which includes all standard "
                            "extensions (openssl, mbstring, etc.)."
                        ),
                        "icon": "🍺",
                        "recommended": False,
                        "strategy": "switch_method",
                        "method": "brew",
                    },
                ],
            },
]
