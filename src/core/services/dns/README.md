# DNS Domain

> **2 files · 571 lines · DNS detection, CDN provider analysis, live
> DNS lookup, SSL certificate check, and DNS record generation with
> BIND zone file output.**
>
> A three-phase domain: **detect** what DNS/CDN infrastructure exists
> in the project (offline, from config files), **observe** live DNS and
> SSL state (online, via `dig` and `openssl`), and **facilitate** new
> DNS configuration by generating record sets and zone files.

---

## How It Works

The DNS domain operates in three distinct phases. Each phase can run
independently — detection is offline and instant, observation requires
network access, and generation is pure computation.

```
┌──────────────────────────────────────────────────────────────────┐
│ Phase 1: DETECT — What DNS/CDN exists in this project?           │
│                                                                   │
│  dns_cdn_status(project_root)                                     │
│    │                                                              │
│    ├── For each of 6 CDN providers:                               │
│    │     _detect_cdn_provider(root, id, spec)                     │
│    │       ├── Check spec.config_files on disk                    │
│    │       ├── Check spec.env_keys in .env / .env.production      │
│    │       ├── Check spec.tf_resource in *.tf files               │
│    │       └── If anything found → {id, name, detected_by, cli,   │
│    │                                 cli_available}                │
│    │                                                              │
│    ├── Extract domains:                                           │
│    │     _extract_domains_from_configs(root)                      │
│    │       ├── Regex-scan: netlify.toml, vercel.json,             │
│    │       │   wrangler.toml, CNAME, package.json                 │
│    │       └── Filter out noise: example.com, localhost,           │
│    │           npmjs.com, github.com, googleapis.com, etc.         │
│    │     + Read CNAME file (GitHub Pages)                          │
│    │                                                              │
│    ├── Scan for DNS zone files:                                   │
│    │     rglob("*.zone", "*.dns", "db.*")                         │
│    │     Skip: .git, .venv, node_modules, .terraform, ...         │
│    │                                                              │
│    ├── Scan for SSL certificate files:                            │
│    │     rglob("*.pem", "*.crt", "*.cert", "*.key")               │
│    │     Classify: .key → "private_key", rest → "certificate"     │
│    │                                                              │
│    └── Check required tools: dig, openssl, curl                   │
│          (via tool_requirements.check_required_tools)              │
│                                                                   │
│  OUTPUT: {cdn_providers, domains, dns_files, ssl_certs,           │
│           has_cdn, has_dns, missing_tools}                         │
├──────────────────────────────────────────────────────────────────┤
│ Phase 2: OBSERVE — What does DNS say right now?                   │
│                                                                   │
│  dns_lookup(domain)                                               │
│    Requires: dig on PATH                                          │
│    Runs 5 sequential dig queries:                                 │
│      dig +short <domain> A     → a_records[]                      │
│      dig +short <domain> CNAME → cname (stripped trailing dot)    │
│      dig +short <domain> MX    → records[]                        │
│      dig +short <domain> TXT   → records[] (stripped quotes)      │
│      dig +short <domain> NS    → nameservers[]                    │
│    Each query has a 10-second timeout.                             │
│                                                                   │
│  ssl_check(domain)                                                │
│    Requires: openssl on PATH                                      │
│    Two-step pipeline:                                              │
│      1. openssl s_client -connect <domain>:443 -servername ...    │
│      2. Pipe cert into: openssl x509 -noout -dates -issuer        │
│    Extracts: issuer, expiry date, validity                         │
│    Each step has a 10/5-second timeout.                            │
├──────────────────────────────────────────────────────────────────┤
│ Phase 3: FACILITATE — Generate DNS records for deployment          │
│                                                                   │
│  generate_dns_records(domain, *, target_ip, cname_target,         │
│                       mail_provider, include_spf, include_dmarc)  │
│    │                                                              │
│    ├── A records (if target_ip given):                             │
│    │     @ → target_ip (TTL 300)                                  │
│    │     www → target_ip (TTL 300)                                 │
│    │                                                              │
│    ├── CNAME record (if cname_target given):                      │
│    │     www → cname_target (TTL 300)                              │
│    │                                                              │
│    ├── MX records (if mail_provider given):                        │
│    │     "google"     → 5 records (pri 1, 5, 5, 10, 10)          │
│    │     "protonmail" → 2 records (pri 10, 20)                    │
│    │                                                              │
│    ├── SPF record (if include_spf):                                │
│    │     "v=spf1 include:<provider_spf> -all"                     │
│    │                                                              │
│    ├── DMARC record (if include_dmarc):                            │
│    │     "_dmarc" TXT → "v=DMARC1; p=quarantine;                  │
│    │                      rua=mailto:dmarc@<domain>; pct=100"     │
│    │                                                              │
│    ├── Build BIND zone file:                                       │
│    │     $ORIGIN <domain>.                                         │
│    │     $TTL 300                                                  │
│    │     <record lines, formatted with 30-char name column>        │
│    │                                                              │
│    └── Audit log: "🌐 DNS Records Generated"                      │
│                                                                   │
│  OUTPUT: {ok, domain, records, record_count, zone_file}           │
└──────────────────────────────────────────────────────────────────┘
```

### CDN Provider Detection

The system checks 6 CDN providers. Each provider has a spec that defines
what to look for. Detection is multi-signal: a provider is considered
"detected" if **any** signal hits — config file on disk, environment
variable in `.env`, or Terraform resource in `*.tf` files.

| Provider | ID | Config Files | Env Keys | TF Resource | CLI |
|----------|----|-------------|----------|-------------|-----|
| Cloudflare | `cloudflare` | `wrangler.toml`, `wrangler.json`, `cloudflare.json` | `CLOUDFLARE_API_TOKEN`, `CF_API_TOKEN`, `CLOUDFLARE_ZONE_ID` | — | `wrangler` |
| AWS CloudFront | `cloudfront` | — | — | `aws_cloudfront_distribution` | `aws` |
| Fastly | `fastly` | `fastly.toml` | `FASTLY_API_TOKEN` | — | `fastly` |
| Netlify | `netlify` | `netlify.toml`, `_redirects`, `_headers` | `NETLIFY_AUTH_TOKEN` | — | `netlify` |
| Vercel | `vercel` | `vercel.json`, `.vercel/project.json` | `VERCEL_TOKEN` | — | `vercel` |
| GitHub Pages | `github_pages` | `CNAME` | — | — | — |

**Detection flow for each provider:**

```
_detect_cdn_provider(root, "cloudflare", spec)
     │
     ├── Config files: does wrangler.toml exist? → "wrangler.toml"
     │
     ├── Env keys: scan .env, .env.production, .env.staging
     │     for CLOUDFLARE_API_TOKEN → "CLOUDFLARE_API_TOKEN in .env"
     │
     ├── TF resource: (only if spec has tf_resource)
     │     rglob("*.tf") → search for resource string
     │     Skip dirs in _SKIP_DIRS
     │
     ├── Nothing found? → return None (not detected)
     │
     └── Found something? → return:
           {
               "id": "cloudflare",
               "name": "Cloudflare",
               "detected_by": ["wrangler.toml", "CF_API_TOKEN in .env"],
               "cli": "wrangler",
               "cli_available": True,   # shutil.which("wrangler")
           }
```

### Domain Extraction

`_extract_domains_from_configs` uses a regex to find domain-like strings
in configuration files:

```python
r'(?:https?://)?([a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?'
r'(?:\.[a-zA-Z]{2,})+)'
```

Scans 5 config files: `netlify.toml`, `vercel.json`, `wrangler.toml`,
`CNAME`, `package.json`.

Filters out common false positives: `example.com`, `localhost`,
`npmjs.com`, `github.com`, `googleapis.com`, `pypi.org`, `python.org`,
`registry.*`, `cdn.*`, `unpkg.com`, `jsdelivr.net`.

### Skip Directories

Both detection and file scanning skip these directories (stored in
`_SKIP_DIRS` as a `frozenset`):

`.git`, `.venv`, `venv`, `node_modules`, `__pycache__`, `.terraform`,
`dist`, `build`, `.pages`, `htmlcov`, `.backup`, `state`

(12 directories)

---

## Key Data Shapes

### dns_cdn_status response

```python
{
    "cdn_providers": [
        {
            "id": "cloudflare",          # provider key
            "name": "Cloudflare",        # display name
            "detected_by": [             # list — what triggered detection
                "wrangler.toml",
                "CF_API_TOKEN in .env",
            ],
            "cli": "wrangler",           # CLI tool name (or None)
            "cli_available": True,       # shutil.which result
        },
    ],
    "domains": ["example.com", "www.example.com"],   # sorted list
    "dns_files": ["CNAME", "dns/example.zone"],
    "ssl_certs": [
        {"path": "certs/server.crt", "type": "certificate"},
        {"path": "certs/server.key", "type": "private_key"},
    ],
    "has_cdn": True,                     # len(cdn_providers) > 0
    "has_dns": True,                     # dns_files or domains non-empty
    "missing_tools": [                   # from check_required_tools
        {"tool": "dig", "available": False},
    ],
}
```

### dns_lookup response

```python
# Success
{
    "ok": True,
    "domain": "example.com",
    "records": [
        {"type": "A", "value": "93.184.216.34"},
        {"type": "CNAME", "value": "cdn.example.com"},
        {"type": "MX", "value": "10 mail.example.com"},
        {"type": "TXT", "value": "v=spf1 include:_spf.google.com ~all"},
        {"type": "NS", "value": "ns1.example.com"},
    ],
    "cname": "cdn.example.com",          # str or None (dot stripped)
    "a_records": ["93.184.216.34"],
    "nameservers": ["ns1.example.com"],   # dot stripped
    "record_count": 5,
}

# CLI not available
{"ok": False, "error": "dig command not available"}
```

### ssl_check response

```python
# Success
{
    "ok": True,
    "domain": "example.com",
    "valid": True,                       # openssl x509 returncode == 0
    "issuer": "C = US, O = Let's Encrypt, CN = R3",
    "expiry": "Jun 15 00:00:00 2026 GMT",
}

# CLI not available
{"ok": False, "error": "openssl not available"}

# Network failure
{"ok": False, "domain": "example.com", "error": "timed out"}
```

Note: `ssl_check` does **not** return `days_remaining` — the README
previously fabricated that field. The raw `notAfter` date string is
returned as `expiry` and the consumer must parse it.

### generate_dns_records response

```python
{
    "ok": True,
    "domain": "example.com",
    "records": [
        {"type": "A", "name": "@", "value": "93.184.216.34", "ttl": 300},
        {"type": "A", "name": "www", "value": "93.184.216.34", "ttl": 300},
        {"type": "MX", "name": "@", "value": "1 aspmx.l.google.com", "ttl": 3600},
        {"type": "TXT", "name": "@",
         "value": "v=spf1 include:_spf.google.com -all", "ttl": 3600},
        {"type": "TXT", "name": "_dmarc",
         "value": "v=DMARC1; p=quarantine; rua=mailto:dmarc@example.com; pct=100",
         "ttl": 3600},
    ],
    "record_count": 5,
    "zone_file": "; DNS records for example.com\n$ORIGIN example.com.\n...",
}
```

**Important details the old README got wrong:**

- A record TTL is **300** (5 minutes), not 3600. Only MX/SPF/DMARC
  use 3600.
- SPF uses **`-all`** (hard fail), not `~all` (soft fail).
- DMARC includes **`pct=100`** which the old README omitted.
- `generate_dns_records` returns **`record_count`** and **`domain`** in
  addition to `ok`, `records`, and `zone_file`.
- The response **does not** include a `priority` field on MX records —
  priority is embedded in the `value` string (e.g., `"1 aspmx.l.google.com"`).

### Mail Provider Presets

Only 2 mail providers are currently implemented (the old README
fabricated `microsoft`, `zoho`, and `fastmail`):

| Provider Key | MX Records | SPF Include |
|-------------|------------|-------------|
| `google` | `1 aspmx.l.google.com`, `5 alt1.aspmx.l.google.com`, `5 alt2.aspmx.l.google.com`, `10 alt3.aspmx.l.google.com`, `10 alt4.aspmx.l.google.com` | `_spf.google.com` |
| `protonmail` | `10 mail.protonmail.ch`, `20 mailsec.protonmail.ch` | `_spf.protonmail.ch` |

Any other `mail_provider` value results in no MX records and a bare
`v=spf1 -all` SPF record.

---

## Architecture

```
              Routes (dns/)     CLI (cli/dns/)     Wizard (setup_dns)
                   │                 │                    │
          ┌────────▼─────────────────▼────────────────────▼──┐
          │  __init__.py (6 lines)                            │
          │  Re-exports: dns_cdn_status, dns_lookup,          │
          │              ssl_check, generate_dns_records       │
          └──────────────────────┬────────────────────────────┘
                                 │
                                 ▼
                          cdn_ops.py (565 lines)
                          ┌──────────────────────────┐
                          │ Constants:                │
                          │   _SKIP_DIRS (12 dirs)    │
                          │   _CDN_PROVIDERS (6 specs)│
                          ├──────────────────────────┤
                          │ Detect:                   │
                          │   dns_cdn_status()        │
                          │   _detect_cdn_provider()  │
                          │   _extract_domains_*()    │
                          ├──────────────────────────┤
                          │ Observe:                  │
                          │   dns_lookup()            │
                          │   ssl_check()             │
                          ├──────────────────────────┤
                          │ Facilitate:               │
                          │   generate_dns_records()  │
                          └──────────────────────────┘
```

This domain is intentionally a single-file module. The entire DNS/CDN
logic lives in `cdn_ops.py` — 4 public functions, 2 private helpers,
and 2 constant registries. Splitting would create 3 tiny files with
excessive import overhead for no structural benefit.

### Backward Compatibility Shim

A shim file exists at `src/core/services/dns_cdn_ops.py`:

```python
from src.core.services.dns.cdn_ops import *  # noqa: F401, F403
```

This re-exports everything so that old imports like
`from src.core.services.dns_cdn_ops import dns_cdn_status` continue
working after the module was moved into the `dns/` package.

---

## Dependency Graph

```
cdn_ops.py
   │
   ├── subprocess              ← dig, openssl (runtime, Phase 2 only)
   ├── shutil.which            ← CLI availability checks
   ├── re                      ← domain extraction regex
   ├── audit_helpers           ← make_auditor("dns") for audit logging
   └── tool_requirements       ← check_required_tools (lazy, inside dns_cdn_status)
```

No circular dependencies. No imports from other service domains.
`tool_requirements` is imported lazily inside `dns_cdn_status` to avoid
load-time coupling.

---

## Consumers

| Layer | Module | What It Uses | Import Style |
|-------|--------|-------------|--------------|
| **Routes** | `routes/dns/__init__.py` | All 4 public functions | `import cdn_ops as dns_cdn_ops` (module-level) |
| **CLI** | `cli/dns/__init__.py` | `dns_cdn_status`, `dns_lookup`, `ssl_check`, `generate_dns_records` | Lazy (inside command functions) |
| **Wizard** | `wizard/setup_dns.py` | `generate_dns_records` | Lazy (inside handler) |
| **Wizard** | `wizard/helpers.py` | `dns_cdn_status` | Lazy (inside detection helper) |
| **Shim** | `dns_cdn_ops.py` (root) | `*` (star re-export) | Module-level |

---

## File Map

```
dns/
├── __init__.py    6 lines    — public API re-exports (4 functions)
├── cdn_ops.py     565 lines  — all DNS/CDN operations
└── README.md                 — this file
```

---

## Per-File Documentation

### `__init__.py` — Public API (6 lines)

Re-exports 4 functions from `cdn_ops.py`:

- `dns_cdn_status` — detect CDN providers, domains, DNS files, SSL certs
- `dns_lookup` — live DNS record lookup via `dig`
- `ssl_check` — SSL certificate check via `openssl`
- `generate_dns_records` — generate DNS records + BIND zone file

### `cdn_ops.py` — DNS & CDN Operations (565 lines)

**Constants:**

| Constant | Type | Contents |
|----------|------|----------|
| `_SKIP_DIRS` | `frozenset` | 12 directories excluded from scanning: `.git`, `.venv`, `venv`, `node_modules`, `__pycache__`, `.terraform`, `dist`, `build`, `.pages`, `htmlcov`, `.backup`, `state` |
| `_CDN_PROVIDERS` | `dict[str, dict]` | 6 provider specs, each with: `name`, `config_files`, optional `env_keys`, optional `tf_resource`, optional `cli`, `markers` |

**Public Functions:**

| Function | What It Does |
|----------|-------------|
| `dns_cdn_status(project_root)` | Detect CDN providers, extract domains from configs, scan for zone files and SSL certs, check required CLI tools. Returns the full detection result used by the DevOps dashboard DNS card. |
| `dns_lookup(domain)` | Run 5 `dig +short` queries (A, CNAME, MX, TXT, NS) with 10s timeouts. Parse output into typed record list. Returns `{"ok": False}` if dig not on PATH. |
| `ssl_check(domain)` | Two-step `openssl` pipeline: `s_client` to fetch cert, then `x509` to extract issuer and expiry. Returns `{"ok": False}` if openssl not on PATH. |
| `generate_dns_records(domain, ...)` | Build DNS record list from parameters + format as BIND zone file. Supports Google and Protonmail MX presets, SPF, and DMARC generation. Audits the generation. |

**Private Functions:**

| Function | What It Does |
|----------|-------------|
| `_detect_cdn_provider(root, prov_id, spec)` | Check a single CDN provider against the project: config files → env keys → Terraform resources. Returns `{id, name, detected_by, cli, cli_available}` or `None`. |
| `_extract_domains_from_configs(root)` | Regex-scan 5 config files for domain-like strings. Filters common false positives (npm, GitHub, PyPI, CDN hosts). Returns `set[str]`. |

---

## Advanced Feature Showcase

### 1. Multi-Signal CDN Detection — Config → Env → Terraform Cascade

Each CDN provider is checked against three independent signal sources:

```python
# cdn_ops.py — _detect_cdn_provider (lines 170-227)

def _detect_cdn_provider(project_root, prov_id, spec):
    detected_by: list[str] = []

    # Signal 1: Config files on disk
    for cfg in spec.get("config_files", []):
        if (project_root / cfg).is_file():
            detected_by.append(cfg)

    # Signal 2: Environment variables in .env files
    for env_file_name in (".env", ".env.production", ".env.staging"):
        env_path = project_root / env_file_name
        if env_path.is_file():
            content = env_path.read_text(...)
            for key in spec.get("env_keys", []):
                if key in content:
                    detected_by.append(f"{key} in {env_file_name}")
                    break   # one key per file is enough

    # Signal 3: Terraform resources in *.tf files
    tf_resource = spec.get("tf_resource")
    if tf_resource:
        for tf_file in project_root.rglob("*.tf"):
            # skip _SKIP_DIRS ...
            if tf_resource in content:
                detected_by.append(f"{tf_resource} in {tf_file}")
                break

    if not detected_by:
        return None     # not detected

    return {"id": prov_id, "name": spec["name"],
            "detected_by": detected_by,
            "cli": spec.get("cli"),
            "cli_available": shutil.which(cli_name) is not None}
```

Key: the `detected_by` list accumulates ALL signals — a project might
have both `wrangler.toml` and `CF_API_TOKEN in .env`. This gives the
dashboard a complete picture of why a provider was flagged. The env
scan checks 3 env files (`.env`, `.env.production`, `.env.staging`)
but breaks after one key match per file to avoid noise.

### 2. Domain Regex with False-Positive Filtering

Domain extraction uses a broad regex then filters common noise:

```python
# cdn_ops.py — _extract_domains_from_configs (lines 230-264)

domain_pattern = re.compile(
    r'(?:https?://)?([a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?'
    r'(?:\.[a-zA-Z]{2,})+)'
)

# Scans 5 files: netlify.toml, vercel.json, wrangler.toml, CNAME, package.json
for name in config_files:
    content = path.read_text(...)
    for m in domain_pattern.finditer(content):
        domain = m.group(1)
        if not any(skip in domain for skip in [
            "example.com", "localhost", "npmjs.com", "github.com",
            "googleapis.com", "pypi.org", "python.org",
            "registry.", "cdn.", "unpkg.com", "jsdelivr.net",
        ]):
            domains.add(domain)
```

The regex matches both bare domains (`example.com`) and URL-prefixed
ones (`https://example.com`). The 11-item filter list removes false
positives from package metadata (npm registry, PyPI, CDN hosts) that
would pollute the domain list shown on the dashboard.

### 3. BIND Zone File Formatting — 30-Character Column Alignment

Generated zone files use column-aligned formatting for readability:

```python
# cdn_ops.py — generate_dns_records (lines 527-548)

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
```

The `@` → FQDN expansion and the `:<30` format specifier ensure
zone files are valid BIND syntax and readable. The `$ORIGIN` directive
sets the base, and `$TTL 300` provides the default TTL. This output
can be directly imported into Cloudflare, Route53, or used with BIND.

### 4. Two-Step SSL Pipeline — s_client → x509 Pipe

SSL certificate checking uses two chained openssl commands:

```python
# cdn_ops.py — ssl_check (lines 371-424)

# Step 1: Fetch certificate from server (10s timeout)
result = subprocess.run(
    ["openssl", "s_client", "-connect", f"{domain}:443",
     "-servername", domain, "-showcerts"],
    input="", capture_output=True, text=True, timeout=10,
)

# Step 2: Parse certificate details (5s timeout)
cert_result = subprocess.run(
    ["openssl", "x509", "-noout", "-dates", "-issuer"],
    input=result.stdout,   # pipe step 1 output as input
    capture_output=True, text=True, timeout=5,
)

# Parse: issuer= and notAfter= lines
for line in cert_result.stdout.splitlines():
    if line.startswith("notAfter="):
        expiry = line.split("=", 1)[1].strip()
    elif line.startswith("issuer="):
        issuer = line.split("=", 1)[1].strip()
```

Why two steps? `s_client` connects to the TLS endpoint and dumps the
raw certificate. `x509` then parses just the fields we need. The empty
`input=""` for step 1 is intentional — it prevents `s_client` from
blocking on stdin. Different timeouts (10s network vs 5s parsing)
reflect the different failure modes.

### 5. Provider-Aware SPF Record Generation

SPF records adapt based on the selected mail provider:

```python
# cdn_ops.py — generate_dns_records (lines 502-516)

if include_spf:
    spf_value = "v=spf1"
    if mail_provider == "google":
        spf_value += " include:_spf.google.com"
    elif mail_provider == "protonmail":
        spf_value += " include:_spf.protonmail.ch"
    spf_value += " -all"      # HARD fail, not ~all (soft fail)

    records.append({
        "type": "TXT", "name": "@",
        "value": spf_value, "ttl": 3600,
    })
```

Three possible SPF outputs depending on `mail_provider`:
- `"google"` → `v=spf1 include:_spf.google.com -all`
- `"protonmail"` → `v=spf1 include:_spf.protonmail.ch -all`
- `""` or unknown → `v=spf1 -all` (reject all, no provider authorized)

The `-all` hard fail is deliberate — it's the production-correct
setting. Soft fail (`~all`) would only be appropriate during migration.

### 6. Directory Skip Cascade — Shared Across All File Scans

A single `_SKIP_DIRS` frozenset protects all recursive scans:

```python
# cdn_ops.py — (lines 37-41)

_SKIP_DIRS = frozenset({
    ".git", ".venv", "venv", "node_modules", "__pycache__",
    ".terraform", "dist", "build", ".pages",
    "htmlcov", ".backup", "state",
})

# Used in 3 different scan loops:
# 1. _detect_cdn_provider → *.tf scanning
# 2. dns_cdn_status → *.zone / *.dns / db.* scanning
# 3. dns_cdn_status → *.pem / *.crt / *.cert / *.key scanning

for f in project_root.rglob(pattern):
    skip = False
    for part in f.relative_to(project_root).parts:
        if part in _SKIP_DIRS:
            skip = True
            break
    if not skip:
        # process file
```

12 directories × 3 scan loops = 36 potential skip checks. The
frozenset gives O(1) lookup per path component. The per-part check
catches nested skip dirs (e.g., `vendor/node_modules/foo.tf`).

### 7. Audit-Integrated DNS Generation

Record generation logs to the audit trail for operational visibility:

```python
# cdn_ops.py — generate_dns_records (lines 550-556)

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
```

Unlike detection and observation (which are read-only), generation is
a "change" operation — it produces configuration that will be applied
externally. The audit entry creates traceability: who generated what
records, for which domain, and when. The `record_count` in both the
audit detail and the response enables quick verification.

---

### Feature Coverage Summary

| Feature | Where | Complexity |
|---------|-------|-----------|
| Three-signal CDN detection cascade | `cdn_ops.py` `_detect_cdn_provider` | Config files → env vars → Terraform resources |
| Domain regex with 11-item false-positive filter | `cdn_ops.py` `_extract_domains_from_configs` | Broad capture → noise removal |
| BIND zone file with 30-char column alignment | `cdn_ops.py` `generate_dns_records` | `@` → FQDN expansion + `:<30` formatting |
| Two-step SSL certificate pipeline | `cdn_ops.py` `ssl_check` | s_client (10s) → x509 (5s) with stdout pipe |
| Provider-aware SPF with hard fail | `cdn_ops.py` `generate_dns_records` | google/protonmail/bare `-all` variants |
| Shared 12-dir skip cascade across 3 scan loops | `cdn_ops.py` `_SKIP_DIRS` | frozenset O(1) × per-path-component check |
| Audit-integrated generation for traceability | `cdn_ops.py` `generate_dns_records` | `_audit()` with domain + record count |

---

## Design Decisions

### Why a single-file domain instead of splitting detect/lookup/generate?

The DNS domain has 4 public functions and 2 private helpers totaling
565 lines. The functions share `_SKIP_DIRS` and the detection functions
share `_CDN_PROVIDERS`. Splitting into 3 files would mean each file
imports from the others for shared constants, creating cross-file
coupling for no benefit. The three phases (detect/observe/facilitate)
are separated by section headers within the file, which provides the
same navigability without the overhead.

### Why CLI-based DNS lookup instead of dnspython?

Using `dig` and `openssl` avoids adding a dependency for a single
domain. These tools are universally available on servers where this
control plane runs. The output parsing is straightforward — each query
returns one value per line. `dnspython` would add a dependency, custom
resolver configuration, and more complex error handling for the same
result.

### Why embed CDN provider specs in code instead of DataRegistry?

The CDN provider list is static (6 providers), rarely changes, and is
tightly coupled to the detection logic — each provider has different
detection signals (config files vs env keys vs Terraform resources).
Moving to DataRegistry would add indirection without benefit. If the
provider list grows beyond ~15, migration to DataRegistry would make
sense.

### Why generate BIND zone files alongside record dicts?

Zone files are the universal DNS configuration format — they can be
imported into any DNS provider (Cloudflare, Route53, GCP Cloud DNS)
or used directly with BIND. The structured record list serves
programmatic consumers (UI rendering, Terraform variable generation).
Both representations are generated in the same pass because they share
the same record computation.

### Why only google and protonmail mail presets?

These are the two providers the project actively uses. Adding presets
for Microsoft 365, Zoho, or Fastmail is trivial (add an `elif` branch
with the MX records) but they haven't been needed yet. The code
structure makes it easy to add providers without touching the rest
of the function.

### Why -all (hard fail) in SPF instead of ~all (soft fail)?

Hard fail (`-all`) is the recommended production setting — it tells
receiving mail servers to reject messages that don't pass SPF checks.
Soft fail (`~all`) is only appropriate during migration. Since this
tool generates records for new domains, hard fail is the correct default.
