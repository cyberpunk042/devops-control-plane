"""DNS/CDN — status, lookup, SSL check, record generation."""
from __future__ import annotations
from .cdn_ops import (  # noqa: F401
    dns_cdn_status, dns_lookup, ssl_check, generate_dns_records,
)
