"""
L0 Data — Database CLI tools.

Categories: database
Pure data, no logic.
"""

from __future__ import annotations


_DATABASES_RECIPES: dict[str, dict] = {

    "psql": {
        "cli": "psql",
        "label": "PostgreSQL client (psql command-line interface)",
        "category": "database",
        # Written in C. Available in all major distro repos.
        # Package names differ: apt=postgresql-client, dnf/pacman/zypper=postgresql,
        # apk=postgresql-client, brew=libpq (client-only formula).
        # brew libpq installs to keg-only — needs `brew link --force libpq`
        # or PATH addition. Formula provides psql without server.
        # No _default needed — every target platform has it.
        "install": {
            "apt": ["apt-get", "install", "-y", "postgresql-client"],
            "dnf": ["dnf", "install", "-y", "postgresql"],
            "apk": ["apk", "add", "--no-cache", "postgresql-client"],
            "pacman": ["pacman", "-S", "--noconfirm", "postgresql"],
            "zypper": ["zypper", "install", "-y", "postgresql"],
            "brew": ["brew", "install", "libpq"],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "apk": True,
            "pacman": True, "zypper": True, "brew": False,
        },
        "prefer": ["apt", "dnf", "apk", "pacman", "zypper", "brew"],
        "verify": ["psql", "--version"],
        "update": {
            "apt": ["apt-get", "install", "--only-upgrade", "-y", "postgresql-client"],
            "dnf": ["dnf", "upgrade", "-y", "postgresql"],
            "apk": ["apk", "upgrade", "postgresql-client"],
            "pacman": ["pacman", "-Syu", "--noconfirm", "postgresql"],
            "zypper": ["zypper", "update", "-y", "postgresql"],
            "brew": ["brew", "upgrade", "libpq"],
        },
    },
    "mysql-client": {
        "cli": "mysql",
        "label": "MySQL client (mysql command-line interface)",
        "category": "database",
        # Written in C/C++. Client-only — no server installed.
        # Package names differ: apt=mysql-client, dnf=mysql,
        # apk=mysql-client, pacman=mariadb-clients (provides mysql binary),
        # zypper=mysql-client, brew=mysql-client (keg-only).
        # Arch uses MariaDB as default MySQL-compatible client.
        # No _default needed — every target platform has it.
        "install": {
            "apt": ["apt-get", "install", "-y", "mysql-client"],
            "dnf": ["dnf", "install", "-y", "mysql"],
            "apk": ["apk", "add", "--no-cache", "mysql-client"],
            "pacman": ["pacman", "-S", "--noconfirm", "mariadb-clients"],
            "zypper": ["zypper", "install", "-y", "mysql-client"],
            "brew": ["brew", "install", "mysql-client"],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "apk": True,
            "pacman": True, "zypper": True, "brew": False,
        },
        "prefer": ["apt", "dnf", "apk", "pacman", "zypper", "brew"],
        "verify": ["mysql", "--version"],
        "update": {
            "apt": ["apt-get", "install", "--only-upgrade", "-y", "mysql-client"],
            "dnf": ["dnf", "upgrade", "-y", "mysql"],
            "apk": ["apk", "upgrade", "mysql-client"],
            "pacman": ["pacman", "-Syu", "--noconfirm", "mariadb-clients"],
            "zypper": ["zypper", "update", "-y", "mysql-client"],
            "brew": ["brew", "upgrade", "mysql-client"],
        },
    },
    "mongosh": {
        "cli": "mongosh",
        "label": "MongoDB Shell (mongosh interactive client)",
        "category": "database",
        # Written in TypeScript/Node.js. Modern replacement for mongo shell.
        # npm: mongosh (global install). brew: mongosh.
        # NOT in apt, dnf, apk, pacman, zypper (MongoDB provides own repos
        # but setup is complex — repo + key. npm is simpler).
        # _default uses npm because mongosh is a Node.js package.
        "install": {
            "brew": ["brew", "install", "mongosh"],
            "_default": ["npm", "install", "-g", "mongosh"],
        },
        "needs_sudo": {"brew": False, "_default": False},
        "install_via": {"_default": "npm"},
        "requires": {"binaries": ["npm"]},
        "prefer": ["brew"],
        "verify": ["mongosh", "--version"],
        "update": {
            "brew": ["brew", "upgrade", "mongosh"],
            "_default": ["npm", "update", "-g", "mongosh"],
        },
    },
    "redis-cli": {
        "cli": "redis-cli",
        "label": "Redis CLI (redis-cli command-line interface)",
        "category": "database",
        # Written in C. Client-only — installs redis-cli without server.
        # Package names: apt=redis-tools (client-only), dnf/apk/pacman/
        # zypper/brew=redis (full package, includes redis-cli).
        # No _default needed — every target platform has it.
        "install": {
            "apt": ["apt-get", "install", "-y", "redis-tools"],
            "dnf": ["dnf", "install", "-y", "redis"],
            "apk": ["apk", "add", "--no-cache", "redis"],
            "pacman": ["pacman", "-S", "--noconfirm", "redis"],
            "zypper": ["zypper", "install", "-y", "redis"],
            "brew": ["brew", "install", "redis"],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "apk": True,
            "pacman": True, "zypper": True, "brew": False,
        },
        "prefer": ["apt", "dnf", "apk", "pacman", "zypper", "brew"],
        "verify": ["redis-cli", "--version"],
        "update": {
            "apt": ["apt-get", "install", "--only-upgrade", "-y", "redis-tools"],
            "dnf": ["dnf", "upgrade", "-y", "redis"],
            "apk": ["apk", "upgrade", "redis"],
            "pacman": ["pacman", "-Syu", "--noconfirm", "redis"],
            "zypper": ["zypper", "update", "-y", "redis"],
            "brew": ["brew", "upgrade", "redis"],
        },
    },
    "sqlite3": {
        "cli": "sqlite3",
        "label": "SQLite3 (lightweight embedded SQL database)",
        "category": "database",
        # Written in C. Self-contained, serverless, zero-configuration.
        # Package names: apt/zypper=sqlite3, dnf/apk/pacman/brew=sqlite.
        # Available in ALL major distro repos.
        # No _default needed — universal availability.
        "install": {
            "apt": ["apt-get", "install", "-y", "sqlite3"],
            "dnf": ["dnf", "install", "-y", "sqlite"],
            "apk": ["apk", "add", "--no-cache", "sqlite"],
            "pacman": ["pacman", "-S", "--noconfirm", "sqlite"],
            "zypper": ["zypper", "install", "-y", "sqlite3"],
            "brew": ["brew", "install", "sqlite"],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "apk": True,
            "pacman": True, "zypper": True, "brew": False,
        },
        "prefer": ["apt", "dnf", "apk", "pacman", "zypper", "brew"],
        "verify": ["sqlite3", "--version"],
        "update": {
            "apt": ["apt-get", "install", "--only-upgrade", "-y", "sqlite3"],
            "dnf": ["dnf", "upgrade", "-y", "sqlite"],
            "apk": ["apk", "upgrade", "sqlite"],
            "pacman": ["pacman", "-Syu", "--noconfirm", "sqlite"],
            "zypper": ["zypper", "update", "-y", "sqlite3"],
            "brew": ["brew", "upgrade", "sqlite"],
        },
    },
}
