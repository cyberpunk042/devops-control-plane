# Contextual Glossary — Stage 2: All Language Strategies

**Status**: ✅ COMPLETE — implemented 2026-03-05  
**Depends on**: `.agent/plans/contextual-glossary.md` (Stage 1) ✅  
**Scope**: Add outline extraction strategies for all remaining file types  
**Result**: 30 extensions across 14 strategies, all registered and tested


## 1. Context

Stage 1 delivers the panel infrastructure, API, and two strategies:
- `MarkdownOutlineStrategy` — heading extraction via regex
- `PythonOutlineStrategy` — class/function extraction via `ast.parse()`
- `EncryptedOutlineStrategy` — stub returning `{encrypted: true}`
- `FallbackOutlineStrategy` — empty outline for unsupported types

Stage 2 replaces `FallbackOutlineStrategy` for all common languages with
purpose-built regex extractors. Each strategy is a self-contained class in
`src/core/services/content/outline.py` that follows the same interface.


## 2. Strategy Interface (from Stage 1)

Every strategy implements:

```python
class OutlineStrategy:
    """Base class for outline extraction strategies."""
    
    extensions: set[str]  # file extensions this strategy handles
    
    def extract(self, source: str, file_path: str) -> list[dict]:
        """Extract outline nodes from source text.
        
        Returns list of:
            {"text": str, "kind": str, "line": int, "children": list[dict]}
        """
        raise NotImplementedError
```

Dispatching (already built in Stage 1):
```python
_STRATEGIES: dict[str, OutlineStrategy] = {}  # extension -> strategy

def _register_strategy(strategy: OutlineStrategy) -> None:
    for ext in strategy.extensions:
        _STRATEGIES[ext] = strategy

def extract_outline(file_path: Path, content: str | None = None) -> dict:
    ext = file_path.suffix.lower()
    strategy = _STRATEGIES.get(ext, _fallback_strategy)
    # ... dispatch
```


## 3. Strategies to Implement

### 3.1. JavaScript / TypeScript

**Extensions**: `.js`, `.jsx`, `.ts`, `.tsx`, `.mjs`, `.cjs`

**Extraction approach**: Line-by-line regex (no parser dependency).

**Symbols extracted**:

| Pattern | Kind | Example |
|---------|------|---------|
| `class Foo` / `export class Foo` | `class` | `class UserService {` |
| `function foo(` / `export function` | `function` | `function handleClick(e) {` |
| `async function foo(` | `function` | `async function fetchData() {` |
| `const foo = (` / `const foo = function` | `function` | `const mapItems = (items) => {` |
| `export default function` | `function` | `export default function App() {` |
| `export default class` | `class` | `export default class Router {}` |

**Nesting**: Methods inside classes detected by indentation heuristic:
- After a `class` line, indented `function`/method lines become children
- Method detection: lines starting with whitespace + identifier + `(`
- Reset on next top-level definition

```python
_JS_CLASS = re.compile(r'^(?:export\s+(?:default\s+)?)?class\s+(\w+)')
_JS_FUNC = re.compile(r'^(?:export\s+(?:default\s+)?)?(?:async\s+)?function\s+(\w+)')
_JS_ARROW = re.compile(r'^(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:\(|function)')
_JS_METHOD = re.compile(r'^\s+(?:async\s+)?(\w+)\s*\(')
```

**Edge cases handled**:
- TypeScript generics: `class Foo<T>` → strip `<T>` from name
- Decorators: `@decorator` lines skipped
- Comment blocks: Skip lines inside `/* ... */`

**Edge cases NOT handled (acceptable)**:
- Object literal methods: `const obj = { method() {} }` → not extracted
- Deeply nested arrow functions → not extracted
- `module.exports = ...` → not extracted as named symbol


### 3.2. Go

**Extensions**: `.go`

**Extraction approach**: Regex on function/type declarations.

| Pattern | Kind | Example |
|---------|------|---------|
| `func Foo(` | `function` | `func HandleRequest(w http.ResponseWriter, r *http.Request) {` |
| `func (r *Repo) Foo(` | `method` | `func (s *Server) Start() error {` |
| `type Foo struct` | `class` | `type Config struct {` |
| `type Foo interface` | `class` | `type Handler interface {` |
| `type Foo = ...` / `type Foo int` | `constant` | `type Status int` |

```python
_GO_FUNC = re.compile(r'^func\s+(\w+)\s*\(')
_GO_METHOD = re.compile(r'^func\s+\([^)]+\)\s+(\w+)\s*\(')
_GO_TYPE = re.compile(r'^type\s+(\w+)\s+(?:struct|interface)\b')
_GO_TYPE_ALIAS = re.compile(r'^type\s+(\w+)\s+')
```

**Nesting**: Methods grouped under their receiver type when possible.
Heuristic: if `func (s *Server) Start()` appears, group `Start` under `Server`.


### 3.3. Rust

**Extensions**: `.rs`

| Pattern | Kind | Example |
|---------|------|---------|
| `fn foo(` | `function` | `fn process_event(event: &Event) -> Result<()> {` |
| `pub fn foo(` | `function` | `pub fn new() -> Self {` |
| `struct Foo` | `class` | `pub struct Config {` |
| `enum Foo` | `class` | `enum State { Running, Stopped }` |
| `trait Foo` | `class` | `pub trait Handler {` |
| `impl Foo` | `class` | `impl Config {` |
| `impl Trait for Foo` | `class` | `impl Display for Config {` |

```python
_RS_FN = re.compile(r'^(?:pub\s+)?(?:async\s+)?fn\s+(\w+)')
_RS_STRUCT = re.compile(r'^(?:pub\s+)?struct\s+(\w+)')
_RS_ENUM = re.compile(r'^(?:pub\s+)?enum\s+(\w+)')
_RS_TRAIT = re.compile(r'^(?:pub\s+)?trait\s+(\w+)')
_RS_IMPL = re.compile(r'^impl(?:\s*<[^>]*>)?\s+(\w+)')
```

**Nesting**: Functions inside `impl` blocks become children of the impl node.


### 3.4. HTML

**Extensions**: `.html`, `.htm`

| Pattern | Kind | Example |
|---------|------|---------|
| `<h1>` - `<h6>` | `heading` | `<h2>Getting Started</h2>` |
| `<section id="...">` | `section` | `<section id="features">` |
| Elements with `id=` | `anchor` | `<div id="main-content">` |

```python
_HTML_HEADING = re.compile(r'<h([1-6])[^>]*>(.*?)</h\1>', re.IGNORECASE)
_HTML_SECTION = re.compile(r'<section[^>]*id=["\']([^"\']+)["\']', re.IGNORECASE)
_HTML_ID = re.compile(r'<(\w+)[^>]*id=["\']([^"\']+)["\']', re.IGNORECASE)
```

**Nesting**: Headings nested by level (h1 > h2 > h3), same as Markdown strategy.


### 3.5. CSS / SCSS / LESS

**Extensions**: `.css`, `.scss`, `.less`, `.sass`

| Pattern | Kind | Example |
|---------|------|---------|
| `/* ── Section ──── */` | `section` | `/* ── Layout ──────── */` |
| `/* === Section === */` | `section` | `/* === Variables === */` |
| `@media` | `media` | `@media (max-width: 768px) {` |
| `@keyframes` | `animation` | `@keyframes fadeIn {` |
| `@mixin` (SCSS) | `function` | `@mixin responsive($bp) {` |

```python
_CSS_SECTION = re.compile(r'/\*\s*[═─=─]{2,}\s*(.+?)\s*[═─=─]{2,}\s*\*/')
_CSS_MEDIA = re.compile(r'^@media\s+(.+)\s*\{')
_CSS_KEYFRAMES = re.compile(r'^@keyframes\s+(\w+)')
_CSS_MIXIN = re.compile(r'^@mixin\s+(\w[\w-]*)')
```


### 3.6. YAML

**Extensions**: `.yaml`, `.yml`

| Pattern | Kind | Example |
|---------|------|---------|
| Top-level keys | `section` | `modules:` |
| Comment headers | `section` | `# ── Adapters ──` |

```python
_YAML_KEY = re.compile(r'^(\w[\w_-]*)\s*:')
_YAML_SECTION_COMMENT = re.compile(r'^#\s*[═─=]{2,}\s*(.+?)\s*[═─=]{2,}')
```

**Note**: Only top-level keys (no leading whitespace). Nested YAML structure
is not extracted — would require a parser and adds too much noise.


### 3.7. JSON

**Extensions**: `.json`

| Pattern | Kind | Example |
|---------|------|---------|
| Top-level object keys | `section` | `"dependencies": {` |

Implementation: Parse with `json.loads()`, extract top-level keys.
If the file is an array, extract nothing (no meaningful structure).
If parsing fails, return empty outline.

```python
import json

def extract_json_outline(source: str) -> list[dict]:
    try:
        data = json.loads(source)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, dict):
        return []
    outline = []
    for key in data:
        # Find the line number by searching for the key in source
        line = _find_json_key_line(source, key)
        outline.append({"text": key, "kind": "section", "line": line, "children": []})
    return outline
```


### 3.8. TOML

**Extensions**: `.toml`

| Pattern | Kind | Example |
|---------|------|---------|
| `[section]` | `section` | `[tool.pytest]` |
| `[[array]]` | `section` | `[[tool.mypy.overrides]]` |

```python
_TOML_TABLE = re.compile(r'^\[([^\]]+)\]')
_TOML_ARRAY_TABLE = re.compile(r'^\[\[([^\]]+)\]\]')
```


### 3.9. Shell / Bash

**Extensions**: `.sh`, `.bash`, `.zsh`, `.fish`

| Pattern | Kind | Example |
|---------|------|---------|
| `function foo` | `function` | `function setup_env() {` |
| `foo()` | `function` | `build_docker() {` |
| Section comments | `section` | `# ═══ Docker Setup ═══` |

```python
_SH_FUNC_KW = re.compile(r'^function\s+(\w+)')
_SH_FUNC_PAREN = re.compile(r'^(\w+)\s*\(\s*\)')
_SH_SECTION = re.compile(r'^#\s*[═─=]{2,}\s*(.+?)\s*[═─=]{2,}')
```


### 3.10. SQL

**Extensions**: `.sql`

| Pattern | Kind | Example |
|---------|------|---------|
| `CREATE TABLE` | `class` | `CREATE TABLE users (` |
| `CREATE VIEW` | `class` | `CREATE VIEW active_users AS` |
| `CREATE FUNCTION` | `function` | `CREATE FUNCTION get_user(id INT)` |
| `CREATE PROCEDURE` | `function` | `CREATE PROCEDURE update_stats()` |
| `CREATE INDEX` | `constant` | `CREATE INDEX idx_email ON users` |

```python
_SQL_TABLE = re.compile(r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)', re.IGNORECASE)
_SQL_VIEW = re.compile(r'CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+(\w+)', re.IGNORECASE)
_SQL_FUNC = re.compile(r'CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+(\w+)', re.IGNORECASE)
_SQL_PROC = re.compile(r'CREATE\s+(?:OR\s+REPLACE\s+)?PROCEDURE\s+(\w+)', re.IGNORECASE)
_SQL_INDEX = re.compile(r'CREATE\s+(?:UNIQUE\s+)?INDEX\s+(\w+)', re.IGNORECASE)
```


## 4. Implementation Order

Each strategy is independent. Recommended priority based on this project's
actual file types and general developer utility:

| Priority | Strategy | Reason |
|----------|----------|--------|
| 1 | JavaScript/TypeScript | Very common, significant value for web code |
| 2 | Shell/Bash | This project has many `.sh` scripts |
| 3 | YAML | `project.yml`, `docker-compose.yml`, configs everywhere |
| 4 | Go | Used in many DevOps tools (Terraform, K8s) |
| 5 | HTML | Template files in `src/ui/web/templates/` |
| 6 | CSS/SCSS | Style files in the project |
| 7 | TOML | `pyproject.toml`, Rust configs |
| 8 | JSON | `package.json`, config files |
| 9 | SQL | Database migrations, less common |
| 10 | Rust | Future language support |


## 5. Testing Strategy

Each strategy gets tested by feeding it a known source file and asserting
the outline matches expected output. Tests are fast (pure string processing):

```python
def test_js_class_extraction():
    source = """
class UserService {
    constructor(db) { ... }
    async getUser(id) { ... }
}

export function createApp() { ... }
"""
    outline = JavaScriptOutlineStrategy().extract(source, "app.js")
    assert outline[0]["text"] == "UserService"
    assert outline[0]["kind"] == "class"
    assert len(outline[0]["children"]) == 2
    assert outline[1]["text"] == "createApp"
    assert outline[1]["kind"] == "function"
```


## 6. Performance Budget

All regex strategies must stay within:
- **< 5ms per file** for files under 50KB
- **< 20ms per file** for files up to 512KB
- **No external dependencies** — stdlib only (re, json, ast)
- **Graceful degradation** — if a file causes a regex to hang (ReDoS),
  timeout after 50ms and return empty outline

Since Python's `re` module doesn't support timeout natively, use
`signal.alarm()` on Unix or simply limit line count (max 10,000 lines
per file for regex strategies).


## 7. Files Changed

| File | Action | Purpose |
|------|--------|---------|
| `src/core/services/content/outline.py` | Edit | Add all new strategy classes |

That's it — one file. Each strategy is registered via `_register_strategy()`
in the module's top-level initialization. No API changes, no frontend changes.
The frontend already handles all `kind` values via the icon system.


## 8. Completion Criteria

Stage 2 is complete when:
- [ ] All 10 strategies implemented and registered
- [ ] Each strategy handles edge cases (empty files, syntax errors, UTF-8 issues)
- [ ] No strategy takes > 20ms on a 512KB file
- [ ] `/api/content/outline?path=file.EXT` returns correct outline for each type
- [ ] Glossary panel displays appropriate icons for each kind
- [ ] Stage 1 fallback behavior preserved for unrecognized extensions
