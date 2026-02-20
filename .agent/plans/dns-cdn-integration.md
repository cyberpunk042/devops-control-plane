# DNS & CDN Integration — Full Implementation Plan

> Created: 2026-02-18
> Source of truth: TECHNOLOGY SPEC + PROJECT SCOPE, not the current code.
> Status: Planning — approved architecture, ready to implement

---

## 1. Architecture — What DNS and CDN Actually Are

### DNS (`./dns/`)

DNS is domain name system configuration. In the real world, a project's DNS setup is:

| File | Format | Purpose |
|------|--------|---------|
| `dns/<domain>.zone` | BIND zone file (RFC 1035) | The standard: SOA, NS, A, AAAA, CNAME, MX, TXT records |
| `dns/records.json` | JSON | Machine-readable record list — consumed by external-dns, CI scripts, the control plane itself |
| `dns/README.md` | Markdown | What domain(s), where they're managed, how to update |

Standard BIND zone file:
```
$ORIGIN example.com.
$TTL 300

@   IN  SOA  ns1.example.com. admin.example.com. (
        2024021801  ; serial
        3600        ; refresh
        600         ; retry
        604800      ; expire
        300         ; minimum TTL
    )

@       IN  NS      ns1.example.com.
@       IN  NS      ns2.example.com.
@       IN  A       203.0.113.1
www     IN  CNAME   example.com.
api     IN  A       203.0.113.2
@       IN  MX      10 mail.example.com.
@       IN  TXT     "v=spf1 include:_spf.google.com -all"
_dmarc  IN  TXT     "v=DMARC1; p=quarantine; rua=mailto:dmarc@example.com; pct=100"
```

Machine-readable `records.json`:
```json
{
  "domain": "example.com",
  "provider": "cloudflare",
  "records": [
    { "type": "A",     "name": "@",      "value": "203.0.113.1", "ttl": 300 },
    { "type": "CNAME", "name": "www",    "value": "example.com", "ttl": 300 },
    { "type": "A",     "name": "api",    "value": "203.0.113.2", "ttl": 300 },
    { "type": "MX",    "name": "@",      "value": "10 mail.example.com", "ttl": 3600 },
    { "type": "TXT",   "name": "@",      "value": "v=spf1 include:_spf.google.com -all", "ttl": 3600 },
    { "type": "TXT",   "name": "_dmarc", "value": "v=DMARC1; p=quarantine; rua=mailto:dmarc@example.com; pct=100", "ttl": 3600 }
  ]
}
```

### CDN (`./cdn/`)

CDN is content delivery / edge configuration. The format is provider-specific because CDN providers are opinionated:

| Provider | Config file | Format |
|----------|-------------|--------|
| Cloudflare | `cdn/cloudflare.json` | Page rules, cache rules, SSL mode, minification |
| CloudFront | `cdn/cloudfront.json` | Distribution config: origins, behaviors, cache policies |
| Nginx | `cdn/nginx.conf` | Reverse proxy + caching + SSL termination |
| Caddy | `cdn/Caddyfile` | Automatic HTTPS, reverse proxy, file server |
| Traefik | `cdn/traefik.yml` | Routers, middlewares, TLS config |
| Generic | `cdn/config.json` | Minimal config: origin, cache TTL, SSL mode |
| All | `cdn/README.md` | CDN provider, setup instructions, purge commands |

### Cross-Domain References

Other tools reference DNS/CDN — they don't own it:

| Tool | References | How |
|------|-----------|-----|
| **Terraform** | `dns/records.json` for managed DNS records | Generates `terraform/dns.tf` that creates records in Route53/Cloud DNS/Cloudflare |
| **Terraform** | `cdn/` config for CDN distribution | Generates `terraform/cdn.tf` for CloudFront/Azure CDN resources |
| **K8s** | Domain from `dns/` for Ingress host rules | Generates `k8s/ingress.yaml` with TLS + cert-manager |
| **CI/CD** | Domain for deploy verification, SSL renewal | CI job step for DNS propagation check, cert renewal |
| **Pages** | Domain for custom domain hosting | `CNAME` file at project root |

---

## 2. Current State vs Required State

### What exists ✅
- `dns_cdn_ops.py` (562 lines) — detection + DNS lookup + SSL check + basic zone generation
- `routes_dns.py` (80 lines) — 4 API endpoints, blueprint registered
- `_devops_dns.html` (218 lines) — DevOps tab card with 3 action modals
- `probe_dns()` — checks CNAME + project.yml domain
- `integration_graph.json` — DNS in the graph, depends on Pages

### What's broken 🔴
- `wizard_ops.py` — DNS probe hardcoded to `detected: False, suggest: hidden` (NEVER reads `probe_dns()`)
- No integration card (`_INT_CARDS` doesn't include DNS)
- No setup wizard (toast placeholder)
- No `setup_dns()` backend
- No generation to `./dns/` or `./cdn/` directories
- `generate_dns_records()` only returns in-memory — doesn't write files
- No Terraform DNS/CDN catalogs
- No K8s Ingress/cert-manager generation
- No reverse proxy generation

### What's needed 🎯
- Write files to `./dns/` and `./cdn/` — standard formats
- Integration card in Integrations tab
- 5-step setup wizard with full context awareness
- Backend generators for DNS zone files, CDN configs, Terraform, K8s Ingress
- Cross-domain wiring (Terraform, K8s, Pages, CI/CD wizards)
- Documentation generated with configs (README.md in each dir)

---

## 3. Implementation Plan

### Phase 1 — Foundation + Probe Fix
> Wire what exists, make DNS visible

1. [ ] **Fix probe wiring** in `wizard_ops.py` — read `probe_dns()` + check for `./dns/` and `./cdn/` dirs
2. [ ] **Enrich `probe_dns()`** — detect `dns/` dir, `cdn/` dir, CDN providers (reuse `dns_cdn_ops` logic), count records
3. [ ] **Integration card** — `_integrations_dns.html`:
   - Detection: CDN providers, domains, zone files, SSL certs, dns/ and cdn/ dirs
   - Toolbar: Lookup, SSL Check, Generate, Setup Wizard
   - Cross-domain hints (Terraform, K8s, Pages)
4. [ ] **Register** in `_INT_CARDS`
5. [ ] **Verify**: DNS card visible in Integrations tab

### Phase 2 — Setup Wizard UI
> 5-step wizard, full context awareness

6. [ ] **New file**: `_integrations_setup_dns.html`
7. [ ] **Step 1 (Detect)**: `/dns/status` + cross-domain context (K8s? Terraform? Pages? Docker?)
8. [ ] **Step 2 (Domain & DNS)**:
   - Primary domain (pre-filled from detection / CNAME / project.yml)
   - Subdomains (add/remove: api.X, docs.X, cdn.X, ...)
   - DNS provider: Cloudflare / Route 53 / Cloud DNS / Azure DNS / Manual
   - Mail: None / Google Workspace / ProtonMail / Custom MX
   - Email security: SPF ✓ / DMARC ✓
9. [ ] **Step 3 (CDN & SSL)**:
   - CDN: None / Cloudflare (acts as CDN natively) / CloudFront / Cloud CDN / Azure CDN / Reverse Proxy (Nginx/Caddy)
   - SSL: Managed (provider) / Let's Encrypt / cert-manager (K8s) / Manual
   - If K8s detected: Ingress controller select (nginx / traefik / ALB)
10. [ ] **Step 4 (Traffic Routing)**: Context-adaptive:
    - K8s → Ingress host rules, TLS config, cert-manager toggle
    - Docker (no K8s) → Reverse proxy upstream config
    - Pages → Custom domain setup
    - Terraform only → DNS/CDN resources only
11. [ ] **Step 5 (Review & Generate)**: Summary, file list (`dns/`, `cdn/`), overwrite toggle
12. [ ] **Update dispatcher**: Wire in `_integrations_setup_dispatch.html`

### Phase 3 — Backend Generators
> Make the wizard actually write files to `./dns/` and `./cdn/`

13. [ ] **DNS generator**: `generate_dns_config(root, domain, records, provider, mail, ...)`
    - Writes `dns/<domain>.zone` — standard BIND zone file
    - Writes `dns/records.json` — machine-readable records
    - Writes `dns/README.md` — provider info, update instructions
14. [ ] **CDN generator**: `generate_cdn_config(root, provider, domain, ssl, ...)`
    - Writes provider-specific config to `cdn/`
    - Cloudflare → `cdn/cloudflare.json`
    - CloudFront → `cdn/cloudfront.json`
    - Nginx → `cdn/nginx.conf`
    - Caddy → `cdn/Caddyfile`
    - Writes `cdn/README.md` — CDN provider, purge commands, cache rules
15. [ ] **Backend**: `setup_dns(root, data)` in `wizard_setup.py`
    - Routes to DNS generator + CDN generator
    - Conditionally generates Terraform resources, K8s manifests, proxy configs
16. [ ] **Register** in `_SETUP_ACTIONS`

### Phase 4 — Terraform + K8s DNS/CDN Resources
> Cross-domain generators — Terraform resources and K8s manifests

17. [ ] **Data catalog**: `terraform_dns.json` — per-provider HCL templates:
    - AWS: `aws_route53_zone`, `aws_route53_record`, `aws_cloudfront_distribution`, `aws_acm_certificate`
    - Google: `google_dns_managed_zone`, `google_dns_record_set`, `google_compute_managed_ssl_certificate`
    - Azure: `azurerm_dns_zone`, `azurerm_dns_a_record`, `azurerm_cdn_profile`, `azurerm_cdn_endpoint`
    - Cloudflare: `cloudflare_zone`, `cloudflare_record`
18. [ ] **Data catalog**: `k8s_ingress.json` — Ingress controller configs (nginx, traefik, ALB)
19. [ ] **Generator**: `generate_terraform_dns()` — writes `terraform/dns.tf`, `terraform/cdn.tf`, `terraform/ssl.tf`
20. [ ] **Generator**: K8s Ingress + cert-manager manifests → `k8s/ingress.yaml`, `k8s/cert-manager/`

### Phase 5 — Cross-Domain Wiring + Polish
> Connect DNS/CDN to other wizards

21. [ ] **Terraform wizard Step 3**: Add DNS Zone, CDN Distribution, SSL Certificate as resource options
22. [ ] **K8s wizard infrastructure step**: Add Ingress + cert-manager alongside Skaffold/Helm
23. [ ] **Pages**: Custom domain field → CNAME + DNS record generation
24. [ ] **CI/CD**: SSL renewal job, DNS propagation check step
25. [ ] **Enhance detection**: Parse existing nginx/caddy/traefik configs in `cdn/`
26. [ ] **Update audit plan**

---

## 4. Output Directory Structure

After wizard completes, the project should have:

```
project-root/
├── dns/
│   ├── example.com.zone          # Standard BIND zone file
│   ├── records.json              # Machine-readable DNS records
│   └── README.md                 # Domain info, provider, how to update
├── cdn/
│   ├── cloudflare.json           # or cloudfront.json, nginx.conf, Caddyfile
│   ├── config.json               # Generic CDN config (origin, cache, SSL)
│   └── README.md                 # CDN provider, purge commands, cache rules
├── terraform/                    # (if Terraform integration active)
│   ├── dns.tf                    # DNS zone + record resources
│   ├── cdn.tf                    # CDN distribution resources
│   └── ssl.tf                    # Certificate resources
├── k8s/                          # (if K8s integration active)
│   ├── ingress.yaml              # Ingress with TLS + host rules
│   └── cert-manager/
│       ├── cluster-issuer.yaml   # Let's Encrypt issuer
│       └── certificate.yaml      # TLS certificate CRD
└── CNAME                         # (if Pages with custom domain)
```

---

## 5. Immediate Scope (Phase 1 + Phase 2)

Following the Terraform wizard pattern: build the UI wizard first, stub backend generators.

**What we code now:**
- Fix probe wiring (trivial)
- Integration card (reuse DevOps card patterns)
- 5-step wizard (full UI, context-aware steps)
- Wire onComplete to send payload to `/wizard/setup`

**What we defer:**
- Backend generators (`setup_dns()`, file writing) → Phase 3
- Terraform/K8s catalogs and generators → Phase 4
- Cross-domain wiring to other wizards → Phase 5

This matches exactly how we did Docker, K8s, CI/CD, and Terraform.
