"""
L0 Data — Browser tool recipes (Google Chrome, Chromium).

Categories: browser
Pure data, no logic.
"""

from __future__ import annotations


_BROWSER_RECIPES: dict[str, dict] = {

    "google-chrome": {
        "cli": "google-chrome-stable",
        "label": "Google Chrome (browser for CDP automation)",
        "category": "browser",
        # Proprietary. Only available from Google's own .deb/.rpm.
        # NOT in standard distro repos.
        # apt path: download .deb, install with apt (handles deps).
        # dnf path: direct RPM install from Google URL.
        # _default: same as apt (wget .deb + dpkg + fix deps).
        "install": {
            "apt": [
                "bash", "-c",
                "wget -q -O /tmp/google-chrome-stable.deb "
                "https://dl.google.com/linux/direct/"
                "google-chrome-stable_current_amd64.deb "
                "&& apt-get install -y /tmp/google-chrome-stable.deb "
                "&& rm -f /tmp/google-chrome-stable.deb",
            ],
            "dnf": [
                "bash", "-c",
                "dnf install -y "
                "https://dl.google.com/linux/direct/"
                "google-chrome-stable_current_x86_64.rpm",
            ],
            "_default": [
                "bash", "-c",
                "wget -q -O /tmp/google-chrome-stable.deb "
                "https://dl.google.com/linux/direct/"
                "google-chrome-stable_current_amd64.deb "
                "&& dpkg -i /tmp/google-chrome-stable.deb "
                "&& apt-get -f install -y "
                "&& rm -f /tmp/google-chrome-stable.deb",
            ],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "_default": True,
        },
        "install_via": {"_default": "deb_download"},
        "requires": {"binaries": ["wget"]},
        "prefer": ["apt", "dnf"],
        "verify": ["google-chrome-stable", "--version"],
        "update": {
            "apt": [
                "bash", "-c",
                "wget -q -O /tmp/google-chrome-stable.deb "
                "https://dl.google.com/linux/direct/"
                "google-chrome-stable_current_amd64.deb "
                "&& apt-get install -y /tmp/google-chrome-stable.deb "
                "&& rm -f /tmp/google-chrome-stable.deb",
            ],
            "dnf": [
                "bash", "-c",
                "dnf install -y "
                "https://dl.google.com/linux/direct/"
                "google-chrome-stable_current_x86_64.rpm",
            ],
        },
    },

    "chromium": {
        "cli": "chromium-browser",
        "label": "Chromium (open-source browser for CDP automation)",
        "category": "browser",
        # Open-source. Available in most distro repos.
        # Binary name varies: chromium-browser (Debian/Ubuntu),
        # chromium (Fedora/Arch/Alpine).
        # snap is the default on Ubuntu 20.04+ for chromium-browser.
        "install": {
            "apt":    ["apt-get", "install", "-y", "chromium-browser"],
            "dnf":    ["dnf", "install", "-y", "chromium"],
            "apk":    ["apk", "add", "chromium"],
            "pacman": ["pacman", "-S", "--noconfirm", "chromium"],
            "zypper": ["zypper", "install", "-y", "chromium"],
            "brew":   ["brew", "install", "--cask", "chromium"],
            "snap":   ["snap", "install", "chromium"],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "apk": True,
            "pacman": True, "zypper": True, "brew": False,
            "snap": True,
        },
        "prefer": ["apt", "dnf", "apk", "pacman", "zypper", "brew", "snap"],
        "verify": ["chromium-browser", "--version"],
        "update": {
            "apt": ["apt-get", "install", "-y", "--only-upgrade",
                    "chromium-browser"],
            "dnf":    ["dnf", "upgrade", "-y", "chromium"],
            "apk":    ["apk", "upgrade", "chromium"],
            "pacman": ["pacman", "-Syu", "--noconfirm", "chromium"],
            "zypper": ["zypper", "update", "-y", "chromium"],
            "brew":   ["brew", "upgrade", "--cask", "chromium"],
            "snap":   ["snap", "refresh", "chromium"],
        },
    },
}
