"""
L0 Data — Build tools & embedded.

Categories: cpp, embedded
Pure data, no logic.
"""

from __future__ import annotations

from src.core.services.tool_install.data.constants import _PIP


_BUILD_TOOLS_RECIPES: dict[str, dict] = {

    "build-essential": {
        "label": "Build Essential (C/C++ toolchain)",
        "category": "cpp",
        "cli": "gcc",
        "install": {
            "apt": ["apt-get", "install", "-y", "build-essential"],
            "dnf": ["dnf", "groupinstall", "-y", "Development Tools"],
            "pacman": ["pacman", "-S", "--noconfirm", "base-devel"],
            "apk": ["apk", "add", "build-base"],
            "brew": ["brew", "install", "gcc"],
            "_default": ["apt-get", "install", "-y", "build-essential"],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "pacman": True,
            "apk": True, "brew": False, "_default": True,
        },
        "verify": ["gcc", "--version"],
        "update": {
            "apt": ["apt-get", "install", "-y", "--only-upgrade", "build-essential"],
            "dnf": ["dnf", "groupupdate", "-y", "Development Tools"],
            "pacman": ["pacman", "-Syu", "--noconfirm", "base-devel"],
        },
    },

    "gcc": {
        "label": "GCC",
        "category": "cpp",
        "install": {
            "apt": ["apt-get", "install", "-y", "gcc"],
            "dnf": ["dnf", "install", "-y", "gcc"],
            "apk": ["apk", "add", "gcc", "musl-dev"],
            "pacman": ["pacman", "-S", "--noconfirm", "gcc"],
            "zypper": ["zypper", "install", "-y", "gcc"],
            "brew": ["brew", "install", "gcc"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "verify": ["gcc", "--version"],
    },
    "clang": {
        "label": "Clang/LLVM",
        "category": "cpp",
        "install": {
            "apt": ["apt-get", "install", "-y", "clang"],
            "dnf": ["dnf", "install", "-y", "clang"],
            "apk": ["apk", "add", "clang"],
            "pacman": ["pacman", "-S", "--noconfirm", "clang"],
            "zypper": ["zypper", "install", "-y", "clang"],
            "brew": ["brew", "install", "llvm"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "verify": ["clang", "--version"],
    },
    "cmake": {
        "label": "CMake",
        "category": "cpp",
        "install": {
            "apt": ["apt-get", "install", "-y", "cmake"],
            "dnf": ["dnf", "install", "-y", "cmake"],
            "apk": ["apk", "add", "cmake"],
            "pacman": ["pacman", "-S", "--noconfirm", "cmake"],
            "zypper": ["zypper", "install", "-y", "cmake"],
            "brew": ["brew", "install", "cmake"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "verify": ["cmake", "--version"],
    },
    "ninja": {
        "label": "Ninja (build system)",
        "category": "cpp",
        "install": {
            "apt": ["apt-get", "install", "-y", "ninja-build"],
            "dnf": ["dnf", "install", "-y", "ninja-build"],
            "apk": ["apk", "add", "samurai"],
            "pacman": ["pacman", "-S", "--noconfirm", "ninja"],
            "zypper": ["zypper", "install", "-y", "ninja"],
            "brew": ["brew", "install", "ninja"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "cli": "ninja",
        "verify": ["ninja", "--version"],
    },
    "valgrind": {
        "label": "Valgrind (memory debugger)",
        "category": "cpp",
        "install": {
            "apt": ["apt-get", "install", "-y", "valgrind"],
            "dnf": ["dnf", "install", "-y", "valgrind"],
            "apk": ["apk", "add", "valgrind"],
            "pacman": ["pacman", "-S", "--noconfirm", "valgrind"],
            "zypper": ["zypper", "install", "-y", "valgrind"],
            "brew": ["brew", "install", "valgrind"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "verify": ["valgrind", "--version"],
    },
    "gdb": {
        "label": "GDB (debugger)",
        "category": "cpp",
        "install": {
            "apt": ["apt-get", "install", "-y", "gdb"],
            "dnf": ["dnf", "install", "-y", "gdb"],
            "apk": ["apk", "add", "gdb"],
            "pacman": ["pacman", "-S", "--noconfirm", "gdb"],
            "zypper": ["zypper", "install", "-y", "gdb"],
            "brew": ["brew", "install", "gdb"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "verify": ["gdb", "--version"],
    },

    "arm-gcc": {
        "label": "ARM GCC toolchain",
        "category": "embedded",
        "cli": "arm-none-eabi-gcc",
        "install": {
            "apt": ["apt-get", "install", "-y",
                    "gcc-arm-none-eabi"],
            "dnf": ["dnf", "install", "-y",
                    "arm-none-eabi-gcc-cs"],
            "pacman": ["pacman", "-S", "--noconfirm",
                       "arm-none-eabi-gcc"],
            "brew": ["brew", "install", "arm-none-eabi-gcc"],
        },
        "needs_sudo": {"apt": True, "dnf": True,
                       "pacman": True, "brew": False},
        "verify": ["arm-none-eabi-gcc", "--version"],
    },
    "openocd": {
        "label": "OpenOCD (on-chip debugger)",
        "category": "embedded",
        "install": {
            "apt": ["apt-get", "install", "-y", "openocd"],
            "dnf": ["dnf", "install", "-y", "openocd"],
            "pacman": ["pacman", "-S", "--noconfirm", "openocd"],
            "brew": ["brew", "install", "openocd"],
        },
        "needs_sudo": {"apt": True, "dnf": True,
                       "pacman": True, "brew": False},
        "verify": ["openocd", "--version"],
    },
    "platformio": {
        "label": "PlatformIO (embedded IoT)",
        "category": "embedded",
        "cli": "pio",
        "install": {
            "_default": _PIP + ["install", "platformio"],
        },
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "pip"},
        "verify": ["pio", "--version"],
        "update": {"_default": _PIP + ["install", "--upgrade",
                                       "platformio"]},
    },
    "esptool": {
        "label": "esptool (ESP8266/ESP32 flasher)",
        "category": "embedded",
        "install": {
            "_default": _PIP + ["install", "esptool"],
        },
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "pip"},
        "verify": ["esptool.py", "version"],
        "cli": "esptool.py",
    },
}
