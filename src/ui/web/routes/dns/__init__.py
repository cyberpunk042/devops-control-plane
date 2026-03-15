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


from flask import Blueprint, jsonify, request

from src.core.services.dns import cdn_ops as dns_cdn_ops
from src.core.services.events.tracked import tracked

dns_bp = Blueprint("dns", __name__)


@dns_bp.route("/dns/status")
def dns_status():  # type: ignore[no-untyped-def]
    """DNS/CDN provider detection."""
    force = request.args.get("bust", "") == "1"

    from src.core.services.mediator import get_mediator
    m = get_mediator()
    result = m.get("devops.dns", force=force)
    return jsonify(result["data"])


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
@tracked("dns.records.generated")
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
    return jsonify(result)
