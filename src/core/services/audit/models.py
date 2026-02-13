"""
Audit data models — TypedDicts for all layer results.

Provides consistent typing for the audit engine output,
plus the _meta envelope pattern that every result wraps in.
"""

from __future__ import annotations

import time
from typing import Any, TypedDict


# ═══════════════════════════════════════════════════════════════════
#  Meta envelope — wraps every analysis result
# ═══════════════════════════════════════════════════════════════════


class AuditMeta(TypedDict):
    layer: str          # "L0" | "L1" | "L2" | "L3"
    dimension: str      # "system" | "dependencies" | "structure" | ...
    computed_at: float   # time.time()
    duration_ms: int     # wall-clock milliseconds
    scope: str          # "full" | "module:<path>"


def make_meta(
    layer: str,
    dimension: str,
    started: float,
    *,
    scope: str = "full",
) -> AuditMeta:
    """Build a _meta envelope from a start timestamp."""
    now = time.time()
    return {
        "layer": layer,
        "dimension": dimension,
        "computed_at": now,
        "duration_ms": int((now - started) * 1000),
        "scope": scope,
    }


def wrap_result(
    data: dict[str, Any],
    layer: str,
    dimension: str,
    started: float,
    *,
    scope: str = "full",
) -> dict[str, Any]:
    """Wrap a result dict with _meta. Returns a new dict — never mutates."""
    return {"_meta": make_meta(layer, dimension, started, scope=scope), **data}


# ═══════════════════════════════════════════════════════════════════
#  L0 — Detection layer types
# ═══════════════════════════════════════════════════════════════════


class OSInfo(TypedDict, total=False):
    system: str
    release: str
    machine: str
    wsl: bool
    distro: str


class PythonInfo(TypedDict):
    version: str
    implementation: str
    executable: str
    prefix: str


class VenvInfo(TypedDict):
    in_venv: bool
    venvs: list[dict]
    active_prefix: str | None


class ToolInfo(TypedDict):
    id: str
    cli: str
    label: str
    available: bool
    path: str | None


class ModuleInfo(TypedDict, total=False):
    name: str
    path: str
    domain: str
    stack: str
    language: str
    version: str
    detected: bool
    description: str
    file_count: int


class ManifestInfo(TypedDict):
    file: str
    ecosystem: str
    manager: str
    size: int


class L0Result(TypedDict, total=False):
    _meta: AuditMeta
    os: OSInfo
    python: PythonInfo
    venv: VenvInfo
    tools: list[ToolInfo]
    modules: list[ModuleInfo]
    manifests: list[ManifestInfo]
    project_root: str


# ═══════════════════════════════════════════════════════════════════
#  L1 — Classification layer types
# ═══════════════════════════════════════════════════════════════════


class DependencyInfo(TypedDict, total=False):
    name: str
    version: str
    dev: bool
    ecosystem: str
    source_file: str
    classification: dict | None  # LibraryInfo or None


class CrossoverInfo(TypedDict):
    service_type: str
    service: str
    libraries: list[dict]
    ecosystems: list[str]


class L1DepsResult(TypedDict, total=False):
    _meta: AuditMeta
    dependencies: list[DependencyInfo]
    total: int
    total_prod: int
    total_dev: int
    categories: dict[str, int]
    frameworks: list[dict]
    orms: list[dict]
    crossovers: list[CrossoverInfo]
    ecosystems: dict[str, int]


class ComponentInfo(TypedDict, total=False):
    type: str
    name: str
    technologies: list[str]
    path: str


class EntrypointInfo(TypedDict, total=False):
    type: str
    path: str
    description: str


class L1StructResult(TypedDict, total=False):
    _meta: AuditMeta
    solution_type: str
    components: list[ComponentInfo]
    has_cli: bool
    has_web: bool
    has_docs: bool
    has_tests: bool
    has_iac: bool
    has_ci: bool
    has_docker: bool
    entrypoints: list[EntrypointInfo]


class ClientInfo(TypedDict, total=False):
    name: str
    type: str
    ecosystem: str
    description: str
    library: str
    service: str  # Logical service identity (e.g., "Redis", "PostgreSQL")


class L1ClientsResult(TypedDict, total=False):
    _meta: AuditMeta
    clients: list[ClientInfo]
    total: int
    by_type: dict[str, int]
    by_ecosystem: dict[str, int]
    by_service: dict[str, list[dict]]  # Grouped by logical service


# ═══════════════════════════════════════════════════════════════════
#  Scores
# ═══════════════════════════════════════════════════════════════════


class ScoreBreakdownItem(TypedDict):
    score: float
    weight: float
    detail: str


class ScoreResult(TypedDict):
    score: float
    breakdown: dict[str, ScoreBreakdownItem]


class AuditScores(TypedDict, total=False):
    _meta: AuditMeta
    complexity: ScoreResult
    quality: ScoreResult
