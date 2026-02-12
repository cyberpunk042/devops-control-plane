"""
Detection service — discover modules and match stacks.

This is the core intelligence layer that looks at a project's filesystem
and determines what's there. It matches directories against stack
detection rules and enriches module references with discovered state.

Pure logic — no side effects, no persistence.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from src.core.models.module import Module
from src.core.models.project import Project
from src.core.models.stack import Stack

logger = logging.getLogger(__name__)


@dataclass
class DetectionResult:
    """Result of detecting modules in a project."""

    modules: list[Module] = field(default_factory=list)
    unmatched_refs: list[str] = field(default_factory=list)  # declared but path missing
    extra_detections: list[Module] = field(default_factory=list)  # found but undeclared

    @property
    def total_detected(self) -> int:
        return sum(1 for m in self.modules if m.detected)

    @property
    def total_modules(self) -> int:
        return len(self.modules)

    def get_module(self, name: str) -> Module | None:
        for m in self.modules:
            if m.name == name:
                return m
        return None

    def to_dict(self) -> dict:
        return {
            "total": self.total_modules,
            "detected": self.total_detected,
            "unmatched": self.unmatched_refs,
            "modules": [m.model_dump(mode="json") for m in self.modules],
            "extra_detections": [m.model_dump(mode="json") for m in self.extra_detections],
        }


def match_stack(directory: Path, stacks: dict[str, Stack]) -> Stack | None:
    """Match a directory against available stack detection rules.

    Checks each stack's detection rules against the directory contents:
    - files_any_of: at least one must exist
    - files_all_of: all must exist
    - content_contains: file must contain the specified string

    Returns the first matching stack, or None.
    """
    for stack in stacks.values():
        rule = stack.detection

        # Check files_any_of
        if rule.files_any_of and not any(
            (directory / f).exists() for f in rule.files_any_of
        ):
            continue

        # Check files_all_of
        if rule.files_all_of and not all(
            (directory / f).exists() for f in rule.files_all_of
        ):
            continue

        # Check content_contains
        if rule.content_contains:
            content_match = True
            for filename, search_string in rule.content_contains.items():
                filepath = directory / filename
                if not filepath.is_file():
                    content_match = False
                    break
                try:
                    content = filepath.read_text(encoding="utf-8", errors="ignore")
                    if search_string not in content:
                        content_match = False
                        break
                except OSError:
                    content_match = False
                    break
            if not content_match:
                continue

        return stack

    return None


def detect_version(directory: Path, stack_name: str) -> str | None:
    """Try to detect the version of a module from its config files.

    Checks technology-specific marker files in order of specificity.
    """
    # Python: pyproject.toml
    pyproject = directory / "pyproject.toml"
    if pyproject.is_file():
        try:
            content = pyproject.read_text(encoding="utf-8")
            match = re.search(r'version\s*=\s*"([^"]+)"', content)
            if match:
                return match.group(1)
        except OSError:
            pass

    # Node / TypeScript: package.json
    package_json = directory / "package.json"
    if package_json.is_file():
        try:
            import json

            data = json.loads(package_json.read_text(encoding="utf-8"))
            version = data.get("version")
            return str(version) if version is not None else None
        except (OSError, json.JSONDecodeError):
            pass

    # Go: go.mod  →  module version from the go directive
    go_mod = directory / "go.mod"
    if go_mod.is_file():
        try:
            content = go_mod.read_text(encoding="utf-8")
            match = re.search(r"^go\s+(\d+\.\d+(?:\.\d+)?)", content, re.MULTILINE)
            if match:
                return match.group(1)
        except OSError:
            pass

    # Rust: Cargo.toml
    cargo = directory / "Cargo.toml"
    if cargo.is_file():
        try:
            content = cargo.read_text(encoding="utf-8")
            match = re.search(r'version\s*=\s*"([^"]+)"', content)
            if match:
                return match.group(1)
        except OSError:
            pass

    # Elixir: mix.exs  →  version: "x.y.z"
    mix = directory / "mix.exs"
    if mix.is_file():
        try:
            content = mix.read_text(encoding="utf-8")
            match = re.search(r'version:\s*"([^"]+)"', content)
            if match:
                return match.group(1)
        except OSError:
            pass

    # Helm: Chart.yaml
    chart = directory / "Chart.yaml"
    if chart.is_file():
        try:
            content = chart.read_text(encoding="utf-8")
            match = re.search(r"^version:\s*(.+)$", content, re.MULTILINE)
            if match:
                return match.group(1).strip().strip("\"'")
        except OSError:
            pass

    return None


def detect_language(stack_name: str) -> str | None:
    """Infer primary language from stack name.

    Uses prefix matching so stack variants (e.g. python-flask,
    java-maven) automatically resolve to their base language.
    """
    lang_map = {
        # ── Service stacks (languages) ──────────────────────────
        "python": "python",
        "node": "javascript",
        "typescript": "typescript",
        "go": "go",
        "rust": "rust",
        "ruby": "ruby",
        "java": "java",
        "dotnet": "csharp",
        "swift": "swift",
        "elixir": "elixir",
        "zig": "zig",
        "cpp": "cpp",
        "c": "c",
        "protobuf": "protobuf",
        # ── Ops / infra stacks ──────────────────────────────────
        "terraform": "hcl",
        "helm": "yaml",
        "kubernetes": "yaml",
        "docker-compose": None,
        "static-site": "html",
        # ── Docs ────────────────────────────────────────────────
        "markdown": None,
    }
    # Exact match first
    if stack_name in lang_map:
        return lang_map[stack_name]
    # Longest prefix match for variants (e.g. python-flask → python)
    best_match: str | None = None
    best_len = 0
    for prefix, lang in lang_map.items():
        if stack_name.startswith(prefix + "-") and len(prefix) > best_len:
            best_match = lang
            best_len = len(prefix)
    return best_match


def detect_modules(
    project: Project,
    project_root: Path,
    stacks: dict[str, Stack],
) -> DetectionResult:
    """Detect modules declared in the project configuration.

    For each module reference in project.yml:
    1. Check if the path exists
    2. Try to match it against stack detection rules
    3. Extract version information
    4. Build an enriched Module model

    Args:
        project: The loaded project configuration.
        project_root: Absolute path to the project root.
        stacks: Available stack definitions.

    Returns:
        DetectionResult with enriched modules.
    """
    result = DetectionResult()

    for ref in project.modules:
        module_dir = project_root / ref.path

        if not module_dir.is_dir():
            logger.warning("Module '%s' path does not exist: %s", ref.name, ref.path)
            result.unmatched_refs.append(ref.name)
            # Still add the module, but mark as not detected
            result.modules.append(
                Module(
                    name=ref.name,
                    path=ref.path,
                    domain=ref.domain,
                    stack_name=ref.stack,
                    description=ref.description,
                    detected=False,
                )
            )
            continue

        # Try to match stack
        matched_stack = match_stack(module_dir, stacks)

        # Determine effective stack name
        detected_stack_name = matched_stack.name if matched_stack else ""
        effective_stack = detected_stack_name or ref.stack

        # Detect version
        version = detect_version(module_dir, effective_stack)

        # Detect language
        language = detect_language(effective_stack)

        module = Module(
            name=ref.name,
            path=ref.path,
            domain=ref.domain,
            stack_name=ref.stack,
            description=ref.description,
            detected=True,
            detected_stack=detected_stack_name,
            version=version,
            language=language,
        )
        result.modules.append(module)

        logger.info(
            "Detected module '%s': stack=%s, version=%s",
            ref.name,
            module.effective_stack,
            version,
        )

    return result
