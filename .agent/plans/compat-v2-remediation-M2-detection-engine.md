# M2 — Detection Engine: Use Program's AST Infrastructure

> The detection engine is the core of the compat system. It's currently O(files × entries
> × AST_nodes) = 57 seconds for 146 files. It builds its own file discovery, its own AST
> cache, its own parser, ignoring ScanView, ParserRegistry, yield checkpoints, and
> incremental indexing. This milestone rewrites it to use all of them.

---

## What Exists Now (broken)

`analysis/engine.py` — DetectionEngine.analyze_module():
- File discovery: `rglob("*")` then filter by extension — should use ScanView
- AST parsing: Own `_parse_cached()` with dict cache keyed on path string —
  should use ParserRegistry per-file mtime cache
- Matching loop: For each file → for each entry (~600) → walk entire AST
  = O(files × entries × nodes). 146 files × 600 entries = 87,600 AST walks
- No yield checkpoints — blocks Flask single thread for 57+ seconds
- No incremental capability — re-scans all files every time, no delta awareness
- `_discover_files()` uses `rglob("*")` then checks extension — O(all files in tree)
- Every consumer that needs compat data triggers a full independent walk of all files

`backends/python_backend.py`:
- `walk_ast()` just yields `ast.walk(tree)` — called per entry, per file
- `_get_parent_map()` caches on tree object (good) but the walk itself is repeated
- `has_future_annotations()` does its OWN walk of the tree — another repeat
- `extract_imports()` does its OWN walk of the tree — another repeat
- Duplicates what PythonParser already extracts in ONE walk (imports, symbols, context)

---

## The Program's Pattern: ONE Walk Serves ALL Consumers

The program's index system demonstrates the correct pattern:

1. `index.scan` walks the filesystem ONCE (38ms) — produces a snapshot
2. `index.delta` diffs against the previous snapshot (1ms) — knows exactly what changed
3. `index.symbols` walks each changed file ONCE — extracts ALL symbols in that walk
4. Every downstream consumer (classify, peek, view) reads from the already-walked results
5. Multiple tasks entering the WorkQueue that need the same file share the same walk result
6. When a file changes, only THAT file is re-walked — not the whole tree

The compat engine must follow this SAME pattern:

- Walk each file ONCE → build a node-type index + parent map + context info
- ALL entries match against that pre-built index — no re-walking
- The index is stored (mediator cache or accumulator) — shared across consumers
- When `index.delta` says a file changed, only that file's index is rebuilt
- Multiple analysis requests for the same module share the same walked data

---

## What M2 Delivers

### 1. Single-walk node-type index per file

One walk produces everything the compat engine needs for a file:

```python
@dataclass
class FileNodeIndex:
    """Pre-built index from a single AST walk. All compat matching uses this."""
    nodes_by_type: dict[str, list[ast.AST]]   # {type_name: [nodes]}
    parent_map: dict[ast.AST, ast.AST]        # child → parent (for context)
    has_future: bool                           # __future__ annotations present
    imports: list[dict]                        # extracted imports (for import resolver)
    source: str                               # file source text
    line_count: int
    mtime: float                              # for cache invalidation

def build_file_index(file_path: Path, tree: ast.Module, source: str) -> FileNodeIndex:
    """Walk the AST exactly ONCE. Build everything from that walk."""
    nodes_by_type = {}
    parent_map = {}
    has_future = False
    imports = []

    for parent in ast.walk(tree):
        type_name = type(parent).__name__
        nodes_by_type.setdefault(type_name, []).append(parent)

        # Build parent map in the same walk
        for child in ast.iter_child_nodes(parent):
            parent_map[child] = parent

        # Detect __future__ in the same walk
        if isinstance(parent, ast.ImportFrom):
            if parent.module == "__future__":
                if any(alias.name == "annotations" for alias in parent.names):
                    has_future = True

        # Extract imports in the same walk
        if isinstance(parent, (ast.Import, ast.ImportFrom)):
            imports.append(_extract_import_info(parent))

    return FileNodeIndex(
        nodes_by_type=nodes_by_type,
        parent_map=parent_map,
        has_future=has_future,
        imports=imports,
        source=source,
        line_count=source.count("\n") + 1,
        mtime=file_path.stat().st_mtime,
    )
```

ONE walk. Nodes grouped by type. Parent map built. Future annotations detected.
Imports extracted. No repeated walks for any of these.

### 2. Matching uses the pre-built index — never walks

```python
def _scan_file(self, file_index: FileNodeIndex, entries, rel_path):
    findings = []

    for entry in entries:
        # O(1) lookup — get only nodes of the required type
        target_type = entry.detection.primary.ast_type
        candidates = file_index.nodes_by_type.get(target_type, [])

        if not candidates:
            continue  # No nodes of this type in file — skip entire entry

        for node in candidates:
            if self._backend.node_matches(node, target_type, entry.detection.primary.match):
                # Context check uses pre-built parent_map — no walk
                context = self._get_context(node, file_index.parent_map)
                if entry.detection.primary.context and not self._context_matches(entry.detection.primary.context, context):
                    continue
                # Exclusion check uses pre-built parent_map — no walk
                if self._is_excluded(node, file_index, entry.detection.exclude):
                    continue
                findings.append(Finding(...))

        # Same for alternatives — still uses the index, never walks
        for alt in entry.detection.alternatives:
            candidates = file_index.nodes_by_type.get(alt.ast_type, [])
            for node in candidates:
                ...

    return findings
```

No `ast.walk()` anywhere in matching. No `walk_ast()` calls. Nodes are looked up
by type from the pre-built dict. Context is determined from the pre-built parent map.

### 3. File index cache — shared across consumers

The file node indexes are stored as a mediator-friendly accumulator (same pattern
as `index.symbols` in `registrations/index.py`):

```python
# In the compat mediator registration:
_state = {
    "file_indexes": {},  # {rel_path: FileNodeIndex}
}

def _resolve_compat_index():
    """Build/update file indexes incrementally using index.delta."""
    delta = mediator.get("index.delta")["data"]
    scan = mediator.get("index.scan")["data"]
    indexes = _state["file_indexes"]

    if delta.empty and indexes:
        return indexes  # Nothing changed — return cached

    # Purge removed + modified files
    dirty = set(delta.removed + delta.modified)
    for path in dirty:
        indexes.pop(path, None)

    # Build index for new + modified files (ONE walk per file)
    for rel_path in delta.changed_paths:
        if not rel_path.endswith(".py"):
            continue
        abs_path = project_root / rel_path
        if not abs_path.is_file():
            continue

        try:
            source = abs_path.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(source, filename=str(abs_path))
            indexes[rel_path] = build_file_index(abs_path, tree, source)
        except Exception:
            pass

        # Yield checkpoint every 10 files
        if len(indexes) % 10 == 0:
            if current_yield_check():
                time.sleep(YIELD_SLEEP)

    _state["file_indexes"] = indexes
    return indexes
```

This is the delta-driven incremental pattern from `index.symbols`:
- Cold start: walk all .py files, build all indexes
- Warm update: purge dirty files, walk only changed files
- Multiple consumers get the same pre-built indexes — no re-walking
- Yield checkpoints every 10 files — web requests not blocked

### 4. File discovery via ScanView

```python
def _discover_files(self, module_dir: Path) -> list[str]:
    """Get Python files in module via ScanView (O(1)) or fallback."""
    view = get_scan_view()
    if view is not None:
        rel_dir = str(module_dir.relative_to(self._project_root))
        return [
            p for p in view.files_in_dir(rel_dir, recursive=True)
            if p.endswith(".py")
        ]

    # CLI fallback
    return [
        str(f.relative_to(self._project_root))
        for f in sorted(module_dir.rglob("*.py"))
        if "__pycache__" not in str(f)
    ][:_MAX_FILES]
```

### 5. Entry pre-filtering per file

Before checking entries against a file, filter to only entries whose required
node types exist in the file's index:

```python
def _filter_relevant_entries(self, file_index: FileNodeIndex, entries):
    """Only check entries whose detection type exists in this file."""
    present_types = set(file_index.nodes_by_type.keys())
    return [
        e for e in entries
        if e.detection.primary.ast_type in present_types
        or any(alt.ast_type in present_types for alt in e.detection.alternatives)
    ]
```

If a file has no `Match` nodes, skip the match/case entry. If no `Import` nodes,
skip all 300+ import-based entries. Most files need <50 entries checked, not 600.

### 6. python_backend.py refactored

The backend no longer does its own walking. It provides matching and context logic
that operates on pre-built data:

- `walk_ast()` — removed from hot path. Only used in `_get_parent_map` which is
  now part of `build_file_index()` (ONE walk)
- `has_future_annotations()` — removed. Computed in `build_file_index()` during
  the single walk
- `extract_imports()` — removed from hot path. Computed in `build_file_index()`
- `node_matches()` — stays. Called with pre-filtered candidates from node index
- `get_node_context()` — stays. Uses pre-built parent_map, no walking

---

## Complexity Analysis

Before M2:
- O(files × entries × all_nodes_per_file)
- 146 files × 600 entries × ~500 nodes = 43,800,000 operations
- Measured: 57 seconds

After M2:
- Walk: O(files × nodes_per_file) — ONE walk per file to build index
- Match: O(files × relevant_entries × candidates_per_type)
- 146 files × ~50 relevant entries × ~10 candidates = 73,000 operations
- Plus 146 × 500 = 73,000 for the single walk
- Total: ~146,000 operations vs 43,800,000 — **300x reduction**
- Expected: <1 second

With delta (warm update — 1 file changed):
- Walk: 1 file × 500 nodes = 500 operations
- Match: 1 file × 50 entries × 10 candidates = 500 operations
- Total: ~1,000 operations — **<10ms**

---

## Files Changed

| File | Action |
|------|--------|
| `src/core/services/compat/analysis/engine.py` | Rewrite: use file indexes, no walking in match loop, ScanView, yield checkpoints, incremental via delta |
| `src/core/services/compat/backends/python_backend.py` | Refactor: remove walk-based methods from hot path, keep matching + context |
| `src/core/services/mediator/registrations/compat.py` | Add compat.file_indexes node with delta-driven incremental accumulator |

---

## Verification

1. `analyze_module(web, 146 files)` completes in <1s (down from 57s)
2. `analyze_module(core, 634 files)` completes in <5s (down from 346s)
3. Second analysis of same module (no file changes) completes in <50ms (cached indexes)
4. After editing 1 file, re-analysis takes <100ms (delta: only that file re-walked)
5. Web requests not blocked during analysis (yield checkpoints)
6. `grep -r "walk_ast\|ast\.walk" src/core/services/compat/analysis/engine.py` — zero hits in matching code
7. Analysis results identical to before (same findings, same count)
