"""
CLI commands for DNS & CDN integration.

Thin wrappers over ``src.core.services.dns_cdn_ops``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click


def _resolve_project_root(ctx: click.Context) -> Path:
    """Resolve project root from context or CWD."""
    config_path: Path | None = ctx.obj.get("config_path")
    if config_path is None:
        from src.core.config.loader import find_project_file

        config_path = find_project_file()
    return config_path.parent.resolve() if config_path else Path.cwd()


@click.group("dns")
def dns() -> None:
    """DNS & CDN — providers, domains, lookups, SSL, and record generation."""


# ── Detect ──────────────────────────────────────────────────────


@dns.command("status")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def status(ctx: click.Context, as_json: bool) -> None:
    """Show DNS and CDN configuration status."""
    from src.core.services.dns_cdn_ops import dns_cdn_status

    project_root = _resolve_project_root(ctx)
    result = dns_cdn_status(project_root)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    click.secho("🌐 DNS & CDN Status:", fg="cyan", bold=True)
    click.echo()

    # CDN providers
    providers = result.get("cdn_providers", [])
    if providers:
        click.secho("   CDN Providers:", fg="cyan")
        for p in providers:
            cli_icon = "✅" if p.get("cli_available") else "⚠️"
            click.secho(f"      {cli_icon} {p['name']}", fg="green")
            for d in p.get("detected_by", []):
                click.echo(f"         Detected: {d}")
    else:
        click.echo("   📡 No CDN providers detected")

    # Domains
    domains = result.get("domains", [])
    if domains:
        click.echo(f"\n   🔗 Domains ({len(domains)}):")
        for d in domains:
            click.echo(f"      {d}")

    # DNS files
    dns_files = result.get("dns_files", [])
    if dns_files:
        click.echo(f"\n   📄 DNS files ({len(dns_files)}):")
        for f in dns_files:
            click.echo(f"      {f}")

    # SSL certs
    certs = result.get("ssl_certs", [])
    if certs:
        click.echo(f"\n   🔒 SSL certificates ({len(certs)}):")
        for c in certs:
            icon = "🔑" if c["type"] == "private_key" else "📜"
            click.echo(f"      {icon} {c['path']} ({c['type']})")

    if not providers and not domains and not dns_files:
        click.echo("\n   💡 No DNS/CDN configuration detected")

    click.echo()


# ── Observe ─────────────────────────────────────────────────────


@dns.command("lookup")
@click.argument("domain")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
def lookup(domain: str, as_json: bool) -> None:
    """Perform DNS lookup for a domain."""
    from src.core.services.dns_cdn_ops import dns_lookup

    if not as_json:
        click.secho(f"🔍 Looking up {domain}...", fg="cyan")

    result = dns_lookup(domain)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    if "error" in result:
        click.secho(f"❌ {result['error']}", fg="red")
        sys.exit(1)

    records = result.get("records", [])
    if not records:
        click.secho(f"❌ No records found for {domain}", fg="yellow")
        return

    click.secho(f"🌐 {domain} ({result['record_count']} records):", fg="cyan", bold=True)
    click.echo()

    # Grouped by type
    types_seen: set[str] = set()
    for r in records:
        rtype = r["type"]
        if rtype not in types_seen:
            types_seen.add(rtype)
            click.secho(f"   {rtype}:", fg="cyan")
        click.echo(f"      {r['value']}")

    # Nameservers
    ns = result.get("nameservers", [])
    if ns:
        click.echo(f"\n   Nameservers: {', '.join(ns)}")

    click.echo()


@dns.command("ssl")
@click.argument("domain")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
def ssl(domain: str, as_json: bool) -> None:
    """Check SSL certificate for a domain."""
    from src.core.services.dns_cdn_ops import ssl_check

    if not as_json:
        click.secho(f"🔒 Checking SSL for {domain}...", fg="cyan")

    result = ssl_check(domain)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    if "error" in result:
        click.secho(f"❌ {result['error']}", fg="red")
        sys.exit(1)

    if result.get("valid"):
        click.secho(f"✅ SSL valid for {domain}", fg="green", bold=True)
    else:
        click.secho(f"❌ SSL invalid for {domain}", fg="red", bold=True)

    if result.get("issuer"):
        click.echo(f"   Issuer: {result['issuer']}")
    if result.get("expiry"):
        click.echo(f"   Expires: {result['expiry']}")

    click.echo()


# ── Facilitate ──────────────────────────────────────────────────


@dns.command("generate")
@click.argument("domain")
@click.option("--ip", "target_ip", default="", help="Target IP for A records.")
@click.option("--cname", "cname_target", default="", help="CNAME target.")
@click.option("--mail", "mail_provider", default="", help="Mail provider (google/protonmail).")
@click.option("--no-spf", is_flag=True, help="Skip SPF record.")
@click.option("--no-dmarc", is_flag=True, help="Skip DMARC record.")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
def generate(
    domain: str,
    target_ip: str,
    cname_target: str,
    mail_provider: str,
    no_spf: bool,
    no_dmarc: bool,
    as_json: bool,
) -> None:
    """Generate DNS records for a domain."""
    from src.core.services.dns_cdn_ops import generate_dns_records

    result = generate_dns_records(
        domain,
        target_ip=target_ip,
        cname_target=cname_target,
        mail_provider=mail_provider,
        include_spf=not no_spf,
        include_dmarc=not no_dmarc,
    )

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    if "error" in result:
        click.secho(f"❌ {result['error']}", fg="red")
        sys.exit(1)

    click.secho(f"🌐 DNS Records for {domain}:", fg="cyan", bold=True)
    click.echo()

    for r in result.get("records", []):
        rtype = r["type"]
        color = {
            "A": "green", "CNAME": "blue", "MX": "yellow", "TXT": "magenta",
        }.get(rtype, "white")
        click.secho(
            f"   {rtype:<8} {r['name']:<15} → {r['value']}",
            fg=color,
        )

    click.echo()
    click.secho("   📄 Zone file:", fg="cyan")
    click.echo("─" * 60)
    click.echo(result.get("zone_file", ""))
    click.echo("─" * 60)
