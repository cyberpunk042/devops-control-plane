"""
Template parser — regex-based analysis for template engine files.

Handles template files across multiple engines:
    Jinja2      (.j2, .jinja, .jinja2)
    ERB         (.erb)
    EJS         (.ejs)
    Go Template (.tmpl, .gohtml)
    Handlebars  (.hbs, .handlebars)
    Mustache    (.mustache)
    Pug/Jade    (.pug, .jade)
    Slim        (.slim)
    HAML        (.haml)
    Twig        (.twig)
    HEEx/EEx    (.heex, .eex, .leex)
    Svelte      (.svelte)
    Vue SFC     (.vue)
    Razor       (.cshtml, .razor)
    MDX         (.mdx)

NOTE: .html files ARE claimed by this parser (Phase 8.1). Content-based
analysis via detect_html_content_type() classifies them as jinja2,
jinja2-js, embedded-js, or plain html.

Extracts:
    - Template directives (blocks, loops, conditionals, includes)
    - Macro/partial/component definitions
    - Expression counts ({{ }}, <% %>, etc.)
    - Embedded script/style section detection
    - Line counts and comment detection

Consumers: ParserRegistry → l2_quality (_rubrics "template"), l2_structure
"""

from __future__ import annotations

import re
from pathlib import Path

from src.core.services.audit.parsers._base import (
    BaseParser,
    FileAnalysis,
    FileMetrics,
)

# ═══════════════════════════════════════════════════════════════════
#  Extension → template engine mapping
# ═══════════════════════════════════════════════════════════════════

_EXT_ENGINE: dict[str, str] = {
    # Jinja2 family
    ".j2": "jinja2",
    ".jinja": "jinja2",
    ".jinja2": "jinja2",

    # Ruby
    ".erb": "erb",

    # Node.js
    ".ejs": "ejs",

    # Go
    ".tmpl": "go-template",
    ".gohtml": "go-template",

    # Handlebars / Mustache
    ".hbs": "handlebars",
    ".handlebars": "handlebars",
    ".mustache": "mustache",

    # Indentation-based
    ".pug": "pug",
    ".jade": "pug",
    ".slim": "slim",
    ".haml": "haml",

    # PHP templates
    # .blade.php handled separately (compound extension)

    # Twig (PHP / Symfony)
    ".twig": "twig",

    # Elixir
    ".heex": "heex",
    ".eex": "eex",
    ".leex": "leex",

    # Component frameworks
    ".svelte": "svelte",
    ".vue": "vue",

    # .NET
    ".cshtml": "razor",
    ".razor": "razor",

    # Markdown + JSX
    ".mdx": "mdx",

    # HTML — classified by content via detect_html_content_type() (Phase 8.1)
    ".html": "html-detect",
}


# ═══════════════════════════════════════════════════════════════════
#  Content-based HTML classification (Phase 8.1)
# ═══════════════════════════════════════════════════════════════════

# JS patterns that indicate embedded JavaScript (outside template blocks)
_RE_JS_FUNCTION = re.compile(r"\bfunction\s+\w+\s*\(")
_RE_JS_ARROW = re.compile(r"(?:const|let|var)\s+\w+\s*=\s*(?:\([^)]*\)|[^=])\s*=>")
_RE_JS_ADDEVENTLISTENER = re.compile(r"\baddEventListener\s*\(")
_RE_JS_DOM_API = re.compile(
    r"\b(?:document|window|Element|HTMLElement)\."
    r"(?:getElementById|querySelector|querySelectorAll|createElement|"
    r"addEventListener|dispatchEvent|innerHTML|textContent|classList)\b"
)
_RE_JS_CLASS = re.compile(r"\bclass\s+\w+\s*(?:extends\s+\w+\s*)?\{")
_RE_SCRIPT_TAG = re.compile(r"<script[^>]*>", re.IGNORECASE)
_RE_SCRIPT_CLOSE = re.compile(r"</script>", re.IGNORECASE)


def detect_html_content_type(source: str) -> str:
    """Classify an .html file by examining its content.

    Returns one of:
        "jinja2"      — Jinja2 template ({{ }}, {% %} patterns dominant)
        "jinja2-js"   — Jinja2 wrapper around primarily JavaScript content
        "embedded-js" — HTML with heavy embedded JavaScript (no template engine)
        "html"        — Plain HTML (static content, no significant logic)

    The classification is based on pattern density analysis:
    - Jinja2 patterns: {{ }}, {% %}, {# #}
    - JS patterns: function declarations, DOM API, addEventListener, arrow fns
    - The ratio of JS patterns to total content determines the subtype
    """
    total_lines = source.count("\n") + 1
    if total_lines < 2:
        return "html"

    # ── Count Jinja2 patterns ──
    jinja_exprs = len(_RE_JINJA_EXPR.findall(source))
    jinja_directives = len(_RE_JINJA_DIRECTIVE.findall(source))
    jinja_comments = len(_RE_JINJA_COMMENT.findall(source))
    jinja_total = jinja_exprs + jinja_directives + jinja_comments

    # ── Count JS patterns ──
    js_functions = len(_RE_JS_FUNCTION.findall(source))
    js_arrows = len(_RE_JS_ARROW.findall(source))
    js_listeners = len(_RE_JS_ADDEVENTLISTENER.findall(source))
    js_dom = len(_RE_JS_DOM_API.findall(source))
    js_classes = len(_RE_JS_CLASS.findall(source))
    js_total = js_functions + js_arrows + js_listeners + js_dom + js_classes

    # ── Check if content is wrapped in <script> tags ──
    script_opens = len(_RE_SCRIPT_TAG.findall(source))
    script_closes = len(_RE_SCRIPT_CLOSE.findall(source))
    is_single_script = (script_opens == 1 and script_closes == 1)

    # If the file is basically one giant <script> block, it's JS-dominant
    if is_single_script:
        # Check if the <script> tag wraps most of the file
        script_start = _RE_SCRIPT_TAG.search(source)
        script_end = _RE_SCRIPT_CLOSE.search(source)
        if script_start and script_end:
            script_content_len = script_end.start() - script_start.end()
            if script_content_len / len(source) > 0.8:
                # >80% of the file is inside <script> tags
                if jinja_total > 0:
                    return "jinja2-js"
                return "embedded-js"

    # ── Decision logic ──
    has_jinja = jinja_total >= 3  # At least 3 Jinja2 patterns
    has_js = js_total >= 3        # At least 3 JS patterns

    if has_jinja and has_js:
        # Both present — classify by dominant content
        if js_total > jinja_total * 2:
            return "jinja2-js"  # JS-heavy Jinja2 template
        return "jinja2"         # Normal Jinja2 template
    elif has_jinja:
        return "jinja2"
    elif has_js:
        return "embedded-js"
    else:
        return "html"

# ═══════════════════════════════════════════════════════════════════
#  Per-engine regex patterns
# ═══════════════════════════════════════════════════════════════════

# ── Jinja2 / Twig ─────────────────────────────────────────────
# Expressions: {{ variable }}, {{ foo | filter }}
_RE_JINJA_EXPR = re.compile(r"\{\{.*?\}\}")
# Directives: {% if %}, {% for %}, {% block %}, {% macro %}, etc.
_RE_JINJA_DIRECTIVE = re.compile(r"\{%[-\s]*(\w+).*?%\}")
# Comments: {# ... #}
_RE_JINJA_COMMENT = re.compile(r"\{#.*?#\}", re.DOTALL)

# ── ERB / EEx / Leex ─────────────────────────────────────────
# Output expressions: <%= ... %>
_RE_ERB_OUTPUT = re.compile(r"<%=.*?%>", re.DOTALL)
# Code blocks: <% ... %>
_RE_ERB_CODE = re.compile(r"<%[^=].*?%>", re.DOTALL)
# Comments: <%# ... %>
_RE_ERB_COMMENT = re.compile(r"<%#.*?%>", re.DOTALL)

# ── HEEx (Elixir LiveView) ──────────────────────────────────
# Phoenix components: <.component>, <Component>
_RE_HEEX_COMPONENT = re.compile(r"<\.?\w+[\s/>]")
# Elixir expressions: {@variable}, {expression}
_RE_HEEX_EXPR = re.compile(r"\{[^}]+\}")

# ── Go Templates ─────────────────────────────────────────────
# Actions: {{ .Value }}, {{ range }}, {{ if }}, {{ template }}
_RE_GO_TMPL_ACTION = re.compile(r"\{\{[-\s]*([.\w]+).*?\}\}")
# Custom directives used in THIS project:
# // __IF_FEATURE_xxx__ / // __ENDIF__ / __PLACEHOLDER__
_RE_CUSTOM_DIRECTIVE = re.compile(r"//\s*__(?:IF_(?:NOT_)?FEATURE_\w+|ENDIF)__")
_RE_CUSTOM_PLACEHOLDER = re.compile(r"__[A-Z][A-Z0-9_]+__")

# ── EJS ──────────────────────────────────────────────────────
# Same as ERB but with different semantics
# Output: <%= ... %>, <%- ... %> (unescaped)
_RE_EJS_OUTPUT = re.compile(r"<%[-=].*?%>", re.DOTALL)
# Code: <% ... %>
_RE_EJS_CODE = re.compile(r"<%[^-=].*?%>", re.DOTALL)

# ── Handlebars / Mustache ────────────────────────────────────
# Expressions: {{variable}}, {{{unescaped}}}
_RE_HBS_EXPR = re.compile(r"\{\{\{?[^}]+\}\}\}?")
# Block helpers: {{#if}}, {{#each}}, {{#unless}}
_RE_HBS_BLOCK = re.compile(r"\{\{#(\w+)")
# Partials: {{> partial}}
_RE_HBS_PARTIAL = re.compile(r"\{\{>\s*(\w+)")
# Comments: {{!-- ... --}}, {{! ... }}
_RE_HBS_COMMENT = re.compile(r"\{\{!(?:--.*?--|[^}]*)\}\}", re.DOTALL)

# ── Pug/Jade ────────────────────────────────────────────────
# Mixin definitions: mixin name(args)
_RE_PUG_MIXIN_DEF = re.compile(r"^mixin\s+(\w+)", re.MULTILINE)
# Mixin calls: +name(args)
_RE_PUG_MIXIN_CALL = re.compile(r"^\s*\+(\w+)", re.MULTILINE)
# Includes: include path
_RE_PUG_INCLUDE = re.compile(r"^\s*include\s+", re.MULTILINE)
# Extends: extends path
_RE_PUG_EXTENDS = re.compile(r"^\s*extends\s+", re.MULTILINE)
# Interpolation: #{expr}
_RE_PUG_INTERP = re.compile(r"#\{[^}]+\}")

# ── Razor (.cshtml, .razor) ─────────────────────────────────
# Code blocks: @{ ... }, @code { ... }
_RE_RAZOR_CODE = re.compile(r"@(?:code\s*)?\{")
# Expressions: @variable, @Model.X
_RE_RAZOR_EXPR = re.compile(r"@(?!using|model|page|inject|layout|section|attribute)(\w+)")
# Directives: @using, @model, @page, @inject
_RE_RAZOR_DIRECTIVE = re.compile(r"@(using|model|page|inject|layout|section|attribute)\b")

# ── Svelte / Vue SFC ────────────────────────────────────────
# Section tags: <script>, <style>, <template>
_RE_SECTION_TAG = re.compile(
    r"<(script|style|template)(?:\s[^>]*)?>",
    re.IGNORECASE,
)

# ── MDX ──────────────────────────────────────────────────────
# JSX expressions: {expression}
_RE_MDX_JSX = re.compile(r"\{[^}]+\}")
# Import statements
_RE_MDX_IMPORT = re.compile(r"^import\s+", re.MULTILINE)
# Component usage: <Component />
_RE_MDX_COMPONENT = re.compile(r"<[A-Z]\w+[\s/>]")

# ── HAML ─────────────────────────────────────────────────────
# Ruby interpolation: = expression, - code
_RE_HAML_OUTPUT = re.compile(r"^\s*=\s+", re.MULTILINE)
_RE_HAML_CODE = re.compile(r"^\s*-\s+", re.MULTILINE)

# ── Slim ─────────────────────────────────────────────────────
# Ruby output: = expression, == unescaped
_RE_SLIM_OUTPUT = re.compile(r"^\s*==?\s+", re.MULTILINE)
_RE_SLIM_CODE = re.compile(r"^\s*-\s+", re.MULTILINE)

# ── HTML comment ─────────────────────────────────────────────
_RE_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)


# ═══════════════════════════════════════════════════════════════════
#  Comment prefixes for template engines (single-line)
# ═══════════════════════════════════════════════════════════════════

_ENGINE_COMMENT_PREFIX: dict[str, tuple[str, ...]] = {
    "jinja2": (),       # {# #} handled by regex
    "twig": (),         # {# #} handled by regex
    "erb": (),          # <%# %> handled by regex
    "ejs": (),          # <%# %> handled by regex
    "eex": (),          # <%# %> handled by regex
    "heex": (),         # <%# %> handled by regex
    "leex": (),         # <%# %> handled by regex
    "go-template": ("//",),
    "handlebars": (),   # {{!-- --}} handled by regex
    "mustache": (),     # {{! }} handled by regex
    "pug": ("//",),
    "slim": ("/",),
    "haml": ("-#",),
    "razor": ("//",),   # C#-style
    "svelte": ("//",),
    "vue": ("//",),
    "mdx": (),          # {/* */} handled differently
}


# ═══════════════════════════════════════════════════════════════════
#  Analysis helpers
# ═══════════════════════════════════════════════════════════════════


def _analyze_jinja2(source: str) -> dict:
    """Analyze Jinja2 / Twig template content."""
    directives = _RE_JINJA_DIRECTIVE.findall(source)
    expressions = _RE_JINJA_EXPR.findall(source)
    comments = _RE_JINJA_COMMENT.findall(source)

    # Classify directives
    blocks = [d for d in directives if d in ("block", "endblock")]
    macros = [d for d in directives if d in ("macro", "endmacro")]
    includes = [d for d in directives if d == "include"]
    extends = [d for d in directives if d == "extends"]
    loops = [d for d in directives if d in ("for", "endfor")]
    conditionals = [d for d in directives if d in ("if", "elif", "else", "endif")]
    sets = [d for d in directives if d == "set"]
    filters = [d for d in directives if d == "filter"]
    calls = [d for d in directives if d == "call"]

    return {
        "engine": "jinja2",
        "expression_count": len(expressions),
        "directive_count": len(directives),
        "block_count": len(blocks) // 2,  # block + endblock pairs
        "macro_count": len(macros) // 2,
        "include_count": len(includes),
        "extends_count": len(extends),
        "loop_count": len(loops) // 2,
        "conditional_count": len(conditionals) // 2,
        "set_count": len(sets),
        "filter_count": len(filters),
        "call_count": len(calls),
        "comment_lines": sum(c.count("\n") + 1 for c in comments),
        "has_inheritance": len(extends) > 0,
        "has_macros": len(macros) > 0,
        "logic_density": len(directives) + len(expressions),
    }


def _analyze_erb(source: str) -> dict:
    """Analyze ERB / EEx template content."""
    outputs = _RE_ERB_OUTPUT.findall(source)
    code_blocks = _RE_ERB_CODE.findall(source)
    comments = _RE_ERB_COMMENT.findall(source)

    return {
        "engine": "erb",
        "expression_count": len(outputs),
        "code_block_count": len(code_blocks),
        "directive_count": len(outputs) + len(code_blocks),
        "comment_lines": sum(c.count("\n") + 1 for c in comments),
        "logic_density": len(outputs) + len(code_blocks),
    }


def _analyze_go_template(source: str) -> dict:
    """Analyze Go template content (standard + custom directives)."""
    actions = _RE_GO_TMPL_ACTION.findall(source)
    custom_directives = _RE_CUSTOM_DIRECTIVE.findall(source)
    placeholders = _RE_CUSTOM_PLACEHOLDER.findall(source)

    # Classify standard Go template actions
    range_count = sum(1 for a in actions if a == "range")
    if_count = sum(1 for a in actions if a == "if")
    template_count = sum(1 for a in actions if a == "template")
    define_count = sum(1 for a in actions if a == "define")
    with_count = sum(1 for a in actions if a == "with")

    # Custom directive analysis (this project's pattern)
    feature_gates = len(custom_directives)
    placeholder_count = len(placeholders)

    return {
        "engine": "go-template",
        "action_count": len(actions),
        "directive_count": len(actions) + feature_gates,
        "expression_count": len(actions),
        "range_count": range_count,
        "if_count": if_count,
        "template_count": template_count,
        "define_count": define_count,
        "with_count": with_count,
        "custom_feature_gates": feature_gates,
        "custom_placeholders": placeholder_count,
        "logic_density": len(actions) + feature_gates,
    }


def _analyze_handlebars(source: str) -> dict:
    """Analyze Handlebars / Mustache template content."""
    expressions = _RE_HBS_EXPR.findall(source)
    blocks = _RE_HBS_BLOCK.findall(source)
    partials = _RE_HBS_PARTIAL.findall(source)
    comments = _RE_HBS_COMMENT.findall(source)

    return {
        "engine": "handlebars",
        "expression_count": len(expressions),
        "block_count": len(blocks),
        "partial_count": len(partials),
        "directive_count": len(blocks) + len(partials),
        "comment_lines": sum(c.count("\n") + 1 for c in comments),
        "helpers_used": list(set(blocks)),
        "logic_density": len(expressions) + len(blocks),
    }


def _analyze_pug(source: str, lines: list[str]) -> dict:
    """Analyze Pug/Jade template content."""
    mixin_defs = _RE_PUG_MIXIN_DEF.findall(source)
    mixin_calls = _RE_PUG_MIXIN_CALL.findall(source)
    includes = _RE_PUG_INCLUDE.findall(source)
    extends = _RE_PUG_EXTENDS.findall(source)
    interpolations = _RE_PUG_INTERP.findall(source)

    # Max nesting from indentation
    max_indent = 0
    for line in lines:
        stripped = line.lstrip()
        if stripped:
            indent = len(line) - len(stripped)
            if indent > max_indent:
                max_indent = indent
    max_nesting = max_indent // 2  # Pug uses 2-space indent

    return {
        "engine": "pug",
        "mixin_def_count": len(mixin_defs),
        "mixin_call_count": len(mixin_calls),
        "include_count": len(includes),
        "extends_count": len(extends),
        "expression_count": len(interpolations),
        "directive_count": len(mixin_defs) + len(includes) + len(extends),
        "max_nesting": max_nesting,
        "has_inheritance": len(extends) > 0,
        "has_mixins": len(mixin_defs) > 0,
        "logic_density": len(interpolations) + len(mixin_calls),
    }


def _analyze_razor(source: str) -> dict:
    """Analyze Razor (.cshtml / .razor) template content."""
    code_blocks = _RE_RAZOR_CODE.findall(source)
    expressions = _RE_RAZOR_EXPR.findall(source)
    directives = _RE_RAZOR_DIRECTIVE.findall(source)

    return {
        "engine": "razor",
        "expression_count": len(expressions),
        "code_block_count": len(code_blocks),
        "directive_count": len(directives),
        "directives_used": list(set(directives)),
        "logic_density": len(expressions) + len(code_blocks),
    }


def _analyze_sfc(source: str, engine: str) -> dict:
    """Analyze Single File Component (Svelte/Vue)."""
    sections = _RE_SECTION_TAG.findall(source)
    section_names = [s.lower() for s in sections]

    return {
        "engine": engine,
        "has_script": "script" in section_names,
        "has_style": "style" in section_names,
        "has_template": "template" in section_names,
        "section_count": len(sections),
        "expression_count": len(_RE_JINJA_EXPR.findall(source)),  # {{ }} in Vue
        "directive_count": 0,
        "logic_density": len(sections),
    }


def _analyze_mdx(source: str) -> dict:
    """Analyze MDX (Markdown + JSX) content."""
    imports = _RE_MDX_IMPORT.findall(source)
    jsx_exprs = _RE_MDX_JSX.findall(source)
    components = _RE_MDX_COMPONENT.findall(source)

    return {
        "engine": "mdx",
        "import_count": len(imports),
        "jsx_expression_count": len(jsx_exprs),
        "component_count": len(components),
        "expression_count": len(jsx_exprs),
        "directive_count": len(imports) + len(components),
        "logic_density": len(jsx_exprs) + len(components),
    }


def _analyze_haml(source: str) -> dict:
    """Analyze HAML template content."""
    outputs = _RE_HAML_OUTPUT.findall(source)
    code_lines = _RE_HAML_CODE.findall(source)

    return {
        "engine": "haml",
        "expression_count": len(outputs),
        "code_block_count": len(code_lines),
        "directive_count": len(outputs) + len(code_lines),
        "logic_density": len(outputs) + len(code_lines),
    }


def _analyze_slim(source: str) -> dict:
    """Analyze Slim template content."""
    outputs = _RE_SLIM_OUTPUT.findall(source)
    code_lines = _RE_SLIM_CODE.findall(source)

    return {
        "engine": "slim",
        "expression_count": len(outputs),
        "code_block_count": len(code_lines),
        "directive_count": len(outputs) + len(code_lines),
        "logic_density": len(outputs) + len(code_lines),
    }


def _analyze_heex(source: str) -> dict:
    """Analyze HEEx (Elixir LiveView) template content."""
    components = _RE_HEEX_COMPONENT.findall(source)
    expressions = _RE_HEEX_EXPR.findall(source)
    erb_outputs = _RE_ERB_OUTPUT.findall(source)
    erb_code = _RE_ERB_CODE.findall(source)

    return {
        "engine": "heex",
        "component_count": len(components),
        "expression_count": len(expressions) + len(erb_outputs),
        "code_block_count": len(erb_code),
        "directive_count": len(components) + len(erb_outputs) + len(erb_code),
        "logic_density": len(expressions) + len(erb_outputs) + len(erb_code),
    }


def _analyze_generic(source: str, engine: str) -> dict:
    """Generic analysis for engines without specific patterns."""
    # Try common patterns
    jinja_exprs = len(_RE_JINJA_EXPR.findall(source))
    erb_blocks = len(_RE_ERB_OUTPUT.findall(source)) + len(_RE_ERB_CODE.findall(source))
    hbs_exprs = len(_RE_HBS_EXPR.findall(source))

    total_directives = jinja_exprs + erb_blocks + hbs_exprs

    return {
        "engine": engine,
        "expression_count": total_directives,
        "directive_count": total_directives,
        "logic_density": total_directives,
    }


# Engine → analyzer function
_ANALYZERS: dict[str, object] = {
    "jinja2": _analyze_jinja2,
    "twig": _analyze_jinja2,     # Twig uses similar syntax
    "erb": _analyze_erb,
    "ejs": _analyze_erb,         # EJS uses similar syntax
    "eex": _analyze_erb,
    "leex": _analyze_erb,
    "go-template": _analyze_go_template,
    "handlebars": _analyze_handlebars,
    "mustache": _analyze_handlebars,  # Subset of Handlebars
    "razor": _analyze_razor,
    "svelte": lambda s: _analyze_sfc(s, "svelte"),
    "vue": lambda s: _analyze_sfc(s, "vue"),
    "mdx": _analyze_mdx,
    "haml": _analyze_haml,
    "slim": _analyze_slim,
    "heex": _analyze_heex,
}


# ═══════════════════════════════════════════════════════════════════
#  Parser implementation
# ═══════════════════════════════════════════════════════════════════


class TemplateParser(BaseParser):
    """Parser for template engine files.

    Extracts template-specific metrics:
    - Expression counts ({{ }}, <% %>, etc.)
    - Directive counts (blocks, loops, conditionals)
    - Macro/partial/component definitions
    - Template inheritance and composition patterns
    - Embedded script/style section detection

    .html files are classified by content analysis (Phase 8.1):
    detect_html_content_type() examines patterns to distinguish
    Jinja2 templates, JS-heavy templates, and plain HTML.
    """

    @property
    def language(self) -> str:
        return "template"

    def extensions(self) -> set[str]:
        return set(_EXT_ENGINE.keys())

    def parse_file(
        self,
        file_path: Path,
        project_root: Path | None = None,
        project_prefix: str = "src",
    ) -> FileAnalysis:
        """Parse a template file into the universal FileAnalysis model."""
        rel_path = (
            str(file_path.relative_to(project_root))
            if project_root
            else str(file_path)
        )
        ext = file_path.suffix.lower()
        engine = _EXT_ENGINE.get(ext, "unknown")

        try:
            source = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return FileAnalysis(
                path=rel_path,
                language=engine,
                file_type="template",
                template_engine=engine,
                parse_error=str(exc),
            )

        lines = source.splitlines()
        total_lines = len(lines)

        # ── Content-based HTML classification (Phase 8.1) ────
        content_class = ""
        if engine == "html-detect":
            content_class = detect_html_content_type(source)
            # Map content classification to analyzer engine
            if content_class in ("jinja2", "jinja2-js"):
                engine = "jinja2"
            elif content_class == "embedded-js":
                engine = "html"  # Stays as "html" but with JS metrics
            else:
                engine = "html"

        # ── Engine-specific analysis ─────────────────────────
        analyzer = _ANALYZERS.get(engine)
        if analyzer is not None:
            # Pug needs lines for indentation analysis
            if engine == "pug":
                tmpl_metrics = _analyze_pug(source, lines)
            else:
                tmpl_metrics = analyzer(source)
        else:
            tmpl_metrics = _analyze_generic(source, engine)

        # Annotate with content classification if applicable
        if content_class:
            tmpl_metrics["content_classification"] = content_class

        # ── Determine file_type and language labels ──────────
        if content_class == "jinja2-js":
            file_type = "template"
            lang_label = "jinja2-js"
            tmpl_engine = "jinja2"
        elif content_class == "embedded-js":
            file_type = "template"
            lang_label = "html-js"
            tmpl_engine = "html"
        elif content_class == "html":
            file_type = "markup"
            lang_label = "html"
            tmpl_engine = ""
        elif engine in _ANALYZERS:
            file_type = "template"
            lang_label = engine
            tmpl_engine = engine
        else:
            file_type = "template"
            lang_label = engine
            tmpl_engine = engine

        # ── Line metrics ─────────────────────────────────────
        blank_lines = sum(1 for line in lines if not line.strip())

        # Comment lines: engine-specific block comments + line comments
        comment_lines = tmpl_metrics.get("comment_lines", 0)

        # Add line-based comments
        comment_prefixes = _ENGINE_COMMENT_PREFIX.get(engine, ())
        if comment_prefixes:
            for line in lines:
                stripped = line.strip()
                if stripped and any(stripped.startswith(p) for p in comment_prefixes):
                    comment_lines += 1

        # HTML comments
        html_comments = _RE_HTML_COMMENT.findall(source)
        comment_lines += sum(c.count("\n") + 1 for c in html_comments)

        code_lines = max(0, total_lines - blank_lines - comment_lines)

        # ── Nesting depth ─────────────────────────────────────
        # For indentation-based engines (Pug, Slim, HAML)
        max_nesting = tmpl_metrics.get("max_nesting", 0)
        if not max_nesting and engine not in ("pug", "slim", "haml"):
            # Estimate from HTML nesting / indentation
            max_indent = 0
            for line in lines:
                stripped = line.lstrip()
                if stripped:
                    indent = len(line) - len(stripped)
                    if indent > max_indent:
                        max_indent = indent
            # Use 2-space convention for templates
            max_nesting = max_indent // 2

        metrics = FileMetrics(
            total_lines=total_lines,
            code_lines=code_lines,
            blank_lines=blank_lines,
            comment_lines=comment_lines,
            max_nesting_depth=max_nesting,
        )

        return FileAnalysis(
            path=rel_path,
            language=lang_label,
            file_type=file_type,
            template_engine=tmpl_engine,
            metrics=metrics,
            language_metrics=tmpl_metrics,
        )


# ═══════════════════════════════════════════════════════════════════
#  Registry self-registration
# ═══════════════════════════════════════════════════════════════════

_template_parser = TemplateParser()


def _register():
    """Register TemplateParser for all template extensions."""
    from src.core.services.audit.parsers import registry
    registry.register(_template_parser)


_register()
