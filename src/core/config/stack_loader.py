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
    """Discover and load all stack definitions from a directory.

    Expects structure:
        stacks/
            python/
                stack.yml
            node/
                stack.yml
            ...

    Args:
        stacks_dir: Path to the stacks directory.

    Returns:
        Dictionary mapping stack name to Stack model.
    """
    stacks: dict[str, Stack] = {}

    if not stacks_dir.is_dir():
        logger.debug("Stacks directory not found: %s", stacks_dir)
        return stacks

    for child in sorted(stacks_dir.iterdir()):
        if not child.is_dir():
            continue
        stack_file = child / "stack.yml"
        if not stack_file.is_file():
            # Also try stack.yaml
            stack_file = child / "stack.yaml"
        if not stack_file.is_file():
            continue

        stack = load_stack(stack_file)
        if stack:
            stacks[stack.name] = stack

    logger.info("Discovered %d stacks: %s", len(stacks), list(stacks.keys()))
    return stacks
