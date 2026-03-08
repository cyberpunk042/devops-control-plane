"""
Scripts data models — ScriptMeta, ScriptParameter, ScriptConfig.

Pure data shapes with no I/O. These define how scripts are described
(ScriptMeta), what parameters they accept (ScriptParameter), and
how the system is configured (ScriptConfig from project.yml).

Used by:
  - registry.py (discovery produces ScriptMeta instances)
  - config.py (loads ScriptConfig from project.yml)
  - executor.py (reads ScriptMeta for execution)
  - output_router.py (reads ScriptMeta.default_output)
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ── Script Parameter ────────────────────────────────────────────────


@dataclass
class ScriptParameter:
    """A declared parameter for a script.

    Used for:
    - CLI flag generation (--output, --scope, etc.)
    - Form field rendering in admin panel (M4)
    - Validation before execution

    Parsed from @param declarations in the script's @script header.
    Example header line:
        @param output: path = docs/diagrams/ | Output directory for diagrams
    """

    name: str                                   # Parameter name (e.g., "output")
    type: str = "string"                        # "string" | "path" | "boolean" | "choice" | "integer"
    description: str = ""                       # Help text
    required: bool = False                      # Must be provided
    default: str = ""                           # Default value (as string)
    choices: list[str] = field(default_factory=list)
                                                # Valid values for "choice" type


# ── Script Metadata ─────────────────────────────────────────────────


@dataclass
class ScriptMeta:
    """Metadata for a registered script.

    Every script in the system — whether from root scripts/ or from
    templates — has a ScriptMeta describing it. This is what the
    registry stores, the executor reads, and the UI displays.

    Populated by parse_script_meta() in registry.py, which reads @script
    headers from the script file.
    """

    # ── Identity ──────────────────────────────────────────────────
    id: str                                     # Unique identifier (derived from filename)
                                                # e.g., "00_class_diagrams" or "audit/route_quality"
    name: str                                   # Human-readable name
                                                # e.g., "Class Diagram Generator"
    description: str = ""                       # One-paragraph description of what this does

    # ── Classification ────────────────────────────────────────────
    category: str = "general"                   # "audit" | "generator" | "analyzer" | "debug" | "ops" | "general"
    tags: list[str] = field(default_factory=list)
                                                # Free-form tags for filtering
                                                # e.g., ["mermaid", "diagrams", "docs"]

    # ── Execution ─────────────────────────────────────────────────
    language: str = "python"                    # "python" | "bash" | "powershell" | "executable"
    mode: str = "fully_automated"               # "fully_automated" | "semi_automated" | "interactive"
    timeout: int = 300                          # Max execution time in seconds

    # ── Parameters ────────────────────────────────────────────────
    parameters: list[ScriptParameter] = field(default_factory=list)
                                                # Declared parameters the script accepts
                                                # Rendered as form fields in UI, CLI flags

    # ── Output ────────────────────────────────────────────────────
    default_output: str = ""                    # Default output directory/path
                                                # e.g., "docs/diagrams/" for class diagrams
    output_formats: list[str] = field(default_factory=list)
                                                # Supported output formats
                                                # e.g., ["mermaid", "json", "markdown"]

    # ── Source ────────────────────────────────────────────────────
    source: str = "root"                        # "root" | "template" | "override"
                                                # "root" = from scripts/ directory
                                                # "template" = from program templates
                                                # "override" = root script overriding a template
    path: str = ""                              # Absolute path to the script file on disk
    relative_path: str = ""                     # Path relative to its source root
                                                # e.g., "00_class_diagrams.py" or "audit/route_quality.py"

    # ── Override ──────────────────────────────────────────────────
    override_target: str = ""                   # Template ID this script overrides (if any)
                                                # e.g., "generators/class_diagrams"
                                                # Empty = no override, this is a standalone script

    # ── Dependencies ──────────────────────────────────────────────
    dependencies: list[str] = field(default_factory=list)
                                                # Other script IDs this depends on
                                                # e.g., ["00_class_diagrams"] for a diagram auditor
    requires_tools: list[str] = field(default_factory=list)
                                                # External tools needed
                                                # e.g., ["pyreverse"] or ["pwsh"]

    # ── Numbering ─────────────────────────────────────────────────
    number: int | None = None                   # Extracted from filename prefix (00, 01, ...)
                                                # None = unnumbered (temporary/one-off)
    is_permanent: bool = False                  # True if numbered (part of official toolkit)


# ── System Configuration ────────────────────────────────────────────


@dataclass
class ScriptConfig:
    """Configuration for the script system.

    Read from project.yml scripts: section.
    Mirrors the YAML schema defined in the M1 plan §2.1.

    Provides sensible defaults — the system works even if the
    scripts: section is missing from project.yml.
    """

    # ── Paths ─────────────────────────────────────────────────────
    root: str = "scripts"                       # Where project scripts live
    template_source: str = "auto"               # "auto" | "always" | "never"
    default_output: str = "scripts/output"      # Default output directory

    # ── History ───────────────────────────────────────────────────
    history_max_runs: int = 100                 # Max execution records
    history_persist_output: bool = True         # Keep old output files

    # ── Execution ─────────────────────────────────────────────────
    execution_default_timeout: int = 300        # Default timeout (seconds)
    execution_parallel: bool = False            # Allow parallel execution
    execution_venv_python: str = "auto"         # Python executable

    # ── Categories ────────────────────────────────────────────────
    categories: list[str] = field(default_factory=lambda: [
        "audit", "generator", "analyzer", "debug", "ops", "general",
    ])
