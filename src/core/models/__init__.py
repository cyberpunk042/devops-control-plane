"""
Domain models — Pydantic types for the control plane.

All models are re-exported here for convenient access:

    from src.core.models import Project, Module, Stack, Action, Receipt, ProjectState
"""

from src.core.models.action import Action, Receipt
from src.core.models.module import Module, ModuleHealth
from src.core.models.project import Environment, ExternalLinks, ModuleRef, Project
from src.core.models.stack import (
    AdapterRequirement,
    DetectionRule,
    Stack,
    StackCapability,
)
from src.core.models.state import (
    AdapterState,
    ModuleState,
    OperationRecord,
    ProjectState,
)

__all__ = [
    # action.py
    "Action",
    "AdapterRequirement",
    "AdapterState",
    "DetectionRule",
    "Environment",
    "ExternalLinks",
    # module.py
    "Module",
    "ModuleHealth",
    "ModuleRef",
    "ModuleState",
    "OperationRecord",
    # project.py
    "Project",
    # state.py
    "ProjectState",
    "Receipt",
    # stack.py
    "Stack",
    "StackCapability",
]
