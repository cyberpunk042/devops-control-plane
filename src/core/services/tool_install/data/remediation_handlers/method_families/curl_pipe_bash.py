"""
L0 Data — curl_pipe_bash method-family remediation handlers.

Pure data, no logic.
"""

from __future__ import annotations


_CURL_PIPE_BASH_HANDLERS: list[dict] = [
            # ── TLS / certificate error ──────────────────────────
            # Minimal Docker images (alpine, distroless, scratch)
            # often lack CA certificates. curl can reach the host
            # but rejects the TLS cert. This is NOT a network
            # failure — DNS and TCP work fine.
            {
                "pattern": (
                    r"curl:\s*\(60\).*SSL certificate problem|"
                    r"curl:\s*\(60\).*certificate.*not trusted|"
                    r"curl:\s*\(77\).*error setting certificate|"
                    r"curl:\s*\(35\).*SSL connect error|"
                    r"ssl_client:.*SSL connection error|"
                    r"unable to get local issuer certificate"
                ),
                "failure_id": "curl_tls_certificate",
                "category": "environment",
                "label": "TLS certificate verification failed",
                "description": (
                    "curl could not verify the server's TLS "
                    "certificate. This usually means the system "
                    "is missing CA certificates — common on "
                    "minimal Docker images (Alpine, slim). "
                    "Install the ca-certificates package."
                ),
                "example_stderr": (
                    "curl: (60) SSL certificate problem: "
                    "unable to get local issuer certificate"
                ),
                "options": [
                    {
                        "id": "install-ca-certs",
                        "label": "Install CA certificates",
                        "description": (
                            "Install the system CA certificate "
                            "bundle so curl can verify TLS"
                        ),
                        "icon": "🔒",
                        "recommended": True,
                        "strategy": "install_packages",
                        "packages": {
                            "debian": ["ca-certificates"],
                            "rhel": ["ca-certificates"],
                            "alpine": ["ca-certificates"],
                            "arch": ["ca-certificates"],
                            "suse": ["ca-certificates"],
                            "macos": ["ca-certificates"],
                        },
                    },
                    {
                        "id": "curl-insecure",
                        "label": "Retry with --insecure (unsafe)",
                        "description": (
                            "Skip TLS verification. NOT recommended"
                            " — only use in isolated/test "
                            "environments where you trust the "
                            "network."
                        ),
                        "icon": "⚠️",
                        "recommended": False,
                        "risk": "high",
                        "strategy": "manual",
                        "instructions": (
                            "Re-run the command with curl -k or "
                            "curl --insecure. This skips TLS "
                            "certificate verification."
                        ),
                    },
                ],
            },
            # ── Unsupported architecture ─────────────────────────
            # Many install scripts detect the system architecture
            # (uname -m / uname -s) and fail if it's not x86_64
            # or aarch64. Common on arm7l (32-bit ARM), s390x,
            # ppc64le, riscv64.
            {
                "pattern": (
                    r"unsupported (?:os|arch|platform|system)|"
                    r"architecture .* (?:not supported|unsupported)|"
                    r"no (?:binary|release|download) (?:available |found )?for|"
                    r"(?:os|platform|arch).*not (?:recognized|supported)|"
                    r"does not support .* architecture|"
                    r"No prebuilt binary"
                ),
                "failure_id": "curl_unsupported_arch",
                "category": "environment",
                "label": "Unsupported OS or architecture",
                "description": (
                    "The install script does not have a binary "
                    "for your OS/architecture combination. This "
                    "is common on ARM 32-bit, s390x, ppc64le, "
                    "and RISC-V. You may need to build from "
                    "source or use a different install method."
                ),
                "example_stderr": (
                    "Error: unsupported arch: armv7l. "
                    "Only x86_64 and aarch64 are supported."
                ),
                "options": [
                    {
                        "id": "switch-to-source",
                        "label": "Build from source",
                        "description": (
                            "Some tools offer source builds for "
                            "unsupported architectures. Check the "
                            "tool's documentation for instructions."
                        ),
                        "icon": "🔨",
                        "recommended": True,
                        "strategy": "manual",
                        "instructions": (
                            "Check the tool's GitHub/documentation "
                            "for source build instructions for "
                            "your architecture."
                        ),
                    },
                    {
                        "id": "switch-to-brew-arch",
                        "label": "Try brew instead",
                        "description": (
                            "Homebrew builds from source on "
                            "unsupported architectures."
                        ),
                        "icon": "🍺",
                        "recommended": False,
                        "strategy": "switch_method",
                        "method": "brew",
                    },
                ],
            },
            # ── Script URL gone (404/410) ────────────────────────
            # Projects move domains, change URLs, or deprecate
            # install scripts. curl returns the HTTP error page
            # content which the shell tries to execute.
            {
                "pattern": (
                    r"curl:\s*\(22\).*(?:404|410|403)|"
                    r"The requested URL returned error: (?:404|410|403)|"
                    r"curl:\s*\(22\).*not found|"
                    r"sh:.*syntax error.*unexpected|"
                    r"bash:.*syntax error near unexpected token|"
                    r"<!DOCTYPE html>|<html"
                ),
                "failure_id": "curl_script_not_found",
                "category": "environment",
                "label": "Install script URL not found or returned HTML",
                "description": (
                    "The install script URL returned a 404/403 "
                    "error or an HTML page instead of a shell "
                    "script. The project may have moved to a new "
                    "URL, or the install script format may have "
                    "changed. Check the project's documentation "
                    "for the current install method."
                ),
                "example_stderr": (
                    "curl: (22) The requested URL returned error: "
                    "404 Not Found"
                ),
                "options": [
                    {
                        "id": "check-docs",
                        "label": "Check project documentation",
                        "description": (
                            "The install script URL may have "
                            "changed. Check the project's website "
                            "or GitHub for the current install "
                            "instructions."
                        ),
                        "icon": "📖",
                        "recommended": True,
                        "strategy": "manual",
                        "instructions": (
                            "Visit the project's official website "
                            "or GitHub page to find the current "
                            "installation instructions."
                        ),
                    },
                    {
                        "id": "switch-to-brew-404",
                        "label": "Install via brew instead",
                        "description": (
                            "Homebrew formulae don't depend on "
                            "third-party install scripts."
                        ),
                        "icon": "🍺",
                        "recommended": False,
                        "strategy": "switch_method",
                        "method": "brew",
                    },
                ],
            },
]
