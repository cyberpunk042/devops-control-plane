"""Import chain resolver — traces imports across files and modules.

Builds a directed graph of what imports what. Follows project-internal
imports only (skips stdlib and third-party). Handles:
- Absolute imports (import X, from X import Y)
- Relative imports (from . import X, from ..X import Y)
- Star imports (from X import *)
- Conditional imports (try/except ImportError)
- TYPE_CHECKING imports
- Circular import detection
"""

from __future__ import annotations

import logging
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..backends.base import LanguageBackend

logger = logging.getLogger(__name__)

# Max depth for transitive import resolution
_MAX_DEPTH = 50
# Max files to process (safety limit)
_MAX_FILES = 10000


# ── Data models ──────────────────────────────────────────────────


class ImportNode:
    """A file in the import graph."""

    __slots__ = ("file_path", "module_path", "belongs_to_module", "is_entry_point")

    def __init__(
        self,
        file_path: str,
        module_path: str = "",
        belongs_to_module: str = "",
        is_entry_point: bool = False,
    ):
        self.file_path = file_path
        self.module_path = module_path
        self.belongs_to_module = belongs_to_module
        self.is_entry_point = is_entry_point

    def __repr__(self) -> str:
        return f"ImportNode({self.file_path!r}, module={self.belongs_to_module!r})"


class ImportEdge:
    """A directed edge: source imports target."""

    __slots__ = (
        "source", "target", "import_type", "names_imported",
        "line", "is_conditional", "is_type_only",
    )

    def __init__(
        self,
        source: str,
        target: str,
        import_type: str = "from_import",
        names_imported: list[str] | None = None,
        line: int = 0,
        is_conditional: bool = False,
        is_type_only: bool = False,
    ):
        self.source = source
        self.target = target
        self.import_type = import_type
        self.names_imported = names_imported or []
        self.line = line
        self.is_conditional = is_conditional
        self.is_type_only = is_type_only

    def __repr__(self) -> str:
        return f"ImportEdge({self.source!r} → {self.target!r})"


class ImportGraph:
    """Complete import dependency graph."""

    def __init__(self, root_module: str = "", project_root: str = ""):
        self.nodes: dict[str, ImportNode] = {}
        self.edges: list[ImportEdge] = []
        self.root_module = root_module
        self.project_root = project_root
        self._forward: dict[str, list[ImportEdge]] = {}   # source → edges
        self._reverse: dict[str, list[ImportEdge]] = {}   # target → edges

    def add_node(self, node: ImportNode) -> None:
        """Add a node to the graph."""
        if node.file_path not in self.nodes:
            self.nodes[node.file_path] = node

    def add_edge(self, edge: ImportEdge) -> None:
        """Add an edge to the graph."""
        self.edges.append(edge)
        self._forward.setdefault(edge.source, []).append(edge)
        self._reverse.setdefault(edge.target, []).append(edge)

    def direct_imports(self, file_path: str) -> list[ImportEdge]:
        """What does this file directly import?"""
        return list(self._forward.get(file_path, []))

    def direct_importers(self, file_path: str) -> list[ImportEdge]:
        """What files directly import this file?"""
        return list(self._reverse.get(file_path, []))

    def transitive_imports(self, file_path: str, max_depth: int = _MAX_DEPTH) -> list[str]:
        """All files reachable by following imports from this file."""
        visited: set[str] = set()
        queue: deque[tuple[str, int]] = deque([(file_path, 0)])

        while queue:
            current, depth = queue.popleft()
            if current in visited or depth > max_depth:
                continue
            visited.add(current)
            for edge in self._forward.get(current, []):
                if edge.target not in visited:
                    queue.append((edge.target, depth + 1))

        visited.discard(file_path)
        return sorted(visited)

    def transitive_importers(self, file_path: str, max_depth: int = _MAX_DEPTH) -> list[str]:
        """All files that transitively import this file."""
        visited: set[str] = set()
        queue: deque[tuple[str, int]] = deque([(file_path, 0)])

        while queue:
            current, depth = queue.popleft()
            if current in visited or depth > max_depth:
                continue
            visited.add(current)
            for edge in self._reverse.get(current, []):
                if edge.source not in visited:
                    queue.append((edge.source, depth + 1))

        visited.discard(file_path)
        return sorted(visited)

    def files_in_module(self, module_name: str) -> list[str]:
        """All files belonging to a specific project module."""
        return sorted(
            fp for fp, node in self.nodes.items()
            if node.belongs_to_module == module_name
        )

    def cross_module_edges(self) -> list[ImportEdge]:
        """All edges where source and target belong to different modules."""
        result = []
        for edge in self.edges:
            src_node = self.nodes.get(edge.source)
            tgt_node = self.nodes.get(edge.target)
            if src_node and tgt_node and src_node.belongs_to_module != tgt_node.belongs_to_module:
                result.append(edge)
        return result

    def dependency_modules(self, module_name: str) -> list[str]:
        """Which other project modules does this module depend on?"""
        deps: set[str] = set()
        for edge in self.cross_module_edges():
            src_node = self.nodes.get(edge.source)
            tgt_node = self.nodes.get(edge.target)
            if src_node and src_node.belongs_to_module == module_name and tgt_node:
                deps.add(tgt_node.belongs_to_module)
        return sorted(deps)

    def shortest_path(self, from_file: str, to_file: str) -> list[str] | None:
        """Find shortest import chain from one file to another."""
        if from_file == to_file:
            return [from_file]

        visited: set[str] = set()
        queue: deque[list[str]] = deque([[from_file]])

        while queue:
            path = queue.popleft()
            current = path[-1]

            if current in visited:
                continue
            visited.add(current)

            for edge in self._forward.get(current, []):
                if edge.target == to_file:
                    return path + [to_file]
                if edge.target not in visited:
                    queue.append(path + [edge.target])

        return None

    def shortest_path_from_module(
        self,
        module_name: str,
        to_file: str,
    ) -> list[str] | None:
        """Find shortest import chain from any file in a module to a target file."""
        module_files = self.files_in_module(module_name)
        best: list[str] | None = None

        for mf in module_files:
            path = self.shortest_path(mf, to_file)
            if path and (best is None or len(path) < len(best)):
                best = path

        return best

    def has_cycles(self) -> bool:
        """Does the graph contain any import cycles?"""
        return len(self.find_cycles()) > 0

    def find_cycles(self) -> list[list[str]]:
        """Find all import cycles using DFS."""
        cycles: list[list[str]] = []
        visited: set[str] = set()
        rec_stack: set[str] = set()
        path: list[str] = []

        def dfs(node: str) -> None:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for edge in self._forward.get(node, []):
                target = edge.target
                if target not in visited:
                    dfs(target)
                elif target in rec_stack:
                    # Found a cycle — extract it
                    cycle_start = path.index(target)
                    cycle = path[cycle_start:] + [target]
                    cycles.append(cycle)

            path.pop()
            rec_stack.discard(node)

        for node in list(self.nodes.keys()):
            if node not in visited:
                dfs(node)

        return cycles

    def stats(self) -> dict:
        """Graph statistics."""
        cross = self.cross_module_edges()
        modules = set(n.belongs_to_module for n in self.nodes.values() if n.belongs_to_module)
        return {
            "nodes": len(self.nodes),
            "edges": len(self.edges),
            "cross_module_edges": len(cross),
            "modules": sorted(modules),
            "has_cycles": self.has_cycles(),
        }


# ── Import resolver ──────────────────────────────────────────────


class ImportResolver:
    """Build import graph for a module."""

    def __init__(
        self,
        backend: LanguageBackend,
        project_root: Path,
        module_configs: list[dict] | None = None,
    ):
        self._backend = backend
        self._project_root = project_root
        self._module_configs = module_configs or []

    def build_graph(
        self,
        module_dir: Path,
        module_name: str = "",
        follow_transitive: bool = True,
        max_depth: int = _MAX_DEPTH,
    ) -> ImportGraph:
        """Build the complete import graph starting from a module.

        1. Find all source files in module_dir
        2. Parse each file's imports
        3. Resolve each import to a file path
        4. If follow_transitive, recursively process imported files
           (only project-internal imports, not stdlib/third-party)
        5. Return the complete graph
        """
        graph = ImportGraph(
            root_module=module_name,
            project_root=str(self._project_root),
        )

        # Discover entry point files
        extensions = set(self._backend.file_extensions)
        entry_files: list[Path] = []
        for f in sorted(module_dir.rglob("*")):
            if f.is_file() and f.suffix in extensions:
                if "__pycache__" not in str(f):
                    entry_files.append(f)

        # BFS to build graph
        queue: deque[tuple[Path, int]] = deque()
        visited: set[str] = set()

        for ef in entry_files:
            rel = str(ef.relative_to(self._project_root))
            graph.add_node(ImportNode(
                file_path=rel,
                module_path=self._file_to_module_path(ef),
                belongs_to_module=module_name or self._determine_module(rel),
                is_entry_point=True,
            ))
            queue.append((ef, 0))

        while queue:
            file_path, depth = queue.popleft()
            rel_path = str(file_path.relative_to(self._project_root))

            if rel_path in visited:
                continue
            visited.add(rel_path)

            if depth > max_depth:
                continue

            if len(visited) > _MAX_FILES:
                logger.warning("Import resolver: hit file limit (%d)", _MAX_FILES)
                break

            # Parse the file and extract imports
            try:
                tree = self._backend.parse_file(file_path)
            except Exception:
                continue

            raw_imports = self._backend.extract_imports(tree, file_path)

            for raw in raw_imports:
                module_str = raw.get("module", "")
                level = raw.get("level", 0)

                # Handle relative imports
                if level > 0:
                    module_str = self._resolve_relative_module(
                        module_str, level, file_path,
                    )
                    if not module_str:
                        continue

                resolved = self._backend.resolve_import_path(
                    module_str, file_path, self._project_root,
                )
                if resolved is None:
                    continue  # stdlib or third-party

                resolved_rel = str(resolved.relative_to(self._project_root))

                # Add edge
                graph.add_edge(ImportEdge(
                    source=rel_path,
                    target=resolved_rel,
                    import_type=raw.get("import_type", "from_import"),
                    names_imported=raw.get("names", []),
                    line=raw.get("line", 0),
                    is_conditional=raw.get("is_conditional", False),
                    is_type_only=raw.get("is_type_only", False),
                ))

                # Add target node if new
                if resolved_rel not in graph.nodes:
                    target_module = self._determine_module(resolved_rel)
                    graph.add_node(ImportNode(
                        file_path=resolved_rel,
                        module_path=self._file_to_module_path(resolved),
                        belongs_to_module=target_module,
                        is_entry_point=False,
                    ))

                # Follow transitive imports
                if follow_transitive and resolved_rel not in visited:
                    queue.append((resolved, depth + 1))

        return graph

    def _resolve_relative_module(
        self,
        module: str | None,
        level: int,
        source_file: Path,
    ) -> str:
        """Resolve a relative import to an absolute module path.

        level=1: from . import X → current package
        level=2: from .. import X → parent package
        """
        # Find the package directory
        pkg_dir = source_file.parent
        for _ in range(level - 1):
            pkg_dir = pkg_dir.parent

        # Convert package dir to module path
        try:
            rel = pkg_dir.relative_to(self._project_root)
        except ValueError:
            return ""

        base = str(rel).replace("/", ".").replace("\\", ".")

        if module:
            return f"{base}.{module}"
        return base

    def _file_to_module_path(self, file_path: Path) -> str:
        """Convert a file path to a Python module path."""
        try:
            rel = file_path.relative_to(self._project_root)
        except ValueError:
            return ""

        # Remove .py extension and convert separators
        module = str(rel.with_suffix("")).replace("/", ".").replace("\\", ".")

        # Handle __init__.py → package name
        if module.endswith(".__init__"):
            module = module[:-9]

        return module

    def _determine_module(self, file_path: str) -> str:
        """Determine which project module a file belongs to.

        Uses module_configs from project.yml. Falls back to
        first directory component.
        """
        # Check configured modules (longest path match first)
        sorted_configs = sorted(
            self._module_configs,
            key=lambda m: len(m.get("path", "")),
            reverse=True,
        )
        for mod in sorted_configs:
            mod_path = mod.get("path", "")
            if file_path.startswith(mod_path):
                return mod.get("name", "")

        # Fallback: use top-level directory
        parts = file_path.split("/")
        if len(parts) >= 2:
            return parts[1] if parts[0] == "src" else parts[0]
        return "unknown"
