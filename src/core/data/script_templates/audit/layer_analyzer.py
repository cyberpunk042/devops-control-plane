"""Layer analyzer — detect data that lives in the wrong architectural layer.

This module provides:
- Data models for 4 tiers of data layer leaks
- A LayerAnalyzer that scans Python files via AST
- Smart heuristics for classifying inline data (leak vs. response)
- Duplication detection across constants

Design principle: OBSERVE, DON'T JUDGE.
"This 26-key dict is inside a route handler" is a fact.
Whether it should be extracted is a human decision.
The classifier adds *likely* labels to help the human prioritise.

Tier 1: Inline data — dicts/lists/sets inside function bodies
Tier 2: Wrong-layer definitions — module constants outside data layers
Tier 3: Import direction violations — UI importing from data/persistence
Tier 4: Lateral service coupling — service importing sibling service
"""

from __future__ import annotations

import ast
import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path


# ═══════════════════════════════════════════════════════════════════
#  Layer Configuration
# ═══════════════════════════════════════════════════════════════════


# Default layer map — auto-maps directory prefixes to layer names.
# Order matters: first match wins.
DEFAULT_LAYER_MAP: list[tuple[str, str]] = [
    ("ui/web/routes", "ui-routes"),
    ("ui/web/templates", "ui-templates"),
    ("ui/web", "ui-web"),
    ("ui/cli", "ui-cli"),
    ("core/data", "core-data"),
    ("core/models", "core-models"),
    ("core/persistence", "core-persistence"),
    ("core/use_cases", "core-usecases"),
    ("core/config", "core-config"),
    ("core/services", "core-services"),
    ("core/engine", "core-engine"),
    ("core/observability", "core-observability"),
    ("core/reliability", "core-reliability"),
    ("core/security", "core-security"),
    ("adapters", "adapters"),
]

# Layers that are canonical homes for data definitions
DATA_LAYERS = frozenset({
    "core-data", "core-models", "core-persistence", "core-config",
})

# Layers that should NOT import directly from data/persistence
UI_LAYERS = frozenset({
    "ui-routes", "ui-cli",
})

# Import classification map (module string patterns → layer)
IMPORT_LAYER_MAP: list[tuple[str, str]] = [
    ("core.data", "core-data"),
    ("core.models", "core-models"),
    ("core.persistence", "core-persistence"),
    ("core.use_cases", "core-usecases"),
    ("core.config", "core-config"),
    ("core.services", "core-services"),
    ("core.engine", "core-engine"),
    ("ui.web.routes", "ui-routes"),
    ("ui.cli", "ui-cli"),
    ("adapters", "adapters"),
]


# ═══════════════════════════════════════════════════════════════════
#  Data Models
# ═══════════════════════════════════════════════════════════════════


@dataclass
class InlineDataLeak:
    """Tier 1 — data literal found inside a function body."""

    file: str
    function_name: str
    lineno: int
    data_type: str                      # "dict", "list", "set"
    item_count: int                     # number of keys/elements
    classification: str                 # "data_leak", "response", "constructed"
    reason: str                         # why it was classified
    assigned_to: str | None = None      # variable name if assigned
    is_upper_case: bool = False         # UPPER_CASE → almost certainly data
    layer: str = ""


@dataclass
class WrongLayerDef:
    """Tier 2 — module-level constant or type outside its canonical layer."""

    file: str
    symbol_name: str
    lineno: int
    data_type: str                      # "Dict", "List", "Set", "dataclass", ...
    item_count: int
    current_layer: str                  # "core-services"
    suggested_layer: str                # "core-data"
    suggested_path: str                 # "core/data/catalogs/..."
    content_hash: str = ""              # for duplication detection
    layer: str = ""


@dataclass
class ImportViolation:
    """Tier 3 — import that crosses an architectural boundary."""

    file: str
    lineno: int
    import_module: str                  # "src.core.persistence.audit"
    imported_names: list[str] = field(default_factory=list)
    source_layer: str = ""              # "ui-routes"
    target_layer: str = ""              # "core-persistence"
    is_lazy: bool = False               # inside a function body
    is_type_checking: bool = False      # inside TYPE_CHECKING block
    severity: str = "violation"         # "violation" | "soft_violation"


@dataclass
class LateralCoupling:
    """Tier 4 — service importing from a sibling service."""

    file: str
    lineno: int
    source_package: str                 # "docker"
    target_package: str                 # "generators"
    import_module: str
    imported_names: list[str] = field(default_factory=list)
    is_private: bool = False            # imports _private names
    severity: str = "advisory"          # "advisory" | "moderate" | "major"


@dataclass
class DuplicationGroup:
    """Two or more constants with overlapping content."""

    content_hash: str
    entries: list[tuple[str, str, int]]  # [(file, symbol, item_count), ...]
    overlap_pct: float = 100.0


@dataclass
class LayerAuditResult:
    """Complete results of a data layer leak scan."""

    project_root: str = ""
    timestamp: str = ""
    files_scanned: int = 0
    layer_counts: dict[str, int] = field(default_factory=dict)

    inline_leaks: list[InlineDataLeak] = field(default_factory=list)
    wrong_layer_defs: list[WrongLayerDef] = field(default_factory=list)
    import_violations: list[ImportViolation] = field(default_factory=list)
    lateral_couplings: list[LateralCoupling] = field(default_factory=list)
    duplications: list[DuplicationGroup] = field(default_factory=list)

    # Summary counts for the report
    @property
    def tier1_real(self) -> int:
        return sum(1 for l in self.inline_leaks if l.classification == "data_leak")

    @property
    def tier1_noise(self) -> int:
        return sum(1 for l in self.inline_leaks if l.classification != "data_leak")

    @property
    def tier2_count(self) -> int:
        return len(self.wrong_layer_defs)

    @property
    def tier3_count(self) -> int:
        return len(self.import_violations)

    @property
    def tier4_count(self) -> int:
        return len(self.lateral_couplings)


# ═══════════════════════════════════════════════════════════════════
#  Layer Classification Helpers
# ═══════════════════════════════════════════════════════════════════


def classify_file(filepath: str, source_dir: str = "src") -> str:
    """Classify a file path into an architectural layer.

    Uses ``DEFAULT_LAYER_MAP`` to match directory prefixes.
    Returns the layer name or "other".
    """
    # Normalise: strip leading src/ or source_dir/
    path = filepath.replace("\\", "/")
    for prefix in (f"{source_dir}/", "src/"):
        if path.startswith(prefix):
            path = path[len(prefix):]
            break

    for dir_prefix, layer in DEFAULT_LAYER_MAP:
        if path.startswith(dir_prefix):
            return layer
    return "other"


def classify_import(module_str: str) -> str:
    """Classify an import target module string into a layer.

    Returns the layer name or "external" for third-party / stdlib.
    """
    for pattern, layer in IMPORT_LAYER_MAP:
        if pattern in module_str:
            return layer
    return "external"


def get_service_subpackage(path_str: str) -> str | None:
    """Extract the service sub-package name from a file path.

    Example: "src/core/services/docker/compose.py" → "docker"
    Files directly in services/ → "__root__"
    """
    norm = path_str.replace("\\", "/")
    if "core/services/" not in norm:
        return None
    after = norm.split("core/services/")[1]
    parts = after.split("/")
    if len(parts) <= 1:
        return "__root__"  # file directly in services/
    return parts[0]


def get_service_subpackage_from_import(module_str: str) -> str | None:
    """Extract the service sub-package from an import module string.

    Example: "src.core.services.docker.compose" → "docker"
    """
    if "core.services." not in module_str:
        return None
    after = module_str.split("core.services.")[1]
    parts = after.split(".")
    return parts[0] if parts else None


# ═══════════════════════════════════════════════════════════════════
#  AST Analysis Engine
# ═══════════════════════════════════════════════════════════════════


class LayerAnalyzer:
    """Scans Python files for data layer leaks across 4 tiers."""

    def __init__(
        self,
        *,
        min_dict_size: int = 5,
        min_const_size: int = 3,
        source_dir: str = "src",
    ):
        self.min_dict_size = min_dict_size
        self.min_const_size = min_const_size
        self.source_dir = source_dir

    def analyze(self, project_root: Path, *, scope: str | None = None) -> LayerAuditResult:
        """Run the full analysis across all Python files.

        Args:
            project_root: Root of the project.
            scope: Optional sub-directory to limit analysis (e.g. "core/services").

        Returns:
            LayerAuditResult with all tiers populated.
        """
        result = LayerAuditResult(project_root=str(project_root))

        src = project_root / self.source_dir
        if not src.is_dir():
            return result

        layer_counts: dict[str, int] = defaultdict(int)
        # For duplication detection: hash → [(file, symbol, count)]
        const_hashes: dict[str, list[tuple[str, str, int]]] = defaultdict(list)

        for py_file in sorted(src.rglob("*.py")):
            rel = str(py_file.relative_to(project_root))

            # Scope filter
            if scope:
                scope_prefix = f"{self.source_dir}/{scope}"
                if not rel.startswith(scope_prefix):
                    continue

            # Skip __pycache__
            if "__pycache__" in rel:
                continue

            layer = classify_file(rel, self.source_dir)
            layer_counts[layer] += 1
            result.files_scanned += 1

            try:
                source_code = py_file.read_text(errors="replace")
                tree = ast.parse(source_code)
            except (SyntaxError, UnicodeDecodeError):
                continue

            # ── Tier 1: Inline data in function bodies ──
            if layer not in DATA_LAYERS:
                self._scan_inline_data(tree, rel, layer, result)

            # ── Tier 2: Module-level constants in wrong layer ──
            if layer not in DATA_LAYERS:
                self._scan_wrong_layer_defs(
                    tree, rel, layer, result, const_hashes,
                )

            # ── Tier 3: Import direction violations ──
            self._scan_import_violations(tree, rel, layer, result)

            # ── Tier 4: Lateral service coupling ──
            if layer == "core-services":
                self._scan_lateral_coupling(tree, rel, result)

        result.layer_counts = dict(layer_counts)

        # ── Duplication detection (post-scan) ──
        for h, entries in const_hashes.items():
            if len(entries) >= 2:
                result.duplications.append(DuplicationGroup(
                    content_hash=h,
                    entries=entries,
                ))

        return result

    # ── Tier 1: Inline data ───────────────────────────────────────

    def _scan_inline_data(
        self,
        tree: ast.Module,
        filepath: str,
        layer: str,
        result: LayerAuditResult,
    ) -> None:
        """Find data literals inside function bodies."""
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            func_name = node.name

            # Walk the function body for data literals
            for child in ast.walk(node):
                if isinstance(child, ast.Dict):
                    count = len(child.keys)
                    if count < self.min_dict_size:
                        continue
                    classification, reason, assigned_to, is_upper = (
                        self._classify_inline_dict(child, node)
                    )
                    result.inline_leaks.append(InlineDataLeak(
                        file=filepath,
                        function_name=func_name,
                        lineno=child.lineno,
                        data_type="dict",
                        item_count=count,
                        classification=classification,
                        reason=reason,
                        assigned_to=assigned_to,
                        is_upper_case=is_upper,
                        layer=layer,
                    ))

                elif isinstance(child, (ast.List, ast.Set)):
                    count = len(child.elts)
                    if count < self.min_dict_size:
                        continue
                    assigned_to, is_upper = self._find_assignment_target(
                        child, node,
                    )
                    # Lists/sets of all-string literals are very likely data
                    all_strings = all(
                        isinstance(e, ast.Constant) and isinstance(e.value, str)
                        for e in child.elts
                    )
                    dtype = "set" if isinstance(child, ast.Set) else "list"
                    if all_strings and count >= 5:
                        classification = "data_leak"
                        reason = f"All-string {dtype} with {count} items"
                    elif is_upper:
                        classification = "data_leak"
                        reason = f"Assigned to UPPER_CASE variable {assigned_to}"
                    else:
                        classification = "constructed"
                        reason = f"{dtype} with computed/mixed values"

                    result.inline_leaks.append(InlineDataLeak(
                        file=filepath,
                        function_name=func_name,
                        lineno=child.lineno,
                        data_type=dtype,
                        item_count=count,
                        classification=classification,
                        reason=reason,
                        assigned_to=assigned_to,
                        is_upper_case=is_upper,
                        layer=layer,
                    ))

    def _classify_inline_dict(
        self,
        dict_node: ast.Dict,
        func_node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> tuple[str, str, str | None, bool]:
        """Classify an inline dict as data_leak, response, or constructed.

        Returns: (classification, reason, assigned_to, is_upper_case)
        """
        assigned_to, is_upper = self._find_assignment_target(
            dict_node, func_node,
        )

        # Rule 1: UPPER_CASE assignment → data leak (certain)
        if is_upper and assigned_to:
            return (
                "data_leak",
                f"Assigned to UPPER_CASE variable {assigned_to}",
                assigned_to,
                True,
            )

        # Rule 2: Argument to jsonify / json.dumps / Response → response
        if self._is_response_arg(dict_node, func_node):
            return (
                "response",
                "Argument to jsonify/json.dumps/Response",
                assigned_to,
                False,
            )

        # Rule 3: Direct return value → response/result
        if self._is_return_value(dict_node, func_node):
            return (
                "response",
                "Directly returned from function",
                assigned_to,
                False,
            )

        # Rule 4: All values are function calls / attribute lookups → constructed
        values = [v for v in dict_node.values if v is not None]
        if values and all(
            isinstance(v, (ast.Call, ast.Attribute, ast.Subscript, ast.JoinedStr))
            for v in values
        ):
            return (
                "constructed",
                "All values are computed (calls/lookups)",
                assigned_to,
                False,
            )

        # Rule 5: All keys and values are string/int/bool literals → data leak
        all_static_keys = all(
            isinstance(k, ast.Constant) and isinstance(k.value, (str, int))
            for k in dict_node.keys
            if k is not None
        )
        all_static_vals = all(
            isinstance(v, ast.Constant) and isinstance(v.value, (str, int, bool, float))
            for v in values
        )
        if all_static_keys and all_static_vals and len(values) >= 5:
            return (
                "data_leak",
                f"All-static dict with {len(values)} literal key-value pairs",
                assigned_to,
                False,
            )

        # Rule 6: Mix of static and computed → constructed (benefit of doubt)
        return (
            "constructed",
            "Mixed static and computed values",
            assigned_to,
            False,
        )

    def _find_assignment_target(
        self,
        literal_node: ast.AST,
        func_node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> tuple[str | None, bool]:
        """Find if a literal was assigned to a variable, and if it's UPPER_CASE.

        Returns: (variable_name_or_None, is_upper_case)
        """
        for stmt in ast.walk(func_node):
            if isinstance(stmt, ast.Assign) and stmt.value is literal_node:
                for target in stmt.targets:
                    if isinstance(target, ast.Name):
                        name = target.id
                        is_upper = name.isupper() or (
                            "_" in name and name == name.upper()
                        )
                        return name, is_upper
            elif isinstance(stmt, ast.AnnAssign):
                if stmt.value is literal_node and isinstance(stmt.target, ast.Name):
                    name = stmt.target.id
                    is_upper = name.isupper() or (
                        "_" in name and name == name.upper()
                    )
                    return name, is_upper
        return None, False

    def _is_response_arg(
        self,
        dict_node: ast.Dict,
        func_node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> bool:
        """Check if a dict is passed as argument to jsonify/json.dumps/Response."""
        response_funcs = {"jsonify", "json_dumps", "dumps", "Response"}
        for node in ast.walk(func_node):
            if isinstance(node, ast.Call):
                # Direct call: jsonify({...})
                if isinstance(node.func, ast.Name):
                    if node.func.id in response_funcs:
                        if dict_node in node.args:
                            return True
                # Attribute call: json.dumps({...})
                if isinstance(node.func, ast.Attribute):
                    if node.func.attr in response_funcs:
                        if dict_node in node.args:
                            return True
                # **kwargs: jsonify(**{...})
                for kw in node.keywords:
                    if kw.value is dict_node:
                        # Check if the call is a response function
                        if isinstance(node.func, ast.Name):
                            if node.func.id in response_funcs:
                                return True
        return False

    def _is_return_value(
        self,
        dict_node: ast.Dict,
        func_node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> bool:
        """Check if a dict is the direct return value of the function."""
        for node in ast.walk(func_node):
            if isinstance(node, ast.Return) and node.value is dict_node:
                return True
        return False

    # ── Tier 2: Wrong-layer definitions ───────────────────────────

    def _scan_wrong_layer_defs(
        self,
        tree: ast.Module,
        filepath: str,
        layer: str,
        result: LayerAuditResult,
        const_hashes: dict[str, list[tuple[str, str, int]]],
    ) -> None:
        """Find module-level constants and types in wrong layers."""
        for node in ast.iter_child_nodes(tree):
            # ── Module-level UPPER_CASE assignments ──
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if not isinstance(target, ast.Name):
                        continue
                    name = target.id

                    # Must be UPPER_CASE (with underscore)
                    if not (name.isupper() or ("_" in name and name == name.upper())):
                        continue

                    # Skip known non-data patterns
                    if name in (
                        "__all__",
                        "TYPE_CHECKING",
                    ) or name.startswith("__"):
                        continue

                    if isinstance(node.value, ast.Dict):
                        count = len(node.value.keys)
                        if count < self.min_const_size:
                            continue
                        h = self._hash_literal(node.value)
                        const_hashes[h].append((filepath, name, count))
                        suggested = self._suggest_home(name, "Dict", filepath)
                        result.wrong_layer_defs.append(WrongLayerDef(
                            file=filepath,
                            symbol_name=name,
                            lineno=node.lineno,
                            data_type="Dict",
                            item_count=count,
                            current_layer=layer,
                            suggested_layer="core-data",
                            suggested_path=suggested,
                            content_hash=h,
                            layer=layer,
                        ))

                    elif isinstance(node.value, (ast.List, ast.Set)):
                        count = len(node.value.elts)
                        if count < self.min_const_size:
                            continue
                        dtype = "Set" if isinstance(node.value, ast.Set) else "List"
                        h = self._hash_literal(node.value)
                        const_hashes[h].append((filepath, name, count))
                        suggested = self._suggest_home(name, dtype, filepath)
                        result.wrong_layer_defs.append(WrongLayerDef(
                            file=filepath,
                            symbol_name=name,
                            lineno=node.lineno,
                            data_type=dtype,
                            item_count=count,
                            current_layer=layer,
                            suggested_layer="core-data",
                            suggested_path=suggested,
                            content_hash=h,
                            layer=layer,
                        ))

            # ── Dataclass / TypedDict outside models/ ──
            if isinstance(node, ast.ClassDef) and layer != "core-models":
                has_dataclass = any(
                    (isinstance(d, ast.Name) and d.id == "dataclass")
                    or (isinstance(d, ast.Attribute) and d.attr == "dataclass")
                    or (isinstance(d, ast.Call) and (
                        (isinstance(d.func, ast.Name) and d.func.id == "dataclass")
                        or (isinstance(d.func, ast.Attribute) and d.func.attr == "dataclass")
                    ))
                    for d in node.decorator_list
                )
                inherits_typeddict = any(
                    (isinstance(b, ast.Name) and b.id == "TypedDict")
                    or (isinstance(b, ast.Attribute) and b.attr == "TypedDict")
                    for b in node.bases
                )
                # Also check for BaseModel (Pydantic)
                inherits_basemodel = any(
                    (isinstance(b, ast.Name) and b.id == "BaseModel")
                    or (isinstance(b, ast.Attribute) and b.attr == "BaseModel")
                    for b in node.bases
                )
                if has_dataclass or inherits_typeddict or inherits_basemodel:
                    # Count fields (class body assignments)
                    field_count = sum(
                        1 for child in node.body
                        if isinstance(child, (ast.Assign, ast.AnnAssign))
                    )
                    if inherits_typeddict:
                        dtype = "TypedDict"
                    elif inherits_basemodel:
                        dtype = "BaseModel"
                    else:
                        dtype = "dataclass"
                    result.wrong_layer_defs.append(WrongLayerDef(
                        file=filepath,
                        symbol_name=node.name,
                        lineno=node.lineno,
                        data_type=dtype,
                        item_count=field_count,
                        current_layer=layer,
                        suggested_layer="core-models",
                        suggested_path=f"core/models/{_snake_case(node.name)}.py",
                        layer=layer,
                    ))

    def _hash_literal(self, node: ast.AST) -> str:
        """Compute a content hash for a literal (dict/list/set).

        Used for duplication detection — two constants with the same
        hash have identical or near-identical content.
        """
        try:
            content = ast.dump(node, annotate_fields=False)
        except Exception:
            content = str(id(node))
        return hashlib.md5(content.encode()).hexdigest()[:12]

    def _suggest_home(
        self, symbol_name: str, data_type: str, filepath: str,
    ) -> str:
        """Suggest a canonical home path for a misplaced constant."""
        # Try to derive from the symbol name
        name_lower = symbol_name.lower().rstrip("s")
        if "ext" in name_lower:
            return "core/data/catalogs/file_extensions.py"
        if "keyword" in name_lower or "token" in name_lower:
            return "core/data/catalogs/code_keywords.py"
        if "type" in name_lower or "kind" in name_lower:
            return "core/data/catalogs/types.py"
        if "mime" in name_lower:
            return "core/data/catalogs/mime_types.py"
        if "run" in name_lower:
            return "core/data/catalogs/run_types.py"
        # Fallback: derive from the file where it currently lives
        stem = Path(filepath).stem
        return f"core/data/catalogs/{stem}_data.py"

    # ── Tier 3: Import direction violations ───────────────────────

    def _scan_import_violations(
        self,
        tree: ast.Module,
        filepath: str,
        source_layer: str,
        result: LayerAuditResult,
    ) -> None:
        """Find imports that cross forbidden architectural boundaries."""
        # Only check UI layers for boundary violations
        if source_layer not in UI_LAYERS:
            return

        # Detect TYPE_CHECKING blocks
        type_checking_ranges = _find_type_checking_ranges(tree)

        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            if not node.module:
                continue

            target_layer = classify_import(node.module)

            # Only flag imports into data/persistence/models
            if target_layer not in DATA_LAYERS:
                continue

            names = [alias.name for alias in (node.names or [])]
            lineno = node.lineno

            # Check if inside TYPE_CHECKING block
            in_type_checking = any(
                start <= lineno <= end
                for start, end in type_checking_ranges
            )
            if in_type_checking:
                continue  # TYPE_CHECKING imports are fine

            # Check if lazy (inside a function body)
            is_lazy = _is_inside_function(tree, lineno)

            # Import into models for type hints is soft
            severity = "violation"
            if target_layer == "core-models":
                severity = "soft_violation"

            result.import_violations.append(ImportViolation(
                file=filepath,
                lineno=lineno,
                import_module=node.module,
                imported_names=names,
                source_layer=source_layer,
                target_layer=target_layer,
                is_lazy=is_lazy,
                is_type_checking=False,
                severity=severity,
            ))

    # ── Tier 4: Lateral service coupling ──────────────────────────

    def _scan_lateral_coupling(
        self,
        tree: ast.Module,
        filepath: str,
        result: LayerAuditResult,
    ) -> None:
        """Find services importing from sibling service sub-packages."""
        src_pkg = get_service_subpackage(filepath)
        if not src_pkg or src_pkg == "__root__":
            return  # Files directly in services/ are shared, skip

        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            if not node.module:
                continue
            if "core.services." not in node.module:
                continue

            tgt_pkg = get_service_subpackage_from_import(node.module)
            if not tgt_pkg or tgt_pkg == src_pkg:
                continue  # Same package, not lateral

            names = [alias.name for alias in (node.names or [])]
            is_private = any(n.startswith("_") for n in names)

            severity = "advisory"
            if is_private:
                severity = "moderate"

            result.lateral_couplings.append(LateralCoupling(
                file=filepath,
                lineno=node.lineno,
                source_package=src_pkg,
                target_package=tgt_pkg,
                import_module=node.module,
                imported_names=names,
                is_private=is_private,
                severity=severity,
            ))


# ═══════════════════════════════════════════════════════════════════
#  AST Helpers
# ═══════════════════════════════════════════════════════════════════


def _find_type_checking_ranges(tree: ast.Module) -> list[tuple[int, int]]:
    """Find line ranges of ``if TYPE_CHECKING:`` blocks."""
    ranges = []
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            if isinstance(node.test, ast.Name) and node.test.id == "TYPE_CHECKING":
                start = node.lineno
                end = max(
                    (getattr(child, "end_lineno", start) or start)
                    for child in ast.walk(node)
                )
                ranges.append((start, end))
    return ranges


def _is_inside_function(tree: ast.Module, lineno: int) -> bool:
    """Check if a given line number is inside a function body."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start = node.lineno
            end = node.end_lineno or start
            if start <= lineno <= end:
                return True
    return False


def _snake_case(name: str) -> str:
    """Convert CamelCase to snake_case."""
    result = []
    for i, ch in enumerate(name):
        if ch.isupper() and i > 0:
            result.append("_")
        result.append(ch.lower())
    return "".join(result)
