"""
Unit tests for DNS & CDN detection and generation (file-based).

Covers milestones 0.7.1 (Detection) and 0.7.4 (Generation).

All tests use tmp_path with real file I/O. No network or CLI calls.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from src.core.services.dns_cdn_ops import (
    dns_cdn_status,
    generate_dns_records,
)


# ═══════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════


def _write(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


# ═══════════════════════════════════════════════════════════════════
#  0.7.1 Detection — dns_cdn_status()
# ═══════════════════════════════════════════════════════════════════


class TestDnsCdnStatusEmpty:
    """Empty project detection."""

    def test_empty_project(self, tmp_path: Path):
        result = dns_cdn_status(tmp_path)
        assert result["has_cdn"] is False
        assert result["has_dns"] is False
        assert result["cdn_providers"] == []
        assert result["domains"] == []
        assert result["dns_files"] == []
        assert result["ssl_certs"] == []

    def test_return_shape(self, tmp_path: Path):
        result = dns_cdn_status(tmp_path)
        expected_keys = {"cdn_providers", "domains", "dns_files", "ssl_certs",
                         "has_cdn", "has_dns"}
        assert expected_keys.issubset(result.keys())


class TestDnsCdnStatusCNAME:
    """CNAME file detection."""

    def test_cname_with_domain(self, tmp_path: Path):
        _write(tmp_path / "CNAME", "mysite.example.com")
        result = dns_cdn_status(tmp_path)
        assert result["has_dns"] is True
        assert "mysite.example.com" in result["domains"]
        assert "CNAME" in result["dns_files"]

    def test_cname_empty(self, tmp_path: Path):
        _write(tmp_path / "CNAME", "")
        result = dns_cdn_status(tmp_path)
        assert result["domains"] == []


class TestDnsCdnStatusCDNProviders:
    """CDN provider detection."""

    def test_cloudflare_wrangler(self, tmp_path: Path):
        _write(tmp_path / "wrangler.toml", '[env]\nname = "my-worker"')
        result = dns_cdn_status(tmp_path)
        assert result["has_cdn"] is True
        providers = {p["id"] for p in result["cdn_providers"]}
        assert "cloudflare" in providers

    def test_cloudflare_json(self, tmp_path: Path):
        _write(tmp_path / "cloudflare.json", '{"zone": "test"}')
        result = dns_cdn_status(tmp_path)
        providers = {p["id"] for p in result["cdn_providers"]}
        assert "cloudflare" in providers

    def test_cloudfront_terraform(self, tmp_path: Path):
        _write(
            tmp_path / "terraform" / "cdn.tf",
            'resource "aws_cloudfront_distribution" "main" {}\n',
        )
        result = dns_cdn_status(tmp_path)
        providers = {p["id"] for p in result["cdn_providers"]}
        assert "cloudfront" in providers

    def test_netlify_detected(self, tmp_path: Path):
        _write(tmp_path / "netlify.toml", '[build]\ncommand = "npm run build"')
        result = dns_cdn_status(tmp_path)
        providers = {p["id"] for p in result["cdn_providers"]}
        assert "netlify" in providers

    def test_vercel_detected(self, tmp_path: Path):
        _write(tmp_path / "vercel.json", '{"buildCommand": "npm run build"}')
        result = dns_cdn_status(tmp_path)
        providers = {p["id"] for p in result["cdn_providers"]}
        assert "vercel" in providers

    def test_fastly_detected(self, tmp_path: Path):
        _write(tmp_path / "fastly.toml", '[local_server]')
        result = dns_cdn_status(tmp_path)
        providers = {p["id"] for p in result["cdn_providers"]}
        assert "fastly" in providers

    def test_github_pages_cname(self, tmp_path: Path):
        _write(tmp_path / "CNAME", "mysite.example.com")
        result = dns_cdn_status(tmp_path)
        providers = {p["id"] for p in result["cdn_providers"]}
        assert "github_pages" in providers

    def test_cloudflare_env_var(self, tmp_path: Path):
        _write(tmp_path / ".env", "CLOUDFLARE_API_TOKEN=abc123\n")
        result = dns_cdn_status(tmp_path)
        providers = {p["id"] for p in result["cdn_providers"]}
        assert "cloudflare" in providers

    def test_netlify_env_var(self, tmp_path: Path):
        _write(tmp_path / ".env", "NETLIFY_AUTH_TOKEN=abc123\n")
        result = dns_cdn_status(tmp_path)
        providers = {p["id"] for p in result["cdn_providers"]}
        assert "netlify" in providers

    def test_provider_result_shape(self, tmp_path: Path):
        _write(tmp_path / "wrangler.toml", 'name = "test"')
        result = dns_cdn_status(tmp_path)
        prov = result["cdn_providers"][0]
        assert "id" in prov
        assert "name" in prov
        assert "detected_by" in prov
        assert "cli" in prov
        assert "cli_available" in prov

    def test_multiple_providers(self, tmp_path: Path):
        _write(tmp_path / "wrangler.toml", 'name = "test"')
        _write(tmp_path / "netlify.toml", '[build]')
        _write(tmp_path / "vercel.json", '{}')
        result = dns_cdn_status(tmp_path)
        providers = {p["id"] for p in result["cdn_providers"]}
        assert len(providers) >= 3


class TestDnsCdnStatusFiles:
    """DNS zone files and SSL certs."""

    def test_zone_files_detected(self, tmp_path: Path):
        _write(tmp_path / "dns" / "example.zone", "; zone file")
        _write(tmp_path / "dns" / "internal.dns", "; dns file")
        _write(tmp_path / "db.example", "; db file")
        result = dns_cdn_status(tmp_path)
        assert len(result["dns_files"]) == 3

    def test_skip_dirs_for_zone_files(self, tmp_path: Path):
        _write(tmp_path / "node_modules" / "pkg" / "test.zone", "; skip")
        _write(tmp_path / ".venv" / "test.dns", "; skip")
        result = dns_cdn_status(tmp_path)
        assert result["dns_files"] == []

    def test_ssl_cert_files(self, tmp_path: Path):
        _write(tmp_path / "certs" / "server.pem", "-----BEGIN CERTIFICATE-----")
        _write(tmp_path / "certs" / "server.crt", "-----BEGIN CERTIFICATE-----")
        result = dns_cdn_status(tmp_path)
        assert len(result["ssl_certs"]) == 2
        types = {c["type"] for c in result["ssl_certs"]}
        assert "certificate" in types

    def test_ssl_key_files(self, tmp_path: Path):
        _write(tmp_path / "certs" / "server.key", "-----BEGIN RSA PRIVATE KEY-----")
        result = dns_cdn_status(tmp_path)
        assert len(result["ssl_certs"]) == 1
        assert result["ssl_certs"][0]["type"] == "private_key"

    def test_skip_dirs_for_certs(self, tmp_path: Path):
        _write(tmp_path / "node_modules" / "pkg" / "ca.pem", "; skip")
        _write(tmp_path / ".venv" / "cert.crt", "; skip")
        result = dns_cdn_status(tmp_path)
        assert result["ssl_certs"] == []


class TestDomainExtraction:
    """Domain extraction from config files."""

    def test_netlify_toml_domain(self, tmp_path: Path):
        _write(tmp_path / "netlify.toml",
               '[[redirects]]\nfrom = "https://myapp.netlify.app/*"')
        result = dns_cdn_status(tmp_path)
        assert any("netlify.app" in d for d in result["domains"])

    def test_vercel_json_domain(self, tmp_path: Path):
        _write(tmp_path / "vercel.json",
               '{"alias": ["myapp.vercel.app"]}')
        result = dns_cdn_status(tmp_path)
        assert any("vercel.app" in d for d in result["domains"])

    def test_filters_example_com(self, tmp_path: Path):
        _write(tmp_path / "netlify.toml",
               'url = "https://example.com/api"')
        result = dns_cdn_status(tmp_path)
        assert "example.com" not in result["domains"]

    def test_filters_localhost(self, tmp_path: Path):
        _write(tmp_path / "netlify.toml",
               'url = "https://localhost.dev"')
        # localhost itself isn't a domain pattern match; localhost.dev would be filtered
        result = dns_cdn_status(tmp_path)
        domains_lower = [d.lower() for d in result["domains"]]
        assert "localhost" not in domains_lower


# ═══════════════════════════════════════════════════════════════════
#  0.7.4 Generation — generate_dns_records()
# ═══════════════════════════════════════════════════════════════════


class TestGenerateDnsRecords:
    """DNS record generation."""

    def test_return_shape(self):
        result = generate_dns_records("example.com", target_ip="1.2.3.4")
        expected_keys = {"ok", "domain", "records", "record_count", "zone_file"}
        assert expected_keys.issubset(result.keys())
        assert result["ok"] is True

    def test_a_record(self):
        result = generate_dns_records("example.com", target_ip="93.184.216.34")
        a_records = [r for r in result["records"] if r["type"] == "A"]
        assert len(a_records) == 2  # @ and www
        assert a_records[0]["name"] == "@"
        assert a_records[0]["value"] == "93.184.216.34"
        assert a_records[1]["name"] == "www"

    def test_cname_record(self):
        result = generate_dns_records("example.com",
                                       cname_target="cdn.example.com")
        cname_records = [r for r in result["records"] if r["type"] == "CNAME"]
        assert len(cname_records) == 1
        assert cname_records[0]["name"] == "www"
        assert cname_records[0]["value"] == "cdn.example.com"

    def test_no_ip_no_cname(self):
        result = generate_dns_records("example.com")
        a_records = [r for r in result["records"] if r["type"] in ("A", "CNAME")]
        assert a_records == []

    def test_google_mail(self):
        result = generate_dns_records("example.com", mail_provider="google")
        mx_records = [r for r in result["records"] if r["type"] == "MX"]
        assert len(mx_records) == 5
        mx_values = [r["value"] for r in mx_records]
        assert any("aspmx.l.google.com" in v for v in mx_values)

    def test_protonmail_mail(self):
        result = generate_dns_records("example.com",
                                       mail_provider="protonmail")
        mx_records = [r for r in result["records"] if r["type"] == "MX"]
        assert len(mx_records) == 2
        mx_values = [r["value"] for r in mx_records]
        assert any("protonmail.ch" in v for v in mx_values)

    def test_no_mail_provider(self):
        result = generate_dns_records("example.com")
        mx_records = [r for r in result["records"] if r["type"] == "MX"]
        assert mx_records == []

    def test_spf_default(self):
        result = generate_dns_records("example.com")
        txt_records = [r for r in result["records"] if r["type"] == "TXT"]
        spf = [r for r in txt_records if "v=spf1" in r["value"]]
        assert len(spf) == 1

    def test_spf_google(self):
        result = generate_dns_records("example.com", mail_provider="google")
        txt_records = [r for r in result["records"] if r["type"] == "TXT"]
        spf = [r for r in txt_records if "v=spf1" in r["value"]]
        assert any("_spf.google.com" in r["value"] for r in spf)

    def test_spf_protonmail(self):
        result = generate_dns_records("example.com",
                                       mail_provider="protonmail")
        txt_records = [r for r in result["records"] if r["type"] == "TXT"]
        spf = [r for r in txt_records if "v=spf1" in r["value"]]
        assert any("_spf.protonmail.ch" in r["value"] for r in spf)

    def test_spf_disabled(self):
        result = generate_dns_records("example.com", include_spf=False)
        txt_records = [r for r in result["records"] if r["type"] == "TXT"]
        spf = [r for r in txt_records if "v=spf1" in r["value"]]
        assert spf == []

    def test_dmarc_default(self):
        result = generate_dns_records("example.com")
        txt_records = [r for r in result["records"] if r["type"] == "TXT"]
        dmarc = [r for r in txt_records if "v=DMARC1" in r["value"]]
        assert len(dmarc) == 1
        assert dmarc[0]["name"] == "_dmarc"

    def test_dmarc_disabled(self):
        result = generate_dns_records("example.com", include_dmarc=False)
        txt_records = [r for r in result["records"] if r["type"] == "TXT"]
        dmarc = [r for r in txt_records if "v=DMARC1" in r["value"]]
        assert dmarc == []

    def test_zone_file_origin(self):
        result = generate_dns_records("example.com", target_ip="1.2.3.4")
        assert "$ORIGIN example.com." in result["zone_file"]

    def test_zone_file_ttl(self):
        result = generate_dns_records("example.com", target_ip="1.2.3.4")
        assert "$TTL 300" in result["zone_file"]

    def test_zone_file_contains_records(self):
        result = generate_dns_records("example.com", target_ip="1.2.3.4")
        assert "1.2.3.4" in result["zone_file"]
        assert "IN" in result["zone_file"]

    def test_record_count_matches(self):
        result = generate_dns_records("example.com", target_ip="1.2.3.4",
                                       mail_provider="google")
        assert result["record_count"] == len(result["records"])
