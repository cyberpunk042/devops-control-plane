"""
Integration routes — Git, GitHub, and terminal endpoints.

Blueprint: integrations_bp
Prefix: /api

Sub-modules:
    git.py      — git status, log, commit, pull, push
    github.py   — GitHub status, pulls, actions, workflows, user, repo
    gh_auth.py  — GitHub authentication (login, logout, device flow, terminal poll)
    gh_repo.py  — GitHub repo management (create, visibility, default branch, rename)
    remotes.py  — git remote management (list, add, remove, rename, set-url)
    history.py  — git history & maintenance (gc, repack, history reset, filter-repo)
    terminal.py — terminal emulator status
"""

from __future__ import annotations

from flask import Blueprint

integrations_bp = Blueprint("integrations", __name__)

from . import git, github, gh_auth, gh_repo, remotes, history, terminal  # noqa: E402, F401

