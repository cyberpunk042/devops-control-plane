# Class Diagram — core

> Generated: 2026-03-08 01:54 UTC

## Table of Contents

- [Statistics](#statistics)
- [Diagram](#diagram)
- [Class Index](#class-index)
- [Relationships](#relationships)

## Statistics

| Metric | Value |
|--------|-------|
| Files analyzed | 659 |
| Files with errors | 0 |
| Total classes | 179 |
| Nodes in graph | 168 |
| Relationships | 135 |
| ↳ aggregates | 40 |
| ↳ associates | 10 |
| ↳ composes | 18 |
| ↳ depends | 21 |
| ↳ inherits | 46 |
| Connected components | 53 |
| Orphan classes | 32 |
| Packages | 76 |

## Diagram

```mermaid
classDiagram
    direction TD

    namespace src_core_data_script_templates_lib_code_analyzer {
        class src_core_data_script_templates_lib_code_analyzer_ClassInfo {
            <<dataclass>>
            + name: str
            + qualified_name: str
            + file_path: str
            + module: str
            + bases: list[str]
            + fields: list[FieldInfo]
            + methods: list[MethodInfo]
            + is_abstract: bool
            + is_dataclass: bool
            + is_pydantic: bool
            ... 5 more fields
        }
        class src_core_data_script_templates_lib_code_analyzer_FieldInfo {
            <<dataclass>>
            + name: str
            + type_annotation: str
            + is_class_var: bool
            + visibility: str
        }
        class src_core_data_script_templates_lib_code_analyzer_MethodInfo {
            <<dataclass>>
            + name: str
            + is_async: bool
            + is_static: bool
            + is_classmethod: bool
            + is_property: bool
            + is_abstract: bool
            + visibility: str
            + parameters: list[str]
            + return_type: str
            + decorators: list[str]
        }
        class src_core_data_script_templates_lib_code_analyzer_ProjectAnalysis {
            <<dataclass>>
            + classes: list[ClassInfo]
            + files_analyzed: int
            + files_with_errors: int
            + total_classes: int
            + analysis_errors: list[str]
        }
    }

    namespace src_core_data_script_templates_lib_graph_builder {
        class src_core_data_script_templates_lib_graph_builder_ClassGraph {
            <<dataclass>>
            + nodes: dict[str, GraphNode]
            + edges: list[GraphEdge]
            + title: str
            + scope: str
            + add_node(node) None
            + add_edge(edge) None
            + filter_by_package(package) ClassGraph
            + get_connected_components() list[list[str]]
            + get_orphan_nodes() list[str]
        }
        class src_core_data_script_templates_lib_graph_builder_GraphEdge {
            <<dataclass>>
            + source: str
            + target: str
            + relation: RelationType
            + label: str
            + cardinality: str
        }
        class src_core_data_script_templates_lib_graph_builder_GraphNode {
            <<dataclass>>
            + id: str
            + label: str
            + kind: str
            + package: str
            + fields: list[str]
            + methods: list[str]
            + metadata: dict
        }
        class src_core_data_script_templates_lib_graph_builder_RelationType {
        }
    }

    namespace src_core_engine_executor {
        class src_core_engine_executor_ExecutionPlan {
            <<dataclass>>
            + operation_id: str
            + automation: str
            + actions: list[Action]
            + module_actions: dict[str, list[Action]]
            + total_actions() int
        }
        class src_core_engine_executor_ExecutionReport {
            <<dataclass>>
            + operation_id: str
            + automation: str
            + receipts: list[Receipt]
            + module_receipts: dict[str, list[Receipt]]
            + total() int
            + succeeded() int
            + failed() int
            + skipped() int
            + all_ok() bool
            + status() str
            + to_dict() dict
        }
    }

    namespace src_core_models_action {
        class src_core_models_action_Action {
            + id: str
            + name: str
            + adapter: str
            + capability: str
            + params: dict[str, Any]
            + for_module: str | None
        }
        class src_core_models_action_Receipt {
            + adapter: str
            + action_id: str
            + status: Literal['ok', 'skipped', 'failed']
            + started_at: str
            + ended_at: str
            + duration_ms: int
            + output: str
            + error: str | None
            + delivery_id: str | None
            + metadata: dict[str, Any]
            + ok() bool
            + failed() bool
            + success(adapter, action_id, output) Receipt
            + failure(adapter, action_id, error) Receipt
            + skip(adapter, action_id, reason) Receipt
        }
    }

    namespace src_core_models_module {
        class src_core_models_module_Module {
            + name: str
            + path: str
            + domain: str
            + stack_name: str
            + description: str
            + detected: bool
            + detected_stack: str
            + version: str | None
            + language: str | None
            + dependencies: list[str]
            ... 1 more fields
            + effective_stack() str
            + is_detected() bool
        }
        class src_core_models_module_ModuleHealth {
            + status: str
            + message: str
            + last_checked_at: str | None
        }
    }

    namespace src_core_models_project {
        class src_core_models_project_Environment {
            + name: str
            + description: str
            + default: bool
        }
        class src_core_models_project_ExternalLinks {
            + ci: str | None
            + registry: str | None
            + monitoring: str | None
            + extra: dict[str, str]
        }
        class src_core_models_project_ModuleRef {
            + name: str
            + path: str
            + domain: str
            + stack: str
            + description: str
        }
        class src_core_models_project_Project {
            + version: int
            + name: str
            + description: str
            + repository: str
            + domains: list[str]
            + environments: list[Environment]
            + modules: list[ModuleRef]
            + external: ExternalLinks
            + get_environment(name) Environment | None
            + default_environment() Environment | None
            + get_module(name) ModuleRef | None
            + modules_by_domain(domain) list[ModuleRef]
        }
    }

    namespace src_core_models_stack {
        class src_core_models_stack_AdapterRequirement {
            + adapter: str
            + min_version: str
        }
        class src_core_models_stack_DetectionRule {
            + files_any_of: list[str]
            + files_all_of: list[str]
            + content_contains: dict[str, str]
        }
        class src_core_models_stack_Stack {
            + name: str
            + description: str
            + detail: str
            + domain: str
            + icon: str
            + parent: str
            + requires: list[AdapterRequirement]
            + detection: DetectionRule
            + capabilities: list[StackCapability]
            + has_capability(name) bool
            + get_capability(name) StackCapability | None
            + capability_names() list[str]
        }
        class src_core_models_stack_StackCapability {
            + name: str
            + adapter: str
            + command: str
            + description: str
        }
    }

    namespace src_core_models_state {
        class src_core_models_state_AdapterState {
            + name: str
            + available: bool
            + version: str | None
            + last_used_at: str | None
            + failure_count: int
            + circuit_state: str
        }
        class src_core_models_state_ModuleState {
            + name: str
            + detected: bool
            + stack: str
            + version: str | None
            + last_action_at: str | None
            + last_action_status: str | None
        }
        class src_core_models_state_OperationRecord {
            + operation_id: str
            + automation: str
            + started_at: str
            + ended_at: str
            + status: str
            + actions_total: int
            + actions_succeeded: int
            + actions_failed: int
        }
        class src_core_models_state_ProjectState {
            + schema_version: int
            + project_name: str
            + current_environment: str
            + created_at: str
            + updated_at: str
            + last_detection_at: str | None
            + modules: dict[str, ModuleState]
            + adapters: dict[str, AdapterState]
            + last_operation: OperationRecord
            + metadata: dict[str, Any]
            + touch() None
            + set_module_state(name) None
            + set_adapter_state(name) None
        }
    }

    namespace src_core_observability_health {
        class src_core_observability_health_ComponentHealth {
            <<dataclass>>
            + name: str
            + status: str
            + message: str
            + details: dict[str, Any]
            + to_dict() dict[str, Any]
        }
        class src_core_observability_health_SystemHealth {
            <<dataclass>>
            + status: str
            + timestamp: str
            + components: list[ComponentHealth]
            # __post_init__() None
            + add(component) None
            # _recalculate() None
            + to_dict() dict[str, Any]
        }
    }

    namespace src_core_observability_metrics {
        class src_core_observability_metrics_Counter {
            <<dataclass>>
            + name: str
            + value: int
            + labels: dict[str, str]
            + inc(n) None
            + to_dict() dict[str, Any]
        }
        class src_core_observability_metrics_Gauge {
            <<dataclass>>
            + name: str
            + value: float
            + labels: dict[str, str]
            + set(v) None
            + inc(n) None
            + dec(n) None
            + to_dict() dict[str, Any]
        }
        class src_core_observability_metrics_Histogram {
            <<dataclass>>
            + name: str
            # _values: list[float]
            + labels: dict[str, str]
            + observe(value) None
            + count() int
            + total() float
            + mean() float
            + min() float
            + max() float
            + p95() float
            + to_dict() dict[str, Any]
        }
        class src_core_observability_metrics_MetricsRegistry {
            # _counters: dict[str, Counter]
            # _gauges: dict[str, Gauge]
            # _histograms: dict[str, Histogram]
            # __init__() None
            + counter(name) Counter
            + gauge(name) Gauge
            + histogram(name) Histogram
            + timer(name) TimerContext
            + to_dict() dict[str, list[dict]]
            + reset() None
        }
        class src_core_observability_metrics_TimerContext {
            # _histogram: Any
            # _start: float
            # __init__(histogram)
            # __enter__() TimerContext
            # __exit__() None
        }
    }

    namespace src_core_reliability_circuit_breaker {
        class src_core_reliability_circuit_breaker_CircuitBreaker {
            <<dataclass>>
            + name: str
            + failure_threshold: int
            + recovery_timeout: float
            + success_threshold: int
            + state: CircuitState
            + failure_count: int
            + success_count: int
            + last_failure_time: float
            + last_state_change: float
            + total_rejections: int
            + allow_request() bool
            + record_success() None
            + record_failure() None
            + reset() None
            + to_dict() dict[str, Any]
            # _transition(new_state) None
        }
        class src_core_reliability_circuit_breaker_CircuitBreakerRegistry {
            <<dataclass>>
            + breakers: dict[str, CircuitBreaker]
            + default_threshold: int
            + default_timeout: float
            + get_or_create(name) CircuitBreaker
            + get_status() dict[str, dict[str, Any]]
            + reset_all() None
        }
        class src_core_reliability_circuit_breaker_CircuitState {
        }
    }

    namespace src_core_reliability_retry_queue {
        class src_core_reliability_retry_queue_RetryItem {
            <<dataclass>>
            + id: str
            + action_id: str
            + adapter: str
            + params: dict[str, Any]
            + attempt: int
            + max_attempts: int
            + next_retry_at: float
            + created_at: float
            + last_error: str
            + exhausted() bool
            + ready() bool
            + schedule_retry(base_delay, max_delay) None
            + to_dict() dict[str, Any]
            + from_dict(data) RetryItem
        }
        class src_core_reliability_retry_queue_RetryQueue {
            # _path: Any
            # _items: dict[str, RetryItem]
            # _max_attempts: Any
            # _base_delay: Any
            # _max_delay: Any
            # __init__(path, max_attempts, base_delay, max_delay)
            + size() int
            + ready_count() int
            + enqueue(item_id, action_id, adapter, error, params) RetryItem
            + dequeue_ready() list[RetryItem]
            + complete(item_id) None
            + fail(item_id, error) RetryItem | None
            + remove_exhausted() list[RetryItem]
            + clear() None
            + get_status() dict[str, Any]
            # _save() None
            # _load() None
        }
    }

    namespace src_core_services_artifacts_builders_base {
        class src_core_services_artifacts_builders_base_ArtifactBuilder {
            <<abstract>>
            + name() str
            + label() str
            + stages(target) list[ArtifactStageInfo]
            + build(target, project_root) Generator[dict, None, ArtifactBuildResult]
        }
    }

    namespace src_core_services_artifacts_builders_cargo {
        class src_core_services_artifacts_builders_cargo_CargoBuilder {
            + name() str
            + label() str
            + stages(target) list[ArtifactStageInfo]
            + build(target, project_root) Generator[dict, None, ArtifactBuildResult]
        }
    }

    namespace src_core_services_artifacts_builders_docker {
        class src_core_services_artifacts_builders_docker_DockerBuilder {
            + name() str
            + label() str
            + stages(target) list[ArtifactStageInfo]
            # _detect_engine() str | None
            # _resolve_tag(target, project_root) str
            + build(target, project_root) Generator[dict, None, ArtifactBuildResult]
        }
    }

    namespace src_core_services_artifacts_builders_dotnet {
        class src_core_services_artifacts_builders_dotnet_DotnetBuilder {
            + name() str
            + label() str
            + stages(target) list[ArtifactStageInfo]
            + build(target, project_root) Generator[dict, None, ArtifactBuildResult]
        }
    }

    namespace src_core_services_artifacts_builders_gem {
        class src_core_services_artifacts_builders_gem_GemBuilder {
            + name() str
            + label() str
            + stages(target) list[ArtifactStageInfo]
            + build(target, project_root) Generator[dict, None, ArtifactBuildResult]
        }
    }

    namespace src_core_services_artifacts_builders_go {
        class src_core_services_artifacts_builders_go_GoBuilder {
            + name() str
            + label() str
            + stages(target) list[ArtifactStageInfo]
            + build(target, project_root) Generator[dict, None, ArtifactBuildResult]
        }
    }

    namespace src_core_services_artifacts_builders_gradle {
        class src_core_services_artifacts_builders_gradle_GradleBuilder {
            + name() str
            + label() str
            + stages(target) list[ArtifactStageInfo]
            # _find_gradle(project_root) str | None
            + build(target, project_root) Generator[dict, None, ArtifactBuildResult]
        }
    }

    namespace src_core_services_artifacts_builders_makefile {
        class src_core_services_artifacts_builders_makefile_MakefileBuilder {
            + name() str
            + label() str
            + stages(target) list[ArtifactStageInfo]
            # _parse_makefile_targets(project_root) dict[str, dict]
            # _detect_stages(target, project_root) list[ArtifactStageInfo]
            + build(target, project_root) Generator[dict, None, ArtifactBuildResult]
            # _run_make_stage(make_target, stage_info, project_root, env) Generator[dict, None, tuple[bool, int]]
        }
    }

    namespace src_core_services_artifacts_builders_maven {
        class src_core_services_artifacts_builders_maven_MavenBuilder {
            + name() str
            + label() str
            + stages(target) list[ArtifactStageInfo]
            + build(target, project_root) Generator[dict, None, ArtifactBuildResult]
        }
    }

    namespace src_core_services_artifacts_builders_mix {
        class src_core_services_artifacts_builders_mix_MixBuilder {
            + name() str
            + label() str
            + stages(target) list[ArtifactStageInfo]
            + build(target, project_root) Generator[dict, None, ArtifactBuildResult]
        }
    }

    namespace src_core_services_artifacts_builders_npm {
        class src_core_services_artifacts_builders_npm_NpmBuilder {
            + name() str
            + label() str
            + stages(target) list[ArtifactStageInfo]
            + build(target, project_root) Generator[dict, None, ArtifactBuildResult]
        }
    }

    namespace src_core_services_artifacts_builders_pip_builder {
        class src_core_services_artifacts_builders_pip_builder_PipBuilder {
            + name() str
            + label() str
            + stages(target) list[ArtifactStageInfo]
            # _detect_version(project_root) str
            # _find_python(project_root) str
            + build(target, project_root) Generator[dict, None, ArtifactBuildResult]
        }
    }

    namespace src_core_services_artifacts_builders_script {
        class src_core_services_artifacts_builders_script_ScriptBuilder {
            + name() str
            + label() str
            + stages(target) list[ArtifactStageInfo]
            + build(target, project_root) Generator[dict, None, ArtifactBuildResult]
        }
    }

    namespace src_core_services_artifacts_publishers_base {
        class src_core_services_artifacts_publishers_base_ArtifactPublisher {
            <<abstract>>
            + name() str
            + label() str
            + publish(target, project_root, version, files) Generator[dict, None, ArtifactPublishResult]
        }
    }

    namespace src_core_services_artifacts_publishers_github_release {
        class src_core_services_artifacts_publishers_github_release_GitHubReleasePublisher {
            + name() str
            + label() str
            + publish(target, project_root, version, files) Generator[dict, None, ArtifactPublishResult]
        }
    }

    namespace src_core_services_artifacts_publishers_npm_publisher {
        class src_core_services_artifacts_publishers_npm_publisher_NpmPublisher {
            + name() str
            + label() str
            + publish(target, project_root, version, files) Generator[dict, None, ArtifactPublishResult]
        }
    }

    namespace src_core_services_artifacts_publishers_pypi {
        class src_core_services_artifacts_publishers_pypi_PyPIPublisher {
            # _test: Any
            # __init__(test)
            + name() str
            + label() str
            + publish(target, project_root, version, files) Generator[dict, None, ArtifactPublishResult]
        }
    }

    namespace src_core_services_audit_models {
        class src_core_services_audit_models_AuditMeta {
            + layer: str
            + dimension: str
            + computed_at: float
            + duration_ms: int
            + scope: str
        }
        class src_core_services_audit_models_AuditScores {
            # _meta: AuditMeta
            + complexity: ScoreResult
            + quality: ScoreResult
        }
        class src_core_services_audit_models_ClientInfo {
            + name: str
            + type: str
            + ecosystem: str
            + description: str
            + library: str
            + service: str
        }
        class src_core_services_audit_models_ComponentInfo {
            + type: str
            + name: str
            + technologies: list[str]
            + path: str
        }
        class src_core_services_audit_models_CrossoverInfo {
            + service_type: str
            + service: str
            + libraries: list[dict]
            + ecosystems: list[str]
        }
        class src_core_services_audit_models_DependencyInfo {
            + name: str
            + version: str
            + dev: bool
            + ecosystem: str
            + source_file: str
            + classification: dict | None
        }
        class src_core_services_audit_models_EntrypointInfo {
            + type: str
            + path: str
            + description: str
        }
        class src_core_services_audit_models_L0Result {
            # _meta: AuditMeta
            + os: OSInfo
            + runtime: RuntimeInfo
            + tools: list[ToolInfo]
            + modules: list[ModuleInfo]
            + manifests: list[ManifestInfo]
            + project_root: str
        }
        class src_core_services_audit_models_L1ClientsResult {
            # _meta: AuditMeta
            + clients: list[ClientInfo]
            + total: int
            + by_type: dict[str, int]
            + by_ecosystem: dict[str, int]
            + by_service: dict[str, list[dict]]
        }
        class src_core_services_audit_models_L1DepsResult {
            # _meta: AuditMeta
            + dependencies: list[DependencyInfo]
            + total: int
            + total_prod: int
            + total_dev: int
            + categories: dict[str, int]
            + frameworks: list[dict]
            + orms: list[dict]
            + crossovers: list[CrossoverInfo]
            + ecosystems: dict[str, int]
        }
        class src_core_services_audit_models_L1StructResult {
            # _meta: AuditMeta
            + solution_type: str
            + components: list[ComponentInfo]
            + has_cli: bool
            + has_web: bool
            + has_docs: bool
            + has_tests: bool
            + has_iac: bool
            + has_ci: bool
            + has_docker: bool
            ... 1 more fields
        }
        class src_core_services_audit_models_ManifestInfo {
            + file: str
            + ecosystem: str
            + manager: str
            + size: int
        }
        class src_core_services_audit_models_ModuleInfo {
            + name: str
            + path: str
            + domain: str
            + stack: str
            + language: str
            + version: str
            + detected: bool
            + description: str
            + file_count: int
        }
        class src_core_services_audit_models_OSInfo {
            + system: str
            + release: str
            + machine: str
            + wsl: bool
            + distro: str
        }
        class src_core_services_audit_models_RuntimeInfo {
            + version: str
            + version_tuple: list[int]
            + implementation: str
            + executable: str
            + prefix: str
            + base_prefix: str
            + env_type: str
            + in_managed_env: bool
            + pep668: bool
            + env_managers: dict[str, bool]
            ... 3 more fields
        }
        class src_core_services_audit_models_ScoreBreakdownItem {
            + score: float
            + weight: float
            + detail: str
        }
        class src_core_services_audit_models_ScoreResult {
            + score: float
            + breakdown: dict[str, ScoreBreakdownItem]
        }
        class src_core_services_audit_models_ToolInfo {
            + id: str
            + cli: str
            + label: str
            + available: bool
            + path: str | None
        }
    }

    namespace src_core_services_audit_parsers {
        class src_core_services_audit_parsers_ParserRegistry {
            # _parsers: dict[str, BaseParser]
            # _fallback: BaseParser | None
            # _languages: dict[str, BaseParser]
            # _file_cache: dict[str, tuple[float, FileAnalysis]]
            # __init__() None
            + register(parser) None
            + set_fallback(parser) None
            + get_parser(path) BaseParser | None
            + get_parser_for_language(language) BaseParser | None
            + registered_extensions() set[str]
            + registered_languages() list[str]
            + has_fallback() bool
            + parse_file(path, project_root, project_prefix) FileAnalysis | None
            + parse_tree(project_root) dict[str, FileAnalysis]
            + bust_cache() int
            # __repr__() str
        }
    }

    namespace src_core_services_audit_parsers__base {
        class src_core_services_audit_parsers__base_BaseParser {
            <<abstract>>
            + language() str
            + extensions() set[str]
            + parse_file(path, project_root, project_prefix) FileAnalysis
            + file_type() str
        }
        class src_core_services_audit_parsers__base_FileAnalysis {
            <<dataclass>>
            + path: str
            + language: str
            + file_type: str
            + template_engine: str | None
            + imports: list[ImportInfo]
            + symbols: list[SymbolInfo]
            + metrics: FileMetrics
            + parse_error: str | None
            + language_metrics: dict
            + symbol_locations: list[SymbolLocation]
            + to_dict() dict
        }
        class src_core_services_audit_parsers__base_FileMetrics {
            <<dataclass>>
            + total_lines: int
            + code_lines: int
            + blank_lines: int
            + comment_lines: int
            + docstring_lines: int
            + avg_function_length: float
            + max_function_length: int
            + max_nesting_depth: int
            + import_count: int
            + function_count: int
            ... 3 more fields
        }
        class src_core_services_audit_parsers__base_ImportInfo {
            <<dataclass>>
            + module: str
            + names: list[str]
            + alias: str | None
            + is_from: bool
            + lineno: int
            + is_internal: bool
            + is_stdlib: bool
            + is_relative: bool
            + top_level() str
        }
        class src_core_services_audit_parsers__base_SymbolInfo {
            <<dataclass>>
            + name: str
            + kind: str
            + lineno: int
            + end_lineno: int
            + decorators: list[str]
            + is_public: bool
            + visibility: str
            + has_docstring: bool
            + num_args: int
            + body_lines: int
            ... 2 more fields
            + length() int
        }
        class src_core_services_audit_parsers__base_SymbolLocation {
            <<dataclass>>
            + symbol: str
            + kind: str
            + file: str
            + line_start: int
            + line_end: int
            + preview: str
        }
    }

    namespace src_core_services_audit_parsers__fallback {
        class src_core_services_audit_parsers__fallback_FallbackParser {
            + language() str
            + extensions() set[str]
            + parse_file(path, project_root, project_prefix) FileAnalysis
        }
    }

    namespace src_core_services_audit_parsers_c_parser {
        class src_core_services_audit_parsers_c_parser_CFamilyParser {
            + language() str
            + extensions() set[str]
            + parse_file(file_path, project_root, project_prefix) FileAnalysis
            # _extract_includes(source, lang) list[ImportInfo]
            # _extract_symbols(source, lines) list[SymbolInfo]
            # _compute_metrics(source, lines, imports, symbols, lang) tuple[FileMetrics, dict]
        }
    }

    namespace src_core_services_audit_parsers_config_parser {
        class src_core_services_audit_parsers_config_parser_ConfigParser {
            + language() str
            + extensions() set[str]
            + parse_file(file_path, project_root, project_prefix) FileAnalysis
        }
    }

    namespace src_core_services_audit_parsers_css_parser {
        class src_core_services_audit_parsers_css_parser_CSSParser {
            + language() str
            + extensions() set[str]
            + parse_file(file_path, project_root, project_prefix) FileAnalysis
            # _extract_imports(source) list[ImportInfo]
            # _compute_metrics(source, lines, imports, is_preprocessor, lang) tuple[FileMetrics, dict]
        }
    }

    namespace src_core_services_audit_parsers_go_parser {
        class src_core_services_audit_parsers_go_parser_GoParser {
            + language() str
            + extensions() set[str]
            + parse_file(file_path, project_root, project_prefix) FileAnalysis
            # _extract_imports(source) list[ImportInfo]
            # _extract_symbols(source, lines) list[SymbolInfo]
            # _compute_metrics(source, lines, imports, symbols, package_name) tuple[FileMetrics, dict]
        }
    }

    namespace src_core_services_audit_parsers_js_parser {
        class src_core_services_audit_parsers_js_parser_JavaScriptParser {
            + language() str
            + extensions() set[str]
            + parse_file(file_path, project_root, project_prefix) FileAnalysis
            # _extract_imports(source, project_prefix) list[ImportInfo]
            # _extract_symbols(lines, is_typescript) list[SymbolInfo]
            # _compute_metrics(source, lines, imports, symbols, is_typescript) FileMetrics
        }
    }

    namespace src_core_services_audit_parsers_jvm_parser {
        class src_core_services_audit_parsers_jvm_parser_JVMParser {
            + language() str
            + extensions() set[str]
            + parse_file(file_path, project_root, project_prefix) FileAnalysis
            # _parse_java(source, lines, rel_path) FileAnalysis
            # _extract_java_imports(source) list[ImportInfo]
            # _extract_java_symbols(source, lines) list[SymbolInfo]
            # _compute_java_metrics(source, lines, imports, symbols, package_name) tuple[FileMetrics, dict]
            # _parse_kotlin(source, lines, rel_path) FileAnalysis
            # _extract_kotlin_imports(source) list[ImportInfo]
            # _extract_kotlin_symbols(source, lines) list[SymbolInfo]
            # _compute_kotlin_metrics(source, lines, imports, symbols, package_name) tuple[FileMetrics, dict]
            # _parse_scala(source, lines, rel_path) FileAnalysis
            # _extract_scala_imports(source) list[ImportInfo]
            # _extract_scala_symbols(source, lines) list[SymbolInfo]
            # _compute_scala_metrics(source, lines, imports, symbols, package_name) tuple[FileMetrics, dict]
        }
    }

    namespace src_core_services_audit_parsers_multilang_parser {
        class src_core_services_audit_parsers_multilang_parser_MultiLangParser {
            + language() str
            + extensions() set[str]
            + parse_file(file_path, project_root, project_prefix) FileAnalysis
        }
    }

    namespace src_core_services_audit_parsers_python_parser {
        class src_core_services_audit_parsers_python_parser_PythonParser {
            + language() str
            + extensions() set[str]
            + parse_file(path, project_root, project_prefix) FileAnalysis
        }
    }

    namespace src_core_services_audit_parsers_rust_parser {
        class src_core_services_audit_parsers_rust_parser_RustParser {
            + language() str
            + extensions() set[str]
            + parse_file(file_path, project_root, project_prefix) FileAnalysis
            # _extract_imports(source) list[ImportInfo]
            # _extract_symbols(source, lines) list[SymbolInfo]
            # _compute_metrics(source, lines, imports, symbols) tuple[FileMetrics, dict]
        }
    }

    namespace src_core_services_audit_parsers_template_parser {
        class src_core_services_audit_parsers_template_parser_TemplateParser {
            + language() str
            + extensions() set[str]
            + parse_file(file_path, project_root, project_prefix) FileAnalysis
        }
    }

    namespace src_core_services_changelog_models {
        class src_core_services_changelog_models_Changelog {
            <<dataclass>>
            + header: str
            + unreleased: ChangelogSection
            + releases: list[ChangelogSection]
            + all_sections() list[ChangelogSection]
            + latest_version() str | None
        }
        class src_core_services_changelog_models_ChangelogSection {
            <<dataclass>>
            + version: str
            + date: str
            + entries: dict[str, list[ChangelogEntry]]
            + is_unreleased() bool
            + is_empty() bool
            + entry_count() int
            + has_breaking() bool
            + has_features() bool
        }
    }

    namespace src_core_services_chat_models {
        class src_core_services_chat_models_ChatMessage {
            + id: str
            + ts: str
            + user: str
            + hostname: str
            + text: str
            + thread_id: str | None
            + run_id: str | None
            + trace_id: str | None
            + refs: list[str]
            + source: Literal['manual', 'trace', 'system']
            ... 1 more fields
            + ensure_id() str
            + to_jsonl() str
            + from_jsonl(line) ChatMessage
        }
        class src_core_services_chat_models_MessageFlags {
            + publish: bool
            + encrypted: bool
        }
    }

    namespace src_core_services_content_outline {
        class src_core_services_content_outline_CssOutlineStrategy {
            + extract(source, file_path) list[dict]
        }
        class src_core_services_content_outline_EncryptedOutlineStrategy {
            + extract(source, file_path) list[dict]
        }
        class src_core_services_content_outline_FallbackOutlineStrategy {
            + extract(source, file_path) list[dict]
        }
        class src_core_services_content_outline_GoOutlineStrategy {
            + extract(source, file_path) list[dict]
        }
        class src_core_services_content_outline_HtmlOutlineStrategy {
            + extract(source, file_path) list[dict]
        }
        class src_core_services_content_outline_JavaScriptOutlineStrategy {
            + extract(source, file_path) list[dict]
        }
        class src_core_services_content_outline_JsonOutlineStrategy {
            + extract(source, file_path) list[dict]
            # _find_key_line(lines, key, found) int
        }
        class src_core_services_content_outline_MarkdownOutlineStrategy {
            + extract(source, file_path) list[dict]
        }
        class src_core_services_content_outline_OutlineStrategy {
            + extensions: set[str]
            + extract(source, file_path) list[dict]
        }
        class src_core_services_content_outline_PythonOutlineStrategy {
            + extract(source, file_path) list[dict]
        }
        class src_core_services_content_outline_RustOutlineStrategy {
            + extract(source, file_path) list[dict]
        }
        class src_core_services_content_outline_ShellOutlineStrategy {
            + extract(source, file_path) list[dict]
        }
        class src_core_services_content_outline_SqlOutlineStrategy {
            + extract(source, file_path) list[dict]
        }
        class src_core_services_content_outline_TomlOutlineStrategy {
            + extract(source, file_path) list[dict]
        }
        class src_core_services_content_outline_YamlOutlineStrategy {
            + extract(source, file_path) list[dict]
        }
    }

    namespace src_core_services_detection {
        class src_core_services_detection_DetectionResult {
            <<dataclass>>
            + modules: list[Module]
            + unmatched_refs: list[str]
            + extra_detections: list[Module]
            + total_detected() int
            + total_modules() int
            + get_module(name) Module | None
            + to_dict() dict
        }
    }

    namespace src_core_services_pages_pipeline_scanner {
        class src_core_services_pages_pipeline_scanner_DetectedCI {
            <<dataclass>>
            + path: str
            + name: str
            + provider: str
            + build_script: str
            + env_vars: dict
            + deploy_target: str
        }
        class src_core_services_pages_pipeline_scanner_DetectedFramework {
            <<dataclass>>
            + name: str
            + config_path: str
            + output_dir: str
            + build_cmd: str
            + preview_cmd: str
            + preview_port: int
            + version: str
        }
        class src_core_services_pages_pipeline_scanner_DetectedScript {
            <<dataclass>>
            + path: str
            + type: str
            + description: str
            + flags: list[str]
            + stages: list[dict]
            + operability: str
            + operability_notes: list[str]
            + remediation: dict
        }
        class src_core_services_pages_pipeline_scanner_PipelineScanResult {
            <<dataclass>>
            + scripts: list[DetectedScript]
            + frameworks: list[DetectedFramework]
            + ci_workflows: list[DetectedCI]
            + suggested_config: dict
            + compatibility: str
            + compatibility_notes: list[str]
        }
    }

    namespace src_core_services_pages_builders_audit_directive {
        class src_core_services_pages_builders_audit_directive_AuditScope {
            <<dataclass>>
            + module: str
            + sub_path: str
            + source_prefix: str
            + module_path: str
        }
        class src_core_services_pages_builders_audit_directive_ScopedAuditData {
            <<dataclass>>
            + scope: AuditScope
            + source_label: str
            + computed_at: str
            + health_score: float | None
            + file_count: int
            + total_lines: int
            + total_functions: int
            + total_classes: int
            + cached_file_count: int
            + subcategory_averages: dict
            ... 24 more fields
        }
    }

    namespace src_core_services_pages_builders_base {
        class src_core_services_pages_builders_base_BuilderInfo {
            <<dataclass>>
            + name: str
            + label: str
            + requires: list[str]
            + description: str
            + available: bool
            + install_hint: str
            + install_cmd: list[str]
        }
        class src_core_services_pages_builders_base_PageBuilder {
            <<abstract>>
            + info() BuilderInfo
            + pipeline_stages() list[StageInfo]
            + run_stage(stage, segment, workspace) LogStream
            + output_dir(workspace) Path
            + config_schema() list[ConfigField]
            + detect() bool
            + preview(segment, workspace) tuple[subprocess.Popen, int]
            + scaffold(segment, workspace) None
            + build(segment, workspace) subprocess.Popen
        }
        class src_core_services_pages_builders_base_PipelineResult {
            <<dataclass>>
            + segment: str
            + builder: str
            + stages: list[StageResult]
            + ok: bool
            + total_duration_ms: int
            + serve_url: str
            + output_dir: str
        }
        class src_core_services_pages_builders_base_SegmentConfig {
            <<dataclass>>
            + name: str
            + source: str
            + builder: str
            + path: str
            + auto: bool
            + config: dict
        }
        class src_core_services_pages_builders_base_StageResult {
            <<dataclass>>
            + name: str
            + label: str
            + status: str
            + duration_ms: int
            + log_lines: list[str]
            + error: str
            + detail: dict
        }
    }

    namespace src_core_services_pages_builders_custom {
        class src_core_services_pages_builders_custom_CustomBuilder {
            # _segment: SegmentConfig | None
            + info() BuilderInfo
            + detect() bool
            + config_schema() list[ConfigField]
            + pipeline_stages() list[StageInfo]
            + run_stage(stage, segment, workspace) LogStream
            # _build_env(segment, workspace) dict[str, str]
            # _resolve_project_root(workspace) Path
            # _resolve_cwd(segment, workspace) str
            # _resolve_output_dir(segment, workspace) Path
            # _stage_scaffold(segment, workspace) LogStream
            # _stage_build(segment, workspace) LogStream
            # _run_custom_stage(stage_def, segment, workspace) LogStream
            # _exec_command(cmd, cwd, env) LogStream
            + output_dir(workspace) Path
            + preview(segment, workspace) tuple[subprocess.Popen, int]
        }
    }

    namespace src_core_services_pages_builders_docusaurus {
        class src_core_services_pages_builders_docusaurus_DocusaurusBuilder {
            # _admin_url_cache: str | None
            + info() BuilderInfo
            # _admin_url() str
            + pipeline_stages() list[StageInfo]
            + run_stage(stage, segment, workspace) LogStream
            # _stage_source(segment, workspace) LogStream
            # _stage_transform(segment, workspace) LogStream
            # _stage_scaffold(segment, workspace) LogStream
            # _detect_repo_url(segment) str
            # _stage_install(segment, workspace) LogStream
            # _compute_workspace_hash(workspace) str
            # _maybe_clear_caches(workspace) list[str]
            # _stage_build(segment, workspace) LogStream
            # _stream_subprocess(cmd, workspace, env) 'Generator[str, None, tuple[list[str], int]]'
            + output_dir(workspace) Path
            + preview(segment, workspace) tuple[subprocess.Popen, int]
        }
    }

    namespace src_core_services_pages_builders_hugo {
        class src_core_services_pages_builders_hugo_HugoBuilder {
            + info() BuilderInfo
            + pipeline_stages() list[StageInfo]
            + config_schema() list[ConfigField]
            + run_stage(stage, segment, workspace) LogStream
            # _stage_scaffold(segment, workspace) LogStream
            # _stage_build(segment, workspace) LogStream
            + output_dir(workspace) Path
            + preview(segment, workspace) tuple[subprocess.Popen, int]
        }
    }

    namespace src_core_services_pages_builders_mkdocs {
        class src_core_services_pages_builders_mkdocs_MkDocsBuilder {
            + info() BuilderInfo
            + detect() bool
            + config_schema() list[ConfigField]
            + pipeline_stages() list[StageInfo]
            + run_stage(stage, segment, workspace) LogStream
            # _stage_scaffold(segment, workspace) LogStream
            # _stage_build(segment, workspace) LogStream
            + output_dir(workspace) Path
            + preview(segment, workspace) tuple[subprocess.Popen, int]
        }
    }

    namespace src_core_services_pages_builders_raw {
        class src_core_services_pages_builders_raw_RawBuilder {
            + info() BuilderInfo
            + detect() bool
            + pipeline_stages() list[StageInfo]
            + run_stage(stage, segment, workspace) LogStream
            # _stage_source(segment, workspace) LogStream
            + output_dir(workspace) Path
            + preview(segment, workspace) tuple[subprocess.Popen, int]
        }
    }

    namespace src_core_services_pages_builders_sphinx {
        class src_core_services_pages_builders_sphinx_SphinxBuilder {
            + info() BuilderInfo
            + detect() bool
            + config_schema() list[ConfigField]
            + pipeline_stages() list[StageInfo]
            + run_stage(stage, segment, workspace) LogStream
            # _stage_scaffold(segment, workspace) LogStream
            # _stage_build(segment, workspace) LogStream
            + output_dir(workspace) Path
            + preview(segment, workspace) tuple[subprocess.Popen, int]
        }
    }

    namespace src_core_services_scripts_models {
        class src_core_services_scripts_models_ScriptMeta {
            <<dataclass>>
            + id: str
            + name: str
            + description: str
            + category: str
            + tags: list[str]
            + language: str
            + mode: str
            + timeout: int
            + parameters: list[ScriptParameter]
            + default_output: str
            ... 9 more fields
        }
        class src_core_services_scripts_models_ScriptParameter {
            <<dataclass>>
            + name: str
            + type: str
            + description: str
            + required: bool
            + default: str
            + choices: list[str]
        }
    }

    namespace src_core_services_trace_models {
        class src_core_services_trace_models_SessionTrace {
            + trace_id: str
            + name: str
            + classification: str
            + started_at: str
            + ended_at: str
            + user: str
            + code_ref: str
            + events: list[TraceEvent]
            + auto_summary: str
            + audit_refs: list[str]
            ... 3 more fields
            + ensure_id() str
        }
        class src_core_services_trace_models_TraceEvent {
            + seq: int
            + ts: str
            + type: str
            + key: str
            + target: str
            + result: str
            + duration_ms: int
            + detail: dict[str, Any]
        }
    }

    namespace src_core_use_cases_config_check {
        class src_core_use_cases_config_check_ConfigCheckResult {
            <<dataclass>>
            + valid: bool
            + project: Project | None
            + config_path: Path | None
            + errors: list[str]
            + warnings: list[str]
            + to_dict() dict
        }
    }

    namespace src_core_use_cases_detect {
        class src_core_use_cases_detect_DetectResult {
            <<dataclass>>
            + detection: DetectionResult | None
            + project: Project | None
            + project_root: Path | None
            + stacks_loaded: int
            + state_saved: bool
            + error: str | None
            + to_dict() dict
        }
    }

    namespace src_core_use_cases_run {
        class src_core_use_cases_run_RunResult {
            <<dataclass>>
            + report: ExecutionReport | None
            + plan: ExecutionPlan | None
            + project: Project | None
            + project_root: Path | None
            + modules_targeted: int
            + actions_planned: int
            + error: str | None
            + to_dict() dict
        }
    }

    namespace src_core_use_cases_status {
        class src_core_use_cases_status_StatusResult {
            <<dataclass>>
            + project: Project | None
            + state: ProjectState | None
            + project_root: Path | None
            + config_path: Path | None
            + error: str | None
            + module_count: int
            + environment_count: int
            + detected_count: int
            + current_environment: str
            + to_dict() dict
        }
    }

    src_core_services_artifacts_builders_cargo_CargoBuilder --|> src_core_services_artifacts_builders_base_ArtifactBuilder : ArtifactBuilder
    src_core_services_artifacts_builders_docker_DockerBuilder --|> src_core_services_artifacts_builders_base_ArtifactBuilder : ArtifactBuilder
    src_core_services_artifacts_builders_dotnet_DotnetBuilder --|> src_core_services_artifacts_builders_base_ArtifactBuilder : ArtifactBuilder
    src_core_services_artifacts_builders_gem_GemBuilder --|> src_core_services_artifacts_builders_base_ArtifactBuilder : ArtifactBuilder
    src_core_services_artifacts_builders_go_GoBuilder --|> src_core_services_artifacts_builders_base_ArtifactBuilder : ArtifactBuilder
    src_core_services_artifacts_builders_gradle_GradleBuilder --|> src_core_services_artifacts_builders_base_ArtifactBuilder : ArtifactBuilder
    src_core_services_artifacts_builders_makefile_MakefileBuilder --|> src_core_services_artifacts_builders_base_ArtifactBuilder : ArtifactBuilder
    src_core_services_artifacts_builders_maven_MavenBuilder --|> src_core_services_artifacts_builders_base_ArtifactBuilder : ArtifactBuilder
    src_core_services_artifacts_builders_mix_MixBuilder --|> src_core_services_artifacts_builders_base_ArtifactBuilder : ArtifactBuilder
    src_core_services_artifacts_builders_npm_NpmBuilder --|> src_core_services_artifacts_builders_base_ArtifactBuilder : ArtifactBuilder
    src_core_services_artifacts_builders_pip_builder_PipBuilder --|> src_core_services_artifacts_builders_base_ArtifactBuilder : ArtifactBuilder
    src_core_services_artifacts_builders_script_ScriptBuilder --|> src_core_services_artifacts_builders_base_ArtifactBuilder : ArtifactBuilder
    src_core_services_artifacts_publishers_github_release_GitHubReleasePublisher --|> src_core_services_artifacts_publishers_base_ArtifactPublisher : ArtifactPublisher
    src_core_services_artifacts_publishers_npm_publisher_NpmPublisher --|> src_core_services_artifacts_publishers_base_ArtifactPublisher : ArtifactPublisher
    src_core_services_artifacts_publishers_pypi_PyPIPublisher --|> src_core_services_artifacts_publishers_base_ArtifactPublisher : ArtifactPublisher
    src_core_services_audit_parsers__fallback_FallbackParser --|> src_core_services_audit_parsers__base_BaseParser : BaseParser
    src_core_services_audit_parsers_c_parser_CFamilyParser --|> src_core_services_audit_parsers__base_BaseParser : BaseParser
    src_core_services_audit_parsers_config_parser_ConfigParser --|> src_core_services_audit_parsers__base_BaseParser : BaseParser
    src_core_services_audit_parsers_css_parser_CSSParser --|> src_core_services_audit_parsers__base_BaseParser : BaseParser
    src_core_services_audit_parsers_go_parser_GoParser --|> src_core_services_audit_parsers__base_BaseParser : BaseParser
    src_core_services_audit_parsers_js_parser_JavaScriptParser --|> src_core_services_audit_parsers__base_BaseParser : BaseParser
    src_core_services_audit_parsers_jvm_parser_JVMParser --|> src_core_services_audit_parsers__base_BaseParser : BaseParser
    src_core_services_audit_parsers_multilang_parser_MultiLangParser --|> src_core_services_audit_parsers__base_BaseParser : BaseParser
    src_core_services_audit_parsers_python_parser_PythonParser --|> src_core_services_audit_parsers__base_BaseParser : BaseParser
    src_core_services_audit_parsers_rust_parser_RustParser --|> src_core_services_audit_parsers__base_BaseParser : BaseParser
    src_core_services_audit_parsers_template_parser_TemplateParser --|> src_core_services_audit_parsers__base_BaseParser : BaseParser
    src_core_services_content_outline_MarkdownOutlineStrategy --|> src_core_services_content_outline_OutlineStrategy : OutlineStrategy
    src_core_services_content_outline_PythonOutlineStrategy --|> src_core_services_content_outline_OutlineStrategy : OutlineStrategy
    src_core_services_content_outline_EncryptedOutlineStrategy --|> src_core_services_content_outline_OutlineStrategy : OutlineStrategy
    src_core_services_content_outline_JavaScriptOutlineStrategy --|> src_core_services_content_outline_OutlineStrategy : OutlineStrategy
    src_core_services_content_outline_GoOutlineStrategy --|> src_core_services_content_outline_OutlineStrategy : OutlineStrategy
    src_core_services_content_outline_RustOutlineStrategy --|> src_core_services_content_outline_OutlineStrategy : OutlineStrategy
    src_core_services_content_outline_HtmlOutlineStrategy --|> src_core_services_content_outline_OutlineStrategy : OutlineStrategy
    src_core_services_content_outline_CssOutlineStrategy --|> src_core_services_content_outline_OutlineStrategy : OutlineStrategy
    src_core_services_content_outline_YamlOutlineStrategy --|> src_core_services_content_outline_OutlineStrategy : OutlineStrategy
    src_core_services_content_outline_JsonOutlineStrategy --|> src_core_services_content_outline_OutlineStrategy : OutlineStrategy
    src_core_services_content_outline_TomlOutlineStrategy --|> src_core_services_content_outline_OutlineStrategy : OutlineStrategy
    src_core_services_content_outline_ShellOutlineStrategy --|> src_core_services_content_outline_OutlineStrategy : OutlineStrategy
    src_core_services_content_outline_SqlOutlineStrategy --|> src_core_services_content_outline_OutlineStrategy : OutlineStrategy
    src_core_services_content_outline_FallbackOutlineStrategy --|> src_core_services_content_outline_OutlineStrategy : OutlineStrategy
    src_core_services_pages_builders_custom_CustomBuilder --|> src_core_services_pages_builders_base_PageBuilder : PageBuilder
    src_core_services_pages_builders_docusaurus_DocusaurusBuilder --|> src_core_services_pages_builders_base_PageBuilder : PageBuilder
    src_core_services_pages_builders_hugo_HugoBuilder --|> src_core_services_pages_builders_base_PageBuilder : PageBuilder
    src_core_services_pages_builders_mkdocs_MkDocsBuilder --|> src_core_services_pages_builders_base_PageBuilder : PageBuilder
    src_core_services_pages_builders_raw_RawBuilder --|> src_core_services_pages_builders_base_PageBuilder : PageBuilder
    src_core_services_pages_builders_sphinx_SphinxBuilder --|> src_core_services_pages_builders_base_PageBuilder : PageBuilder
    src_core_data_script_templates_lib_code_analyzer_ClassInfo o-- src_core_data_script_templates_lib_code_analyzer_FieldInfo : fields
    src_core_data_script_templates_lib_code_analyzer_ClassInfo o-- src_core_data_script_templates_lib_code_analyzer_MethodInfo : methods
    src_core_data_script_templates_lib_code_analyzer_ProjectAnalysis o-- src_core_data_script_templates_lib_code_analyzer_ClassInfo : classes
    src_core_data_script_templates_lib_graph_builder_GraphEdge *-- src_core_data_script_templates_lib_graph_builder_RelationType : relation
    src_core_data_script_templates_lib_graph_builder_ClassGraph o-- src_core_data_script_templates_lib_graph_builder_GraphNode : nodes
    src_core_data_script_templates_lib_graph_builder_ClassGraph o-- src_core_data_script_templates_lib_graph_builder_GraphEdge : edges
    src_core_engine_executor_ExecutionPlan o-- src_core_models_action_Action : actions
    src_core_engine_executor_ExecutionReport o-- src_core_models_action_Receipt : receipts
    src_core_models_module_Module *-- src_core_models_module_ModuleHealth : health
    src_core_models_project_Project o-- src_core_models_project_Environment : environments
    src_core_models_project_Project o-- src_core_models_project_ModuleRef : modules
    src_core_models_project_Project *-- src_core_models_project_ExternalLinks : external
    src_core_models_stack_Stack o-- src_core_models_stack_AdapterRequirement : requires
    src_core_models_stack_Stack *-- src_core_models_stack_DetectionRule : detection
    src_core_models_stack_Stack o-- src_core_models_stack_StackCapability : capabilities
    src_core_models_state_ProjectState o-- src_core_models_state_ModuleState : modules
    src_core_models_state_ProjectState o-- src_core_models_state_AdapterState : adapters
    src_core_models_state_ProjectState *-- src_core_models_state_OperationRecord : last_operation
    src_core_observability_health_SystemHealth o-- src_core_observability_health_ComponentHealth : components
    src_core_observability_metrics_MetricsRegistry o-- src_core_observability_metrics_Counter : _counters
    src_core_observability_metrics_MetricsRegistry o-- src_core_observability_metrics_Gauge : _gauges
    src_core_observability_metrics_MetricsRegistry o-- src_core_observability_metrics_Histogram : _histograms
    src_core_reliability_circuit_breaker_CircuitBreaker *-- src_core_reliability_circuit_breaker_CircuitState : state
    src_core_reliability_circuit_breaker_CircuitBreakerRegistry o-- src_core_reliability_circuit_breaker_CircuitBreaker : breakers
    src_core_reliability_retry_queue_RetryQueue o-- src_core_reliability_retry_queue_RetryItem : _items
    src_core_services_audit_models_L0Result *-- src_core_services_audit_models_AuditMeta : _meta
    src_core_services_audit_models_L0Result *-- src_core_services_audit_models_OSInfo : os
    src_core_services_audit_models_L0Result *-- src_core_services_audit_models_RuntimeInfo : runtime
    src_core_services_audit_models_L0Result o-- src_core_services_audit_models_ToolInfo : tools
    src_core_services_audit_models_L0Result o-- src_core_services_audit_models_ModuleInfo : modules
    src_core_services_audit_models_L0Result o-- src_core_services_audit_models_ManifestInfo : manifests
    src_core_services_audit_models_L1DepsResult *-- src_core_services_audit_models_AuditMeta : _meta
    src_core_services_audit_models_L1DepsResult o-- src_core_services_audit_models_DependencyInfo : dependencies
    src_core_services_audit_models_L1DepsResult o-- src_core_services_audit_models_CrossoverInfo : crossovers
    src_core_services_audit_models_L1StructResult *-- src_core_services_audit_models_AuditMeta : _meta
    src_core_services_audit_models_L1StructResult o-- src_core_services_audit_models_ComponentInfo : components
    src_core_services_audit_models_L1StructResult o-- src_core_services_audit_models_EntrypointInfo : entrypoints
    src_core_services_audit_models_L1ClientsResult *-- src_core_services_audit_models_AuditMeta : _meta
    src_core_services_audit_models_L1ClientsResult o-- src_core_services_audit_models_ClientInfo : clients
    src_core_services_audit_models_ScoreResult o-- src_core_services_audit_models_ScoreBreakdownItem : breakdown
    src_core_services_audit_models_AuditScores *-- src_core_services_audit_models_AuditMeta : _meta
    src_core_services_audit_models_AuditScores *-- src_core_services_audit_models_ScoreResult : complexity
    src_core_services_audit_parsers_ParserRegistry o-- src_core_services_audit_parsers__base_BaseParser : _parsers
    src_core_services_audit_parsers_ParserRegistry --> src_core_services_audit_parsers__base_BaseParser : _fallback
    src_core_services_audit_parsers__base_FileAnalysis o-- src_core_services_audit_parsers__base_ImportInfo : imports
    src_core_services_audit_parsers__base_FileAnalysis o-- src_core_services_audit_parsers__base_SymbolInfo : symbols
    src_core_services_audit_parsers__base_FileAnalysis *-- src_core_services_audit_parsers__base_FileMetrics : metrics
    src_core_services_audit_parsers__base_FileAnalysis o-- src_core_services_audit_parsers__base_SymbolLocation : symbol_locations
    src_core_services_changelog_models_Changelog *-- src_core_services_changelog_models_ChangelogSection : unreleased
    src_core_services_changelog_models_Changelog o-- src_core_services_changelog_models_ChangelogSection : releases
    src_core_services_chat_models_ChatMessage *-- src_core_services_chat_models_MessageFlags : flags
    src_core_services_detection_DetectionResult o-- src_core_models_module_Module : modules
    src_core_services_pages_pipeline_scanner_PipelineScanResult o-- src_core_services_pages_pipeline_scanner_DetectedScript : scripts
    src_core_services_pages_pipeline_scanner_PipelineScanResult o-- src_core_services_pages_pipeline_scanner_DetectedFramework : frameworks
    src_core_services_pages_pipeline_scanner_PipelineScanResult o-- src_core_services_pages_pipeline_scanner_DetectedCI : ci_workflows
    src_core_services_pages_builders_audit_directive_ScopedAuditData *-- src_core_services_pages_builders_audit_directive_AuditScope : scope
    src_core_services_pages_builders_base_PipelineResult o-- src_core_services_pages_builders_base_StageResult : stages
    src_core_services_pages_builders_custom_CustomBuilder --> src_core_services_pages_builders_base_SegmentConfig : _segment
    src_core_services_scripts_models_ScriptMeta o-- src_core_services_scripts_models_ScriptParameter : parameters
    src_core_services_trace_models_SessionTrace o-- src_core_services_trace_models_TraceEvent : events
    src_core_use_cases_config_check_ConfigCheckResult --> src_core_models_project_Project : project
    src_core_use_cases_detect_DetectResult --> src_core_services_detection_DetectionResult : detection
    src_core_use_cases_detect_DetectResult --> src_core_models_project_Project : project
    src_core_use_cases_run_RunResult --> src_core_engine_executor_ExecutionReport : report
    src_core_use_cases_run_RunResult --> src_core_engine_executor_ExecutionPlan : plan
    src_core_use_cases_run_RunResult --> src_core_models_project_Project : project
    src_core_use_cases_status_StatusResult --> src_core_models_project_Project : project
    src_core_use_cases_status_StatusResult --> src_core_models_state_ProjectState : state
    src_core_observability_metrics_MetricsRegistry ..> src_core_observability_metrics_TimerContext
    src_core_services_audit_parsers__base_BaseParser ..> src_core_services_audit_parsers__base_FileAnalysis
    src_core_services_audit_parsers__fallback_FallbackParser ..> src_core_services_audit_parsers__base_FileAnalysis
    src_core_services_audit_parsers_c_parser_CFamilyParser ..> src_core_services_audit_parsers__base_FileAnalysis
    src_core_services_audit_parsers_config_parser_ConfigParser ..> src_core_services_audit_parsers__base_FileAnalysis
    src_core_services_audit_parsers_css_parser_CSSParser ..> src_core_services_audit_parsers__base_FileAnalysis
    src_core_services_audit_parsers_go_parser_GoParser ..> src_core_services_audit_parsers__base_FileAnalysis
    src_core_services_audit_parsers_js_parser_JavaScriptParser ..> src_core_services_audit_parsers__base_FileAnalysis
    src_core_services_audit_parsers_js_parser_JavaScriptParser ..> src_core_services_audit_parsers__base_FileMetrics
    src_core_services_audit_parsers_jvm_parser_JVMParser ..> src_core_services_audit_parsers__base_FileAnalysis
    src_core_services_audit_parsers_multilang_parser_MultiLangParser ..> src_core_services_audit_parsers__base_FileAnalysis
    src_core_services_audit_parsers_python_parser_PythonParser ..> src_core_services_audit_parsers__base_FileAnalysis
    src_core_services_audit_parsers_rust_parser_RustParser ..> src_core_services_audit_parsers__base_FileAnalysis
    src_core_services_audit_parsers_template_parser_TemplateParser ..> src_core_services_audit_parsers__base_FileAnalysis
    src_core_services_pages_builders_base_PageBuilder ..> src_core_services_pages_builders_base_BuilderInfo
    src_core_services_pages_builders_custom_CustomBuilder ..> src_core_services_pages_builders_base_BuilderInfo
    src_core_services_pages_builders_docusaurus_DocusaurusBuilder ..> src_core_services_pages_builders_base_BuilderInfo
    src_core_services_pages_builders_hugo_HugoBuilder ..> src_core_services_pages_builders_base_BuilderInfo
    src_core_services_pages_builders_mkdocs_MkDocsBuilder ..> src_core_services_pages_builders_base_BuilderInfo
    src_core_services_pages_builders_raw_RawBuilder ..> src_core_services_pages_builders_base_BuilderInfo
    src_core_services_pages_builders_sphinx_SphinxBuilder ..> src_core_services_pages_builders_base_BuilderInfo
```

## Class Index

### src.core.config.loader

- **ConfigError** (0 fields, 0 methods) — Raised when project configuration is invalid or missing.

### src.core.data

- **DataRegistry** (0 fields, 23 methods) — Central registry for all static data catalogs.

### src.core.data.script_templates.lib.code_analyzer

- **ClassInfo** `dataclass` (15 fields, 0 methods) — Complete class information for diagram generation.
- **FieldInfo** `dataclass` (4 fields, 0 methods) — A class field (instance or class variable).
- **MethodInfo** `dataclass` (10 fields, 0 methods) — A method in a class.
- **ProjectAnalysis** `dataclass` (5 fields, 0 methods) — Complete project analysis result.

### src.core.data.script_templates.lib.graph_builder

- **ClassGraph** `dataclass` (4 fields, 5 methods) — A complete relationship graph.
- **GraphEdge** `dataclass` (5 fields, 0 methods) — A directed edge in the relationship graph.
- **GraphNode** `dataclass` (7 fields, 0 methods) — A node in the relationship graph.
- **RelationType** (0 fields, 0 methods) — Types of relationships between classes.

### src.core.data.script_templates.lib.mermaid_generator

- **MermaidConfig** `dataclass` (9 fields, 0 methods) — Configuration for Mermaid diagram generation.

### src.core.engine.executor

- **ExecutionPlan** `dataclass` (4 fields, 1 methods) — A planned set of actions to execute.
- **ExecutionReport** `dataclass` (4 fields, 7 methods) — Result of executing a plan.

### src.core.models.action

- **Action** (6 fields, 0 methods) — A requested operation to be executed by an adapter.
- **Receipt** (10 fields, 5 methods) — Result of an adapter execution.

### src.core.models.module

- **Module** (11 fields, 2 methods) — A project module with both declared and discovered state.
- **ModuleHealth** (3 fields, 0 methods) — Health snapshot of a module.

### src.core.models.project

- **Environment** (3 fields, 0 methods) — A deployment context (dev, staging, production).
- **ExternalLinks** (4 fields, 0 methods) — Links to external systems (informational, resolved by adapters).
- **ModuleRef** (5 fields, 0 methods) — A module reference declared in project.yml.
- **Project** (8 fields, 4 methods) — Root project identity — loaded from project.yml.

### src.core.models.stack

- **AdapterRequirement** (2 fields, 0 methods) — A required tool adapter with optional version constraint.
- **DetectionRule** (3 fields, 0 methods) — How to detect this stack in a directory.
- **Stack** (9 fields, 3 methods) — Technology knowledge — how a kind of module behaves.
- **StackCapability** (4 fields, 0 methods) — A named capability that this stack supports.

### src.core.models.state

- **AdapterState** (6 fields, 0 methods) — Runtime state of an adapter.
- **ModuleState** (6 fields, 0 methods) — Runtime state of a module.
- **OperationRecord** (8 fields, 0 methods) — Summary of the last operation.
- **ProjectState** (10 fields, 3 methods) — Root state model — serialized to .state/current.json.

### src.core.models.template

- **GeneratedFile** (4 fields, 0 methods) — A file produced by the facilitate/generate phase.

### src.core.observability.health

- **ComponentHealth** `dataclass` (4 fields, 1 methods) — Health of a single component.
- **SystemHealth** `dataclass` (3 fields, 4 methods) — Aggregate health of the entire system.

### src.core.observability.metrics

- **Counter** `dataclass` (3 fields, 2 methods) — Monotonically increasing counter.
- **Gauge** `dataclass` (3 fields, 4 methods) — Value that can go up and down.
- **Histogram** `dataclass` (3 fields, 8 methods) — Simple histogram tracking min, max, sum, count.
- **MetricsRegistry** (3 fields, 7 methods) — Central registry for all metrics.
- **TimerContext** (2 fields, 3 methods) — Context manager for timing operations.

### src.core.persistence.audit

- **AuditEntry** (13 fields, 0 methods) — A single audit log entry.
- **AuditWriter** (1 fields, 6 methods) — Append-only audit ledger writer.

### src.core.reliability.circuit_breaker

- **CircuitBreaker** `dataclass` (10 fields, 6 methods) — Per-adapter circuit breaker.
- **CircuitBreakerRegistry** `dataclass` (3 fields, 3 methods) — Manages circuit breakers for all adapters.
- **CircuitState** (0 fields, 0 methods) — Circuit breaker states.

### src.core.reliability.retry_queue

- **RetryItem** `dataclass` (9 fields, 5 methods) — A single item in the retry queue.
- **RetryQueue** (5 fields, 12 methods) — Persistent retry queue with exponential backoff.

### src.core.services.artifacts.builders.base

- **ArtifactBuilder** `abstract` (0 fields, 4 methods) — Base class for artifact builders.
- **ArtifactStageInfo** `dataclass` (3 fields, 0 methods) — Metadata about a build stage.

### src.core.services.artifacts.builders.cargo

- **CargoBuilder** (0 fields, 4 methods) — Builds Rust crates with structured events.

### src.core.services.artifacts.builders.docker

- **DockerBuilder** (0 fields, 6 methods) — Builds Docker/Podman container images with structured events.

### src.core.services.artifacts.builders.dotnet

- **DotnetBuilder** (0 fields, 4 methods) — Builds .NET projects with structured events.

### src.core.services.artifacts.builders.gem

- **GemBuilder** (0 fields, 4 methods) — Builds Ruby gems with structured events.

### src.core.services.artifacts.builders.go

- **GoBuilder** (0 fields, 4 methods) — Builds Go binaries with structured events.

### src.core.services.artifacts.builders.gradle

- **GradleBuilder** (0 fields, 5 methods) — Builds Java/Kotlin projects via Gradle with structured events.

### src.core.services.artifacts.builders.makefile

- **MakefileBuilder** (0 fields, 7 methods) — Runs Makefile targets with structured event streaming.

### src.core.services.artifacts.builders.maven

- **MavenBuilder** (0 fields, 4 methods) — Builds Java projects via Maven with structured events.

### src.core.services.artifacts.builders.mix

- **MixBuilder** (0 fields, 4 methods) — Builds Elixir projects via Mix with structured events.

### src.core.services.artifacts.builders.npm

- **NpmBuilder** (0 fields, 4 methods) — Builds Node.js packages with structured events.

### src.core.services.artifacts.builders.pip_builder

- **PipBuilder** (0 fields, 6 methods) — Builds pip wheel/sdist packages with structured events.

### src.core.services.artifacts.builders.script

- **ScriptBuilder** (0 fields, 4 methods) — Runs arbitrary shell scripts with structured event streaming.

### src.core.services.artifacts.engine

- **ArtifactBuildResult** `dataclass` (6 fields, 0 methods) — Result of building an artifact target.
- **ArtifactTarget** `dataclass` (9 fields, 0 methods) — A build target that produces a distributable artifact.

### src.core.services.artifacts.publishers.base

- **ArtifactPublishResult** `dataclass` (8 fields, 0 methods) — Result of publishing an artifact.
- **ArtifactPublisher** `abstract` (0 fields, 3 methods) — Base class for artifact publishers.

### src.core.services.artifacts.publishers.github_release

- **GitHubReleasePublisher** (0 fields, 3 methods) — Creates GitHub Releases and uploads built artifacts.

### src.core.services.artifacts.publishers.npm_publisher

- **NpmPublisher** (0 fields, 3 methods) — Publishes Node packages to the npm registry.

### src.core.services.artifacts.publishers.pypi

- **PyPIPublisher** (1 fields, 4 methods) — Publishes Python packages to PyPI/TestPyPI via twine.

### src.core.services.audit.catalog

- **LibraryInfo** (5 fields, 0 methods)

### src.core.services.audit.models

- **AuditMeta** (5 fields, 0 methods)
- **AuditScores** (3 fields, 0 methods)
- **ClientInfo** (6 fields, 0 methods)
- **ComponentInfo** (4 fields, 0 methods)
- **CrossoverInfo** (4 fields, 0 methods)
- **DependencyInfo** (6 fields, 0 methods)
- **EntrypointInfo** (3 fields, 0 methods)
- **L0Result** (7 fields, 0 methods)
- **L1ClientsResult** (6 fields, 0 methods)
- **L1DepsResult** (10 fields, 0 methods)
- **L1StructResult** (11 fields, 0 methods)
- **ManifestInfo** (4 fields, 0 methods)
- **ModuleInfo** (9 fields, 0 methods)
- **OSInfo** (5 fields, 0 methods)
- **RuntimeInfo** (13 fields, 0 methods) — Merged Python runtime + virtual environment info.
- **ScoreBreakdownItem** (3 fields, 0 methods)
- **ScoreResult** (2 fields, 0 methods)
- **ToolInfo** (5 fields, 0 methods)

### src.core.services.audit.narrative

- **Observation** `dataclass` (4 fields, 0 methods) — A single narrative observation about the audit data.
- **Recommendation** `dataclass` (3 fields, 0 methods) — A specific actionable recommendation.

### src.core.services.audit.parsers

- **ParserRegistry** (4 fields, 12 methods) — Routes files to the correct language parser based on extension.

### src.core.services.audit.parsers._base

- **BaseParser** `abstract` (0 fields, 4 methods) — Abstract base for all language parsers.
- **FileAnalysis** `dataclass` (10 fields, 1 methods) — Complete analysis result for one source file.
- **FileMetrics** `dataclass` (13 fields, 0 methods) — Code metrics for a single file.
- **ImportInfo** `dataclass` (8 fields, 1 methods) — A single import statement, language-agnostic.
- **SymbolInfo** `dataclass` (12 fields, 1 methods) — A function, class, struct, or other named definition.
- **SymbolLocation** `dataclass` (6 fields, 0 methods) — Links a symbol to its source position for code peeking.

### src.core.services.audit.parsers._fallback

- **FallbackParser** (0 fields, 3 methods) — Generic line-counter for any file type.

### src.core.services.audit.parsers._rubrics

- **QualityDimension** `dataclass` (4 fields, 0 methods) — A single quality dimension within a language rubric.

### src.core.services.audit.parsers.c_parser

- **CFamilyParser** (0 fields, 6 methods) — Regex-based parser for C and C++ source files.

### src.core.services.audit.parsers.config_parser

- **ConfigParser** (0 fields, 3 methods) — Parser for configuration, infrastructure, scripting, and doc files.

### src.core.services.audit.parsers.css_parser

- **CSSParser** (0 fields, 5 methods) — Parser for CSS, SCSS, SASS, Less, and Stylus files.

### src.core.services.audit.parsers.go_parser

- **GoParser** (0 fields, 6 methods) — Regex-based parser for Go source files.

### src.core.services.audit.parsers.js_parser

- **JavaScriptParser** (0 fields, 6 methods) — Parser for JavaScript and TypeScript files.

### src.core.services.audit.parsers.jvm_parser

- **JVMParser** (0 fields, 15 methods) — Regex-based parser for Java, Kotlin, and Scala source files.

### src.core.services.audit.parsers.multilang_parser

- **MultiLangParser** (0 fields, 3 methods) — Parser for Ruby, PHP, C#, Elixir, Swift, and Zig.

### src.core.services.audit.parsers.python_parser

- **PythonParser** (0 fields, 3 methods) — Python AST parser — extracts imports, symbols, and code metrics.

### src.core.services.audit.parsers.rust_parser

- **RustParser** (0 fields, 6 methods) — Regex-based parser for Rust source files.

### src.core.services.audit.parsers.template_parser

- **TemplateParser** (0 fields, 3 methods) — Parser for template engine files.

### src.core.services.changelog.models

- **CCMessage** `dataclass` (8 fields, 2 methods) — A parsed Conventional Commit message.
- **Changelog** `dataclass` (3 fields, 2 methods) — The full CHANGELOG.md document, parsed.
- **ChangelogEntry** `dataclass` (4 fields, 0 methods) — A single line item in a changelog section.
- **ChangelogSection** `dataclass` (3 fields, 5 methods) — A version section in the changelog.

### src.core.services.chat.models

- **ChatMessage** (11 fields, 3 methods) — A single chat message.
- **MessageFlags** (2 fields, 0 methods) — Per-message control flags.
- **Thread** (6 fields, 1 methods) — A conversation thread.

### src.core.services.content.outline

- **CssOutlineStrategy** (0 fields, 1 methods) — Extract section comments and CSS at-rules.
- **EncryptedOutlineStrategy** (0 fields, 1 methods) — Encrypted files cannot be parsed without the key.
- **FallbackOutlineStrategy** (0 fields, 1 methods) — Default strategy for file types without a dedicated extractor.
- **GoOutlineStrategy** (0 fields, 1 methods) — Extract functions, methods, and type declarations from Go source.
- **HtmlOutlineStrategy** (0 fields, 1 methods) — Extract headings and named sections from HTML files.
- **JavaScriptOutlineStrategy** (0 fields, 1 methods) — Extract classes, functions, and arrow-function constants from JS/TS.
- **JsonOutlineStrategy** (0 fields, 2 methods) — Extract top-level keys from JSON objects.
- **MarkdownOutlineStrategy** (0 fields, 1 methods) — Extract headings from Markdown files, nested by level.
- **OutlineStrategy** (1 fields, 1 methods) — Base class for outline extraction strategies.
- **PythonOutlineStrategy** (0 fields, 1 methods) — Extract classes, functions, methods, and top-level constants from Python.
- **RustOutlineStrategy** (0 fields, 1 methods) — Extract functions, structs, enums, traits, and impl blocks from Rust.
- **ShellOutlineStrategy** (0 fields, 1 methods) — Extract function definitions and section comments from shell scripts.
- **SqlOutlineStrategy** (0 fields, 1 methods) — Extract DDL statements (CREATE TABLE, VIEW, FUNCTION, etc.) from SQL.
- **TomlOutlineStrategy** (0 fields, 1 methods) — Extract ``[table]`` and ``[[array-table]]`` headers from TOML.
- **YamlOutlineStrategy** (0 fields, 1 methods) — Extract top-level keys and section-separator comments from YAML.

### src.core.services.detection

- **DetectionResult** `dataclass` (3 fields, 4 methods) — Result of detecting modules in a project.

### src.core.services.event_bus

- **EventBus** (7 fields, 11 methods) — Thread-safe, in-process pub/sub with bounded replay buffer.

### src.core.services.ledger.models

- **Run** (13 fields, 3 methods) — A recorded execution run.
- **RunEvent** (9 fields, 0 methods) — A single fine-grained event within a run's event stream.

### src.core.services.ledger.worktree

- **GitIdentityError** (0 fields, 0 methods) — Raised when git user.name / user.email are not configured.

### src.core.services.pages.pipeline_scanner

- **DetectedCI** `dataclass` (6 fields, 0 methods) — A CI workflow found in the project.
- **DetectedFramework** `dataclass` (7 fields, 0 methods) — A static site framework found in the project.
- **DetectedScript** `dataclass` (8 fields, 0 methods) — A build script found in the project.
- **PipelineScanResult** `dataclass` (6 fields, 0 methods) — Complete scan result for a project.

### src.core.services.pages_builders.audit_directive

- **AuditDataBundle** `dataclass` (9 fields, 0 methods) — All audit data needed for rendering a directive.
- **AuditScope** `dataclass` (4 fields, 0 methods) — Resolved scope for filtering audit data.
- **DirectiveMatch** `dataclass` (5 fields, 0 methods) — A single :::audit-data block found in markdown content.
- **ScopedAuditData** `dataclass` (34 fields, 0 methods) — Audit data filtered and enriched for a specific code scope.

### src.core.services.pages_builders.base

- **BuildResult** `dataclass` (6 fields, 0 methods) — Result of a segment build (legacy model — kept for backward compat).
- **BuilderInfo** `dataclass` (7 fields, 0 methods) — Metadata about a builder.
- **ConfigField** `dataclass` (9 fields, 0 methods) — Declaration of a configurable field for a builder's config modal.
- **PageBuilder** `abstract` (0 fields, 9 methods) — Abstract base for page builders.
- **PipelineResult** `dataclass` (7 fields, 0 methods) — Result of a full pipeline execution.
- **SegmentConfig** `dataclass` (6 fields, 0 methods) — Configuration for a single site segment.
- **StageInfo** `dataclass` (3 fields, 0 methods) — Declaration of a pipeline stage (before execution).
- **StageResult** `dataclass` (7 fields, 0 methods) — Result of executing one pipeline stage.

### src.core.services.pages_builders.custom

- **CustomBuilder** (1 fields, 15 methods) — User-defined build process with multi-stage pipeline support.

### src.core.services.pages_builders.docusaurus

- **DocusaurusBuilder** (1 fields, 15 methods) — Build docs with Docusaurus v3 + MD → MDX transform pipeline.

### src.core.services.pages_builders.hugo

- **HugoBuilder** (0 fields, 8 methods) — Build docs with Hugo.

### src.core.services.pages_builders.mkdocs

- **MkDocsBuilder** (0 fields, 9 methods) — Build docs with MkDocs.

### src.core.services.pages_builders.raw

- **RawBuilder** (0 fields, 7 methods) — Copy-only builder — no external tooling required.

### src.core.services.pages_builders.sphinx

- **SphinxBuilder** (0 fields, 9 methods) — Build docs with Sphinx.

### src.core.services.peek

- **PeekCandidate** `dataclass` (5 fields, 0 methods) — A potential file reference found in text, before validation.
- **PeekReference** `dataclass` (5 fields, 0 methods) — A validated file reference that resolves to a real path.
- **SymbolEntry** `dataclass` (4 fields, 0 methods) — A single symbol location in the project.

### src.core.services.project_index

- **IndexSymbolEntry** `dataclass` (4 fields, 0 methods) — A symbol location in the project (for serialization).
- **ProjectIndex** `dataclass` (16 fields, 0 methods) — In-memory project index — all data fields.

### src.core.services.scripts.models

- **ScriptConfig** `dataclass` (9 fields, 0 methods) — Configuration for the script system.
- **ScriptMeta** `dataclass` (19 fields, 0 methods) — Metadata for a registered script.
- **ScriptParameter** `dataclass` (6 fields, 0 methods) — A declared parameter for a script.

### src.core.services.trace.models

- **SessionTrace** (13 fields, 1 methods) — A recorded session.
- **TraceEvent** (8 fields, 0 methods) — A single event within a session trace.

### src.core.use_cases.config_check

- **ConfigCheckResult** `dataclass` (5 fields, 1 methods) — Result of configuration validation.

### src.core.use_cases.detect

- **DetectResult** `dataclass` (6 fields, 1 methods) — Result of the detect use case.

### src.core.use_cases.run

- **RunResult** `dataclass` (7 fields, 1 methods) — Result of running an automation.

### src.core.use_cases.status

- **StatusResult** `dataclass` (9 fields, 1 methods) — Aggregated project status.


## Relationships

| Source | → | Target | Type | Label |
|--------|---|--------|------|-------|
| ClassInfo | has-many | FieldInfo | aggregates | fields [*] |
| ClassInfo | has-many | MethodInfo | aggregates | methods [*] |
| ProjectAnalysis | has-many | ClassInfo | aggregates | classes [*] |
| ClassGraph | has-many | GraphEdge | aggregates | edges [*] |
| ClassGraph | has-many | GraphNode | aggregates | nodes [*] |
| GraphEdge | has-a | RelationType | composes | relation [1] |
| ExecutionPlan | has-many | Action | aggregates | actions [*] |
| ExecutionReport | has-many | Receipt | aggregates | receipts [*] |
| Module | has-a | ModuleHealth | composes | health [1] |
| Project | has-many | Environment | aggregates | environments [*] |
| Project | has-a | ExternalLinks | composes | external [1] |
| Project | has-many | ModuleRef | aggregates | modules [*] |
| Stack | has-many | AdapterRequirement | aggregates | requires [*] |
| Stack | has-a | DetectionRule | composes | detection [1] |
| Stack | has-many | StackCapability | aggregates | capabilities [*] |
| ProjectState | has-many | AdapterState | aggregates | adapters [*] |
| ProjectState | has-many | ModuleState | aggregates | modules [*] |
| ProjectState | has-a | OperationRecord | composes | last_operation [1] |
| SystemHealth | has-many | ComponentHealth | aggregates | components [*] |
| MetricsRegistry | has-many | Counter | aggregates | _counters [*] |
| MetricsRegistry | has-many | Gauge | aggregates | _gauges [*] |
| MetricsRegistry | has-many | Histogram | aggregates | _histograms [*] |
| MetricsRegistry | uses | TimerContext | depends |  |
| CircuitBreaker | has-a | CircuitState | composes | state [1] |
| CircuitBreakerRegistry | has-many | CircuitBreaker | aggregates | breakers [*] |
| RetryQueue | has-many | RetryItem | aggregates | _items [*] |
| CargoBuilder | extends | ArtifactBuilder | inherits | ArtifactBuilder |
| DockerBuilder | extends | ArtifactBuilder | inherits | ArtifactBuilder |
| DotnetBuilder | extends | ArtifactBuilder | inherits | ArtifactBuilder |
| GemBuilder | extends | ArtifactBuilder | inherits | ArtifactBuilder |
| GoBuilder | extends | ArtifactBuilder | inherits | ArtifactBuilder |
| GradleBuilder | extends | ArtifactBuilder | inherits | ArtifactBuilder |
| MakefileBuilder | extends | ArtifactBuilder | inherits | ArtifactBuilder |
| MavenBuilder | extends | ArtifactBuilder | inherits | ArtifactBuilder |
| MixBuilder | extends | ArtifactBuilder | inherits | ArtifactBuilder |
| NpmBuilder | extends | ArtifactBuilder | inherits | ArtifactBuilder |
| PipBuilder | extends | ArtifactBuilder | inherits | ArtifactBuilder |
| ScriptBuilder | extends | ArtifactBuilder | inherits | ArtifactBuilder |
| GitHubReleasePublisher | extends | ArtifactPublisher | inherits | ArtifactPublisher |
| NpmPublisher | extends | ArtifactPublisher | inherits | ArtifactPublisher |
| PyPIPublisher | extends | ArtifactPublisher | inherits | ArtifactPublisher |
| AuditScores | has-a | AuditMeta | composes | _meta [1] |
| AuditScores | has-a | ScoreResult | composes | complexity [1] |
| L0Result | has-a | AuditMeta | composes | _meta [1] |
| L0Result | has-many | ManifestInfo | aggregates | manifests [*] |
| L0Result | has-many | ModuleInfo | aggregates | modules [*] |
| L0Result | has-a | OSInfo | composes | os [1] |
| L0Result | has-a | RuntimeInfo | composes | runtime [1] |
| L0Result | has-many | ToolInfo | aggregates | tools [*] |
| L1ClientsResult | has-a | AuditMeta | composes | _meta [1] |
| L1ClientsResult | has-many | ClientInfo | aggregates | clients [*] |
| L1DepsResult | has-a | AuditMeta | composes | _meta [1] |
| L1DepsResult | has-many | CrossoverInfo | aggregates | crossovers [*] |
| L1DepsResult | has-many | DependencyInfo | aggregates | dependencies [*] |
| L1StructResult | has-a | AuditMeta | composes | _meta [1] |
| L1StructResult | has-many | ComponentInfo | aggregates | components [*] |
| L1StructResult | has-many | EntrypointInfo | aggregates | entrypoints [*] |
| ScoreResult | has-many | ScoreBreakdownItem | aggregates | breakdown [*] |
| ParserRegistry | has-many | BaseParser | aggregates | _parsers [*] |
| ParserRegistry | knows | BaseParser | associates | _fallback [0..1] |
| BaseParser | uses | FileAnalysis | depends |  |
| FileAnalysis | has-a | FileMetrics | composes | metrics [1] |
| FileAnalysis | has-many | ImportInfo | aggregates | imports [*] |
| FileAnalysis | has-many | SymbolInfo | aggregates | symbols [*] |
| FileAnalysis | has-many | SymbolLocation | aggregates | symbol_locations [*] |
| FallbackParser | extends | BaseParser | inherits | BaseParser |
| FallbackParser | uses | FileAnalysis | depends |  |
| CFamilyParser | extends | BaseParser | inherits | BaseParser |
| CFamilyParser | uses | FileAnalysis | depends |  |
| ConfigParser | extends | BaseParser | inherits | BaseParser |
| ConfigParser | uses | FileAnalysis | depends |  |
| CSSParser | extends | BaseParser | inherits | BaseParser |
| CSSParser | uses | FileAnalysis | depends |  |
| GoParser | extends | BaseParser | inherits | BaseParser |
| GoParser | uses | FileAnalysis | depends |  |
| JavaScriptParser | extends | BaseParser | inherits | BaseParser |
| JavaScriptParser | uses | FileAnalysis | depends |  |
| JavaScriptParser | uses | FileMetrics | depends |  |
| JVMParser | extends | BaseParser | inherits | BaseParser |
| JVMParser | uses | FileAnalysis | depends |  |
| MultiLangParser | extends | BaseParser | inherits | BaseParser |
| MultiLangParser | uses | FileAnalysis | depends |  |
| PythonParser | extends | BaseParser | inherits | BaseParser |
| PythonParser | uses | FileAnalysis | depends |  |
| RustParser | extends | BaseParser | inherits | BaseParser |
| RustParser | uses | FileAnalysis | depends |  |
| TemplateParser | extends | BaseParser | inherits | BaseParser |
| TemplateParser | uses | FileAnalysis | depends |  |
| Changelog | has-a | ChangelogSection | composes | unreleased [1] |
| Changelog | has-many | ChangelogSection | aggregates | releases [*] |
| ChatMessage | has-a | MessageFlags | composes | flags [1] |
| CssOutlineStrategy | extends | OutlineStrategy | inherits | OutlineStrategy |
| EncryptedOutlineStrategy | extends | OutlineStrategy | inherits | OutlineStrategy |
| FallbackOutlineStrategy | extends | OutlineStrategy | inherits | OutlineStrategy |
| GoOutlineStrategy | extends | OutlineStrategy | inherits | OutlineStrategy |
| HtmlOutlineStrategy | extends | OutlineStrategy | inherits | OutlineStrategy |
| JavaScriptOutlineStrategy | extends | OutlineStrategy | inherits | OutlineStrategy |
| JsonOutlineStrategy | extends | OutlineStrategy | inherits | OutlineStrategy |
| MarkdownOutlineStrategy | extends | OutlineStrategy | inherits | OutlineStrategy |
| PythonOutlineStrategy | extends | OutlineStrategy | inherits | OutlineStrategy |
| RustOutlineStrategy | extends | OutlineStrategy | inherits | OutlineStrategy |
| ShellOutlineStrategy | extends | OutlineStrategy | inherits | OutlineStrategy |
| SqlOutlineStrategy | extends | OutlineStrategy | inherits | OutlineStrategy |
| TomlOutlineStrategy | extends | OutlineStrategy | inherits | OutlineStrategy |
| YamlOutlineStrategy | extends | OutlineStrategy | inherits | OutlineStrategy |
| DetectionResult | has-many | Module | aggregates | modules [*] |
| PipelineScanResult | has-many | DetectedCI | aggregates | ci_workflows [*] |
| PipelineScanResult | has-many | DetectedFramework | aggregates | frameworks [*] |
| PipelineScanResult | has-many | DetectedScript | aggregates | scripts [*] |
| ScopedAuditData | has-a | AuditScope | composes | scope [1] |
| PageBuilder | uses | BuilderInfo | depends |  |
| PipelineResult | has-many | StageResult | aggregates | stages [*] |
| CustomBuilder | uses | BuilderInfo | depends |  |
| CustomBuilder | extends | PageBuilder | inherits | PageBuilder |
| CustomBuilder | knows | SegmentConfig | associates | _segment [0..1] |
| DocusaurusBuilder | uses | BuilderInfo | depends |  |
| DocusaurusBuilder | extends | PageBuilder | inherits | PageBuilder |
| HugoBuilder | uses | BuilderInfo | depends |  |
| HugoBuilder | extends | PageBuilder | inherits | PageBuilder |
| MkDocsBuilder | uses | BuilderInfo | depends |  |
| MkDocsBuilder | extends | PageBuilder | inherits | PageBuilder |
| RawBuilder | uses | BuilderInfo | depends |  |
| RawBuilder | extends | PageBuilder | inherits | PageBuilder |
| SphinxBuilder | uses | BuilderInfo | depends |  |
| SphinxBuilder | extends | PageBuilder | inherits | PageBuilder |
| ScriptMeta | has-many | ScriptParameter | aggregates | parameters [*] |
| SessionTrace | has-many | TraceEvent | aggregates | events [*] |
| ConfigCheckResult | knows | Project | associates | project [0..1] |
| DetectResult | knows | Project | associates | project [0..1] |
| DetectResult | knows | DetectionResult | associates | detection [0..1] |
| RunResult | knows | ExecutionPlan | associates | plan [0..1] |
| RunResult | knows | ExecutionReport | associates | report [0..1] |
| RunResult | knows | Project | associates | project [0..1] |
| StatusResult | knows | Project | associates | project [0..1] |
| StatusResult | knows | ProjectState | associates | state [0..1] |
