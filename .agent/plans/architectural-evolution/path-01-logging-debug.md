# Path 1: Logging & Debug Infrastructure

> **Status**: ✅ COMPLETE (2026-02-14)
> **Effort**: 0.5–1 day
> **Risk**: Very Low — additive change, zero breakage potential
> **Prereqs**: None (this IS the prereq for everything else)

---

## 1. What Exists Today

### Declarations (the good)

43 Python modules declare `logger = logging.getLogger(__name__)` and make
a total of **192 logger calls** across the codebase:

| Level | Core | Web Routes | Total |
|-------|-----:|----------:|------:|
| `debug` | 46 | 0 | **46** |
| `info` | 75 | 11 | **86** |
| `warning` | 35 | 0 | **35** |
| `error` | 8 | 0 | **8** |
| `exception` | 8 | 5 | **13** |
| `critical` | 0 | 0 | **0** |

### Configuration (the gap)

- **Zero `logging.basicConfig()` calls** in the entire codebase
- **Zero `StreamHandler` / `FileHandler` setup** anywhere
- **Zero log formatting** — no timestamps, no module names, no level indicators
- **No `--debug` flag** on the CLI
- The existing `--verbose` flag controls **Click echo output only** (line 280: `if ctx.obj.get("verbose") and receipt.output`), not Python log levels
- Flask's own `app.logger` works because Flask configures it internally, but all `src.core.*` loggers are deaf

### What this means

All 46 `logger.debug(...)` calls and 86 `logger.info(...)` calls — containing
diagnostic messages like `"cache HIT for %s (age %ds)"`, `"Git probe failed: %s"`,
`"Executing: %s (cwd=%s)"` — are **silently discarded** because Python's
default root logger level is `WARNING`. Only `warning`, `error`, and `exception`
calls would theoretically show up, and even those go nowhere without a handler attached.

### Entrypoints

There are **3 entrypoints** where logging configuration must be set:

1. **`src/main.py`** — CLI entrypoint (`python -m src.main`). This is the root.
   All CLI commands, TUI commands, and the `web` command pass through here.
2. **`src/ui/web/server.py`** — Web server factory. Currently called FROM `main.py`
   so it inherits whatever main.py configures. However, `run_server()` also accepts
   a `debug` parameter (line 120) that is **never passed from main.py**.
3. **`manage.sh`** — TUI wrapper. Calls `python -m src.main` so it inherits from main.py.

**The clean architecture**: Configure logging in `main.py` (the root). All paths
(CLI, TUI, Web) flow through it. Web gets its `debug` parameter from the same flag.

---

## 2. Design Decisions

### 2.1 Where does configuration live?

**Decision**: New module `src/core/observability/logging_config.py`

**Rationale**: 
- The `observability` package already exists (`health.py` is there)
- Logging configuration is infrastructure, not UI
- Both CLI and Web need it, so it must be in core
- Keeps main.py thin — it calls `setup_logging(level, log_file)` and moves on

### 2.2 How does the user control log level?

**Decision**: CLI flags + environment variable, with precedence:

```
CLI flag > ENV var > Default (WARNING)
```

| Source | Mechanism | Level |
|--------|-----------|-------|
| `--debug` flag | CLI flag on root group | `DEBUG` |
| `--verbose` flag (existing) | CLI flag on root group | `INFO` (enhanced from current behavior) |
| `--quiet` flag (existing) | CLI flag on root group | `ERROR` (enhanced from current behavior) |
| `DCP_LOG_LEVEL` env var | Environment variable | Any Python log level |
| Default | None | `WARNING` |

**Breaking change assessment**: The `--verbose` flag currently only controls Click's
`ctx.obj["verbose"]` which is checked in exactly 2 places (line 280 `run` command, 
line 363 `health` command) to show extra output. We will **preserve this behavior** 
AND also set `logging.INFO`. This is additive — the same flag now does more, never less.

The `--quiet` flag currently only sets `ctx.obj["quiet"]` which is checked in 1 place
(line 64 `status` command). We will preserve this AND set `logging.ERROR`. Additive.

### 2.3 Log output format

**Decision**: Differentiated by level:

| Mode | Format | Example |
|------|--------|---------|
| Normal (`WARNING`) | No prefix, minimal | `⚠ Overwriting existing adapter: docker` |
| Verbose (`INFO`) | Timestamped, module | `12:34:56 [vault_io] Vault imported — written to secrets.yml` |
| Debug (`DEBUG`) | Full, with line numbers | `12:34:56.789 DEBUG src.core.services.devops_cache:211 — cache HIT for testing (age 42s)` |

**Rationale**: 
- Normal mode: users don't want noise. Only warnings and errors.
- Verbose mode: operators want to see what's happening, timestamped.
- Debug mode: developers need file:line for tracing integration issues.

### 2.4 File output

**Decision**: Optional via env var `DCP_LOG_FILE`

| Env var | Behavior |
|---------|----------|
| Not set | Console only (stderr) |
| `DCP_LOG_FILE=.state/controlplane.log` | Console + file (both get same level) |
| `DCP_LOG_FILE=.state/controlplane.log` + `DCP_LOG_FILE_LEVEL=DEBUG` | Console at configured level, file always at DEBUG |

**Rationale**: 
- File logging should not require a restart when troubleshooting
- `.state/` is the natural place for runtime artifacts
- Allowing file to always be DEBUG while console is WARNING is useful
  for production-like operation where you want minimal console noise
  but full debug trail on disk

### 2.5 Flask's own logging

**Decision**: Wire Flask's logger to use the same configuration.

When `--debug` is passed to the `web` command:
1. Python root logger → `DEBUG`
2. `run_server(app, debug=True)` → Flask also in debug mode
3. Flask's Werkzeug request logging becomes visible

When `--verbose` is passed:
1. Python root logger → `INFO`
2. Flask stays in production mode but INFO messages are visible

### 2.6 Third-party noise control

**Decision**: Explicitly silence noisy third-party loggers at `WARNING`:

```python
# These produce excessive output at INFO/DEBUG
for lib in ("urllib3", "werkzeug", "watchdog", "PIL"):
    logging.getLogger(lib).setLevel(logging.WARNING)
```

Unless `--debug` is passed, in which case everything is loud.

---

## 3. Implementation Plan

### File: `src/core/observability/logging_config.py` (NEW)

```
Purpose: Central logging configuration for all entrypoints.
~60-80 lines.
```

**Functions**:

```python
def setup_logging(
    level: str = "WARNING",
    log_file: str | None = None,
    log_file_level: str | None = None,
    quiet_third_party: bool = True,
) -> None:
    """Configure Python logging for the entire process.
    
    Called once at startup by main.py. All subsequent
    logging.getLogger(__name__) calls inherit this config.
    """
```

**Responsibilities**:
1. Parse level string to `logging.LEVEL` constant
2. Create a `StreamHandler(sys.stderr)` with appropriate formatter
3. Optionally create a `FileHandler` with its own level/formatter
4. Set root logger level to the minimum of console and file levels
5. Optionally quiet third-party loggers
6. Set `logging.raiseExceptions = False` for production safety

### File: `src/main.py` (MODIFIED)

**Changes** (~15 lines):

1. Add `--debug` flag to the `cli()` group (alongside existing `--verbose`, `--quiet`)
2. In the `cli()` function body, call `setup_logging()` with resolved level
3. Store `debug` in `ctx.obj["debug"]` for downstream use
4. In the `web()` command, pass `debug=ctx.obj.get("debug", False)` to `run_server()`

**Level resolution logic**:
```python
import os

# Flag precedence: explicit flag > env > default
if debug:
    level = "DEBUG"
elif verbose:
    level = "INFO"
elif quiet:
    level = "ERROR"
else:
    level = os.environ.get("DCP_LOG_LEVEL", "WARNING")

setup_logging(
    level=level,
    log_file=os.environ.get("DCP_LOG_FILE"),
    log_file_level=os.environ.get("DCP_LOG_FILE_LEVEL"),
    quiet_third_party=not debug,
)
```

### File: `src/ui/web/server.py` (MODIFIED)

**Changes** (~3 lines):

1. `web()` command in main.py now passes `debug` to `run_server()` — this already
   exists as a parameter but was never wired (!). Just connecting the dots.

### File: `manage.sh` (NO CHANGES NEEDED)

`manage.sh` calls `python -m src.main <args>` which goes through `main.py`.
Logging is configured there. If someone wants debug mode from the TUI:

```bash
./manage.sh --debug web
# or via env:
DCP_LOG_LEVEL=DEBUG ./manage.sh web
```

The TUI menu items would also benefit from debug mode. No code changes needed —
the flag passes through.

---

## 4. Modules WITHOUT Loggers (Gap List)

These 19 modules currently have no `logger = logging.getLogger(__name__)`:

| Module | Should have logging? | Priority |
|--------|:---:|:---:|
| `generators/compose.py` | Yes — generates files, should log what it writes | Medium |
| `generators/dockerfile.py` | Yes — generates files | Medium |
| `generators/dockerignore.py` | Yes — generates files | Low |
| `generators/github_workflow.py` | Yes — generates files | Medium |
| `pages_builders/base.py` | Yes — base class, log lifecycle | Medium |
| `pages_builders/custom.py` | Yes | Low |
| `pages_builders/docusaurus.py` | Yes — complex builder | High |
| `pages_builders/hugo.py` | Yes | Low |
| `pages_builders/mkdocs.py` | Yes | Low |
| `pages_builders/raw.py` | No — trivial | Skip |
| `pages_builders/sphinx.py` | Yes | Low |
| `pages_builders/template_engine.py` | Yes — template rendering | Medium |
| `md_transforms.py` | Maybe — pure function, low value | Skip |
| `audit/__init__.py` | No — package init | Skip |
| `audit/models.py` | No — data models only | Skip |
| `generators/__init__.py` | No — package init | Skip |
| `pages_builders/__init__.py` | No — package init | Skip |
| `services/__init__.py` | No — package init | Skip |
| `audit/parsers/__init__.py` | No — package init | Skip |

**Scope decision**: We will NOT add loggers to all 19 modules in this path.
That's a separate concern (gradual improvement). Path 1 is about **configuring
the 43 existing loggers so their 192 calls actually produce output.** Adding
loggers to the remaining modules is a natural ongoing practice as we touch
those files in later paths.

---

## 5. Testing Strategy

### Manual verification:

```bash
# 1. Default mode — should see nothing (WARNING level)
./manage.sh status

# 2. Verbose mode — should see INFO messages with timestamps
./manage.sh -v status

# 3. Debug mode — should see DEBUG messages with file:line
./manage.sh --debug status

# 4. Debug web — should see all Flask + core debug output
./manage.sh --debug web

# 5. File output — should create log file
DCP_LOG_FILE=.state/controlplane.log ./manage.sh --debug status
cat .state/controlplane.log

# 6. Env var — should behave like --debug
DCP_LOG_LEVEL=DEBUG ./manage.sh status

# 7. Quiet mode — should suppress info/warning
./manage.sh -q status
```

### What "success" looks like:

1. Running `./manage.sh --debug web` then visiting the dashboard should produce
   visible console output like:
   ```
   12:34:56.789 DEBUG src.core.services.devops_cache:211 — cache HIT for testing (age 42s)
   12:34:56.790 INFO  src.core.services.metrics_ops:81 — Git probe failed: ...
   ```

2. Running `./manage.sh -v detect` should show timestamped info about what's
   being detected, without the noisy debug lines.

3. Running `./manage.sh status` (no flags) should produce exactly the same
   output as today — zero logging noise.

---

## 6. What This Unlocks

Once Path 1 is complete:

| Subsequent Path | How logging helps |
|-----------------|-------------------|
| **Path 2 (Data extraction)** | Debug output shows where datasets are loaded from, cache status |
| **Path 3 (File split)** | Can verify each split file loads correctly by watching import logs |
| **Path 5 (Audit expansion)** | Audit writes will be logged at INFO level with `logger.info("Audit entry written: %s")` |
| **Path 6 (Route thinning)** | Can trace request → route → core → adapter flow at DEBUG level |
| **Path 7 (Caching)** | Cache HIT/MISS/BUST visible at DEBUG, already instrumented in `devops_cache.py` |
| **General debugging** | Any integration issue (Docker, K8s, Terraform) becomes diagnosable |

---

## 7. Open Questions

1. **Log rotation**: Do we want `RotatingFileHandler` (max size + backup count) 
   instead of plain `FileHandler`? For Path 1, I'd say no — keep it simple with 
   plain `FileHandler`, and add rotation later if the file grows large.

2. **JSON structured logging**: Some projects use JSON-formatted log lines for 
   machine parsing. Do we want this as an option? 
   My recommendation: not now. Human-readable first. JSON logging can be a 
   future option (`DCP_LOG_FORMAT=json`).

3. **The naming prefix**: `DCP_` for env vars (DevOps Control Plane). Is this the 
   right prefix? Alternatives: `CONTROLPLANE_`, `CP_`.

4. **Should `--verbose` also print `logger.info` output for the `web` command?**
   Currently web server only shows Flask request logs. With this change, 
   `--verbose` would also show core service INFO messages during web requests.
   This seems correct but wanted to flag it.

---

## 8. Files Touched Summary

| File | Action | Lines changed |
|------|--------|:---:|
| `src/core/observability/logging_config.py` | **NEW** | ~70 |
| `src/main.py` | Modified | ~15 |
| `src/ui/web/server.py` | Modified | ~3 |

**Total**: ~88 lines of new/modified code. Zero breakage risk.
