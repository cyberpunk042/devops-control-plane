# 03 — AST Detection Engine Design

> **Document**: 3 of 37
> **Milestone**: M2 — AST detection engine
> **Status**: Draft

---

## 1. Purpose

The AST detection engine is the core analysis component. It takes source code files, parses them into Abstract Syntax Trees, and matches feature database entries against the AST nodes. It replaces all regex-based scanning in v1.

The engine is language-agnostic at the orchestration level — it delegates parsing and matching to language backends. The engine itself handles:
- File discovery and filtering
- Coordinating parsing across files
- Collecting and deduplicating findings
- Caching parsed ASTs for performance
- Reporting results in a uniform format

---

## 2. Why AST, Not Regex

### 2.1 What regex gets wrong

**False positives — matching inside strings and comments:**
```python
# This comment mentions datetime.UTC but it's not code
logger.info("datetime.UTC is a Python 3.11 feature")  # string, not usage
```
Regex matches both. AST ignores both — they're not AST nodes.

**False negatives — missing variant patterns:**
```python
from datetime import UTC                    # regex needs pattern A
from datetime import datetime, UTC          # regex needs pattern B
from datetime import (                      # regex needs pattern C
    datetime,
    UTC,
)
import datetime; x = datetime.UTC           # regex needs pattern D
```
Each variant needs a different regex. AST sees ONE node type (`ImportFrom` or `Attribute`) regardless of formatting.

**False negatives — missing aliased imports:**
```python
from datetime import UTC as utc_constant    # regex for "UTC" won't find "utc_constant" usage
```
AST tracks the alias — it knows `utc_constant` refers to `datetime.UTC`.

**Scope confusion — matching wrong scope:**
```python
UTC = "not datetime"        # local variable shadows the import
def foo():
    from datetime import UTC  # different scope
    return UTC                # this IS the feature
return UTC                    # this is NOT (it's the local variable)
```
Regex can't distinguish. AST has scope information.

### 2.2 What AST gets right

- **Exact node types** — `ImportFrom`, `Attribute`, `Match`, `NamedExpr` — no ambiguity
- **No strings/comments** — AST doesn't include them as executable nodes
- **Format-independent** — same AST whether code is on one line or ten
- **Alias tracking** — knows that `import X as Y` means `Y` refers to `X`
- **Scope awareness** — knows which function/class/module a name belongs to
- **Exact positions** — line number AND column, not approximate regex match position

---

## 3. Architecture

```
┌─────────────────────────────────────────────┐
│           Detection Engine                   │
│                                             │
│  ┌─────────────────────────────────────┐    │
│  │         File Discovery              │    │
│  │  Find all source files for language │    │
│  └──────────────┬──────────────────────┘    │
│                 │                            │
│  ┌──────────────▼──────────────────────┐    │
│  │         AST Parser Cache            │    │
│  │  Parse file → AST, cache result     │    │
│  └──────────────┬──────────────────────┘    │
│                 │                            │
│  ┌──────────────▼──────────────────────┐    │
│  │         Feature Matcher             │    │
│  │  Match entries against AST nodes    │    │
│  └──────────────┬──────────────────────┘    │
│                 │                            │
│  ┌──────────────▼──────────────────────┐    │
│  │         Finding Collector           │    │
│  │  Collect, dedup, enrich findings    │    │
│  └─────────────────────────────────────┘    │
│                                             │
└─────────────────────────────────────────────┘
         │                    ▲
         │                    │
    ┌────▼────┐         ┌────┴────┐
    │ Language │         │ Feature │
    │ Backend  │         │Database │
    └─────────┘         └─────────┘
```

---

## 4. Components

### 4.1 File Discovery

Finds all source files for a given language within a module directory.

```python
class FileDiscovery:
    """Find source files for analysis."""

    def discover(
        self,
        module_dir: Path,
        language: str,
        exclude_patterns: list[str] | None = None,
    ) -> list[Path]:
        """Find all source files for the given language.

        Args:
            module_dir: Root directory of the module to scan
            language: Language identifier (python, javascript, etc.)
            exclude_patterns: Glob patterns to exclude (e.g., __pycache__, node_modules)

        Returns:
            Sorted list of source file paths
        """
```

**Default exclusions per language:**

| Language | Excluded |
|----------|----------|
| Python | `__pycache__`, `.venv`, `venv`, `.tox`, `*.pyc` |
| JavaScript/TypeScript | `node_modules`, `dist`, `build`, `.next` |
| Go | `vendor` (unless `go.mod` has `vendor` flag) |
| Rust | `target` |
| Ruby | `vendor/bundle` |
| Java | `target`, `build`, `.gradle` |
| C# | `bin`, `obj` |
| PHP | `vendor` |
| Elixir | `_build`, `deps` |

### 4.2 AST Parser Cache

Parses files into ASTs and caches the results. Parsing is expensive — a large module might have hundreds of files. We parse each file once and reuse the AST for all feature checks.

```python
class ASTCache:
    """Parse and cache ASTs for source files."""

    def __init__(self, backend: LanguageBackend):
        self._backend = backend
        self._cache: dict[Path, CachedAST] = {}

    def get_ast(self, file_path: Path) -> ASTNode:
        """Get the AST for a file, parsing if needed.

        Uses file modification time to invalidate cache.
        """

    def invalidate(self, file_path: Path) -> None:
        """Invalidate the cache for a file (after a fix modifies it)."""

    def invalidate_all(self) -> None:
        """Clear the entire cache."""

    def stats(self) -> dict:
        """Return cache hit/miss statistics."""
```

**Cache entry:**
```python
@dataclass
class CachedAST:
    ast: ASTNode
    file_path: Path
    mtime: float          # File modification time when parsed
    parse_errors: list    # Any parse errors/warnings
    line_count: int       # For statistics
```

**Cache invalidation:**
- When the fix engine modifies a file, it calls `cache.invalidate(file_path)`
- The verification step re-parses the file fresh
- Cache entries are invalidated if `file.stat().st_mtime > cached.mtime`

### 4.3 Feature Matcher

The core matching logic. Takes an AST and a list of feature database entries, returns findings.

```python
class FeatureMatcher:
    """Match feature database entries against AST nodes."""

    def __init__(self, backend: LanguageBackend):
        self._backend = backend

    def match_file(
        self,
        ast: ASTNode,
        file_path: Path,
        entries: list[FeatureEntry],
    ) -> list[Finding]:
        """Match all entries against a single file's AST.

        For each entry:
        1. Walk the AST looking for nodes matching entry.detection.primary
        2. Also check entry.detection.alternatives
        3. Exclude matches matching entry.detection.exclude
        4. Create a Finding for each match

        Returns:
            List of findings, one per match
        """

    def match_node(
        self,
        node: ASTNode,
        detection_rule: DetectionRule,
    ) -> bool:
        """Check if a single AST node matches a detection rule.

        Delegates to the language backend for language-specific matching.
        """
```

**Matching algorithm:**

```
For each feature entry:
    For each AST node (depth-first walk):
        1. Check if node.type matches entry.detection.primary.ast_type
        2. If yes, check if node attributes match entry.detection.primary.match
        3. If yes, check context constraint (module_level, function_body, etc.)
        4. If yes, check against entry.detection.exclude rules
        5. If not excluded → create Finding

    Repeat for entry.detection.alternatives
```

**Context matching:**

The `context` field on detection rules constrains WHERE in the file a match is valid:

| Context | Meaning |
|---------|---------|
| `any` | Match anywhere (default) |
| `module_level` | Only match at the top level of the file |
| `function_body` | Only match inside a function/method body |
| `class_body` | Only match inside a class body |
| `type_checking_block` | Only match inside `if TYPE_CHECKING:` blocks |
| `try_block` | Only match inside `try:` blocks |
| `except_block` | Only match inside `except:` blocks |

Context is determined by the node's position in the AST tree — walk up to the parent nodes to determine the enclosing scope.

### 4.4 Finding Collector

Collects all findings from the matcher, deduplicates, and enriches them with additional information.

```python
class FindingCollector:
    """Collect, deduplicate, and enrich findings."""

    def __init__(self):
        self._findings: list[Finding] = []

    def add(self, finding: Finding) -> None:
        """Add a finding, skipping duplicates."""

    def add_all(self, findings: list[Finding]) -> None:
        """Add multiple findings."""

    def deduplicate(self) -> None:
        """Remove duplicate findings (same feature, same file, same line)."""

    def enrich(self, import_graph: ImportGraph | None = None) -> None:
        """Enrich findings with transitive import information.

        If import_graph is provided, mark findings that are
        transitively imported by the module being analyzed.
        """

    def get_findings(self) -> list[Finding]:
        """Return all findings, sorted by file then line."""

    def get_by_feature(self, feature_id: str) -> list[Finding]:
        """Return findings for a specific feature."""

    def get_by_file(self, file_path: str) -> list[Finding]:
        """Return findings in a specific file."""

    def get_by_severity(self, severity: str) -> list[Finding]:
        """Return findings with a specific severity."""

    def summary(self) -> dict:
        """Return summary statistics."""
```

**Deduplication rules:**
- Same `feature_id` + same `file` + same `line` + same `col` → duplicate, keep one
- Same `feature_id` + same `file` + different `line` → NOT duplicate (multiple usages)
- Different `feature_id` + same `file` + same `line` → NOT duplicate (multiple features on one line)

---

## 5. Detection Engine API

The main entry point for analysis:

```python
class DetectionEngine:
    """Main API for code analysis."""

    def __init__(
        self,
        registry: FeatureRegistry,
        backend_factory: Callable[[str], LanguageBackend],
    ):
        self._registry = registry
        self._backend_factory = backend_factory
        self._cache = {}  # language -> ASTCache

    def analyze_module(
        self,
        module_dir: Path,
        language: str,
        target_version: str,
        direction: str = "downgrade",
        import_graph: ImportGraph | None = None,
    ) -> AnalysisResult:
        """Analyze a module for version compatibility issues.

        Args:
            module_dir: Path to the module directory
            language: Language identifier
            target_version: The version we're targeting (e.g., "3.8")
            direction: "downgrade" or "upgrade"
            import_graph: Optional pre-computed import graph for transitive analysis

        Returns:
            AnalysisResult with all findings
        """

    def analyze_file(
        self,
        file_path: Path,
        language: str,
        target_version: str,
        direction: str = "downgrade",
    ) -> list[Finding]:
        """Analyze a single file."""

    def analyze_transitive(
        self,
        module_dir: Path,
        language: str,
        target_version: str,
        project_root: Path,
        direction: str = "downgrade",
    ) -> AnalysisResult:
        """Analyze a module INCLUDING its transitive dependencies.

        1. Build import graph from module's files
        2. Follow imports to other modules in the project
        3. Analyze those files too
        4. Mark findings as direct or transitive
        """

    def verify_fix(
        self,
        file_path: Path,
        feature_id: str,
        language: str,
    ) -> VerificationResult:
        """Verify that a fix removed a specific feature from a file.

        1. Invalidate AST cache for this file
        2. Re-parse the file
        3. Run detection for the specific feature
        4. Return pass/fail
        """
```

**AnalysisResult:**

```python
@dataclass
class AnalysisResult:
    module_dir: str
    language: str
    target_version: str
    direction: str
    findings: list[Finding]
    files_scanned: int
    files_with_findings: int
    parse_errors: list[ParseError]    # Files that couldn't be parsed
    scan_duration_ms: int

    @property
    def total_findings(self) -> int:
        return len(self.findings)

    @property
    def direct_findings(self) -> list[Finding]:
        return [f for f in self.findings if not f.is_transitive]

    @property
    def transitive_findings(self) -> list[Finding]:
        return [f for f in self.findings if f.is_transitive]

    @property
    def fixable_findings(self) -> list[Finding]:
        return [f for f in self.findings if f.fix_available]

    @property
    def manual_findings(self) -> list[Finding]:
        return [f for f in self.findings if not f.fix_available]

    def by_feature(self) -> dict[str, list[Finding]]:
        """Group findings by feature_id."""

    def by_file(self) -> dict[str, list[Finding]]:
        """Group findings by file path."""

    def by_severity(self) -> dict[str, list[Finding]]:
        """Group findings by severity."""
```

---

## 6. Language-Specific AST Matching

### 6.1 Python

Python uses the `ast` stdlib module. Every Python version since 3.8 includes it.

**Node types used for detection:**

| AST Node | Feature Example | How It Matches |
|----------|----------------|----------------|
| `ast.ImportFrom` | `from datetime import UTC` | `node.module == 'datetime'` and `'UTC' in [a.name for a in node.names]` |
| `ast.Import` | `import tomllib` | `'tomllib' in [a.name for a in node.names]` |
| `ast.Attribute` | `datetime.UTC` | `node.attr == 'UTC'` and `node.value` is `Name(id='datetime')` |
| `ast.Match` | `match x:` | Node exists → feature used |
| `ast.MatchAs` | `case x as y:` | Pattern matching sub-node |
| `ast.NamedExpr` | `x := expr` | Walrus operator |
| `ast.BinOp` with `BitOr` | `dict_a \| dict_b` | Check operand types at analysis time |
| `ast.Subscript` | `list[int]` | Builtin generic — check if `node.value` is a builtin name |
| `ast.BoolOp` with `\|` on types | `int \| str` | Union type syntax |
| `ast.Try` with `ast.ExceptHandler` star | `except* ValueError:` | Exception group syntax |
| `ast.FunctionDef` with `/` | `def f(x, /, y):` | Positional-only parameter |
| `ast.Call` with method name | `s.removeprefix("x")` | `node.func.attr == 'removeprefix'` |

**Handling `from __future__ import annotations`:**

When a file has `from __future__ import annotations`, type annotation features are NOT runtime issues — they're evaluated lazily. The detection engine must:

1. Check if the file has the `__future__` import
2. If yes, skip annotation-only features (union types in annotations, builtin generics in annotations)
3. Still flag runtime usages of those features (e.g., `isinstance(x, int | str)` is runtime even with `__future__`)

**Implementation:**

```python
class PythonBackend(LanguageBackend):

    def parse_file(self, path: Path) -> ast.Module:
        source = path.read_text(encoding="utf-8", errors="ignore")
        return ast.parse(source, filename=str(path))

    def match_feature(self, tree: ast.Module, detection_rule: DetectionRule) -> list[Finding]:
        findings = []
        for node in ast.walk(tree):
            if self._node_matches(node, detection_rule):
                findings.append(self._create_finding(node, detection_rule))
        return findings

    def _node_matches(self, node: ast.AST, rule: DetectionRule) -> bool:
        # Check AST node type
        if type(node).__name__ != rule.ast_type:
            return False
        # Check attribute matches
        for key, expected in rule.match.items():
            actual = self._get_node_attr(node, key)
            if actual != expected:
                return False
        # Check context
        if rule.context and not self._check_context(node, rule.context):
            return False
        return True
```

### 6.2 JavaScript / TypeScript

Uses tree-sitter for parsing. Tree-sitter produces a concrete syntax tree (CST) that includes all tokens — we query it using tree-sitter's query language or walk the tree.

**Node types:**

| Tree-sitter Node | Feature Example | Query |
|-----------------|----------------|-------|
| `optional_chain_expression` | `a?.b` | Node type match |
| `binary_expression` with `??` | `a ?? b` | `node.operator == '??'` |
| `class_declaration` with `#` fields | `#private` | Check for `private_property_identifier` children |
| `template_string` | `` `hello ${name}` `` | Node type match with ES version check |
| `arrow_function` | `() => {}` | Node type match |
| `for_of_statement` with `await` | `for await (const x of y)` | Check for `await` keyword child |
| `spread_element` | `...args` | Node type match with context |
| `logical_expression` with `??=` | `x ??= default` | Logical assignment operator |

**TypeScript-specific:**

| Node | Feature | Query |
|------|---------|-------|
| `satisfies_expression` | `x satisfies T` | TS 4.9+ |
| `const_type_parameter` | `<const T>` | TS 5.0+ |
| `decorator` on class fields | `@decorator field` | TS 5.0+ |

### 6.3 Go

Uses tree-sitter-go or `go/parser` via subprocess.

| Node | Feature | Version |
|------|---------|---------|
| `type_parameter_list` | `func F[T any]()` | 1.18 (generics) |
| `for_range` over integer | `for i := range 10` | 1.22 |
| `import_spec` with new packages | `"slices"`, `"maps"`, `"log/slog"` | 1.21 |
| `function_call` to `min`/`max` | `min(a, b)` | 1.21 (builtins) |

### 6.4 Rust

Uses tree-sitter-rust. Detection is per-edition AND per-version.

| Node | Feature | Version/Edition |
|------|---------|-----------------|
| `use_declaration` with new paths | `use std::sync::OnceLock` | 1.70 |
| `let_else` | `let Some(x) = y else { return }` | 1.65 |
| `generic_type` with `impl` | `fn f(x: impl Trait)` | 2018 edition |

### 6.5 Ruby

Uses tree-sitter-ruby or Prism (Ruby 3.3+).

| Node | Feature | Version |
|------|---------|---------|
| `pattern_matching` | `case x in` | 3.0 |
| `endless_method` | `def foo = bar` | 3.0 |
| `hash_shorthand` | `{x:, y:}` | 3.1 |
| `anonymous_rest` | `def f(*, **)` | 3.2 |

### 6.6 Java

Uses tree-sitter-java or Eclipse JDT parser.

| Node | Feature | Version |
|------|---------|---------|
| `record_declaration` | `record Point(int x, int y)` | 14 |
| `text_block` | `"""triple quotes"""` | 15 |
| `pattern_match` in instanceof | `if (x instanceof String s)` | 16 |
| `sealed_class` | `sealed class Shape` | 17 |
| `switch_expression` | `int x = switch(y) { ... }` | 14 |
| `virtual_thread` | `Thread.ofVirtual()` | 21 |

### 6.7 C#

Uses tree-sitter-c-sharp or Roslyn.

| Node | Feature | Version |
|------|---------|---------|
| `record_declaration` | `record Point(int X, int Y)` | 9 |
| `global_using` | `global using System;` | 10 |
| `file_scoped_namespace` | `namespace Foo;` | 10 |
| `raw_string_literal` | `"""raw"""` | 11 |
| `list_pattern` | `[1, 2, ..]` | 11 |
| `primary_constructor` | `class C(int x)` | 12 |

### 6.8 PHP

Uses tree-sitter-php or php-parser.

| Node | Feature | Version |
|------|---------|---------|
| `union_type` | `int\|string` | 8.0 |
| `named_argument` | `foo(name: 'bar')` | 8.0 |
| `match_expression` | `match($x) { ... }` | 8.0 |
| `enum_declaration` | `enum Suit: string` | 8.1 |
| `readonly_property` | `readonly int $x` | 8.1 |
| `intersection_type` | `A&B` | 8.1 |

### 6.9 Elixir

Uses tree-sitter-elixir.

| Node | Feature | Version |
|------|---------|---------|
| `range` with step | `1..10//2` | 1.12 |
| `tap` / `then` call | `\|> then(&func/1)` | 1.12 |
| `dbg` call | `dbg(expr)` | 1.14 |
| `Duration` struct | `Duration.new!(hour: 1)` | 1.15 |

---

## 7. Performance Considerations

### 7.1 Parsing cost

| Language | Parser | Typical speed |
|----------|--------|---------------|
| Python | `ast.parse` | ~1ms per file |
| JS/TS | tree-sitter | ~0.5ms per file |
| Go | tree-sitter | ~0.5ms per file |
| Others | tree-sitter | ~0.5ms per file |

For a module with 500 files: ~250–500ms parse time. Acceptable.

### 7.2 Matching cost

Each file's AST is walked once per feature entry. With 200 entries and 500 files:
- 100,000 walk operations
- Each walk visits ~100 nodes (typical file)
- 10M node comparisons
- At ~10ns per comparison: ~100ms

Total analysis time for a large module: ~500ms parse + ~100ms match = ~600ms. Fast enough for interactive use.

### 7.3 Caching strategy

- Cache parsed ASTs in memory during a session
- Invalidate on file modification (mtime check)
- Don't persist cache across sessions — disk cache adds complexity for minimal gain
- For very large projects (10,000+ files), consider lazy parsing — only parse files that are imported by the module

---

## 8. Error Handling

### 8.1 Parse errors

Not all files parse cleanly. The engine must handle:

- **Syntax errors**: File has invalid syntax → skip file, record as `ParseError`
- **Encoding errors**: File has non-UTF-8 encoding → try common encodings, skip if all fail
- **Binary files**: Not a source file despite extension → skip
- **Permission errors**: Can't read file → skip, record error
- **Huge files**: File exceeds size limit (e.g., generated code) → skip with warning

```python
@dataclass
class ParseError:
    file: str
    error_type: str      # "syntax" | "encoding" | "permission" | "size"
    message: str
    line: int | None      # For syntax errors
```

### 8.2 Match errors

Detection rules from the database might not match the parser's node types exactly. Handle:

- **Unknown AST type**: Detection rule references a node type the parser doesn't produce → warning, skip entry for this file
- **Missing attribute**: Detection rule checks an attribute the node doesn't have → no match (not an error)
- **Version mismatch**: File is parsed with Python 3.12 parser but target is 3.8 — some node types may not exist in 3.8's `ast` module → use the running Python's parser, but match against the database entry's version, not the parser version

---

## 9. Integration Points

### 9.1 With Feature Database
- Engine loads entries from `FeatureRegistry`
- Queries: `registry.above_version(language, target)` for downgrade
- Queries: `registry.below_version(language, target)` for upgrade

### 9.2 With Import Chain Resolver (Document 04)
- Engine receives an `ImportGraph` for transitive analysis
- Marks findings as `is_transitive=True` when found via import chain
- Enriches findings with `imported_by` path

### 9.3 With Fix Engine (Document 05)
- Findings are passed to the fix engine
- Fix engine uses `finding.feature_id` to look up the fix strategy
- After fix, engine's `verify_fix()` re-scans to confirm

### 9.4 With Lifecycle (Document 06)
- Engine's `AnalysisResult` determines step state
- Findings exist → step state = NEEDS_ATTENTION
- No findings → step state = PASSED
- Parse errors → step state = FAILED (with details)
