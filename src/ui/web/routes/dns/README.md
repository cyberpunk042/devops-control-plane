# DNS Routes — DNS/CDN Detection, Lookup, SSL & Record Generation API

> **1 file · 78 lines · 4 endpoints · Blueprint: `dns_bp` · Prefix: `/api`**
>
> Thin HTTP wrappers over `src.core.services.dns.cdn_ops` (565 lines).
> These routes provide DNS and CDN infrastructure inspection: provider
> detection (Cloudflare, Netlify, Vercel, GitHub Pages, AWS CloudFront),
> live DNS lookups (A, CNAME, MX, TXT, NS records via `dig`), SSL
> certificate checking (via `openssl`), and DNS record generation with
> mail provider integration (Google Workspace, ProtonMail) including
> SPF and DMARC policies. The status endpoint uses server-side caching
> with cache-bust support; lookup and SSL endpoints make live network
> calls; generation produces both structured records and BIND zone file
> format.

---

## How It Works

### Request Flow

```
Frontend
│
├── devops/_dns.html ─────────────── Dashboard DNS card
│   └── GET  /api/dns/status         (cached detection)
│
├── integrations/_dns.html ───────── Integration panel
│   ├── GET  /api/dns/status         (cached detection)
│   ├── GET  /api/dns/lookup/<dom>   (live DNS lookup)
│   └── GET  /api/dns/ssl/<dom>      (live SSL check)
│
├── integrations/setup/_dns.html ─── DNS setup wizard
│   └── POST /api/dns/generate       (record generation)
│
└── wizard/_integration_actions.html
    └── POST /api/wizard/setup { action: "dns" }
         (via devops routes, not dns routes)
     │
     ▼
routes/dns/__init__.py                ← HTTP layer (this file)
     │
     ▼
core/services/dns/cdn_ops.py (565 lines) ← Business logic
├── dns_cdn_status()         — offline detection (filesystem scan)
├── dns_lookup()             — live DNS resolution (subprocess: dig)
├── ssl_check()              — live SSL inspection (subprocess: openssl)
└── generate_dns_records()   — record composition + zone file output
```

### Provider Detection Pipeline (Offline)

```
GET /api/dns/status
     │
     ▼
devops_cache.get_cached(root, "dns", ...)
     │
     ├── Cache HIT → return immediately
     └── Cache MISS → dns_cdn_ops.dns_cdn_status(root)
         │
         ├── 1. Detect CDN providers:
         │   For each of 5 providers, check:
         │   ├── Cloudflare:    wrangler.toml, wrangler.json, cloudflare.json
         │   ├── AWS CloudFront: cloudformation templates, CDK config
         │   ├── Netlify:       netlify.toml
         │   ├── Vercel:        vercel.json
         │   └── GitHub Pages:  CNAME file
         │        │
         │        └── For each: scan config files + check CLI tool availability
         │
         ├── 2. Extract domains from configs:
         │   _extract_domains_from_configs(root)
         │   ├── Scan YAML/JSON/TOML configs for domain patterns
         │   └── Read CNAME file if present
         │
         ├── 3. Scan for DNS zone files:
         │   *.zone, *.dns, db.*
         │   (respecting _SKIP_DIRS: .git, node_modules, .terraform, etc.)
         │
         ├── 4. Scan for SSL certificate files:
         │   *.pem, *.crt, *.cert, *.key
         │   (classify as "certificate" or "private_key")
         │
         └── 5. Check required tools:
             check_required_tools(["dig", "openssl", "curl"])
             → { dig: {found: true}, openssl: {found: true}, ... }
```

### DNS Lookup Pipeline (Live)

```
GET /api/dns/lookup/example.com
     │
     ▼
dns_cdn_ops.dns_lookup("example.com")
     │
     ├── Check: is `dig` available?
     │   └── NO → { ok: false, error: "dig command not available" }
     │
     └── YES → run 5 sequential dig queries:
         │
         ├── dig +short example.com A
         │   → ["93.184.216.34"]
         │
         ├── dig +short example.com CNAME
         │   → "cdn.example.com" (or null)
         │
         ├── dig +short example.com MX
         │   → ["10 mail.example.com"]
         │
         ├── dig +short example.com TXT
         │   → ["v=spf1 include:..."]
         │
         └── dig +short example.com NS
             → ["ns1.example.com", "ns2.example.com"]
         │
         Each query: timeout=10s, capture_output=True
         Lines starting with ";" are filtered (comments)
```

### SSL Check Pipeline (Live)

```
GET /api/dns/ssl/example.com
     │
     ▼
dns_cdn_ops.ssl_check("example.com")
     │
     ├── Check: is `openssl` available?
     │   └── NO → { ok: false, error: "openssl not available" }
     │
     └── YES → two-stage openssl pipeline:
         │
         ├── Stage 1: Connect and get certificate
         │   openssl s_client -connect example.com:443
         │                    -servername example.com
         │                    -showcerts
         │   timeout=10s
         │
         └── Stage 2: Extract dates and issuer
             openssl x509 -noout -dates -issuer
             (pipe stage 1 stdout as input)
             timeout=5s
             │
             ├── Parse notAfter= → expiry date
             ├── Parse issuer=   → issuer name
             └── returncode == 0 → valid: true
```

### DNS Record Generation Pipeline

```
POST /api/dns/generate
{ domain: "example.com", ip: "1.2.3.4", mail: "google",
  spf: true, dmarc: true }
     │
     ▼
dns_cdn_ops.generate_dns_records(
    "example.com",
    target_ip="1.2.3.4",
    cname_target="",
    mail_provider="google",
    include_spf=True,
    include_dmarc=True,
)
     │
     ├── 1. A records (if target_ip provided):
     │   @ → 1.2.3.4 (TTL 300)
     │   www → 1.2.3.4 (TTL 300)
     │
     ├── 2. CNAME record (if cname_target provided):
     │   www → cdn.example.com (TTL 300)
     │
     ├── 3. MX records (mail provider specific):
     │   ├── "google" → 5 Google Workspace MX records
     │   │   1  aspmx.l.google.com
     │   │   5  alt1.aspmx.l.google.com
     │   │   5  alt2.aspmx.l.google.com
     │   │   10 alt3.aspmx.l.google.com
     │   │   10 alt4.aspmx.l.google.com
     │   │
     │   └── "protonmail" → 2 ProtonMail MX records
     │       10 mail.protonmail.ch
     │       20 mailsec.protonmail.ch
     │
     ├── 4. SPF record (if include_spf):
     │   TXT @ "v=spf1 include:_spf.google.com -all"
     │   (or include:_spf.protonmail.ch for protonmail)
     │
     ├── 5. DMARC record (if include_dmarc):
     │   TXT _dmarc "v=DMARC1; p=quarantine; rua=mailto:dmarc@example.com; pct=100"
     │
     ├── 6. Generate BIND zone file:
     │   ; DNS records for example.com
     │   $ORIGIN example.com.
     │   $TTL 300
     │   example.com.         300      IN  A        1.2.3.4
     │   www.example.com.     300      IN  A        1.2.3.4
     │   ...
     │
     └── 7. Audit log: "🌐 DNS Records Generated"
```

---

## File Map

```
routes/dns/
├── __init__.py     78 lines  — blueprint + all 4 endpoints
└── README.md                 — this file
```

Single-file package. Core business logic lives in
`core/services/dns/cdn_ops.py` (565 lines).

---

## Per-File Documentation

### `__init__.py` — Blueprint + All Endpoints (78 lines)

| Function | Method | Route | What It Does |
|----------|--------|-------|-------------|
| `dns_status()` | GET | `/dns/status` | CDN provider detection (cached) |
| `dns_lookup()` | GET | `/dns/lookup/<domain>` | Live DNS lookup via `dig` |
| `dns_ssl()` | GET | `/dns/ssl/<domain>` | Live SSL certificate check via `openssl` |
| `dns_generate()` | POST | `/dns/generate` | Generate DNS records + BIND zone file |

**Status with caching:**

```python
from src.core.services.devops.cache import get_cached

root = _project_root()
force = request.args.get("bust", "") == "1"
return jsonify(get_cached(
    root, "dns",
    lambda: dns_cdn_ops.dns_cdn_status(root),
    force=force,
))
```

Detection is offline (filesystem scan only) but can be slow on large
projects. Cache key is `"dns"` in the devops cache system.

**Lookup — URL parameter as domain:**

```python
@dns_bp.route("/dns/lookup/<domain>")
def dns_lookup(domain: str):
    result = dns_cdn_ops.dns_lookup(domain)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)
```

The domain comes from the URL path, not query params. This makes
the endpoint cacheable by browsers and CDNs (GET with full URL).

**SSL — same URL parameter pattern:**

```python
@dns_bp.route("/dns/ssl/<domain>")
def dns_ssl(domain: str):
    result = dns_cdn_ops.ssl_check(domain)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)
```

**Generate — rich parameter set:**

```python
result = dns_cdn_ops.generate_dns_records(
    domain,
    target_ip=data.get("ip", ""),
    cname_target=data.get("cname", ""),
    mail_provider=data.get("mail", ""),
    include_spf=data.get("spf", True),
    include_dmarc=data.get("dmarc", True),
)
```

Six parameters control record generation. SPF and DMARC default to
`True` — security-first design.

---

## Dependency Graph

```
__init__.py (routes)
├── dns.cdn_ops             ← eager import (used by all endpoints)
│   ├── subprocess          ← dig, openssl (lookup, ssl)
│   ├── shutil.which()      ← tool availability checks
│   ├── yaml, json, tomllib ← config file parsing (detection)
│   ├── audit_helpers       ← audit trail on generation
│   └── tool_requirements   ← check_required_tools (status)
├── devops.cache            ← lazy import for get_cached (status only)
└── helpers                 ← project_root
```

**Core service internals (cdn_ops.py, 565 lines):**

```
cdn_ops.py
├── _CDN_PROVIDERS dict — 5 provider definitions
│   ├── cloudflare   (config: wrangler.toml, cli: wrangler)
│   ├── aws_cloudfront (config: cloudformation templates)
│   ├── netlify      (config: netlify.toml, cli: netlify)
│   ├── vercel       (config: vercel.json, cli: vercel)
│   └── github_pages (config: CNAME file)
├── _SKIP_DIRS       — directories excluded from scanning
├── dns_cdn_status()        — offline detection (93-167)
├── _detect_cdn_provider()  — per-provider check (170-227)
├── _extract_domains_from_configs() — domain extraction (230-264)
├── dns_lookup()            — live DNS via dig (272-368)
├── ssl_check()             — live SSL via openssl (371-424)
└── generate_dns_records()  — record + zone file generation (432-564)
```

---

## Consumers

| Layer | Module | What It Uses |
|-------|--------|-------------|
| Server | `ui/web/server.py` | Imports `dns_bp`, registers at `/api` prefix |
| Dashboard | `scripts/devops/_dns.html` | `GET /dns/status` (DNS card) |
| Integrations | `scripts/integrations/_dns.html` | `GET /dns/status`, `/dns/lookup/*`, `/dns/ssl/*` |
| DNS setup | `scripts/integrations/setup/_dns.html` | `POST /dns/generate` |
| Wizard | `scripts/wizard/_integration_actions.html` | Triggers DNS generation via `/wizard/setup { action: "dns" }` |
| Cache | `scripts/globals/_cache.html` | Cache bust includes `"dns"` key |

---

## Service Delegation Map

```
Route Handler       →   Core Service Function
──────────────────────────────────────────────────────────────────
dns_status()        →   devops_cache.get_cached("dns", ...)
                         └→ dns_cdn_ops.dns_cdn_status(root)
                              ├→ _detect_cdn_provider() × 5 providers
                              ├→ _extract_domains_from_configs()
                              ├→ rglob(*.zone, *.dns, db.*)
                              ├→ rglob(*.pem, *.crt, *.cert, *.key)
                              └→ check_required_tools(["dig", "openssl", "curl"])

dns_lookup(domain)  →   dns_cdn_ops.dns_lookup(domain)
                         ├→ shutil.which("dig")  — availability gate
                         ├→ subprocess: dig +short <domain> A
                         ├→ subprocess: dig +short <domain> CNAME
                         ├→ subprocess: dig +short <domain> MX
                         ├→ subprocess: dig +short <domain> TXT
                         └→ subprocess: dig +short <domain> NS

dns_ssl(domain)     →   dns_cdn_ops.ssl_check(domain)
                         ├→ shutil.which("openssl")  — availability gate
                         ├→ subprocess: openssl s_client -connect <domain>:443
                         └→ subprocess: openssl x509 -noout -dates -issuer

dns_generate()      →   dns_cdn_ops.generate_dns_records(domain, ...)
                         ├→ compose A, CNAME, MX, TXT records
                         ├→ format BIND zone file
                         └→ _audit("🌐 DNS Records Generated", ...)
```

---

## Data Shapes

### `GET /api/dns/status` response

```json
{
    "cdn_providers": [
        {
            "id": "github_pages",
            "name": "GitHub Pages",
            "detected_by": "CNAME file",
            "cli_available": false
        }
    ],
    "domains": ["example.com", "docs.example.com"],
    "dns_files": ["CNAME"],
    "ssl_certs": [
        { "path": "certs/server.crt", "type": "certificate" },
        { "path": "certs/server.key", "type": "private_key" }
    ],
    "has_cdn": true,
    "has_dns": true,
    "missing_tools": {
        "dig": { "found": true, "path": "/usr/bin/dig" },
        "openssl": { "found": true, "path": "/usr/bin/openssl" },
        "curl": { "found": true, "path": "/usr/bin/curl" }
    }
}
```

### `GET /api/dns/status` response (no DNS/CDN)

```json
{
    "cdn_providers": [],
    "domains": [],
    "dns_files": [],
    "ssl_certs": [],
    "has_cdn": false,
    "has_dns": false,
    "missing_tools": {
        "dig": { "found": false },
        "openssl": { "found": true, "path": "/usr/bin/openssl" },
        "curl": { "found": true, "path": "/usr/bin/curl" }
    }
}
```

### `GET /api/dns/lookup/example.com` response

```json
{
    "ok": true,
    "domain": "example.com",
    "records": [
        { "type": "A", "value": "93.184.216.34" },
        { "type": "CNAME", "value": "cdn.example.com" },
        { "type": "MX", "value": "10 mail.example.com" },
        { "type": "TXT", "value": "v=spf1 include:_spf.google.com -all" },
        { "type": "NS", "value": "ns1.example.com" },
        { "type": "NS", "value": "ns2.example.com" }
    ],
    "cname": "cdn.example.com",
    "a_records": ["93.184.216.34"],
    "nameservers": ["ns1.example.com", "ns2.example.com"],
    "record_count": 6
}
```

### `GET /api/dns/lookup/example.com` response (dig unavailable)

```json
{
    "ok": false,
    "error": "dig command not available"
}
```

### `GET /api/dns/ssl/example.com` response

```json
{
    "ok": true,
    "domain": "example.com",
    "valid": true,
    "issuer": "C = US, O = Let's Encrypt, CN = E5",
    "expiry": "Mar 15 12:00:00 2026 GMT"
}
```

### `GET /api/dns/ssl/example.com` response (openssl unavailable)

```json
{
    "ok": false,
    "error": "openssl not available"
}
```

### `POST /api/dns/generate` request

```json
{
    "domain": "example.com",
    "ip": "1.2.3.4",
    "cname": "",
    "mail": "google",
    "spf": true,
    "dmarc": true
}
```

### `POST /api/dns/generate` response

```json
{
    "ok": true,
    "domain": "example.com",
    "records": [
        { "type": "A", "name": "@", "value": "1.2.3.4", "ttl": 300 },
        { "type": "A", "name": "www", "value": "1.2.3.4", "ttl": 300 },
        { "type": "MX", "name": "@", "value": "1 aspmx.l.google.com", "ttl": 3600 },
        { "type": "MX", "name": "@", "value": "5 alt1.aspmx.l.google.com", "ttl": 3600 },
        { "type": "MX", "name": "@", "value": "5 alt2.aspmx.l.google.com", "ttl": 3600 },
        { "type": "MX", "name": "@", "value": "10 alt3.aspmx.l.google.com", "ttl": 3600 },
        { "type": "MX", "name": "@", "value": "10 alt4.aspmx.l.google.com", "ttl": 3600 },
        { "type": "TXT", "name": "@", "value": "v=spf1 include:_spf.google.com -all", "ttl": 3600 },
        { "type": "TXT", "name": "_dmarc", "value": "v=DMARC1; p=quarantine; rua=mailto:dmarc@example.com; pct=100", "ttl": 3600 }
    ],
    "record_count": 9,
    "zone_file": "; DNS records for example.com\n$ORIGIN example.com.\n$TTL 300\n\nexample.com.                   300      IN  A        1.2.3.4\nwww.example.com.               300      IN  A        1.2.3.4\n..."
}
```

### `POST /api/dns/generate` response (missing domain)

```json
{
    "error": "Missing 'domain' field"
}
```

---

## Advanced Feature Showcase

### 1. Multi-Provider CDN Detection

The core service detects 5 CDN providers by scanning for provider-specific
config files and checking CLI tool availability:

```python
# From cdn_ops.py — provider definitions
_CDN_PROVIDERS = {
    "cloudflare": {
        "name": "Cloudflare",
        "config_files": ["wrangler.toml", "wrangler.json", "cloudflare.json"],
        "cli": "wrangler",
        "markers": ["cloudflare", "CF-"],
    },
    "netlify": {
        "name": "Netlify",
        "config_files": ["netlify.toml"],
        "cli": "netlify",
        "markers": ["netlify", "netlify.app"],
    },
    # ... aws_cloudfront, vercel, github_pages
}
```

Each detection returns both what was detected and how:

```python
detection = {
    "id": "cloudflare",
    "name": "Cloudflare",
    "detected_by": "wrangler.toml",      # which file triggered detection
    "cli_available": True,               # whether CLI tool is installed
}
```

### 2. Tool Availability Gates

Lookup and SSL endpoints check for required CLI tools before attempting
subprocess calls:

```python
# dns_lookup()
if not shutil.which("dig"):
    return {"ok": False, "error": "dig command not available"}

# ssl_check()
if not shutil.which("openssl"):
    return {"ok": False, "error": "openssl not available"}
```

The status endpoint also reports tool availability via
`check_required_tools(["dig", "openssl", "curl"])`, allowing the
UI to show install buttons for missing tools.

### 3. Mail Provider Integration

Record generation includes full MX configuration for supported mail
providers:

```python
if mail_provider == "google":
    mx_records = [
        (1,  "aspmx.l.google.com"),
        (5,  "alt1.aspmx.l.google.com"),
        (5,  "alt2.aspmx.l.google.com"),
        (10, "alt3.aspmx.l.google.com"),
        (10, "alt4.aspmx.l.google.com"),
    ]
elif mail_provider == "protonmail":
    mx_records = [
        (10, "mail.protonmail.ch"),
        (20, "mailsec.protonmail.ch"),
    ]
```

SPF records are also provider-aware:

```python
if mail_provider == "google":
    spf_value += " include:_spf.google.com"
elif mail_provider == "protonmail":
    spf_value += " include:_spf.protonmail.ch"
```

### 4. BIND Zone File Generation

The generate endpoint produces both structured JSON records and a
complete BIND-format zone file ready for copy-paste:

```python
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
        name = domain + "."      # BIND requires FQDN
    elif not name.endswith("."):
        name = f"{name}.{domain}."
    zone_lines.append(
        f"{name:<30} {r['ttl']:<8} IN  {r['type']:<8} {r['value']}"
    )
```

### 5. Security-First Defaults

SPF and DMARC are enabled by default:

```python
include_spf=data.get("spf", True),     # default: include SPF
include_dmarc=data.get("dmarc", True),  # default: include DMARC
```

The DMARC policy defaults to `p=quarantine` (not `p=none`), which
actively protects against email spoofing rather than just monitoring.

### 6. Two-Stage OpenSSL Pipeline

The SSL check uses a two-stage subprocess pipeline to extract
certificate details:

```python
# Stage 1: Connect and retrieve certificate chain
result = subprocess.run(
    ["openssl", "s_client", "-connect", f"{domain}:443",
     "-servername", domain, "-showcerts"],
    input="", capture_output=True, text=True, timeout=10,
)

# Stage 2: Parse certificate dates and issuer
cert_result = subprocess.run(
    ["openssl", "x509", "-noout", "-dates", "-issuer"],
    input=result.stdout,      # pipe stage 1 output
    capture_output=True, text=True, timeout=5,
)
```

The `-servername` flag enables SNI (Server Name Indication), which
is required for hosts serving multiple domains on the same IP.

---

## Design Decisions

### Why DNS routes use a single-file package

78 lines, 4 endpoints. The entire package is a thin passthrough
to `dns/cdn_ops.py` (565 lines). Splitting 78 lines into sub-modules
would add directory noise with zero benefit. The package exists as
a directory for consistency with every other route domain.

### Why status is cached but lookup and SSL are not

- **Status** scans the entire project filesystem for CDN configs,
  zone files, and SSL certs. This is expensive and rarely changes.
  Cache key: `"dns"`.
- **Lookup** makes live network calls to DNS servers. Caching would
  return stale DNS data, which defeats the purpose of a live lookup.
- **SSL** connects to remote servers to check certificates. Caching
  would miss certificate renewals or expirations.

### Why domain is a URL path parameter, not a query param

```python
@dns_bp.route("/dns/lookup/<domain>")
```

Using the path makes the URL RESTful (`/dns/lookup/example.com`)
and allows browser-level and CDN-level caching of GET responses.
Query params (`?domain=example.com`) would work but are less
conventional for resource identification.

### Why SPF and DMARC default to True

Email security records are frequently forgotten or misconfigured.
By defaulting to `True`, every generated DNS zone includes baseline
email security. Users who explicitly don't want them can pass
`spf: false, dmarc: false`. This is the "secure by default" principle.

### Why the zone file uses BIND format

BIND format is the universal standard for DNS zone files. Every
DNS provider (Cloudflare, Route 53, Google Cloud DNS, etc.) can
import BIND zone files. Generating provider-specific formats
(Terraform HCL, CloudFormation JSON) would limit portability.

### Why both A and CNAME options exist

- **A record** (`ip: "1.2.3.4"`) → direct IP pointing. Used when
  the user controls the server.
- **CNAME** (`cname: "cdn.example.com"`) → alias to another domain.
  Used when pointing to a CDN or PaaS. These are mutually exclusive
  for the `www` subdomain (DNS RFC doesn't allow CNAME at apex
  alongside other records).

---

## Coverage Summary

| Capability | Endpoint | Method | Live/Cached |
|-----------|----------|--------|-------------|
| CDN provider detection | `/dns/status` | GET | Cached |
| DNS record lookup | `/dns/lookup/<domain>` | GET | Live (dig) |
| SSL certificate check | `/dns/ssl/<domain>` | GET | Live (openssl) |
| DNS record generation | `/dns/generate` | POST | N/A (generation) |
