# CLI

> **56 files. 5,792 lines. 19 command groups. Thin wrappers over core services.**
>
> The CLI layer provides the `controlplane` command-line interface using
> [Click](https://click.palletsprojects.com/). Every CLI command is a thin
> wrapper — it resolves the project root, calls a core service function, and
> formats the result for the terminal. Business logic lives in `core/services/`,
> never in CLI code.

---

## How It Works

The CLI is a Click `@group` tree. The root group is defined in `src/main.py`,
and 19 domain sub-groups are registered via `cli.add_command()`. Each domain
is a self-contained package inside `src/ui/cli/` with its own Click group and
sub-commands.

```
┌──────────────────────────────────────────────────────────────────────┐
│                       src/main.py                                    │
│                                                                      │
│  @click.group()                                                      │
│  def cli():                                                          │
│      ...                                                             │
│                                                                      │
│  cli.add_command(vault)       ← from src.ui.cli.vault                │
│  cli.add_command(content)     ← from src.ui.cli.content              │
│  cli.add_command(pages)       ← from src.ui.cli.pages                │
│  cli.add_command(git)         ← from src.ui.cli.git                  │
│  cli.add_command(backup)      ← from src.ui.cli.backup               │
│  cli.add_command(secrets)     ← from src.ui.cli.secrets              │
│  cli.add_command(docker)      ← from src.ui.cli.docker               │
│  cli.add_command(ci)          ← from src.ui.cli.ci                   │
│  cli.add_command(packages)    ← from src.ui.cli.packages             │
│  cli.add_command(infra)       ← from src.ui.cli.infra                │
│  cli.add_command(quality)     ← from src.ui.cli.quality              │
│  cli.add_command(metrics)     ← from src.ui.cli.metrics              │
│  cli.add_command(security)    ← from src.ui.cli.security             │
│  cli.add_command(docs)        ← from src.ui.cli.docs                 │
│  cli.add_command(testing)     ← from src.ui.cli.testing              │
│  cli.add_command(k8s)         ← from src.ui.cli.k8s                  │
│  cli.add_command(terraform)   ← from src.ui.cli.terraform            │
│  cli.add_command(dns)         ← from src.ui.cli.dns                  │
│  cli.add_command(audit)       ← from src.ui.cli.audit                │
└──────────────────────────────────────────────────────────────────────┘
```

### The Thin Wrapper Pattern

Every CLI command follows the same structural pattern:

```
┌──────────────────────────────────────────────────────────────────┐
│  @domain.command("verb")                                         │
│  @click.option(...)                                              │
│  @click.pass_context                                             │
│  def verb(ctx, ...):                                             │
│      1. root = _resolve_project_root(ctx)                        │
│      2. result = core_service_function(root, ...)    ← delegate  │
│      3. click.echo(formatted_output)                 ← display   │
│                                                                  │
│  ┌─────────────────────────────────────────────────────┐         │
│  │ RULE: No business logic in CLI commands.            │         │
│  │       CLI only resolves args → calls core → prints. │         │
│  └─────────────────────────────────────────────────────┘         │
└──────────────────────────────────────────────────────────────────┘
```

**Example — `controlplane docker containers`:**

```python
@docker.command("containers")
@click.option("--compose", is_flag=True, help="Show compose services")
@click.pass_context
def containers(ctx, compose):
    root = _resolve_project_root(ctx)
    from src.core.services.docker_ops import docker_containers
    result = docker_containers(root, compose=compose)
    # Format and print result
    click.echo(result)
```

### Domain Organization Pattern

Larger domains split their commands across files following a consistent
internal structure:

```
src/ui/cli/<domain>/
├── __init__.py     @click.group() definition + helper (_resolve_project_root)
├── detect.py       status / detection commands
├── observe.py      read-only observation commands
├── actions.py      mutating action commands
└── generate.py     @click.group("generate") → file generation sub-commands
```

Not all domains need all four files. Small domains (backup, metrics) put
everything in `__init__.py`. The split happens only when the command count
makes a single file unwieldy.

### Project Root Resolution

Every domain uses the same helper to find the project root:

```python
def _resolve_project_root(ctx: click.Context) -> Path:
    config_path = ctx.obj.get("config_path")
    if config_path is None:
        from src.core.config.loader import find_project_file
        config_path = find_project_file()
    return config_path.parent.resolve() if config_path else Path.cwd()
```

This reads `config_path` from the Click context (set by the root group in
`main.py`) or auto-discovers it by searching for the project config file.

### Global Options

The root `cli` group in `main.py` accepts:

| Option | Short | Purpose |
|--------|-------|---------|
| `--verbose` | `-v` | Enable verbose output |
| `--quiet` | `-q` | Suppress non-essential output |
| `--debug` | | Enable debug logging (very verbose) |
| `--config` | | Path to project config file |
| `--version` | | Show version and exit |

These are stored in `ctx.obj` and available to all sub-commands.

---

## File Map

```
src/ui/cli/
├── __init__.py                         Module docstring (1 line)
│
├── audit/                              Code quality audit commands
│   ├── __init__.py                     @click.group + scan command (34 lines)
│   ├── install.py                      Tool install commands (184 lines)
│   ├── plans.py                        Remediation plan commands (39 lines)
│   └── resume.py                       Resume interrupted scans (120 lines)
│
├── backup/                             Backup & restore commands
│   └── __init__.py                     All commands in one file (196 lines)
│
├── ci/                                 CI/CD pipeline commands
│   └── __init__.py                     All commands in one file (236 lines)
│
├── content/                            Content management commands
│   ├── __init__.py                     @click.group definition (35 lines)
│   ├── crypto.py                       Encrypt/decrypt/metadata/gallery (102 lines)
│   ├── optimize.py                     folders/optimize commands (86 lines)
│   └── release.py                      Release artifact management (118 lines)
│
├── dns/                                DNS & CDN commands
│   └── __init__.py                     All commands in one file (229 lines)
│
├── docker/                             Docker & Compose commands
│   ├── __init__.py                     @click.group + helpers (35 lines)
│   ├── detect.py                       Docker status/detection (60 lines)
│   ├── observe.py                      containers/images/ps/logs/stats (154 lines)
│   ├── actions.py                      build/up/down/restart/prune (107 lines)
│   └── generate.py                     dockerfile/dockerignore/compose (107 lines)
│
├── docs/                               Documentation management commands
│   └── __init__.py                     All commands in one file (264 lines)
│
├── git/                                Git & GitHub commands
│   ├── __init__.py                     @click.group definition (34 lines)
│   ├── core.py                         status/log/commit/push/pull (140 lines)
│   └── github.py                       gh group: workflows/runs/prs/dispatch (129 lines)
│
├── infra/                              Infrastructure commands
│   ├── __init__.py                     @click.group + helpers (55 lines)
│   ├── detect.py                       Infrastructure status (49 lines)
│   ├── env.py                          Environment management sub-group (187 lines)
│   └── iac.py                          IaC status/resources sub-group (69 lines)
│
├── k8s/                                Kubernetes commands
│   ├── __init__.py                     @click.group definition (35 lines)
│   ├── detect.py                       K8s status/validate (134 lines)
│   ├── generate.py                     Manifest generation (74 lines)
│   └── observe.py                      Cluster info/resource listing (91 lines)
│
├── metrics/                            Project metrics commands
│   └── __init__.py                     All commands in one file (197 lines)
│
├── packages/                           Package management commands
│   └── __init__.py                     All commands in one file (205 lines)
│
├── pages/                              Documentation site builder commands
│   ├── __init__.py                     @click.group definition (36 lines)
│   ├── build.py                        build/preview/deploy/ci/status (146 lines)
│   ├── info.py                         Pages info command (35 lines)
│   └── segments.py                     list/add/remove segments (87 lines)
│
├── quality/                            Code quality commands
│   └── __init__.py                     All commands in one file (221 lines)
│
├── secrets/                            Secrets management commands
│   ├── __init__.py                     @click.group definition (34 lines)
│   ├── crud.py                         set/remove/list secrets (135 lines)
│   ├── envs.py                         Environment sub-group (106 lines)
│   └── status.py                       Status/auto-detect/sync (110 lines)
│
├── security/                           Security scanning commands
│   ├── __init__.py                     @click.group definition (46 lines)
│   ├── detect.py                       scan/files commands (108 lines)
│   ├── generate.py                     gitignore generation (52 lines)
│   └── observe.py                      gitignore/posture analysis (107 lines)
│
├── terraform/                          Terraform/IaC commands
│   ├── __init__.py                     @click.group definition (35 lines)
│   ├── detect.py                       Terraform status (81 lines)
│   ├── generate.py                     Terraform config generation (57 lines)
│   └── observe.py                      validate/plan/state/workspaces (149 lines)
│
├── testing/                            Test management commands
│   ├── __init__.py                     @click.group definition (34 lines)
│   ├── detect.py                       Testing framework detection (63 lines)
│   ├── generate.py                     Test templates + coverage config (77 lines)
│   └── observe.py                      inventory/run/coverage (167 lines)
│
└── vault/                              Secrets vault commands
    ├── __init__.py                     @click.group definition (42 lines)
    ├── crypto.py                       lock/unlock/status/export (101 lines)
    ├── detect.py                       Vault file detection (38 lines)
    └── env_mgmt.py                     keys/templates/create/add/update/delete/activate (219 lines)
```

---

## Complete Command Reference

### `controlplane audit` — Code Quality Audit

| Command | File | Core Service | Purpose |
|---------|------|-------------|---------|
| `audit scan` | `__init__.py` | `audit/` | Run audit scan on project |
| `audit install` | `install.py` | `tool_install/` | Install audit tools |
| `audit plans` | `plans.py` | `audit/` | View remediation plans |
| `audit resume` | `resume.py` | `audit/` | Resume interrupted scans |

### `controlplane backup` — Backup & Restore

| Command | File | Core Service | Purpose |
|---------|------|-------------|---------|
| `backup create` | `__init__.py` | `backup_ops` | Create project backup |
| `backup list` | `__init__.py` | `backup_ops` | List available backups |
| `backup restore` | `__init__.py` | `backup_ops` | Restore from backup |
| `backup delete` | `__init__.py` | `backup_ops` | Delete a backup |
| `backup info` | `__init__.py` | `backup_ops` | Show backup details |

### `controlplane ci` — CI/CD Pipelines

| Command | File | Core Service | Purpose |
|---------|------|-------------|---------|
| `ci status` | `__init__.py` | `ci_ops` | Show CI configuration status |
| `ci workflows` | `__init__.py` | `ci_ops` | List CI workflows |
| `ci generate ci` | `__init__.py` | `ci_ops` | Generate CI pipeline config |
| `ci generate lint` | `__init__.py` | `ci_ops` | Generate linting workflow |

### `controlplane content` — Content Management

| Command | File | Core Service | Purpose |
|---------|------|-------------|---------|
| `content encrypt` | `crypto.py` | `content.crypto` | Encrypt content files |
| `content decrypt` | `crypto.py` | `content.crypto` | Decrypt content files |
| `content metadata` | `crypto.py` | `content.crypto` | Show file metadata |
| `content gallery` | `crypto.py` | `content.crypto` | Browse content gallery |
| `content folders` | `optimize.py` | `content.optimize` | List content folders |
| `content optimize` | `optimize.py` | `content.optimize` | Optimize media files |
| `content release list` | `release.py` | `content.release` | List release artifacts |
| `content release upload` | `release.py` | `content.release` | Upload release artifact |
| `content release delete` | `release.py` | `content.release` | Delete release artifact |

### `controlplane dns` — DNS & CDN

| Command | File | Core Service | Purpose |
|---------|------|-------------|---------|
| `dns status` | `__init__.py` | `dns.cdn_ops` | Show DNS/CDN status |
| `dns lookup` | `__init__.py` | `dns.cdn_ops` | Perform DNS lookup |
| `dns ssl` | `__init__.py` | `dns.cdn_ops` | Check SSL certificate |
| `dns generate` | `__init__.py` | `dns.cdn_ops` | Generate DNS records |

### `controlplane docker` — Docker & Compose

| Command | File | Core Service | Purpose |
|---------|------|-------------|---------|
| `docker status` | `detect.py` | `docker_ops` | Docker/Compose detection |
| `docker containers` | `observe.py` | `docker_ops` | List running containers |
| `docker images` | `observe.py` | `docker_ops` | List local images |
| `docker ps` | `observe.py` | `docker_ops` | Process listing |
| `docker logs` | `observe.py` | `docker_ops` | View service logs |
| `docker stats` | `observe.py` | `docker_ops` | Resource usage stats |
| `docker build` | `actions.py` | `docker_ops` | Build images |
| `docker up` | `actions.py` | `docker_ops` | Start services |
| `docker down` | `actions.py` | `docker_ops` | Stop services |
| `docker restart` | `actions.py` | `docker_ops` | Restart services |
| `docker prune` | `actions.py` | `docker_ops` | Clean up unused resources |
| `docker generate dockerfile` | `generate.py` | `docker_ops` | Generate Dockerfile |
| `docker generate dockerignore` | `generate.py` | `docker_ops` | Generate .dockerignore |
| `docker generate compose` | `generate.py` | `docker_ops` | Generate docker-compose.yml |

### `controlplane docs` — Documentation

| Command | File | Core Service | Purpose |
|---------|------|-------------|---------|
| `docs status` | `__init__.py` | `docs_svc.ops` | Documentation coverage status |
| `docs coverage` | `__init__.py` | `docs_svc.ops` | Detailed coverage report |
| `docs links` | `__init__.py` | `docs_svc.ops` | Check for broken links |
| `docs generate changelog` | `__init__.py` | `docs_svc.ops` | Generate CHANGELOG |
| `docs generate readme` | `__init__.py` | `docs_svc.ops` | Generate README templates |

### `controlplane git` — Git & GitHub

| Command | File | Core Service | Purpose |
|---------|------|-------------|---------|
| `git status` | `core.py` | `git_ops` | Repository status |
| `git log` | `core.py` | `git_ops` | Commit history |
| `git commit` | `core.py` | `git_ops` | Stage and commit |
| `git push` | `core.py` | `git_ops` | Push to remote |
| `git pull` | `core.py` | `git_ops` | Pull from remote |
| `git gh workflows` | `github.py` | `git_ops` | List GitHub Actions workflows |
| `git gh runs` | `github.py` | `git_ops` | List GitHub Actions runs |
| `git gh prs` | `github.py` | `git_ops` | List pull requests |
| `git gh dispatch` | `github.py` | `git_ops` | Trigger workflow dispatch |

### `controlplane infra` — Infrastructure

| Command | File | Core Service | Purpose |
|---------|------|-------------|---------|
| `infra status` | `detect.py` | `env_ops` | Infrastructure status |
| `infra env status` | `env.py` | `env_ops` | Environment file status |
| `infra env vars` | `env.py` | `env_ops` | List environment variables |
| `infra env diff` | `env.py` | `env_ops` | Compare environments |
| `infra env validate` | `env.py` | `env_ops` | Validate env file |
| `infra env generate-example` | `env.py` | `env_ops` | Generate .env.example |
| `infra env generate-env` | `env.py` | `env_ops` | Generate .env from example |
| `infra iac status` | `iac.py` | `env_ops` | IaC status |
| `infra iac resources` | `iac.py` | `env_ops` | List IaC resources |

### `controlplane k8s` — Kubernetes

| Command | File | Core Service | Purpose |
|---------|------|-------------|---------|
| `k8s status` | `detect.py` | `k8s_ops` | K8s configuration status |
| `k8s validate` | `detect.py` | `k8s_ops` | Validate manifests |
| `k8s cluster` | `observe.py` | `k8s_ops` | Show cluster information |
| `k8s get` | `observe.py` | `k8s_ops` | Get K8s resources |
| `k8s generate manifests` | `generate.py` | `k8s_ops` | Generate K8s manifests |

### `controlplane metrics` — Project Metrics

| Command | File | Core Service | Purpose |
|---------|------|-------------|---------|
| `metrics health` | `__init__.py` | `metrics.ops` | Overall project health score |
| `metrics summary` | `__init__.py` | `metrics.ops` | Project summary dashboard |
| `metrics report` | `__init__.py` | `metrics.ops` | Full metrics report |

### `controlplane packages` — Package Management

| Command | File | Core Service | Purpose |
|---------|------|-------------|---------|
| `packages status` | `__init__.py` | `packages_svc.ops` | Package manager status |
| `packages outdated` | `__init__.py` | `packages_svc.ops` | List outdated packages |
| `packages audit` | `__init__.py` | `packages_svc.ops` | Security audit of packages |
| `packages list` | `__init__.py` | `packages_svc.ops` | List installed packages |
| `packages install` | `__init__.py` | `packages_svc.ops` | Install packages |
| `packages update` | `__init__.py` | `packages_svc.ops` | Update packages |

### `controlplane pages` — Documentation Sites

| Command | File | Core Service | Purpose |
|---------|------|-------------|---------|
| `pages build` | `build.py` | `pages_engine` | Build documentation site |
| `pages preview` | `build.py` | `pages_engine` | Preview site locally |
| `pages deploy` | `build.py` | `pages_engine` | Deploy to GitHub Pages |
| `pages ci` | `build.py` | `pages_engine` | Generate CI workflow |
| `pages status` | `build.py` | `pages_engine` | Build status |
| `pages info` | `info.py` | `pages_builders` | Builder information |
| `pages list` | `segments.py` | `pages_engine` | List configured segments |
| `pages add` | `segments.py` | `pages_engine` | Add a segment |
| `pages remove` | `segments.py` | `pages_engine` | Remove a segment |

### `controlplane quality` — Code Quality

| Command | File | Core Service | Purpose |
|---------|------|-------------|---------|
| `quality status` | `__init__.py` | `quality.ops` | Quality tool status |
| `quality check` | `__init__.py` | `quality.ops` | Run quality checks |
| `quality lint` | `__init__.py` | `quality.ops` | Run linter |
| `quality typecheck` | `__init__.py` | `quality.ops` | Run type checker |
| `quality test` | `__init__.py` | `quality.ops` | Run tests |
| `quality format` | `__init__.py` | `quality.ops` | Format code |
| `quality generate config` | `__init__.py` | `quality.ops` | Generate quality config |

### `controlplane secrets` — Secrets Management

| Command | File | Core Service | Purpose |
|---------|------|-------------|---------|
| `secrets status` | `status.py` | `secrets_ops` | Secrets status overview |
| `secrets auto-detect` | `status.py` | `secrets_ops` | Auto-detect secret files |
| `secrets sync` | `status.py` | `secrets_ops` | Sync secrets |
| `secrets set` | `crud.py` | `secrets_ops` | Set a secret value |
| `secrets remove` | `crud.py` | `secrets_ops` | Remove a secret |
| `secrets list` | `crud.py` | `secrets_ops` | List secrets |
| `secrets envs list` | `envs.py` | `secrets_ops` | List environments |
| `secrets envs create` | `envs.py` | `secrets_ops` | Create environment |
| `secrets envs cleanup` | `envs.py` | `secrets_ops` | Clean up environments |

### `controlplane security` — Security Scanning

| Command | File | Core Service | Purpose |
|---------|------|-------------|---------|
| `security scan` | `detect.py` | `security_ops` | Scan for secrets/leaks |
| `security files` | `detect.py` | `security_ops` | Detect sensitive files |
| `security gitignore` | `observe.py` | `security_ops` | Analyze .gitignore |
| `security posture` | `observe.py` | `security_ops` | Security posture assessment |
| `security generate gitignore` | `generate.py` | `security_ops` | Generate .gitignore |

### `controlplane terraform` — Terraform

| Command | File | Core Service | Purpose |
|---------|------|-------------|---------|
| `terraform status` | `detect.py` | `terraform.ops` | Terraform status |
| `terraform validate` | `observe.py` | `terraform.ops` | Validate configuration |
| `terraform plan` | `observe.py` | `terraform.ops` | Run terraform plan |
| `terraform state` | `observe.py` | `terraform.ops` | Show state |
| `terraform workspaces` | `observe.py` | `terraform.ops` | List workspaces |
| `terraform generate` | `generate.py` | `terraform.ops` | Generate Terraform config |

### `controlplane testing` — Test Management

| Command | File | Core Service | Purpose |
|---------|------|-------------|---------|
| `testing status` | `detect.py` | `testing_ops` | Testing framework status |
| `testing inventory` | `observe.py` | `testing_ops` | List test files |
| `testing run` | `observe.py` | `testing_ops` | Run tests |
| `testing coverage` | `observe.py` | `testing_ops` | Show coverage report |
| `testing generate template` | `generate.py` | `testing_ops` | Generate test templates |
| `testing generate coverage-config` | `generate.py` | `testing_ops` | Generate coverage config |

### `controlplane vault` — Secrets Vault

| Command | File | Core Service | Purpose |
|---------|------|-------------|---------|
| `vault lock` | `crypto.py` | `vault` | Lock the vault |
| `vault unlock` | `crypto.py` | `vault` | Unlock the vault |
| `vault status` | `crypto.py` | `vault` | Vault lock status |
| `vault export` | `crypto.py` | `vault` | Export vault contents |
| `vault detect` | `detect.py` | `vault` | Detect vault files |
| `vault keys` | `env_mgmt.py` | `vault_env_ops` | List environment keys |
| `vault templates` | `env_mgmt.py` | `vault_env_ops` | List templates |
| `vault create` | `env_mgmt.py` | `vault_env_ops` | Create environment |
| `vault add-key` | `env_mgmt.py` | `vault_env_ops` | Add key to environment |
| `vault update-key` | `env_mgmt.py` | `vault_env_ops` | Update key value |
| `vault delete-key` | `env_mgmt.py` | `vault_env_ops` | Delete key |
| `vault activate` | `env_mgmt.py` | `vault_env_ops` | Activate environment |

---

## Dependency Graph

The CLI layer has a strict, one-directional dependency: **CLI → Core**.
No core module ever imports from CLI. No CLI module imports from another
CLI module.

```
src/ui/cli/
    │
    │  Every domain imports from:
    │
    ├──── src.core.config.loader         (project discovery)
    │
    └──── src.core.services.*            (business logic)
              │
              ├── docker_ops
              ├── git_ops
              ├── k8s_ops
              ├── terraform.ops
              ├── security_ops
              ├── secrets_ops
              ├── testing_ops
              ├── env_ops
              ├── backup_ops
              ├── vault / vault_env_ops
              ├── content.crypto / .optimize / .release
              ├── quality.ops
              ├── metrics.ops
              ├── packages_svc.ops
              ├── pages_engine / pages_builders
              ├── docs_svc.ops
              ├── dns.cdn_ops
              ├── ci_ops
              └── audit/
```

**Internal dependency map (CLI domain → core service):**

| CLI Domain | Core Service(s) |
|-----------|----------------|
| `audit` | `audit/`, `tool_install/` |
| `backup` | `backup_ops` |
| `ci` | `ci_ops` |
| `content` | `content.crypto`, `content.optimize`, `content.release` |
| `dns` | `dns.cdn_ops` |
| `docker` | `docker_ops` |
| `docs` | `docs_svc.ops`, `docker_ops` (for write_generated_file) |
| `git` | `git_ops` |
| `infra` | `env_ops` |
| `k8s` | `k8s_ops`, `docker_ops` (for write_generated_file) |
| `metrics` | `metrics.ops` |
| `packages` | `packages_svc.ops` |
| `pages` | `pages_engine`, `pages_builders` |
| `quality` | `quality.ops`, `detection`, `config.stack_loader` |
| `secrets` | `secrets_ops` |
| `security` | `security_ops`, `env_ops` |
| `terraform` | `terraform.ops`, `docker_ops` (for write_generated_file) |
| `testing` | `testing_ops` |
| `vault` | `vault`, `vault_env_ops` |

---

## Consumers

| Consumer | What It Uses |
|----------|-------------|
| `src/main.py` | Imports all 19 Click groups and registers them via `cli.add_command()` |
| End users | Run `controlplane <domain> <command>` from the terminal |
| CI pipelines | Automate operations via CLI commands in scripts |

No other source module imports from the CLI layer.

---

## Design Decisions

### Why Click Instead of Typer?

Click was chosen over Typer for several reasons:

- **Stability** — Click is the mature foundation; Typer is built on top of it
- **Groups and sub-groups** — Click's `@group` decorator maps perfectly to
  the domain-based command tree
- **Context passing** — `@click.pass_context` provides clean project root
  resolution without global state
- **No magic** — explicit decorators, no hidden type annotation inference

### Why Thin Wrappers?

CLI commands contain **zero business logic**. They only do three things:

1. **Resolve project root** — from the Click context or auto-discovery
2. **Call a core service function** — delegate all logic to `core/services/`
3. **Format output** — print results for the terminal

This means:

- **Core services are testable** without Click
- **The same logic powers both CLI and Web** — the web admin calls the same
  core services
- **CLI changes don't affect business logic** — safe to refactor commands
  without risk to the backend

### Why Lazy Imports?

Most CLI commands use lazy imports inside the function body:

```python
@docker.command("containers")
@click.pass_context
def containers(ctx, compose):
    root = _resolve_project_root(ctx)
    from src.core.services.docker_ops import docker_containers  # lazy
    result = docker_containers(root, compose=compose)
```

**Why not top-level imports?** Because the CLI registers 19 command groups
at startup. If every group eagerly imported its core services, startup time
would be measured in seconds. Lazy imports mean only the invoked command
pays the import cost.

### Why the detect/observe/actions/generate Split?

Domains with many commands split them by **intent**:

| File | Intent | Side Effects | Example |
|------|--------|-------------|---------|
| `detect.py` | Discovery | None | Is Docker installed? |
| `observe.py` | Read-only | None | List containers, show logs |
| `actions.py` | Mutation | Yes | Build, deploy, restart |
| `generate.py` | File creation | Yes (writes files) | Generate Dockerfile |

This makes it easy to find commands by what they do, and allows
code review to focus on the mutating files (`actions.py`, `generate.py`).

### Why `_resolve_project_root` in Every Domain?

Each domain has its own copy of this helper instead of a shared utility
because:

- It keeps each domain **self-contained** — no cross-domain imports
- The function is trivially small (4 lines)
- It avoids creating a "CLI utils" module that would attract unrelated helpers

### Why 19 Separate Domains Instead of Fewer?

Each CLI domain maps 1:1 to a **feature boundary** in the core services
layer. This alignment means:

- Adding a new feature = adding a new CLI domain
- Removing a feature = removing its CLI domain
- No domain grows unbounded — each stays focused on its service

---

## Per-Domain Summary

| Domain | Files | Lines | Commands | Core Service | Purpose |
|--------|-------|-------|----------|-------------|---------|
| `audit` | 4 | 377 | 4 | `audit/`, `tool_install/` | Code quality audit, tool installation |
| `backup` | 1 | 196 | 5 | `backup_ops` | Create/list/restore/delete backups |
| `ci` | 1 | 236 | 4 | `ci_ops` | CI/CD pipeline status and generation |
| `content` | 4 | 341 | 9 | `content.*` | Encrypt, optimize, release content |
| `dns` | 1 | 229 | 4 | `dns.cdn_ops` | DNS records, SSL, CDN status |
| `docker` | 5 | 463 | 14 | `docker_ops` | Container lifecycle management |
| `docs` | 1 | 264 | 5 | `docs_svc.ops` | Documentation coverage and generation |
| `git` | 3 | 303 | 9 | `git_ops` | Git operations + GitHub Actions |
| `infra` | 4 | 360 | 9 | `env_ops` | Environment files, IaC resources |
| `k8s` | 4 | 334 | 5 | `k8s_ops` | Kubernetes manifests and cluster |
| `metrics` | 1 | 197 | 3 | `metrics.ops` | Project health and summaries |
| `packages` | 1 | 205 | 6 | `packages_svc.ops` | Package management |
| `pages` | 4 | 304 | 9 | `pages_engine` | Doc site build/deploy/segments |
| `quality` | 1 | 221 | 7 | `quality.ops` | Lint, typecheck, test, format |
| `secrets` | 4 | 385 | 9 | `secrets_ops` | Secrets CRUD + environments |
| `security` | 4 | 313 | 5 | `security_ops` | Scans, posture, gitignore |
| `terraform` | 4 | 322 | 6 | `terraform.ops` | Terraform lifecycle |
| `testing` | 4 | 341 | 6 | `testing_ops` | Test inventory, run, coverage |
| `vault` | 4 | 400 | 12 | `vault`, `vault_env_ops` | Vault encryption + env management |

**Totals: 56 files, 5,792 lines, ~131 commands across 19 domains.**

---

## Adding a New CLI Domain

### 1. Create the domain package

```bash
mkdir src/ui/cli/monitoring
```

### 2. Create `__init__.py` with the Click group

```python
"""CLI commands for Monitoring & Alerting.

Thin wrappers over ``src.core.services.monitoring_ops``.
"""
from __future__ import annotations
from pathlib import Path
import click


def _resolve_project_root(ctx: click.Context) -> Path:
    config_path = ctx.obj.get("config_path")
    if config_path is None:
        from src.core.config.loader import find_project_file
        config_path = find_project_file()
    return config_path.parent.resolve() if config_path else Path.cwd()


@click.group()
@click.pass_context
def monitoring(ctx):
    """Monitoring & alerting operations."""
    pass


@monitoring.command()
@click.pass_context
def status(ctx):
    """Show monitoring status."""
    root = _resolve_project_root(ctx)
    from src.core.services.monitoring_ops import monitoring_status
    result = monitoring_status(root)
    click.echo(result)
```

### 3. Register in `src/main.py`

```python
from src.ui.cli.monitoring import monitoring
cli.add_command(monitoring)
```

### 4. Rules to follow

- **No business logic** — only resolve root → call core → print
- **Lazy imports** — import core services inside command functions
- **`_resolve_project_root`** — copy the standard helper
- **Domain-specific group** — `@click.group()` as the entry point
- **Split by intent** — use detect/observe/actions/generate as the domain grows
