# Quick Start Guide

> From `git clone` to running automations in 5 minutes.

---

## 1. Clone & Install

```bash
git clone https://github.com/cyberpunk042/devops-control-plane.git
cd devops-control-plane

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install with dev dependencies
pip install -e ".[dev]"
```

## 2. Verify Installation

```bash
# Check CLI is working
./manage.sh --help

# Run the test suite
make check
```

You should see all tests pass and the CLI help menu.

## 3. Check Project Status

```bash
./manage.sh status
```

This shows:
- Project name and description
- Detected modules with their stacks
- Available environments
- Last operation result

## 4. Detect Modules

```bash
./manage.sh detect
```

Scans the project for modules matching stack definitions. Each module gets
tagged with its stack (e.g., `python`, `node`, `docker-compose`).

## 5. Run an Automation

```bash
# Mock mode (no real execution — safe to try)
./manage.sh run test --mock

# Dry run (shows plan without executing)
./manage.sh run lint --dry-run

# Target a specific module
./manage.sh run test --mock -m core
```

## 6. Check Health

```bash
./manage.sh health
```

Shows system health including circuit breaker states and retry queue status.

## 7. Launch the Web Dashboard

```bash
./manage.sh web
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) to see the admin dashboard.

The dashboard has 7 tabs:

| Tab | What it does |
|-----|-------------|
| 📊 Dashboard | Project overview, modules, activity feed |
| 🧙 Setup | Guided project configuration wizard |
| 🔐 Secrets | Vault encryption, secrets editor |
| ⚡ Commands | Run capabilities on modules |
| 📁 Content | File browser, encryption, media optimization |
| 🔌 Integrations | Git, GitHub, Pages builder, CI/CD |
| 🐛 Debugging | Audit logs, state inspector, health details |

Press **SPACE** to live-reload the server. Press **Ctrl+C** or **q** to quit.

## 8. JSON Output

All commands support `--json` for machine-readable output:

```bash
./manage.sh status --json
./manage.sh detect --json
./manage.sh run test --mock --json
./manage.sh health --json
```

---

## What's Next?

- Create custom stacks → [STACKS.md](STACKS.md)
- Write custom adapters → [ADAPTERS.md](ADAPTERS.md)
- Explore the web admin → [WEB_ADMIN.md](WEB_ADMIN.md)
- Build documentation sites → [PAGES.md](PAGES.md)
- Set up secrets encryption → [VAULT.md](VAULT.md)
- Understand the architecture → [ARCHITECTURE.md](ARCHITECTURE.md)
- Start developing → [DEVELOPMENT.md](DEVELOPMENT.md)
