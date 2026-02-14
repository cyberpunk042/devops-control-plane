"""
Audit API routes — serve analysis data for the Audit tab.

All endpoints use server-side caching via devops_cache.
L0/L1 endpoints auto-load. L2/L3 endpoints are on-demand.
"""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

from src.core.services import devops_cache
from src.core.services.audit import (
    audit_scores,
    audit_scores_enriched,
    l0_system_profile,
    l1_clients,
    l1_dependencies,
    l1_structure,
    l2_quality,
    l2_repo,
    l2_risks,
    l2_structure,
)

audit_bp = Blueprint("audit", __name__, url_prefix="/api")


def _project_root() -> Path:
    return Path(current_app.config["PROJECT_ROOT"])


# ── L0: System Profile ─────────────────────────────────────────

@audit_bp.route("/audit/system")
def audit_system():
    root = _project_root()
    bust = "bust" in request.args
    result = devops_cache.get_cached(
        root, "audit:system",
        lambda: l0_system_profile(root),
        force=bust,
    )
    return jsonify(result)


# ── L1: Dependencies & Libraries ───────────────────────────────

@audit_bp.route("/audit/dependencies")
def audit_dependencies():
    root = _project_root()
    bust = "bust" in request.args
    result = devops_cache.get_cached(
        root, "audit:deps",
        lambda: l1_dependencies(root),
        force=bust,
    )
    return jsonify(result)


# ── L1: Structure & Modules ────────────────────────────────────

@audit_bp.route("/audit/structure")
def audit_structure():
    root = _project_root()
    bust = "bust" in request.args
    result = devops_cache.get_cached(
        root, "audit:structure",
        lambda: l1_structure(root),
        force=bust,
    )
    return jsonify(result)


# ── L1: Clients & Services ─────────────────────────────────────

@audit_bp.route("/audit/clients")
def audit_clients():
    root = _project_root()
    bust = "bust" in request.args
    result = devops_cache.get_cached(
        root, "audit:clients",
        lambda: l1_clients(root),
        force=bust,
    )
    return jsonify(result)


# ── Scores ──────────────────────────────────────────────────────

@audit_bp.route("/audit/scores")
def audit_scores_endpoint():
    root = _project_root()
    bust = "bust" in request.args
    result = devops_cache.get_cached(
        root, "audit:scores",
        lambda: audit_scores(root),
        force=bust,
    )
    return jsonify(result)


@audit_bp.route("/audit/scores/enriched")
def audit_scores_enriched_endpoint():
    """L2-enriched master scores — uses full L2 analysis.

    On-demand — takes 5-25s total. Results are cached.
    """
    root = _project_root()
    bust = "bust" in request.args
    result = devops_cache.get_cached(
        root, "audit:scores:enriched",
        lambda: audit_scores_enriched(root),
        force=bust,
    )
    return jsonify(result)


@audit_bp.route("/audit/scores/history")
def audit_scores_history():
    """Score history — last N snapshots for trend rendering."""
    from src.core.services.audit.scoring import _load_history
    root = _project_root()
    history = _load_history(root)
    return jsonify({"history": history, "total": len(history)})


# ── L2: Structure Analysis (on-demand) ─────────────────────────

@audit_bp.route("/audit/structure-analysis")
def audit_structure_analysis():
    """L2: Import graph, module boundaries, cross-module deps.

    On-demand — typically takes 1-5s. Results are cached.
    """
    root = _project_root()
    bust = "bust" in request.args
    result = devops_cache.get_cached(
        root, "audit:l2:structure",
        lambda: l2_structure(root),
        force=bust,
    )
    return jsonify(result)


# ── L2: Code Health (on-demand) ────────────────────────────────

@audit_bp.route("/audit/code-health")
def audit_code_health():
    """L2: Code quality metrics — health scores, hotspots, naming.

    On-demand — typically takes 1-5s. Results are cached.
    """
    root = _project_root()
    bust = "bust" in request.args
    result = devops_cache.get_cached(
        root, "audit:l2:quality",
        lambda: l2_quality(root),
        force=bust,
    )
    return jsonify(result)


# ── L2: Repo Health (on-demand) ────────────────────────────────

@audit_bp.route("/audit/repo")
def audit_repo_health():
    """L2: Repository health — git objects, history, large files.

    On-demand — typically takes 1-3s. Results are cached.
    """
    root = _project_root()
    bust = "bust" in request.args
    result = devops_cache.get_cached(
        root, "audit:l2:repo",
        lambda: l2_repo(root),
        force=bust,
    )
    return jsonify(result)


# ── L2: Risks & Issues (on-demand) ─────────────────────────────

@audit_bp.route("/audit/risks")
def audit_risks():
    """L2: Risk aggregation — security, deps, docs, testing, infra.

    On-demand — typically takes 2-8s (calls multiple ops services).
    Results are cached.
    """
    root = _project_root()
    bust = "bust" in request.args
    result = devops_cache.get_cached(
        root, "audit:l2:risks",
        lambda: l2_risks(root),
        force=bust,
    )
    return jsonify(result)


@audit_bp.route("/audit/install-tool", methods=["POST"])
def audit_install_tool():
    """Install a missing devops tool.

    POST body: {"tool": "helm", "cli": "helm", "sudo_password": "..."}
    For tools requiring sudo, password is piped via sudo -S.
    For pip/npm tools, no password needed.
    """
    import shutil
    import subprocess

    body = request.get_json(silent=True) or {}
    tool = body.get("tool", "").lower().strip()
    cli = body.get("cli", tool).strip()
    sudo_pw = body.get("sudo_password", "")

    if not tool:
        return jsonify({"ok": False, "error": "No tool specified"}), 400

    # Check if already installed
    if shutil.which(cli):
        return jsonify({"ok": True, "message": f"{tool} is already installed", "already_installed": True})

    # Commands that DON'T need sudo
    no_sudo_commands: dict[str, list[str]] = {
        "ruff":       ["pip", "install", "ruff"],
        "mypy":       ["pip", "install", "mypy"],
        "pytest":     ["pip", "install", "pytest"],
        "black":      ["pip", "install", "black"],
        "pip-audit":  ["pip", "install", "pip-audit"],
        "safety":     ["pip", "install", "safety"],
        "bandit":     ["pip", "install", "bandit"],
        "eslint":     ["npm", "install", "-g", "eslint"],
        "prettier":   ["npm", "install", "-g", "prettier"],
    }

    # Commands that NEED sudo
    sudo_commands: dict[str, list[str]] = {
        "helm":           ["bash", "-c", "curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash"],
        "kubectl":        ["snap", "install", "kubectl", "--classic"],
        "terraform":      ["snap", "install", "terraform"],
        "docker":         ["apt-get", "install", "-y", "docker.io"],
        "docker-compose": ["apt-get", "install", "-y", "docker-compose-v2"],
        "trivy":          ["bash", "-c", "curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh -s -- -b /usr/local/bin"],
        "git":            ["apt-get", "install", "-y", "git"],
        "gh":             ["snap", "install", "gh"],
        "ffmpeg":         ["apt-get", "install", "-y", "ffmpeg"],
        "gzip":           ["apt-get", "install", "-y", "gzip"],
        "curl":           ["apt-get", "install", "-y", "curl"],
        "jq":             ["apt-get", "install", "-y", "jq"],
        "make":           ["apt-get", "install", "-y", "make"],
        "python":         ["apt-get", "install", "-y", "python3"],
        "pip":            ["apt-get", "install", "-y", "python3-pip"],
        "node":           ["snap", "install", "node", "--classic"],
        "npm":            ["apt-get", "install", "-y", "npm"],
        "npx":            ["apt-get", "install", "-y", "npm"],
        "go":             ["snap", "install", "go", "--classic"],
        "cargo":          ["bash", "-c", "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y"],
        "rustc":          ["bash", "-c", "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y"],
        "skaffold":       ["bash", "-c", "curl -Lo /usr/local/bin/skaffold https://storage.googleapis.com/skaffold/releases/latest/skaffold-linux-amd64 && chmod +x /usr/local/bin/skaffold"],
    }

    # Determine which command to run
    if tool in no_sudo_commands:
        cmd = no_sudo_commands[tool]
        needs_sudo = False
    elif tool in sudo_commands:
        needs_sudo = True
        if not sudo_pw:
            return jsonify({"ok": False, "needs_sudo": True, "error": "This tool requires sudo. Please enter your password."})
        # Prepend sudo -S to the command
        base_cmd = sudo_commands[tool]
        if base_cmd[0] == "bash":
            # For bash -c commands, wrap the whole thing with sudo
            cmd = ["sudo", "-S"] + base_cmd
        else:
            cmd = ["sudo", "-S"] + base_cmd
    else:
        return jsonify({"ok": False, "error": f"No install recipe for '{tool}'. Install manually."}), 400

    try:
        stdin_data = (sudo_pw + "\n") if needs_sudo else None
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120,
            input=stdin_data,
        )
        if result.returncode == 0:
            installed = shutil.which(cli) is not None
            return jsonify({
                "ok": True,
                "message": f"{tool} installed successfully" if installed else f"Command succeeded but '{cli}' not found in PATH yet — you may need to restart your shell",
                "installed": installed,
                "stdout": result.stdout[-2000:] if result.stdout else "",
            })
        else:
            stderr = result.stderr[-2000:] if result.stderr else ""
            # Check for wrong password
            if "incorrect password" in stderr.lower() or "sorry" in stderr.lower():
                return jsonify({"ok": False, "needs_sudo": True, "error": "Wrong password. Try again."})
            return jsonify({
                "ok": False,
                "error": f"Install failed (exit {result.returncode})",
                "stderr": stderr,
                "stdout": result.stdout[-2000:] if result.stdout else "",
            })
    except subprocess.TimeoutExpired:
        return jsonify({"ok": False, "error": "Install timed out (120s)"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

