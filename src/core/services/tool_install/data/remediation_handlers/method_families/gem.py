"""
L0 Data — gem method-family remediation handlers.

Pure data, no logic.
"""

from __future__ import annotations


_GEM_HANDLERS: list[dict] = [
        # ── Gem::FilePermissionError ────────────────────────────
        # Common when `gem install` tries to write to the system
        # gem directory (/usr/lib/ruby/gems/) without sudo.
        # Happens on systems where Ruby was installed via PM and
        # the default gem path is a root-owned directory.
        {
            "pattern": (
                r"Gem::FilePermissionError|"
                r"You don't have write permissions for the .*/gems/|"
                r"ERROR:.*permission denied.*gems"
            ),
            "failure_id": "gem_permission_error",
            "category": "permissions",
            "label": "No write permission to gem directory",
            "description": (
                "gem install is trying to write to the system gem "
                "directory which requires root permissions. You can "
                "either install to a user-local directory or use "
                "sudo."
            ),
            "example_stderr": (
                "ERROR:  While executing gem ... "
                "(Gem::FilePermissionError)\n"
                "    You don't have write permissions for the "
                "/usr/lib/ruby/gems/3.0.0 directory."
            ),
            "options": [
                {
                    "id": "gem-user-install",
                    "label": "Install to user gem directory",
                    "description": (
                        "Set GEM_HOME to ~/.gem and re-run the "
                        "install. This avoids needing root."
                    ),
                    "icon": "👤",
                    "recommended": True,
                    "strategy": "retry_with_modifier",
                    "modifier": {
                        "env": {
                            "GEM_HOME": "$HOME/.gem",
                        },
                        "prepend_path": "$HOME/.gem/bin",
                    },
                },
                {
                    "id": "gem-sudo-install",
                    "label": "Install with sudo",
                    "description": (
                        "Run gem install with sudo to write to "
                        "the system gem directory"
                    ),
                    "icon": "🔒",
                    "recommended": False,
                    "strategy": "retry_with_modifier",
                    "modifier": {"sudo": True},
                },
            ],
        },
        # ── Native extension build failure ──────────────────────
        # Some gems need C compilation. If ruby-dev / ruby-devel
        # headers are missing, mkmf.rb fails.
        # Note: bundler itself is pure Ruby and won't hit this,
        # but other gems installed via `gem install` will.
        #
        # Platform considerations:
        #   macOS: system Ruby (deprecated since Catalina) has no
        #     headers. Fix = brew ruby (includes everything) OR
        #     Xcode CLT for the SDK headers + clang compiler.
        #   Raspbian (ARM64): same debian packages work, but
        #     native extensions may compile slower on Pi.
        #     build-essential provides ARM-native gcc.
        {
            "pattern": (
                r"mkmf\.rb can't find header files|"
                r"extconf\.rb failed|"
                r"ERROR: Failed to build gem native extension|"
                r"You have to install development tools first"
            ),
            "failure_id": "gem_native_extension_failed",
            "category": "dependency",
            "label": "Gem native extension build failed",
            "description": (
                "This gem includes a C extension that requires "
                "Ruby development headers (ruby.h) and a C compiler "
                "to build. On Linux, install the ruby-dev package. "
                "On macOS, install Xcode Command Line Tools or use "
                "Homebrew Ruby (which includes headers)."
            ),
            "example_stderr": (
                "Building native extensions. This could take a while...\n"
                "ERROR: Error installing nokogiri:\n"
                "    ERROR: Failed to build gem native extension.\n"
                "    mkmf.rb can't find header files for ruby"
            ),
            "options": [
                {
                    "id": "install-ruby-dev",
                    "label": "Install Ruby development headers",
                    "description": (
                        "Install the ruby-dev / ruby-devel package "
                        "for your system. On macOS, this installs "
                        "Homebrew Ruby which includes headers."
                    ),
                    "icon": "📦",
                    "recommended": True,
                    "strategy": "install_packages",
                    "packages": {
                        # debian covers: Ubuntu, Debian, Raspbian
                        "debian": ["ruby-dev"],
                        "rhel": ["ruby-devel"],
                        "alpine": ["ruby-dev"],
                        "arch": ["ruby"],
                        "suse": ["ruby-devel"],
                        # brew install ruby includes headers + compiler
                        # shim; covers the common macOS case where
                        # system Ruby has no headers post-Catalina
                        "macos": ["ruby"],
                    },
                },
                {
                    "id": "install-build-tools",
                    "label": "Install C compiler and build tools",
                    "description": (
                        "Install gcc/make for native extension "
                        "compilation. On Debian/Raspbian this "
                        "installs build-essential (ARM-native "
                        "on Pi). On macOS, prefer Xcode CLT."
                    ),
                    "icon": "🔧",
                    "recommended": False,
                    "strategy": "install_packages",
                    "packages": {
                        # build-essential works on both x86_64 and
                        # arm64 (Raspbian) — installs ARM-native gcc
                        "debian": ["build-essential"],
                        "rhel": ["gcc", "gcc-c++", "make"],
                        "alpine": ["build-base"],
                        "arch": ["base-devel"],
                        "suse": ["gcc", "gcc-c++", "make"],
                        # brew install gcc gives real GCC (not clang);
                        # for most gems, Xcode CLT clang is enough —
                        # see the manual option below
                        "macos": ["gcc"],
                    },
                },
                {
                    # macOS-specific: Xcode Command Line Tools gives
                    # clang (as cc/gcc), make, headers, and the SDK.
                    # This is the standard macOS way to get build tools.
                    "id": "install-xcode-clt",
                    "label": "Install Xcode Command Line Tools (macOS)",
                    "description": (
                        "On macOS, run 'xcode-select --install' to "
                        "get clang, make, and macOS SDK headers. "
                        "This is the standard way to enable native "
                        "extension compilation on macOS."
                    ),
                    "icon": "🍎",
                    "recommended": False,
                    "strategy": "manual",
                    "instructions": (
                        "Run the following command in Terminal:\n"
                        "  xcode-select --install\n\n"
                        "A dialog will appear to download and install "
                        "the Command Line Tools. After installation, "
                        "retry the gem install."
                    ),
                },
            ],
        },
]
