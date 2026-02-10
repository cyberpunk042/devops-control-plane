# Example: Multi-Service Project

> A typical microservices project managed by the Control Plane.

---

## Project Structure

```
my-platform/
├── project.yml              # Control Plane config
├── manage.sh                # → copy from devops-control-plane
├── stacks/
│   ├── python/
│   │   └── stack.yml
│   ├── node/
│   │   └── stack.yml
│   └── docker-compose/
│       └── stack.yml
├── services/
│   ├── api/                 # Python FastAPI service
│   │   ├── pyproject.toml
│   │   └── src/
│   ├── auth/                # Python auth service
│   │   ├── pyproject.toml
│   │   └── src/
│   └── dashboard/           # React frontend
│       ├── package.json
│       └── src/
├── infra/
│   ├── gateway/             # Docker Compose stack
│   │   └── docker-compose.yml
│   └── monitoring/
│       └── docker-compose.yml
└── docs/
    └── README.md
```

## `project.yml`

```yaml
name: my-platform
description: E-commerce platform with microservices
repository: github.com/org/my-platform

modules:
  - name: api
    path: services/api
    domain: backend
    stack: python

  - name: auth
    path: services/auth
    domain: backend
    stack: python

  - name: dashboard
    path: services/dashboard
    domain: frontend
    stack: node

  - name: gateway
    path: infra/gateway
    domain: infrastructure
    stack: docker-compose

  - name: monitoring
    path: infra/monitoring
    domain: infrastructure
    stack: docker-compose

environments:
  - name: dev
    default: true
  - name: staging
  - name: production
```

## Usage

```bash
# Install the control plane (from pip or local)
pip install devops-control-plane
# — or —
pip install -e /path/to/devops-control-plane

# Detect all modules
python -m src.main --config project.yml detect

# Run tests across all services
python -m src.main run test

# Lint only backend services
python -m src.main run lint -m api -m auth

# Dry run to see what would happen
python -m src.main run build --dry-run

# Check system health
python -m src.main health

# Launch dashboard
python -m src.main web
```

## Cross-Cutting Operations

The power of the control plane is running the same capability across all modules:

```bash
# Test everything
python -m src.main run test
# → api: pytest ✓
# → auth: pytest ✓
# → dashboard: npm test ✓
# → gateway: docker compose run test ✓
# → monitoring: docker compose run test ✓

# Lint everything
python -m src.main run lint
# → api: ruff check . ✓
# → auth: ruff check . ✓
# → dashboard: npm run lint ✓
```

Each module uses the capabilities defined in its matched stack, so `test` runs `pytest` for Python modules and `npm test` for Node modules.
