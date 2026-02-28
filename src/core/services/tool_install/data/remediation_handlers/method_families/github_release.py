"""
L0 Data — github_release method-family remediation handlers.

Pure data, no logic.
"""

from __future__ import annotations


_GITHUB_RELEASE_HANDLERS: list[dict] = [
            # ── GitHub API rate limit ────────────────────────────
            # Many install commands first query the GitHub API to
            # resolve "latest" → concrete version. Unauthenticated
            # requests are limited to 60/hour. CI/CD pipelines and
            # containers burn through this quickly.
            {
                "pattern": (
                    r"API rate limit exceeded|"
                    r"403.*rate limit|"
                    r"rate limit.*exceeded|"
                    r"429 Too Many Requests|"
                    r"secondary rate limit|"
                    r"You have exceeded.*rate limit"
                ),
                "failure_id": "github_rate_limit",
                "category": "environment",
                "label": "GitHub API rate limit exceeded",
                "description": (
                    "The install command hit GitHub's API rate "
                    "limit. Unauthenticated requests are limited "
                    "to 60/hour per IP. This is common in CI/CD "
                    "pipelines and Docker builds. Solutions: set "
                    "a GITHUB_TOKEN, wait, or use a different "
                    "install method."
                ),
                "example_stderr": (
                    "Error: API rate limit exceeded for "
                    "203.0.113.1. (But here's the good news: "
                    "Authenticated requests get a higher rate "
                    "limit.)"
                ),
                "options": [
                    {
                        "id": "set-gh-token",
                        "label": "Set GITHUB_TOKEN for higher rate limit",
                        "description": (
                            "Authenticated requests get 5,000/hour "
                            "instead of 60/hour. Set a personal "
                            "access token."
                        ),
                        "icon": "🔑",
                        "recommended": True,
                        "strategy": "manual",
                        "instructions": (
                            "1. Create a token at github.com/"
                            "settings/tokens (no scopes needed "
                            "for public repos)\n"
                            "2. Export GITHUB_TOKEN=ghp_xxx\n"
                            "3. Re-run the install command"
                        ),
                    },
                    {
                        "id": "switch-to-brew-rate",
                        "label": "Install via brew instead",
                        "description": (
                            "Homebrew has its own caching and "
                            "doesn't hit GitHub API rate limits."
                        ),
                        "icon": "🍺",
                        "recommended": False,
                        "strategy": "switch_method",
                        "method": "brew",
                    },
                ],
            },
            # ── Release asset not found ──────────────────────────
            # The GitHub release exists, but there's no binary for
            # this OS/arch combination. Different from
            # curl_unsupported_arch — here the install script
            # doesn't detect arch; the download URL itself 404s.
            {
                "pattern": (
                    r"No assets? (?:found|matching|available)|"
                    r"release.*not found|"
                    r"no (?:matching|suitable) release|"
                    r"could not find.*release.*for|"
                    r"unable to determine download URL|"
                    r"asset.*not found.*for.*(?:linux|darwin|amd64|arm)"
                ),
                "failure_id": "github_asset_not_found",
                "category": "environment",
                "label": "No release asset for this platform",
                "description": (
                    "The GitHub release exists but does not "
                    "include a binary for your OS/architecture "
                    "combination. The project may not support "
                    "your platform, or the asset naming may have "
                    "changed between versions."
                ),
                "example_stderr": (
                    "Error: no assets found matching "
                    "linux/armv7l in release v2.1.0"
                ),
                "options": [
                    {
                        "id": "build-from-source-gh",
                        "label": "Build from source",
                        "description": (
                            "Clone the repository and build the "
                            "binary for your architecture."
                        ),
                        "icon": "🔨",
                        "recommended": True,
                        "strategy": "manual",
                        "instructions": (
                            "Check the project's README for build "
                            "instructions. Most Go/Rust projects "
                            "support cross-compilation."
                        ),
                    },
                    {
                        "id": "switch-to-brew-asset",
                        "label": "Try brew instead",
                        "description": (
                            "Homebrew builds from source when no "
                            "bottle exists for your architecture."
                        ),
                        "icon": "🍺",
                        "recommended": False,
                        "strategy": "switch_method",
                        "method": "brew",
                    },
                ],
            },
            # ── Archive extraction failure ───────────────────────
            # The download succeeded but the archive can't be
            # extracted. Common causes: partial download, wrong
            # format (HTML error page saved as .tar.gz), or
            # missing extraction tools.
            {
                "pattern": (
                    r"tar:.*Error.*not in gzip format|"
                    r"tar:.*Exiting with failure|"
                    r"gzip:.*not in gzip format|"
                    r"unzip:.*End-of-central-directory|"
                    r"zip:.*bad zipfile|"
                    r"cannot open:.*No such file or directory|"
                    r"unexpected end of file|"
                    r"short read|"
                    r"data integrity error"
                ),
                "failure_id": "github_extract_failed",
                "category": "environment",
                "label": "Archive extraction failed",
                "description": (
                    "The downloaded archive could not be "
                    "extracted. This usually means the download "
                    "was incomplete (network interruption) or the "
                    "server returned an error page (HTML) instead "
                    "of the actual binary archive."
                ),
                "example_stderr": (
                    "gzip: stdin: not in gzip format\n"
                    "tar: Child returned status 1\n"
                    "tar: Error is not recoverable: "
                    "exiting now"
                ),
                "options": [
                    {
                        "id": "retry-download",
                        "label": "Retry the download",
                        "description": (
                            "The archive may have been partially "
                            "downloaded. Retry the install."
                        ),
                        "icon": "🔄",
                        "recommended": True,
                        "strategy": "retry",
                    },
                    {
                        "id": "switch-to-brew-extract",
                        "label": "Install via brew instead",
                        "description": (
                            "Homebrew handles downloads and "
                            "extraction automatically."
                        ),
                        "icon": "🍺",
                        "recommended": False,
                        "strategy": "switch_method",
                        "method": "brew",
                    },
                ],
            },
]
