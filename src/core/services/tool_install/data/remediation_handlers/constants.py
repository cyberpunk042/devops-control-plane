"""
L0 Data — Remediation handler constants.

Valid values for strategy, availability, and category fields.
Pure data, no logic.
"""

from __future__ import annotations


VALID_STRATEGIES = {
    "install_dep",
    "install_dep_then_switch",
    "install_packages",
    "switch_method",
    "retry_with_modifier",
    "add_repo",
    "upgrade_dep",
    "env_fix",
    "manual",
    "cleanup_retry",
    "retry",
}

VALID_AVAILABILITY = {"ready", "locked", "impossible"}

VALID_CATEGORIES = {
    "environment",
    "dependency",
    "permissions",
    "network",
    "disk",
    "resources",
    "timeout",
    "compiler",
    "package_manager",
    "bootstrap",
    "install",
    "compatibility",
    "configuration",
}
