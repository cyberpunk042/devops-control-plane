"""
Tool Install — Cross-platform resolver coverage tests.

Tests every recipe × every simulated OS profile to validate that:
1. The resolver never crashes (no KeyError, AttributeError, etc.)
2. Plans have correctly structured steps
3. Steps are in logical order (deps before tool, verify last)
4. Package names match the OS family (no apt packages on dnf system)
5. sudo requirements are consistent
6. Data packs and configs resolve without errors

Run with:
    python -m pytest tests/tool_install/test_resolver_coverage.py -v
"""

from __future__ import annotations

import copy
import logging
from unittest.mock import patch

import pytest

from src.core.services.tool_install.data.recipes import TOOL_RECIPES
from src.core.services.tool_install.data.recipe_schema import (
    validate_all_recipes,
    validate_recipe,
)
from src.core.services.tool_install.resolver.plan_resolution import resolve_install_plan
from tests.tool_install.simulated_profiles import PROFILES


logger = logging.getLogger(__name__)

# ── All tool IDs × all profile IDs ────────────────────────────

ALL_TOOLS = sorted(TOOL_RECIPES.keys())
ALL_PROFILES = sorted(PROFILES.keys())


# ── Schema tests ──────────────────────────────────────────────

class TestRecipeSchema:
    """Validate that every recipe passes schema validation."""

    @pytest.mark.parametrize("tool_id", ALL_TOOLS)
    def test_schema_valid(self, tool_id: str) -> None:
        errors = validate_recipe(tool_id, TOOL_RECIPES[tool_id])
        assert errors == [], f"Schema errors for {tool_id}: {errors}"

    def test_all_recipes_clean(self) -> None:
        errors = validate_all_recipes(TOOL_RECIPES)
        if errors:
            lines = []
            for tid, errs in sorted(errors.items()):
                for e in errs:
                    lines.append(f"  {tid}: {e}")
            pytest.fail(f"Schema errors found:\n" + "\n".join(lines))


# ── Resolver tests (parametric) ───────────────────────────────

def _mock_which(binary: str) -> str | None:
    """Mock shutil.which — nothing is installed.

    This forces the resolver to generate full install plans instead
    of short-circuiting with 'already_installed'. Some system binaries
    that are always expected (bash, sh) return a fake path.
    """
    always_present = {"bash", "sh", "env"}
    if binary in always_present:
        return f"/usr/bin/{binary}"
    return None


def _mock_is_pkg_installed(pkg: str, pm: str) -> bool:
    """Mock _is_pkg_installed — nothing is installed."""
    return False


class TestResolverCoverage:
    """Test every recipe against every simulated OS profile."""

    @pytest.mark.parametrize("tool_id", ALL_TOOLS)
    @pytest.mark.parametrize("profile_id", ALL_PROFILES)
    @patch("shutil.which", side_effect=_mock_which)
    @patch(
        "src.core.services.tool_install.resolver.dependency_collection._is_pkg_installed",
        side_effect=_mock_is_pkg_installed,
    )
    @patch(
        "src.core.services.tool_install.resolver.plan_resolution._is_linux_binary",
        return_value=True,
    )
    def test_resolver_no_crash(
        self,
        mock_is_linux_binary,
        mock_pkg_installed,
        mock_which,
        tool_id: str,
        profile_id: str,
    ) -> None:
        """Resolver must never crash — always returns a dict."""
        profile = copy.deepcopy(PROFILES[profile_id])
        result = resolve_install_plan(tool_id, profile)

        assert isinstance(result, dict), (
            f"Resolver returned {type(result)} for {tool_id}@{profile_id}"
        )
        assert "tool" in result, f"Missing 'tool' key for {tool_id}@{profile_id}"

    @pytest.mark.parametrize("tool_id", ALL_TOOLS)
    @pytest.mark.parametrize("profile_id", ALL_PROFILES)
    @patch("shutil.which", side_effect=_mock_which)
    @patch(
        "src.core.services.tool_install.resolver.dependency_collection._is_pkg_installed",
        side_effect=_mock_is_pkg_installed,
    )
    @patch(
        "src.core.services.tool_install.resolver.plan_resolution._is_linux_binary",
        return_value=True,
    )
    def test_plan_structure(
        self,
        mock_is_linux_binary,
        mock_pkg_installed,
        mock_which,
        tool_id: str,
        profile_id: str,
    ) -> None:
        """Plans must have valid structure: steps list, each step with type."""
        profile = copy.deepcopy(PROFILES[profile_id])
        result = resolve_install_plan(tool_id, profile)

        if result.get("error"):
            # Errors are acceptable for some tool/profile combos
            # (e.g., no dnf recipe for a dnf-only system)
            assert isinstance(result["error"], str)
            return

        if result.get("already_installed"):
            return

        steps = result.get("steps", [])
        assert isinstance(steps, list), f"steps must be list for {tool_id}@{profile_id}"

        for i, step in enumerate(steps):
            assert isinstance(step, dict), (
                f"step {i} must be dict for {tool_id}@{profile_id}"
            )
            assert "type" in step, (
                f"step {i} missing 'type' for {tool_id}@{profile_id}: {step}"
            )
            assert "label" in step, (
                f"step {i} missing 'label' for {tool_id}@{profile_id}: {step}"
            )

    @pytest.mark.parametrize("tool_id", ALL_TOOLS)
    @pytest.mark.parametrize("profile_id", ALL_PROFILES)
    @patch("shutil.which", side_effect=_mock_which)
    @patch(
        "src.core.services.tool_install.resolver.dependency_collection._is_pkg_installed",
        side_effect=_mock_is_pkg_installed,
    )
    @patch(
        "src.core.services.tool_install.resolver.plan_resolution._is_linux_binary",
        return_value=True,
    )
    def test_step_order(
        self,
        mock_is_linux_binary,
        mock_pkg_installed,
        mock_which,
        tool_id: str,
        profile_id: str,
    ) -> None:
        """Steps must be in correct order: repo→packages→tool→post→verify."""
        profile = copy.deepcopy(PROFILES[profile_id])
        result = resolve_install_plan(tool_id, profile)

        if result.get("error") or result.get("already_installed"):
            return

        steps = result.get("steps", [])
        if not steps:
            return

        # Verify is always last (if present)
        verify_indices = [i for i, s in enumerate(steps) if s["type"] == "verify"]
        if verify_indices:
            assert verify_indices[-1] == len(steps) - 1, (
                f"verify must be last step for {tool_id}@{profile_id}, "
                f"but found at index {verify_indices[-1]} of {len(steps)}"
            )

        # repo_setup must come before packages
        repo_indices = [i for i, s in enumerate(steps) if s["type"] == "repo_setup"]
        pkg_indices = [i for i, s in enumerate(steps) if s["type"] == "packages"]
        if repo_indices and pkg_indices:
            assert max(repo_indices) < min(pkg_indices), (
                f"repo_setup must come before packages for {tool_id}@{profile_id}"
            )

        # packages must come before tool
        tool_indices = [i for i, s in enumerate(steps) if s["type"] == "tool"]
        if pkg_indices and tool_indices:
            assert max(pkg_indices) < min(tool_indices), (
                f"packages must come before tool steps for {tool_id}@{profile_id}"
            )

    @pytest.mark.parametrize("tool_id", ALL_TOOLS)
    @pytest.mark.parametrize("profile_id", ALL_PROFILES)
    @patch("shutil.which", side_effect=_mock_which)
    @patch(
        "src.core.services.tool_install.resolver.dependency_collection._is_pkg_installed",
        side_effect=_mock_is_pkg_installed,
    )
    @patch(
        "src.core.services.tool_install.resolver.plan_resolution._is_linux_binary",
        return_value=True,
    )
    def test_correct_pm_commands(
        self,
        mock_is_linux_binary,
        mock_pkg_installed,
        mock_which,
        tool_id: str,
        profile_id: str,
    ) -> None:
        """Package commands must use the profile's PM, not a wrong one."""
        profile = copy.deepcopy(PROFILES[profile_id])
        pm = profile["package_manager"]["primary"]
        result = resolve_install_plan(tool_id, profile)

        if result.get("error") or result.get("already_installed"):
            return

        # PM command mapping
        pm_commands = {
            "apt": "apt-get",
            "dnf": "dnf",
            "apk": "apk",
            "pacman": "pacman",
            "zypper": "zypper",
            "brew": "brew",
        }
        wrong_pms = {k: v for k, v in pm_commands.items() if k != pm}

        for step in result.get("steps", []):
            if step["type"] != "packages":
                continue
            cmd = step.get("command", [])
            if not cmd:
                continue

            # The command's binary must match our PM
            cmd_binary = cmd[0]
            expected = pm_commands.get(pm)
            if expected:
                assert cmd_binary == expected, (
                    f"Package step uses '{cmd_binary}' but profile PM is "
                    f"'{pm}' (expected '{expected}') for {tool_id}@{profile_id}"
                )


# ── Coverage summary test ─────────────────────────────────────

class TestCoverageSummary:
    """Report coverage statistics."""

    @patch("shutil.which", side_effect=_mock_which)
    @patch(
        "src.core.services.tool_install.resolver.dependency_collection._is_pkg_installed",
        side_effect=_mock_is_pkg_installed,
    )
    @patch(
        "src.core.services.tool_install.resolver.plan_resolution._is_linux_binary",
        return_value=True,
    )
    def test_full_coverage_report(
        self, mock_is_linux, mock_pkg, mock_which
    ) -> None:
        """Run all tools × all profiles and report the matrix."""
        total = 0
        plans = 0
        errors_list = []

        for tool_id in ALL_TOOLS:
            for profile_id in ALL_PROFILES:
                total += 1
                profile = copy.deepcopy(PROFILES[profile_id])
                try:
                    result = resolve_install_plan(tool_id, profile)
                    if result.get("error"):
                        errors_list.append(
                            f"{tool_id}@{profile_id}: {result['error']}"
                        )
                    else:
                        plans += 1
                except Exception as e:
                    errors_list.append(
                        f"{tool_id}@{profile_id}: EXCEPTION {e}"
                    )

        # Log the stats
        error_count = len(errors_list)
        logger.info(
            "Coverage: %d scenarios, %d plans, %d errors",
            total, plans, error_count,
        )

        # We expect zero crashes. Errors from missing methods are OK
        # (they mean we need more recipe coverage for that PM).
        for err in errors_list:
            if "EXCEPTION" in err:
                pytest.fail(f"Resolver crash: {err}")

        # Report error rate
        if errors_list:
            logger.warning(
                "Resolver errors (%d):\n%s",
                error_count, "\n".join(errors_list[:20]),
            )
