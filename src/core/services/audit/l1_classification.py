"""
L1 — Classification layer (fast, < 500ms).

Parses dependency manifests, classifies libraries against the catalog,
identifies frameworks/ORMs/clients, detects crossover patterns.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from src.core.services.audit.catalog import (
    LibraryInfo,
    categories_summary,
    classify_batch,
    lookup,
)
from src.core.services.audit.l1_parsers import PARSERS as _PARSERS

logger = logging.getLogger(__name__)




# ══════════════════════════════════════════════════════════════════
#  Classification logic
# ══════════════════════════════════════════════════════════════════


def _extract_all_deps(project_root: Path) -> list[dict]:
    """Extract dependencies from all manifest files.

    Returns list of {name, version, dev, source_file, ecosystem}.
    Deduplicates by (name, ecosystem).
    """
    all_deps: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for filename, parser in _PARSERS.items():
        path = project_root / filename
        if path.is_file():
            deps = parser(path)
            # Infer ecosystem from filename
            if filename in ("pyproject.toml", "requirements.txt", "requirements-dev.txt"):
                eco = "python"
            elif filename == "package.json":
                eco = "node"
            elif filename == "go.mod":
                eco = "go"
            elif filename == "Cargo.toml":
                eco = "rust"
            elif filename == "Gemfile":
                eco = "ruby"
            elif filename == "mix.exs":
                eco = "elixir"
            else:
                eco = "unknown"

            for dep in deps:
                key = (dep["name"].lower(), eco)
                if key not in seen:
                    seen.add(key)
                    dep["source_file"] = filename
                    dep["ecosystem"] = eco
                    all_deps.append(dep)

    return all_deps


def _identify_frameworks(classified: dict[str, LibraryInfo | None]) -> list[dict]:
    """Extract identified frameworks from classified deps."""
    frameworks = []
    for name, info in classified.items():
        if info and info.get("category") == "framework":
            frameworks.append({
                "name": name,
                "type": info.get("type", ""),
                "ecosystem": info.get("ecosystem", ""),
                "description": info.get("description", ""),
            })
    return frameworks


def _identify_orms(classified: dict[str, LibraryInfo | None]) -> list[dict]:
    """Extract identified ORMs/ODMs from classified deps."""
    orms = []
    for name, info in classified.items():
        if info and info.get("category") == "orm":
            orms.append({
                "name": name,
                "type": info.get("type", ""),
                "ecosystem": info.get("ecosystem", ""),
                "description": info.get("description", ""),
            })
    return orms


def _identify_clients(classified: dict[str, LibraryInfo | None]) -> list[dict]:
    """Extract identified external service clients."""
    clients = []
    for name, info in classified.items():
        if info and info.get("category") in ("client", "database"):
            clients.append({
                "name": name,
                "category": info["category"],
                "type": info.get("type", ""),
                "ecosystem": info.get("ecosystem", ""),
                "description": info.get("description", ""),
            })
    return clients


def _detect_crossovers(deps: list[dict], classified: dict[str, LibraryInfo | None]) -> list[dict]:
    """Detect library crossovers — same logical service used across ecosystems.

    Example: Redis client in both Python and Node modules.
    Uses the catalog ``service`` field for grouping when available,
    falling back to ``type``.
    """
    # Group by logical service identity
    service_map: dict[str, list[dict]] = {}
    for dep in deps:
        info = classified.get(dep["name"])
        if info and info.get("category") in ("client", "database", "orm"):
            # Prefer service identity, fall back to type
            svc = info.get("service") or info.get("type", "unknown")
            service_map.setdefault(svc, []).append({
                "name": dep["name"],
                "ecosystem": dep.get("ecosystem", ""),
            })

    crossovers = []
    for service, libs in service_map.items():
        ecosystems = set(lib["ecosystem"] for lib in libs)
        if len(ecosystems) > 1:
            crossovers.append({
                "service": service,
                "service_type": service,  # backwards-compat
                "description": f"{service} used across {', '.join(sorted(ecosystems))}",
                "libraries": libs,
                "ecosystems": sorted(ecosystems),
            })

    return crossovers


# ══════════════════════════════════════════════════════════════════
#  Public API
# ══════════════════════════════════════════════════════════════════


def l1_dependencies(project_root: Path) -> dict:
    """L1: Full dependency inventory with classification.

    Returns:
        {
            "_meta": AuditMeta,
            "dependencies": [{name, version, dev, ecosystem, source_file, classification}, ...],
            "total": int,
            "total_prod": int,
            "total_dev": int,
            "classified": int,
            "unclassified": int,
            "categories": {framework: 2, orm: 1, client: 5, ...},
            "frameworks": [{name, type, ecosystem, description}, ...],
            "orms": [{name, type, ecosystem, description}, ...],
            "crossovers": [{service, libraries, ecosystems}, ...],
            "ecosystems": {python: 20, node: 15, ...},
        }
    """
    import time

    from src.core.services.audit.models import wrap_result

    started = time.time()

    deps = _extract_all_deps(project_root)
    names = [d["name"] for d in deps]
    classified = classify_batch(names)

    # Enrich deps with classification
    enriched = []
    for dep in deps:
        info = classified.get(dep["name"])
        enriched.append({
            **dep,
            "classification": dict(info) if info else None,
        })

    # Ecosystem counts
    eco_counts: dict[str, int] = {}
    for dep in deps:
        eco = dep.get("ecosystem", "unknown")
        eco_counts[eco] = eco_counts.get(eco, 0) + 1

    prod_count = sum(1 for d in deps if not d.get("dev"))
    dev_count = sum(1 for d in deps if d.get("dev"))
    classified_count = sum(1 for info in classified.values() if info)

    data = {
        "dependencies": enriched,
        "total": len(deps),
        "total_prod": prod_count,
        "total_dev": dev_count,
        "classified": classified_count,
        "unclassified": len(deps) - classified_count,
        "categories": categories_summary(classified),
        "frameworks": _identify_frameworks(classified),
        "orms": _identify_orms(classified),
        "crossovers": _detect_crossovers(deps, classified),
        "ecosystems": eco_counts,
    }
    return wrap_result(data, "L1", "dependencies", started)


def l1_structure(project_root: Path) -> dict:
    """L1: Solution structure — what kind of project is this?

    Returns:
        {
            "_meta": AuditMeta,
            "solution_type": "multi-module python monorepo",
            "components": [{type, name, technologies, ...}],
            "has_cli": bool,
            "has_web": bool,
            "has_api": bool,
            "has_docs": bool,
            "has_tests": bool,
            "has_iac": bool,
            "has_ci": bool,
            "entrypoints": [{type, path, description}, ...],
        }
    """
    import time

    from src.core.services.audit.models import wrap_result

    started = time.time()

    # Check for structural indicators
    indicators: dict[str, bool] = {
        "has_cli": (project_root / "src" / "ui" / "cli").is_dir()
            or (project_root / "cli").is_dir()
            or (project_root / "src" / "cli").is_dir(),
        "has_web": (project_root / "src" / "ui" / "web").is_dir()
            or (project_root / "app").is_dir()
            or (project_root / "src" / "app").is_dir(),
        "has_api": (project_root / "api").is_dir()
            or (project_root / "src" / "api").is_dir(),
        "has_docs": (project_root / "docs").is_dir(),
        "has_tests": (project_root / "tests").is_dir()
            or (project_root / "test").is_dir()
            or (project_root / "spec").is_dir(),
        "has_iac": (project_root / "terraform").is_dir()
            or (project_root / "infra").is_dir()
            or (project_root / "k8s").is_dir()
            or (project_root / "deploy").is_dir(),
        "has_ci": (project_root / ".github" / "workflows").is_dir()
            or (project_root / ".gitlab-ci.yml").is_file()
            or (project_root / "Jenkinsfile").is_file()
            or (project_root / ".circleci").is_dir(),
        "has_docker": (project_root / "Dockerfile").is_file()
            or (project_root / "docker-compose.yml").is_file()
            or (project_root / "docker-compose.yaml").is_file(),
    }

    # Detect entrypoints
    entrypoints: list[dict] = []

    # Python entrypoints
    for name in ("manage.py", "app.py", "main.py", "run.py", "manage.sh"):
        p = project_root / name
        if p.is_file():
            entrypoints.append({"type": "script", "path": name, "description": name})

    src_main = project_root / "src" / "main.py"
    if src_main.is_file():
        entrypoints.append({"type": "module", "path": "src/main.py", "description": "Module entry"})

    # Package.json scripts
    pkg = project_root / "package.json"
    if pkg.is_file():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
            scripts = data.get("scripts", {})
            for script_name in ("start", "dev", "serve", "build"):
                if script_name in scripts:
                    entrypoints.append({
                        "type": "npm-script",
                        "path": f"npm run {script_name}",
                        "description": scripts[script_name],
                    })
        except (json.JSONDecodeError, OSError):
            pass

    # Makefile
    if (project_root / "Makefile").is_file():
        entrypoints.append({"type": "makefile", "path": "Makefile", "description": "GNU Make"})

    # Detect solution type
    components: list[dict] = []
    if indicators["has_cli"]:
        components.append({"type": "cli", "description": "Command-line interface"})
    if indicators["has_web"]:
        components.append({"type": "web", "description": "Web application"})
    if indicators["has_api"]:
        components.append({"type": "api", "description": "API server"})
    if indicators["has_docs"]:
        components.append({"type": "docs", "description": "Documentation"})
    if indicators["has_iac"]:
        components.append({"type": "iac", "description": "Infrastructure as Code"})
    if indicators["has_docker"]:
        components.append({"type": "docker", "description": "Containerized"})

    # Infer solution type label
    parts = []
    if len(components) > 2:
        parts.append("multi-component")
    # Check ecosystems from manifests
    manifests = [f.name for f in project_root.iterdir() if f.is_file()]
    if "pyproject.toml" in manifests or "requirements.txt" in manifests:
        parts.append("python")
    if "package.json" in manifests:
        parts.append("node")
    if "go.mod" in manifests:
        parts.append("go")
    if "Cargo.toml" in manifests:
        parts.append("rust")

    if any(c["type"] == "web" for c in components):
        parts.append("web app")
    elif any(c["type"] == "cli" for c in components):
        parts.append("CLI tool")
    elif any(c["type"] == "api" for c in components):
        parts.append("API service")
    else:
        parts.append("project")

    solution_type = " ".join(parts) if parts else "project"

    data = {
        "solution_type": solution_type,
        "components": components,
        **indicators,
        "entrypoints": entrypoints,
    }
    return wrap_result(data, "L1", "structure", started)


def l1_clients(project_root: Path) -> dict:
    """L1: External service client detection.

    Returns:
        {
            "_meta": AuditMeta,
            "clients": [{name, type, ecosystem, description, service}, ...],
            "total": int,
            "by_type": {cache: 1, message-broker: 2, ...},
            "by_ecosystem": {python: 3, node: 2, ...},
            "by_service": {Redis: [{...}], PostgreSQL: [{...}], ...},
        }
    """
    import time

    from src.core.services.audit.models import wrap_result

    started = time.time()

    deps = _extract_all_deps(project_root)
    classified = classify_batch([d["name"] for d in deps])
    clients = _identify_clients(classified)

    # Add database drivers too
    for dep in deps:
        info = classified.get(dep["name"])
        if info and info.get("category") == "database" and info.get("type") == "driver":
            clients.append({
                "name": dep["name"],
                "category": "database",
                "type": info.get("type", ""),
                "ecosystem": info.get("ecosystem", ""),
                "description": info.get("description", ""),
            })

    # Enrich each client with service identity from catalog
    for c in clients:
        info = classified.get(c["name"])
        if info:
            c["service"] = info.get("service", c.get("description", "").split(" ")[0])
        else:
            c["service"] = c.get("description", "").split(" ")[0]

    # Deduplicate
    seen: set[str] = set()
    unique_clients: list[dict] = []
    for c in clients:
        if c["name"] not in seen:
            seen.add(c["name"])
            unique_clients.append(c)

    # Group by type, ecosystem, and service
    by_type: dict[str, int] = {}
    by_eco: dict[str, int] = {}
    by_service: dict[str, list[dict]] = {}
    for c in unique_clients:
        t = c.get("type", "other")
        by_type[t] = by_type.get(t, 0) + 1
        e = c.get("ecosystem", "unknown")
        by_eco[e] = by_eco.get(e, 0) + 1
        svc = c.get("service", "other")
        by_service.setdefault(svc, []).append(c)

    data = {
        "clients": unique_clients,
        "total": len(unique_clients),
        "by_type": by_type,
        "by_ecosystem": by_eco,
        "by_service": by_service,
    }
    return wrap_result(data, "L1", "clients", started)
