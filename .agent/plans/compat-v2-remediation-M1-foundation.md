# M1 — Foundation: Registry & Orchestrator Into Mediator

> Every compat-v2 component must use the program's systems. This milestone wires the
> foundation layer — the FeatureRegistry and CompatOrchestrator — into the mediator.
> After M1, no code anywhere calls `CompatOrchestrator.create()`. The compat engine
> is a mediator node like everything else in this program.

---

## What Exists Now (broken)

`CompatOrchestrator.create()` is called at 6 locations. Each call:
- Triggers `FeatureRegistry.load()` — parses 157 YAML files (2,921ms first time)
- Creates NEW DetectionEngine, FixEngine, VersionResolver, StepExecutor, BatchRunner
- Each DetectionEngine has its own empty AST cache — files re-parsed from disk every time
- `_load_module_configs()` reads project.yml from disk every time
- All 10 languages loaded when only Python is used
- No persistence — cold restart re-parses all YAML
- No integration with mediator, index, WorkQueue, or any program system

`_cached.py` exists as a hand-rolled cache for the orchestrator. Dead code — never imported.
Duplicates what the mediator does better.

---

## What M1 Delivers

### 1. `compat.registry` mediator node

```
Path:        compat.registry
TTL:         inf (YAML entries don't change at runtime)
Persist:     True (pickle shard — hydrates in <50ms, avoids 2.9s YAML parse)
Depends on:  nothing (root node)
Priority:    BACKGROUND(5) on startup dispatch (sub-feature of posture)
```

Resolver:
- Calls `FeatureRegistry.load(language="python")` — uses the existing `language`
  parameter that was never passed, cuts load from 1000 to ~700 entries
- Returns the registry instance
- Persisted as pickle shard to `.state/mediator_index/compat.registry.pkl`
- On warm restart: hydrates from pickle in <50ms — no YAML parsing
- On first-ever start: YAML parse runs in WorkQueue at BACKGROUND(5) — zero boot latency,
  zero request latency. `peek("compat.registry")` returns None until loaded. Handlers
  use legacy path until then.

### 2. `compat.orchestrator` mediator node

```
Path:        compat.orchestrator
TTL:         inf
Persist:     False (lightweight — engine objects wired to cached registry)
Depends on:  compat.registry (cascade: if registry reloads, orchestrator rebuilds)
```

Resolver:
- Gets registry from `mediator.get("compat.registry")`
- Creates ONE CompatOrchestrator with that registry
- All engines share the SAME AST cache, source cache, registry reference
- Returns the orchestrator
- Subsequent calls: <1ms cache hit

New classmethod on CompatOrchestrator:
```python
@classmethod
def create_from_registry(cls, registry, project_root):
    """Create orchestrator using an existing registry (no loading)."""
```

### 3. Registration file

New file: `src/core/services/mediator/registrations/compat.py`

Follows the exact pattern of `registrations/posture.py` and `registrations/index.py`:
- `register_compat(mediator)` function
- Called from `registrations/__init__.py` in `register_all()`
- Deferred imports inside resolver functions (keeps startup fast)

### 4. All `CompatOrchestrator.create()` call sites replaced

| File | Line | Old | New |
|------|------|-----|-----|
| code_scanner.py | 143 | `CompatOrchestrator.create(ctx.project_root)` | `m.peek("compat.orchestrator")` data access |
| code_scanner.py | 306 | `CompatOrchestrator.create(ctx.project_root)` | `m.peek("compat.orchestrator")` data access |
| code_scanner.py | 761 | `CompatOrchestrator.create(ctx.project_root)` | `m.peek("compat.orchestrator")` data access |
| executor.py | 161 | `CompatOrchestrator.create(ctx.project_root)` | `m.peek("compat.orchestrator")` data access |
| posture.py | 1719 | `CompatOrchestrator.create(project_root)` | `m.peek("compat.orchestrator")` data access |
| compat.py | 28 | `CompatOrchestrator.create(project_root)` | `m.get("compat.orchestrator")` data access |

Handler sites use `peek()` — returns None if not loaded, handler falls through to legacy.
The /api/compat/ routes use `get()` — blocks until loaded (user explicitly requested compat).

### 5. `_cached.py` deleted

Dead code. The mediator IS the cache. Delete the file.

### 6. `exploration_output.md` deleted

Rogue agent artifact in project root. Delete.

---

## Files Changed

| File | Action |
|------|--------|
| `src/core/services/mediator/registrations/compat.py` | NEW |
| `src/core/services/mediator/registrations/__init__.py` | Add register_compat() call |
| `src/core/services/compat/orchestrator.py` | Add create_from_registry() classmethod |
| `src/core/services/compat/database/registry.py` | Add pickle serialization support |
| `src/core/services/compat/_cached.py` | DELETE |
| `exploration_output.md` | DELETE |
| `src/core/services/module_upgrade/automation/code_scanner.py` | Replace 3x create() with peek() |
| `src/core/services/module_upgrade/automation/executor.py` | Replace 1x create() with peek() |
| `src/ui/web/routes/posture.py` | Replace 1x create() with peek() |
| `src/ui/web/routes/compat.py` | Replace _get_orchestrator() with mediator.get() |

---

## Verification

1. `grep -r "CompatOrchestrator.create(" src/` returns ONLY orchestrator.py and cli.py
2. `mediator.diag("compat.registry")` shows cached, TTL=inf
3. Application starts in <100ms
4. First request is not delayed
5. `_cached.py` does not exist
6. `exploration_output.md` does not exist
7. All existing tests pass
8. CLI still works (uses create() directly — no mediator in CLI, that's fine)
