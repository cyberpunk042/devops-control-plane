"""
Unit tests for DNS lookup and SSL check (mocked CLI).

Covers milestones 0.7.2 (DNS Lookup) and 0.7.3 (SSL Check).

Every test mocks subprocess.run and shutil.which — no real `dig`
or `openssl` is needed.
"""

from __future__ import annotations

import subprocess
from unittest.mock import patch, MagicMock

import pytest

from src.core.services.dns_cdn_ops import dns_lookup, ssl_check


# ═══════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════


def _mock_result(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(
        args=["dig"], returncode=rc,
        stdout=stdout, stderr=stderr,
    )


def _dig_available():
    """Patch shutil.which to return a path for dig."""
    return "/usr/bin/dig"


def _dig_unavailable():
    return None


# ═══════════════════════════════════════════════════════════════════
#  0.7.2 — DNS Lookup: dns_lookup()
# ═══════════════════════════════════════════════════════════════════


class TestDnsLookup:
    """dns_lookup() tests."""

    def test_return_shape(self):
        with patch("src.core.services.dns_cdn_ops.shutil.which",
                    return_value=_dig_available()), \
             patch("src.core.services.dns_cdn_ops.subprocess.run",
                    return_value=_mock_result()):
            result = dns_lookup("example.com")
            expected_keys = {"ok", "domain", "records", "cname",
                             "a_records", "nameservers", "record_count"}
            assert expected_keys.issubset(result.keys())

    def test_dig_not_available(self):
        with patch("src.core.services.dns_cdn_ops.shutil.which",
                    return_value=None):
            result = dns_lookup("example.com")
            assert result["ok"] is False
            assert "dig" in result["error"]

    def test_a_record(self):
        def mock_run(cmd, **kw):
            record_type = cmd[3] if len(cmd) > 3 else "A"
            if record_type == "A":
                return _mock_result(stdout="93.184.216.34\n")
            return _mock_result()

        with patch("src.core.services.dns_cdn_ops.shutil.which",
                    return_value=_dig_available()), \
             patch("src.core.services.dns_cdn_ops.subprocess.run",
                    side_effect=mock_run):
            result = dns_lookup("example.com")
            assert result["ok"] is True
            assert "93.184.216.34" in result["a_records"]
            a_recs = [r for r in result["records"] if r["type"] == "A"]
            assert len(a_recs) >= 1
            assert a_recs[0]["value"] == "93.184.216.34"

    def test_cname_record(self):
        def mock_run(cmd, **kw):
            record_type = cmd[3] if len(cmd) > 3 else "A"
            if record_type == "CNAME":
                return _mock_result(stdout="cdn.example.com.\n")
            return _mock_result()

        with patch("src.core.services.dns_cdn_ops.shutil.which",
                    return_value=_dig_available()), \
             patch("src.core.services.dns_cdn_ops.subprocess.run",
                    side_effect=mock_run):
            result = dns_lookup("www.example.com")
            assert result["cname"] == "cdn.example.com"
            cname_recs = [r for r in result["records"]
                          if r["type"] == "CNAME"]
            assert len(cname_recs) == 1

    def test_cname_trailing_dot_stripped(self):
        def mock_run(cmd, **kw):
            record_type = cmd[3] if len(cmd) > 3 else "A"
            if record_type == "CNAME":
                return _mock_result(stdout="target.example.com.\n")
            return _mock_result()

        with patch("src.core.services.dns_cdn_ops.shutil.which",
                    return_value=_dig_available()), \
             patch("src.core.services.dns_cdn_ops.subprocess.run",
                    side_effect=mock_run):
            result = dns_lookup("www.example.com")
            assert result["cname"] == "target.example.com"
            assert not result["cname"].endswith(".")

    def test_mx_record(self):
        def mock_run(cmd, **kw):
            record_type = cmd[3] if len(cmd) > 3 else "A"
            if record_type == "MX":
                return _mock_result(stdout="10 mail.example.com.\n")
            return _mock_result()

        with patch("src.core.services.dns_cdn_ops.shutil.which",
                    return_value=_dig_available()), \
             patch("src.core.services.dns_cdn_ops.subprocess.run",
                    side_effect=mock_run):
            result = dns_lookup("example.com")
            mx_recs = [r for r in result["records"] if r["type"] == "MX"]
            assert len(mx_recs) == 1
            assert "mail.example.com" in mx_recs[0]["value"]

    def test_txt_record(self):
        def mock_run(cmd, **kw):
            record_type = cmd[3] if len(cmd) > 3 else "A"
            if record_type == "TXT":
                return _mock_result(
                    stdout='"v=spf1 include:_spf.google.com -all"\n'
                )
            return _mock_result()

        with patch("src.core.services.dns_cdn_ops.shutil.which",
                    return_value=_dig_available()), \
             patch("src.core.services.dns_cdn_ops.subprocess.run",
                    side_effect=mock_run):
            result = dns_lookup("example.com")
            txt_recs = [r for r in result["records"] if r["type"] == "TXT"]
            assert len(txt_recs) == 1
            assert "v=spf1" in txt_recs[0]["value"]
            # Quotes should be stripped
            assert not txt_recs[0]["value"].startswith('"')

    def test_ns_record(self):
        def mock_run(cmd, **kw):
            record_type = cmd[3] if len(cmd) > 3 else "A"
            if record_type == "NS":
                return _mock_result(stdout="ns1.example.com.\nns2.example.com.\n")
            return _mock_result()

        with patch("src.core.services.dns_cdn_ops.shutil.which",
                    return_value=_dig_available()), \
             patch("src.core.services.dns_cdn_ops.subprocess.run",
                    side_effect=mock_run):
            result = dns_lookup("example.com")
            assert "ns1.example.com" in result["nameservers"]
            assert "ns2.example.com" in result["nameservers"]
            # Trailing dots stripped
            assert not any(ns.endswith(".") for ns in result["nameservers"])
            ns_recs = [r for r in result["records"] if r["type"] == "NS"]
            assert len(ns_recs) == 2

    def test_multiple_a_records(self):
        def mock_run(cmd, **kw):
            record_type = cmd[3] if len(cmd) > 3 else "A"
            if record_type == "A":
                return _mock_result(stdout="1.2.3.4\n5.6.7.8\n")
            return _mock_result()

        with patch("src.core.services.dns_cdn_ops.shutil.which",
                    return_value=_dig_available()), \
             patch("src.core.services.dns_cdn_ops.subprocess.run",
                    side_effect=mock_run):
            result = dns_lookup("example.com")
            assert len(result["a_records"]) == 2
            assert "1.2.3.4" in result["a_records"]
            assert "5.6.7.8" in result["a_records"]

    def test_no_records(self):
        with patch("src.core.services.dns_cdn_ops.shutil.which",
                    return_value=_dig_available()), \
             patch("src.core.services.dns_cdn_ops.subprocess.run",
                    return_value=_mock_result(stdout="")):
            result = dns_lookup("nxdomain.example.com")
            assert result["ok"] is True
            assert result["records"] == []
            assert result["record_count"] == 0

    def test_timeout_graceful(self):
        call_count = [0]

        def mock_run(cmd, **kw):
            call_count[0] += 1
            if call_count[0] == 1:  # First call (A record) times out
                raise subprocess.TimeoutExpired("dig", 10)
            return _mock_result()  # Other calls succeed

        with patch("src.core.services.dns_cdn_ops.shutil.which",
                    return_value=_dig_available()), \
             patch("src.core.services.dns_cdn_ops.subprocess.run",
                    side_effect=mock_run):
            # Should not crash, partial results returned
            result = dns_lookup("slow.example.com")
            assert result["ok"] is True


# ═══════════════════════════════════════════════════════════════════
#  0.7.3 — SSL Check: ssl_check()
# ═══════════════════════════════════════════════════════════════════


class TestSslCheck:
    """ssl_check() tests."""

    def test_return_shape(self):
        with patch("src.core.services.dns_cdn_ops.shutil.which",
                    return_value="/usr/bin/openssl"), \
             patch("src.core.services.dns_cdn_ops.subprocess.run",
                    return_value=_mock_result(
                        stdout="notAfter=Dec 31 23:59:59 2026 GMT\n"
                               "issuer=CN = Let's Encrypt\n"
                    )):
            result = ssl_check("example.com")
            expected_keys = {"ok", "domain", "valid", "issuer", "expiry"}
            assert expected_keys.issubset(result.keys())

    def test_openssl_not_available(self):
        with patch("src.core.services.dns_cdn_ops.shutil.which",
                    return_value=None):
            result = ssl_check("example.com")
            assert result["ok"] is False
            assert "openssl" in result["error"]

    def test_valid_cert(self):
        def mock_run(cmd, **kw):
            if "x509" in cmd:
                return _mock_result(
                    stdout="notAfter=Dec 31 23:59:59 2026 GMT\n"
                           "issuer=CN = Let's Encrypt\n"
                )
            return _mock_result(stdout="-----BEGIN CERTIFICATE-----\n")

        with patch("src.core.services.dns_cdn_ops.shutil.which",
                    return_value="/usr/bin/openssl"), \
             patch("src.core.services.dns_cdn_ops.subprocess.run",
                    side_effect=mock_run):
            result = ssl_check("example.com")
            assert result["ok"] is True
            assert result["valid"] is True
            assert "Let's Encrypt" in result["issuer"]
            assert "2026" in result["expiry"]

    def test_timeout(self):
        with patch("src.core.services.dns_cdn_ops.shutil.which",
                    return_value="/usr/bin/openssl"), \
             patch("src.core.services.dns_cdn_ops.subprocess.run",
                    side_effect=subprocess.TimeoutExpired("openssl", 10)):
            result = ssl_check("slow.example.com")
            assert result["ok"] is False
            assert "error" in result
