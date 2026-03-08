# Class Architecture — Full Project

> Generated: 2026-03-08 03:17 UTC  |  179 classes  |  155 relationships  |  17 modules

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Inheritance Forests](#inheritance-forests)
  - [OutlineStrategy (14 implementations)](#outlinestrategy-14-implementations)
  - [ArtifactBuilder (12 implementations)](#artifactbuilder-12-implementations)
  - [BaseParser (11 implementations)](#baseparser-11-implementations)
  - [Adapter (7 implementations)](#adapter-7-implementations)
  - [PageBuilder (6 implementations)](#pagebuilder-6-implementations)
  - [ArtifactPublisher (3 implementations)](#artifactpublisher-3-implementations)
- [Module Details](#module-details)
  - [core.data (10 classes)](#core.data-10-classes)
  - [core.models (17 classes)](#core.models-17-classes)
  - [core.observability (7 classes)](#core.observability-7-classes)
  - [core.reliability (5 classes)](#core.reliability-5-classes)
  - [core.services (120 classes)](#core.services-120-classes)
  - [core.use_cases (4 classes)](#core.use_cases-4-classes)
  - [Small Modules (16 classes)](#small-modules-16-classes)
- [Hub Analysis](#hub-analysis)
- [Orphan Index](#orphan-index)

---

## Architecture Overview

```mermaid
graph TD

    adapters_base[adapters.base<br/>2 classes]
    adapters_containers[adapters.containers<br/>1 classes]
    adapters_languages[adapters.languages<br/>2 classes]
    adapters_mock[adapters.mock<br/>1 classes]
    adapters_registry[adapters.registry<br/>1 classes]
    adapters_shell[adapters.shell<br/>2 classes]
    adapters_vcs[adapters.vcs<br/>1 classes]
    core_config[core.config<br/>1 classes]
    core_data[core.data<br/>10 classes]
    core_engine[core.engine<br/>2 classes]
    core_models[core.models<br/>17 classes]
    core_observability[core.observability<br/>7 classes]
    core_persistence[core.persistence<br/>2 classes]
    core_reliability[core.reliability<br/>5 classes]
    core_services[core.services<br/>120 classes]
    core_use_cases[core.use_cases<br/>4 classes]
    ui_web[ui.web<br/>1 classes]

    adapters_base --> core_models
    adapters_containers --> adapters_base
    adapters_containers --> core_models
    adapters_languages --> adapters_base
    adapters_languages --> core_models
    adapters_mock --> adapters_base
    adapters_mock --> core_models
    adapters_registry --> adapters_base
    adapters_registry --> core_models
    adapters_shell --> adapters_base
    adapters_shell --> core_models
    adapters_vcs --> adapters_base
    adapters_vcs --> core_models
    core_engine --> core_models
    core_services --> core_models
    core_use_cases --> core_engine
    core_use_cases --> core_models
    core_use_cases --> core_services
```

## Inheritance Forests

> 6 inheritance hierarchies detected. Each shows a base class and its direct implementations.

### OutlineStrategy (14 implementations)

```mermaid
classDiagram
    direction TD

    class CssOutlineStrategy {
    }
    class EncryptedOutlineStrategy {
    }
    class FallbackOutlineStrategy {
    }
    class GoOutlineStrategy {
    }
    class HtmlOutlineStrategy {
    }
    class JavaScriptOutlineStrategy {
    }
    class JsonOutlineStrategy {
    }
    class MarkdownOutlineStrategy {
    }
    class OutlineStrategy {
    }
    class PythonOutlineStrategy {
    }
    class RustOutlineStrategy {
    }
    class ShellOutlineStrategy {
    }
    class SqlOutlineStrategy {
    }
    class TomlOutlineStrategy {
    }
    class YamlOutlineStrategy {
    }

    MarkdownOutlineStrategy --|> OutlineStrategy
    PythonOutlineStrategy --|> OutlineStrategy
    EncryptedOutlineStrategy --|> OutlineStrategy
    JavaScriptOutlineStrategy --|> OutlineStrategy
    GoOutlineStrategy --|> OutlineStrategy
    RustOutlineStrategy --|> OutlineStrategy
    HtmlOutlineStrategy --|> OutlineStrategy
    CssOutlineStrategy --|> OutlineStrategy
    YamlOutlineStrategy --|> OutlineStrategy
    JsonOutlineStrategy --|> OutlineStrategy
    TomlOutlineStrategy --|> OutlineStrategy
    ShellOutlineStrategy --|> OutlineStrategy
    SqlOutlineStrategy --|> OutlineStrategy
    FallbackOutlineStrategy --|> OutlineStrategy
```

### ArtifactBuilder (12 implementations)

```mermaid
classDiagram
    direction TD

    class ArtifactBuilder {
        <<abstract>>
    }
    class CargoBuilder {
    }
    class DockerBuilder {
    }
    class DotnetBuilder {
    }
    class GemBuilder {
    }
    class GoBuilder {
    }
    class GradleBuilder {
    }
    class MakefileBuilder {
    }
    class MavenBuilder {
    }
    class MixBuilder {
    }
    class NpmBuilder {
    }
    class PipBuilder {
    }
    class ScriptBuilder {
    }

    CargoBuilder --|> ArtifactBuilder
    DockerBuilder --|> ArtifactBuilder
    DotnetBuilder --|> ArtifactBuilder
    GemBuilder --|> ArtifactBuilder
    GoBuilder --|> ArtifactBuilder
    GradleBuilder --|> ArtifactBuilder
    MakefileBuilder --|> ArtifactBuilder
    MavenBuilder --|> ArtifactBuilder
    MixBuilder --|> ArtifactBuilder
    NpmBuilder --|> ArtifactBuilder
    PipBuilder --|> ArtifactBuilder
    ScriptBuilder --|> ArtifactBuilder
```

### BaseParser (11 implementations)

```mermaid
classDiagram
    direction TD

    class BaseParser {
        <<abstract>>
    }
    class CFamilyParser {
    }
    class CSSParser {
    }
    class ConfigParser {
    }
    class FallbackParser {
    }
    class GoParser {
    }
    class JVMParser {
    }
    class JavaScriptParser {
    }
    class MultiLangParser {
    }
    class PythonParser {
    }
    class RustParser {
    }
    class TemplateParser {
    }

    FallbackParser --|> BaseParser
    CFamilyParser --|> BaseParser
    ConfigParser --|> BaseParser
    CSSParser --|> BaseParser
    GoParser --|> BaseParser
    JavaScriptParser --|> BaseParser
    JVMParser --|> BaseParser
    MultiLangParser --|> BaseParser
    PythonParser --|> BaseParser
    RustParser --|> BaseParser
    TemplateParser --|> BaseParser
```

### Adapter (7 implementations)

```mermaid
classDiagram
    direction TD

    class Adapter {
        <<abstract>>
    }
    class DockerAdapter {
    }
    class FilesystemAdapter {
    }
    class GitAdapter {
    }
    class MockAdapter {
    }
    class NodeAdapter {
    }
    class PythonAdapter {
    }
    class ShellCommandAdapter {
    }

    DockerAdapter --|> Adapter
    NodeAdapter --|> Adapter
    PythonAdapter --|> Adapter
    MockAdapter --|> Adapter
    ShellCommandAdapter --|> Adapter
    FilesystemAdapter --|> Adapter
    GitAdapter --|> Adapter
```

### PageBuilder (6 implementations)

```mermaid
classDiagram
    direction TD

    class CustomBuilder {
    }
    class DocusaurusBuilder {
    }
    class HugoBuilder {
    }
    class MkDocsBuilder {
    }
    class PageBuilder {
        <<abstract>>
    }
    class RawBuilder {
    }
    class SphinxBuilder {
    }

    CustomBuilder --|> PageBuilder
    DocusaurusBuilder --|> PageBuilder
    HugoBuilder --|> PageBuilder
    MkDocsBuilder --|> PageBuilder
    RawBuilder --|> PageBuilder
    SphinxBuilder --|> PageBuilder
```

### ArtifactPublisher (3 implementations)

```mermaid
classDiagram
    direction TD

    class ArtifactPublisher {
        <<abstract>>
    }
    class GitHubReleasePublisher {
    }
    class NpmPublisher {
    }
    class PyPIPublisher {
    }

    GitHubReleasePublisher --|> ArtifactPublisher
    NpmPublisher --|> ArtifactPublisher
    PyPIPublisher --|> ArtifactPublisher
```

## Module Details

### core.data (10 classes)

```mermaid
classDiagram
    direction TD

    namespace src_core_data {
        class DataRegistry {
            + infra_services() list[dict]
            + infra_categories() dict[str, str]
            + docker_defaults() dict[str, dict]
            + docker_options() dict[str, list]
            + storage_classes() list[dict]
            + k8s_kinds() list[str]
            + card_labels() dict[str, str]
            + iac_providers() dict[str, dict]
            + mesh_annotations() dict[str, dict]
            + terraform_providers() dict[str, dict]
            + terraform_backends() dict[str, str]
            + terraform_k8s() dict[str, dict]
            + sensitive_files() list[list]
            + gitignore_patterns() dict
            + api_spec_files() list[list]
            ... 8 more methods
        }
    }

    namespace src_core_data_script_templates_lib_code_analyzer {
        class ClassInfo {
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
        class FieldInfo {
            <<dataclass>>
            + name: str
            + type_annotation: str
            + is_class_var: bool
            + visibility: str
        }
        class MethodInfo {
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
        class ProjectAnalysis {
            <<dataclass>>
            + classes: list[ClassInfo]
            + files_analyzed: int
            + files_with_errors: int
            + total_classes: int
            + analysis_errors: list[str]
        }
    }

    namespace src_core_data_script_templates_lib_graph_builder {
        class ClassGraph {
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
        class GraphEdge {
            <<dataclass>>
            + source: str
            + target: str
            + relation: RelationType
            + label: str
            + cardinality: str
        }
        class GraphNode {
            <<dataclass>>
            + id: str
            + label: str
            + kind: str
            + package: str
            + fields: list[str]
            + methods: list[str]
            + metadata: dict
        }
        class RelationType {
        }
    }

    namespace src_core_data_script_templates_lib_mermaid_generator {
        class MermaidConfig {
            <<dataclass>>
            + direction: str
            + show_fields: bool
            + show_methods: bool
            + show_visibility: bool
            + max_fields: int
            + max_methods: int
            + group_by_package: bool
            + include_orphans: bool
            + theme: str
        }
    }

    ClassInfo o-- FieldInfo : fields
    ClassInfo o-- MethodInfo : methods
    ProjectAnalysis o-- ClassInfo : classes
    GraphEdge *-- RelationType : relation
    ClassGraph o-- GraphNode : nodes
    ClassGraph o-- GraphEdge : edges
```

### core.models (17 classes)

#### Overview

```mermaid
classDiagram
    direction TD

    namespace src_core_models_action {
        class Action {
        }
        class Receipt {
        }
    }

    namespace src_core_models_module {
        class Module {
        }
        class ModuleHealth {
        }
    }

    namespace src_core_models_project {
        class Environment {
        }
        class ExternalLinks {
        }
        class ModuleRef {
        }
        class Project {
        }
    }

    namespace src_core_models_stack {
        class AdapterRequirement {
        }
        class DetectionRule {
        }
        class Stack {
        }
        class StackCapability {
        }
    }

    namespace src_core_models_state {
        class AdapterState {
        }
        class ModuleState {
        }
        class OperationRecord {
        }
        class ProjectState {
        }
    }

    namespace src_core_models_template {
        class GeneratedFile {
        }
    }

    Module *-- ModuleHealth : health
    Project o-- Environment : environments
    Project o-- ModuleRef : modules
    Project *-- ExternalLinks : external
    Stack o-- AdapterRequirement : requires
    Stack *-- DetectionRule : detection
    Stack o-- StackCapability : capabilities
    ProjectState o-- ModuleState : modules
    ProjectState o-- AdapterState : adapters
    ProjectState *-- OperationRecord : last_operation
```

#### core.models.action (2 classes)

```mermaid
classDiagram
    direction TD

    namespace src_core_models_action {
        class Action {
            + id: str
            + name: str
            + adapter: str
            + capability: str
            + params: dict[str, Any]
            + for_module: str | None
        }
        class Receipt {
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

```

#### core.models.module (2 classes)

```mermaid
classDiagram
    direction TD

    namespace src_core_models_module {
        class Module {
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
        class ModuleHealth {
            + status: str
            + message: str
            + last_checked_at: str | None
        }
    }

    Module *-- ModuleHealth : health
```

#### core.models.project (4 classes)

```mermaid
classDiagram
    direction TD

    namespace src_core_models_project {
        class Environment {
            + name: str
            + description: str
            + default: bool
        }
        class ExternalLinks {
            + ci: str | None
            + registry: str | None
            + monitoring: str | None
            + extra: dict[str, str]
        }
        class ModuleRef {
            + name: str
            + path: str
            + domain: str
            + stack: str
            + description: str
        }
        class Project {
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

    Project o-- Environment : environments
    Project o-- ModuleRef : modules
    Project *-- ExternalLinks : external
```

#### core.models.stack (4 classes)

```mermaid
classDiagram
    direction TD

    namespace src_core_models_stack {
        class AdapterRequirement {
            + adapter: str
            + min_version: str
        }
        class DetectionRule {
            + files_any_of: list[str]
            + files_all_of: list[str]
            + content_contains: dict[str, str]
        }
        class Stack {
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
        class StackCapability {
            + name: str
            + adapter: str
            + command: str
            + description: str
        }
    }

    Stack o-- AdapterRequirement : requires
    Stack *-- DetectionRule : detection
    Stack o-- StackCapability : capabilities
```

#### core.models.state (4 classes)

```mermaid
classDiagram
    direction TD

    namespace src_core_models_state {
        class AdapterState {
            + name: str
            + available: bool
            + version: str | None
            + last_used_at: str | None
            + failure_count: int
            + circuit_state: str
        }
        class ModuleState {
            + name: str
            + detected: bool
            + stack: str
            + version: str | None
            + last_action_at: str | None
            + last_action_status: str | None
        }
        class OperationRecord {
            + operation_id: str
            + automation: str
            + started_at: str
            + ended_at: str
            + status: str
            + actions_total: int
            + actions_succeeded: int
            + actions_failed: int
        }
        class ProjectState {
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

    ProjectState o-- ModuleState : modules
    ProjectState o-- AdapterState : adapters
    ProjectState *-- OperationRecord : last_operation
```

#### core.models.template (1 classes)

```mermaid
classDiagram
    direction TD

    namespace src_core_models_template {
        class GeneratedFile {
            + path: str
            + content: str
            + overwrite: bool
            + reason: str
        }
    }

```

### core.observability (7 classes)

```mermaid
classDiagram
    direction TD

    namespace src_core_observability_health {
        class ComponentHealth {
            <<dataclass>>
            + name: str
            + status: str
            + message: str
            + details: dict[str, Any]
            + to_dict() dict[str, Any]
        }
        class SystemHealth {
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
        class Counter {
            <<dataclass>>
            + name: str
            + value: int
            + labels: dict[str, str]
            + inc(n) None
            + to_dict() dict[str, Any]
        }
        class Gauge {
            <<dataclass>>
            + name: str
            + value: float
            + labels: dict[str, str]
            + set(v) None
            + inc(n) None
            + dec(n) None
            + to_dict() dict[str, Any]
        }
        class Histogram {
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
        class MetricsRegistry {
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
        class TimerContext {
            # _histogram: Any
            # _start: float
            # __init__(histogram)
            # __enter__() TimerContext
            # __exit__() None
        }
    }

    SystemHealth o-- ComponentHealth : components
    MetricsRegistry o-- Counter : _counters
    MetricsRegistry o-- Gauge : _gauges
    MetricsRegistry o-- Histogram : _histograms
    MetricsRegistry ..> TimerContext
```

### core.reliability (5 classes)

```mermaid
classDiagram
    direction TD

    namespace src_core_reliability_circuit_breaker {
        class CircuitBreaker {
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
        class CircuitBreakerRegistry {
            <<dataclass>>
            + breakers: dict[str, CircuitBreaker]
            + default_threshold: int
            + default_timeout: float
            + get_or_create(name) CircuitBreaker
            + get_status() dict[str, dict[str, Any]]
            + reset_all() None
        }
        class CircuitState {
        }
    }

    namespace src_core_reliability_retry_queue {
        class RetryItem {
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
        class RetryQueue {
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

    CircuitBreaker *-- CircuitState : state
    CircuitBreakerRegistry o-- CircuitBreaker : breakers
    RetryQueue o-- RetryItem : _items
```

### core.services (120 classes)

#### Overview

```mermaid
classDiagram
    direction TD

    namespace src_core_services_artifacts_builders_base {
        class ArtifactBuilder {
            <<abstract>>
        }
        class ArtifactStageInfo {
            <<dataclass>>
        }
    }

    namespace src_core_services_artifacts_builders_cargo {
        class CargoBuilder {
        }
    }

    namespace src_core_services_artifacts_builders_docker {
        class DockerBuilder {
        }
    }

    namespace src_core_services_artifacts_builders_dotnet {
        class DotnetBuilder {
        }
    }

    namespace src_core_services_artifacts_builders_gem {
        class GemBuilder {
        }
    }

    namespace src_core_services_artifacts_builders_go {
        class GoBuilder {
        }
    }

    namespace src_core_services_artifacts_builders_gradle {
        class GradleBuilder {
        }
    }

    namespace src_core_services_artifacts_builders_makefile {
        class MakefileBuilder {
        }
    }

    namespace src_core_services_artifacts_builders_maven {
        class MavenBuilder {
        }
    }

    namespace src_core_services_artifacts_builders_mix {
        class MixBuilder {
        }
    }

    namespace src_core_services_artifacts_builders_npm {
        class NpmBuilder {
        }
    }

    namespace src_core_services_artifacts_builders_pip_builder {
        class PipBuilder {
        }
    }

    namespace src_core_services_artifacts_builders_script {
        class ScriptBuilder {
        }
    }

    namespace src_core_services_artifacts_engine {
        class ArtifactBuildResult {
            <<dataclass>>
        }
        class ArtifactTarget {
            <<dataclass>>
        }
    }

    namespace src_core_services_artifacts_publishers_base {
        class ArtifactPublishResult {
            <<dataclass>>
        }
        class ArtifactPublisher {
            <<abstract>>
        }
    }

    namespace src_core_services_artifacts_publishers_github_release {
        class GitHubReleasePublisher {
        }
    }

    namespace src_core_services_artifacts_publishers_npm_publisher {
        class NpmPublisher {
        }
    }

    namespace src_core_services_artifacts_publishers_pypi {
        class PyPIPublisher {
        }
    }

    namespace src_core_services_audit_catalog {
        class LibraryInfo {
        }
    }

    namespace src_core_services_audit_models {
        class AuditMeta {
        }
        class AuditScores {
        }
        class ClientInfo {
        }
        class ComponentInfo {
        }
        class CrossoverInfo {
        }
        class DependencyInfo {
        }
        class EntrypointInfo {
        }
        class L0Result {
        }
        class L1ClientsResult {
        }
        class L1DepsResult {
        }
        class L1StructResult {
        }
        class ManifestInfo {
        }
        class ModuleInfo {
        }
        class OSInfo {
        }
        class RuntimeInfo {
        }
        class ScoreBreakdownItem {
        }
        class ScoreResult {
        }
        class ToolInfo {
        }
    }

    namespace src_core_services_audit_narrative {
        class Observation {
            <<dataclass>>
        }
        class Recommendation {
            <<dataclass>>
        }
    }

    namespace src_core_services_audit_parsers {
        class ParserRegistry {
        }
    }

    namespace src_core_services_audit_parsers__base {
        class BaseParser {
            <<abstract>>
        }
        class FileAnalysis {
            <<dataclass>>
        }
        class FileMetrics {
            <<dataclass>>
        }
        class ImportInfo {
            <<dataclass>>
        }
        class SymbolInfo {
            <<dataclass>>
        }
        class SymbolLocation {
            <<dataclass>>
        }
    }

    namespace src_core_services_audit_parsers__fallback {
        class FallbackParser {
        }
    }

    namespace src_core_services_audit_parsers__rubrics {
        class QualityDimension {
            <<dataclass>>
        }
    }

    namespace src_core_services_audit_parsers_c_parser {
        class CFamilyParser {
        }
    }

    namespace src_core_services_audit_parsers_config_parser {
        class ConfigParser {
        }
    }

    namespace src_core_services_audit_parsers_css_parser {
        class CSSParser {
        }
    }

    namespace src_core_services_audit_parsers_go_parser {
        class GoParser {
        }
    }

    namespace src_core_services_audit_parsers_js_parser {
        class JavaScriptParser {
        }
    }

    namespace src_core_services_audit_parsers_jvm_parser {
        class JVMParser {
        }
    }

    namespace src_core_services_audit_parsers_multilang_parser {
        class MultiLangParser {
        }
    }

    namespace src_core_services_audit_parsers_python_parser {
        class PythonParser {
        }
    }

    namespace src_core_services_audit_parsers_rust_parser {
        class RustParser {
        }
    }

    namespace src_core_services_audit_parsers_template_parser {
        class TemplateParser {
        }
    }

    namespace src_core_services_changelog_models {
        class CCMessage {
            <<dataclass>>
        }
        class Changelog {
            <<dataclass>>
        }
        class ChangelogEntry {
            <<dataclass>>
        }
        class ChangelogSection {
            <<dataclass>>
        }
    }

    namespace src_core_services_chat_models {
        class ChatMessage {
        }
        class MessageFlags {
        }
        class Thread {
        }
    }

    namespace src_core_services_content_outline {
        class CssOutlineStrategy {
        }
        class EncryptedOutlineStrategy {
        }
        class FallbackOutlineStrategy {
        }
        class GoOutlineStrategy {
        }
        class HtmlOutlineStrategy {
        }
        class JavaScriptOutlineStrategy {
        }
        class JsonOutlineStrategy {
        }
        class MarkdownOutlineStrategy {
        }
        class OutlineStrategy {
        }
        class PythonOutlineStrategy {
        }
        class RustOutlineStrategy {
        }
        class ShellOutlineStrategy {
        }
        class SqlOutlineStrategy {
        }
        class TomlOutlineStrategy {
        }
        class YamlOutlineStrategy {
        }
    }

    namespace src_core_services_detection {
        class DetectionResult {
            <<dataclass>>
        }
    }

    namespace src_core_services_event_bus {
        class EventBus {
        }
    }

    namespace src_core_services_ledger_models {
        class Run {
        }
        class RunEvent {
        }
    }

    namespace src_core_services_ledger_worktree {
        class GitIdentityError {
        }
    }

    namespace src_core_services_pages_pipeline_scanner {
        class DetectedCI {
            <<dataclass>>
        }
        class DetectedFramework {
            <<dataclass>>
        }
        class DetectedScript {
            <<dataclass>>
        }
        class PipelineScanResult {
            <<dataclass>>
        }
    }

    namespace src_core_services_pages_builders_audit_directive {
        class AuditDataBundle {
            <<dataclass>>
        }
        class AuditScope {
            <<dataclass>>
        }
        class DirectiveMatch {
            <<dataclass>>
        }
        class ScopedAuditData {
            <<dataclass>>
        }
    }

    namespace src_core_services_pages_builders_base {
        class BuildResult {
            <<dataclass>>
        }
        class BuilderInfo {
            <<dataclass>>
        }
        class ConfigField {
            <<dataclass>>
        }
        class PageBuilder {
            <<abstract>>
        }
        class PipelineResult {
            <<dataclass>>
        }
        class SegmentConfig {
            <<dataclass>>
        }
        class StageInfo {
            <<dataclass>>
        }
        class StageResult {
            <<dataclass>>
        }
    }

    namespace src_core_services_pages_builders_custom {
        class CustomBuilder {
        }
    }

    namespace src_core_services_pages_builders_docusaurus {
        class DocusaurusBuilder {
        }
    }

    namespace src_core_services_pages_builders_hugo {
        class HugoBuilder {
        }
    }

    namespace src_core_services_pages_builders_mkdocs {
        class MkDocsBuilder {
        }
    }

    namespace src_core_services_pages_builders_raw {
        class RawBuilder {
        }
    }

    namespace src_core_services_pages_builders_sphinx {
        class SphinxBuilder {
        }
    }

    namespace src_core_services_peek {
        class PeekCandidate {
            <<dataclass>>
        }
        class PeekReference {
            <<dataclass>>
        }
        class SymbolEntry {
            <<dataclass>>
        }
    }

    namespace src_core_services_project_index {
        class IndexSymbolEntry {
            <<dataclass>>
        }
        class ProjectIndex {
            <<dataclass>>
        }
    }

    namespace src_core_services_scripts_models {
        class ScriptConfig {
            <<dataclass>>
        }
        class ScriptMeta {
            <<dataclass>>
        }
        class ScriptParameter {
            <<dataclass>>
        }
    }

    namespace src_core_services_trace_models {
        class SessionTrace {
        }
        class TraceEvent {
        }
    }

    CargoBuilder --|> ArtifactBuilder
    DockerBuilder --|> ArtifactBuilder
    DotnetBuilder --|> ArtifactBuilder
    GemBuilder --|> ArtifactBuilder
    GoBuilder --|> ArtifactBuilder
    GradleBuilder --|> ArtifactBuilder
    MakefileBuilder --|> ArtifactBuilder
    MavenBuilder --|> ArtifactBuilder
    MixBuilder --|> ArtifactBuilder
    NpmBuilder --|> ArtifactBuilder
    PipBuilder --|> ArtifactBuilder
    ScriptBuilder --|> ArtifactBuilder
    GitHubReleasePublisher --|> ArtifactPublisher
    NpmPublisher --|> ArtifactPublisher
    PyPIPublisher --|> ArtifactPublisher
    FallbackParser --|> BaseParser
    CFamilyParser --|> BaseParser
    ConfigParser --|> BaseParser
    CSSParser --|> BaseParser
    GoParser --|> BaseParser
    JavaScriptParser --|> BaseParser
    JVMParser --|> BaseParser
    MultiLangParser --|> BaseParser
    PythonParser --|> BaseParser
    RustParser --|> BaseParser
    TemplateParser --|> BaseParser
    MarkdownOutlineStrategy --|> OutlineStrategy
    PythonOutlineStrategy --|> OutlineStrategy
    EncryptedOutlineStrategy --|> OutlineStrategy
    JavaScriptOutlineStrategy --|> OutlineStrategy
    GoOutlineStrategy --|> OutlineStrategy
    RustOutlineStrategy --|> OutlineStrategy
    HtmlOutlineStrategy --|> OutlineStrategy
    CssOutlineStrategy --|> OutlineStrategy
    YamlOutlineStrategy --|> OutlineStrategy
    JsonOutlineStrategy --|> OutlineStrategy
    TomlOutlineStrategy --|> OutlineStrategy
    ShellOutlineStrategy --|> OutlineStrategy
    SqlOutlineStrategy --|> OutlineStrategy
    FallbackOutlineStrategy --|> OutlineStrategy
    CustomBuilder --|> PageBuilder
    DocusaurusBuilder --|> PageBuilder
    HugoBuilder --|> PageBuilder
    MkDocsBuilder --|> PageBuilder
    RawBuilder --|> PageBuilder
    SphinxBuilder --|> PageBuilder
    L0Result *-- AuditMeta : _meta
    L0Result *-- OSInfo : os
    L0Result *-- RuntimeInfo : runtime
    L0Result o-- ToolInfo : tools
    L0Result o-- ModuleInfo : modules
    L0Result o-- ManifestInfo : manifests
    L1DepsResult *-- AuditMeta : _meta
    L1DepsResult o-- DependencyInfo : dependencies
    L1DepsResult o-- CrossoverInfo : crossovers
    L1StructResult *-- AuditMeta : _meta
    L1StructResult o-- ComponentInfo : components
    L1StructResult o-- EntrypointInfo : entrypoints
    L1ClientsResult *-- AuditMeta : _meta
    L1ClientsResult o-- ClientInfo : clients
    ScoreResult o-- ScoreBreakdownItem : breakdown
    AuditScores *-- AuditMeta : _meta
    AuditScores *-- ScoreResult : complexity
    ParserRegistry o-- BaseParser : _parsers
    ParserRegistry --> BaseParser : _fallback
    FileAnalysis o-- ImportInfo : imports
    FileAnalysis o-- SymbolInfo : symbols
    FileAnalysis *-- FileMetrics : metrics
    FileAnalysis o-- SymbolLocation : symbol_locations
    Changelog *-- ChangelogSection : unreleased
    Changelog o-- ChangelogSection : releases
    ChatMessage *-- MessageFlags : flags
    PipelineScanResult o-- DetectedScript : scripts
    PipelineScanResult o-- DetectedFramework : frameworks
    PipelineScanResult o-- DetectedCI : ci_workflows
    ScopedAuditData *-- AuditScope : scope
    PipelineResult o-- StageResult : stages
    CustomBuilder --> SegmentConfig : _segment
    ScriptMeta o-- ScriptParameter : parameters
    SessionTrace o-- TraceEvent : events
    BaseParser ..> FileAnalysis
    FallbackParser ..> FileAnalysis
    CFamilyParser ..> FileAnalysis
    ConfigParser ..> FileAnalysis
    CSSParser ..> FileAnalysis
    GoParser ..> FileAnalysis
    JavaScriptParser ..> FileAnalysis
    JavaScriptParser ..> FileMetrics
    JVMParser ..> FileAnalysis
    MultiLangParser ..> FileAnalysis
    PythonParser ..> FileAnalysis
    RustParser ..> FileAnalysis
    TemplateParser ..> FileAnalysis
    PageBuilder ..> BuilderInfo
    CustomBuilder ..> BuilderInfo
    DocusaurusBuilder ..> BuilderInfo
    HugoBuilder ..> BuilderInfo
    MkDocsBuilder ..> BuilderInfo
    RawBuilder ..> BuilderInfo
    SphinxBuilder ..> BuilderInfo
```

#### core.services.artifacts (21 classes)

##### Overview

```mermaid
classDiagram
    direction TD

    namespace src_core_services_artifacts_builders_base {
        class ArtifactBuilder {
            <<abstract>>
        }
        class ArtifactStageInfo {
            <<dataclass>>
        }
    }

    namespace src_core_services_artifacts_builders_cargo {
        class CargoBuilder {
        }
    }

    namespace src_core_services_artifacts_builders_docker {
        class DockerBuilder {
        }
    }

    namespace src_core_services_artifacts_builders_dotnet {
        class DotnetBuilder {
        }
    }

    namespace src_core_services_artifacts_builders_gem {
        class GemBuilder {
        }
    }

    namespace src_core_services_artifacts_builders_go {
        class GoBuilder {
        }
    }

    namespace src_core_services_artifacts_builders_gradle {
        class GradleBuilder {
        }
    }

    namespace src_core_services_artifacts_builders_makefile {
        class MakefileBuilder {
        }
    }

    namespace src_core_services_artifacts_builders_maven {
        class MavenBuilder {
        }
    }

    namespace src_core_services_artifacts_builders_mix {
        class MixBuilder {
        }
    }

    namespace src_core_services_artifacts_builders_npm {
        class NpmBuilder {
        }
    }

    namespace src_core_services_artifacts_builders_pip_builder {
        class PipBuilder {
        }
    }

    namespace src_core_services_artifacts_builders_script {
        class ScriptBuilder {
        }
    }

    namespace src_core_services_artifacts_engine {
        class ArtifactBuildResult {
            <<dataclass>>
        }
        class ArtifactTarget {
            <<dataclass>>
        }
    }

    namespace src_core_services_artifacts_publishers_base {
        class ArtifactPublishResult {
            <<dataclass>>
        }
        class ArtifactPublisher {
            <<abstract>>
        }
    }

    namespace src_core_services_artifacts_publishers_github_release {
        class GitHubReleasePublisher {
        }
    }

    namespace src_core_services_artifacts_publishers_npm_publisher {
        class NpmPublisher {
        }
    }

    namespace src_core_services_artifacts_publishers_pypi {
        class PyPIPublisher {
        }
    }

    CargoBuilder --|> ArtifactBuilder
    DockerBuilder --|> ArtifactBuilder
    DotnetBuilder --|> ArtifactBuilder
    GemBuilder --|> ArtifactBuilder
    GoBuilder --|> ArtifactBuilder
    GradleBuilder --|> ArtifactBuilder
    MakefileBuilder --|> ArtifactBuilder
    MavenBuilder --|> ArtifactBuilder
    MixBuilder --|> ArtifactBuilder
    NpmBuilder --|> ArtifactBuilder
    PipBuilder --|> ArtifactBuilder
    ScriptBuilder --|> ArtifactBuilder
    GitHubReleasePublisher --|> ArtifactPublisher
    NpmPublisher --|> ArtifactPublisher
    PyPIPublisher --|> ArtifactPublisher
```

#### core.services.audit (40 classes)

##### Overview

```mermaid
classDiagram
    direction TD

    namespace src_core_services_audit_catalog {
        class LibraryInfo {
        }
    }

    namespace src_core_services_audit_models {
        class AuditMeta {
        }
        class AuditScores {
        }
        class ClientInfo {
        }
        class ComponentInfo {
        }
        class CrossoverInfo {
        }
        class DependencyInfo {
        }
        class EntrypointInfo {
        }
        class L0Result {
        }
        class L1ClientsResult {
        }
        class L1DepsResult {
        }
        class L1StructResult {
        }
        class ManifestInfo {
        }
        class ModuleInfo {
        }
        class OSInfo {
        }
        class RuntimeInfo {
        }
        class ScoreBreakdownItem {
        }
        class ScoreResult {
        }
        class ToolInfo {
        }
    }

    namespace src_core_services_audit_narrative {
        class Observation {
            <<dataclass>>
        }
        class Recommendation {
            <<dataclass>>
        }
    }

    namespace src_core_services_audit_parsers {
        class ParserRegistry {
        }
    }

    namespace src_core_services_audit_parsers__base {
        class BaseParser {
            <<abstract>>
        }
        class FileAnalysis {
            <<dataclass>>
        }
        class FileMetrics {
            <<dataclass>>
        }
        class ImportInfo {
            <<dataclass>>
        }
        class SymbolInfo {
            <<dataclass>>
        }
        class SymbolLocation {
            <<dataclass>>
        }
    }

    namespace src_core_services_audit_parsers__fallback {
        class FallbackParser {
        }
    }

    namespace src_core_services_audit_parsers__rubrics {
        class QualityDimension {
            <<dataclass>>
        }
    }

    namespace src_core_services_audit_parsers_c_parser {
        class CFamilyParser {
        }
    }

    namespace src_core_services_audit_parsers_config_parser {
        class ConfigParser {
        }
    }

    namespace src_core_services_audit_parsers_css_parser {
        class CSSParser {
        }
    }

    namespace src_core_services_audit_parsers_go_parser {
        class GoParser {
        }
    }

    namespace src_core_services_audit_parsers_js_parser {
        class JavaScriptParser {
        }
    }

    namespace src_core_services_audit_parsers_jvm_parser {
        class JVMParser {
        }
    }

    namespace src_core_services_audit_parsers_multilang_parser {
        class MultiLangParser {
        }
    }

    namespace src_core_services_audit_parsers_python_parser {
        class PythonParser {
        }
    }

    namespace src_core_services_audit_parsers_rust_parser {
        class RustParser {
        }
    }

    namespace src_core_services_audit_parsers_template_parser {
        class TemplateParser {
        }
    }

    FallbackParser --|> BaseParser
    CFamilyParser --|> BaseParser
    ConfigParser --|> BaseParser
    CSSParser --|> BaseParser
    GoParser --|> BaseParser
    JavaScriptParser --|> BaseParser
    JVMParser --|> BaseParser
    MultiLangParser --|> BaseParser
    PythonParser --|> BaseParser
    RustParser --|> BaseParser
    TemplateParser --|> BaseParser
    L0Result *-- AuditMeta : _meta
    L0Result *-- OSInfo : os
    L0Result *-- RuntimeInfo : runtime
    L0Result o-- ToolInfo : tools
    L0Result o-- ModuleInfo : modules
    L0Result o-- ManifestInfo : manifests
    L1DepsResult *-- AuditMeta : _meta
    L1DepsResult o-- DependencyInfo : dependencies
    L1DepsResult o-- CrossoverInfo : crossovers
    L1StructResult *-- AuditMeta : _meta
    L1StructResult o-- ComponentInfo : components
    L1StructResult o-- EntrypointInfo : entrypoints
    L1ClientsResult *-- AuditMeta : _meta
    L1ClientsResult o-- ClientInfo : clients
    ScoreResult o-- ScoreBreakdownItem : breakdown
    AuditScores *-- AuditMeta : _meta
    AuditScores *-- ScoreResult : complexity
    ParserRegistry o-- BaseParser : _parsers
    ParserRegistry --> BaseParser : _fallback
    FileAnalysis o-- ImportInfo : imports
    FileAnalysis o-- SymbolInfo : symbols
    FileAnalysis *-- FileMetrics : metrics
    FileAnalysis o-- SymbolLocation : symbol_locations
    BaseParser ..> FileAnalysis
    FallbackParser ..> FileAnalysis
    CFamilyParser ..> FileAnalysis
    ConfigParser ..> FileAnalysis
    CSSParser ..> FileAnalysis
    GoParser ..> FileAnalysis
    JavaScriptParser ..> FileAnalysis
    JavaScriptParser ..> FileMetrics
    JVMParser ..> FileAnalysis
    MultiLangParser ..> FileAnalysis
    PythonParser ..> FileAnalysis
    RustParser ..> FileAnalysis
    TemplateParser ..> FileAnalysis
```

#### core.services.changelog (4 classes)

```mermaid
classDiagram
    direction TD

    namespace src_core_services_changelog_models {
        class CCMessage {
            <<dataclass>>
            + type: str
            + scope: str
            + description: str
            + body: str
            + breaking: bool
            + breaking_note: str
            + footers: dict[str, str]
            + raw: str
            + header() str
            + full_message() str
        }
        class Changelog {
            <<dataclass>>
            + header: str
            + unreleased: ChangelogSection
            + releases: list[ChangelogSection]
            + all_sections() list[ChangelogSection]
            + latest_version() str | None
        }
        class ChangelogEntry {
            <<dataclass>>
            + text: str
            + breaking: bool
            + scope: str
            + section_key: str
        }
        class ChangelogSection {
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

    Changelog *-- ChangelogSection : unreleased
    Changelog o-- ChangelogSection : releases
```

#### core.services.chat (3 classes)

```mermaid
classDiagram
    direction TD

    namespace src_core_services_chat_models {
        class ChatMessage {
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
        class MessageFlags {
            + publish: bool
            + encrypted: bool
        }
        class Thread {
            + thread_id: str
            + title: str
            + created_at: str
            + created_by: str
            + anchor_run: str | None
            + tags: list[str]
            + ensure_id() str
        }
    }

    ChatMessage *-- MessageFlags : flags
```

#### core.services.content (15 classes)

```mermaid
classDiagram
    direction TD

    namespace src_core_services_content_outline {
        class CssOutlineStrategy {
            + extract(source, file_path) list[dict]
        }
        class EncryptedOutlineStrategy {
            + extract(source, file_path) list[dict]
        }
        class FallbackOutlineStrategy {
            + extract(source, file_path) list[dict]
        }
        class GoOutlineStrategy {
            + extract(source, file_path) list[dict]
        }
        class HtmlOutlineStrategy {
            + extract(source, file_path) list[dict]
        }
        class JavaScriptOutlineStrategy {
            + extract(source, file_path) list[dict]
        }
        class JsonOutlineStrategy {
            + extract(source, file_path) list[dict]
            # _find_key_line(lines, key, found) int
        }
        class MarkdownOutlineStrategy {
            + extract(source, file_path) list[dict]
        }
        class OutlineStrategy {
            + extensions: set[str]
            + extract(source, file_path) list[dict]
        }
        class PythonOutlineStrategy {
            + extract(source, file_path) list[dict]
        }
        class RustOutlineStrategy {
            + extract(source, file_path) list[dict]
        }
        class ShellOutlineStrategy {
            + extract(source, file_path) list[dict]
        }
        class SqlOutlineStrategy {
            + extract(source, file_path) list[dict]
        }
        class TomlOutlineStrategy {
            + extract(source, file_path) list[dict]
        }
        class YamlOutlineStrategy {
            + extract(source, file_path) list[dict]
        }
    }

    MarkdownOutlineStrategy --|> OutlineStrategy
    PythonOutlineStrategy --|> OutlineStrategy
    EncryptedOutlineStrategy --|> OutlineStrategy
    JavaScriptOutlineStrategy --|> OutlineStrategy
    GoOutlineStrategy --|> OutlineStrategy
    RustOutlineStrategy --|> OutlineStrategy
    HtmlOutlineStrategy --|> OutlineStrategy
    CssOutlineStrategy --|> OutlineStrategy
    YamlOutlineStrategy --|> OutlineStrategy
    JsonOutlineStrategy --|> OutlineStrategy
    TomlOutlineStrategy --|> OutlineStrategy
    ShellOutlineStrategy --|> OutlineStrategy
    SqlOutlineStrategy --|> OutlineStrategy
    FallbackOutlineStrategy --|> OutlineStrategy
```

#### core.services.detection (1 classes)

```mermaid
classDiagram
    direction TD

    namespace src_core_services_detection {
        class DetectionResult {
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

```

#### core.services.event_bus (1 classes)

```mermaid
classDiagram
    direction TD

    namespace src_core_services_event_bus {
        class EventBus {
            # _lock: Any
            # _seq: int
            # _buffer: deque[dict]
            # _subscribers: list[queue.Queue[dict]]
            # _subscriber_queue_size: Any
            # _instance_id: str
            # _latest: dict[str, dict]
            # __init__() None
            + instance_id() str
            + seq() int
            + subscriber_count() int
            + add_listener(q) None
            + remove_listener(q) None
            + publish(event_type) dict
            + subscribe() Generator[dict, None, None]
            + snapshot() dict[str, dict]
            # _make_ready_event() dict
            # _make_snapshot_event() dict
        }
    }

```

#### core.services.ledger (3 classes)

```mermaid
classDiagram
    direction TD

    namespace src_core_services_ledger_models {
        class Run {
            + run_id: str
            + type: str
            + subtype: str
            + status: Literal['ok', 'failed', 'partial']
            + user: str
            + code_ref: str
            + started_at: str
            + ended_at: str
            + duration_ms: int
            + environment: str
            ... 3 more fields
            + ensure_id() str
            + to_tag_message() str
            + from_tag_message(message) Run
        }
        class RunEvent {
            + seq: int
            + ts: str
            + type: str
            + adapter: str
            + action_id: str
            + target: str
            + status: str
            + duration_ms: int
            + detail: dict[str, Any]
        }
    }

    namespace src_core_services_ledger_worktree {
        class GitIdentityError {
        }
    }

```

#### core.services.pages (4 classes)

```mermaid
classDiagram
    direction TD

    namespace src_core_services_pages_pipeline_scanner {
        class DetectedCI {
            <<dataclass>>
            + path: str
            + name: str
            + provider: str
            + build_script: str
            + env_vars: dict
            + deploy_target: str
        }
        class DetectedFramework {
            <<dataclass>>
            + name: str
            + config_path: str
            + output_dir: str
            + build_cmd: str
            + preview_cmd: str
            + preview_port: int
            + version: str
        }
        class DetectedScript {
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
        class PipelineScanResult {
            <<dataclass>>
            + scripts: list[DetectedScript]
            + frameworks: list[DetectedFramework]
            + ci_workflows: list[DetectedCI]
            + suggested_config: dict
            + compatibility: str
            + compatibility_notes: list[str]
        }
    }

    PipelineScanResult o-- DetectedScript : scripts
    PipelineScanResult o-- DetectedFramework : frameworks
    PipelineScanResult o-- DetectedCI : ci_workflows
```

#### core.services.pages_builders (18 classes)

##### Overview

```mermaid
classDiagram
    direction TD

    namespace src_core_services_pages_builders_audit_directive {
        class AuditDataBundle {
            <<dataclass>>
        }
        class AuditScope {
            <<dataclass>>
        }
        class DirectiveMatch {
            <<dataclass>>
        }
        class ScopedAuditData {
            <<dataclass>>
        }
    }

    namespace src_core_services_pages_builders_base {
        class BuildResult {
            <<dataclass>>
        }
        class BuilderInfo {
            <<dataclass>>
        }
        class ConfigField {
            <<dataclass>>
        }
        class PageBuilder {
            <<abstract>>
        }
        class PipelineResult {
            <<dataclass>>
        }
        class SegmentConfig {
            <<dataclass>>
        }
        class StageInfo {
            <<dataclass>>
        }
        class StageResult {
            <<dataclass>>
        }
    }

    namespace src_core_services_pages_builders_custom {
        class CustomBuilder {
        }
    }

    namespace src_core_services_pages_builders_docusaurus {
        class DocusaurusBuilder {
        }
    }

    namespace src_core_services_pages_builders_hugo {
        class HugoBuilder {
        }
    }

    namespace src_core_services_pages_builders_mkdocs {
        class MkDocsBuilder {
        }
    }

    namespace src_core_services_pages_builders_raw {
        class RawBuilder {
        }
    }

    namespace src_core_services_pages_builders_sphinx {
        class SphinxBuilder {
        }
    }

    CustomBuilder --|> PageBuilder
    DocusaurusBuilder --|> PageBuilder
    HugoBuilder --|> PageBuilder
    MkDocsBuilder --|> PageBuilder
    RawBuilder --|> PageBuilder
    SphinxBuilder --|> PageBuilder
    ScopedAuditData *-- AuditScope : scope
    PipelineResult o-- StageResult : stages
    CustomBuilder --> SegmentConfig : _segment
    PageBuilder ..> BuilderInfo
    CustomBuilder ..> BuilderInfo
    DocusaurusBuilder ..> BuilderInfo
    HugoBuilder ..> BuilderInfo
    MkDocsBuilder ..> BuilderInfo
    RawBuilder ..> BuilderInfo
    SphinxBuilder ..> BuilderInfo
```

#### core.services.peek (3 classes)

```mermaid
classDiagram
    direction TD

    namespace src_core_services_peek {
        class PeekCandidate {
            <<dataclass>>
            + text: str
            + type: str
            + candidate_path: str
            + line_number: int | None
            + in_code_fence: bool
        }
        class PeekReference {
            <<dataclass>>
            + text: str
            + type: str
            + resolved_path: str
            + line_number: int | None
            + is_directory: bool
        }
        class SymbolEntry {
            <<dataclass>>
            + name: str
            + file: str
            + line: int
            + kind: str
        }
    }

```

#### core.services.project_index (2 classes)

```mermaid
classDiagram
    direction TD

    namespace src_core_services_project_index {
        class IndexSymbolEntry {
            <<dataclass>>
            + name: str
            + file: str
            + line: int
            + kind: str
        }
        class ProjectIndex {
            <<dataclass>>
            + file_map: dict[str, list[str]]
            + dir_map: dict[str, list[str]]
            + all_paths: set[str]
            + symbol_map: dict[str, list[IndexSymbolEntry]]
            + peek_cache: dict[str, dict[str, list[dict]]]
            + ready: bool
            + symbols_ready: bool
            + peek_cached: bool
            + building: bool
            + last_built: float
            ... 6 more fields
        }
    }

```

#### core.services.scripts (3 classes)

```mermaid
classDiagram
    direction TD

    namespace src_core_services_scripts_models {
        class ScriptConfig {
            <<dataclass>>
            + root: str
            + template_source: str
            + default_output: str
            + history_max_runs: int
            + history_persist_output: bool
            + execution_default_timeout: int
            + execution_parallel: bool
            + execution_venv_python: str
            + categories: list[str]
        }
        class ScriptMeta {
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
        class ScriptParameter {
            <<dataclass>>
            + name: str
            + type: str
            + description: str
            + required: bool
            + default: str
            + choices: list[str]
        }
    }

    ScriptMeta o-- ScriptParameter : parameters
```

#### core.services.trace (2 classes)

```mermaid
classDiagram
    direction TD

    namespace src_core_services_trace_models {
        class SessionTrace {
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
        class TraceEvent {
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

    SessionTrace o-- TraceEvent : events
```

### core.use_cases (4 classes)

```mermaid
classDiagram
    direction TD

    namespace src_core_use_cases_config_check {
        class ConfigCheckResult {
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
        class DetectResult {
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
        class RunResult {
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
        class StatusResult {
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

```

### Small Modules (16 classes)

> Modules: adapters.base, adapters.containers, adapters.languages, adapters.mock, adapters.registry, adapters.shell, adapters.vcs, core.config, core.engine, core.persistence, ui.web

```mermaid
classDiagram
    direction TD

    namespace src_adapters_base {
        class Adapter {
            <<abstract>>
            + name() str
            + is_available() bool
            + validate(context) tuple[bool, str]
            + execute(context) Receipt
            # __repr__() str
        }
        class ExecutionContext {
            + action: Action
            + project_root: str
            + environment: str
            + module_path: str | None
            + dry_run: bool
            + params: dict[str, Any]
            + working_dir() str
        }
    }

    namespace src_adapters_containers_docker {
        class DockerAdapter {
            + name() str
            + is_available() bool
            + validate(context) tuple[bool, str]
            + execute(context) Receipt
            # _ps(ctx) Receipt
            # _images(ctx) Receipt
            # _build(ctx) Receipt
            # _up(ctx) Receipt
            # _down(ctx) Receipt
            # _logs(ctx) Receipt
            # _version(ctx) Receipt
            # _docker(args, ctx, timeout) str
            # _run_command(ctx, command) Receipt
        }
    }

    namespace src_adapters_languages_node {
        class NodeAdapter {
            + name() str
            + is_available() bool
            # _detect_package_manager(cwd) str
            + version() str | None
            + validate(context) tuple[bool, str]
            + execute(context) Receipt
            # _get_version(ctx) Receipt
            # _run_node(ctx) Receipt
            # _install(ctx) Receipt
            # _run_script(ctx) Receipt
            # _exec(ctx, cmd, timeout) Receipt
            # _run_command(ctx, command) Receipt
        }
    }

    namespace src_adapters_languages_python {
        class PythonAdapter {
            + name() str
            + is_available() bool
            # _python_cmd() str
            + version() str | None
            + validate(context) tuple[bool, str]
            + execute(context) Receipt
            # _get_version(ctx) Receipt
            # _run_script(ctx) Receipt
            # _create_venv(ctx) Receipt
            # _pip_install(ctx) Receipt
            # _exec(ctx, cmd, timeout) Receipt
            # _run_command(ctx, command) Receipt
        }
    }

    namespace src_adapters_mock {
        class MockAdapter {
            # _name: Any
            # _available: Any
            # _default_output: Any
            # _responses: dict[str, Receipt]
            # _call_log: list[ExecutionContext]
            # __init__(adapter_name, available, default_output)
            + name() str
            + call_log() list[ExecutionContext]
            + call_count() int
            + is_available() bool
            + set_response(action_id, receipt) None
            + set_failure(action_id, error) None
            + validate(context) tuple[bool, str]
            + execute(context) Receipt
            + reset() None
        }
    }

    namespace src_adapters_registry {
        class AdapterRegistry {
            # _adapters: dict[str, Adapter]
            # _mock_mode: Any
            # _mock_adapter: Adapter | None
            # _circuit_breakers: Any
            # __init__(mock_mode, circuit_breakers)
            + mock_mode() bool
            + set_mock_mode(enabled, mock_adapter) None
            + register(adapter) None
            + unregister(name) None
            + get(name) Adapter | None
            + list_adapters() list[str]
            + adapter_status() dict[str, dict[str, Any]]
            + execute_action(action, project_root, environment, module_path, dry_run) Receipt
        }
    }

    namespace src_adapters_shell_command {
        class ShellCommandAdapter {
            + name() str
            + is_available() bool
            + validate(context) tuple[bool, str]
            + execute(context) Receipt
        }
    }

    namespace src_adapters_shell_filesystem {
        class FilesystemAdapter {
            + name() str
            + is_available() bool
            + validate(context) tuple[bool, str]
            + execute(context) Receipt
            # _exists(ctx, target) Receipt
            # _read(ctx, target) Receipt
            # _write(ctx, target) Receipt
            # _mkdir(ctx, target) Receipt
            # _list(ctx, target) Receipt
        }
    }

    namespace src_adapters_vcs_git {
        class GitAdapter {
            + name() str
            + is_available() bool
            + validate(context) tuple[bool, str]
            + execute(context) Receipt
            # _status(ctx) Receipt
            # _commit(ctx) Receipt
            # _push(ctx) Receipt
            # _pull(ctx) Receipt
            # _log(ctx) Receipt
            # _branch(ctx) Receipt
            # _diff(ctx) Receipt
            # _init(ctx) Receipt
            # _git(args, cwd, timeout) str
            # _run_command(ctx, command) Receipt
        }
    }

    namespace src_core_config_loader {
        class ConfigError {
        }
    }

    namespace src_core_engine_executor {
        class ExecutionPlan {
            <<dataclass>>
            + operation_id: str
            + automation: str
            + actions: list[Action]
            + module_actions: dict[str, list[Action]]
            + total_actions() int
        }
        class ExecutionReport {
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

    namespace src_core_persistence_audit {
        class AuditEntry {
            + timestamp: str
            + operation_id: str
            + operation_type: str
            + automation: str
            + environment: str
            + modules_affected: list[str]
            + status: str
            + actions_total: int
            + actions_succeeded: int
            + actions_failed: int
            ... 3 more fields
        }
        class AuditWriter {
            # _path: Any
            # __init__(path, project_root)
            + path() Path
            + write(entry) None
            + read_all() list[AuditEntry]
            + read_recent(n) list[AuditEntry]
            + entry_count() int
        }
    }

    namespace src_ui_web_routes_audit_async_scan {
        class ScanTask {
            <<dataclass>>
            + task_id: str
            + status: str
            + progress: float
            + phase: str
            + phase_detail: str
            + started_at: float
            + completed_at: float
            + duration_ms: int
            + result: dict
            + error: str
        }
    }

```

## Hub Analysis

> Classes with the most connections — critical nexus points for understanding system coupling.

```mermaid
classDiagram
    direction TD

    namespace src_adapters_base {
        class Adapter {
            <<abstract>>
        }
    }

    namespace src_adapters_containers_docker {
        class DockerAdapter {
        }
    }

    namespace src_adapters_languages_node {
        class NodeAdapter {
        }
    }

    namespace src_adapters_languages_python {
        class PythonAdapter {
        }
    }

    namespace src_adapters_mock {
        class MockAdapter {
        }
    }

    namespace src_adapters_registry {
        class AdapterRegistry {
        }
    }

    namespace src_adapters_shell_command {
        class ShellCommandAdapter {
        }
    }

    namespace src_adapters_shell_filesystem {
        class FilesystemAdapter {
        }
    }

    namespace src_adapters_vcs_git {
        class GitAdapter {
        }
    }

    namespace src_core_engine_executor {
        class ExecutionReport {
            <<dataclass>>
        }
    }

    namespace src_core_models_action {
        class Receipt {
        }
    }

    namespace src_core_models_project {
        class Environment {
        }
        class ExternalLinks {
        }
        class ModuleRef {
        }
        class Project {
        }
    }

    namespace src_core_services_artifacts_builders_base {
        class ArtifactBuilder {
            <<abstract>>
        }
    }

    namespace src_core_services_artifacts_builders_cargo {
        class CargoBuilder {
        }
    }

    namespace src_core_services_artifacts_builders_docker {
        class DockerBuilder {
        }
    }

    namespace src_core_services_artifacts_builders_dotnet {
        class DotnetBuilder {
        }
    }

    namespace src_core_services_artifacts_builders_gem {
        class GemBuilder {
        }
    }

    namespace src_core_services_artifacts_builders_go {
        class GoBuilder {
        }
    }

    namespace src_core_services_artifacts_builders_gradle {
        class GradleBuilder {
        }
    }

    namespace src_core_services_artifacts_builders_makefile {
        class MakefileBuilder {
        }
    }

    namespace src_core_services_artifacts_builders_maven {
        class MavenBuilder {
        }
    }

    namespace src_core_services_artifacts_builders_mix {
        class MixBuilder {
        }
    }

    namespace src_core_services_artifacts_builders_npm {
        class NpmBuilder {
        }
    }

    namespace src_core_services_artifacts_builders_pip_builder {
        class PipBuilder {
        }
    }

    namespace src_core_services_artifacts_builders_script {
        class ScriptBuilder {
        }
    }

    namespace src_core_services_audit_models {
        class AuditMeta {
        }
        class L0Result {
        }
        class ManifestInfo {
        }
        class ModuleInfo {
        }
        class OSInfo {
        }
        class RuntimeInfo {
        }
        class ToolInfo {
        }
    }

    namespace src_core_services_audit_parsers {
        class ParserRegistry {
        }
    }

    namespace src_core_services_audit_parsers__base {
        class BaseParser {
            <<abstract>>
        }
        class FileAnalysis {
            <<dataclass>>
        }
        class FileMetrics {
            <<dataclass>>
        }
        class ImportInfo {
            <<dataclass>>
        }
        class SymbolInfo {
            <<dataclass>>
        }
        class SymbolLocation {
            <<dataclass>>
        }
    }

    namespace src_core_services_audit_parsers__fallback {
        class FallbackParser {
        }
    }

    namespace src_core_services_audit_parsers_c_parser {
        class CFamilyParser {
        }
    }

    namespace src_core_services_audit_parsers_config_parser {
        class ConfigParser {
        }
    }

    namespace src_core_services_audit_parsers_css_parser {
        class CSSParser {
        }
    }

    namespace src_core_services_audit_parsers_go_parser {
        class GoParser {
        }
    }

    namespace src_core_services_audit_parsers_js_parser {
        class JavaScriptParser {
        }
    }

    namespace src_core_services_audit_parsers_jvm_parser {
        class JVMParser {
        }
    }

    namespace src_core_services_audit_parsers_multilang_parser {
        class MultiLangParser {
        }
    }

    namespace src_core_services_audit_parsers_python_parser {
        class PythonParser {
        }
    }

    namespace src_core_services_audit_parsers_rust_parser {
        class RustParser {
        }
    }

    namespace src_core_services_audit_parsers_template_parser {
        class TemplateParser {
        }
    }

    namespace src_core_services_content_outline {
        class CssOutlineStrategy {
        }
        class EncryptedOutlineStrategy {
        }
        class FallbackOutlineStrategy {
        }
        class GoOutlineStrategy {
        }
        class HtmlOutlineStrategy {
        }
        class JavaScriptOutlineStrategy {
        }
        class JsonOutlineStrategy {
        }
        class MarkdownOutlineStrategy {
        }
        class OutlineStrategy {
        }
        class PythonOutlineStrategy {
        }
        class RustOutlineStrategy {
        }
        class ShellOutlineStrategy {
        }
        class SqlOutlineStrategy {
        }
        class TomlOutlineStrategy {
        }
        class YamlOutlineStrategy {
        }
    }

    namespace src_core_services_pages_builders_base {
        class BuilderInfo {
            <<dataclass>>
        }
        class PageBuilder {
            <<abstract>>
        }
    }

    namespace src_core_services_pages_builders_custom {
        class CustomBuilder {
        }
    }

    namespace src_core_services_pages_builders_docusaurus {
        class DocusaurusBuilder {
        }
    }

    namespace src_core_services_pages_builders_hugo {
        class HugoBuilder {
        }
    }

    namespace src_core_services_pages_builders_mkdocs {
        class MkDocsBuilder {
        }
    }

    namespace src_core_services_pages_builders_raw {
        class RawBuilder {
        }
    }

    namespace src_core_services_pages_builders_sphinx {
        class SphinxBuilder {
        }
    }

    namespace src_core_use_cases_config_check {
        class ConfigCheckResult {
            <<dataclass>>
        }
    }

    namespace src_core_use_cases_detect {
        class DetectResult {
            <<dataclass>>
        }
    }

    namespace src_core_use_cases_run {
        class RunResult {
            <<dataclass>>
        }
    }

    namespace src_core_use_cases_status {
        class StatusResult {
            <<dataclass>>
        }
    }

    DockerAdapter --|> Adapter
    NodeAdapter --|> Adapter
    PythonAdapter --|> Adapter
    MockAdapter --|> Adapter
    ShellCommandAdapter --|> Adapter
    FilesystemAdapter --|> Adapter
    GitAdapter --|> Adapter
    CargoBuilder --|> ArtifactBuilder
    DockerBuilder --|> ArtifactBuilder
    DotnetBuilder --|> ArtifactBuilder
    GemBuilder --|> ArtifactBuilder
    GoBuilder --|> ArtifactBuilder
    GradleBuilder --|> ArtifactBuilder
    MakefileBuilder --|> ArtifactBuilder
    MavenBuilder --|> ArtifactBuilder
    MixBuilder --|> ArtifactBuilder
    NpmBuilder --|> ArtifactBuilder
    PipBuilder --|> ArtifactBuilder
    ScriptBuilder --|> ArtifactBuilder
    FallbackParser --|> BaseParser
    CFamilyParser --|> BaseParser
    ConfigParser --|> BaseParser
    CSSParser --|> BaseParser
    GoParser --|> BaseParser
    JavaScriptParser --|> BaseParser
    JVMParser --|> BaseParser
    MultiLangParser --|> BaseParser
    PythonParser --|> BaseParser
    RustParser --|> BaseParser
    TemplateParser --|> BaseParser
    MarkdownOutlineStrategy --|> OutlineStrategy
    PythonOutlineStrategy --|> OutlineStrategy
    EncryptedOutlineStrategy --|> OutlineStrategy
    JavaScriptOutlineStrategy --|> OutlineStrategy
    GoOutlineStrategy --|> OutlineStrategy
    RustOutlineStrategy --|> OutlineStrategy
    HtmlOutlineStrategy --|> OutlineStrategy
    CssOutlineStrategy --|> OutlineStrategy
    YamlOutlineStrategy --|> OutlineStrategy
    JsonOutlineStrategy --|> OutlineStrategy
    TomlOutlineStrategy --|> OutlineStrategy
    ShellOutlineStrategy --|> OutlineStrategy
    SqlOutlineStrategy --|> OutlineStrategy
    FallbackOutlineStrategy --|> OutlineStrategy
    CustomBuilder --|> PageBuilder
    DocusaurusBuilder --|> PageBuilder
    HugoBuilder --|> PageBuilder
    MkDocsBuilder --|> PageBuilder
    RawBuilder --|> PageBuilder
    SphinxBuilder --|> PageBuilder
    MockAdapter o-- Receipt : _responses
    AdapterRegistry o-- Adapter : _adapters
    AdapterRegistry --> Adapter : _mock_adapter
    ExecutionReport o-- Receipt : receipts
    Project o-- Environment : environments
    Project o-- ModuleRef : modules
    Project *-- ExternalLinks : external
    L0Result *-- AuditMeta : _meta
    L0Result *-- OSInfo : os
    L0Result *-- RuntimeInfo : runtime
    L0Result o-- ToolInfo : tools
    L0Result o-- ModuleInfo : modules
    L0Result o-- ManifestInfo : manifests
    ParserRegistry o-- BaseParser : _parsers
    ParserRegistry --> BaseParser : _fallback
    FileAnalysis o-- ImportInfo : imports
    FileAnalysis o-- SymbolInfo : symbols
    FileAnalysis *-- FileMetrics : metrics
    FileAnalysis o-- SymbolLocation : symbol_locations
    ConfigCheckResult --> Project : project
    DetectResult --> Project : project
    RunResult --> Project : project
    StatusResult --> Project : project
    Adapter ..> Receipt
    DockerAdapter ..> Receipt
    NodeAdapter ..> Receipt
    PythonAdapter ..> Receipt
    AdapterRegistry ..> Receipt
    ShellCommandAdapter ..> Receipt
    FilesystemAdapter ..> Receipt
    GitAdapter ..> Receipt
    BaseParser ..> FileAnalysis
    FallbackParser ..> FileAnalysis
    CFamilyParser ..> FileAnalysis
    ConfigParser ..> FileAnalysis
    CSSParser ..> FileAnalysis
    GoParser ..> FileAnalysis
    JavaScriptParser ..> FileAnalysis
    JVMParser ..> FileAnalysis
    MultiLangParser ..> FileAnalysis
    PythonParser ..> FileAnalysis
    RustParser ..> FileAnalysis
    TemplateParser ..> FileAnalysis
    PageBuilder ..> BuilderInfo
    CustomBuilder ..> BuilderInfo
    DocusaurusBuilder ..> BuilderInfo
    HugoBuilder ..> BuilderInfo
    MkDocsBuilder ..> BuilderInfo
    RawBuilder ..> BuilderInfo
    SphinxBuilder ..> BuilderInfo
```

| Class | Connections | Module |

|-------|------------|--------|

| **FileAnalysis** | 16 | src.core.services.audit.parsers._base |

| **BaseParser** | 14 | src.core.services.audit.parsers._base |

| **OutlineStrategy** | 14 | src.core.services.content.outline |

| **ArtifactBuilder** | 12 | src.core.services.artifacts.builders.base |

| **Adapter** | 10 | src.adapters.base |

| **Receipt** | 10 | src.core.models.action |

| **PageBuilder** | 7 | src.core.services.pages_builders.base |

| **Project** | 7 | src.core.models.project |

| **BuilderInfo** | 7 | src.core.services.pages_builders.base |

| **L0Result** | 6 | src.core.services.audit.models |


## Orphan Index

> 33 classes with no detected relationships. These may be utility classes, constants, or under-connected code.

| Class | Module | Kind | Fields | Methods |

|-------|--------|------|--------|--------|

| ConfigError | src.core.config.loader | class | 0 | 0 |

| DataRegistry | src.core.data | class | 0 | 23 |

| MermaidConfig | src.core.data.script_templates.lib.mermaid_generator | dataclass | 9 | 0 |

| GeneratedFile | src.core.models.template | class | 4 | 0 |

| AuditEntry | src.core.persistence.audit | class | 13 | 0 |

| AuditWriter | src.core.persistence.audit | class | 1 | 6 |

| ArtifactStageInfo | src.core.services.artifacts.builders.base | dataclass | 3 | 0 |

| ArtifactBuildResult | src.core.services.artifacts.engine | dataclass | 6 | 0 |

| ArtifactTarget | src.core.services.artifacts.engine | dataclass | 9 | 0 |

| ArtifactPublishResult | src.core.services.artifacts.publishers.base | dataclass | 8 | 0 |

| LibraryInfo | src.core.services.audit.catalog | class | 5 | 0 |

| Observation | src.core.services.audit.narrative | dataclass | 4 | 0 |

| Recommendation | src.core.services.audit.narrative | dataclass | 3 | 0 |

| QualityDimension | src.core.services.audit.parsers._rubrics | dataclass | 4 | 0 |

| CCMessage | src.core.services.changelog.models | dataclass | 8 | 2 |

| ChangelogEntry | src.core.services.changelog.models | dataclass | 4 | 0 |

| Thread | src.core.services.chat.models | class | 6 | 1 |

| EventBus | src.core.services.event_bus | class | 7 | 11 |

| Run | src.core.services.ledger.models | class | 13 | 3 |

| RunEvent | src.core.services.ledger.models | class | 9 | 0 |

| GitIdentityError | src.core.services.ledger.worktree | class | 0 | 0 |

| AuditDataBundle | src.core.services.pages_builders.audit_directive | dataclass | 9 | 0 |

| DirectiveMatch | src.core.services.pages_builders.audit_directive | dataclass | 5 | 0 |

| BuildResult | src.core.services.pages_builders.base | dataclass | 6 | 0 |

| ConfigField | src.core.services.pages_builders.base | dataclass | 9 | 0 |

| StageInfo | src.core.services.pages_builders.base | dataclass | 3 | 0 |

| PeekCandidate | src.core.services.peek | dataclass | 5 | 0 |

| PeekReference | src.core.services.peek | dataclass | 5 | 0 |

| SymbolEntry | src.core.services.peek | dataclass | 4 | 0 |

| IndexSymbolEntry | src.core.services.project_index | dataclass | 4 | 0 |

| ProjectIndex | src.core.services.project_index | dataclass | 16 | 0 |

| ScriptConfig | src.core.services.scripts.models | dataclass | 9 | 0 |

| ScanTask | src.ui.web.routes.audit.async_scan | dataclass | 10 | 0 |

