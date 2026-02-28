"""
L0 Data — Method-family remediation handlers (Layer 2).

Merges all 19 per-method handler lists into the canonical
METHOD_FAMILY_HANDLERS dict. Pure data, no logic.
"""

from __future__ import annotations

from .pip import _PIP_HANDLERS
from .pipx import _PIPX_HANDLERS
from .cargo import _CARGO_HANDLERS
from .go import _GO_HANDLERS
from .npm import _NPM_HANDLERS
from .apt import _APT_HANDLERS
from .dnf import _DNF_HANDLERS
from .yum import _YUM_HANDLERS
from .snap import _SNAP_HANDLERS
from .brew import _BREW_HANDLERS
from .apk import _APK_HANDLERS
from .pacman import _PACMAN_HANDLERS
from .zypper import _ZYPPER_HANDLERS
from .default import _DEFAULT_HANDLERS
from .gem import _GEM_HANDLERS
from .source import _SOURCE_HANDLERS
from .composer import _COMPOSER_HANDLERS
from .curl_pipe_bash import _CURL_PIPE_BASH_HANDLERS
from .github_release import _GITHUB_RELEASE_HANDLERS

METHOD_FAMILY_HANDLERS: dict[str, list[dict]] = {
    "pip": _PIP_HANDLERS,
    "pipx": _PIPX_HANDLERS,
    "cargo": _CARGO_HANDLERS,
    "go": _GO_HANDLERS,
    "npm": _NPM_HANDLERS,
    "apt": _APT_HANDLERS,
    "dnf": _DNF_HANDLERS,
    "yum": _YUM_HANDLERS,
    "snap": _SNAP_HANDLERS,
    "brew": _BREW_HANDLERS,
    "apk": _APK_HANDLERS,
    "pacman": _PACMAN_HANDLERS,
    "zypper": _ZYPPER_HANDLERS,
    "_default": _DEFAULT_HANDLERS,
    "gem": _GEM_HANDLERS,
    "source": _SOURCE_HANDLERS,
    "composer_global": _COMPOSER_HANDLERS,
    "curl_pipe_bash": _CURL_PIPE_BASH_HANDLERS,
    "github_release": _GITHUB_RELEASE_HANDLERS,
}
