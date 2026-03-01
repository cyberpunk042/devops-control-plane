"""
Server PATH refresh — ensures newly-installed tool directories are found.

After installing tools (e.g. rustup → ~/.cargo/bin, pip → ~/.local/bin),
the server process's ``os.environ['PATH']`` may be stale because it was
inherited at startup.  Even if the dir is already on PATH, it may appear
after ``/usr/bin``, so ``shutil.which()`` finds the older system binary
first.

This module prepends known directories to the front (if they exist on
disk), mirroring what ``source ~/.cargo/env`` does in a new shell.

No Flask dependency — pure OS-level utility.
"""

from __future__ import annotations

import os
from pathlib import Path


def refresh_server_path() -> None:
    """Prepend common tool-install directories to the FRONT of PATH.

    Order matters — first entry wins in PATH lookup.  Only directories
    that actually exist on disk are prepended.
    """
    home = Path.home()
    candidates = [
        home / ".cargo" / "bin",
        home / ".local" / "bin",
        home / "go" / "bin",
        home / ".nvm" / "current" / "bin",       # nvm symlink
        Path("/usr/local/go/bin"),
        Path("/snap/bin"),
    ]
    current = os.environ.get("PATH", "")
    dirs = current.split(os.pathsep)

    # Build new PATH: known tool dirs first, then everything else (deduped)
    front: list[str] = []
    for d in candidates:
        s = str(d)
        if d.is_dir() and s not in front:
            front.append(s)

    if not front:
        return

    # Remove duplicates from the rest of PATH
    seen = set(front)
    rest = []
    for d in dirs:
        if d not in seen:
            seen.add(d)
            rest.append(d)

    os.environ["PATH"] = os.pathsep.join(front + rest)
