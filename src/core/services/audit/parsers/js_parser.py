"""
JavaScript / TypeScript parser — regex-based.

Extracts imports (ES Module + CommonJS), function/class declarations,
exports, JSDoc/TSDoc comments, and basic metrics from JS/TS files.

No external dependencies — uses only Python stdlib regex.

Registered extensions:
    .js, .mjs, .cjs, .jsx  → language="javascript"
    .ts, .mts, .cts, .tsx  → language="typescript"

Consumers: ParserRegistry → l2_quality, l2_structure, scoring
"""

from __future__ import annotations

import re
from pathlib import Path

from src.core.services.audit.parsers._base import (
    BaseParser,
    FileAnalysis,
    FileMetrics,
    ImportInfo,
    SymbolInfo,
)

# ═══════════════════════════════════════════════════════════════════
#  Node.js / browser standard library modules
# ═══════════════════════════════════════════════════════════════════

# Node.js built-in modules (no npm install needed)
_NODE_STDLIB = frozenset({
    "assert", "async_hooks", "buffer", "child_process", "cluster",
    "console", "constants", "crypto", "dgram", "diagnostics_channel",
    "dns", "domain", "events", "fs", "http", "http2", "https",
    "inspector", "module", "net", "os", "path", "perf_hooks",
    "process", "punycode", "querystring", "readline", "repl",
    "stream", "string_decoder", "sys", "timers", "tls", "trace_events",
    "tty", "url", "util", "v8", "vm", "wasi", "worker_threads", "zlib",
    # node: prefixed variants handled separately
})

# Browser globals / built-in APIs (not importable, but sometimes
# referenced in import-like statements for polyfills)
_BROWSER_GLOBALS = frozenset({
    "react", "react-dom",  # Not stdlib but handled separately
})


# ═══════════════════════════════════════════════════════════════════
#  Regex patterns for JS/TS parsing
# ═══════════════════════════════════════════════════════════════════

# ES Module imports:
#   import X from 'Y'
#   import { A, B } from 'Y'
#   import * as X from 'Y'
#   import 'Y'  (side-effect)
_RE_ES_IMPORT = re.compile(
    r"""^[ \t]*import\s+"""
    r"""(?:"""
    r"""(?:type\s+)?"""                             # optional 'type' keyword (TS)
    r"""(?:"""
    r"""(\w+)"""                                    # default import: import X from
    r"""|"""
    r"""\{([^}]*)\}"""                              # named imports: import { A, B } from
    r"""|"""
    r"""\*\s+as\s+(\w+)"""                          # namespace: import * as X from
    r""")"""
    r"""(?:\s*,\s*\{([^}]*)\})?"""                  # optional additional named: import X, { Y } from
    r"""\s+from\s+"""
    r""")?"""
    r"""['"]([^'"]+)['"]"""                          # module specifier
    r"""\s*;?\s*$""",
    re.MULTILINE,
)

# CommonJS require:
#   const X = require('Y')
#   const { A, B } = require('Y')
#   require('Y')
_RE_REQUIRE = re.compile(
    r"""^[ \t]*(?:const|let|var)\s+"""
    r"""(?:"""
    r"""(\w+)"""                                    # const X = require('Y')
    r"""|"""
    r"""\{([^}]*)\}"""                              # const { A, B } = require('Y')
    r""")"""
    r"""\s*=\s*require\s*\(\s*['"]([^'"]+)['"]\s*\)""",
    re.MULTILINE,
)

# Standalone require (side-effect):
#   require('Y')
_RE_REQUIRE_SIDE = re.compile(
    r"""^[ \t]*require\s*\(\s*['"]([^'"]+)['"]\s*\)""",
    re.MULTILINE,
)

# Dynamic import:
#   import('Y')
#   await import('Y')
_RE_DYNAMIC_IMPORT = re.compile(
    r"""(?:await\s+)?import\s*\(\s*['"]([^'"]+)['"]\s*\)""",
)

# Function declarations:
#   function foo(args) {
#   async function foo(args) {
#   export function foo(args) {
#   export default function foo(args) {
_RE_FUNC_DECL = re.compile(
    r"""^[ \t]*(?:export\s+(?:default\s+)?)?"""
    r"""(async\s+)?function\s*(\*?)"""
    r"""\s*(\w+)\s*"""
    r"""\(([^)]*)\)""",
    re.MULTILINE,
)

# Arrow functions assigned to const/let/var:
#   const foo = (args) => {
#   export const foo = async (args) => {
_RE_ARROW_FUNC = re.compile(
    r"""^[ \t]*(?:export\s+(?:default\s+)?)?"""
    r"""(?:const|let|var)\s+"""
    r"""(\w+)\s*=\s*"""
    r"""(async\s+)?"""
    r"""(?:\([^)]*\)|(\w+))\s*=>\s*""",
    re.MULTILINE,
)

# Class declarations:
#   class Foo {
#   class Foo extends Bar {
#   export class Foo {
#   export default class Foo {
_RE_CLASS_DECL = re.compile(
    r"""^[ \t]*(?:export\s+(?:default\s+)?)?"""
    r"""(?:abstract\s+)?"""
    r"""class\s+(\w+)"""
    r"""(?:\s+extends\s+(\w+))?"""
    r"""(?:\s+implements\s+[\w,\s]+)?"""
    r"""\s*\{""",
    re.MULTILINE,
)

# Class methods (inside class body):
#   method(args) {
#   async method(args) {
#   static method(args) {
#   get/set prop(args) {
#   #privateMethod(args) {
_RE_CLASS_METHOD = re.compile(
    r"""^[ \t]+"""
    r"""(?:(?:public|private|protected|static|readonly|abstract|override)\s+)*"""
    r"""(?:async\s+)?"""
    r"""(?:get\s+|set\s+)?"""
    r"""(#?\w+)\s*"""
    r"""\(([^)]*)\)\s*"""
    r"""(?::\s*[^{]+)?"""      # TS return type
    r"""\s*\{""",
    re.MULTILINE,
)

# Export statements:
#   export default X
#   export { A, B }
#   module.exports = X
_RE_EXPORT = re.compile(
    r"""^[ \t]*(?:export\s+(?:default\s+)?|module\.exports\s*=)""",
    re.MULTILINE,
)

# JSDoc / TSDoc block comments
_RE_JSDOC = re.compile(
    r"""/\*\*[\s\S]*?\*/""",
)

# Single-line // comments
_RE_LINE_COMMENT = re.compile(
    r"""^[ \t]*//""",
    re.MULTILINE,
)

# Block comments (non-JSDoc)
_RE_BLOCK_COMMENT = re.compile(
    r"""/\*(?!\*)[\s\S]*?\*/""",
)

# TypeScript type annotations indicators
_RE_TS_TYPE_ANNOTATION = re.compile(
    r""":\s*(?:string|number|boolean|void|any|unknown|never|null|undefined|"""
    r"""object|Array|Map|Set|Promise|Record|Partial|Required|Readonly|"""
    r"""Pick|Omit|Exclude|Extract|ReturnType|Parameters|"""
    r"""\w+(?:\[\])?(?:\s*\|\s*\w+(?:\[\])?)*)\b""",
)

# Interface / type alias declarations
_RE_TS_INTERFACE = re.compile(
    r"""^[ \t]*(?:export\s+)?"""
    r"""(?:interface|type)\s+(\w+)""",
    re.MULTILINE,
)


# ═══════════════════════════════════════════════════════════════════
#  Helper functions
# ═══════════════════════════════════════════════════════════════════


def _is_internal(module: str, project_prefix: str) -> bool:
    """Determine if a module specifier refers to project-internal code.

    Internal indicators:
    - Starts with './' or '../' (relative import)
    - Starts with '@/' (common alias for project root)
    - Starts with '~/' (some bundler configs)
    """
    return module.startswith(("./", "../", "@/", "~/"))


def _is_stdlib(module: str) -> bool:
    """Determine if a module specifier is a Node.js built-in."""
    if module.startswith("node:"):
        return True
    return module in _NODE_STDLIB


def _top_level_package(module: str) -> str:
    """Extract the top-level package name from a module specifier.

    @scope/pkg/sub → @scope/pkg
    lodash/fp → lodash
    ./relative → ./relative
    """
    if module.startswith("@") and "/" in module:
        parts = module.split("/")
        return f"{parts[0]}/{parts[1]}" if len(parts) >= 2 else module
    return module.split("/")[0]


def _extract_names(name_str: str | None) -> list[str]:
    """Extract imported names from a destructured import string.

    Input: 'A, B as C, D'
    Output: ['A', 'C', 'D']
    """
    if not name_str:
        return []
    names = []
    for part in name_str.split(","):
        part = part.strip()
        if not part or part.startswith("type "):
            continue
        # Handle 'X as Y' — use the alias Y
        if " as " in part:
            names.append(part.split(" as ")[-1].strip())
        else:
            names.append(part)
    return names


def _count_nesting(line: str) -> int:
    """Estimate nesting depth from indentation.

    JS typically uses 2 or 4 spaces per level.
    """
    stripped = line.lstrip()
    if not stripped:
        return 0
    indent = len(line) - len(stripped)
    # Detect indent style: 2-space or 4-space
    # Use 2-space as the more common JS convention
    return indent // 2


def _has_preceding_jsdoc(lines: list[str], line_idx: int) -> bool:
    """Check if a function/class has a JSDoc comment immediately preceding it."""
    # Walk backwards from the line before the declaration
    idx = line_idx - 1
    while idx >= 0:
        stripped = lines[idx].strip()
        if stripped.endswith("*/"):
            # Found end of a block comment — check if it's JSDoc
            while idx >= 0:
                if lines[idx].strip().startswith("/**"):
                    return True
                if lines[idx].strip().startswith("/*"):
                    return False  # Regular block comment, not JSDoc
                idx -= 1
            return False
        elif stripped == "" or stripped.startswith("//"):
            idx -= 1
            continue
        elif stripped.startswith("@") or stripped.startswith("export"):
            # Decorator or export keyword — look above those too
            idx -= 1
            continue
        else:
            return False
    return False


def _find_block_end(lines: list[str], start_line: int) -> int:
    """Find the closing brace of a block that starts at start_line.

    Counts { and } to find the matching close.
    Returns the line index of the closing brace, or len(lines)-1 if not found.
    """
    depth = 0
    for i in range(start_line, len(lines)):
        line = lines[i]
        # Skip string contents and comments (rough approximation)
        for ch in line:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return i
    return len(lines) - 1


# ═══════════════════════════════════════════════════════════════════
#  Parser implementation
# ═══════════════════════════════════════════════════════════════════


class JavaScriptParser(BaseParser):
    """Parser for JavaScript and TypeScript files.

    Extracts:
    - ES Module imports (import X from 'Y')
    - CommonJS require() calls
    - Function declarations and arrow functions
    - Class declarations and methods
    - JSDoc/TSDoc documentation
    - Export analysis
    - TypeScript type annotations (for .ts/.tsx files)
    """

    @property
    def language(self) -> str:
        return "javascript"  # Overridden per-file for TypeScript

    def extensions(self) -> set[str]:
        return {
            ".js", ".mjs", ".cjs", ".jsx",
            ".ts", ".mts", ".cts", ".tsx",
        }

    def parse_file(
        self,
        file_path: Path,
        project_root: Path,
        project_prefix: str = "src",
    ) -> FileAnalysis:
        """Parse a JS/TS file into the universal FileAnalysis model."""
        rel_path = str(file_path.relative_to(project_root))
        ext = file_path.suffix.lower()
        is_typescript = ext in (".ts", ".mts", ".cts", ".tsx")
        lang = "typescript" if is_typescript else "javascript"

        try:
            source = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return FileAnalysis(
                path=rel_path,
                language=lang,
                file_type=ext.lstrip("."),
                parse_error=str(exc),
            )

        lines = source.splitlines()
        total_lines = len(lines)

        # ── Imports ───────────────────────────────────────────
        imports = self._extract_imports(source, project_prefix)

        # ── Symbols (functions, classes, interfaces) ──────────
        symbols = self._extract_symbols(lines, is_typescript)

        # ── Metrics ───────────────────────────────────────────
        metrics = self._compute_metrics(
            source, lines, imports, symbols, is_typescript,
        )

        # ── File type refinement ──────────────────────────────
        file_type = ext.lstrip(".")
        if ext in (".jsx", ".tsx"):
            file_type = "tsx" if is_typescript else "jsx"

        return FileAnalysis(
            path=rel_path,
            language=lang,
            file_type=file_type,
            imports=imports,
            symbols=symbols,
            metrics=metrics,
        )

    # ── Import extraction ─────────────────────────────────────

    def _extract_imports(
        self,
        source: str,
        project_prefix: str,
    ) -> list[ImportInfo]:
        """Extract all imports from source."""
        imports: list[ImportInfo] = []
        seen: set[tuple[str, int]] = set()  # (module, lineno) dedup

        # ES Module imports
        for m in _RE_ES_IMPORT.finditer(source):
            default_name = m.group(1)     # import X from 'Y'
            named_str = m.group(2)        # import { A, B } from 'Y'
            namespace = m.group(3)        # import * as X from 'Y'
            extra_named = m.group(4)      # import X, { Y } from 'Y'
            module = m.group(5)           # the module specifier

            lineno = source[:m.start()].count("\n") + 1
            key = (module, lineno)
            if key in seen:
                continue
            seen.add(key)

            names: list[str] = []
            if default_name:
                names.append(default_name)
            if named_str:
                names.extend(_extract_names(named_str))
            if namespace:
                names.append(f"* as {namespace}")
            if extra_named:
                names.extend(_extract_names(extra_named))

            imports.append(ImportInfo(
                module=module,
                names=names,
                is_from=True,
                lineno=lineno,
                is_internal=_is_internal(module, project_prefix),
                is_stdlib=_is_stdlib(module),
                is_relative=module.startswith("."),
            ))

        # CommonJS require
        for m in _RE_REQUIRE.finditer(source):
            name = m.group(1)
            named_str = m.group(2)
            module = m.group(3)

            lineno = source[:m.start()].count("\n") + 1
            key = (module, lineno)
            if key in seen:
                continue
            seen.add(key)

            names = []
            if name:
                names.append(name)
            if named_str:
                names.extend(_extract_names(named_str))

            imports.append(ImportInfo(
                module=module,
                names=names,
                is_from=False,
                lineno=lineno,
                is_internal=_is_internal(module, project_prefix),
                is_stdlib=_is_stdlib(module),
                is_relative=module.startswith("."),
            ))

        # Side-effect require
        for m in _RE_REQUIRE_SIDE.finditer(source):
            module = m.group(1)
            lineno = source[:m.start()].count("\n") + 1
            key = (module, lineno)
            if key in seen:
                continue
            seen.add(key)

            imports.append(ImportInfo(
                module=module,
                names=[],
                is_from=False,
                lineno=lineno,
                is_internal=_is_internal(module, project_prefix),
                is_stdlib=_is_stdlib(module),
                is_relative=module.startswith("."),
            ))

        return imports

    # ── Symbol extraction ─────────────────────────────────────

    def _extract_symbols(
        self,
        lines: list[str],
        is_typescript: bool,
    ) -> list[SymbolInfo]:
        """Extract function, class, and interface declarations."""
        source = "\n".join(lines)
        symbols: list[SymbolInfo] = []

        # ── Function declarations ─────────────────────────────
        for m in _RE_FUNC_DECL.finditer(source):
            is_async = bool(m.group(1))
            is_generator = bool(m.group(2))
            name = m.group(3)
            params = m.group(4)
            lineno = source[:m.start()].count("\n") + 1

            # Find the block end
            end_line = _find_block_end(lines, lineno - 1)
            body_lines = end_line - (lineno - 1) + 1

            # Max nesting within this function
            max_nesting = 0
            base_indent = _count_nesting(lines[lineno - 1])
            for i in range(lineno - 1, min(end_line + 1, len(lines))):
                depth = _count_nesting(lines[i]) - base_indent
                if depth > max_nesting:
                    max_nesting = depth

            # Check for JSDoc
            has_doc = _has_preceding_jsdoc(lines, lineno - 1)

            # Determine if exported
            full_line = lines[lineno - 1].strip()
            is_public = full_line.startswith("export") or not full_line.startswith("_")

            kind = "async_function" if is_async else "function"
            if is_generator:
                kind = "generator"

            symbols.append(SymbolInfo(
                name=name,
                kind=kind,
                lineno=lineno,
                end_lineno=end_line + 1,
                body_lines=body_lines,
                max_nesting=max_nesting,
                has_docstring=has_doc,
                is_public=is_public,
            ))

        # ── Arrow functions ───────────────────────────────────
        for m in _RE_ARROW_FUNC.finditer(source):
            name = m.group(1)
            is_async = bool(m.group(2))
            lineno = source[:m.start()].count("\n") + 1

            # Rough block end estimate — look for the assignment's end
            end_line = _find_block_end(lines, lineno - 1)
            body_lines = end_line - (lineno - 1) + 1

            # Max nesting
            max_nesting = 0
            base_indent = _count_nesting(lines[lineno - 1])
            for i in range(lineno - 1, min(end_line + 1, len(lines))):
                depth = _count_nesting(lines[i]) - base_indent
                if depth > max_nesting:
                    max_nesting = depth

            has_doc = _has_preceding_jsdoc(lines, lineno - 1)
            full_line = lines[lineno - 1].strip()
            is_public = full_line.startswith("export")

            symbols.append(SymbolInfo(
                name=name,
                kind="async_function" if is_async else "function",
                lineno=lineno,
                end_lineno=end_line + 1,
                body_lines=body_lines,
                max_nesting=max_nesting,
                has_docstring=has_doc,
                is_public=is_public,
            ))

        # ── Class declarations ────────────────────────────────
        for m in _RE_CLASS_DECL.finditer(source):
            name = m.group(1)
            parent = m.group(2)
            lineno = source[:m.start()].count("\n") + 1

            end_line = _find_block_end(lines, lineno - 1)
            body_lines = end_line - (lineno - 1) + 1

            has_doc = _has_preceding_jsdoc(lines, lineno - 1)
            full_line = lines[lineno - 1].strip()
            is_public = full_line.startswith("export") or not name.startswith("_")

            # Extract methods within the class body
            class_body = "\n".join(lines[lineno:end_line])
            methods = []
            for mm in _RE_CLASS_METHOD.finditer(class_body):
                method_name = mm.group(1)
                if method_name != "constructor":
                    methods.append(method_name)

            symbols.append(SymbolInfo(
                name=name,
                kind="class",
                lineno=lineno,
                end_lineno=end_line + 1,
                body_lines=body_lines,
                max_nesting=0,
                has_docstring=has_doc,
                is_public=is_public,
                methods=methods,
            ))

        # ── TypeScript interfaces and type aliases ────────────
        if is_typescript:
            for m in _RE_TS_INTERFACE.finditer(source):
                name = m.group(1)
                lineno = source[:m.start()].count("\n") + 1
                full_line = lines[lineno - 1].strip()

                symbols.append(SymbolInfo(
                    name=name,
                    kind="interface",
                    lineno=lineno,
                    end_lineno=lineno,
                    body_lines=1,
                    max_nesting=0,
                    has_docstring=_has_preceding_jsdoc(lines, lineno - 1),
                    is_public=full_line.startswith("export"),
                ))

        return symbols

    # ── Metrics computation ───────────────────────────────────

    def _compute_metrics(
        self,
        source: str,
        lines: list[str],
        imports: list[ImportInfo],
        symbols: list[SymbolInfo],
        is_typescript: bool,
    ) -> FileMetrics:
        """Compute file-level metrics."""
        total_lines = len(lines)

        # Blank lines
        blank_lines = sum(1 for line in lines if not line.strip())

        # Comment lines (single-line //)
        comment_lines = len(_RE_LINE_COMMENT.findall(source))

        # Add block comment lines
        for m in _RE_BLOCK_COMMENT.finditer(source):
            comment_lines += m.group(0).count("\n") + 1
        for m in _RE_JSDOC.finditer(source):
            comment_lines += m.group(0).count("\n") + 1

        code_lines = max(0, total_lines - blank_lines - comment_lines)

        # Functions and classes
        func_count = sum(1 for s in symbols
                        if s.kind in ("function", "async_function", "generator"))
        class_count = sum(1 for s in symbols if s.kind == "class")

        # Average function length
        func_lengths = [s.body_lines for s in symbols
                       if s.kind in ("function", "async_function", "generator")]
        avg_func_len = (
            sum(func_lengths) / len(func_lengths) if func_lengths else 0.0
        )

        # Max nesting across all symbols
        max_nesting = max(
            (s.max_nesting for s in symbols if s.max_nesting > 0),
            default=0,
        )

        # Docstring coverage (JSDoc coverage)
        documented = sum(1 for s in symbols if s.has_docstring)
        total_funcs_and_classes = func_count + class_count
        docstring_pct = (
            documented / total_funcs_and_classes * 100
            if total_funcs_and_classes > 0
            else 100.0
        )

        # Type hint coverage (TypeScript only)
        type_hint_pct = 0.0
        if is_typescript:
            type_annotations = len(_RE_TS_TYPE_ANNOTATION.findall(source))
            # Heuristic: annotations per function/class as proxy for coverage
            type_hint_pct = min(
                100.0,
                type_annotations / max(1, total_funcs_and_classes) * 20,
            )

        return FileMetrics(
            total_lines=total_lines,
            code_lines=code_lines,
            blank_lines=blank_lines,
            comment_lines=comment_lines,
            docstring_lines=sum(
                m.group(0).count("\n") + 1
                for m in _RE_JSDOC.finditer(source)
            ),
            import_count=len(imports),
            function_count=func_count,
            class_count=class_count,
            avg_function_length=round(avg_func_len, 1),
            max_function_length=max(func_lengths, default=0),
            max_nesting_depth=max_nesting,
            has_type_hints=round(type_hint_pct, 1),
        )


# ═══════════════════════════════════════════════════════════════════
#  Registry self-registration
# ═══════════════════════════════════════════════════════════════════

_js_parser = JavaScriptParser()


def _register():
    """Register JavaScriptParser for JS/TS extensions."""
    from src.core.services.audit.parsers import registry
    registry.register(_js_parser)


_register()
