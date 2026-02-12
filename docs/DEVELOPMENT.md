# Development Guide

> Setting up a development environment, running tests, and contributing.

---

## Prerequisites

- **Python 3.12+** (via pyenv or system)
- **Git**
- **Optional**: Node.js (for Docusaurus builder), Hugo binary, MkDocs

See [ADR-001](adr/001-python-version.md) for the Python version decision.

---

## Setup

```bash
# Clone
git clone https://github.com/cyberpunk042/devops-control-plane.git
cd devops-control-plane

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install with dev dependencies
pip install -e ".[dev]"

# Verify
make check
```

---

## Development Commands

```bash
# Full check suite (lint + types + tests)
make check

# Individual
make lint      # ruff
make types     # mypy
make test      # pytest

# Web admin with live reload
./manage.sh web
# Press SPACE to reload, Ctrl+C or q to quit

# CLI commands
./manage.sh status
./manage.sh detect
./manage.sh health
```

---

## Project Structure

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full directory layout.

Key locations:

| Purpose | Path |
|---------|------|
| CLI entrypoint | `src/main.py` |
| Domain models | `src/core/models/` |
| Business logic | `src/core/services/` |
| Adapters | `src/adapters/` |
| Web admin | `src/ui/web/` |
| Page builders | `src/ui/web/pages_builders/` |
| Templates (HTML) | `src/ui/web/templates/partials/` |
| Templates (JS) | `src/ui/web/templates/scripts/` |
| CSS | `src/ui/web/static/css/admin.css` |
| Stack definitions | `stacks/` |
| Tests | `tests/` |
| Documentation | `docs/` |

---

## Testing

Tests are in the `tests/` directory using pytest:

```bash
# Run all tests
make test

# Run specific test file
.venv/bin/pytest tests/test_vault.py -v

# Run with coverage
.venv/bin/pytest --cov=src tests/
```

### Test Organization

| File | Tests |
|------|-------|
| `test_models.py` | Pydantic model serialization roundtrips |
| `test_config.py` | YAML loading, validation |
| `test_adapters.py` | Adapter protocol, registry, mock mode |
| `test_cli.py` | CLI command invocations |
| `test_detection.py` | Stack matching, module discovery |
| `test_engine.py` | Execution phases, receipts |
| `test_reliability.py` | Circuit breaker, retry queue |
| `test_observability.py` | Health checks, metrics |
| `test_persistence.py` | State file, audit ledger |
| `test_vault.py` | Vault encryption roundtrips |
| `test_web.py` | Web route status codes, response shapes |
| `test_e2e.py` | End-to-end integration |
| `test_smoke.py` | Basic import and startup |

---

## Code Style

- **Linter**: Ruff (configured in `ruff.toml`)
- **Type checker**: mypy (configured in `pyproject.toml`)
- **Line length**: 99 characters
- **Imports**: sorted by ruff, absolute imports preferred
- **Docstrings**: Google style

### Commit Messages

Follow conventional commits:

```
feat(pages): add MkDocs config schema
fix(vault): handle lock race condition
docs: update architecture diagram
test(engine): add dry-run receipt test
refactor(adapters): extract base protocol
chore: update dependencies
```

---

## Adding Features

### New CLI Command

1. Create `src/ui/cli/mycommand.py`
2. Register with Click group in `src/main.py`
3. Call use-cases from `src/core/use_cases/`
4. Add tests in `tests/test_cli.py`

### New Web Tab

1. Create partial: `templates/partials/_tab_mytab.html`
2. Create script: `templates/scripts/_mytab.html`
3. Register in `_nav.html` tab bar
4. Create Flask blueprint: `routes_mytab.py`
5. Register blueprint in `server.py`

### New Adapter

See [ADAPTERS.md](ADAPTERS.md).

### New Stack

See [STACKS.md](STACKS.md).

### New Page Builder

See [PAGES.md](PAGES.md) → Extending.

---

## ADRs

Architecture Decision Records live in `docs/adr/`:

| ADR | Decision |
|-----|----------|
| [001](adr/001-python-version.md) | Python 3.12 via pyenv |

For non-obvious architectural decisions, create a new ADR:

```bash
# Template
cat > docs/adr/NNN-title.md << 'EOF'
# ADR-NNN: Title

**Status:** Proposed
**Date:** YYYY-MM-DD

## Context
## Decision
## Consequences
EOF
```

---

## See Also

- [ARCHITECTURE.md](ARCHITECTURE.md) — System architecture
- [QUICKSTART.md](QUICKSTART.md) — 5-minute setup
- [ADAPTERS.md](ADAPTERS.md) — Creating adapters
- [STACKS.md](STACKS.md) — Creating stacks
