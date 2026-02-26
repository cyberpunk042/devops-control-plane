# Domain: Inputs

> ⚠️ **PHASE LABELS MAY BE STALE** — As of 2026-02-25, code has evolved far beyond
> what the phase roadmaps suggest. Many features labeled "Phase 4-8 future" are
> ALREADY IMPLEMENTED. See `audit-domain-docs.md` and `audit-missing-pieces.md`
> for the verified truth. Code is the source of truth, not these phase labels.


> This document catalogs user-provided inputs in the tool install
> system: text, number, path, select, boolean, password fields.
> Default values, validation rules (client + server), template
> variable substitution into commands and config files.
>
> SOURCE DOCS: scope-expansion §2.2 (configuration inputs),
>              scope-expansion §2.14 (template variables),
>              domain-config-files §user inputs,
>              domain-choices §option schema

---

## Overview

Inputs are user-provided values that customize an installation.
They are DIFFERENT from choices:

| Concept | What it is | Example |
|---------|-----------|---------|
| **Choice** | Pick from predefined options | CPU vs CUDA (radio buttons) |
| **Input** | Enter a custom value | Port number, data directory (text fields) |

Choices select a BRANCH. Inputs fill in VALUES within that branch.

### Phase 2 vs Phase 4

| Phase | Input capability |
|-------|-----------------|
| Phase 2 | No user inputs. All values are hardcoded in recipes. |
| Phase 4 | Input framework: types, defaults, validation, substitution. |

---

## Input Types

### Type catalog

| Type | Widget | Value | Example |
|------|--------|-------|---------|
| `select` | Dropdown | One of predefined values | Storage driver: overlay2 |
| `number` | Number spinner | Integer or float | Port: 8080 |
| `text` | Text field | Free-form string | Hostname |
| `path` | Path field (with browse) | Absolute filesystem path | Data dir: /var/lib/app |
| `boolean` | Toggle / checkbox | true or false | Enable TLS: yes |
| `password` | Password field (masked) | Secret string | Admin password |

### Full schema

```python
{
    "id": str,              # unique identifier (used as variable name)
    "label": str,           # display label
    "description": str,     # help text below the field
    "type": str,            # "select" | "number" | "text" | "path" | "boolean" | "password"
    "default": Any,         # pre-filled value
    "required": bool,       # must have a value (default True)
    "validation": dict,     # type-specific validation rules
    "options": list[str],   # for select type only
    "condition": str | dict,# show only if condition met
    "sensitive": bool,      # if True: not logged, not persisted
    "group": str,           # visual grouping label
}
```

---

## Per-Type Details

### select

```python
{
    "id": "docker_storage_driver",
    "label": "Storage Driver",
    "type": "select",
    "options": ["overlay2", "btrfs", "devicemapper"],
    "default": "overlay2",
    "description": "overlay2 is recommended for most systems",
}
```

**Validation:** Value must be in `options` list.

### number

```python
{
    "id": "port",
    "label": "Listen Port",
    "type": "number",
    "default": 8080,
    "validation": {
        "min": 1,
        "max": 65535,
        "integer": True,    # no decimals
    },
}
```

**Validation:** Must be within `min`/`max` range. If `integer: True`,
no decimal values.

### text

```python
{
    "id": "hostname",
    "label": "Server Hostname",
    "type": "text",
    "default": "localhost",
    "validation": {
        "pattern": "^[a-zA-Z0-9][a-zA-Z0-9.-]+$",
        "min_length": 1,
        "max_length": 253,
    },
}
```

**Validation:** Regex pattern match, length constraints.

### path

```python
{
    "id": "data_dir",
    "label": "Data Directory",
    "type": "path",
    "default": "/var/lib/myapp",
    "validation": {
        "must_be_absolute": True,       # starts with /
        "must_exist": False,            # will be created if needed
        "must_be_writable": True,       # check write permission
        "min_free_space_mb": 500,       # check disk space
    },
}
```

**Validation:** Path syntax, existence, permissions, disk space.

### boolean

```python
{
    "id": "enable_tls",
    "label": "Enable TLS",
    "type": "boolean",
    "default": True,
    "description": "Encrypt connections with TLS certificates",
}
```

**Validation:** Must be True or False.

### password

```python
{
    "id": "admin_password",
    "label": "Admin Password",
    "type": "password",
    "required": True,
    "sensitive": True,      # never logged, never persisted
    "validation": {
        "min_length": 8,
        "pattern": ".*[A-Z].*",  # at least one uppercase
    },
}
```

**Validation:** Length, complexity pattern.

**Security:**
- Never logged in plan output
- Never persisted to plan state file
- Never sent back in API responses
- Cleared from memory after substitution

---

## Default Values

### Static defaults

```python
"default": 8080              # fixed value
"default": "overlay2"         # fixed string
"default": "/var/lib/myapp"   # fixed path
"default": True               # fixed boolean
```

### Dynamic defaults (Phase 8)

```python
"default_from": "system",     # read from system profile
"default_source": "cpu.cores" # e.g., -j$(nproc)
```

### Default behavior

| Situation | Behavior |
|-----------|----------|
| User doesn't change default | Default value used |
| User clears field | If `required: True`: validation error. If `required: False`: omit from config |
| No default provided | Field starts empty. If `required: True`: must be filled |

---

## Validation

### Two-layer validation

```
┌─────────────┐     ┌─────────────┐
│  Frontend    │     │  Backend     │
│  (client)    │────►│  (server)    │
│              │     │              │
│ • Type check │     │ • Type check │
│ • Range      │     │ • Range      │
│ • Pattern    │     │ • Pattern    │
│ • Required   │     │ • Required   │
│              │     │ • Path exist │
│              │     │ • Disk space │
│              │     │ • Permission │
└─────────────┘     └─────────────┘
```

**Client-side** catches obvious errors immediately (fast UX).
**Server-side** catches things the client can't check (filesystem,
permissions, disk) and is the source of truth (security).

### Validation function

```python
def validate_input(input_def: dict, value: Any) -> str | None:
    """Validate a single input value.
    Returns error message string or None if valid.
    """
    itype = input_def["type"]

    # Required check
    if input_def.get("required", True) and (value is None or value == ""):
        return f"{input_def['label']} is required"

    # Type-specific
    if itype == "number":
        v = input_def.get("validation", {})
        if not isinstance(value, (int, float)):
            return "Must be a number"
        if v.get("integer") and not isinstance(value, int):
            return "Must be a whole number"
        if "min" in v and value < v["min"]:
            return f"Must be at least {v['min']}"
        if "max" in v and value > v["max"]:
            return f"Must be at most {v['max']}"

    elif itype == "text" or itype == "password":
        v = input_def.get("validation", {})
        if "min_length" in v and len(value) < v["min_length"]:
            return f"Must be at least {v['min_length']} characters"
        if "max_length" in v and len(value) > v["max_length"]:
            return f"Must be at most {v['max_length']} characters"
        if "pattern" in v and not re.match(v["pattern"], value):
            return f"Invalid format"

    elif itype == "select":
        if value not in input_def.get("options", []):
            return f"Must be one of: {input_def['options']}"

    elif itype == "path":
        v = input_def.get("validation", {})
        if v.get("must_be_absolute") and not value.startswith("/"):
            return "Must be an absolute path"
        if v.get("must_exist") and not os.path.exists(value):
            return f"Path does not exist: {value}"
        if v.get("must_be_writable"):
            parent = os.path.dirname(value)
            if os.path.exists(parent) and not os.access(parent, os.W_OK):
                return f"No write permission: {parent}"

    elif itype == "boolean":
        if value not in (True, False):
            return "Must be true or false"

    return None


def validate_all_inputs(input_defs: list[dict],
                         values: dict) -> dict[str, str]:
    """Validate all inputs. Returns {input_id: error_message} for failures."""
    errors = {}
    for inp in input_defs:
        val = values.get(inp["id"])
        err = validate_input(inp, val)
        if err:
            errors[inp["id"]] = err
    return errors
```

---

## Template Substitution

### How it works

Input values are substituted into commands and config templates
via `{variable_name}` placeholders:

```python
# Template
"command": ["docker", "run", "-p", "{port}:80", "{image_name}"]

# Input values
{"port": 8080, "image_name": "nginx:latest"}

# Result
["docker", "run", "-p", "8080:80", "nginx:latest"]
```

### Substitution function

```python
def substitute_template(template, values: dict):
    """Substitute {var} placeholders in commands and strings."""
    if isinstance(template, str):
        result = template
        for key, val in values.items():
            result = result.replace(f"{{{key}}}", str(val))
        return result
    elif isinstance(template, list):
        return [substitute_template(item, values) for item in template]
    elif isinstance(template, dict):
        return {k: substitute_template(v, values) for k, v in template.items()}
    return template
```

### Where substitution happens

| Location | Example |
|----------|---------|
| Install command | `pip install torch --index-url {pip_index}` |
| Post-install command | `systemctl restart {service_name}` |
| Config file template | `"storage-driver": "{docker_storage_driver}"` |
| Config file path | `/etc/logrotate.d/{tool_name}` |
| Verify command | `curl http://localhost:{port}/health` |

### Built-in variables

Some variables are auto-populated (not from user input):

| Variable | Source | Value |
|----------|--------|-------|
| `{user}` | `os.getenv("USER")` | Current username |
| `{home}` | `os.path.expanduser("~")` | Home directory |
| `{arch}` | System profile | `amd64`, `arm64` |
| `{distro}` | System profile | `ubuntu`, `fedora` |
| `{tool_name}` | Current recipe | Tool being installed |

---

## Conditional Inputs

### Show input only when relevant

```python
{
    "id": "cuda_path",
    "label": "CUDA Toolkit Path",
    "type": "path",
    "default": "/usr/local/cuda",
    "condition": {"choice": "compute", "value": "cuda121"},
    # Only shown when compute choice is cuda121
}
```

### Multiple conditions

```python
{
    "id": "journal_max_size",
    "label": "Max Journal Size",
    "type": "select",
    "options": ["100M", "500M", "1G", "2G"],
    "condition": "has_systemd",
    # Only shown on systemd systems
}
```

---

## Input Groups

### Visual grouping in UI

```python
"inputs": [
    {"id": "port", "label": "Port", "type": "number",
     "group": "Network"},
    {"id": "hostname", "label": "Hostname", "type": "text",
     "group": "Network"},
    {"id": "data_dir", "label": "Data Directory", "type": "path",
     "group": "Storage"},
    {"id": "log_dir", "label": "Log Directory", "type": "path",
     "group": "Storage"},
]
```

UI renders:

```
┌─ Network ──────────────────┐
│ Port:     [8080        ]   │
│ Hostname: [localhost   ]   │
└────────────────────────────┘
┌─ Storage ──────────────────┐
│ Data Directory: [/var/lib/] │
│ Log Directory:  [/var/log/] │
└────────────────────────────┘
```

---

## Edge Cases

| Case | Impact | Handling |
|------|--------|---------|
| Unsubstituted `{var}` | Literal `{var}` in command — fails | Validate all placeholders resolved |
| Password in command | Visible in process list | Use stdin pipe or env var instead |
| Path with spaces | Command breaks | Quote handling in substitution |
| Empty optional input | Placeholder left as `{var}` | Replace with empty string or omit |
| Port already in use | Service won't start | Post-validation: check port availability |
| Non-ASCII in text input | Encoding issues | UTF-8 everywhere |
| XSS in text input | Security risk in web UI | Sanitize for HTML display |
| Path traversal | `../../etc/passwd` | Canonicalize and validate |
| Extremely long value | Buffer issues | max_length enforcement |

---

## Traceability

| Topic | Source |
|-------|--------|
| Input types + validation | scope-expansion §2.2 |
| Docker config inputs | scope-expansion §2.2 (storage driver, port, data_dir) |
| Client + server validation | scope-expansion §2.2 ("runs client-side AND server-side") |
| Template variable substitution | scope-expansion §2.14 |
| Config template inputs | domain-config-files §user inputs |
| Journald inputs | domain-config-files §journald example |
| Password security | domain-sudo-security (not yet written) |
| Input conditions | domain-choices §conditional |
| Built-in variables | scope-expansion §2.6 ({user}, {home}) |
