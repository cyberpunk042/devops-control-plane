"""
Integration tests for DNS & CDN domain.

Covers milestone 0.7.5 (Round-Trip & Error Cases).

Uses real file I/O, no network or CLI calls.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.core.services.dns_cdn_ops import dns_cdn_status, generate_dns_records

pytestmark = pytest.mark.integration


# ═══════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════


def _write(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


# ═══════════════════════════════════════════════════════════════════
#  0.7.5 — Round-Trip & Error Cases
# ═══════════════════════════════════════════════════════════════════


class TestDnsCdnRoundTrip:
    """Round-trip and integration scenarios."""

    def test_empty_project(self, tmp_path: Path):
        result = dns_cdn_status(tmp_path)
        assert result["has_cdn"] is False
        assert result["has_dns"] is False
        assert result["cdn_providers"] == []
        assert result["domains"] == []

    def test_cdn_domain_round_trip(self, tmp_path: Path):
        """Create config files → detect → verify CDN + domains."""
        _write(tmp_path / "CNAME", "mysite.example.com")
        _write(tmp_path / "netlify.toml",
               '[build]\ncommand = "npm run build"\n'
               '[[redirects]]\nfrom = "https://myapp.netlify.app/*"')

        result = dns_cdn_status(tmp_path)
        assert result["has_cdn"] is True
        assert result["has_dns"] is True

        providers = {p["id"] for p in result["cdn_providers"]}
        assert "netlify" in providers
        assert "github_pages" in providers  # CNAME triggers GH Pages

        assert "mysite.example.com" in result["domains"]

    def test_generate_records_zone_file_format(self):
        """Generated zone file should look like valid BIND format."""
        result = generate_dns_records(
            "example.com",
            target_ip="1.2.3.4",
            mail_provider="google",
        )
        zone = result["zone_file"]

        # BIND zone file markers
        assert zone.startswith(";")
        assert "$ORIGIN example.com." in zone
        assert "$TTL 300" in zone
        assert "IN" in zone

        # Records present
        assert "1.2.3.4" in zone
        assert "aspmx.l.google.com" in zone
        assert "v=spf1" in zone
        assert "v=DMARC1" in zone

    def test_multiple_cdn_providers(self, tmp_path: Path):
        """Multiple CDN configs in one project."""
        _write(tmp_path / "wrangler.toml", 'name = "worker"')
        _write(tmp_path / "netlify.toml", '[build]')
        _write(tmp_path / "vercel.json", '{}')
        _write(tmp_path / "fastly.toml", '[local_server]')

        result = dns_cdn_status(tmp_path)
        providers = {p["id"] for p in result["cdn_providers"]}
        assert "cloudflare" in providers
        assert "netlify" in providers
        assert "vercel" in providers
        assert "fastly" in providers
        assert len(result["cdn_providers"]) >= 4

    def test_combined_detection(self, tmp_path: Path):
        """CNAME + netlify.toml + SSL certs → all three types found."""
        _write(tmp_path / "CNAME", "mysite.example.com")
        _write(tmp_path / "netlify.toml", '[build]\ncommand = "build"')
        _write(tmp_path / "certs" / "server.pem",
               "-----BEGIN CERTIFICATE-----")
        _write(tmp_path / "certs" / "server.key",
               "-----BEGIN RSA PRIVATE KEY-----")

        result = dns_cdn_status(tmp_path)

        # CDN detected
        assert result["has_cdn"] is True
        providers = {p["id"] for p in result["cdn_providers"]}
        assert "netlify" in providers
        assert "github_pages" in providers

        # Domain detected
        assert "mysite.example.com" in result["domains"]

        # DNS files detected (CNAME counts)
        assert "CNAME" in result["dns_files"]

        # SSL certs detected
        assert len(result["ssl_certs"]) == 2
        types = {c["type"] for c in result["ssl_certs"]}
        assert "certificate" in types
        assert "private_key" in types
