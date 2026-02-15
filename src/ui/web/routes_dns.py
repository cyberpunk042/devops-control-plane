"""
DNS & CDN routes — detection, lookups, SSL checks, record generation.

Blueprint: dns_bp
Prefix: /api

Endpoints:
    GET  /dns/status          — DNS/CDN provider detection
    GET  /dns/lookup/<domain> — DNS lookup
    GET  /dns/ssl/<domain>    — SSL certificate check
    POST /dns/generate        — generate DNS records
"""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

from src.core.services import dns_cdn_ops, devops_cache

dns_bp = Blueprint("dns", __name__)


def _project_root() -> Path:
    return Path(current_app.config["PROJECT_ROOT"])


@dns_bp.route("/dns/status")
def dns_status():  # type: ignore[no-untyped-def]
    """DNS/CDN provider detection."""
    from src.core.services.devops_cache import get_cached

    root = _project_root()
    force = request.args.get("bust", "") == "1"
    return jsonify(get_cached(
        root, "dns",
        lambda: dns_cdn_ops.dns_cdn_status(root),
        force=force,
    ))


@dns_bp.route("/dns/lookup/<domain>")
def dns_lookup(domain: str):  # type: ignore[no-untyped-def]
    """DNS lookup for a domain."""
    result = dns_cdn_ops.dns_lookup(domain)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@dns_bp.route("/dns/ssl/<domain>")
def dns_ssl(domain: str):  # type: ignore[no-untyped-def]
    """SSL certificate check."""
    result = dns_cdn_ops.ssl_check(domain)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@dns_bp.route("/dns/generate", methods=["POST"])
def dns_generate():  # type: ignore[no-untyped-def]
    """Generate DNS records."""
    data = request.get_json(silent=True) or {}
    domain = data.get("domain", "")
    if not domain:
        return jsonify({"error": "Missing 'domain' field"}), 400

    result = dns_cdn_ops.generate_dns_records(
        domain,
        target_ip=data.get("ip", ""),
        cname_target=data.get("cname", ""),
        mail_provider=data.get("mail", ""),
        include_spf=data.get("spf", True),
        include_dmarc=data.get("dmarc", True),
    )
    if "error" in result:
        return jsonify(result), 400

    devops_cache.record_event(
        _project_root(),
        label="🌐 DNS Records Generated",
        summary=f"DNS records generated for {domain}",
        detail={"domain": domain},
        card="dns",
        action="generated",
        target=domain,
    )
    return jsonify(result)
