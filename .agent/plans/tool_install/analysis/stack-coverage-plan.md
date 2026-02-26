# Stack Coverage Plan — 25+ Stacks, 100+ Tools, 1000+ Cases

## Objective

Expand TOOL_RECIPES to cover every major DevOps stack with all their
tools, dependencies, packages, configs, and services. Then simulate
every tool × every OS family and validate the resolver produces
correct, executable plans.

---

## Part 1: Stacks and Their Tools

### Currently covered (61 recipes, ~7 stacks)
- Python (ruff, mypy, pytest, black, pip-audit, safety, bandit)
- Node.js (eslint, prettier, docusaurus)
- Rust (cargo-audit, cargo-outdated)
- K8s/Cloud (kubectl, helm, terraform, skaffold, trivy, gh)
- System (git, curl, make, jq, docker, docker-compose, etc.)
- GPU (nvidia-driver, cuda-toolkit, rocm, pytorch, opencv)
- Data packs (trivy-db, geoip-db, wordlists, spacy-en, hf-model)

### Missing stacks and tools to add

| Stack | Tools to add | Count |
|-------|-------------|-------|
| **Go** | gopls, golangci-lint, delve, air, mockgen, protoc-gen-go | 6 |
| **Java** | maven, gradle, openjdk, spotless, checkstyle, pmd, jacoco | 7 |
| **.NET** | dotnet-sdk, dotnet-ef, nuget, omnisharp | 4 |
| **Ruby** | ruby, gem, bundler, rubocop, rails, rspec, solargraph | 7 |
| **PHP** | php, composer, phpstan, phpcs, phpunit, laravel-cli | 6 |
| **C/C++** | gcc, g++, clang, clang-tidy, clang-format, cmake, ninja, valgrind, gdb | 9 |
| **Zig** | zig | 1 |
| **Elixir** | elixir, erlang, mix, credo, dialyxir | 5 |
| **Scala** | sbt, scala, scalafmt, metals | 4 |
| **Dart/Flutter** | dart, flutter | 2 |
| **Cloud CLI** | aws-cli, gcloud, az-cli | 3 |
| **CI/CD tools** | act, gitlab-cli, circleci-cli, jenkins-cli | 4 |
| **Monitoring** | prometheus, grafana, alertmanager, node-exporter | 4 |
| **IaC** | ansible, pulumi, crossplane, cdk, cdktf | 5 |
| **Database CLI** | psql, mysql-client, mongosh, redis-cli, sqlite3 | 5 |
| **Security** | snyk, grype, gitleaks, tfsec, checkov, semgrep, sonarqube-cli | 7 |
| **Container** | buildx, podman, skopeo, dive, hadolint, dagger | 6 |
| **Networking** | nginx, caddy, mkcert, step-cli, wireguard-tools | 5 |
| **Observability** | otel-collector, jaeger, loki, vector | 4 |
| **K8s extended** | kustomize, k9s, stern, kubectx, kubens, argocd-cli, flux, istioctl | 8 |
| **Dev tools** | direnv, tmux, zoxide, fzf, ripgrep, bat, exa/eza, fd, starship | 9 |
| **Python extended** | poetry, pdm, hatch, uv, pyright, isort, flake8, tox, nox | 9 |
| **Node extended** | yarn, pnpm, bun, tsx, vitest, playwright, cypress, storybook | 8 |

**Total new: ~131 tools → recipes goes from 61 → ~192**

---

## Part 2: Simulated OS Profiles (6 families × variants)

Each simulated profile has: `package_manager.primary`, `distro.family`,
`distro.id`, `package_manager.snap_available`, `capabilities.has_sudo`.

| Profile ID | Family | PM | Snap? | Sudo? | Represents |
|------------|--------|-----|-------|-------|------------|
| `ubuntu-desktop`   | debian  | apt    | ✅ | ✅ | Ubuntu 22.04+ desktop |
| `ubuntu-server`    | debian  | apt    | ✅ | ✅ | Ubuntu server minimal |
| `debian-container` | debian  | apt    | ❌ | ✅ | Debian Docker image |
| `debian-rootless`  | debian  | apt    | ❌ | ❌ | Non-root container |
| `fedora`           | rhel    | dnf    | ❌ | ✅ | Fedora workstation |
| `rhel`             | rhel    | dnf    | ❌ | ✅ | RHEL 8/9 server |
| `centos-stream`    | rhel    | dnf    | ❌ | ✅ | CentOS Stream |
| `alpine`           | alpine  | apk    | ❌ | ✅ | Alpine 3.18+ |
| `alpine-rootless`  | alpine  | apk    | ❌ | ❌ | Alpine non-root |
| `arch`             | arch    | pacman | ❌ | ✅ | Arch Linux |
| `manjaro`          | arch    | pacman | ✅ | ✅ | Manjaro desktop |
| `opensuse`         | suse    | zypper | ❌ | ✅ | openSUSE Leap/Tumbleweed |
| `macos-intel`      | macos   | brew   | ❌ | ✅ | macOS x86_64 |
| `macos-arm`        | macos   | brew   | ❌ | ✅ | macOS aarch64 |

**14 profiles × ~192 tools = ~2,688 scenario combinations**

---

## Part 3: Test Framework

### File: `tests/test_tool_install_coverage.py`

```python
# For each tool × each profile:
# 1. resolve_install_plan(tool, profile)
# 2. Assert: no exception
# 3. Assert: returns either a valid plan OR already_installed OR a clear error
# 4. If plan: validate every step has type, label, command
# 5. If plan has packages: validate package names exist for this family
# 6. If plan needs sudo: validate profile has_sudo (else should warn)
# 7. Validate dependency chains are correct
```

### Assertions per scenario:
- No crash (KeyError, AttributeError, etc.)
- Steps in logical order (deps before tool, verify last)
- Package names match the OS family (no apt packages on dnf system)
- sudo requirements match capabilities
- post_env propagates correctly
- Source method generates source→build→install→cleanup

---

## Part 4: Execution Order

1. **Create test framework** with simulated profiles
2. **Add recipes in batches** by stack (Go, Java, Ruby, etc.)
3. **Run tests after each batch** — fix issues immediately
4. **Final run** — all ~2,688 scenarios pass

---

## Scope Boundary

This plan covers:
- Recipe data (what to install and how)
- Resolver logic (plan generation is correct)
- Simulated validation (no real installs)

This plan does NOT cover:
- Actually running installs (would need Docker matrix)
- Frontend/UI changes
- Real-world execution testing
