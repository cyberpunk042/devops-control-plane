"""
JVM languages parser — regex-based analysis for Java, Kotlin, and Scala.

Extracts:
    Java (.java):
        - package declaration
        - import statements
        - class, interface, enum, record, annotation declarations
        - method declarations (visibility, static, abstract, synchronized)
        - Annotation usage (@Override, @Inject, etc.)
        - Javadoc comments (/** ... */)
        - Generics detection

    Kotlin (.kt, .kts):
        - package declaration
        - import statements
        - class, interface, object, data class, sealed class, enum class
        - fun declarations (regular, extension, suspend)
        - Companion objects, property declarations
        - Coroutine usage (suspend, launch, async, withContext)
        - KDoc comments (/** ... */)

    Scala (.scala, .sc):
        - package/object declarations
        - import statements
        - class, trait, case class, object declarations
        - def/val/var declarations
        - Implicit, lazy val detection
        - Pattern matching usage
        - ScalaDoc comments (/** ... */)

Registered extensions:
    .java   → language="java"
    .kt     → language="kotlin"
    .kts    → language="kotlin"
    .scala  → language="scala"
    .sc     → language="scala"

Consumers: ParserRegistry → l2_quality (_rubrics "java", "kotlin", "scala"), l2_structure
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
#  Extension → language mapping
# ═══════════════════════════════════════════════════════════════════

_EXT_LANG: dict[str, str] = {
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".scala": "scala",
    ".sc": "scala",
}

# ═══════════════════════════════════════════════════════════════════
#  Shared regex patterns
# ═══════════════════════════════════════════════════════════════════

_RE_BLOCK_COMMENT = re.compile(r"/\*[\s\S]*?\*/")
_RE_LINE_COMMENT = re.compile(r"^\s*//", re.MULTILINE)
_RE_JAVADOC = re.compile(r"/\*\*[\s\S]*?\*/")

# ═══════════════════════════════════════════════════════════════════
#  Java patterns
# ═══════════════════════════════════════════════════════════════════

_RE_JAVA_PACKAGE = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.MULTILINE)

_RE_JAVA_IMPORT = re.compile(
    r"^\s*import\s+(static\s+)?([\w.*]+)\s*;", re.MULTILINE,
)

_RE_JAVA_CLASS = re.compile(
    r"^\s*((?:public|protected|private|abstract|final|static|sealed|non-sealed)\s+)*"
    r"(class|interface|enum|record|@interface)\s+"
    r"(\w+)",
    re.MULTILINE,
)

_RE_JAVA_METHOD = re.compile(
    r"^\s*((?:(?:public|protected|private|abstract|static|final|"
    r"synchronized|native|default|strictfp)\s+)*)"
    r"(?:<[^>]+>\s+)?"                      # optional generic return type params
    r"([\w\[\]<>?,.\s]+?)\s+"               # return type
    r"(\w+)\s*"                              # method name
    r"\(([^)]*)\)\s*"                        # parameters
    r"(?:throws\s+[\w,.\s]+)?\s*"           # optional throws
    r"\{",
    re.MULTILINE,
)

_RE_JAVA_ANNOTATION = re.compile(r"^\s*@(\w+)", re.MULTILINE)

# ═══════════════════════════════════════════════════════════════════
#  Kotlin patterns
# ═══════════════════════════════════════════════════════════════════

_RE_KT_PACKAGE = re.compile(r"^\s*package\s+([\w.]+)", re.MULTILINE)

_RE_KT_IMPORT = re.compile(
    r"^\s*import\s+([\w.*]+)(?:\s+as\s+(\w+))?\s*$", re.MULTILINE,
)

_RE_KT_CLASS = re.compile(
    r"^\s*((?:(?:public|private|protected|internal|abstract|open|"
    r"sealed|inner|data|value|inline|enum|annotation)\s+)*)"
    r"(class|interface|object)\s+"
    r"(\w+)",
    re.MULTILINE,
)

# Kotlin companion object
_RE_KT_COMPANION = re.compile(r"^\s*companion\s+object\b", re.MULTILINE)

_RE_KT_FUN = re.compile(
    r"^\s*((?:(?:public|private|protected|internal|override|open|"
    r"abstract|final|inline|infix|operator|tailrec|suspend|external)\s+)*)"
    r"fun\s+"
    r"(?:(\w+)\.)??"                      # optional extension receiver
    r"(\w+)\s*"                           # function name
    r"\(([^)]*)\)",                       # parameters
    re.MULTILINE,
)

_RE_KT_PROPERTY = re.compile(
    r"^\s*((?:(?:public|private|protected|internal|override|open|"
    r"abstract|final|const|lateinit|lazy)\s+)*)"
    r"(val|var)\s+(\w+)",
    re.MULTILINE,
)

# Coroutine patterns
_RE_KT_SUSPEND = re.compile(r"\bsuspend\s+fun\b")
_RE_KT_LAUNCH = re.compile(r"\blaunch\s*\{")
_RE_KT_ASYNC = re.compile(r"\basync\s*\{")
_RE_KT_WITH_CONTEXT = re.compile(r"\bwithContext\s*\(")

# ═══════════════════════════════════════════════════════════════════
#  Scala patterns
# ═══════════════════════════════════════════════════════════════════

_RE_SCALA_PACKAGE = re.compile(r"^\s*package\s+([\w.]+)", re.MULTILINE)

_RE_SCALA_IMPORT = re.compile(
    r"^\s*import\s+([\w._{}=>,\s*]+)", re.MULTILINE,
)

_RE_SCALA_CLASS = re.compile(
    r"^\s*((?:(?:abstract|sealed|final|implicit|lazy|private|protected|"
    r"override|case)\s+)*)"
    r"(class|trait|object)\s+"
    r"(\w+)",
    re.MULTILINE,
)

_RE_SCALA_DEF = re.compile(
    r"^\s*((?:(?:private|protected|override|final|implicit|lazy)\s+)*)"
    r"def\s+(\w+)\s*"
    r"(?:\[([^\]]*)\])?\s*"              # type params
    r"(?:\(([^)]*)\))?",                 # params
    re.MULTILINE,
)

_RE_SCALA_VAL = re.compile(
    r"^\s*((?:(?:private|protected|override|final|implicit|lazy)\s+)*)"
    r"(val|var)\s+(\w+)",
    re.MULTILINE,
)

_RE_SCALA_MATCH = re.compile(r"\bmatch\s*\{", re.MULTILINE)
_RE_SCALA_IMPLICIT = re.compile(r"\bimplicit\s+")
_RE_SCALA_LAZY = re.compile(r"\blazy\s+val\b")

# ═══════════════════════════════════════════════════════════════════
#  Standard library detection
# ═══════════════════════════════════════════════════════════════════

_JAVA_STDLIB_PREFIXES = (
    "java.", "javax.", "sun.", "jdk.",
)

_KOTLIN_STDLIB_PREFIXES = (
    "kotlin.", "kotlinx.",
)

_SCALA_STDLIB_PREFIXES = (
    "scala.", "java.", "javax.",
)


# ═══════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════


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


def _max_nesting(lines: list[str], start_0: int, end_0: int) -> int:
    """Max brace nesting minus 1 for outer block."""
    max_d = 0
    d = 0
    for i in range(start_0, min(end_0 + 1, len(lines))):
        for ch in lines[i]:
            if ch == "{":
                d += 1
                if d > max_d:
                    max_d = d
            elif ch == "}":
                d = max(0, d - 1)
    return max(0, max_d - 1)


def _has_preceding_javadoc(lines: list[str], lineno_0: int) -> bool:
    """Check if lines preceding lineno have /** ... */ or /// or //."""
    i = lineno_0 - 1
    while i >= 0:
        stripped = lines[i].strip()
        if stripped.startswith("*/") or stripped.endswith("*/"):
            return True
        if stripped.startswith("/**"):
            return True
        if stripped.startswith("///"):
            return True
        if stripped.startswith("@"):
            # annotation, keep going
            i -= 1
            continue
        if stripped.startswith("*"):
            # inside javadoc block, keep going
            i -= 1
            continue
        break
    return False


def _count_params(params_str: str) -> int:
    """Count parameters in a method signature."""
    if not params_str or not params_str.strip():
        return 0
    depth = 0
    count = 1
    for ch in params_str:
        if ch in ("(", "<", "["):
            depth += 1
        elif ch in (")", ">", "]"):
            depth -= 1
        elif ch == "," and depth == 0:
            count += 1
    return count


def _java_visibility(modifiers: str) -> tuple[str, bool]:
    """Extract visibility from Java modifier string."""
    if "private" in modifiers:
        return "private", False
    if "protected" in modifiers:
        return "protected", False
    if "public" in modifiers:
        return "public", True
    return "package", False  # Java default = package-private


def _kt_visibility(modifiers: str) -> tuple[str, bool]:
    """Extract visibility from Kotlin modifier string."""
    if "private" in modifiers:
        return "private", False
    if "protected" in modifiers:
        return "protected", False
    if "internal" in modifiers:
        return "internal", False
    return "public", True  # Kotlin default = public


# ═══════════════════════════════════════════════════════════════════
#  Parser implementation
# ═══════════════════════════════════════════════════════════════════


class JVMParser(BaseParser):
    """Regex-based parser for Java, Kotlin, and Scala source files."""

    @property
    def language(self) -> str:
        return "java"  # primary language

    def extensions(self) -> set[str]:
        return set(_EXT_LANG.keys())

    def parse_file(
        self,
        file_path: Path,
        project_root: Path | None = None,
        project_prefix: str = "src",
    ) -> FileAnalysis:
        """Parse a JVM source file into the universal FileAnalysis model."""
        rel_path = (
            str(file_path.relative_to(project_root))
            if project_root
            else str(file_path)
        )
        ext = file_path.suffix.lower()
        lang = _EXT_LANG.get(ext, "java")

        try:
            source = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return FileAnalysis(
                path=rel_path,
                language=lang,
                file_type="source",
                parse_error=str(exc),
            )

        lines = source.splitlines()

        if lang == "java":
            return self._parse_java(source, lines, rel_path)
        elif lang == "kotlin":
            return self._parse_kotlin(source, lines, rel_path)
        else:
            return self._parse_scala(source, lines, rel_path)

    # ── Java ──────────────────────────────────────────────────

    def _parse_java(
        self, source: str, lines: list[str], rel_path: str,
    ) -> FileAnalysis:
        """Parse Java source."""
        # Package
        pkg = _RE_JAVA_PACKAGE.search(source)
        package_name = pkg.group(1) if pkg else ""

        # Imports
        imports = self._extract_java_imports(source)

        # Symbols
        symbols = self._extract_java_symbols(source, lines)

        # Metrics
        metrics, lang_metrics = self._compute_java_metrics(
            source, lines, imports, symbols, package_name,
        )

        return FileAnalysis(
            path=rel_path,
            language="java",
            file_type="source",
            imports=imports,
            symbols=symbols,
            metrics=metrics,
            language_metrics=lang_metrics,
        )

    def _extract_java_imports(self, source: str) -> list[ImportInfo]:
        imports: list[ImportInfo] = []
        for m in _RE_JAVA_IMPORT.finditer(source):
            is_static = bool(m.group(1))
            module = m.group(2)
            lineno = source[:m.start()].count("\n") + 1

            # Extract name from path
            parts = module.rsplit(".", 1)
            name = parts[-1] if len(parts) > 1 else module

            is_stdlib = module.startswith(_JAVA_STDLIB_PREFIXES)

            imports.append(ImportInfo(
                module=module,
                names=[name],
                is_from=is_static,
                lineno=lineno,
                is_stdlib=is_stdlib,
                is_internal=not is_stdlib and not module.startswith(("org.", "com.", "io.", "net.")),
                is_relative=False,
            ))
        return imports

    def _extract_java_symbols(
        self, source: str, lines: list[str],
    ) -> list[SymbolInfo]:
        symbols: list[SymbolInfo] = []

        # Classes, interfaces, enums, records
        for m in _RE_JAVA_CLASS.finditer(source):
            modifiers = m.group(1) or ""
            kind_raw = m.group(2)
            name = m.group(3)
            lineno_0 = source[:m.start()].count("\n")
            lineno = lineno_0 + 1

            kind_map = {
                "class": "class",
                "interface": "interface",
                "enum": "enum",
                "record": "record",
                "@interface": "annotation",
            }
            kind = kind_map.get(kind_raw, "class")
            visibility, is_public = _java_visibility(modifiers)
            has_doc = _has_preceding_javadoc(lines, lineno_0)

            end_0 = _find_block_end(lines, lineno_0)

            symbols.append(SymbolInfo(
                name=name,
                kind=kind,
                lineno=lineno,
                end_lineno=end_0 + 1,
                body_lines=max(0, end_0 - lineno_0),
                max_nesting=0,
                has_docstring=has_doc,
                is_public=is_public,
                visibility=visibility,
            ))

        # Methods
        for m in _RE_JAVA_METHOD.finditer(source):
            modifiers = m.group(1) or ""
            name = m.group(3)
            params = m.group(4)
            lineno_0 = source[:m.start()].count("\n")
            lineno = lineno_0 + 1

            # Skip control flow keywords that the regex falsely matches
            if name in (
                "if", "for", "while", "switch", "catch",
                "synchronized", "return", "try", "else",
            ):
                continue

            # Skip constructors that match as methods (return type == name)
            return_type = m.group(2).strip()

            visibility, is_public = _java_visibility(modifiers)
            has_doc = _has_preceding_javadoc(lines, lineno_0)
            end_0 = _find_block_end(lines, lineno_0)
            body_lines = max(0, end_0 - lineno_0 - 1)
            nesting = _max_nesting(lines, lineno_0, end_0)
            num_args = _count_params(params)

            kind = "method"
            if "static" in modifiers:
                kind = "static_method"

            decorators: list[str] = []
            if "abstract" in modifiers:
                decorators.append("abstract")
            if "synchronized" in modifiers:
                decorators.append("synchronized")
            if "final" in modifiers:
                decorators.append("final")

            symbols.append(SymbolInfo(
                name=name,
                kind=kind,
                lineno=lineno,
                end_lineno=end_0 + 1,
                body_lines=body_lines,
                max_nesting=nesting,
                has_docstring=has_doc,
                is_public=is_public,
                visibility=visibility,
                num_args=num_args,
                decorators=decorators,
            ))

        return symbols

    def _compute_java_metrics(
        self,
        source: str,
        lines: list[str],
        imports: list[ImportInfo],
        symbols: list[SymbolInfo],
        package_name: str,
    ) -> tuple[FileMetrics, dict]:
        total_lines = len(lines)
        block_comments = _RE_BLOCK_COMMENT.findall(source)
        comment_lines = sum(c.count("\n") + 1 for c in block_comments)
        comment_lines += len(_RE_LINE_COMMENT.findall(source))
        blank_lines = sum(1 for l in lines if not l.strip())
        code_lines = max(0, total_lines - blank_lines - comment_lines)

        methods = [s for s in symbols if "method" in s.kind]
        classes = [s for s in symbols if s.kind in ("class", "interface", "enum", "record", "annotation")]
        func_lengths = [s.body_lines for s in methods]
        avg_func = sum(func_lengths) / len(func_lengths) if func_lengths else 0.0
        max_nest = max((s.max_nesting for s in symbols), default=0)

        # Annotations
        annotations = _RE_JAVA_ANNOTATION.findall(source)
        javadoc_count = len(_RE_JAVADOC.findall(source))

        doc_count = sum(1 for s in symbols if s.has_docstring)
        total_syms = len(symbols)
        doc_coverage = round(doc_count / total_syms * 100, 1) if total_syms else 0.0

        # Test detection
        is_test = any(a in ("Test", "TestInstance", "ParameterizedTest") for a in annotations)

        metrics = FileMetrics(
            total_lines=total_lines,
            code_lines=code_lines,
            blank_lines=blank_lines,
            comment_lines=comment_lines,
            import_count=len(imports),
            function_count=len(methods),
            class_count=len(classes),
            avg_function_length=round(avg_func, 1),
            max_function_length=max(func_lengths, default=0),
            max_nesting_depth=max_nest,
        )

        lang_metrics = {
            "type": "java",
            "package": package_name,
            "class_count": len(classes),
            "interface_count": sum(1 for s in symbols if s.kind == "interface"),
            "enum_count": sum(1 for s in symbols if s.kind == "enum"),
            "record_count": sum(1 for s in symbols if s.kind == "record"),
            "annotation_count": len(annotations),
            "unique_annotations": sorted(set(annotations)),
            "javadoc_count": javadoc_count,
            "doc_coverage": doc_coverage,
            "static_method_count": sum(1 for s in methods if s.kind == "static_method"),
            "is_test_file": is_test,
        }

        return metrics, lang_metrics

    # ── Kotlin ────────────────────────────────────────────────

    def _parse_kotlin(
        self, source: str, lines: list[str], rel_path: str,
    ) -> FileAnalysis:
        pkg = _RE_KT_PACKAGE.search(source)
        package_name = pkg.group(1) if pkg else ""

        imports = self._extract_kotlin_imports(source)
        symbols = self._extract_kotlin_symbols(source, lines)
        metrics, lang_metrics = self._compute_kotlin_metrics(
            source, lines, imports, symbols, package_name,
        )

        return FileAnalysis(
            path=rel_path,
            language="kotlin",
            file_type="source",
            imports=imports,
            symbols=symbols,
            metrics=metrics,
            language_metrics=lang_metrics,
        )

    def _extract_kotlin_imports(self, source: str) -> list[ImportInfo]:
        imports: list[ImportInfo] = []
        for m in _RE_KT_IMPORT.finditer(source):
            module = m.group(1).strip()
            alias = m.group(2)
            lineno = source[:m.start()].count("\n") + 1

            name = alias or module.rsplit(".", 1)[-1]
            is_stdlib = module.startswith(_KOTLIN_STDLIB_PREFIXES + _JAVA_STDLIB_PREFIXES)

            imports.append(ImportInfo(
                module=module,
                names=[name],
                is_from=False,
                lineno=lineno,
                is_stdlib=is_stdlib,
                is_internal=not is_stdlib,
                is_relative=False,
            ))
        return imports

    def _extract_kotlin_symbols(
        self, source: str, lines: list[str],
    ) -> list[SymbolInfo]:
        symbols: list[SymbolInfo] = []

        # Classes / interfaces / objects
        for m in _RE_KT_CLASS.finditer(source):
            modifiers = m.group(1) or ""
            kind_raw = m.group(2)
            name = m.group(3)
            lineno_0 = source[:m.start()].count("\n")
            lineno = lineno_0 + 1
            visibility, is_public = _kt_visibility(modifiers)
            has_doc = _has_preceding_javadoc(lines, lineno_0)

            kind = kind_raw  # class, interface, object
            if "data" in modifiers:
                kind = "data_class"
            elif "sealed" in modifiers:
                kind = "sealed_class"
            elif "enum" in modifiers:
                kind = "enum_class"

            end_0 = _find_block_end(lines, lineno_0) if "{" in (lines[lineno_0] if lineno_0 < len(lines) else "") else lineno_0

            symbols.append(SymbolInfo(
                name=name,
                kind=kind,
                lineno=lineno,
                end_lineno=end_0 + 1,
                body_lines=max(0, end_0 - lineno_0),
                max_nesting=0,
                has_docstring=has_doc,
                is_public=is_public,
                visibility=visibility,
            ))

        # Functions
        for m in _RE_KT_FUN.finditer(source):
            modifiers = m.group(1) or ""
            receiver = m.group(2)
            name = m.group(3)
            params = m.group(4)
            lineno_0 = source[:m.start()].count("\n")
            lineno = lineno_0 + 1
            visibility, is_public = _kt_visibility(modifiers)
            has_doc = _has_preceding_javadoc(lines, lineno_0)
            num_args = _count_params(params)

            # Find body
            line_text = lines[lineno_0] if lineno_0 < len(lines) else ""
            if "{" in line_text:
                end_0 = _find_block_end(lines, lineno_0)
            else:
                end_0 = lineno_0  # expression function or abstract

            body_lines = max(0, end_0 - lineno_0 - 1)
            nesting = _max_nesting(lines, lineno_0, end_0) if end_0 > lineno_0 else 0

            kind = "function"
            if receiver:
                kind = "extension_function"
            if "suspend" in modifiers:
                kind = "suspend_" + kind

            decorators: list[str] = []
            if "inline" in modifiers:
                decorators.append("inline")
            if "operator" in modifiers:
                decorators.append("operator")

            symbols.append(SymbolInfo(
                name=f"{receiver}.{name}" if receiver else name,
                kind=kind,
                lineno=lineno,
                end_lineno=end_0 + 1,
                body_lines=body_lines,
                max_nesting=nesting,
                has_docstring=has_doc,
                is_public=is_public,
                visibility=visibility,
                num_args=num_args,
                decorators=decorators,
            ))

        return symbols

    def _compute_kotlin_metrics(
        self,
        source: str,
        lines: list[str],
        imports: list[ImportInfo],
        symbols: list[SymbolInfo],
        package_name: str,
    ) -> tuple[FileMetrics, dict]:
        total_lines = len(lines)
        block_comments = _RE_BLOCK_COMMENT.findall(source)
        comment_lines = sum(c.count("\n") + 1 for c in block_comments)
        comment_lines += len(_RE_LINE_COMMENT.findall(source))
        blank_lines = sum(1 for l in lines if not l.strip())
        code_lines = max(0, total_lines - blank_lines - comment_lines)

        functions = [s for s in symbols if "function" in s.kind]
        classes = [s for s in symbols if "class" in s.kind or s.kind in ("interface", "object")]
        func_lengths = [s.body_lines for s in functions]
        avg_func = sum(func_lengths) / len(func_lengths) if func_lengths else 0.0
        max_nest = max((s.max_nesting for s in symbols), default=0)

        # Kotlin-specific
        suspend_count = len(_RE_KT_SUSPEND.findall(source))
        launch_count = len(_RE_KT_LAUNCH.findall(source))
        async_count = len(_RE_KT_ASYNC.findall(source))
        companion_count = len(_RE_KT_COMPANION.findall(source))
        property_count = len(_RE_KT_PROPERTY.findall(source))

        doc_count = sum(1 for s in symbols if s.has_docstring)
        total_syms = len(symbols)
        doc_coverage = round(doc_count / total_syms * 100, 1) if total_syms else 0.0

        metrics = FileMetrics(
            total_lines=total_lines,
            code_lines=code_lines,
            blank_lines=blank_lines,
            comment_lines=comment_lines,
            import_count=len(imports),
            function_count=len(functions),
            class_count=len(classes),
            avg_function_length=round(avg_func, 1),
            max_function_length=max(func_lengths, default=0),
            max_nesting_depth=max_nest,
        )

        lang_metrics = {
            "type": "kotlin",
            "package": package_name,
            "data_class_count": sum(1 for s in symbols if s.kind == "data_class"),
            "sealed_class_count": sum(1 for s in symbols if s.kind == "sealed_class"),
            "object_count": sum(1 for s in symbols if s.kind == "object"),
            "companion_count": companion_count,
            "property_count": property_count,
            "extension_function_count": sum(1 for s in functions if "extension" in s.kind),
            "suspend_function_count": suspend_count,
            "coroutine_launch_count": launch_count,
            "coroutine_async_count": async_count,
            "doc_coverage": doc_coverage,
        }

        return metrics, lang_metrics

    # ── Scala ─────────────────────────────────────────────────

    def _parse_scala(
        self, source: str, lines: list[str], rel_path: str,
    ) -> FileAnalysis:
        pkg = _RE_SCALA_PACKAGE.search(source)
        package_name = pkg.group(1) if pkg else ""

        imports = self._extract_scala_imports(source)
        symbols = self._extract_scala_symbols(source, lines)
        metrics, lang_metrics = self._compute_scala_metrics(
            source, lines, imports, symbols, package_name,
        )

        return FileAnalysis(
            path=rel_path,
            language="scala",
            file_type="source",
            imports=imports,
            symbols=symbols,
            metrics=metrics,
            language_metrics=lang_metrics,
        )

    def _extract_scala_imports(self, source: str) -> list[ImportInfo]:
        imports: list[ImportInfo] = []
        for m in _RE_SCALA_IMPORT.finditer(source):
            module = m.group(1).strip()
            lineno = source[:m.start()].count("\n") + 1

            # Clean up multi-import: import foo.{A, B}
            if "{" in module:
                base = module.split("{")[0].strip().rstrip(".")
                names_str = module.split("{")[1].split("}")[0]
                names = [n.strip().split(" => ")[0].strip() for n in names_str.split(",") if n.strip()]
            else:
                base = module
                names = [module.rsplit(".", 1)[-1]]

            is_stdlib = module.startswith(_SCALA_STDLIB_PREFIXES)

            imports.append(ImportInfo(
                module=base,
                names=names,
                is_from=True,
                lineno=lineno,
                is_stdlib=is_stdlib,
                is_internal=not is_stdlib,
                is_relative=False,
            ))
        return imports

    def _extract_scala_symbols(
        self, source: str, lines: list[str],
    ) -> list[SymbolInfo]:
        symbols: list[SymbolInfo] = []

        # Classes / traits / objects
        for m in _RE_SCALA_CLASS.finditer(source):
            modifiers = m.group(1) or ""
            kind_raw = m.group(2)
            name = m.group(3)
            lineno_0 = source[:m.start()].count("\n")
            lineno = lineno_0 + 1
            has_doc = _has_preceding_javadoc(lines, lineno_0)

            kind = kind_raw
            if "case" in modifiers and kind == "class":
                kind = "case_class"

            is_public = "private" not in modifiers and "protected" not in modifiers
            visibility = "private" if "private" in modifiers else ("protected" if "protected" in modifiers else "public")

            line_text = lines[lineno_0] if lineno_0 < len(lines) else ""
            end_0 = _find_block_end(lines, lineno_0) if "{" in line_text else lineno_0

            symbols.append(SymbolInfo(
                name=name,
                kind=kind,
                lineno=lineno,
                end_lineno=end_0 + 1,
                body_lines=max(0, end_0 - lineno_0),
                max_nesting=0,
                has_docstring=has_doc,
                is_public=is_public,
                visibility=visibility,
            ))

        # Defs
        for m in _RE_SCALA_DEF.finditer(source):
            modifiers = m.group(1) or ""
            name = m.group(2)
            params = m.group(4) or ""
            lineno_0 = source[:m.start()].count("\n")
            lineno = lineno_0 + 1
            has_doc = _has_preceding_javadoc(lines, lineno_0)
            num_args = _count_params(params)

            is_public = "private" not in modifiers and "protected" not in modifiers
            visibility = "private" if "private" in modifiers else ("protected" if "protected" in modifiers else "public")

            line_text = lines[lineno_0] if lineno_0 < len(lines) else ""
            if "{" in line_text:
                end_0 = _find_block_end(lines, lineno_0)
            else:
                end_0 = lineno_0

            body_lines = max(0, end_0 - lineno_0 - 1)
            nesting = _max_nesting(lines, lineno_0, end_0) if end_0 > lineno_0 else 0

            kind = "function"
            if "implicit" in modifiers:
                kind = "implicit_function"

            symbols.append(SymbolInfo(
                name=name,
                kind=kind,
                lineno=lineno,
                end_lineno=end_0 + 1,
                body_lines=body_lines,
                max_nesting=nesting,
                has_docstring=has_doc,
                is_public=is_public,
                visibility=visibility,
                num_args=num_args,
            ))

        return symbols

    def _compute_scala_metrics(
        self,
        source: str,
        lines: list[str],
        imports: list[ImportInfo],
        symbols: list[SymbolInfo],
        package_name: str,
    ) -> tuple[FileMetrics, dict]:
        total_lines = len(lines)
        block_comments = _RE_BLOCK_COMMENT.findall(source)
        comment_lines = sum(c.count("\n") + 1 for c in block_comments)
        comment_lines += len(_RE_LINE_COMMENT.findall(source))
        blank_lines = sum(1 for l in lines if not l.strip())
        code_lines = max(0, total_lines - blank_lines - comment_lines)

        functions = [s for s in symbols if "function" in s.kind]
        classes = [s for s in symbols if s.kind in ("class", "case_class", "trait", "object")]
        func_lengths = [s.body_lines for s in functions]
        avg_func = sum(func_lengths) / len(func_lengths) if func_lengths else 0.0
        max_nest = max((s.max_nesting for s in symbols), default=0)

        match_count = len(_RE_SCALA_MATCH.findall(source))
        implicit_count = len(_RE_SCALA_IMPLICIT.findall(source))
        lazy_val_count = len(_RE_SCALA_LAZY.findall(source))
        val_var = _RE_SCALA_VAL.findall(source)
        val_count = sum(1 for _, vv, _ in val_var if vv == "val")
        var_count = sum(1 for _, vv, _ in val_var if vv == "var")

        doc_count = sum(1 for s in symbols if s.has_docstring)
        total_syms = len(symbols)
        doc_coverage = round(doc_count / total_syms * 100, 1) if total_syms else 0.0

        metrics = FileMetrics(
            total_lines=total_lines,
            code_lines=code_lines,
            blank_lines=blank_lines,
            comment_lines=comment_lines,
            import_count=len(imports),
            function_count=len(functions),
            class_count=len(classes),
            avg_function_length=round(avg_func, 1),
            max_function_length=max(func_lengths, default=0),
            max_nesting_depth=max_nest,
        )

        lang_metrics = {
            "type": "scala",
            "package": package_name,
            "case_class_count": sum(1 for s in symbols if s.kind == "case_class"),
            "trait_count": sum(1 for s in symbols if s.kind == "trait"),
            "object_count": sum(1 for s in symbols if s.kind == "object"),
            "match_count": match_count,
            "implicit_count": implicit_count,
            "lazy_val_count": lazy_val_count,
            "val_count": val_count,
            "var_count": var_count,
            "doc_coverage": doc_coverage,
        }

        return metrics, lang_metrics


# ═══════════════════════════════════════════════════════════════════
#  Registry self-registration
# ═══════════════════════════════════════════════════════════════════

_jvm_parser = JVMParser()


def _register():
    """Register JVMParser for all JVM language extensions."""
    from src.core.services.audit.parsers import registry
    registry.register(_jvm_parser)


_register()
