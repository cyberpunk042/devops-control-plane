"""
Module upgrade service — intelligent checklist generation and automation.

Public API:
    generate_checklist(module_name, target, project_root)
        → list[dict]  (step dicts ready for ModuleVersionPlanStep)

Generates context-aware upgrade/downgrade checklists based on:
  - Module's detected runtime floor (3-tier hierarchy)
  - Dependency floor (from Requires-Python metadata)
  - Code floor (from language feature analysis)
  - Version strategy (latest vs compatibility)
  - File presence (pyproject.toml, setup.py, etc.)

Recipes are JSON data files in data/recipes/. Adding a new language
means adding a JSON file — zero code changes to the generator.
"""

from __future__ import annotations
from .generator import generate_checklist

__all__ = ["generate_checklist"]
