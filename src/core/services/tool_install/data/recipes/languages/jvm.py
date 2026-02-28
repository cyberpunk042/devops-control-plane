"""
L0 Data — JVM ecosystem tools.

Categories: java, scala, kotlin
Pure data, no logic.
"""

from __future__ import annotations


_JVM_RECIPES: dict[str, dict] = {

    "openjdk": {
        "label": "OpenJDK",
        "category": "java",
        "cli": "java",
        "install": {
            "apt": ["apt-get", "install", "-y", "default-jdk"],
            "dnf": ["dnf", "install", "-y", "java-latest-openjdk-devel"],
            "apk": ["apk", "add", "openjdk17"],
            "pacman": ["pacman", "-S", "--noconfirm", "jdk-openjdk"],
            "zypper": ["zypper", "install", "-y", "java-17-openjdk-devel"],
            "brew": ["brew", "install", "openjdk"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "verify": ["java", "--version"],
    },
    "maven": {
        "label": "Apache Maven",
        "category": "java",
        "cli": "mvn",
        "install": {
            "apt": ["apt-get", "install", "-y", "maven"],
            "dnf": ["dnf", "install", "-y", "maven"],
            "apk": ["apk", "add", "maven"],
            "pacman": ["pacman", "-S", "--noconfirm", "maven"],
            "zypper": ["zypper", "install", "-y", "maven"],
            "brew": ["brew", "install", "maven"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "requires": {"binaries": ["java"]},
        "verify": ["mvn", "--version"],
    },
    "gradle": {
        "label": "Gradle",
        "category": "java",
        "install": {
            "apt": ["apt-get", "install", "-y", "gradle"],
            "dnf": ["dnf", "install", "-y", "gradle"],
            "pacman": ["pacman", "-S", "--noconfirm", "gradle"],
            "brew": ["brew", "install", "gradle"],
            "snap": ["snap", "install", "gradle", "--classic"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "pacman": True,
                       "brew": False, "snap": True},
        "requires": {"binaries": ["java"]},
        "verify": ["gradle", "--version"],
        "prefer": ["snap", "brew"],
    },

    "scala": {
        "label": "Scala",
        "category": "scala",
        "install": {
            "apt": ["apt-get", "install", "-y", "scala"],
            "dnf": ["dnf", "install", "-y", "scala"],
            "pacman": ["pacman", "-S", "--noconfirm", "scala"],
            "brew": ["brew", "install", "scala"],
        },
        "needs_sudo": {"apt": True, "dnf": True,
                       "pacman": True, "brew": False},
        "verify": ["scala", "-version"],
    },
    "sbt": {
        "label": "sbt (Scala build tool)",
        "category": "scala",
        "install": {
            "_default": [
                "bash", "-c",
                'echo "deb https://repo.scala-sbt.org/scalasbt/debian all main"'
                " | sudo tee /etc/apt/sources.list.d/sbt.list"
                " && curl -sL https://keyserver.ubuntu.com/pks/lookup?"
                "op=get&search=0x99E82A75642AC823"
                " | sudo apt-key add -"
                " && sudo apt-get update && sudo apt-get install -y sbt",
            ],
            "brew": ["brew", "install", "sbt"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "install_via": {"_default": "curl_pipe_bash"},
        "verify": ["sbt", "--version"],
    },
    "ammonite": {
        "label": "Ammonite (Scala REPL)",
        "category": "scala",
        "cli": "amm",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -sSL -o /usr/local/bin/amm"
                " https://github.com/com-lihaoyi/Ammonite/releases/latest/"
                "download/3.0-M2-2.13/amm && chmod +x /usr/local/bin/amm",
            ],
            "brew": ["brew", "install", "ammonite-repl"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "install_via": {"_default": "github_release"},
        "requires": {"binaries": ["curl"]},
        "verify": ["amm", "--version"],
    },

    "kotlin": {
        "label": "Kotlin",
        "category": "kotlin",
        "cli": "kotlinc",
        "install": {
            "snap": ["snap", "install", "kotlin", "--classic"],
            "brew": ["brew", "install", "kotlin"],
        },
        "needs_sudo": {"snap": True, "brew": False},
        "verify": ["kotlinc", "-version"],
    },
    "ktlint": {
        "label": "ktlint (Kotlin linter)",
        "category": "kotlin",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -sSLO https://github.com/pinterest/ktlint/releases/"
                "latest/download/ktlint && chmod +x ktlint"
                " && sudo mv ktlint /usr/local/bin/",
            ],
            "brew": ["brew", "install", "ktlint"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "install_via": {"_default": "github_release"},
        "requires": {"binaries": ["curl"]},
        "verify": ["ktlint", "--version"],
    },
}
