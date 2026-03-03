# CLI Domain: DNS — Provider Detection, Lookups, SSL & Record Generation

> **1 file · 230 lines · 5 commands · Group: `controlplane dns`**
>
> Detects CDN providers and domain configurations, performs live DNS
> lookups with record-type grouping, checks SSL certificate validity
> and expiration, and generates mail-aware DNS record sets with zone
> file output. All DNS operations support JSON output.
>
> Core service: `core/services/dns/cdn_ops.py`

---

## How It Works

```
┌──────────────────────────────────────────────────────────────────────┐
│                         controlplane dns                            │
│                                                                      │
│  ┌─ Detect ──┐   ┌──── Observe ──────┐   ┌── Generate ──────────┐  │
│  │ status    │   │ lookup DOMAIN     │   │ generate DOMAIN      │  │
│  └───────────┘   │ ssl DOMAIN        │   │   --ip / --cname     │  │
│                   └───────────────────┘   │   --mail / --no-spf  │  │
│                                           └──────────────────────┘  │
└──────────┬────────────────┬──────────────────┬──────────────────────┘
           │                │                  │
           ▼                ▼                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    core/services/dns/cdn_ops.py                     │
│                                                                      │
│  dns_cdn_status(root)                                                │
│    ├── Detect CDN providers (Cloudflare, AWS, etc.)                  │
│    ├── Find domains from config files                                │
│    ├── List DNS zone files                                           │
│    └── Detect SSL certificate files                                  │
│                                                                      │
│  dns_lookup(domain) → resolve A, AAAA, CNAME, MX, TXT, NS          │
│  ssl_check(domain)  → connect, read cert, check validity/expiry     │
│  generate_dns_records(domain, ...) → records[] + zone_file text     │
└──────────────────────────────────────────────────────────────────────┘
```

### Detection-Observe-Generate Pattern

Like Docker, CI, Security, and other domains, DNS follows the
three-phase pattern:

1. **Detect** (`status`) — scan project for CDN config, domains, certs
2. **Observe** (`lookup`, `ssl`) — query live DNS and SSL for a domain
3. **Generate** (`generate`) — create DNS record sets from parameters

### CDN Provider Detection

```
status(root)
├── Scan for CDN provider config files
│   ├── Cloudflare → wrangler.toml, cloudflare.yml, CF_* env vars
│   ├── AWS CloudFront → cloudfront.json, aws CDK config
│   ├── Vercel → vercel.json
│   └── Netlify → netlify.toml
├── Check CLI availability for each provider
├── Extract configured domains from config files
├── Find DNS zone files (*.zone, *.bind)
└── Find SSL cert/key files (*.pem, *.crt, *.key)
```

### DNS Lookup

The `lookup` command performs live DNS resolution using the system
resolver. Records are grouped by type for readability:

```
lookup("example.com")
├── Query multiple record types: A, AAAA, CNAME, MX, TXT, NS
├── Collect all results
├── Group by type
└── Report record_count + nameservers
```

### SSL Certificate Check

```
ssl("example.com")
├── TLS connect to domain:443
├── Read server certificate
├── Check:
│   ├── Validity (is the cert currently valid?)
│   ├── Issuer (who signed it?)
│   └── Expiry (when does it expire?)
└── Report valid/invalid + details
```

### Record Generation

```
generate("example.com", ip="1.2.3.4", mail="google")
├── Create A record → 1.2.3.4
├── If --cname → create CNAME record
├── If --mail=google → add Google Workspace MX records
├── If --mail=protonmail → add Proton MX records
├── Unless --no-spf → add SPF TXT record
├── Unless --no-dmarc → add DMARC TXT record
├── Combine into records[]
└── Generate zone_file text (BIND format)
```

---

## Commands

### `controlplane dns status`

Show DNS and CDN configuration status for the current project.

```bash
controlplane dns status
controlplane dns status --json
```

**Output example:**

```
🌐 DNS & CDN Status:

   CDN Providers:
      ✅ cloudflare
         Detected: wrangler.toml

   🔗 Domains (2):
      example.com
      api.example.com

   📄 DNS files (1):
      dns/example.com.zone

   🔒 SSL certificates (2):
      🔑 certs/privkey.pem (private_key)
      📜 certs/fullchain.pem (certificate)
```

**Empty project:**

```
🌐 DNS & CDN Status:

   📡 No CDN providers detected

   💡 No DNS/CDN configuration detected
```

---

### `controlplane dns lookup DOMAIN`

Perform DNS lookup for a domain, grouped by record type.

```bash
controlplane dns lookup example.com
controlplane dns lookup example.com --json
```

**Output example:**

```
🔍 Looking up example.com...
🌐 example.com (6 records):

   A:
      93.184.216.34
   AAAA:
      2606:2800:220:1:248:1893:25c8:1946
   MX:
      10 mail.example.com
   TXT:
      "v=spf1 include:_spf.google.com ~all"
   NS:
      ns1.example.com
      ns2.example.com

   Nameservers: ns1.example.com, ns2.example.com
```

---

### `controlplane dns ssl DOMAIN`

Check SSL certificate validity and expiration for a domain.

```bash
controlplane dns ssl example.com
controlplane dns ssl example.com --json
```

**Output examples:**

```
🔒 Checking SSL for example.com...
✅ SSL valid for example.com
   Issuer: Let's Encrypt Authority X3
   Expires: 2026-06-15
```

```
🔒 Checking SSL for expired.example.com...
❌ SSL invalid for expired.example.com
   Issuer: DigiCert Inc
   Expires: 2025-01-01
```

---

### `controlplane dns generate DOMAIN`

Generate DNS records for a domain with optional mail configuration.

```bash
# Basic A record
controlplane dns generate example.com --ip 93.184.216.34

# CNAME + mail records for Google Workspace
controlplane dns generate example.com --cname app.example.com --mail google

# Without SPF/DMARC
controlplane dns generate example.com --ip 1.2.3.4 --no-spf --no-dmarc

# JSON output
controlplane dns generate example.com --ip 1.2.3.4 --json
```

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `DOMAIN` | argument | (required) | Domain to generate records for |
| `--ip` | string | (none) | Target IP for A records |
| `--cname` | string | (none) | CNAME target |
| `--mail` | string | (none) | Mail provider (`google` or `protonmail`) |
| `--no-spf` | flag | off | Skip SPF TXT record |
| `--no-dmarc` | flag | off | Skip DMARC TXT record |
| `--json` | flag | off | JSON output |

**Output example:**

```
🌐 DNS Records for example.com:

   A        example.com     → 93.184.216.34
   MX       example.com     → 1 aspmx.l.google.com
   MX       example.com     → 5 alt1.aspmx.l.google.com
   TXT      example.com     → "v=spf1 include:_spf.google.com ~all"
   TXT      _dmarc          → "v=DMARC1; p=none; rua=mailto:dmarc@example.com"

   📄 Zone file:
────────────────────────────────────────────────────────
; Zone file for example.com
; Generated by controlplane
$ORIGIN example.com.
$TTL 3600

@    IN  A      93.184.216.34
@    IN  MX     1 aspmx.l.google.com.
@    IN  MX     5 alt1.aspmx.l.google.com.
@    IN  TXT    "v=spf1 include:_spf.google.com ~all"
_dmarc  IN  TXT "v=DMARC1; p=none; rua=mailto:dmarc@example.com"
────────────────────────────────────────────────────────
```

**Record type color coding:** In terminal output, each record type gets
a distinct color: A (green), CNAME (blue), MX (yellow), TXT (magenta).

---

## File Map

```
cli/dns/
├── __init__.py    230 lines — group definition + 5 commands +
│                              _resolve_project_root helper
└── README.md               — this file
```

**Total: 230 lines of Python in 1 file.**

---

## Per-File Documentation

### `__init__.py` — Group + all commands (230 lines)

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `_resolve_project_root(ctx)` | helper | Reads `config_path` from context, falls back to `find_project_file()` |
| `dns()` | Click group | Top-level `dns` group |
| `status(ctx, as_json)` | command | Scan project for CDN providers, domains, DNS files, SSL certs |
| `lookup(domain, as_json)` | command | Live DNS resolution with record-type grouping |
| `ssl(domain, as_json)` | command | SSL certificate validity and expiry check |
| `generate(domain, ...)` | command | Generate DNS records with zone file output |

**Code organization within the file:**

```python
# ── Detect ──   (status)        lines 31-88
# ── Observe ──  (lookup, ssl)   lines 91-169
# ── Facilitate ── (generate)    lines 172-230
```

The file uses section markers (`# ── Detect ──`, `# ── Observe ──`,
`# ── Facilitate ──`) to organize commands by their role in the
detect-observe-generate pattern.

**Core service imports (all lazy):**

| Import | From | Used For |
|--------|------|----------|
| `dns_cdn_status` | `dns.cdn_ops` | CDN provider detection + project DNS scan |
| `dns_lookup` | `dns.cdn_ops` | Live DNS record resolution |
| `ssl_check` | `dns.cdn_ops` | TLS connection + certificate check |
| `generate_dns_records` | `dns.cdn_ops` | Record set generation with mail support |

**Note on `lookup` and `ssl`:** These commands don't use `_resolve_project_root`
because they operate on arbitrary domains, not project-specific data. Only
`status` needs the project root to scan for configuration files.

---

## Dependency Graph

```
__init__.py
├── click                      ← click.group, click.command
├── core.config.loader         ← find_project_file (lazy, _resolve_project_root)
└── core.services.dns.cdn_ops  ← dns_cdn_status, dns_lookup,
                                  ssl_check, generate_dns_records (all lazy)
```

This is one of the simplest dependency graphs — all commands go to
a single core module (`dns.cdn_ops`), no cross-domain imports.

---

## Consumers

### Who registers this CLI group

| Layer | Module | What It Does |
|-------|--------|-------------|
| CLI entry | `src/main.py` | `from src.ui.cli.dns import dns` |

### Who also uses the same core service

| Layer | Module | Core Service Used |
|-------|--------|------------------|
| Web routes | `routes/dns/__init__.py` | `dns.cdn_ops` (status, lookup, ssl, generate) |
| Core | `wizard/helpers.py:71` | `dns_cdn_status` (wizard environment detection) |
| Core | `wizard/setup_dns.py:49` | `generate_dns_records` (wizard DNS setup handler) |

---

## Design Decisions

### Why all commands are in __init__.py

With 230 lines and 5 commands that all import from the same core module
(`dns.cdn_ops`), splitting into sub-files would add import ceremony
without improving readability. Each command is a thin wrapper with
straightforward formatting logic.

### Why lookup and ssl don't need project root

`lookup` and `ssl` query external DNS/TLS servers for arbitrary domains.
They don't need to read project config. This makes them usable as
standalone diagnostic tools outside any project context.

### Why generate uses --no-spf / --no-dmarc (negative flags)

SPF and DMARC records are security best practices that should be
included by default. Users who specifically don't want them must
opt out explicitly. The negative flag naming makes it clear that
omitting these records is a conscious choice, not an oversight.

### Why mail supports specific providers (not arbitrary MX)

Mail record configuration is complex (MX priorities, SPF includes,
DKIM selectors vary by provider). Pre-built templates for Google
Workspace and Protonmail avoid error-prone manual configuration.
Users with custom mail setups can edit the zone file after generation.

### Why zone file output is always shown (not --write)

Unlike CI/Docker/Quality generators that create `.yml` files in
specific locations, DNS zone files don't have a standard project
path. The command outputs the zone file text so the user can pipe it
to a file or copy it to their DNS provider's dashboard.

### Why record types are color-coded

In DNS troubleshooting, you're often scanning for specific record
types. Color-coding makes A (green), CNAME (blue), MX (yellow),
and TXT (magenta) visually distinct even in long record lists.

---

## JSON Output Examples

### `dns status --json`

```json
{
  "cdn_providers": [
    {
      "name": "cloudflare",
      "cli_available": true,
      "detected_by": ["wrangler.toml"]
    }
  ],
  "domains": ["example.com", "api.example.com"],
  "dns_files": ["dns/example.com.zone"],
  "ssl_certs": [
    {"path": "certs/privkey.pem", "type": "private_key"},
    {"path": "certs/fullchain.pem", "type": "certificate"}
  ]
}
```

### `dns lookup example.com --json`

```json
{
  "domain": "example.com",
  "record_count": 6,
  "records": [
    {"type": "A", "value": "93.184.216.34"},
    {"type": "AAAA", "value": "2606:2800:220:1:248:1893:25c8:1946"},
    {"type": "MX", "value": "10 mail.example.com"},
    {"type": "TXT", "value": "v=spf1 include:_spf.google.com ~all"}
  ],
  "nameservers": ["ns1.example.com", "ns2.example.com"]
}
```

### `dns ssl example.com --json`

```json
{
  "domain": "example.com",
  "valid": true,
  "issuer": "Let's Encrypt Authority X3",
  "expiry": "2026-06-15",
  "days_remaining": 105
}
```

### `dns generate example.com --ip 1.2.3.4 --mail google --json`

```json
{
  "domain": "example.com",
  "records": [
    {"type": "A", "name": "example.com", "value": "1.2.3.4"},
    {"type": "MX", "name": "example.com", "value": "1 aspmx.l.google.com"},
    {"type": "MX", "name": "example.com", "value": "5 alt1.aspmx.l.google.com"},
    {"type": "TXT", "name": "example.com", "value": "v=spf1 include:_spf.google.com ~all"},
    {"type": "TXT", "name": "_dmarc", "value": "v=DMARC1; p=none; rua=mailto:dmarc@example.com"}
  ],
  "zone_file": "; Zone file for example.com\n$ORIGIN example.com.\n..."
}
```

