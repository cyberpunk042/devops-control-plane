"""
L0 Data — Rust ecosystem tool-specific failure handlers.

Tools: cargo, rustup
Pure data, no logic.
"""

from __future__ import annotations


_CARGO_HANDLERS: list[dict] = [
            # ── Raspbian: 64-bit kernel + 32-bit userland ───────
            # uname -m says aarch64 so rustup installs 64-bit binaries,
            # but the userland is armhf — binaries can't execute.
            # Error appears AFTER install when verify runs cargo.
            {
                "pattern": (
                    r"exec format error|"
                    r"cannot execute binary file|"
                    r"command failed.*cargo.*No such file or directory"
                ),
                "failure_id": "rustup_arch_mismatch",
                "category": "environment",
                "label": "Architecture mismatch (32-bit userland on 64-bit kernel)",
                "description": (
                    "Your system has a 64-bit kernel but a 32-bit userland "
                    "(common on Raspberry Pi). rustup detected aarch64 and "
                    "installed 64-bit binaries that cannot run. You need to "
                    "either reinstall with the correct 32-bit target or "
                    "upgrade to a 64-bit OS."
                ),
                "example_stderr": (
                    "bash: /home/pi/.cargo/bin/cargo: "
                    "cannot execute binary file: Exec format error"
                ),
                "options": [
                    {
                        "id": "reinstall-armv7",
                        "label": "Reinstall Rust for 32-bit ARM",
                        "description": (
                            "Uninstall the wrong toolchain and reinstall "
                            "with the armv7 target that matches your "
                            "32-bit userland"
                        ),
                        "icon": "🔧",
                        "recommended": True,
                        "strategy": "env_fix",
                        "fix_commands": [
                            ["bash", "-c",
                             'export PATH="$HOME/.cargo/bin:$PATH" && '
                             "rustup self uninstall -y"],
                            ["bash", "-c",
                             "curl --proto '=https' --tlsv1.2 -sSf "
                             "https://sh.rustup.rs | sh -s -- -y "
                             "--default-toolchain "
                             "stable-armv7-unknown-linux-gnueabihf"],
                        ],
                    },
                    {
                        "id": "upgrade-64bit-os",
                        "label": "Upgrade to 64-bit OS",
                        "description": (
                            "Install a 64-bit Raspberry Pi OS to match "
                            "the 64-bit kernel, then retry the default "
                            "rustup installation"
                        ),
                        "icon": "💡",
                        "recommended": False,
                        "strategy": "manual",
                        "instructions": (
                            "1. Download 64-bit Raspberry Pi OS from "
                            "raspberrypi.com\n"
                            "2. Flash to SD card and boot\n"
                            "3. Retry cargo installation"
                        ),
                    },
                ],
            },
            # ── Low memory: rustup hangs/crashes during unpack ──
            # Raspberry Pi with limited RAM can OOM during toolchain
            # unpacking, especially when extracting rust-docs.
            {
                "pattern": (
                    r"(?i)\bKilled\b|SIGKILL|signal:\s*9|"
                    r"out of memory"
                ),
                "exit_code": 137,
                "failure_id": "rustup_low_memory",
                "category": "resources",
                "label": "Rustup ran out of memory during installation",
                "description": (
                    "rustup was killed due to insufficient memory. This "
                    "is common on Raspberry Pi and other low-RAM devices "
                    "during the toolchain unpacking phase."
                ),
                "example_stderr": (
                    "info: installing component 'rust-docs'\n"
                    "Killed"
                ),
                "example_exit_code": 137,
                "options": [
                    {
                        "id": "minimal-profile",
                        "label": "Install with minimal profile",
                        "description": (
                            "Skip rust-docs and other heavy components "
                            "by using the minimal profile, which only "
                            "includes rustc, cargo, and rust-std"
                        ),
                        "icon": "📦",
                        "recommended": True,
                        "strategy": "env_fix",
                        "fix_commands": [
                            ["bash", "-c",
                             "curl --proto '=https' --tlsv1.2 -sSf "
                             "https://sh.rustup.rs | sh -s -- -y "
                             "--profile minimal"],
                        ],
                    },
                    {
                        "id": "limit-unpack-ram",
                        "label": "Limit unpack memory usage",
                        "description": (
                            "Set RUSTUP_UNPACK_RAM to limit memory used "
                            "during component extraction"
                        ),
                        "icon": "🔧",
                        "recommended": False,
                        "strategy": "retry_with_modifier",
                        "modifier": {
                            "env": {"RUSTUP_UNPACK_RAM": "100000000"},
                        },
                    },
                ],
            },
]


_RUSTUP_HANDLERS: list[dict] = [
        # ── Raspbian: 64-bit kernel + 32-bit userland ───────
        # Same as cargo's rustup_arch_mismatch but triggered during
        # rustup --version verify.
        {
            "pattern": (
                r"exec format error|"
                r"cannot execute binary file|"
                r"command failed.*rustup.*No such file or directory"
            ),
            "failure_id": "rustup_arch_mismatch",
            "category": "environment",
            "label": "Architecture mismatch (32-bit userland on 64-bit kernel)",
            "description": (
                "Your system has a 64-bit kernel but a 32-bit userland "
                "(common on Raspberry Pi). The installer detected aarch64 "
                "and installed 64-bit binaries that cannot run. You need "
                "to either reinstall with the correct 32-bit target or "
                "upgrade to a 64-bit OS."
            ),
            "example_stderr": (
                "bash: /home/pi/.cargo/bin/rustup: "
                "cannot execute binary file: Exec format error"
            ),
            "options": [
                {
                    "id": "reinstall-armv7",
                    "label": "Reinstall Rust for 32-bit ARM",
                    "description": (
                        "Uninstall the wrong toolchain and reinstall "
                        "with the armv7 target that matches your "
                        "32-bit userland"
                    ),
                    "icon": "🔧",
                    "recommended": True,
                    "strategy": "env_fix",
                    "fix_commands": [
                        ["bash", "-c",
                         'export PATH="$HOME/.cargo/bin:$PATH" && '
                         "rustup self uninstall -y"],
                        ["bash", "-c",
                         "curl --proto '=https' --tlsv1.2 -sSf "
                         "https://sh.rustup.rs | sh -s -- -y "
                         "--default-toolchain "
                         "stable-armv7-unknown-linux-gnueabihf"],
                    ],
                },
                {
                    "id": "upgrade-64bit-os",
                    "label": "Upgrade to 64-bit OS",
                    "description": (
                        "Install a 64-bit Raspberry Pi OS to match "
                        "the 64-bit kernel, then retry the default "
                        "rustup installation"
                    ),
                    "icon": "💡",
                    "recommended": False,
                    "strategy": "manual",
                    "instructions": (
                        "1. Download 64-bit Raspberry Pi OS from "
                        "raspberrypi.com\n"
                        "2. Flash to SD card and boot\n"
                        "3. Retry rustup installation"
                    ),
                },
            ],
        },
        # ── Low memory during toolchain unpack ─────────────────
        # Same as cargo — OOM during component extraction.
        {
            "pattern": (
                r"(?i)\bKilled\b|SIGKILL|signal:\s*9|"
                r"out of memory"
            ),
            "exit_code": 137,
            "failure_id": "rustup_low_memory",
            "category": "resources",
            "label": "Rustup ran out of memory during installation",
            "description": (
                "rustup was killed due to insufficient memory. This "
                "is common on Raspberry Pi and other low-RAM devices "
                "during the toolchain unpacking phase."
            ),
            "example_stderr": (
                "info: installing component 'rust-docs'\n"
                "Killed"
            ),
            "example_exit_code": 137,
            "options": [
                {
                    "id": "minimal-profile",
                    "label": "Install with minimal profile",
                    "description": (
                        "Skip rust-docs and other heavy components "
                        "by using the minimal profile, which only "
                        "includes rustc, cargo, and rust-std"
                    ),
                    "icon": "📦",
                    "recommended": True,
                    "strategy": "env_fix",
                    "fix_commands": [
                        ["bash", "-c",
                         "curl --proto '=https' --tlsv1.2 -sSf "
                         "https://sh.rustup.rs | sh -s -- -y "
                         "--profile minimal"],
                    ],
                },
                {
                    "id": "limit-unpack-ram",
                    "label": "Limit unpack memory usage",
                    "description": (
                        "Set RUSTUP_UNPACK_RAM to limit memory used "
                        "during component extraction"
                    ),
                    "icon": "🔧",
                    "recommended": False,
                    "strategy": "retry_with_modifier",
                    "modifier": {
                        "env": {"RUSTUP_UNPACK_RAM": "100000000"},
                    },
                },
            ],
        },
]
