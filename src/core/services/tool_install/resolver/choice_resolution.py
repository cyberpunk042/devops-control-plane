"""
L2 Resolver — Choice and input resolution.

Resolves user choices and input values into concrete plan parameters.
"""

from __future__ import annotations

import logging
import re
import shutil
import time
from typing import Any

from src.core.services.tool_install.data.constants import _VERSION_FETCH_CACHE
from src.core.services.tool_install.data.recipes import TOOL_RECIPES
from src.core.services.tool_install.resolver.dependency_collection import _can_reach

logger = logging.getLogger(__name__)


def _resolve_choice_option(
    option: dict,
    system_profile: dict,
) -> dict:
    """Evaluate a single choice option against the system profile.

    Checks ``requires.network``, ``requires.platforms``,
    ``requires.binaries``, and ``requires.hardware`` constraints.
    Returns the option dict enriched with ``available``,
    ``disabled_reason``, ``enable_hint``, ``failed_constraint``,
    and ``all_failures`` fields.

    Options are NEVER removed — they are returned disabled with reasons.
    All constraint checks run (not short-circuit) to build full
    ``all_failures`` list.
    """
    failures: list[dict] = []

    reqs = option.get("requires", {})

    # ── Network endpoints (reachability probe) ──
    for endpoint in reqs.get("network", []):
        if not _can_reach(endpoint):
            failures.append({
                "constraint": "network",
                "reason": f"Cannot reach {endpoint}",
                "hint": "Check network/proxy settings",
            })

    # ── Platform constraints ──
    platforms = reqs.get("platforms", [])
    if platforms:
        family = system_profile.get("distro_family", "")
        if family not in platforms:
            failures.append({
                "constraint": "platform",
                "reason": f"Not available on {family}",
                "hint": f"Available on: {', '.join(platforms)}",
            })

    # ── Binary requirements ──
    for binary in reqs.get("binaries", []):
        if not shutil.which(binary):
            failures.append({
                "constraint": "binary",
                "reason": f"Requires {binary}",
                "hint": f"Install {binary} first",
            })

    # ── Hardware requirements ──
    hw = reqs.get("hardware", {})
    if isinstance(hw, dict):
        for key, expected in hw.items():
            # Dot-path resolution into system_profile
            parts = key.split(".")
            val = system_profile
            for p in parts:
                if isinstance(val, dict):
                    val = val.get(p)
                else:
                    val = None
                    break

            if val is None:
                failures.append({
                    "constraint": "hardware",
                    "reason": f"Hardware not detected: {key}",
                    "hint": f"Requires {key} = {expected}",
                })
            elif isinstance(expected, bool):
                if bool(val) != expected:
                    failures.append({
                        "constraint": "hardware",
                        "reason": f"{key} is {val}, requires {expected}",
                        "hint": f"Requires {key} = {expected}",
                    })
            elif isinstance(expected, str) and expected.startswith(">="):
                try:
                    if float(val) < float(expected[2:]):
                        failures.append({
                            "constraint": "hardware",
                            "reason": f"{key} is {val}, requires {expected}",
                            "hint": f"Upgrade {key} to {expected}",
                        })
                except (ValueError, TypeError):
                    failures.append({
                        "constraint": "hardware",
                        "reason": f"Cannot compare {key}: {val}",
                        "hint": f"Check {key} value",
                    })
    elif isinstance(hw, list):
        for h in hw:
            gpu = system_profile.get("gpu", {})
            found = False
            if "nvidia" in h.lower() and gpu.get("nvidia", {}).get("present"):
                found = True
            elif "amd" in h.lower() and gpu.get("amd", {}).get("present"):
                found = True
            elif "intel" in h.lower() and gpu.get("intel", {}).get("present"):
                found = True
            if not found:
                failures.append({
                    "constraint": "hardware",
                    "reason": f"No {h} detected",
                    "hint": f"Install {h} hardware to enable",
                })

    available = len(failures) == 0

    return {
        **option,
        "available": available if not option.get("_force_available") else True,
        "disabled_reason": failures[0]["reason"] if failures else None,
        "enable_hint": failures[0]["hint"] if failures else None,
        "failed_constraint": failures[0]["constraint"] if failures else None,
        "all_failures": failures if len(failures) > 1 else None,
    }


def _resolve_single_choice(
    choice: dict,
    system_profile: dict,
) -> dict:
    """Resolve a single choice — evaluate all options for availability.

    Returns the choice dict with resolved ``options`` list where each
    option has ``available``, ``disabled_reason``, and ``enable_hint``.
    Also determines the default value.
    """
    resolved_options = []
    default_value = None

    for opt in choice.get("options", []):
        resolved = _resolve_choice_option(opt, system_profile)
        resolved_options.append(resolved)

        # Track default
        if opt.get("default") and resolved["available"]:
            default_value = opt["id"] if "id" in opt else opt.get("value")

    # If no explicit default, pick first available
    if default_value is None:
        for opt in resolved_options:
            if opt["available"]:
                default_value = opt.get("id", opt.get("value"))
                break

    # Auto-select: if exactly one option is available, auto-select it
    available_opts = [o for o in resolved_options if o["available"]]
    auto_selected = len(available_opts) == 1

    return {
        **choice,
        "options": resolved_options,
        "default": default_value,
        "auto_selected": auto_selected,
    }


def _input_condition_met(
    inp: dict,
    answers: dict,
    system_profile: dict,
) -> bool:
    """Check if an input field should be shown based on its condition.

    Conditions can reference:
      - Other choice answers: ``{"choice": "method", "equals": "source"}``
      - System profile values: ``{"profile": "has_systemd", "equals": True}``
      - Logical operators (future): ``{"and": [...]}``

    Returns True if the input should be shown.
    """
    cond = inp.get("condition")
    if not cond:
        return True

    if isinstance(cond, str):
        # Simple profile flag: "has_systemd"
        return bool(system_profile.get("capabilities", {}).get(cond))

    if isinstance(cond, dict):
        # Choice-dependent: {"choice": "method", "equals": "source"}
        if "choice" in cond:
            choice_id = cond["choice"]
            expected = cond.get("equals")
            actual = answers.get(choice_id)
            if expected is not None:
                return actual == expected
            # "not_equals"
            not_expected = cond.get("not_equals")
            if not_expected is not None:
                return actual != not_expected
            return actual is not None

        # Profile-dependent: {"profile": "has_systemd", "equals": True}
        if "profile" in cond:
            key = cond["profile"]
            expected = cond.get("equals")
            parts = key.split(".")
            val = system_profile
            for p in parts:
                if isinstance(val, dict):
                    val = val.get(p)
                else:
                    val = None
                    break
            if expected is not None:
                return val == expected
            return bool(val)

    return True


def resolve_choices(
    tool: str,
    system_profile: dict,
) -> dict:
    """Pass 1 — Extract choices the user must make before installation.

    Reads the recipe's ``choices`` and ``inputs`` fields, evaluates
    constraints against the system profile, and returns a decision tree
    for the frontend to render.

    If the recipe has NO choices → returns ``auto_resolve: True`` so the
    frontend can skip the choice modal and go straight to the plan.

    Args:
        tool: Tool ID.
        system_profile: Phase 1 ``_detect_os()`` output.

    Returns::

        {
            "tool": "docker",
            "label": "Docker",
            "choices": [...],
            "inputs": [...],
            "defaults": {...},
            "auto_resolve": False,
        }
    """
    recipe = TOOL_RECIPES.get(tool)
    if not recipe:
        return {"tool": tool, "error": f"No recipe for '{tool}'."}

    # Check if already installed
    cli = recipe.get("cli", tool)
    if shutil.which(cli):
        return {
            "tool": tool,
            "label": recipe["label"],
            "already_installed": True,
            "auto_resolve": True,
            "choices": [],
            "inputs": [],
            "defaults": {},
        }

    raw_choices = recipe.get("choices", [])
    raw_inputs = recipe.get("inputs", [])

    # No choices → auto-resolve
    if not raw_choices and not raw_inputs:
        return {
            "tool": tool,
            "label": recipe["label"],
            "auto_resolve": True,
            "choices": [],
            "inputs": [],
            "defaults": {},
        }

    # Resolve each choice
    resolved_choices = []
    defaults: dict[str, Any] = {}

    # ── Version choice (if present) ──
    version_choice = recipe.get("version_choice")
    if version_choice:
        source = version_choice.get("source", "static")
        if source == "static":
            # Static version list — convert to standard choice format
            vc_options = version_choice.get("options", [])
            vc_as_choice = {
                "id": "version",
                "label": version_choice.get("label", "Version"),
                "type": "single",
                "options": [
                    {
                        "id": opt["id"],
                        "label": opt.get("label", opt["id"]),
                        "default": opt.get("default", False),
                        "warning": opt.get("warning"),
                        "requires": opt.get("requires", {}),
                    }
                    for opt in vc_options
                ],
            }
            resolved = _resolve_single_choice(vc_as_choice, system_profile)
            resolved_choices.append(resolved)
            if resolved.get("default") is not None:
                defaults["version"] = resolved["default"]
        elif source == "package_manager":
            # Let the PM decide — no user choice needed
            defaults["version"] = "latest"
        elif source == "dynamic":
            # Dynamic version fetch from GitHub releases API
            repo = version_choice.get("github_repo", "")
            cache_ttl = version_choice.get("cache_ttl", 3600)
            max_versions = version_choice.get("max_versions", 10)
            asset_pattern = version_choice.get("asset_pattern", "")

            dynamic_options: list[dict] = []
            fetch_error: str | None = None

            if repo:
                # Check cache first
                cache_key = f"version_fetch:{repo}"
                cached = _VERSION_FETCH_CACHE.get(cache_key)
                if cached and (time.time() - cached["ts"]) < cache_ttl:
                    dynamic_options = cached["options"]
                else:
                    # Fetch from GitHub API
                    try:
                        import urllib.request
                        import json as _json

                        api_url = f"https://api.github.com/repos/{repo}/releases"
                        req = urllib.request.Request(
                            api_url,
                            headers={
                                "Accept": "application/vnd.github.v3+json",
                                "User-Agent": "devops-cp/1.0",
                            },
                        )
                        with urllib.request.urlopen(req, timeout=10) as resp:
                            releases = _json.loads(resp.read())

                        for rel in releases[:max_versions]:
                            tag = rel.get("tag_name", "")
                            if not tag:
                                continue
                            ver = tag.lstrip("v")
                            dynamic_options.append({
                                "id": ver,
                                "label": f"{ver}" + (" (latest)" if rel == releases[0] else ""),
                                "default": rel == releases[0],
                                "prerelease": rel.get("prerelease", False),
                            })

                        # Cache the results
                        _VERSION_FETCH_CACHE[cache_key] = {
                            "ts": time.time(),
                            "options": dynamic_options,
                        }
                    except Exception as exc:
                        fetch_error = str(exc)[:100]
                        logger.warning(
                            "Dynamic version fetch failed for %s: %s",
                            repo, fetch_error,
                        )

            if dynamic_options:
                # Build a real choice from fetched versions
                vc_options_resolved = []
                for opt in dynamic_options:
                    resolved_opt = _resolve_choice_option(opt, system_profile)
                    # Pre-release versions get a warning
                    if opt.get("prerelease"):
                        resolved_opt["warning"] = "Pre-release version"
                    vc_options_resolved.append(resolved_opt)

                vc_resolved = {
                    "id": "version",
                    "label": version_choice.get("label", "Version"),
                    "type": "single",
                    "options": vc_options_resolved,
                    "default": dynamic_options[0]["id"],
                    "source": "dynamic",
                    "github_repo": repo,
                    "cache_ttl": cache_ttl,
                }
                resolved_choices.append(vc_resolved)
                defaults["version"] = dynamic_options[0]["id"]
            else:
                # Fallback: single "latest" option
                resolved_choices.append({
                    "id": "version",
                    "label": version_choice.get("label", "Version"),
                    "type": "single",
                    "options": [{
                        "id": "latest",
                        "label": "Latest",
                        "available": True,
                        "default": True,
                        "disabled_reason": None,
                        "enable_hint": None,
                    }],
                    "default": "latest",
                    "auto_selected": True,
                    "source": "dynamic",
                    "fetch_error": fetch_error,
                })
                defaults["version"] = "latest"

    for choice in raw_choices:
        resolved = _resolve_single_choice(choice, system_profile)
        resolved_choices.append(resolved)
        if resolved.get("default") is not None:
            defaults[choice["id"]] = resolved["default"]

    # Filter inputs by conditions (using defaults as initial answers)
    visible_inputs = []
    for inp in raw_inputs:
        if _input_condition_met(inp, defaults, system_profile):
            visible_inputs.append(inp)
            if "default" in inp:
                defaults[inp["id"]] = inp["default"]

    # Check if ALL choices are forced (only one available option each)
    all_forced = True
    for choice in resolved_choices:
        available_opts = [o for o in choice["options"] if o["available"]]
        if len(available_opts) != 1:
            all_forced = False
            break

    return {
        "tool": tool,
        "label": recipe["label"],
        "auto_resolve": all_forced and not visible_inputs,
        "choices": resolved_choices,
        "inputs": visible_inputs,
        "defaults": defaults,
    }


def _apply_choices(
    recipe: dict,
    answers: dict,
) -> dict:
    """Apply user's choice answers to produce a flattened recipe.

    For each choice in the recipe, the user's answer selects a branch.
    Fields that are keyed by choice ID are resolved to the selected value.

    Handles:
      - ``install_variants`` → selects the right install commands
      - ``needs_sudo`` dict-of-variants → selects the right sudo flag
      - ``verify`` dict-of-variants → selects the right verify command
      - ``post_install`` dict-of-variants → selects the right post-install
      - ``data_packs`` filtered by selection

    Returns a new recipe dict with choices resolved.
    """
    resolved = dict(recipe)

    # If recipe has install_variants keyed by choice answers
    install_variants = recipe.get("install_variants", {})
    if install_variants:
        # Find which choice answer picks the variant
        for choice in recipe.get("choices", []):
            cid = choice["id"]
            answer = answers.get(cid)
            if answer and answer in install_variants:
                variant = install_variants[answer]

                # Variant can be a dict with "command" or "steps"
                if "steps" in variant:
                    # Multi-step variant — convert to install format
                    resolved["_resolved_steps"] = variant["steps"]
                elif "command" in variant:
                    resolved["install"] = {"_default": variant["command"]}
                    if "needs_sudo" in variant:
                        resolved["needs_sudo"] = {
                            "_default": variant["needs_sudo"]
                        }

                # Resolve post_install for this variant
                post_install = recipe.get("post_install", {})
                if isinstance(post_install, dict) and answer in post_install:
                    resolved["post_install"] = post_install[answer]

                # Resolve verify for this variant
                verify = recipe.get("verify", {})
                if isinstance(verify, dict) and answer in verify:
                    resolved["verify"] = verify[answer]

                break

    return resolved


def _apply_inputs(
    recipe: dict,
    answers: dict,
) -> dict:
    """Substitute user input values into recipe commands.

    Template variables use ``{input_id}`` syntax in commands, configs,
    and paths. Also provides built-in variables:
      - ``{user}`` — current username
      - ``{home}`` — home directory
      - ``{arch}`` — CPU architecture (amd64/arm64)
      - ``{nproc}`` — number of CPU cores

    Returns a new recipe dict with templates substituted.
    """
    import os
    import multiprocessing

    # Build substitution map: user answers + built-in variables
    subs: dict[str, str] = {
        "user": os.environ.get("USER", "unknown"),
        "home": os.path.expanduser("~"),
        "arch": os.uname().machine,
        "nproc": str(multiprocessing.cpu_count()),
    }
    subs.update({k: str(v) for k, v in answers.items()})

    def _sub_str(s: str) -> str:
        """Substitute {var} placeholders in a string."""
        for key, val in subs.items():
            s = s.replace("{" + key + "}", val)
        return s

    def _sub_list(lst: list) -> list:
        """Recursively substitute in a list (command args)."""
        result = []
        for item in lst:
            if isinstance(item, str):
                result.append(_sub_str(item))
            elif isinstance(item, list):
                result.append(_sub_list(item))
            elif isinstance(item, dict):
                result.append(_sub_dict(item))
            else:
                result.append(item)
        return result

    def _sub_dict(d: dict) -> dict:
        """Recursively substitute in a dict."""
        result = {}
        for k, v in d.items():
            if isinstance(v, str):
                result[k] = _sub_str(v)
            elif isinstance(v, list):
                result[k] = _sub_list(v)
            elif isinstance(v, dict):
                result[k] = _sub_dict(v)
            else:
                result[k] = v
        return result

    return _sub_dict(recipe)
