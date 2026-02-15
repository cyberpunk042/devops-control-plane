"""
DNS & CDN operations — channel-independent service.

Detection and analysis of DNS and CDN configurations within a project.
Works offline by parsing configuration files; online checks require
appropriate CLI tools (e.g., dig, nslookup, curl).

Covers:
- DNS record file detection (zone files, CNAME, DNS config)
- CDN configuration detection (Cloudflare, CloudFront, Fastly, Netlify)
- Domain extraction from configs
- SSL/TLS certificate detection
- DNS record generation (CNAME, A, TXT for SPF/DKIM/DMARC)
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _audit(label: str, summary: str, **kwargs) -> None:
    """Record an audit event if a project root is registered."""
    try:
        from src.core.context import get_project_root
        root = get_project_root()
    except Exception:
        return
    if root is None:
        return
    from src.core.services.devops_cache import record_event
    record_event(root, label=label, summary=summary, card="dns", **kwargs)


# ═══════════════════════════════════════════════════════════════════
#  Constants
# ═══════════════════════════════════════════════════════════════════

_SKIP_DIRS = frozenset({
    ".git", ".venv", "venv", "node_modules", "__pycache__",
    ".terraform", "dist", "build", ".pages",
    "htmlcov", ".backup", "state",
})

# CDN provider indicators
_CDN_PROVIDERS: dict[str, dict[str, Any]] = {
    "cloudflare": {
        "name": "Cloudflare",
        "config_files": ["wrangler.toml", "wrangler.json", "cloudflare.json"],
        "env_keys": ["CLOUDFLARE_API_TOKEN", "CF_API_TOKEN", "CLOUDFLARE_ZONE_ID"],
        "cli": "wrangler",
        "markers": ["cloudflare", "cf-", "workers.dev"],
    },
    "cloudfront": {
        "name": "AWS CloudFront",
        "config_files": [],
        "tf_resource": "aws_cloudfront_distribution",
        "cli": "aws",
        "markers": ["cloudfront", "d*.cloudfront.net"],
    },
    "fastly": {
        "name": "Fastly",
        "config_files": ["fastly.toml"],
        "env_keys": ["FASTLY_API_TOKEN"],
        "cli": "fastly",
        "markers": ["fastly", "fastly.net"],
    },
    "netlify": {
        "name": "Netlify",
        "config_files": ["netlify.toml", "_redirects", "_headers"],
        "env_keys": ["NETLIFY_AUTH_TOKEN"],
        "cli": "netlify",
        "markers": ["netlify", "netlify.app"],
    },
    "vercel": {
        "name": "Vercel",
        "config_files": ["vercel.json", ".vercel/project.json"],
        "env_keys": ["VERCEL_TOKEN"],
        "cli": "vercel",
        "markers": ["vercel", "vercel.app"],
    },
    "github_pages": {
        "name": "GitHub Pages",
        "config_files": ["CNAME"],
        "markers": ["github.io", "pages"],
    },
}


# ═══════════════════════════════════════════════════════════════════
#  Detect: DNS & CDN status
# ═══════════════════════════════════════════════════════════════════


def dns_cdn_status(project_root: Path) -> dict:
    """Detect DNS and CDN configurations.

    Returns:
        {
            "cdn_providers": [{name, detected_by, cli_available}, ...],
            "domains": [str, ...],
            "dns_files": [str, ...],
            "ssl_certs": [{path, type}, ...],
            "has_cdn": bool,
            "has_dns": bool,
        }
    """
    cdn_providers: list[dict] = []
    domains: set[str] = set()
    dns_files: list[str] = []
    ssl_certs: list[dict] = []

    # Detect CDN providers
    for prov_id, spec in _CDN_PROVIDERS.items():
        detection = _detect_cdn_provider(project_root, prov_id, spec)
        if detection:
            cdn_providers.append(detection)

    # Scan for domain references
    domains.update(_extract_domains_from_configs(project_root))

    # CNAME file (GitHub Pages)
    cname_path = project_root / "CNAME"
    if cname_path.is_file():
        try:
            domain = cname_path.read_text(encoding="utf-8").strip()
            if domain:
                domains.add(domain)
                dns_files.append("CNAME")
        except OSError:
            pass

    # DNS zone files
    for pattern in ("*.zone", "*.dns", "db.*"):
        for f in project_root.rglob(pattern):
            skip = False
            for part in f.relative_to(project_root).parts:
                if part in _SKIP_DIRS:
                    skip = True
                    break
            if not skip:
                dns_files.append(str(f.relative_to(project_root)))

    # SSL certificate files
    for ext in ("*.pem", "*.crt", "*.cert", "*.key"):
        for f in project_root.rglob(ext):
            skip = False
            for part in f.relative_to(project_root).parts:
                if part in _SKIP_DIRS:
                    skip = True
                    break
            if not skip:
                cert_type = "private_key" if f.suffix == ".key" else "certificate"
                ssl_certs.append({
                    "path": str(f.relative_to(project_root)),
                    "type": cert_type,
                })

    return {
        "cdn_providers": cdn_providers,
        "domains": sorted(domains),
        "dns_files": dns_files,
        "ssl_certs": ssl_certs,
        "has_cdn": len(cdn_providers) > 0,
        "has_dns": len(dns_files) > 0 or len(domains) > 0,
    }


def _detect_cdn_provider(
    project_root: Path, prov_id: str, spec: dict[str, Any]
) -> dict | None:
    """Check if a CDN provider is configured."""
    detected_by: list[str] = []

    # Config files
    for cfg in spec.get("config_files", []):
        if (project_root / cfg).is_file():
            detected_by.append(cfg)

    # Environment variables
    for env_file_name in (".env", ".env.production", ".env.staging"):
        env_path = project_root / env_file_name
        if env_path.is_file():
            try:
                content = env_path.read_text(encoding="utf-8", errors="ignore")
                for key in spec.get("env_keys", []):
                    if key in content:
                        detected_by.append(f"{key} in {env_file_name}")
                        break
            except OSError:
                pass

    # Terraform resources
    tf_resource = spec.get("tf_resource")
    if tf_resource:
        for tf_file in project_root.rglob("*.tf"):
            skip = False
            for part in tf_file.relative_to(project_root).parts:
                if part in _SKIP_DIRS:
                    skip = True
                    break
            if skip:
                continue
            try:
                content = tf_file.read_text(encoding="utf-8", errors="ignore")
                if tf_resource in content:
                    detected_by.append(f"{tf_resource} in {tf_file.relative_to(project_root)}")
                    break
            except OSError:
                pass

    if not detected_by:
        return None

    cli_available = False
    cli_name = spec.get("cli")
    if cli_name:
        cli_available = shutil.which(cli_name) is not None

    return {
        "id": prov_id,
        "name": spec["name"],
        "detected_by": detected_by,
        "cli": cli_name,
        "cli_available": cli_available,
    }


def _extract_domains_from_configs(project_root: Path) -> set[str]:
    """Extract domain names from configuration files."""
    domains: set[str] = set()

    domain_pattern = re.compile(
        r'(?:https?://)?([a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?'
        r'(?:\.[a-zA-Z]{2,})+)'
    )

    # Check common config files
    config_files = [
        "netlify.toml", "vercel.json", "wrangler.toml",
        "CNAME", "package.json",
    ]

    for name in config_files:
        path = project_root / name
        if not path.is_file():
            continue

        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
            for m in domain_pattern.finditer(content):
                domain = m.group(1)
                # Filter out common non-domains
                if not any(skip in domain for skip in [
                    "example.com", "localhost", "npmjs.com", "github.com",
                    "googleapis.com", "pypi.org", "python.org",
                    "registry.", "cdn.", "unpkg.com", "jsdelivr.net",
                ]):
                    domains.add(domain)
        except OSError:
            pass

    return domains


# ═══════════════════════════════════════════════════════════════════
#  Observe: DNS lookup
# ═══════════════════════════════════════════════════════════════════


def dns_lookup(domain: str) -> dict:
    """Perform DNS lookup for a domain.

    Returns:
        {
            "ok": bool,
            "domain": str,
            "records": [{type, value}, ...],
            "cname": str | None,
            "a_records": [str, ...],
            "nameservers": [str, ...],
        }
    """
    if not shutil.which("dig"):
        return {"ok": False, "error": "dig command not available"}

    records: list[dict] = []
    cname = None
    a_records: list[str] = []
    nameservers: list[str] = []

    # A records
    try:
        result = subprocess.run(
            ["dig", "+short", domain, "A"],
            capture_output=True, text=True, timeout=10,
        )
        for line in result.stdout.strip().splitlines():
            line = line.strip()
            if line and not line.startswith(";"):
                a_records.append(line)
                records.append({"type": "A", "value": line})
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # CNAME
    try:
        result = subprocess.run(
            ["dig", "+short", domain, "CNAME"],
            capture_output=True, text=True, timeout=10,
        )
        cn = result.stdout.strip()
        if cn and not cn.startswith(";"):
            cname = cn.rstrip(".")
            records.append({"type": "CNAME", "value": cname})
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # MX records
    try:
        result = subprocess.run(
            ["dig", "+short", domain, "MX"],
            capture_output=True, text=True, timeout=10,
        )
        for line in result.stdout.strip().splitlines():
            line = line.strip()
            if line and not line.startswith(";"):
                records.append({"type": "MX", "value": line})
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # TXT records
    try:
        result = subprocess.run(
            ["dig", "+short", domain, "TXT"],
            capture_output=True, text=True, timeout=10,
        )
        for line in result.stdout.strip().splitlines():
            line = line.strip().strip('"')
            if line and not line.startswith(";"):
                records.append({"type": "TXT", "value": line})
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # NS records
    try:
        result = subprocess.run(
            ["dig", "+short", domain, "NS"],
            capture_output=True, text=True, timeout=10,
        )
        for line in result.stdout.strip().splitlines():
            line = line.strip().rstrip(".")
            if line and not line.startswith(";"):
                nameservers.append(line)
                records.append({"type": "NS", "value": line})
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return {
        "ok": True,
        "domain": domain,
        "records": records,
        "cname": cname,
        "a_records": a_records,
        "nameservers": nameservers,
        "record_count": len(records),
    }


def ssl_check(domain: str) -> dict:
    """Check SSL certificate for a domain.

    Returns:
        {
            "ok": bool,
            "domain": str,
            "valid": bool,
            "issuer": str,
            "expiry": str,
            "days_remaining": int | None,
        }
    """
    if not shutil.which("openssl"):
        return {"ok": False, "error": "openssl not available"}

    try:
        # Connect and get certificate info
        result = subprocess.run(
            ["openssl", "s_client", "-connect", f"{domain}:443",
             "-servername", domain, "-showcerts"],
            input="",
            capture_output=True,
            text=True,
            timeout=10,
        )

        # Extract certificate dates
        cert_result = subprocess.run(
            ["openssl", "x509", "-noout", "-dates", "-issuer"],
            input=result.stdout,
            capture_output=True,
            text=True,
            timeout=5,
        )

        issuer = ""
        expiry = ""
        for line in cert_result.stdout.splitlines():
            if line.startswith("notAfter="):
                expiry = line.split("=", 1)[1].strip()
            elif line.startswith("issuer="):
                issuer = line.split("=", 1)[1].strip()

        return {
            "ok": True,
            "domain": domain,
            "valid": cert_result.returncode == 0,
            "issuer": issuer,
            "expiry": expiry,
        }

    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return {"ok": False, "domain": domain, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════
#  Facilitate: DNS record generation
# ═══════════════════════════════════════════════════════════════════


def generate_dns_records(
    domain: str,
    *,
    target_ip: str = "",
    cname_target: str = "",
    mail_provider: str = "",
    include_spf: bool = True,
    include_dmarc: bool = True,
) -> dict:
    """Generate DNS records for a domain.

    Returns:
        {"ok": True, "records": [{type, name, value, ttl}, ...], "zone_file": str}
    """
    records: list[dict] = []

    # A record
    if target_ip:
        records.append({
            "type": "A",
            "name": "@",
            "value": target_ip,
            "ttl": 300,
        })
        records.append({
            "type": "A",
            "name": "www",
            "value": target_ip,
            "ttl": 300,
        })

    # CNAME
    if cname_target:
        records.append({
            "type": "CNAME",
            "name": "www",
            "value": cname_target,
            "ttl": 300,
        })

    # MX records
    if mail_provider == "google":
        mx_records = [
            (1, "aspmx.l.google.com"),
            (5, "alt1.aspmx.l.google.com"),
            (5, "alt2.aspmx.l.google.com"),
            (10, "alt3.aspmx.l.google.com"),
            (10, "alt4.aspmx.l.google.com"),
        ]
        for priority, server in mx_records:
            records.append({
                "type": "MX",
                "name": "@",
                "value": f"{priority} {server}",
                "ttl": 3600,
            })
    elif mail_provider == "protonmail":
        records.append({
            "type": "MX",
            "name": "@",
            "value": "10 mail.protonmail.ch",
            "ttl": 3600,
        })
        records.append({
            "type": "MX",
            "name": "@",
            "value": "20 mailsec.protonmail.ch",
            "ttl": 3600,
        })

    # SPF
    if include_spf:
        spf_value = "v=spf1"
        if mail_provider == "google":
            spf_value += " include:_spf.google.com"
        elif mail_provider == "protonmail":
            spf_value += " include:_spf.protonmail.ch"
        spf_value += " -all"

        records.append({
            "type": "TXT",
            "name": "@",
            "value": spf_value,
            "ttl": 3600,
        })

    # DMARC
    if include_dmarc:
        records.append({
            "type": "TXT",
            "name": "_dmarc",
            "value": f"v=DMARC1; p=quarantine; rua=mailto:dmarc@{domain}; pct=100",
            "ttl": 3600,
        })

    # Generate zone file content
    zone_lines = [
        f"; DNS records for {domain}",
        f"; Generated by DevOps Control Plane",
        f";",
        f"$ORIGIN {domain}.",
        f"$TTL 300",
        "",
    ]

    for r in records:
        name = r["name"]
        if name == "@":
            name = domain + "."
        elif not name.endswith("."):
            name = f"{name}.{domain}."

        zone_lines.append(
            f"{name:<30} {r['ttl']:<8} IN  {r['type']:<8} {r['value']}"
        )

    zone_file = "\n".join(zone_lines) + "\n"

    _audit(
        "🌐 DNS Records Generated",
        f"DNS records generated for {domain}",
        action="generated",
        target=domain,
        detail={"domain": domain, "record_count": len(records)},
    )

    return {
        "ok": True,
        "domain": domain,
        "records": records,
        "record_count": len(records),
        "zone_file": zone_file,
    }
