"""
Project Audit engine — multi-layered code analysis.

Public API:
    L0 — Detection (auto-load, < 100ms):
        l0_system_profile(root)       → system, tools, modules

    L1 — Classification (auto-load, < 500ms):
        l1_dependencies(root)         → library inventory + classification
        l1_structure(root)            → module map + solution classification
        l1_clients(root)              → external service client detection

    L2 — Analysis (on-demand, 1-5s):
        l2_structure(root)            → import graph + module boundaries
        l2_quality(root)              → code health + hotspots + naming
        l2_repo(root)                 → repository health + git analysis
        l2_risks(root)                → risk register + posture score

    Scoring:
        audit_scores(root)            → complexity + quality master scores
        audit_scores_enriched(root)   → L2-enriched master scores

Models:
    AuditMeta, wrap_result            → result envelope pattern
"""

from src.core.services.audit.l0_detection import l0_system_profile
from src.core.services.audit.l1_classification import (
    l1_clients,
    l1_dependencies,
    l1_structure,
)
from src.core.services.audit.l2_quality import l2_quality
from src.core.services.audit.l2_repo import l2_repo
from src.core.services.audit.l2_risk import l2_risks
from src.core.services.audit.l2_structure import l2_structure
from src.core.services.audit.models import AuditMeta, wrap_result
from src.core.services.audit.scoring import audit_scores, audit_scores_enriched

__all__ = [
    "AuditMeta",
    "audit_scores",
    "audit_scores_enriched",
    "l0_system_profile",
    "l1_clients",
    "l1_dependencies",
    "l1_structure",
    "l2_quality",
    "l2_repo",
    "l2_risks",
    "l2_structure",
    "wrap_result",
]
