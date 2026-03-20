# 29 — Multi-Language Plugin Architecture

> **Document**: 29 of 37
> **Milestone**: M9 — Language modules & edge cases
> **Status**: Draft

---

## 1. Purpose

The multi-language plugin architecture ensures that adding a new language (or improving an existing one) requires ZERO changes to the core engine. The engine is generic — it processes feature database entries and delegates language-specific operations to backends. Each backend is a plugin that implements a standard interface.

---

## 2. Plugin Interface

```python
class LanguageBackend(ABC):
    """Abstract interface every language backend must implement."""

    @property
    @abstractmethod
    def language_id(self) -> str:
        """Unique language identifier: 'python', 'javascript', etc."""

    @property
    @abstractmethod
    def file_extensions(self) -> list[str]:
        """Source file extensions: ['.py'], ['.js', '.jsx'], etc."""

    @property
    @abstractmethod
    def parser_name(self) -> str:
        """Parser used: 'ast', 'tree-sitter-javascript', etc."""

    @abstractmethod
    def parse_file(self, path: Path) -> ASTNode:
        """Parse source file into AST."""

    @abstractmethod
    def walk_ast(self, ast: ASTNode) -> Iterator[ASTNode]:
        """Depth-first walk of all AST nodes."""

    @abstractmethod
    def node_type(self, node: ASTNode) -> str:
        """Get the type name of an AST node."""

    @abstractmethod
    def node_attributes(self, node: ASTNode) -> dict:
        """Get all attributes of an AST node as a dict."""

    @abstractmethod
    def node_location(self, node: ASTNode) -> tuple[int, int]:
        """Get (line, column) of a node."""

    @abstractmethod
    def node_source(self, node: ASTNode, source: str) -> str:
        """Get the source text corresponding to a node."""

    @abstractmethod
    def node_parent(self, node: ASTNode, ast: ASTNode) -> ASTNode | None:
        """Get the parent node (for context detection)."""

    @abstractmethod
    def resolve_imports(self, file_path: Path, project_root: Path) -> list[ImportEdge]:
        """Trace imports from a file. Return edges for project-internal imports."""

    @abstractmethod
    def apply_transform(
        self, source: str, ast: ASTNode, node: ASTNode, transform: Transform
    ) -> str:
        """Apply a transform to a specific AST node. Return modified source."""

    @abstractmethod
    def check_syntax(self, file_path: Path) -> bool:
        """Verify file has valid syntax."""

    @abstractmethod
    def check_importable(self, file_path: Path) -> bool:
        """Verify file can be imported/compiled."""

    @abstractmethod
    def format_source(self, source: str) -> str:
        """Format source code using the language's canonical formatter."""

    @abstractmethod
    def query_package_registry(
        self, package: str, target_version: str
    ) -> PackageCompatResult:
        """Check if a package supports the target version."""

    @abstractmethod
    def parse_manifest(self, module_dir: Path) -> ManifestInfo:
        """Parse the dependency manifest (requirements.txt, package.json, etc.)."""

    @abstractmethod
    def version_floor_from_manifest(self, module_dir: Path) -> str | None:
        """Extract the declared version floor from the manifest."""
```

---

## 3. Backend Registration

```python
class BackendRegistry:
    """Registry of available language backends."""

    _backends: dict[str, type[LanguageBackend]] = {}

    @classmethod
    def register(cls, backend_class: type[LanguageBackend]) -> None:
        """Register a backend class."""
        instance = backend_class()
        cls._backends[instance.language_id] = backend_class

    @classmethod
    def get(cls, language: str) -> LanguageBackend:
        """Get a backend instance for a language."""
        backend_class = cls._backends.get(language)
        if not backend_class:
            raise UnsupportedLanguage(f"No backend for language: {language}")
        return backend_class()

    @classmethod
    def supported_languages(cls) -> list[str]:
        """List all supported language IDs."""
        return sorted(cls._backends.keys())

    @classmethod
    def for_extension(cls, extension: str) -> LanguageBackend | None:
        """Find backend by file extension."""
        for backend_class in cls._backends.values():
            instance = backend_class()
            if extension in instance.file_extensions:
                return instance
        return None
```

### 3.1 Auto-discovery

Backends are auto-discovered from the `backends/` directory:

```python
# backends/__init__.py
from .python_backend import PythonBackend
from .javascript_backend import JavaScriptBackend
from .typescript_backend import TypeScriptBackend
from .go_backend import GoBackend
from .rust_backend import RustBackend
from .ruby_backend import RubyBackend
from .java_backend import JavaBackend
from .csharp_backend import CSharpBackend
from .php_backend import PHPBackend
from .elixir_backend import ElixirBackend

# Auto-register all backends
for backend in [
    PythonBackend, JavaScriptBackend, TypeScriptBackend,
    GoBackend, RustBackend, RubyBackend, JavaBackend,
    CSharpBackend, PHPBackend, ElixirBackend,
]:
    BackendRegistry.register(backend)
```

---

## 4. Adding a New Language

To add language support (e.g., Kotlin):

### Step 1: Create backend

```python
# backends/kotlin_backend.py
class KotlinBackend(LanguageBackend):
    language_id = "kotlin"
    file_extensions = [".kt", ".kts"]
    parser_name = "tree-sitter-kotlin"

    def parse_file(self, path): ...
    def walk_ast(self, ast): ...
    # ... implement all abstract methods
```

### Step 2: Create feature entries

```yaml
# database/entries/kotlin/_meta.yml
language: kotlin
display_name: Kotlin
file_extensions: [".kt", ".kts"]
parser: tree-sitter-kotlin
versions:
  - version: "1.5"
  - version: "1.6"
  - version: "1.7"
  - version: "1.8"
  - version: "1.9"
  - version: "2.0"

# database/entries/kotlin/kotlin1_5.yml
- id: kotlin.1_5.sealed_interfaces
  feature_name: "sealed interfaces"
  introduced: "1.5"
  ...

# database/entries/kotlin/kotlin2_0.yml
- id: kotlin.2_0.k2_compiler
  feature_name: "K2 compiler features"
  introduced: "2.0"
  ...
```

### Step 3: Register

```python
# backends/__init__.py
from .kotlin_backend import KotlinBackend
BackendRegistry.register(KotlinBackend)
```

### Step 4: Test

```
controlplane compat validate-db --language kotlin
```

**No engine code changes.** The engine, detection, fix, verification, lifecycle — ALL remain unchanged. Only the backend and entries are new.

---

## 5. Shared Utilities

Common functionality shared across backends:

### 5.1 Tree-sitter base class

Most backends use tree-sitter. A base class provides common tree-sitter operations:

```python
class TreeSitterBackend(LanguageBackend):
    """Base class for tree-sitter-based backends."""

    def __init__(self, language_lib):
        self._parser = tree_sitter.Parser()
        self._parser.set_language(language_lib)

    def parse_file(self, path: Path) -> tree_sitter.Tree:
        source = path.read_bytes()
        return self._parser.parse(source)

    def walk_ast(self, tree: tree_sitter.Tree) -> Iterator[tree_sitter.Node]:
        cursor = tree.walk()
        visited = False
        while True:
            if not visited:
                yield cursor.node
                if cursor.goto_first_child():
                    continue
            if cursor.goto_next_sibling():
                visited = False
                continue
            if not cursor.goto_parent():
                break
            visited = True

    def node_type(self, node: tree_sitter.Node) -> str:
        return node.type

    def node_location(self, node: tree_sitter.Node) -> tuple[int, int]:
        return (node.start_point[0] + 1, node.start_point[1])

    def node_source(self, node: tree_sitter.Node, source: str) -> str:
        return source[node.start_byte:node.end_byte]
```

Backends that use tree-sitter (JS, TS, Go, Rust, Ruby, Java, C#, PHP, Elixir) extend this class. Only Python uses `ast` stdlib directly.

### 5.2 Package registry base class

```python
class PackageRegistryQuerier(ABC):
    """Base class for package registry queries."""

    @abstractmethod
    def query_package(self, package: str) -> PackageInfo: ...

    @abstractmethod
    def check_compat(self, package: str, version: str, target: str) -> bool: ...

    @abstractmethod
    def find_compatible_versions(self, package: str, target: str) -> list[str]: ...
```

Implementations: `PyPIQuerier`, `NpmQuerier`, `CratesIoQuerier`, `RubyGemsQuerier`, `MavenQuerier`, `NuGetQuerier`, `PackagistQuerier`, `HexQuerier`.

### 5.3 Manifest parser base class

```python
class ManifestParser(ABC):
    """Base class for dependency manifest parsing."""

    @abstractmethod
    def parse(self, module_dir: Path) -> ManifestInfo: ...

    @abstractmethod
    def get_dependencies(self, module_dir: Path) -> list[Dependency]: ...

    @abstractmethod
    def get_version_floor(self, module_dir: Path) -> str | None: ...

    @abstractmethod
    def add_dependency(self, module_dir: Path, package: str, constraint: str) -> None: ...

    @abstractmethod
    def remove_dependency(self, module_dir: Path, package: str) -> None: ...
```

---

## 6. Language Detection

Given a module's `stack` field from project.yml, detect the language:

```python
_STACK_TO_LANGUAGE = {
    "python-lib": "python",
    "python-cli": "python",
    "python-flask": "python",
    "python-django": "python",
    "python-fastapi": "python",
    "node": "javascript",
    "node-express": "javascript",
    "typescript": "typescript",
    "typescript-react": "typescript",
    "go": "go",
    "go-service": "go",
    "rust": "rust",
    "ruby": "ruby",
    "ruby-rails": "ruby",
    "java": "java",
    "java-spring": "java",
    "kotlin": "kotlin",
    "csharp": "csharp",
    "dotnet": "csharp",
    "php": "php",
    "php-laravel": "php",
    "elixir": "elixir",
    "elixir-phoenix": "elixir",
}

def detect_language(stack: str) -> str | None:
    return _STACK_TO_LANGUAGE.get(stack)
```

Auto-detection from file extensions (fallback if stack is not set):

```python
def detect_language_from_files(module_dir: Path) -> str | None:
    """Detect language by counting file extensions."""
    counts = Counter()
    for f in module_dir.rglob("*"):
        if f.is_file():
            ext = f.suffix
            for backend in BackendRegistry.all():
                if ext in backend.file_extensions:
                    counts[backend.language_id] += 1
    if counts:
        return counts.most_common(1)[0][0]
    return None
```

---

## 7. Integration Points

### 7.1 With Detection Engine (Document 03)
- Engine calls `BackendRegistry.get(language)` to get the right backend
- All detection operations go through the backend interface

### 7.2 With Fix Engine (Document 05)
- Fix transforms call `backend.apply_transform()`
- Verification calls `backend.check_syntax()` and `backend.check_importable()`

### 7.3 With Import Resolver (Document 04)
- Import resolution is language-specific: `backend.resolve_imports()`

### 7.4 With Dependency Analysis (Document 14)
- Package registry queries: `backend.query_package_registry()`
- Manifest parsing: `backend.parse_manifest()`

### 7.5 With Feature Database (Document 02)
- Each entry's `language` field routes to the correct backend
- Entries are stored per-language in `database/entries/{language}/`
