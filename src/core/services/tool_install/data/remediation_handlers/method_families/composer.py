"""
L0 Data — composer_global method-family remediation handlers.

Pure data, no logic.
"""

from __future__ import annotations


_COMPOSER_HANDLERS: list[dict] = [
            # ── Composer memory exhaustion ───────────────────────
            # `composer global require` loads the full dependency
            # graph into memory. PHP's default memory_limit (128MB)
            # is often insufficient. Common on Raspberry Pi and
            # other low-RAM devices.
            {
                "pattern": (
                    r"Allowed memory size of \d+ bytes exhausted|"
                    r"PHP Fatal error:.*memory size.*exhausted|"
                    r"mmap\(\) failed:.*Cannot allocate memory|"
                    r"proc_open\(\):.*Cannot allocate memory"
                ),
                "failure_id": "composer_global_memory_limit",
                "category": "resources",
                "label": "Composer ran out of memory during install",
                "description": (
                    "The composer global require command ran out of "
                    "memory. PHP's default memory_limit (128MB) is "
                    "often insufficient for dependency resolution. "
                    "This is especially common on Raspberry Pi and "
                    "other low-RAM devices."
                ),
                "example_stderr": (
                    "PHP Fatal error:  Allowed memory size of "
                    "134217728 bytes exhausted (tried to allocate "
                    "4096 bytes) in phar:///usr/local/bin/composer/"
                    "src/Composer/DependencyResolver/Solver.php "
                    "on line 223"
                ),
                "options": [
                    {
                        "id": "retry-unlimited-memory",
                        "label": "Retry with unlimited memory",
                        "description": (
                            "Re-run composer global require with "
                            "COMPOSER_MEMORY_LIMIT=-1 to remove "
                            "the PHP memory cap"
                        ),
                        "icon": "🔧",
                        "recommended": True,
                        "strategy": "retry_with_modifier",
                        "modifier": {
                            "env": {
                                "COMPOSER_MEMORY_LIMIT": "-1",
                            },
                        },
                    },
                    {
                        "id": "install-via-brew-mem",
                        "label": "Install via brew instead",
                        "description": (
                            "Brew formulae are pre-compiled — no "
                            "Composer dependency resolution needed, "
                            "so no memory pressure."
                        ),
                        "icon": "🍺",
                        "recommended": False,
                        "strategy": "switch_method",
                        "method": "brew",
                    },
                ],
            },
            # ── PHP version too old for the package ──────────────
            # Composer dependency resolution fails when system PHP
            # doesn't meet the package's version requirement.
            # Generic pattern — matches any package/phpversion combo.
            {
                "pattern": (
                    r"requires php \^[\d.]+ .* your PHP version|"
                    r"requires php .* does not satisfy|"
                    r"your PHP version \([\d.]+\) does not satisfy"
                ),
                "failure_id": "composer_global_php_version",
                "category": "environment",
                "label": "PHP version too old for the package",
                "description": (
                    "The package being installed requires a newer "
                    "PHP version than what your system has. Upgrade "
                    "PHP or use brew (brew bundles its own PHP)."
                ),
                "example_stderr": (
                    "phpstan/phpstan 2.1.0 requires php ^7.4 || ^8.0"
                    " -> your PHP version (7.2.33) does not satisfy "
                    "that requirement."
                ),
                "options": [
                    {
                        "id": "upgrade-php",
                        "label": "Upgrade PHP",
                        "description": (
                            "Install a newer PHP version (8.x) "
                            "using your system package manager"
                        ),
                        "icon": "⬆️",
                        "recommended": True,
                        "strategy": "install_dep",
                        "dep": "php",
                    },
                    {
                        "id": "install-via-brew-ver",
                        "label": "Install via brew instead",
                        "description": (
                            "Brew formulae bundle a compatible PHP "
                            "version — no system PHP dependency."
                        ),
                        "icon": "🍺",
                        "recommended": False,
                        "strategy": "switch_method",
                        "method": "brew",
                    },
                ],
            },
]
