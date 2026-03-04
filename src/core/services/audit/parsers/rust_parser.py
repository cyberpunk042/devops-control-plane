"""
Rust parser — regex-based analysis for .rs source files.

Extracts:
    - Module declarations (mod)
    - Use/import statements (use crate::, use std::, use super::)
    - Function declarations (fn, pub fn, async fn)
    - Type declarations (struct, enum, trait, impl)
    - Visibility modifiers (pub, pub(crate), pub(super))
    - Unsafe block counting
    - Doc comments (/// and //!)
    - Lifetime annotations
    - Derive macro usage
    - Attribute macros (#[...])

Registered extensions: .rs

Consumers: ParserRegistry → l2_quality (_rubrics "rust"), l2_structure
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
#  Regex patterns
# ═══════════════════════════════════════════════════════════════════

# ── Use / imports ────────────────────────────────────────────────

# use std::collections::HashMap;
# use crate::models::User;
# use super::helpers;
_RE_USE = re.compile(
    r"^\s*(?:pub\s+)?use\s+([^;{]+?)(?:\s*(?:as\s+(\w+))?\s*;|\s*\{([^}]+)\}\s*;)",
    re.MULTILINE,
)

# mod declarations
_RE_MOD = re.compile(
    r"^\s*(?:pub(?:\([^)]*\))?\s+)?mod\s+(\w+)\s*[;{]",
    re.MULTILINE,
)

# ── Functions ────────────────────────────────────────────────────

# fn name(args) -> ReturnType {
# pub fn name(args) -> ReturnType {
# pub(crate) async fn name(args) -> ReturnType {
# pub async unsafe fn name<T>(args) -> ReturnType {
_RE_FN = re.compile(
    r"^\s*"
    r"((?:pub(?:\([^)]*\))?\s+)?)"    # visibility
    r"((?:async\s+)?)"                 # async modifier
    r"((?:unsafe\s+)?)"               # unsafe modifier
    r"(?:extern\s+\"[^\"]*\"\s+)?"    # extern "C" etc.
    r"fn\s+"
    r"(\w+)"                           # function name
    r"(?:<[^>]*>)?\s*"                 # optional generic params
    r"\(([^)]*)\)"                     # parameters
    r"(?:\s*->\s*(.+?))?\s*"           # optional return type (handles generics)
    r"(?:where\s+[^{]*)?"             # optional where clause
    r"\{",
    re.MULTILINE,
)

# ── Types ────────────────────────────────────────────────────────

# struct Name { ... }  or  struct Name(...);
_RE_STRUCT = re.compile(
    r"^\s*((?:pub(?:\([^)]*\))?\s+)?)"
    r"struct\s+(\w+)",
    re.MULTILINE,
)

# enum Name { ... }
_RE_ENUM = re.compile(
    r"^\s*((?:pub(?:\([^)]*\))?\s+)?)"
    r"enum\s+(\w+)",
    re.MULTILINE,
)

# trait Name { ... }
_RE_TRAIT = re.compile(
    r"^\s*((?:pub(?:\([^)]*\))?\s+)?)"
    r"trait\s+(\w+)",
    re.MULTILINE,
)

# impl Name { ... }  or  impl Trait for Type { ... }
_RE_IMPL = re.compile(
    r"^\s*impl(?:<[^>]*>)?\s+(?:(\w+)\s+for\s+)?(\w+)",
    re.MULTILINE,
)

# type alias: type Name = ...;
_RE_TYPE_ALIAS = re.compile(
    r"^\s*((?:pub(?:\([^)]*\))?\s+)?)"
    r"type\s+(\w+)\s*(?:<[^>]*>)?\s*=",
    re.MULTILINE,
)

# ── Rust-specific patterns ──────────────────────────────────────

_RE_UNSAFE = re.compile(r"\bunsafe\s*\{")
_RE_LIFETIME = re.compile(r"'[a-zA-Z_]\w*")
_RE_DERIVE = re.compile(r"#\[derive\(([^)]+)\)\]")
_RE_ATTRIBUTE = re.compile(r"#\[(?!derive)[^\]]+\]")
_RE_MACRO_CALL = re.compile(r"\b(\w+)!")
_RE_MATCH = re.compile(r"\bmatch\b")
_RE_UNWRAP = re.compile(r"\.(unwrap|expect)\(")
_RE_QUESTION_MARK = re.compile(r"\?[;\s\n]")

# ── Comments ─────────────────────────────────────────────────────

_RE_DOC_COMMENT = re.compile(r"^\s*///", re.MULTILINE)
_RE_INNER_DOC = re.compile(r"^\s*//!", re.MULTILINE)
_RE_LINE_COMMENT = re.compile(r"^\s*//(?!/)", re.MULTILINE)  # // but not ///
_RE_BLOCK_COMMENT = re.compile(r"/\*[\s\S]*?\*/")

# ── Standard library crate roots ────────────────────────────────

_RUST_STDLIB = frozenset({
    "std", "core", "alloc", "proc_macro",
})


# ═══════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════


def _visibility(vis_str: str) -> tuple[str, bool]:
    """Parse Rust visibility into (visibility_label, is_public)."""
    vis = vis_str.strip()
    if not vis:
        return "private", False
    if vis == "pub":
        return "public", True
    if "crate" in vis:
        return "internal", False
    if "super" in vis:
        return "protected", False
    return "public", True


def _is_stdlib_use(path: str) -> bool:
    """Check if a use path refers to stdlib."""
    root = path.split("::")[0].strip()
    return root in _RUST_STDLIB


def _is_internal_use(path: str) -> bool:
    """Check if a use path is crate-internal."""
    root = path.split("::")[0].strip()
    return root in ("crate", "super", "self")


def _count_params(params_str: str) -> int:
    """Count function parameters (excluding self variants)."""
    if not params_str or not params_str.strip():
        return 0
    # Remove self variants
    clean = re.sub(r"&?\s*(?:mut\s+)?self\s*,?", "", params_str).strip()
    if not clean:
        return 0
    depth = 0
    count = 1
    for ch in clean:
        if ch in ("(", "<", "["):
            depth += 1
        elif ch in (")", ">", "]"):
            depth -= 1
        elif ch == "," and depth == 0:
            count += 1
    return count


def _has_self_param(params_str: str) -> bool:
    """Check if function has a self parameter (making it a method)."""
    return bool(re.search(r"(?:&\s*)?(?:mut\s+)?self\b", params_str))


def _has_preceding_doc(lines: list[str], lineno_0: int) -> bool:
    """Check if lines preceding lineno have doc comments (///)."""
    i = lineno_0 - 1
    while i >= 0:
        stripped = lines[i].strip()
        if stripped.startswith("///") or stripped.startswith("//!"):
            return True
        if stripped.startswith("#["):
            # Attribute — keep looking above it
            i -= 1
            continue
        break
    return False


def _find_block_end(lines: list[str], start_0: int) -> int:
    """Find closing } for a block starting at start_0."""
    depth = 0
    for i in range(start_0, len(lines)):
        for ch in lines[i]:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return i
    return len(lines) - 1


def _max_nesting_in_range(lines: list[str], start_0: int, end_0: int) -> int:
    """Max brace nesting in range, minus 1 for the outer block."""
    max_depth = 0
    depth = 0
    for i in range(start_0, min(end_0 + 1, len(lines))):
        for ch in lines[i]:
            if ch == "{":
                depth += 1
                if depth > max_depth:
                    max_depth = depth
            elif ch == "}":
                depth = max(0, depth - 1)
    return max(0, max_depth - 1)


# ═══════════════════════════════════════════════════════════════════
#  Parser implementation
# ═══════════════════════════════════════════════════════════════════


class RustParser(BaseParser):
    """Regex-based parser for Rust source files.

    Extracts:
    - use/import statements (stdlib, crate, external)
    - fn declarations (regular, methods, async, unsafe)
    - Type declarations (struct, enum, trait, impl)
    - Visibility modifiers
    - Unsafe block counting
    - Doc comments (///, //!)
    - Lifetime and derive macro analysis
    - Error handling patterns (?, unwrap, expect)
    """

    @property
    def language(self) -> str:
        return "rust"

    def extensions(self) -> set[str]:
        return {".rs"}

    def parse_file(
        self,
        file_path: Path,
        project_root: Path | None = None,
        project_prefix: str = "src",
    ) -> FileAnalysis:
        """Parse a Rust source file into the universal FileAnalysis model."""
        rel_path = (
            str(file_path.relative_to(project_root))
            if project_root
            else str(file_path)
        )

        try:
            source = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return FileAnalysis(
                path=rel_path,
                language="rust",
                file_type="source",
                parse_error=str(exc),
            )

        lines = source.splitlines()

        imports = self._extract_imports(source)
        symbols = self._extract_symbols(source, lines)
        metrics, lang_metrics = self._compute_metrics(
            source, lines, imports, symbols,
        )

        return FileAnalysis(
            path=rel_path,
            language="rust",
            file_type="source",
            imports=imports,
            symbols=symbols,
            metrics=metrics,
            language_metrics=lang_metrics,
        )

    # ── Import extraction ─────────────────────────────────────

    def _extract_imports(self, source: str) -> list[ImportInfo]:
        """Extract use statements."""
        imports: list[ImportInfo] = []

        for m in _RE_USE.finditer(source):
            path = m.group(1).strip()
            alias = m.group(2)
            group = m.group(3)  # { A, B, C }
            lineno = source[:m.start()].count("\n") + 1

            if group:
                # use std::collections::{HashMap, BTreeMap};
                names = [n.strip().split(" as ")[0].strip() for n in group.split(",") if n.strip()]
            elif alias:
                names = [alias]
            else:
                names = [path.split("::")[-1].strip()]

            module = path.rstrip(":").rstrip()  # clean trailing ::

            imports.append(ImportInfo(
                module=module,
                names=names,
                is_from=True,
                lineno=lineno,
                is_stdlib=_is_stdlib_use(module),
                is_internal=_is_internal_use(module),
                is_relative=module.startswith("super"),
            ))

        return imports

    # ── Symbol extraction ─────────────────────────────────────

    def _extract_symbols(
        self, source: str, lines: list[str],
    ) -> list[SymbolInfo]:
        """Extract function and type declarations."""
        symbols: list[SymbolInfo] = []

        # ── Functions ─────────────────────────────────────────
        for m in _RE_FN.finditer(source):
            vis_str = m.group(1).strip()
            is_async = bool(m.group(2).strip())
            is_unsafe = bool(m.group(3).strip())
            name = m.group(4)
            params = m.group(5)
            return_type = m.group(6) or ""

            lineno_0 = source[:m.start()].count("\n")
            lineno = lineno_0 + 1
            end_0 = _find_block_end(lines, lineno_0)
            end_lineno = end_0 + 1
            body_lines = max(0, end_0 - lineno_0 - 1)
            max_nesting = _max_nesting_in_range(lines, lineno_0, end_0)

            visibility, is_public = _visibility(vis_str)
            has_doc = _has_preceding_doc(lines, lineno_0)
            is_method = _has_self_param(params)
            num_args = _count_params(params)

            kind = "method" if is_method else "function"
            if is_async:
                kind = "async_" + kind

            decorators: list[str] = []
            if is_unsafe:
                decorators.append("unsafe")

            symbols.append(SymbolInfo(
                name=name,
                kind=kind,
                lineno=lineno,
                end_lineno=end_lineno,
                body_lines=body_lines,
                max_nesting=max_nesting,
                has_docstring=has_doc,
                is_public=is_public,
                visibility=visibility,
                num_args=num_args,
                decorators=decorators,
            ))

        # ── Structs ───────────────────────────────────────────
        for m in _RE_STRUCT.finditer(source):
            vis_str = m.group(1).strip()
            name = m.group(2)
            lineno_0 = source[:m.start()].count("\n")
            lineno = lineno_0 + 1
            visibility, is_public = _visibility(vis_str)
            has_doc = _has_preceding_doc(lines, lineno_0)

            # Check if it's a block struct or tuple struct
            rest_of_line = lines[lineno_0] if lineno_0 < len(lines) else ""
            if "{" in rest_of_line:
                end_0 = _find_block_end(lines, lineno_0)
            else:
                end_0 = lineno_0  # tuple struct or unit struct (single line)

            symbols.append(SymbolInfo(
                name=name,
                kind="struct",
                lineno=lineno,
                end_lineno=end_0 + 1,
                body_lines=max(0, end_0 - lineno_0),
                max_nesting=0,
                has_docstring=has_doc,
                is_public=is_public,
                visibility=visibility,
            ))

        # ── Enums ─────────────────────────────────────────────
        for m in _RE_ENUM.finditer(source):
            vis_str = m.group(1).strip()
            name = m.group(2)
            lineno_0 = source[:m.start()].count("\n")
            lineno = lineno_0 + 1
            visibility, is_public = _visibility(vis_str)
            has_doc = _has_preceding_doc(lines, lineno_0)
            end_0 = _find_block_end(lines, lineno_0)

            symbols.append(SymbolInfo(
                name=name,
                kind="enum",
                lineno=lineno,
                end_lineno=end_0 + 1,
                body_lines=max(0, end_0 - lineno_0),
                max_nesting=0,
                has_docstring=has_doc,
                is_public=is_public,
                visibility=visibility,
            ))

        # ── Traits ────────────────────────────────────────────
        for m in _RE_TRAIT.finditer(source):
            vis_str = m.group(1).strip()
            name = m.group(2)
            lineno_0 = source[:m.start()].count("\n")
            lineno = lineno_0 + 1
            visibility, is_public = _visibility(vis_str)
            has_doc = _has_preceding_doc(lines, lineno_0)
            end_0 = _find_block_end(lines, lineno_0)

            # Extract trait method names
            methods = []
            for i in range(lineno_0 + 1, end_0):
                fn_match = re.search(r"fn\s+(\w+)", lines[i])
                if fn_match:
                    methods.append(fn_match.group(1))

            symbols.append(SymbolInfo(
                name=name,
                kind="trait",
                lineno=lineno,
                end_lineno=end_0 + 1,
                body_lines=max(0, end_0 - lineno_0),
                max_nesting=0,
                has_docstring=has_doc,
                is_public=is_public,
                visibility=visibility,
                methods=methods,
            ))

        return symbols

    # ── Metrics computation ───────────────────────────────────

    def _compute_metrics(
        self,
        source: str,
        lines: list[str],
        imports: list[ImportInfo],
        symbols: list[SymbolInfo],
    ) -> tuple[FileMetrics, dict]:
        """Compute file-level and Rust-specific metrics."""
        total_lines = len(lines)

        # ── Line classification ───────────────────────────────
        block_comments = _RE_BLOCK_COMMENT.findall(source)
        comment_lines = sum(c.count("\n") + 1 for c in block_comments)
        comment_lines += len(_RE_DOC_COMMENT.findall(source))
        comment_lines += len(_RE_INNER_DOC.findall(source))
        comment_lines += len(_RE_LINE_COMMENT.findall(source))

        blank_lines = sum(1 for line in lines if not line.strip())
        code_lines = max(0, total_lines - blank_lines - comment_lines)

        # ── Symbol classification ────────────────────────────
        functions = [s for s in symbols if "function" in s.kind or "method" in s.kind]
        structs = [s for s in symbols if s.kind == "struct"]
        enums = [s for s in symbols if s.kind == "enum"]
        traits = [s for s in symbols if s.kind == "trait"]

        func_lengths = [s.body_lines for s in functions]
        avg_func_len = (
            sum(func_lengths) / len(func_lengths) if func_lengths else 0.0
        )
        max_nesting = max((s.max_nesting for s in symbols), default=0)

        # ── Rust-specific counts ─────────────────────────────
        unsafe_count = len(_RE_UNSAFE.findall(source))
        lifetime_count = len(_RE_LIFETIME.findall(source))
        derive_matches = _RE_DERIVE.findall(source)
        derives_used = []
        for d in derive_matches:
            derives_used.extend([x.strip() for x in d.split(",")])
        attribute_count = len(_RE_ATTRIBUTE.findall(source))
        macro_calls = _RE_MACRO_CALL.findall(source)
        match_count = len(_RE_MATCH.findall(source))
        unwrap_count = len(_RE_UNWRAP.findall(source))
        question_mark_count = len(_RE_QUESTION_MARK.findall(source))
        mod_count = len(_RE_MOD.findall(source))

        # ── Doc coverage ──────────────────────────────────────
        total_symbols = len(symbols)
        documented = sum(1 for s in symbols if s.has_docstring)
        doc_coverage = (
            round(documented / total_symbols * 100, 1) if total_symbols else 0.0
        )

        # ── Impl blocks ──────────────────────────────────────
        impl_blocks = _RE_IMPL.findall(source)
        trait_impls = sum(1 for trait_name, _ in impl_blocks if trait_name)
        inherent_impls = sum(1 for trait_name, _ in impl_blocks if not trait_name)

        # Test detection
        is_test = any(
            s.name.startswith("test_") or s.name == "tests"
            for s in symbols
        ) or "#[cfg(test)]" in source

        # ── Build metrics ─────────────────────────────────────
        metrics = FileMetrics(
            total_lines=total_lines,
            code_lines=code_lines,
            blank_lines=blank_lines,
            comment_lines=comment_lines,
            import_count=len(imports),
            function_count=len(functions),
            class_count=len(structs) + len(enums) + len(traits),
            avg_function_length=round(avg_func_len, 1),
            max_function_length=max(func_lengths, default=0),
            max_nesting_depth=max_nesting,
        )

        lang_metrics = {
            "struct_count": len(structs),
            "enum_count": len(enums),
            "trait_count": len(traits),
            "impl_count": len(impl_blocks),
            "trait_impl_count": trait_impls,
            "inherent_impl_count": inherent_impls,
            "mod_count": mod_count,
            "unsafe_block_count": unsafe_count,
            "lifetime_count": lifetime_count,
            "derives_used": sorted(set(derives_used)),
            "attribute_count": attribute_count,
            "macro_call_count": len(macro_calls),
            "match_count": match_count,
            "unwrap_count": unwrap_count,
            "question_mark_count": question_mark_count,
            "doc_coverage": doc_coverage,
            "is_test_file": is_test,
        }

        return metrics, lang_metrics


# ═══════════════════════════════════════════════════════════════════
#  Registry self-registration
# ═══════════════════════════════════════════════════════════════════

_rust_parser = RustParser()


def _register():
    """Register RustParser for .rs files."""
    from src.core.services.audit.parsers import registry
    registry.register(_rust_parser)


_register()
