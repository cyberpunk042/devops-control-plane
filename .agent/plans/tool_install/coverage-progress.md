# Tool Coverage Progress Tracker

> **Last updated:** 2026-02-26
> **Total recipes:** 296 | **Audited:** 5 | **Unaudited:** 291
> **Missing from EXPECTED_TOOLS:** 7 (java, nvm, pipx, python3, rustup, tar, unzip)

## How to use this file

- Process tools **in order**, top to bottom
- Mark status after completing `/tool-coverage-audit` workflow for each tool
- Status legend:
  - `⬜` — Not started
  - `🔄` — In progress
  - `✅` — Recipe complete (cli + install methods + needs_sudo + verify)
  - `⬛` — Non-installable (config/data, marked `_not_installable`)
  - `🔲` — Skipped (deferred or not applicable)

---

## Group 1: Foundational System Tools (category: `?`)

These have NO category and are the most fundamental. Everything else depends on them.
Process these FIRST — they unblock all other stacks.

| # | Tool ID | Status | CLI | Notes |
|---|---------|--------|-----|-------|
| 1 | `curl` | ⬜ | | System utility, download dep for most `_default` methods |
| 2 | `git` | ⬜ | | VCS, dep for source builds and many installers |
| 3 | `make` | ⬜ | | Build tool, dep for source builds |
| 4 | `jq` | ⬜ | | JSON processor, used in many install scripts |
| 5 | `gzip` | ⬜ | | Compression, dep for tar.gz extraction |
| 6 | `openssl` | ⬜ | | Crypto library, runtime dep for many tools |
| 7 | `rsync` | ⬜ | | File sync, deploy dep |
| 8 | `dig` | ⬜ | | DNS lookup, bind-utils |
| 9 | `expect` | ⬜ | | Terminal automation |
| 10 | `pip` | ⬜ | | Python package installer |
| 11 | `python` | ✅ | python3 | 589/589 (100%), 7 Layer 3 handlers |
| 12 | `build-essential` | ⬜ | gcc | Has partial data |

### Missing expected tools (need new recipes)

| # | Tool ID | Status | Notes |
|---|---------|--------|-------|
| 13 | `tar` | ⬜ | Archive extraction, fundamental dep |
| 14 | `unzip` | ⬜ | ZIP extraction, dep for binary downloads |
| 15 | `python3` | ⬜ | Alias/recipe for python3 specifically |
| 16 | `pipx` | ⬜ | Isolated Python tool installer |
| 17 | `rustup` | ⬜ | Rust toolchain manager |
| 18 | `nvm` | ⬜ | Node version manager |
| 19 | `java` | ⬜ | JDK (alias for openjdk?) |

---

## Group 2: Language Runtimes & Package Managers (category: `?`)

These unlock all language-specific stacks.

| # | Tool ID | Status | CLI | Notes |
|---|---------|--------|-----|-------|
| 20 | `node` | ✅ | node | 551/551 (100%), 4 Layer 3 handlers |
| 21 | `npm` | ⬜ | | Node package manager |
| 22 | `npx` | ⬜ | | Node package executor |
| 23 | `go` | ✅ | | Go language runtime |
| 24 | `cargo` | ✅ | | Rust package manager |
| 25 | `rustc` | ⬜ | | Rust compiler |
| 26 | `docker` | ✅ | | Container runtime |
| 27 | `docker-compose` | ✅ | | Container orchestration |

---

## Group 3: Core DevOps (category: `?`)

| # | Tool ID | Status | CLI | Notes |
|---|---------|--------|-----|-------|
| 28 | `kubectl` | ⬜ | | K8s CLI |
| 29 | `helm` | ⬜ | | K8s package manager |
| 30 | `terraform` | ⬜ | | IaC |
| 31 | `skaffold` | ⬜ | | K8s dev workflow |
| 32 | `trivy` | ⬜ | | Security scanner |
| 33 | `gh` | ⬜ | | GitHub CLI |
| 34 | `hugo` | ⬜ | | Static site generator |

---

## Group 4: Terminal Accessories (category: `?`)

| # | Tool ID | Status | CLI | Notes |
|---|---------|--------|-----|-------|
| 35 | `gnome-terminal` | ⬜ | | Desktop terminal |
| 36 | `kitty` | ⬜ | | GPU terminal |
| 37 | `konsole` | ⬜ | | KDE terminal |
| 38 | `xfce4-terminal` | ⬜ | | XFCE terminal |
| 39 | `xterm` | ⬜ | | X11 terminal |
| 40 | `ffmpeg` | ⬜ | | Media processing |

---

## Group 5: Python Stack (categories: `python`, `?`)

| # | Tool ID | Status | CLI | Category | Notes |
|---|---------|--------|-----|----------|-------|
| 41 | `ruff` | ⬜ | | ? | Python linter |
| 42 | `mypy` | ⬜ | | ? | Type checker |
| 43 | `pytest` | ⬜ | | ? | Test framework |
| 44 | `black` | ⬜ | | ? | Formatter |
| 45 | `bandit` | ⬜ | | ? | Security linter |
| 46 | `pip-audit` | ⬜ | | ? | Audit tool |
| 47 | `safety` | ⬜ | | ? | Vulnerability scanner |
| 48 | `poetry` | ⬜ | | python | Dependency management |
| 49 | `pdm` | ⬜ | | python | Package manager |
| 50 | `hatch` | ⬜ | | python | Build backend |
| 51 | `uv` | ⬜ | | python | Fast Python installer |
| 52 | `pyright` | ⬜ | | python | Type checker |
| 53 | `isort` | ⬜ | | python | Import sorter |
| 54 | `flake8` | ⬜ | | python | Linter |
| 55 | `tox` | ⬜ | | python | Test runner |
| 56 | `nox` | ⬜ | | python | Test runner |

---

## Group 6: Node.js Stack (categories: `node`, `?`, `formatting`)

| # | Tool ID | Status | CLI | Category | Notes |
|---|---------|--------|-----|----------|-------|
| 57 | `eslint` | ⬜ | | ? | JS linter |
| 58 | `prettier` | ⬜ | | ? | Formatter |
| 59 | `yarn` | ⬜ | | node | Alt pkg manager |
| 60 | `pnpm` | ⬜ | | node | Alt pkg manager |
| 61 | `bun` | ⬜ | | node | JS runtime |
| 62 | `tsx` | ⬜ | | node | TypeScript runner |
| 63 | `vitest` | ⬜ | | node | Test framework |

---

## Group 7: System Utilities (category: `system`)

| # | Tool ID | Status | CLI | Notes |
|---|---------|--------|-----|-------|
| 64 | `htop` | ⬜ | | Process viewer |
| 65 | `btop` | ⬜ | | Resource monitor |
| 66 | `tree` | ⬜ | | Directory tree |
| 67 | `jc` | ⬜ | | JSON CLI parser |
| 68 | `yq` | ⬜ | | YAML processor |
| 69 | `strace` | ⬜ | | Syscall tracer |
| 70 | `lsof` | ⬜ | | File descriptor lister |
| 71 | `ncdu` | ⬜ | | Disk usage |

---

## Group 8: Dev Tools (category: `devtools`)

| # | Tool ID | Status | CLI | Notes |
|---|---------|--------|-----|-------|
| 72 | `bat` | ⬜ | | Cat replacement |
| 73 | `eza` | ⬜ | | Ls replacement |
| 74 | `fzf` | ⬜ | | Fuzzy finder |
| 75 | `direnv` | ⬜ | | Env per directory |
| 76 | `tmux` | ⬜ | | Terminal multiplexer |
| 77 | `zoxide` | ⬜ | | Smart cd |
| 78 | `starship` | ⬜ | | Prompt |
| 79 | `fd` | ⬜ | fd | Has partial data |
| 80 | `ripgrep` | ⬜ | rg | Has partial data |

---

## Group 9: Shell (category: `shell`)

| # | Tool ID | Status | CLI | Notes |
|---|---------|--------|-----|-------|
| 81 | `zsh` | ⬜ | | Shell |
| 82 | `fish` | ⬜ | | Shell |
| 83 | `shellcheck` | ⬜ | | Shell linter |
| 84 | `shfmt` | ⬜ | | Shell formatter |
| 85 | `bats` | ⬜ | | Shell test framework |
| 86 | `nushell` | ⬜ | nu | Has partial data |

---

## Group 10: Git Tools (category: `git`)

| # | Tool ID | Status | CLI | Notes |
|---|---------|--------|-----|-------|
| 87 | `delta` | ⬜ | | Git diff pager |
| 88 | `lazygit` | ⬜ | | Git TUI |
| 89 | `pre-commit` | ⬜ | | Git hooks |
| 90 | `git-lfs` | ⬜ | git | Has partial data |

---

## Group 11: Network & Proxy (categories: `network`, `proxy`, `dns`)

| # | Tool ID | Status | CLI | Notes |
|---|---------|--------|-----|-------|
| 91 | `wget` | ⬜ | | Download tool |
| 92 | `socat` | ⬜ | | Socket relay |
| 93 | `nmap` | ⬜ | | Port scanner |
| 94 | `mkcert` | ⬜ | | Local CA |
| 95 | `caddy` | ⬜ | | Web server |
| 96 | `nginx` | ⬜ | | Web server |
| 97 | `haproxy` | ⬜ | | Load balancer |
| 98 | `traefik` | ⬜ | | Reverse proxy |
| 99 | `envoy` | ⬜ | | Service proxy |
| 100 | `dnsx` | ⬜ | | DNS toolkit |
| 101 | `dog` | ⬜ | | DNS client |
| 102 | `httpie` | ⬜ | http | Has partial data |
| 103 | `wireguard-tools` | ⬜ | wg | Has partial data |
| 104 | `bind-utils` | ⬜ | nslookup | Has partial data |

---

## Group 12: C/C++ (category: `cpp`)

| # | Tool ID | Status | CLI | Notes |
|---|---------|--------|-----|-------|
| 105 | `gcc` | ⬜ | | C compiler |
| 106 | `clang` | ⬜ | | C/C++ compiler |
| 107 | `cmake` | ⬜ | | Build system |
| 108 | `gdb` | ⬜ | | Debugger |
| 109 | `valgrind` | ⬜ | | Memory checker |
| 110 | `ninja` | ⬜ | ninja | Has partial data |

---

## Group 13: Go Stack (category: `go`)

| # | Tool ID | Status | CLI | Notes |
|---|---------|--------|-----|-------|
| 111 | `golangci-lint` | ⬜ | | Linter |
| 112 | `gopls` | ⬜ | | Language server |
| 113 | `air` | ⬜ | | Live reload |
| 114 | `mockgen` | ⬜ | | Mock generator |
| 115 | `protoc-gen-go` | ⬜ | | Protobuf codegen |
| 116 | `delve` | ⬜ | dlv | Has partial data |

---

## Group 14: Rust Stack (category: `rust`)

| # | Tool ID | Status | CLI | Notes |
|---|---------|--------|-----|-------|
| 117 | `cargo-audit` | ⬜ | | ? (needs recategorize) |
| 118 | `cargo-outdated` | ⬜ | | ? (needs recategorize) |
| 119 | `cargo-edit` | ⬜ | | Cargo extensions |
| 120 | `cargo-nextest` | ⬜ | | Test runner |
| 121 | `cargo-watch` | ⬜ | | File watcher |
| 122 | `cross` | ⬜ | | Cross-compilation |
| 123 | `sccache` | ⬜ | | Build cache |

---

## Group 15: K8s Extended (category: `k8s`)

| # | Tool ID | Status | CLI | Notes |
|---|---------|--------|-----|-------|
| 124 | `kustomize` | ⬜ | | K8s customization |
| 125 | `k9s` | ⬜ | | K8s TUI |
| 126 | `stern` | ⬜ | | K8s log tailing |
| 127 | `kubectx` | ⬜ | | Context switcher |
| 128 | `flux` | ⬜ | | GitOps |
| 129 | `istioctl` | ⬜ | | Service mesh |
| 130 | `helmfile` | ⬜ | | Helm orchestration |
| 131 | `argocd-cli` | ⬜ | argocd | Has partial data |

---

## Group 16: Container (category: `container`)

| # | Tool ID | Status | CLI | Notes |
|---|---------|--------|-----|-------|
| 132 | `podman` | ⬜ | | Container runtime |
| 133 | `skopeo` | ⬜ | | Image operations |
| 134 | `dive` | ⬜ | | Image explorer |
| 135 | `hadolint` | ⬜ | | Dockerfile linter |
| 136 | `dagger` | ⬜ | | CI engine |
| 137 | `buildx` | ⬜ | docker | Has partial data |

---

## Group 17: Security (category: `security`)

| # | Tool ID | Status | CLI | Notes |
|---|---------|--------|-----|-------|
| 138 | `snyk` | ⬜ | | Vulnerability scanner |
| 139 | `grype` | ⬜ | | Image scanner |
| 140 | `gitleaks` | ⬜ | | Secret detection |
| 141 | `tfsec` | ⬜ | | Terraform scanner |
| 142 | `checkov` | ⬜ | | IaC scanner |
| 143 | `semgrep` | ⬜ | | Static analysis |
| 144 | `detect-secrets` | ⬜ | | Secret detection |

---

## Group 18: Cloud CLIs (category: `cloud`)

| # | Tool ID | Status | CLI | Notes |
|---|---------|--------|-----|-------|
| 145 | `gcloud` | ⬜ | | Google Cloud |
| 146 | `doctl` | ⬜ | | DigitalOcean |
| 147 | `vercel` | ⬜ | | Vercel CLI |
| 148 | `wrangler` | ⬜ | | Cloudflare Workers |
| 149 | `linode-cli` | ⬜ | | Linode |
| 150 | `aws-cli` | ⬜ | aws | Has partial data |
| 151 | `az-cli` | ⬜ | az | Has partial data |
| 152 | `flyctl` | ⬜ | fly | Has partial data |
| 153 | `netlify-cli` | ⬜ | netlify | Has partial data |

---

## Group 19: IaC & HashiCorp (categories: `iac`, `hashicorp`)

| # | Tool ID | Status | CLI | Notes |
|---|---------|--------|-----|-------|
| 154 | `ansible` | ⬜ | | Configuration management |
| 155 | `pulumi` | ⬜ | | IaC |
| 156 | `cdktf` | ⬜ | | Terraform CDK |
| 157 | `vault` | ⬜ | | Secrets management |
| 158 | `consul` | ⬜ | | Service discovery |
| 159 | `boundary` | ⬜ | | Access management |
| 160 | `nomad` | ⬜ | | Orchestrator |

---

## Group 20: Database CLIs (category: `database`)

| # | Tool ID | Status | CLI | Notes |
|---|---------|--------|-----|-------|
| 161 | `psql` | ⬜ | | PostgreSQL |
| 162 | `mongosh` | ⬜ | | MongoDB |
| 163 | `sqlite3` | ⬜ | | SQLite |
| 164 | `mysql-client` | ⬜ | mysql | Has partial data |
| 165 | `redis-cli` | ⬜ | redis-cli | Has partial data |

---

## Group 21: Monitoring & Observability (categories: `monitoring`, `logging`)

| # | Tool ID | Status | CLI | Notes |
|---|---------|--------|-----|-------|
| 166 | `prometheus` | ⬜ | | Metrics server |
| 167 | `promtail` | ⬜ | | Log shipper |
| 168 | `vegeta` | ⬜ | | Load testing |
| 169 | `vector` | ⬜ | | Log pipeline |
| 170 | `grafana-cli` | ⬜ | grafana-cli | Has partial data |
| 171 | `jaeger` | ⬜ | jaeger-all-in-one | Has partial data |
| 172 | `loki` | ⬜ | loki | Has partial data |
| 173 | `fluentbit` | ⬜ | fluent-bit | Has partial data |
| 174 | `stern-log` | ⬜ | stern | Has partial data |

---

## Group 22: Remaining Stacks (various categories)

### Compression
| # | Tool ID | Status | Notes |
|---|---------|--------|-------|
| 175 | `xz` | ⬜ | |
| 176 | `zstd` | ⬜ | |
| 177 | `lz4` | ⬜ | |
| 178 | `pigz` | ⬜ | |
| 179 | `p7zip` | ⬜ | Has partial data |

### Formatting
| # | Tool ID | Status | Notes |
|---|---------|--------|-------|
| 180 | `yamllint` | ⬜ | |
| 181 | `jsonlint` | ⬜ | |
| 182 | `markdownlint` | ⬜ | |
| 183 | `taplo` | ⬜ | |
| 184 | `editorconfig-checker` | ⬜ | Has partial data |

### Ruby
| # | Tool ID | Status | Notes |
|---|---------|--------|-------|
| 185 | `ruby` | ⬜ | |
| 186 | `rubocop` | ⬜ | |
| 187 | `bundler` | ⬜ | Has partial data |

### PHP
| # | Tool ID | Status | Notes |
|---|---------|--------|-------|
| 188 | `php` | ⬜ | |
| 189 | `composer` | ⬜ | |
| 190 | `phpstan` | ⬜ | |
| 191 | `phpunit` | ⬜ | |

### Java/Kotlin/Scala
| # | Tool ID | Status | Notes |
|---|---------|--------|-------|
| 192 | `gradle` | ⬜ | |
| 193 | `scala` | ⬜ | |
| 194 | `sbt` | ⬜ | |
| 195 | `ktlint` | ⬜ | |
| 196 | `maven` | ⬜ | Has partial data |
| 197 | `openjdk` | ⬜ | Has partial data |
| 198 | `kotlin` | ⬜ | Has partial data |
| 199 | `ammonite` | ⬜ | Has partial data |

### Elixir
| # | Tool ID | Status | Notes |
|---|---------|--------|-------|
| 200 | `elixir` | ⬜ | |
| 201 | `mix` | ⬜ | |
| 202 | `erlang` | ⬜ | Has partial data |

### Haskell
| # | Tool ID | Status | Notes |
|---|---------|--------|-------|
| 203 | `ghc` | ⬜ | |
| 204 | `stack` | ⬜ | |
| 205 | `cabal` | ⬜ | Has partial data |

### OCaml/Lua/Zig
| # | Tool ID | Status | Notes |
|---|---------|--------|-------|
| 206 | `ocaml` | ⬜ | |
| 207 | `opam` | ⬜ | |
| 208 | `dune` | ⬜ | |
| 209 | `lua` | ⬜ | |
| 210 | `luarocks` | ⬜ | |
| 211 | `stylua` | ⬜ | |
| 212 | `zig` | ⬜ | |
| 213 | `zls` | ⬜ | |

### Editors
| # | Tool ID | Status | Notes |
|---|---------|--------|-------|
| 214 | `code-server` | ⬜ | |
| 215 | `micro` | ⬜ | |
| 216 | `helix` | ⬜ | Has partial data |
| 217 | `neovim` | ⬜ | Has partial data |

### Media
| # | Tool ID | Status | Notes |
|---|---------|--------|-------|
| 218 | `gifsicle` | ⬜ | |
| 219 | `jpegoptim` | ⬜ | |
| 220 | `optipng` | ⬜ | |
| 221 | `svgo` | ⬜ | |
| 222 | `imagemagick` | ⬜ | Has partial data |

### Protobuf
| # | Tool ID | Status | Notes |
|---|---------|--------|-------|
| 223 | `protoc` | ⬜ | |
| 224 | `grpcurl` | ⬜ | |
| 225 | `buf` | ⬜ | |

### Profiling
| # | Tool ID | Status | Notes |
|---|---------|--------|-------|
| 226 | `hyperfine` | ⬜ | |
| 227 | `perf` | ⬜ | |
| 228 | `py-spy` | ⬜ | |
| 229 | `flamegraph` | ⬜ | Has partial data |

### Process Managers
| # | Tool ID | Status | Notes |
|---|---------|--------|-------|
| 230 | `pm2` | ⬜ | |
| 231 | `s6` | ⬜ | Has partial data |
| 232 | `supervisor` | ⬜ | Has partial data |

### Terminal
| # | Tool ID | Status | Notes |
|---|---------|--------|-------|
| 233 | `screen` | ⬜ | |
| 234 | `mosh` | ⬜ | |
| 235 | `zellij` | ⬜ | |

### Task Runners
| # | Tool ID | Status | Notes |
|---|---------|--------|-------|
| 236 | `just` | ⬜ | |
| 237 | `task` | ⬜ | |
| 238 | `earthly` | ⬜ | |
| 239 | `mage` | ⬜ | |

### Testing
| # | Tool ID | Status | Notes |
|---|---------|--------|-------|
| 240 | `k6` | ⬜ | |
| 241 | `artillery` | ⬜ | |
| 242 | `locust` | ⬜ | |
| 243 | `cypress` | ⬜ | |

### WASM
| # | Tool ID | Status | Notes |
|---|---------|--------|-------|
| 244 | `wasm-pack` | ⬜ | |
| 245 | `wasmer` | ⬜ | |
| 246 | `wasmtime` | ⬜ | |

### Crypto
| # | Tool ID | Status | Notes |
|---|---------|--------|-------|
| 247 | `age` | ⬜ | |
| 248 | `certbot` | ⬜ | |
| 249 | `sops` | ⬜ | |
| 250 | `step-cli` | ⬜ | Has partial data |

### Backup
| # | Tool ID | Status | Notes |
|---|---------|--------|-------|
| 251 | `restic` | ⬜ | |
| 252 | `rclone` | ⬜ | |
| 253 | `borgbackup` | ⬜ | Has partial data |

### Virtualization
| # | Tool ID | Status | Notes |
|---|---------|--------|-------|
| 254 | `vagrant` | ⬜ | |
| 255 | `packer` | ⬜ | |
| 256 | `libvirt` | ⬜ | Has partial data |
| 257 | `qemu` | ⬜ | Has partial data |

### Docs
| # | Tool ID | Status | Notes |
|---|---------|--------|-------|
| 258 | `asciidoctor` | ⬜ | |
| 259 | `mdbook` | ⬜ | |
| 260 | `sphinx` | ⬜ | Has partial data |

### Service Discovery
| # | Tool ID | Status | Notes |
|---|---------|--------|-------|
| 261 | `linkerd` | ⬜ | |
| 262 | `etcd` | ⬜ | Has partial data |

### Embedded
| # | Tool ID | Status | Notes |
|---|---------|--------|-------|
| 263 | `openocd` | ⬜ | |
| 264 | `arm-gcc` | ⬜ | Has partial data |
| 265 | `esptool` | ⬜ | Has partial data |
| 266 | `platformio` | ⬜ | Has partial data |

### GPU
| # | Tool ID | Status | Notes |
|---|---------|--------|-------|
| 267 | `cuda-toolkit` | ⬜ | Has partial data |
| 268 | `nvidia-driver` | ⬜ | Has partial data |
| 269 | `rocm` | ⬜ | Has partial data |

---

## Group 23: Non-installable (config/data)

These need `_not_installable: True` set, not full recipes.

| # | Tool ID | Status | Category | Notes |
|---|---------|--------|----------|-------|
| 270 | `docker-daemon-config` | ⬜ | config | Mark as non-installable |
| 271 | `journald-config` | ⬜ | config | Mark as non-installable |
| 272 | `logrotate-docker` | ⬜ | config | Mark as non-installable |
| 273 | `nginx-vhost` | ⬜ | config | Mark as non-installable |
| 274 | `vfio-passthrough` | ⬜ | gpu | Mark as non-installable |
| 275 | `geoip-db` | ⬜ | data_pack | Mark as non-installable |
| 276 | `hf-model` | ⬜ | data_pack | Mark as non-installable |
| 277 | `spacy-en` | ⬜ | data_pack | Mark as non-installable |
| 278 | `trivy-db` | ⬜ | data_pack | Mark as non-installable |
| 279 | `wordlists` | ⬜ | data_pack | Mark as non-installable |

---

## Progress Summary

| Group | Total | ✅ Done | ⬜ Remaining |
|-------|-------|---------|-------------|
| 1. Foundational | 12 | 0 | 12 |
| 1b. Expected missing | 7 | 0 | 7 |
| 2. Language runtimes | 8 | 0 | 8 |
| 3. Core DevOps | 7 | 0 | 7 |
| 4. Terminal accessories | 6 | 0 | 6 |
| 5. Python | 16 | 0 | 16 |
| 6. Node.js | 7 | 0 | 7 |
| 7. System utilities | 8 | 0 | 8 |
| 8. Dev tools | 9 | 0 | 9 |
| 9. Shell | 6 | 0 | 6 |
| 10. Git tools | 4 | 0 | 4 |
| 11-22. Remaining | ~110 | 0 | ~110 |
| 23. Non-installable | 10 | 0 | 10 |
| **TOTAL** | **~210** | **0** | **~210** |
