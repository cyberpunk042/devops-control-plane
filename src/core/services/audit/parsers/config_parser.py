"""
Config/Infrastructure parser — regex-based analysis for configuration,
infrastructure, scripting, and documentation files.

Covers:
    YAML (.yml, .yaml)       — key count, nesting depth, anchors/aliases,
                                purpose heuristic (CI, K8s, Compose, Helm)
    JSON (.json)             — key count, nesting depth, array count
    TOML (.toml)             — section count, key count
    HCL/Terraform (.tf, .tfvars) — resource/variable/output/module/data blocks
    Dockerfile (Dockerfile*) — instruction count, FROM/RUN/COPY/EXPOSE counts,
                                multi-stage detection, layer count
    Makefile (Makefile, *.mk)— target count, .PHONY declarations
    Shell (.sh, .bash, .zsh) — function count, error handling (set -e, pipefail),
                                shebang detection, variable count
    SQL (.sql)               — statement counts (SELECT, INSERT, UPDATE, DELETE,
                                CREATE, ALTER, DROP), transaction usage
    GraphQL (.graphql, .gql) — query/mutation/subscription/type/input/enum counts
    Markdown (.md)           — heading count, link count, code block count,
                                image count, table count
    Protobuf (.proto)        — message/service/enum/rpc counts, package declaration

Registered extensions:
    .yml, .yaml, .json, .toml, .tf, .tfvars,
    .sh, .bash, .zsh, .mk,
    .sql, .graphql, .gql, .md, .proto

Special filename matching:
    Dockerfile, Dockerfile.*, Makefile

Consumers: ParserRegistry → l2_quality, l2_structure
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
    ".yml": "yaml",
    ".yaml": "yaml",
    ".json": "json",
    ".toml": "toml",
    ".tf": "hcl",
    ".tfvars": "hcl",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".mk": "makefile",
    ".sql": "sql",
    ".graphql": "graphql",
    ".gql": "graphql",
    ".md": "markdown",
    ".proto": "protobuf",
}

# Filename-based detection (no extension)
_FILENAME_LANG: dict[str, str] = {
    "Makefile": "makefile",
    "Dockerfile": "dockerfile",
    "Jenkinsfile": "groovy",
    "Vagrantfile": "ruby",
}


# ═══════════════════════════════════════════════════════════════════
#  Shared helpers
# ═══════════════════════════════════════════════════════════════════


def _basic_line_metrics(
    lines: list[str], comment_prefix: str = "#",
) -> tuple[int, int, int, int]:
    """Return (total, code, blank, comment)."""
    total = len(lines)
    blank = 0
    comment = 0
    for line in lines:
        stripped = line.strip()
        if not stripped:
            blank += 1
        elif stripped.startswith(comment_prefix):
            comment += 1
    code = max(0, total - blank - comment)
    return total, code, blank, comment


def _c_style_line_metrics(source: str, lines: list[str]) -> tuple[int, int, int, int]:
    """Line metrics for C-style comment languages (JSON doesn't have comments)."""
    total = len(lines)
    blank = sum(1 for l in lines if not l.strip())
    # Block comments
    block_re = re.compile(r"/\*[\s\S]*?\*/")
    block_comments = block_re.findall(source)
    comment = sum(c.count("\n") + 1 for c in block_comments)
    # Line comments
    line_re = re.compile(r"^\s*//", re.MULTILINE)
    comment += len(line_re.findall(source))
    code = max(0, total - blank - comment)
    return total, code, blank, comment


# ═══════════════════════════════════════════════════════════════════
#  YAML analysis
# ═══════════════════════════════════════════════════════════════════

_RE_YAML_KEY = re.compile(r"^\s*([\w.-]+)\s*:", re.MULTILINE)
_RE_YAML_ANCHOR = re.compile(r"&\w+")
_RE_YAML_ALIAS = re.compile(r"\*\w+")
_RE_YAML_COMMENT = re.compile(r"^\s*#", re.MULTILINE)

# Purpose heuristics
_RE_YAML_K8S = re.compile(r"^\s*apiVersion\s*:", re.MULTILINE)
_RE_YAML_COMPOSE = re.compile(r"^\s*services\s*:", re.MULTILINE)
_RE_YAML_GHA = re.compile(r"^\s*(?:on|jobs)\s*:", re.MULTILINE)
_RE_YAML_HELM_VALUES = re.compile(r"^\s*(?:replicaCount|image|service)\s*:", re.MULTILINE)


def _analyze_yaml(
    source: str, lines: list[str], rel_path: str,
) -> tuple[list[ImportInfo], list[SymbolInfo], FileMetrics, dict]:
    keys = _RE_YAML_KEY.findall(source)
    anchors = _RE_YAML_ANCHOR.findall(source)
    aliases = _RE_YAML_ALIAS.findall(source)

    # Nesting depth (indentation-based)
    max_depth = 0
    for line in lines:
        stripped = line.lstrip()
        if stripped and not stripped.startswith("#"):
            indent = len(line) - len(stripped)
            depth = indent // 2  # YAML standard 2-space indent
            if depth > max_depth:
                max_depth = depth

    # Purpose detection
    purpose = "config"
    if _RE_YAML_K8S.search(source):
        purpose = "kubernetes"
    elif ".github/workflows" in rel_path:
        purpose = "github-actions"
    elif _RE_YAML_COMPOSE.search(source) and ("compose" in rel_path.lower() or "docker" in rel_path.lower()):
        purpose = "docker-compose"
    elif _RE_YAML_HELM_VALUES.search(source) and "values" in rel_path.lower():
        purpose = "helm-values"

    # GHA-specific metrics
    gha_steps = 0
    gha_actions: list[str] = []
    if purpose == "github-actions":
        step_re = re.compile(r"^\s*-\s+(?:name|uses)\s*:", re.MULTILINE)
        gha_steps = len(step_re.findall(source))
        uses_re = re.compile(r"uses\s*:\s*([^\s#]+)")
        gha_actions = uses_re.findall(source)

    total, code, blank, comment = _basic_line_metrics(lines)

    metrics = FileMetrics(
        total_lines=total, code_lines=code, blank_lines=blank,
        comment_lines=comment, max_nesting_depth=max_depth,
    )

    lang_metrics: dict = {
        "type": "yaml",
        "key_count": len(keys),
        "unique_keys": len(set(keys)),
        "max_nesting_depth": max_depth,
        "anchor_count": len(anchors),
        "alias_count": len(aliases),
        "purpose": purpose,
    }
    if purpose == "github-actions":
        lang_metrics["gha_step_count"] = gha_steps
        lang_metrics["gha_actions_used"] = sorted(set(gha_actions))

    return [], [], metrics, lang_metrics


# ═══════════════════════════════════════════════════════════════════
#  JSON analysis
# ═══════════════════════════════════════════════════════════════════

_RE_JSON_KEY = re.compile(r'"(\w[\w.-]*?)"\s*:')


def _analyze_json(
    source: str, lines: list[str],
) -> tuple[list[ImportInfo], list[SymbolInfo], FileMetrics, dict]:
    keys = _RE_JSON_KEY.findall(source)

    # Nesting depth
    max_depth = d = 0
    for ch in source:
        if ch in ("{", "["):
            d += 1
            if d > max_depth:
                max_depth = d
        elif ch in ("}", "]"):
            d = max(0, d - 1)

    # Array count
    array_count = source.count("[")

    total = len(lines)
    blank = sum(1 for l in lines if not l.strip())
    code = max(0, total - blank)

    metrics = FileMetrics(
        total_lines=total, code_lines=code, blank_lines=blank,
        comment_lines=0, max_nesting_depth=max_depth,
    )

    lang_metrics = {
        "type": "json",
        "key_count": len(keys),
        "unique_keys": len(set(keys)),
        "max_nesting_depth": max_depth,
        "array_count": array_count,
    }

    return [], [], metrics, lang_metrics


# ═══════════════════════════════════════════════════════════════════
#  TOML analysis
# ═══════════════════════════════════════════════════════════════════

_RE_TOML_SECTION = re.compile(r"^\s*\[+([^\]]+)\]+", re.MULTILINE)
_RE_TOML_KEY = re.compile(r"^\s*([\w.-]+)\s*=", re.MULTILINE)


def _analyze_toml(
    source: str, lines: list[str],
) -> tuple[list[ImportInfo], list[SymbolInfo], FileMetrics, dict]:
    sections = _RE_TOML_SECTION.findall(source)
    keys = _RE_TOML_KEY.findall(source)

    total, code, blank, comment = _basic_line_metrics(lines)

    metrics = FileMetrics(
        total_lines=total, code_lines=code, blank_lines=blank,
        comment_lines=comment,
    )

    lang_metrics = {
        "type": "toml",
        "section_count": len(sections),
        "key_count": len(keys),
        "sections": sorted(set(sections)),
    }

    return [], [], metrics, lang_metrics


# ═══════════════════════════════════════════════════════════════════
#  HCL/Terraform analysis
# ═══════════════════════════════════════════════════════════════════

_RE_HCL_RESOURCE = re.compile(r'^\s*resource\s+"(\w+)"\s+"(\w+)"', re.MULTILINE)
_RE_HCL_DATA = re.compile(r'^\s*data\s+"(\w+)"\s+"(\w+)"', re.MULTILINE)
_RE_HCL_VARIABLE = re.compile(r'^\s*variable\s+"(\w+)"', re.MULTILINE)
_RE_HCL_OUTPUT = re.compile(r'^\s*output\s+"(\w+)"', re.MULTILINE)
_RE_HCL_MODULE = re.compile(r'^\s*module\s+"(\w+)"', re.MULTILINE)
_RE_HCL_LOCALS = re.compile(r"^\s*locals\s*\{", re.MULTILINE)
_RE_HCL_PROVIDER = re.compile(r'^\s*provider\s+"(\w+)"', re.MULTILINE)


def _analyze_hcl(
    source: str, lines: list[str],
) -> tuple[list[ImportInfo], list[SymbolInfo], FileMetrics, dict]:
    resources = _RE_HCL_RESOURCE.findall(source)
    data_sources = _RE_HCL_DATA.findall(source)
    variables = _RE_HCL_VARIABLE.findall(source)
    outputs = _RE_HCL_OUTPUT.findall(source)
    modules = _RE_HCL_MODULE.findall(source)
    locals_count = len(_RE_HCL_LOCALS.findall(source))
    providers = _RE_HCL_PROVIDER.findall(source)

    symbols: list[SymbolInfo] = []
    for rtype, rname in resources:
        symbols.append(SymbolInfo(
            name=f"{rtype}.{rname}", kind="resource",
            lineno=0, end_lineno=0, is_public=True, visibility="public",
        ))
    for vname in variables:
        symbols.append(SymbolInfo(
            name=vname, kind="variable",
            lineno=0, end_lineno=0, is_public=True, visibility="public",
        ))
    for oname in outputs:
        symbols.append(SymbolInfo(
            name=oname, kind="output",
            lineno=0, end_lineno=0, is_public=True, visibility="public",
        ))

    total, code, blank, comment = _basic_line_metrics(lines)

    metrics = FileMetrics(
        total_lines=total, code_lines=code, blank_lines=blank,
        comment_lines=comment,
        function_count=0,
        class_count=len(resources) + len(data_sources),
    )

    lang_metrics = {
        "type": "hcl",
        "resource_count": len(resources),
        "resource_types": sorted(set(rt for rt, _ in resources)),
        "data_source_count": len(data_sources),
        "variable_count": len(variables),
        "output_count": len(outputs),
        "module_count": len(modules),
        "locals_count": locals_count,
        "provider_count": len(providers),
        "providers": sorted(set(providers)),
    }

    return [], symbols, metrics, lang_metrics


# ═══════════════════════════════════════════════════════════════════
#  Dockerfile analysis
# ═══════════════════════════════════════════════════════════════════

_RE_DOCKER_INSTRUCTION = re.compile(
    r"^\s*(FROM|RUN|CMD|LABEL|MAINTAINER|EXPOSE|ENV|ADD|COPY|"
    r"ENTRYPOINT|VOLUME|USER|WORKDIR|ARG|ONBUILD|STOPSIGNAL|"
    r"HEALTHCHECK|SHELL)\b",
    re.MULTILINE,
)
_RE_DOCKER_FROM = re.compile(r"^\s*FROM\s+(\S+)(?:\s+[Aa][Ss]\s+(\w+))?", re.MULTILINE)
_RE_DOCKER_RUN = re.compile(r"^\s*RUN\b", re.MULTILINE)
_RE_DOCKER_COPY = re.compile(r"^\s*(?:COPY|ADD)\b", re.MULTILINE)
_RE_DOCKER_EXPOSE = re.compile(r"^\s*EXPOSE\s+(.+)", re.MULTILINE)
_RE_DOCKER_ARG = re.compile(r"^\s*ARG\s+(\w+)", re.MULTILINE)
_RE_DOCKER_ENV = re.compile(r"^\s*ENV\s+(\w+)", re.MULTILINE)


def _analyze_dockerfile(
    source: str, lines: list[str],
) -> tuple[list[ImportInfo], list[SymbolInfo], FileMetrics, dict]:
    instructions = _RE_DOCKER_INSTRUCTION.findall(source)
    from_matches = _RE_DOCKER_FROM.findall(source)
    run_count = len(_RE_DOCKER_RUN.findall(source))
    copy_count = len(_RE_DOCKER_COPY.findall(source))
    expose_lines = _RE_DOCKER_EXPOSE.findall(source)
    arg_names = _RE_DOCKER_ARG.findall(source)
    env_names = _RE_DOCKER_ENV.findall(source)

    # Multi-stage detection
    stages = [name for _, name in from_matches if name]
    base_images = [img for img, _ in from_matches]
    is_multistage = len(from_matches) > 1

    total, code, blank, comment = _basic_line_metrics(lines)

    metrics = FileMetrics(
        total_lines=total, code_lines=code, blank_lines=blank,
        comment_lines=comment,
    )

    lang_metrics = {
        "type": "dockerfile",
        "instruction_count": len(instructions),
        "from_count": len(from_matches),
        "base_images": base_images,
        "run_count": run_count,
        "copy_count": copy_count,
        "expose_ports": [p.strip() for e in expose_lines for p in e.split()],
        "is_multistage": is_multistage,
        "stage_names": stages,
        "arg_count": len(arg_names),
        "env_count": len(env_names),
        "layer_count": run_count + copy_count,
    }

    return [], [], metrics, lang_metrics


# ═══════════════════════════════════════════════════════════════════
#  Makefile analysis
# ═══════════════════════════════════════════════════════════════════

_RE_MAKE_TARGET = re.compile(r"^([a-zA-Z_][\w.-]*)\s*:", re.MULTILINE)
_RE_MAKE_PHONY = re.compile(r"^\.PHONY\s*:\s*(.+)", re.MULTILINE)
_RE_MAKE_INCLUDE = re.compile(r"^-?include\s+(.+)", re.MULTILINE)
_RE_MAKE_VAR = re.compile(r"^([A-Z_][A-Z0-9_]*)\s*[:?+]?=", re.MULTILINE)


def _analyze_makefile(
    source: str, lines: list[str],
) -> tuple[list[ImportInfo], list[SymbolInfo], FileMetrics, dict]:
    targets = _RE_MAKE_TARGET.findall(source)
    phony_lines = _RE_MAKE_PHONY.findall(source)
    phonies = set()
    for line in phony_lines:
        phonies.update(t.strip() for t in line.split())
    includes = _RE_MAKE_INCLUDE.findall(source)
    variables = _RE_MAKE_VAR.findall(source)

    symbols = [
        SymbolInfo(
            name=t, kind="target",
            lineno=0, end_lineno=0, is_public=True, visibility="public",
        )
        for t in targets
    ]

    total, code, blank, comment = _basic_line_metrics(lines)

    metrics = FileMetrics(
        total_lines=total, code_lines=code, blank_lines=blank,
        comment_lines=comment, function_count=len(targets),
    )

    lang_metrics = {
        "type": "makefile",
        "target_count": len(targets),
        "phony_count": len(phonies),
        "include_count": len(includes),
        "variable_count": len(variables),
    }

    return [], symbols, metrics, lang_metrics


# ═══════════════════════════════════════════════════════════════════
#  Shell script analysis
# ═══════════════════════════════════════════════════════════════════

_RE_SHELL_SHEBANG = re.compile(r"^#!\s*(/\S+)")
_RE_SHELL_FUNC = re.compile(r"^\s*(?:function\s+)?(\w+)\s*\(\s*\)\s*\{", re.MULTILINE)
_RE_SHELL_SET_E = re.compile(r"^\s*set\s+-e\b", re.MULTILINE)
_RE_SHELL_PIPEFAIL = re.compile(r"^\s*set\s+-o\s+pipefail\b", re.MULTILINE)
_RE_SHELL_ERREXIT = re.compile(r"^\s*set\s+-[a-zA-Z]*e", re.MULTILINE)
_RE_SHELL_SOURCE = re.compile(r"^\s*(?:source|\\.)\s+(\S+)", re.MULTILINE)
_RE_SHELL_VAR = re.compile(r"^\s*(\w+)=", re.MULTILINE)
_RE_SHELL_TRAP = re.compile(r"^\s*trap\b", re.MULTILINE)


def _analyze_shell(
    source: str, lines: list[str],
) -> tuple[list[ImportInfo], list[SymbolInfo], FileMetrics, dict]:
    # Shebang
    shebang_match = _RE_SHELL_SHEBANG.search(source)
    shebang = shebang_match.group(1) if shebang_match else ""

    functions = _RE_SHELL_FUNC.findall(source)
    has_set_e = bool(_RE_SHELL_SET_E.search(source) or _RE_SHELL_ERREXIT.search(source))
    has_pipefail = bool(_RE_SHELL_PIPEFAIL.search(source))
    sources = _RE_SHELL_SOURCE.findall(source)
    variables = _RE_SHELL_VAR.findall(source)
    trap_count = len(_RE_SHELL_TRAP.findall(source))

    symbols = [
        SymbolInfo(
            name=f, kind="function",
            lineno=0, end_lineno=0, is_public=True, visibility="public",
        )
        for f in functions
    ]

    imports = [
        ImportInfo(
            module=s, names=[s.split("/")[-1]], is_from=False,
            lineno=0, is_stdlib=False, is_internal=True, is_relative=False,
        )
        for s in sources
    ]

    total, code, blank, comment = _basic_line_metrics(lines)

    metrics = FileMetrics(
        total_lines=total, code_lines=code, blank_lines=blank,
        comment_lines=comment, function_count=len(functions),
    )

    lang_metrics = {
        "type": "shell",
        "shebang": shebang,
        "function_count": len(functions),
        "has_set_e": has_set_e,
        "has_pipefail": has_pipefail,
        "has_error_handling": has_set_e or has_pipefail,
        "source_count": len(sources),
        "variable_count": len(variables),
        "trap_count": trap_count,
    }

    return imports, symbols, metrics, lang_metrics


# ═══════════════════════════════════════════════════════════════════
#  SQL analysis
# ═══════════════════════════════════════════════════════════════════

_RE_SQL_SELECT = re.compile(r"\bSELECT\b", re.IGNORECASE)
_RE_SQL_INSERT = re.compile(r"\bINSERT\s+INTO\b", re.IGNORECASE)
_RE_SQL_UPDATE = re.compile(r"\bUPDATE\b", re.IGNORECASE)
_RE_SQL_DELETE = re.compile(r"\bDELETE\s+FROM\b", re.IGNORECASE)
_RE_SQL_CREATE = re.compile(r"\bCREATE\s+(?:TABLE|VIEW|INDEX|FUNCTION|PROCEDURE|TRIGGER|TYPE|SCHEMA)\b", re.IGNORECASE)
_RE_SQL_ALTER = re.compile(r"\bALTER\s+(?:TABLE|VIEW|INDEX|FUNCTION)\b", re.IGNORECASE)
_RE_SQL_DROP = re.compile(r"\bDROP\s+(?:TABLE|VIEW|INDEX|FUNCTION|PROCEDURE|TRIGGER)\b", re.IGNORECASE)
_RE_SQL_TRANSACTION = re.compile(r"\b(?:BEGIN|COMMIT|ROLLBACK|SAVEPOINT)\b", re.IGNORECASE)
_RE_SQL_JOIN = re.compile(r"\b(?:INNER|LEFT|RIGHT|FULL|CROSS)?\s*JOIN\b", re.IGNORECASE)


def _analyze_sql(
    source: str, lines: list[str],
) -> tuple[list[ImportInfo], list[SymbolInfo], FileMetrics, dict]:
    total = len(lines)
    blank = sum(1 for l in lines if not l.strip())
    comment = sum(1 for l in lines if l.strip().startswith("--"))
    # Block comments
    block_re = re.compile(r"/\*[\s\S]*?\*/")
    blocks = block_re.findall(source)
    comment += sum(c.count("\n") + 1 for c in blocks)
    code = max(0, total - blank - comment)

    metrics = FileMetrics(
        total_lines=total, code_lines=code, blank_lines=blank,
        comment_lines=comment,
    )

    lang_metrics = {
        "type": "sql",
        "select_count": len(_RE_SQL_SELECT.findall(source)),
        "insert_count": len(_RE_SQL_INSERT.findall(source)),
        "update_count": len(_RE_SQL_UPDATE.findall(source)),
        "delete_count": len(_RE_SQL_DELETE.findall(source)),
        "create_count": len(_RE_SQL_CREATE.findall(source)),
        "alter_count": len(_RE_SQL_ALTER.findall(source)),
        "drop_count": len(_RE_SQL_DROP.findall(source)),
        "join_count": len(_RE_SQL_JOIN.findall(source)),
        "transaction_count": len(_RE_SQL_TRANSACTION.findall(source)),
    }

    return [], [], metrics, lang_metrics


# ═══════════════════════════════════════════════════════════════════
#  GraphQL analysis
# ═══════════════════════════════════════════════════════════════════

_RE_GQL_QUERY = re.compile(r"^\s*(?:query)\s+(\w+)", re.MULTILINE)
_RE_GQL_MUTATION = re.compile(r"^\s*(?:mutation)\s+(\w+)", re.MULTILINE)
_RE_GQL_SUBSCRIPTION = re.compile(r"^\s*(?:subscription)\s+(\w+)", re.MULTILINE)
_RE_GQL_TYPE = re.compile(r"^\s*type\s+(\w+)", re.MULTILINE)
_RE_GQL_INPUT = re.compile(r"^\s*input\s+(\w+)", re.MULTILINE)
_RE_GQL_ENUM = re.compile(r"^\s*enum\s+(\w+)", re.MULTILINE)
_RE_GQL_INTERFACE = re.compile(r"^\s*interface\s+(\w+)", re.MULTILINE)
_RE_GQL_SCALAR = re.compile(r"^\s*scalar\s+(\w+)", re.MULTILINE)
_RE_GQL_FRAGMENT = re.compile(r"^\s*fragment\s+(\w+)", re.MULTILINE)
_RE_GQL_DIRECTIVE = re.compile(r"^\s*directive\s+@(\w+)", re.MULTILINE)


def _analyze_graphql(
    source: str, lines: list[str],
) -> tuple[list[ImportInfo], list[SymbolInfo], FileMetrics, dict]:
    queries = _RE_GQL_QUERY.findall(source)
    mutations = _RE_GQL_MUTATION.findall(source)
    subscriptions = _RE_GQL_SUBSCRIPTION.findall(source)
    types = _RE_GQL_TYPE.findall(source)
    inputs = _RE_GQL_INPUT.findall(source)
    enums = _RE_GQL_ENUM.findall(source)
    interfaces = _RE_GQL_INTERFACE.findall(source)
    fragments = _RE_GQL_FRAGMENT.findall(source)

    symbols = []
    for name in types:
        symbols.append(SymbolInfo(
            name=name, kind="type", lineno=0, end_lineno=0,
            is_public=True, visibility="public",
        ))
    for name in queries:
        symbols.append(SymbolInfo(
            name=name, kind="query", lineno=0, end_lineno=0,
            is_public=True, visibility="public",
        ))
    for name in mutations:
        symbols.append(SymbolInfo(
            name=name, kind="mutation", lineno=0, end_lineno=0,
            is_public=True, visibility="public",
        ))

    total, code, blank, comment = _basic_line_metrics(lines)

    metrics = FileMetrics(
        total_lines=total, code_lines=code, blank_lines=blank,
        comment_lines=comment,
        class_count=len(types) + len(inputs) + len(enums),
        function_count=len(queries) + len(mutations) + len(subscriptions),
    )

    lang_metrics = {
        "type": "graphql",
        "query_count": len(queries),
        "mutation_count": len(mutations),
        "subscription_count": len(subscriptions),
        "type_count": len(types),
        "input_count": len(inputs),
        "enum_count": len(enums),
        "interface_count": len(interfaces),
        "fragment_count": len(fragments),
    }

    return [], symbols, metrics, lang_metrics


# ═══════════════════════════════════════════════════════════════════
#  Markdown analysis
# ═══════════════════════════════════════════════════════════════════

_RE_MD_HEADING = re.compile(r"^(#{1,6})\s+(.+)", re.MULTILINE)
_RE_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]+\)")
_RE_MD_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]+\)")
_RE_MD_CODE_BLOCK = re.compile(r"^```", re.MULTILINE)
_RE_MD_TABLE_ROW = re.compile(r"^\s*\|.+\|", re.MULTILINE)
_RE_MD_TODO = re.compile(r"^\s*-\s*\[[ x]\]", re.MULTILINE)


def _analyze_markdown(
    source: str, lines: list[str],
) -> tuple[list[ImportInfo], list[SymbolInfo], FileMetrics, dict]:
    headings = _RE_MD_HEADING.findall(source)
    links = _RE_MD_LINK.findall(source)
    images = _RE_MD_IMAGE.findall(source)
    code_fences = _RE_MD_CODE_BLOCK.findall(source)
    table_rows = _RE_MD_TABLE_ROW.findall(source)
    todos = _RE_MD_TODO.findall(source)

    # Heading hierarchy
    h_levels = {}
    for hashes, _ in headings:
        level = len(hashes)
        h_levels[f"h{level}"] = h_levels.get(f"h{level}", 0) + 1

    total = len(lines)
    blank = sum(1 for l in lines if not l.strip())
    code = max(0, total - blank)

    metrics = FileMetrics(
        total_lines=total, code_lines=code, blank_lines=blank,
        comment_lines=0,
    )

    lang_metrics = {
        "type": "markdown",
        "heading_count": len(headings),
        "heading_levels": h_levels,
        "link_count": len(links),
        "image_count": len(images),
        "code_block_count": len(code_fences) // 2,  # pairs of ```
        "table_row_count": len(table_rows),
        "todo_count": len(todos),
    }

    return [], [], metrics, lang_metrics


# ═══════════════════════════════════════════════════════════════════
#  Protobuf analysis
# ═══════════════════════════════════════════════════════════════════

_RE_PROTO_PACKAGE = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.MULTILINE)
_RE_PROTO_IMPORT = re.compile(r'^\s*import\s+"([^"]+)"\s*;', re.MULTILINE)
_RE_PROTO_MESSAGE = re.compile(r"^\s*message\s+(\w+)", re.MULTILINE)
_RE_PROTO_SERVICE = re.compile(r"^\s*service\s+(\w+)", re.MULTILINE)
_RE_PROTO_ENUM = re.compile(r"^\s*enum\s+(\w+)", re.MULTILINE)
_RE_PROTO_RPC = re.compile(r"^\s*rpc\s+(\w+)", re.MULTILINE)
_RE_PROTO_SYNTAX = re.compile(r'^\s*syntax\s*=\s*"(proto[23])"\s*;', re.MULTILINE)


def _analyze_protobuf(
    source: str, lines: list[str],
) -> tuple[list[ImportInfo], list[SymbolInfo], FileMetrics, dict]:
    pkg = _RE_PROTO_PACKAGE.search(source)
    proto_imports = _RE_PROTO_IMPORT.findall(source)
    messages = _RE_PROTO_MESSAGE.findall(source)
    services = _RE_PROTO_SERVICE.findall(source)
    enums = _RE_PROTO_ENUM.findall(source)
    rpcs = _RE_PROTO_RPC.findall(source)
    syntax = _RE_PROTO_SYNTAX.search(source)

    imports = [
        ImportInfo(
            module=p, names=[p.split("/")[-1].replace(".proto", "")],
            is_from=False, lineno=0,
            is_stdlib=p.startswith("google/"),
            is_internal=not p.startswith("google/"),
            is_relative=False,
        )
        for p in proto_imports
    ]

    symbols = []
    for name in messages:
        symbols.append(SymbolInfo(
            name=name, kind="message", lineno=0, end_lineno=0,
            is_public=True, visibility="public",
        ))
    for name in services:
        symbols.append(SymbolInfo(
            name=name, kind="service", lineno=0, end_lineno=0,
            is_public=True, visibility="public",
        ))

    total = len(lines)
    blank = sum(1 for l in lines if not l.strip())
    comment = sum(1 for l in lines if l.strip().startswith("//"))
    code = max(0, total - blank - comment)

    metrics = FileMetrics(
        total_lines=total, code_lines=code, blank_lines=blank,
        comment_lines=comment,
        class_count=len(messages) + len(services),
        function_count=len(rpcs),
    )

    lang_metrics = {
        "type": "protobuf",
        "syntax": syntax.group(1) if syntax else "unknown",
        "package": pkg.group(1) if pkg else "",
        "message_count": len(messages),
        "service_count": len(services),
        "enum_count": len(enums),
        "rpc_count": len(rpcs),
    }

    return imports, symbols, metrics, lang_metrics


# ═══════════════════════════════════════════════════════════════════
#  Dispatcher
# ═══════════════════════════════════════════════════════════════════

_ANALYZERS = {
    "yaml": "yaml",
    "json": "json",
    "toml": "toml",
    "hcl": "hcl",
    "dockerfile": "dockerfile",
    "makefile": "makefile",
    "shell": "shell",
    "sql": "sql",
    "graphql": "graphql",
    "markdown": "markdown",
    "protobuf": "protobuf",
}


def _dispatch(
    lang: str, source: str, lines: list[str], rel_path: str,
) -> tuple[list[ImportInfo], list[SymbolInfo], FileMetrics, dict]:
    if lang == "yaml":
        return _analyze_yaml(source, lines, rel_path)
    elif lang == "json":
        return _analyze_json(source, lines)
    elif lang == "toml":
        return _analyze_toml(source, lines)
    elif lang == "hcl":
        return _analyze_hcl(source, lines)
    elif lang == "dockerfile":
        return _analyze_dockerfile(source, lines)
    elif lang == "makefile":
        return _analyze_makefile(source, lines)
    elif lang == "shell":
        return _analyze_shell(source, lines)
    elif lang == "sql":
        return _analyze_sql(source, lines)
    elif lang == "graphql":
        return _analyze_graphql(source, lines)
    elif lang == "markdown":
        return _analyze_markdown(source, lines)
    elif lang == "protobuf":
        return _analyze_protobuf(source, lines)
    else:
        # Shouldn't reach here, but provide basic metrics
        total, code, blank, comment = _basic_line_metrics(lines)
        metrics = FileMetrics(
            total_lines=total, code_lines=code,
            blank_lines=blank, comment_lines=comment,
        )
        return [], [], metrics, {"type": lang}


# ═══════════════════════════════════════════════════════════════════
#  Parser implementation
# ═══════════════════════════════════════════════════════════════════


class ConfigParser(BaseParser):
    """Parser for configuration, infrastructure, scripting, and doc files."""

    @property
    def language(self) -> str:
        return "config"

    def extensions(self) -> set[str]:
        return set(_EXT_LANG.keys())

    def parse_file(
        self,
        file_path: Path,
        project_root: Path | None = None,
        project_prefix: str = "src",
    ) -> FileAnalysis:
        rel_path = (
            str(file_path.relative_to(project_root))
            if project_root
            else str(file_path)
        )

        # Determine language from extension or filename
        ext = file_path.suffix.lower()
        lang = _EXT_LANG.get(ext)

        if lang is None:
            # Check filename-based detection
            name = file_path.name
            for prefix, flang in _FILENAME_LANG.items():
                if name == prefix or name.startswith(prefix + "."):
                    lang = flang
                    break

        if lang is None:
            lang = "config"

        # Determine file_type
        file_type = "config"
        if lang in ("shell", "makefile"):
            file_type = "script"
        elif lang == "markdown":
            file_type = "documentation"
        elif lang in ("hcl", "dockerfile"):
            file_type = "infrastructure"
        elif lang in ("sql", "graphql", "protobuf"):
            file_type = "schema"

        try:
            source = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return FileAnalysis(
                path=rel_path, language=lang, file_type=file_type,
                parse_error=str(exc),
            )

        lines = source.splitlines()
        imports, symbols, metrics, lang_metrics = _dispatch(
            lang, source, lines, rel_path,
        )

        return FileAnalysis(
            path=rel_path,
            language=lang,
            file_type=file_type,
            imports=imports,
            symbols=symbols,
            metrics=metrics,
            language_metrics=lang_metrics,
        )


# ═══════════════════════════════════════════════════════════════════
#  Registry self-registration
# ═══════════════════════════════════════════════════════════════════

_config_parser = ConfigParser()


def _register():
    """Register ConfigParser for all config/infra extensions."""
    from src.core.services.audit.parsers import registry
    registry.register(_config_parser)


_register()
