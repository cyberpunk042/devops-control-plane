# Scripts System — Milestone 1: The Execution Framework

> **Status**: Planning — Iteration 2
> **Parent**: `.agent/plans/scripts-system.md`
> **Milestone**: M1 — The System itself
> **Depends on**: Nothing (this is the foundation)
> **Unlocks**: M2 (Shared Lib), M3 (Class Diagrams), M4 (Interfaces)

---

## 0. What This Milestone Delivers

After M1 is complete:

1. A `ScriptMeta` model exists — any script can be described with structured metadata
2. A `ScriptConfig` model exists — read from `project.yml` `scripts:` section
3. A `ScriptRegistry` exists — it discovers scripts from two locations (root + templates), merges them, and provides a queryable list
4. A `ScriptExecutor` exists — it can run any registered script as a subprocess, stream events, and capture results
5. An `OutputRouter` exists — it directs script output to the right destination (file, stdout, API)
6. `project.yml` has a proper `scripts:` section (not deferred — first-class citizen)
7. `wizard_detect()` detects the scripts folder and scripts capabilities
8. The scripts devops card appears in the wizard when scripts are detected
9. A `_wizard_scripts_status()` helper provides scripts inventory to the wizard
10. All of this integrates with EXISTING infrastructure:
    - `event_bus.py` (SSE events — `bus.publish()`)
    - `stream_subprocess.py` (subprocess with line-by-line streaming)
    - `run_tracker.py` + `ledger/models.py` (Run tracking, `tracked_run()` context manager)
    - `wizard/detect.py` (wizard detection scan)
    - `wizard/helpers.py` (wizard data helpers)

**What you can do after M1**: Register a script, run it from Python code, see events on SSE, see the run in the ledger, see scripts detected in the wizard. No scripts actually exist yet (that's M2+M3), but the system is ready to host them.

---

## 1. Existing Infrastructure We Build On

These already exist and MUST be reused — not reinvented.

### 1.1 `src/core/services/event_bus.py`

- **Singleton**: `bus = EventBus()` — global, import and use
- **Publish**: `bus.publish("script:started", key=run_id, data={...})`
- **Subscribe**: `bus.subscribe(since=0)` — yields events for SSE clients
- **Event format**: `{type, key, data, seq, ts, schema_v}`
- **Namespace convention**: `<domain>:<action>` — we use `script:*`

**Impact on M1**: The executor publishes `script:*` events to the bus. No new event infrastructure needed.

### 1.2 `src/core/services/stream_subprocess.py`

- **Function**: `stream_run(cmd, cwd, stream_id, timeout, env, label)`
- **Returns**: `{"ok": bool, "exit_code": int, "stream_id": str, "lines": [str], "error"?: str}`
- **Events**: Automatically publishes `stream:start`, `stream:line`, `stream:done` to `bus`
- **Handles**: timeout, FileNotFoundError, OSError — all fail-safe

**Impact on M1**: The executor uses `stream_run()` for subprocess execution. We wrap it with script-specific pre/post logic, but the actual process management is already solved.

### 1.3 `src/core/services/run_tracker.py`

- **Context manager**: `tracked_run(project_root, run_type, subtype, summary=...)` 
- **Does**: Creates a Run model, emits `run:started` and `run:completed`, records to `.state/runs.jsonl`
- **Run types already defined**: `install`, `build`, `deploy`, `test`, `scan`, `generate`
- **Pattern**: `with tracked_run(...) as run:` — the `run` dict is mutable, set status/summary in the block

**Impact on M1**: Every script execution is wrapped in `tracked_run()`. We extend `RUN_TYPES` with a new `"script"` type.

### 1.4 `src/core/services/ledger/models.py`

- **Run model**: Pydantic `Run(type, subtype, status, user, code_ref, started_at, ended_at, duration_ms, summary, metadata)`
- **RunEvent model**: Pydantic `RunEvent(seq, ts, type, adapter, action_id, target, status, duration_ms, detail)`

**Impact on M1**: We don't need new models for the run/event lifecycle — we use the existing ones. We DO need new models for script metadata (ScriptMeta) and script-specific config (ScriptConfig).

### 1.5 `src/core/services/artifacts/engine.py` (Pattern Reference)

- **Data model**: `@dataclass ArtifactTarget` — fields for name, kind, builder, etc.
- **Config I/O**: `_load_project_yml()`, `_get_artifacts_config()`, `_set_artifacts_config()`
- **CRUD**: `get_targets()`, `get_target()`, `add_target()`, `update_target()`, `remove_target()`
- **Build**: `build_target_stream()` — yields JSON events for SSE
- **Status**: `get_build_status()`, `_save_build_status()`

**Impact on M1**: The scripts engine follows the same structural pattern. Config I/O via project.yml, CRUD-style access to scripts, streaming execution.

### 1.6 `src/core/services/wizard/detect.py` (Wizard Detection)

This is the wizard's environment scan. It probes the project for every integration and assembles data for the wizard. Key patterns:

- **Tool availability**: `shutil.which("tool_name")` → `tools["tool_name"]`
- **File/dir detection**: `files["scripts_dir"] = (root / "scripts").is_dir()`
- **Integrations dict**: `integrations["int:scripts"] = {detected, status, suggest, label, ...}`
- **DevOps cards dict**: `devops_cards["scripts"] = {detected, status, suggest, label, ...}`
- **Embedded data**: `_wizard_scripts_status(root)` — returns full scripts inventory at detect time

**Impact on M1**: Scripts MUST appear in this detection. The wizard needs to know:
1. Is there a `scripts/` directory?
2. Does `project.yml` have a `scripts:` section?
3. How many scripts are discovered (root + templates)?
4. What categories are represented?
5. What's the last run status?

### 1.7 `src/core/services/wizard/helpers.py` (Wizard Helpers)

Pattern: each integration has a `_wizard_<name>_status(root)` helper that wraps the service layer call, catches exceptions, returns a safe fallback.

**Impact on M1**: We add `_wizard_scripts_status()` following the same pattern.

### 1.8 `project.yml` (Project Configuration)

Current top-level sections: `version`, `name`, `description`, `repository`, `owners`, `domains`, `environments`, `modules`, `content_folders`, `smart_folders`, `external`, `pages`, `artifacts`, `kubernetes`.

Scripts becomes a peer of `pages` and `artifacts` — same level, same importance.

**Impact on M1**: A `scripts:` section is added to `project.yml` with its own schema. This is NOT deferred.

---

## 2. `project.yml` — The `scripts:` Section

### 2.1 Schema

```yaml
scripts:
  root: scripts                        # Where project scripts live (relative to project root)
                                       # Default: "scripts"
                                       # This is what the wizard content step scan detects
                                       # Must be a real directory path on disk

  template_source: auto                # How template scripts are loaded
                                       # "auto" = auto-load in dev mode, explicit in prod
                                       # "always" = always load templates
                                       # "never" = never load templates (user scripts only)
                                       # Default: "auto"

  default_output: scripts/output       # Default output directory for scripts that don't declare one
                                       # Relative to project root
                                       # Default: "scripts/output"

  history:
    max_runs: 100                      # Max execution records to keep in .state/
                                       # Default: 100
    persist_output: true               # Keep output files from previous runs
                                       # Default: true

  execution:
    default_timeout: 300               # Default timeout in seconds for scripts that don't declare one
                                       # Default: 300 (5 minutes)
    parallel: false                    # Whether to allow parallel script execution
                                       # Default: false (serial — safe default)
    venv_python: auto                  # Python executable for script execution
                                       # "auto" = sys.executable (project venv)
                                       # Explicit path allowed for edge cases
                                       # Default: "auto"

  categories:                          # Recognized script categories
    - audit                            # Compliance and quality checks
    - generator                        # Code/doc generation
    - analyzer                         # Code analysis and reporting
    - debug                            # Debugging utilities
    - general                          # Uncategorized
```

### 2.2 Why This Schema

Every field answers a real operational question:

| Field | Question it answers |
|-------|-------------------|
| `root` | "Where do I put my scripts?" — the wizard scans this path |
| `template_source` | "Can I use shipped templates or only my own?" |
| `default_output` | "Where do script results go by default?" |
| `history.max_runs` | "How many runs do we keep?" — ephemeral storage management |
| `history.persist_output` | "Should old output files be cleaned?" |
| `execution.default_timeout` | "How long before a script is killed?" |
| `execution.parallel` | "Can I run multiple scripts at once?" |
| `execution.venv_python` | "Which Python?" — answers the venv rule |
| `categories` | "What types of scripts exist?" — drives UI filtering |

### 2.3 How It's Read

Same pattern as artifacts — a config loader function:

```python
# In src/core/services/scripts/config.py

def load_scripts_config(project_root: Path) -> ScriptConfig:
    """Load scripts configuration from project.yml.
    
    Falls back to sensible defaults if section is missing.
    """

def save_scripts_config(project_root: Path, config: ScriptConfig) -> None:
    """Write scripts configuration to project.yml."""
```

### 2.4 Default When `scripts:` Section Is Missing

If a project has no `scripts:` section in project.yml, the system uses defaults:

```python
ScriptConfig(
    root="scripts",
    template_source="auto",
    default_output="scripts/output",
    history_max_runs=100,
    history_persist_output=True,
    execution_default_timeout=300,
    execution_parallel=False,
    execution_venv_python="auto",
    categories=["audit", "generator", "analyzer", "debug", "general"],
)
```

This means the system works out of the box — but a project that HAS scripts SHOULD declare the section in project.yml so the wizard detects it as a first-class integration.

---

## 3. Wizard Integration

### 3.1 Detection in `wizard_detect()`

The wizard needs to detect scripts the same way it detects Docker, K8s, Terraform, Pages. This means changes to THREE places in `wizard/detect.py`:

#### 3.1.1 File Detection (Add to `files` dict)

```python
# In wizard_detect(), files dict:
files = {
    # ... existing entries ...
    "scripts_dir":    (root / "scripts").is_dir(),  # Default scripts location
    "scripts_config": _has_scripts_config(root),     # project.yml has scripts: section
}
```

Where `_has_scripts_config()` checks if project.yml has a `scripts:` key:
```python
def _has_scripts_config(root: Path) -> bool:
    """Check if project.yml has a scripts: section."""
    try:
        import yaml
        yml = root / "project.yml"
        if not yml.is_file():
            return False
        data = yaml.safe_load(yml.read_text(encoding="utf-8")) or {}
        return "scripts" in data
    except Exception:
        return False
```

#### 3.1.2 DevOps Cards (Add to `devops_cards` dict)

```python
# In wizard_detect(), devops_cards dict:
devops_cards = {
    # ... existing entries ...
    "scripts": {
        "detected": files["scripts_dir"] or files["scripts_config"],
        "status": (
            "ready" if files["scripts_dir"] and files["scripts_config"]
            else "partial" if files["scripts_dir"] or files["scripts_config"]
            else "available"
        ),
        "suggest": (
            "auto" if files["scripts_dir"]
            else "hidden"
        ),
        "label": "📜 Scripts",
        "has_scripts_dir": files["scripts_dir"],
        "has_scripts_config": files["scripts_config"],
        "setup_actions": (
            ([] if files["scripts_dir"] else ["create_scripts_dir"])
            + ([] if files["scripts_config"] else ["add_scripts_config"])
        ),
    },
}
```

#### 3.1.3 Embedded Data in Return Dict

```python
# In wizard_detect(), return dict:
return {
    # ... existing entries ...
    "scripts_status": _wizard_scripts_status(root),
}
```

### 3.2 `_wizard_scripts_status()` Helper

Added to `wizard/helpers.py`, following the same safe-wrapper pattern:

```python
def _wizard_scripts_status(root: Path) -> dict:
    """Scripts status for wizard use — discovered scripts, categories, last runs."""
    try:
        from src.core.services.scripts.registry import discover_scripts
        from src.core.services.scripts.config import load_scripts_config

        config = load_scripts_config(root)
        scripts = discover_scripts(root, config)

        # Group by category
        by_category: dict[str, int] = {}
        for s in scripts:
            by_category[s.category] = by_category.get(s.category, 0) + 1

        # Source breakdown
        root_count = sum(1 for s in scripts if s.source == "root")
        template_count = sum(1 for s in scripts if s.source == "template")
        override_count = sum(1 for s in scripts if s.source == "override")

        return {
            "ok": True,
            "root_path": config.root,
            "scripts_dir_exists": (root / config.root).is_dir(),
            "total_scripts": len(scripts),
            "by_category": by_category,
            "sources": {
                "root": root_count,
                "template": template_count,
                "override": override_count,
            },
            "scripts": [
                {
                    "id": s.id,
                    "name": s.name,
                    "category": s.category,
                    "source": s.source,
                    "language": s.language,
                    "mode": s.mode,
                }
                for s in scripts
            ],
            "config": {
                "root": config.root,
                "template_source": config.template_source,
                "default_output": config.default_output,
                "default_timeout": config.execution_default_timeout,
            },
        }
    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
            "total_scripts": 0,
            "scripts": [],
        }
```

### 3.3 What the Wizard Can Do With This Data

The wizard content step already scans for Pages segments, content folders, and smart folders. Scripts becomes a peer:

| Wizard Content Section | What's Detected | Source |
|----------------------|-----------------|--------|
| Content Folders | `content_folders:` in project.yml | `_wizard_config_data` |
| Smart Folders | `smart_folders:` in project.yml | `_wizard_config_data` |
| Pages Segments | `pages:` in project.yml + framework scan | `_wizard_pages_status` |
| **Scripts** | `scripts:` in project.yml + scripts/ dir scan | `_wizard_scripts_status` |

The scripts card in the wizard shows:
- How many scripts are discovered
- Breakdown by category
- Whether the scripts/ dir exists
- Whether project.yml has the scripts: section
- Setup actions (create dir, add config)

---

## 4. New Data Models

### 4.1 `ScriptMeta` — What describes a script

This is the metadata that makes a script a first-class citizen in the system.

```python
# src/core/services/scripts/models.py

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ScriptMeta:
    """Metadata for a registered script.
    
    Every script in the system — whether from root scripts/ or from
    templates — has a ScriptMeta describing it. This is what the
    registry stores, the executor reads, and the UI displays.
    """

    # ── Identity ──────────────────────────────────────────────────
    id: str                                     # Unique identifier (derived from filename)
                                                # e.g., "00_class_diagrams" or "audit/route_quality"
    name: str                                   # Human-readable name
                                                # e.g., "Class Diagram Generator"
    description: str = ""                       # One-paragraph description of what this does

    # ── Classification ────────────────────────────────────────────
    category: str = "general"                   # "audit" | "generator" | "analyzer" | "debug" | "general"
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


@dataclass
class ScriptParameter:
    """A declared parameter for a script.
    
    Used for:
    - CLI flag generation (--output, --scope, etc.)
    - Form field rendering in admin panel
    - Validation before execution
    """

    name: str                                   # Parameter name (e.g., "output")
    type: str = "string"                        # "string" | "path" | "boolean" | "choice" | "integer"
    description: str = ""                       # Help text
    required: bool = False                      # Must be provided
    default: str = ""                           # Default value (as string)
    choices: list[str] = field(default_factory=list)
                                                # Valid values for "choice" type
```

### 4.2 `ScriptConfig` — System-level configuration from project.yml

```python
@dataclass
class ScriptConfig:
    """Configuration for the script system.
    
    Read from project.yml scripts: section.
    Mirrors the YAML schema in §2.1 exactly.
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
```

### 4.3 Where script metadata comes from (in-file header)

Scripts declare their metadata via a **structured header comment**. This is parsed by the registry during discovery.

```python
#!/usr/bin/env python3
"""
@script
name: Class Diagram Generator
category: generator
mode: fully_automated
tags: mermaid, diagrams, docs, python
default_output: docs/diagrams/
output_formats: mermaid, json, markdown
requires_tools: (none)
timeout: 120

@param output: path = docs/diagrams/ | Output directory for generated diagrams
@param scope: string | Limit to specific package (e.g., core.services.vault)
@param format: choice = mermaid [mermaid, json, markdown] | Output format
"""

# ... actual script code below ...
```

**Why in-file headers instead of companion files**:
- Script is self-contained — no "orphaned metadata" if the script moves
- Grep-able — you can see metadata with `head -20 *.py`
- Same pattern as Java reference project (scripts had docstrings with structured info)

Detection by extension:
| Extension | Metadata location |
|-----------|------------------|
| `.py` | Module docstring (first triple-quoted string) |
| `.sh`, `.bash` | Leading `#` comment block |
| `.ps1` | `<# comment block #>` |
| No extension | Shebang line determines language, then apply above rules |

#### Shell/Bash header format

```bash
#!/usr/bin/env bash
# @script
# name: Deployment Script
# category: ops
# mode: fully_automated
# tags: deploy, infrastructure
# timeout: 600
#
# @param environment: choice = staging [staging, prod] | Target environment
# @param dry-run: boolean = true | Show what would happen without applying
# @param force: boolean = false | Skip confirmation prompts
```

Same `@script` / `@param` syntax, but in `#` comment lines. The parser strips leading `# ` from each line before parsing. The `@script` marker must appear in the first comment block (before any non-comment code).

#### PowerShell header format (planned — M8)

```powershell
<#
@script
name: Windows Config Audit
category: audit
mode: fully_automated

@param scope: string | Target scope to audit
#>
```

### 4.5 Language Coverage Model

Every language supported by the scripts system is measured against these operability features:

| Feature | ID | Description |
|---------|-----|------------|
| Execution | `exec` | Run as subprocess via appropriate interpreter |
| Streaming | `stream` | Real-time stdout/stderr via event bus |
| Tracking | `track` | Run records in ledger (start, stop, exit code, duration) |
| Output routing | `output` | SCRIPT_OUTPUT_DIR env var, output target resolution |
| Header parsing | `header` | Parse `@script` metadata from file |
| Param extraction | `params` | Extract `@param` declarations for form generation |
| Param form | `form` | Auto-generate UI form from parameters (M4) |
| AST analysis | `ast` | Static code analysis (imports, classes, functions) |

**Coverage per language** (what M1 implements, and total across all milestones):

| Language | exec | stream | track | output | header | params | form | ast | M1 features | Total coverage |
|----------|------|--------|-------|--------|--------|--------|------|-----|-------------|---------------|
| Python | ✅ M1 | ✅ M1 | ✅ M1 | ✅ M1 | ✅ M1 | ✅ M1 | M4 | M2 | 6/6 | 8/8 = **100%** |
| Bash/Shell | ✅ M1 | ✅ M1 | ✅ M1 | ✅ M1 | ✅ M1 | ✅ M1 | M4+ | N/A | 6/6 | 6/7 = **85%** |
| PowerShell | 🔮 M8 | 🔮 M8 | 🔮 M8 | 🔮 M8 | 🔮 M8 | 🔮 M8 | M8 | N/A | 0/6 | 0/7 = **0%** |

**Key insight**: M1 implements header parsing and param extraction for **both** Python and Bash/Shell. The parser reads `#`-prefixed comment blocks for shell scripts the same way it reads `"""`-docstrings for Python. Both languages get the same 6 core features in M1.

AST analysis is N/A for shell (no equivalent of Python's `ast` module) — it's not counted against coverage.

Form generation (auto-UI from params) is an M4 concern — Python gets it in M4, Shell gets it in M4+ (params are extracted in M1, the form adapter just needs to be built).

**The "Total coverage" column is what M4's card displays.** See `scripts-system-M4-interfaces.md` §9 for the full coverage model.

### 4.6 `ScriptRun` — A single execution instance

We do NOT create a new model for this. We use the EXISTING `Run` model from `ledger/models.py` with:
- `type = "script"`
- `subtype = "script:<script_id>"` (e.g., `"script:00_class_diagrams"`)
- `metadata = {script_id, parameters, output_path, stream_id, ...}`

This means script runs automatically appear in:
- The run history (`load_runs()`)
- The ledger branch
- The SSE event stream (`run:started`, `run:completed`)

**The stream_subprocess events** (`stream:start`, `stream:line`, `stream:done`) are published alongside the run events, linked by `stream_id`.

---

## 5. Config I/O — project.yml integration

### 5.1 Config Loader

```python
# src/core/services/scripts/config.py

import yaml
from pathlib import Path
from src.core.services.scripts.models import ScriptConfig


def load_scripts_config(project_root: Path) -> ScriptConfig:
    """Load scripts configuration from project.yml.
    
    Falls back to sensible defaults if section is missing.
    Same pattern as artifacts: _load_project_yml() → _get_section().
    """
    yml = project_root / "project.yml"
    if not yml.is_file():
        return ScriptConfig()

    data = yaml.safe_load(yml.read_text(encoding="utf-8")) or {}
    scripts_data = data.get("scripts", {})
    if not scripts_data:
        return ScriptConfig()

    history = scripts_data.get("history", {})
    execution = scripts_data.get("execution", {})

    return ScriptConfig(
        root=scripts_data.get("root", "scripts"),
        template_source=scripts_data.get("template_source", "auto"),
        default_output=scripts_data.get("default_output", "scripts/output"),
        history_max_runs=history.get("max_runs", 100),
        history_persist_output=history.get("persist_output", True),
        execution_default_timeout=execution.get("default_timeout", 300),
        execution_parallel=execution.get("parallel", False),
        execution_venv_python=execution.get("venv_python", "auto"),
        categories=scripts_data.get("categories", [
            "audit", "generator", "analyzer", "debug", "general",
        ]),
    )


def save_scripts_config(project_root: Path, config: ScriptConfig) -> None:
    """Write scripts configuration to project.yml.
    
    Creates the scripts: section if it doesn't exist.
    Preserves all other sections.
    """
    yml = project_root / "project.yml"
    data = {}
    if yml.is_file():
        data = yaml.safe_load(yml.read_text(encoding="utf-8")) or {}

    data["scripts"] = {
        "root": config.root,
        "template_source": config.template_source,
        "default_output": config.default_output,
        "history": {
            "max_runs": config.history_max_runs,
            "persist_output": config.history_persist_output,
        },
        "execution": {
            "default_timeout": config.execution_default_timeout,
            "parallel": config.execution_parallel,
            "venv_python": config.execution_venv_python,
        },
        "categories": config.categories,
    }

    yml.write_text(
        yaml.dump(data, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
```

---

## 6. Script Registry

### 6.1 Responsibilities

The registry is the **discovery and query layer**. It:

1. Reads config from `project.yml` to know where to look
2. Scans the root `scripts/` directory for script files
3. Scans the template scripts directory for template scripts (based on `template_source` config)
4. Merges them (root overrides templates)
5. Parses metadata from each script's header
6. Provides query functions: list all, filter by category/tag, get by ID

### 6.2 Discovery Logic

```python
# src/core/services/scripts/registry.py

def discover_scripts(
    project_root: Path,
    config: ScriptConfig | None = None,
) -> list[ScriptMeta]:
    """Discover all scripts from root + templates, merge, return metadata list.
    
    Discovery order:
    1. Load config (from project.yml or defaults)
    2. Scan templates (Layer 2) first — unless template_source="never"
    3. Scan root (Layer 1) second — from config.root path
    4. Root overrides templates with matching @override declarations
    
    Scanned file extensions: .py, .sh, .bash, .ps1
    Also scans files with no extension that have a recognized shebang line.
    
    Files without @script headers are silently skipped (helpers, libs, etc.)
    
    Returns:
        List of ScriptMeta, one per discovered script.
    """
```

### 6.3 Two-Layer Folder Architecture

```
Layer 1 (root — user-owned, project-specific):
    <project_root>/<config.root>/          ← e.g., scripts/
    ├── 00_class_diagrams.py               ← Numbered = permanent
    ├── 01_route_audit.py                  ← Numbered = permanent
    ├── deploy.sh                          ← Shell script (also scanned)
    ├── quick_debug.py                     ← No number = temporary/one-off
    └── lib/                               ← Shared modules for root scripts
        └── common_utils.py

Layer 2 (templates — shipped with the program, categorized):
    src/core/data/script_templates/
    ├── lib/                               ← Shared lib modules (M2)
    │   └── ...
    ├── audit/
    │   ├── route_quality.py               ← Route Quality Audit (M5)
    │   ├── route_analyzer.py              ← Co-located helper (M5)
    │   ├── code_hygiene.py                ← Code Hygiene Audit (M6)
    │   ├── init_analyzer.py               ← Co-located helper (M6)
    │   └── doc_validator.py               ← Co-located helper (M6)
    ├── generators/
    │   └── class_diagrams.py              ← Class Diagram Generator (M3)
    └── debug/
        └── state_dump.py                  ← (placeholder for future)
```

### 6.4 Merge Algorithm

```
Input:
    templates/ has: generators/class_diagrams.py, audit/route_quality.py
    scripts/  has: 00_class_diagrams.py (declares @override: generators/class_diagrams)

Step 1: Scan templates
    → generators/class_diagrams.py  → id="generators/class_diagrams", source="template"
    → audit/route_quality.py        → id="audit/route_quality", source="template"

Step 2: Scan root
    → 00_class_diagrams.py          → id="00_class_diagrams", @override="generators/class_diagrams"

Step 3: Apply overrides
    → 00_class_diagrams.py overrides generators/class_diagrams.py
    → generators/class_diagrams is REMOVED from results
    → 00_class_diagrams gets source="override"

Result: 2 scripts total
    - 00_class_diagrams (override — was generators/class_diagrams)
    - audit/route_quality (template)
```

**Override mechanism**: A root script overrides a template by declaring `@override: <template_id>` in its `@script` header. This is explicit, not filename-based. Reasons:
- Explicit is better than implicit (Python zen)
- Filenames can differ between root and templates (numbered vs categorized)
- The override relationship is visible in the script header (auditable, grep-able)

### 6.5 Template Source Resolution

Based on `config.template_source`:

| Value | Behavior |
|-------|----------|
| `"auto"` | Load templates in dev mode, skip in prod. Dev mode = `SCP_DEV=1` env var. |
| `"always"` | Always load templates regardless of mode |
| `"never"` | Never load templates — user scripts only |

### 6.6 Metadata Parser

```python
def parse_script_meta(filepath: Path, source: str) -> ScriptMeta | None:
    """Parse the @script header from a script file.
    
    Reads the first docstring or comment block, extracts
    @script and @param declarations.
    
    Returns None if the file has no @script header (not a managed script).
    Files without @script are silently skipped — they might be
    helper modules, lib files, or non-managed scripts.
    """
```

### 6.7 Query Functions

```python
def get_all_scripts(project_root: Path) -> list[ScriptMeta]:
    """Return all discovered scripts (cached after first discovery)."""

def get_script(project_root: Path, script_id: str) -> ScriptMeta | None:
    """Get a single script by ID."""

def get_scripts_by_category(project_root: Path, category: str) -> list[ScriptMeta]:
    """Filter scripts by category."""

def get_scripts_by_tag(project_root: Path, tag: str) -> list[ScriptMeta]:
    """Filter scripts by tag."""

def refresh_registry(project_root: Path) -> list[ScriptMeta]:
    """Force re-discovery (invalidate cache)."""

def get_scripts_summary(project_root: Path) -> dict:
    """Return a summary dict for wizard/API consumption.
    
    Returns:
        {
            "total": int,
            "by_category": {"audit": 3, "generator": 1, ...},
            "by_source": {"root": 2, "template": 3, "override": 1},
            "scripts": [{"id": ..., "name": ..., "category": ...}, ...],
        }
    """
```

### 6.8 Caching

- Scripts are discovered once per process lifetime (or until `refresh_registry()` is called)
- Stored in a module-level `_registry_cache: dict[str, ScriptMeta]`
- Thread-safe via `threading.Lock` (consistent with event_bus pattern)

---

## 7. Script Executor

### 7.1 Responsibilities

The executor is the **run layer**. It:

1. Takes a `ScriptMeta` + parameters
2. Validates: script exists, required tools available, required params provided
3. Builds the subprocess command (language-appropriate)
4. Wraps in `tracked_run()` for ledger integration
5. Calls `stream_run()` for subprocess execution with event streaming
6. Publishes script-specific events to event bus
7. Routes output via OutputRouter
8. Returns structured result

### 7.2 Command Building

```python
def _build_command(meta: ScriptMeta, params: dict[str, str]) -> list[str]:
    """Build the subprocess command for a script.
    
    Language → Command mapping:
        python      → [sys.executable, script_path, --param1, val1, ...]
        bash        → ["bash", script_path, --param1, val1, ...]
        powershell  → ["pwsh", "-File", script_path, -param1, val1, ...]
        executable  → [script_path, --param1, val1, ...]
    
    IMPORTANT: For Python scripts, sys.executable is the project venv's python.
    This satisfies the hard rule: "NEVER USE PYTHON OUTSIDE THE VENV OF THE PROJECT"
    
    IMPORTANT: config.execution.venv_python can override sys.executable.
    If set to "auto", use sys.executable. Otherwise, use the explicit path.
    """
```

Note: `sys.executable` in the running process IS the venv python (because the program itself runs inside the venv). This is the simplest and safest way to ensure venv compliance.

### 7.3 Execution Flow

```python
def execute_script(
    project_root: Path,
    script_id: str,
    *,
    params: dict[str, str] | None = None,
    output_target: str | None = None,
) -> dict:
    """Execute a registered script.
    
    Flow:
    1. Load config from project.yml
    2. Resolve script from registry
    3. Validate prerequisites (tool availability, required params)
    4. Build command
    5. Resolve output target (OutputRouter)
    6. Build environment variables
    7. Wrap in tracked_run() (ledger integration)
    8. Call stream_run() (subprocess + event streaming)
    9. Return result dict
    
    Returns:
        {
            "ok": bool,
            "run_id": str,
            "stream_id": str,
            "exit_code": int,
            "output_path": str | None,
            "duration_ms": int,
            "lines": list[str],
            "error": str | None,
        }
    """
```

### 7.4 How it integrates (sequence diagram)

```
User calls execute_script("00_class_diagrams", params={"output": "docs/diagrams/"})
    │
    ├── 1. Config: load_scripts_config(root) → ScriptConfig
    │
    ├── 2. Registry: get_script("00_class_diagrams") → ScriptMeta
    │
    ├── 3. Validate: check meta.requires_tools are available
    │       check required params are provided
    │
    ├── 4. Build: _build_command(meta, params)
    │       → ["/path/to/.venv/bin/python", "scripts/00_class_diagrams.py", "--output", "docs/diagrams/"]
    │
    ├── 5. Output: resolve_output_target(root, meta, override)
    │       → Path("/path/to/project/docs/diagrams/")
    │
    ├── 6. Env: inject_output_env(env, output_path, meta, run_id, stream_id)
    │       → {SCRIPT_OUTPUT_DIR, SCRIPT_PROJECT_ROOT, SCRIPT_ID, ...}
    │
    ├── 7. tracked_run(root, "script", "script:00_class_diagrams", summary="Class Diagram Generator")
    │       │
    │       │   (publishes run:started via event_bus)
    │       │
    │       ├── 8. stream_run(cmd, cwd=root, stream_id=..., timeout=meta.timeout, env=env)
    │       │       │
    │       │       ├── (publishes stream:start via event_bus)
    │       │       ├── (publishes stream:line for each output line via event_bus)
    │       │       ├── (publishes stream:done when process exits)
    │       │       │
    │       │       └── Returns: {"ok": True, "exit_code": 0, "stream_id": "...", "lines": [...]}
    │       │
    │       └── (run_bag["status"] = "ok", run_bag["metadata"]["stream_id"] = "...")
    │
    │   (publishes run:completed via event_bus)
    │   (records Run to .state/runs.jsonl)
    │
    └── Returns: {"ok": True, "run_id": "run_...", "stream_id": "...", ...}
```

### 7.5 Tool Availability Check

Before executing, verify `requires_tools`:

```python
def _check_tools(meta: ScriptMeta) -> tuple[bool, list[str]]:
    """Check that all required external tools are available.
    
    Returns (all_ok, missing_tools).
    
    Checks:
    - python: always available (we ARE the venv)
    - bash: shutil.which("bash")
    - pwsh: shutil.which("pwsh")
    - pyreverse: shutil.which("pyreverse") or importlib check
    - Any tool name: shutil.which(tool_name)
    """
```

---

## 8. Output Router

### 8.1 Responsibilities

The output router decides WHERE script results go. This is the component that satisfies the user's requirement:

> "produce a report that I can chose where it go even though it can have a default target"

### 8.2 Resolution Order

```
1. Explicit override (passed at execution time: --output flag, API param)
2. Script's default_output (from ScriptMeta)
3. System default (from ScriptConfig.default_output)
```

### 8.3 Implementation

```python
# src/core/services/scripts/output_router.py

def resolve_output_target(
    project_root: Path,
    meta: ScriptMeta,
    override: str | None = None,
    config: ScriptConfig | None = None,
) -> Path:
    """Resolve the output directory for a script run.
    
    Priority:
    1. override (explicit) — if provided, use this
    2. meta.default_output — if script declares one
    3. config.default_output — system default from project.yml
    
    Creates the directory if it doesn't exist.
    Returns absolute path.
    """

def inject_output_env(
    env: dict[str, str],
    output_path: Path,
    meta: ScriptMeta,
    run_id: str = "",
    stream_id: str = "",
) -> dict[str, str]:
    """Inject output-related environment variables for the script.
    
    Sets:
      SCRIPT_OUTPUT_DIR = absolute path to output directory
      SCRIPT_OUTPUT_FORMAT = default format (from meta or "markdown")
      SCRIPT_PROJECT_ROOT = project root path
      SCRIPT_ID = script identifier
      SCRIPT_RUN_ID = run identifier (for correlation)
      SCRIPT_STREAM_ID = stream identifier (for event correlation)
    
    The script reads these to know where to write and how to identify itself.
    """
```

### 8.4 Environment Variables Injected

Every script subprocess gets these environment variables:

| Variable | Source | Example |
|---------|--------|---------|
| `SCRIPT_OUTPUT_DIR` | Resolved output target | `/home/user/project/docs/diagrams/` |
| `SCRIPT_OUTPUT_FORMAT` | From meta or param | `mermaid` |
| `SCRIPT_PROJECT_ROOT` | Project root | `/home/user/project/` |
| `SCRIPT_ID` | Script ID | `00_class_diagrams` |
| `SCRIPT_RUN_ID` | Run ID | `run_20260307T...` |
| `SCRIPT_STREAM_ID` | Stream ID | `script-1741...` |

Scripts can read these or receive them as CLI params (both work).

---

## 9. Run Type Extension

The existing `run_tracker.py` has a `RUN_TYPES` dict. We need to add `"script"`:

```python
# In src/core/services/run_tracker.py RUN_TYPES dict:
"script":    "Script execution (audit, generation, analysis)",
```

This is a ONE-LINE addition to an existing file.

---

## 10. File Inventory — What Gets Created

### 10.1 New Files

| File | Lines (est.) | Purpose |
|------|-------------|---------|
| `src/core/services/scripts/__init__.py` | ~15 | Package init — re-exports only, NO logic |
| `src/core/services/scripts/models.py` | ~120 | `ScriptMeta`, `ScriptParameter`, `ScriptConfig` dataclasses |
| `src/core/services/scripts/config.py` | ~100 | `load_scripts_config()`, `save_scripts_config()` — project.yml I/O |
| `src/core/services/scripts/registry.py` | ~300 | Discovery, merge, metadata parsing, query functions |
| `src/core/services/scripts/executor.py` | ~200 | Command building, execute_script(), validation |
| `src/core/services/scripts/output_router.py` | ~80 | Output target resolution, env var injection |

**Total new code**: ~815 lines across 6 files

### 10.2 New Directories

| Directory | Purpose |
|-----------|---------|
| `src/core/services/scripts/` | Backend service package |
| `src/core/data/script_templates/` | Template scripts directory (empty until M2/M3) |
| `src/core/data/script_templates/audit/` | Audit script templates (empty until M3+) |
| `src/core/data/script_templates/generators/` | Generator templates (empty until M3) |
| `src/core/data/script_templates/debug/` | Debug script templates (empty until later) |

### 10.3 Modified Files

| File | Change | Lines Changed |
|------|--------|---------------|
| `src/core/services/run_tracker.py` | Add `"script"` to `RUN_TYPES` dict | 1 line |
| `src/core/services/wizard/detect.py` | Add scripts file detection, devops cards, embedded data | ~30 lines |
| `src/core/services/wizard/helpers.py` | Add `_wizard_scripts_status()` helper | ~50 lines |

### 10.4 project.yml Changes

The `scripts:` section is added to `project.yml` for THIS project:

```yaml
# Added after artifacts: section
scripts:
  root: scripts
  template_source: auto
  default_output: scripts/output
  history:
    max_runs: 100
    persist_output: true
  execution:
    default_timeout: 300
    parallel: false
    venv_python: auto
  categories:
    - audit
    - generator
    - analyzer
    - debug
    - general
```

---

## 11. Integration Points Map

```
    ┌──────────────────────────────────────────────────────────────┐
    │                     EXISTING CODE                            │
    │                                                              │
    │  project.yml                 wizard/detect.py                │
    │    → scripts: { root, ... }    → files["scripts_dir"]        │
    │                                → devops_cards["scripts"]     │
    │                                → scripts_status: {...}       │
    │                                                              │
    │  wizard/helpers.py           event_bus.py                    │
    │    → _wizard_scripts_status    → bus.publish("script:*")     │
    │                                                              │
    │  stream_subprocess.py        run_tracker.py                  │
    │    → stream_run(cmd, ...)      → tracked_run("script", ...)  │
    │                                → RUN_TYPES["script"]         │
    │                                                              │
    │  ledger/models.py            artifacts/engine.py (pattern)   │
    │    → Run(type="script")        → structural reference        │
    │                                                              │
    └────────────────────────────────┬─────────────────────────────┘
                                     │
    ┌────────────────────────────────▼─────────────────────────────┐
    │                       NEW CODE (M1)                          │
    │                                                              │
    │  scripts/models.py      scripts/config.py                    │
    │    → ScriptMeta           → load_scripts_config()            │
    │    → ScriptParameter      → save_scripts_config()            │
    │    → ScriptConfig         → project.yml I/O                  │
    │                                                              │
    │  scripts/registry.py    scripts/executor.py                  │
    │    → discover_scripts()   → execute_script()                 │
    │    → parse_script_meta()  → _build_command()                 │
    │    → get_all_scripts()    → _check_tools()                   │
    │    → get_scripts_summary()                                   │
    │                                                              │
    │  scripts/output_router.py                                    │
    │    → resolve_output_target()                                 │
    │    → inject_output_env()                                     │
    │                                                              │
    │  data/script_templates/   (empty dirs — populated in M2/M3)  │
    │    → audit/                                                  │
    │    → generators/                                             │
    │    → debug/                                                  │
    │                                                              │
    └──────────────────────────────────────────────────────────────┘
```

---

## 12. What M1 Does NOT Include

To be clear about scope boundaries:

| NOT in M1 | Where it goes |
|-----------|---------------|
| The actual scripts (class diagrams, route audit, etc.) | M2 + M3 |
| The shared lib/ modules (code_analyzer, graph_builder, mermaid_generator, etc.) | M2 |
| CLI commands (`controlplane scripts ...`) | M4 |
| Web API routes (`/api/scripts/...`) | M4 |
| Admin panel UI | M4 |
| Wizard setup action (`setup_scripts`) | M4 (depends on UI for the form) |
| Execution plans (sequences, dependencies, checkpoints) | M7 |
| Semi-automated and interactive mode HANDLING | M7 (the model supports them, execution of them is M7) |
| PowerShell interop specifics | M8 |
| Salt/Ansible export | M8 |

---

## 13. Verification — How We Know M1 Works

### 13.1 Unit Tests

```
tests/scripts/
├── test_models.py           # ScriptMeta creation, parameter validation
├── test_config.py           # Config loading from project.yml, defaults
├── test_registry.py         # Discovery, merge, metadata parsing
├── test_executor.py         # Command building, mock execution
└── test_output_router.py    # Target resolution, env var injection
```

### 13.2 Test Scenarios

**Config tests**:
1. No project.yml → returns defaults
2. project.yml without scripts: → returns defaults
3. project.yml with scripts: → returns configured values
4. Partial scripts: section → missing fields get defaults
5. save_scripts_config() → writes proper YAML, preserves other sections

**Registry tests**:
1. Empty project (no scripts/ dir) → returns empty list, no crash
2. Root scripts only → returns root scripts with source="root"
3. Template scripts only → returns templates with source="template"
4. Both present → returns merged, no duplicates
5. Root overrides template → root wins, source="override"
6. Script with @script header → metadata correctly parsed
7. Script without @script header → skipped (not a managed script)
8. Numbered script (00_foo.py) → number=0, is_permanent=True
9. Unnumbered script (audit_foo.py) → number=None, is_permanent=False
10. template_source="never" → no templates loaded
11. template_source="always" → templates always loaded
12. get_scripts_summary() returns correct counts

**Executor tests**:
1. Python script → command uses sys.executable
2. Bash script → command uses "bash"
3. PowerShell script → command uses "pwsh"
4. Parameters passed as CLI flags
5. Missing required tool → returns error, does not run
6. Missing required param → returns error, does not run
7. Successful run → result has ok=True, run_id, stream_id
8. Failed run (exit code 1) → result has ok=False, error
9. Timeout → result has ok=False, error mentions timeout  
10. Custom venv_python config → command uses custom path

**Output router tests**:
1. Explicit override → uses override path
2. Script default_output → uses it
3. No default → uses config default
4. Directory created if missing
5. Env vars injected correctly

**Wizard integration tests**:
1. scripts/ dir exists → detected in files, card shows "ready"
2. No scripts/ dir → card shows "available" with setup actions
3. scripts: in project.yml → card shows config detected
4. _wizard_scripts_status returns correct inventory

### 13.3 Integration Smoke Test

A simple Python script that exists on disk, can be discovered, and executed:

```python
# tests/scripts/fixtures/test_hello.py
"""
@script
name: Hello World Test
category: debug
mode: fully_automated
"""
print("Hello from script system!")
```

The smoke test:
1. `load_scripts_config()` returns defaults
2. `discover_scripts()` finds the test fixture
3. `get_script("test_hello")` returns its metadata
4. `execute_script("test_hello")` returns `{"ok": True, ...}`
5. The run appears in `load_runs()`
6. Stream events were published to event bus

---

## 14. Implementation Order Within M1

This is the build sequence — each step depends only on previous steps.

```
Step 1: models.py (zero dependencies)
    → ScriptMeta, ScriptParameter, ScriptConfig dataclasses
    → Pure data, no I/O, no imports from other new files

Step 2: config.py (depends on: models.py)
    → load_scripts_config(), save_scripts_config()
    → Uses ScriptConfig, reads/writes project.yml

Step 3: output_router.py (depends on: models.py)
    → resolve_output_target(), inject_output_env()
    → Uses ScriptMeta and ScriptConfig

Step 4: registry.py (depends on: models.py, config.py)
    → discover_scripts(), parse_script_meta(), query functions
    → Uses ScriptMeta, ScriptConfig, reads filesystem

Step 5: executor.py (depends on: models.py, config.py, registry.py, output_router.py + existing infra)
    → execute_script(), _build_command(), _check_tools()
    → Uses registry to find scripts, output_router for targets
    → Calls stream_run() and tracked_run() from existing code

Step 6: __init__.py (depends on: all above)
    → Re-exports: ScriptMeta, discover_scripts, execute_script, etc.
    → NO logic

Step 7: run_tracker.py modification (1 line)
    → Add "script" to RUN_TYPES

Step 8: wizard/helpers.py addition (~50 lines)
    → Add _wizard_scripts_status() helper

Step 9: wizard/detect.py modifications (~30 lines)
    → Add scripts to files dict, devops_cards, embedded data

Step 10: Template directories (empty)
    → Create src/core/data/script_templates/{audit,generators,debug}/
    → Placeholder __init__.py files only

Step 11: project.yml update
    → Add scripts: section to THIS project's project.yml

Step 12: Tests (depends on: all above)
    → Unit tests for each module
    → Wizard integration tests
    → Smoke test with test fixture script
```

---

## 15. Design Decisions — Already Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Metadata format | In-file `@script` header | Self-contained, grep-able, no orphaned metadata |
| Override mechanism | Explicit `@override: template_id` | Explicit > implicit, auditable |
| Existing infra reuse | event_bus, stream_subprocess, run_tracker | Already proven, no reinvention |
| Python execution | sys.executable (venv) | Satisfies "NEVER USE PYTHON OUTSIDE THE VENV" rule |
| Registry caching | Module-level dict + threading.Lock | Consistent with event_bus pattern |
| Config storage | `project.yml` `scripts:` section | First-class citizen, same level as pages/artifacts |
| Template location | `src/core/data/script_templates/` | Consistent with data layer (catalogs/, templates/) |
| Template loading | Configurable via `template_source` | User controls what gets loaded |
| Wizard detection | Same pattern as Docker/K8s/Terraform | Consistent UX, scripts appear in wizard |
| Config defaults | Work without scripts: section | Zero-config start, opt-in refinement |
| Run tracking | Reuse existing `Run` model with type="script" | Appears automatically in run history/ledger |
