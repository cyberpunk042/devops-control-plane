"""
Stack loader — loads stack definitions from YAML files.

Stacks live in stacks/<name>/stack.yml. This module discovers and
loads them all into a registry keyed by name.
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from src.core.models.stack import Stack

logger = logging.getLogger(__name__)


def load_stack(path: Path) -> Stack | None:
    """Load a single stack definition from a YAML file.

    Args:
        path: Path to stack.yml file.

    Returns:
        Stack model, or None if loading fails.
    """
    try:
        raw = path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw)
        if not isinstance(data, dict):
            logger.warning("Stack file %s is not a mapping, skipping", path)
            return None
        stack = Stack.model_validate(data)
        logger.debug("Loaded stack: %s from %s", stack.name, path)
        return stack
    except Exception as e:
        logger.warning("Failed to load stack from %s: %s", path, e)
        return None


def discover_stacks(stacks_dir: Path) -> dict[str, Stack]:
    """Discover, load, and resolve all stack definitions.

    Expects structure::

        stacks/
            python/
                stack.yml
            python-flask/
                stack.yml          # parent: python
            ...

    Resolution:
        1. Load all raw stack.yml files
        2. Resolve parent references (merge capabilities, detection, etc.)
        3. Order by specificity (flavored stacks before base stacks)

    Returns pre-resolved, flat stacks.  Consumers never see parent refs.
    """
    raw = _load_all(stacks_dir)
    resolved = _resolve_parents(raw)
    logger.info("Discovered %d stacks: %s", len(resolved), list(resolved.keys()))
    return resolved


def _load_all(stacks_dir: Path) -> dict[str, Stack]:
    """Walk stacks/ and load every stack.yml."""
    stacks: dict[str, Stack] = {}

    if not stacks_dir.is_dir():
        logger.debug("Stacks directory not found: %s", stacks_dir)
        return stacks

    for child in sorted(stacks_dir.iterdir()):
        if not child.is_dir():
            continue
        stack_file = child / "stack.yml"
        if not stack_file.is_file():
            stack_file = child / "stack.yaml"
        if not stack_file.is_file():
            continue

        stack = load_stack(stack_file)
        if stack:
            stacks[stack.name] = stack

    return stacks


def _resolve_parents(raw: dict[str, Stack]) -> dict[str, Stack]:
    """Resolve parent references and merge inherited fields.

    Merge rules:
        domain      child's value if non-empty and != "service" default, else parent's
        icon        child's if set, else parent's
        requires    parent list + child list (dedup by adapter, child wins)
        detection   UNION — files_any_of and files_all_of concatenated,
                    content_contains merged (child wins on conflict)
        capabilities  parent list with child entries overriding by name,
                      child extras appended
    """
    resolved: dict[str, Stack] = {}

    for name, stack in raw.items():
        if not stack.parent:
            # Base stack — no resolution needed
            resolved[name] = stack
            continue

        parent = raw.get(stack.parent)
        if parent is None:
            logger.warning(
                "Stack '%s' declares parent '%s' which does not exist; "
                "loading as base stack",
                name, stack.parent,
            )
            resolved[name] = stack
            continue

        # ── Merge ────────────────────────────────────────────────

        # Icon: child overrides, else inherit
        merged_icon = stack.icon or parent.icon

        # Detail: child overrides, else inherit parent's
        merged_detail = stack.detail or parent.detail

        # Domain: inherit parent's unless child explicitly sets a different one
        merged_domain = stack.domain if stack.domain != "service" else parent.domain

        # Requires: parent + child, child adapter wins on conflict
        parent_reqs = {r.adapter: r for r in parent.requires}
        for r in stack.requires:
            parent_reqs[r.adapter] = r
        merged_requires = list(parent_reqs.values())

        # Detection: union of rules
        merged_detection = _merge_detection(parent.detection, stack.detection)

        # Capabilities: parent base, child overrides by name
        merged_caps = _merge_capabilities(parent.capabilities, stack.capabilities)

        resolved[name] = Stack(
            name=name,
            description=stack.description,
            detail=merged_detail,
            domain=merged_domain,
            icon=merged_icon,
            parent=stack.parent,  # keep for reference (consumers can ignore)
            requires=merged_requires,
            detection=merged_detection,
            capabilities=merged_caps,
        )

    # ── Ordering: flavored stacks first for detection specificity ──
    bases = {k: v for k, v in resolved.items() if not v.parent}
    flavors = {k: v for k, v in resolved.items() if v.parent}
    ordered: dict[str, Stack] = {}
    ordered.update(flavors)
    ordered.update(bases)
    return ordered


def _merge_detection(
    parent: "DetectionRule", child: "DetectionRule"
) -> "DetectionRule":
    """Merge parent and child detection rules.

    files_any_of/files_all_of are concatenated (deduped).
    content_contains dicts are merged (child wins on conflict).
    """
    from src.core.models.stack import DetectionRule

    merged_any = list(dict.fromkeys(parent.files_any_of + child.files_any_of))
    merged_all = list(dict.fromkeys(parent.files_all_of + child.files_all_of))
    merged_cc = {**parent.content_contains, **child.content_contains}

    return DetectionRule(
        files_any_of=merged_any,
        files_all_of=merged_all,
        content_contains=merged_cc,
    )


def _merge_capabilities(
    parent_caps: list["StackCapability"],
    child_caps: list["StackCapability"],
) -> list["StackCapability"]:
    """Merge capabilities: parent base, child overrides by name.

    If a child declares a capability with the same name as the parent's,
    the child's version fully replaces it.  Child extras are appended.
    """
    # Preserve parent order, override by name
    merged: dict[str, "StackCapability"] = {c.name: c for c in parent_caps}
    for c in child_caps:
        merged[c.name] = c
    return list(merged.values())

