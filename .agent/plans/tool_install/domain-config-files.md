# Domain: Config Files

> ⚠️ **PHASE LABELS MAY BE STALE** — As of 2026-02-25, code has evolved far beyond
> what the phase roadmaps suggest. Many features labeled "Phase 4-8 future" are
> ALREADY IMPLEMENTED. See `audit-domain-docs.md` and `audit-missing-pieces.md`
> for the verified truth. Code is the source of truth, not these phase labels.


> This document catalogs configuration file management in the
> tool install system: daemon.json, nginx.conf, journald.conf,
> logrotate, syslog. The template system with user inputs,
> variable substitution, validation, and post-write commands.
>
> SOURCE DOCS: scope-expansion §2.2 (configuration inputs),
>              scope-expansion §2.12 (logging/journal/logrotate),
>              scope-expansion §2.6 (shell profile config),
>              scope-expansion §unified recipe shape (config_templates)

---

## Overview

Some tools need configuration files written after installation.
This is not just "install the binary" — the tool won't work
without proper config.

### Why config files matter

| Tool | Config file | Without it |
|------|-----------|-----------|
| Docker | `/etc/docker/daemon.json` | Uses defaults (may not be optimal) |
| nginx | `/etc/nginx/nginx.conf` | Won't serve the right content |
| journald | `/etc/systemd/journald.conf.d/` | Logs grow unbounded |
| logrotate | `/etc/logrotate.d/TOOL` | Log files fill disk |
| sshd | `/etc/ssh/sshd_config` | Security risk with defaults |
| Prometheus | `/etc/prometheus/prometheus.yml` | No scrape targets |

### Phase 2 vs Phase 8

| Phase | Config capability |
|-------|------------------|
| Phase 2 | No config file management. Docker daemon.json not written (uses defaults). |
| Phase 3 | Docker post-install could write basic daemon.json. |
| Phase 8 | Full config template system: user inputs, templates, validation, post-write commands. |

---

## Config Template Schema

### Recipe format

```python
"config_templates": {
    "template_id": {
        "file": str,               # absolute path to write
        "template": str,           # content with {var} placeholders
        "inputs": list[dict],      # user-provided values
        "needs_sudo": bool,        # write needs root?
        "post_command": list[str], # run after writing
        "condition": str | None,   # only write if condition met
        "backup": bool,            # back up existing file first
        "mode": str,               # file permissions ("0644")
        "owner": str | None,       # file owner ("root:root")
        "format": str,             # "ini" | "json" | "yaml" | "raw"
    },
}
```

### Schema fields

| Field | Type | Required | Purpose |
|-------|------|----------|---------|
| `file` | str | ✅ | Absolute path to write |
| `template` | str | ✅ | Content with `{var}` placeholders |
| `inputs` | list | ❌ | User-provided values for template |
| `needs_sudo` | bool | ✅ | Whether write needs root |
| `post_command` | list | ❌ | Command to run after writing |
| `condition` | str | ❌ | System condition to check |
| `backup` | bool | ❌ | Back up existing file before overwrite |
| `mode` | str | ❌ | File permissions (default "0644") |
| `owner` | str | ❌ | File owner (default: current user) |
| `format` | str | ❌ | For validation: "json", "ini", "yaml", "raw" |

---

## User Inputs

### Input types

```python
"inputs": [
    {
        "id": "docker_storage_driver",
        "label": "Storage Driver",
        "type": "select",
        "options": ["overlay2", "btrfs", "devicemapper"],
        "default": "overlay2",
        "description": "overlay2 is recommended for most systems",
    },
    {
        "id": "port",
        "label": "Listen Port",
        "type": "number",
        "default": 8080,
        "validation": {"min": 1, "max": 65535},
    },
    {
        "id": "data_dir",
        "label": "Data Directory",
        "type": "path",
        "default": "/var/lib/myapp",
    },
    {
        "id": "log_level",
        "label": "Log Level",
        "type": "select",
        "options": ["debug", "info", "warn", "error"],
        "default": "info",
    },
    {
        "id": "enable_tls",
        "label": "Enable TLS",
        "type": "boolean",
        "default": True,
    },
]
```

### Input type catalog

| Type | Widget | Validation |
|------|--------|-----------|
| `select` | Dropdown | Value must be in `options` list |
| `number` | Number input | `min`, `max` range check |
| `text` | Text input | `pattern` regex, `min_length`, `max_length` |
| `path` | Path input | Must be valid path, optionally check exists |
| `boolean` | Toggle/checkbox | True or False |
| `password` | Password input | Not logged, not stored in plan |

### Variable substitution

```python
def _render_template(template: str, inputs: dict) -> str:
    """Substitute {var} placeholders with input values."""
    result = template
    for key, value in inputs.items():
        result = result.replace(f"{{{key}}}", str(value))
    return result
```

### Validation

```python
def _validate_input(input_def: dict, value) -> str | None:
    """Validate a single input. Returns error message or None."""
    if input_def["type"] == "number":
        v = input_def.get("validation", {})
        if "min" in v and value < v["min"]:
            return f"Must be >= {v['min']}"
        if "max" in v and value > v["max"]:
            return f"Must be <= {v['max']}"
    elif input_def["type"] == "select":
        if value not in input_def["options"]:
            return f"Must be one of: {input_def['options']}"
    elif input_def["type"] == "path":
        if not value.startswith("/"):
            return "Must be an absolute path"
    return None
```

Validation runs client-side (frontend) AND server-side (before write).

---

## Config File Examples

### Docker daemon.json

```python
"docker_config": {
    "file": "/etc/docker/daemon.json",
    "format": "json",
    "template": '''{
  "storage-driver": "{docker_storage_driver}",
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "{log_max_size}",
    "max-file": "{log_max_files}"
  }
}''',
    "inputs": [
        {"id": "docker_storage_driver", "label": "Storage Driver",
         "type": "select", "options": ["overlay2", "btrfs", "devicemapper"],
         "default": "overlay2"},
        {"id": "log_max_size", "label": "Max log size per container",
         "type": "select", "options": ["10m", "50m", "100m", "500m"],
         "default": "50m"},
        {"id": "log_max_files", "label": "Max log files per container",
         "type": "select", "options": ["1", "3", "5", "10"],
         "default": "3"},
    ],
    "needs_sudo": True,
    "post_command": ["systemctl", "restart", "docker"],
    "condition": "has_systemd",
    "backup": True,
    "mode": "0644",
    "owner": "root:root",
}
```

### journald configuration

```python
"journald_config": {
    "file": "/etc/systemd/journald.conf.d/custom.conf",
    "format": "ini",
    "template": "[Journal]\nSystemMaxUse={journal_max_size}\nCompress=yes\nRateLimitBurst={rate_limit}\n",
    "inputs": [
        {"id": "journal_max_size", "label": "Max journal size",
         "type": "select", "options": ["100M", "500M", "1G", "2G"],
         "default": "500M"},
        {"id": "rate_limit", "label": "Rate limit burst",
         "type": "number", "default": 1000,
         "validation": {"min": 100, "max": 100000}},
    ],
    "needs_sudo": True,
    "post_command": ["systemctl", "restart", "systemd-journald"],
    "condition": "has_systemd",
    "mode": "0644",
}
```

### logrotate configuration

```python
"logrotate_config": {
    "file": "/etc/logrotate.d/{tool_name}",
    "format": "raw",
    "template": """{log_path} {
    daily
    rotate {rotate_count}
    compress
    delaycompress
    missingok
    notifempty
    create 0640 {log_user} {log_group}
}
""",
    "inputs": [
        {"id": "log_path", "label": "Log file path",
         "type": "path", "default": "/var/log/{tool_name}.log"},
        {"id": "rotate_count", "label": "Days to keep",
         "type": "number", "default": 14,
         "validation": {"min": 1, "max": 365}},
        {"id": "log_user", "label": "Log file owner",
         "type": "text", "default": "root"},
        {"id": "log_group", "label": "Log file group",
         "type": "text", "default": "adm"},
    ],
    "needs_sudo": True,
    "mode": "0644",
}
```

### nginx virtual host

```python
"nginx_vhost": {
    "file": "/etc/nginx/sites-available/{site_name}",
    "format": "raw",
    "template": """server {
    listen {port};
    server_name {server_name};
    root {document_root};

    location / {
        try_files $uri $uri/ =404;
    }
}
""",
    "inputs": [
        {"id": "site_name", "label": "Site name",
         "type": "text", "default": "default"},
        {"id": "port", "label": "Listen port",
         "type": "number", "default": 80,
         "validation": {"min": 1, "max": 65535}},
        {"id": "server_name", "label": "Server name",
         "type": "text", "default": "_"},
        {"id": "document_root", "label": "Document root",
         "type": "path", "default": "/var/www/html"},
    ],
    "needs_sudo": True,
    "post_command": ["bash", "-c",
                     "ln -sf /etc/nginx/sites-available/{site_name} "
                     "/etc/nginx/sites-enabled/ && nginx -t && "
                     "systemctl reload nginx"],
    "condition": "has_systemd",
    "backup": True,
}
```

---

## Config File Write Pipeline

### Steps

```
1. CHECK CONDITION
   └── Does the condition match? (has_systemd, etc.)
   └── If not: skip this config template

2. COLLECT INPUTS
   └── Present input form to user
   └── Pre-fill with defaults
   └── Validate client-side

3. VALIDATE INPUTS (server-side)
   └── Type checks, range checks, pattern checks
   └── Return errors if invalid

4. RENDER TEMPLATE
   └── Substitute {var} placeholders with input values
   └── Result is the final file content

5. VALIDATE OUTPUT (format-aware)
   └── JSON: json.loads() to verify valid JSON
   └── YAML: yaml.safe_load() to verify valid YAML
   └── INI: configparser to verify valid INI
   └── Raw: no validation (logrotate, nginx)

6. BACKUP EXISTING (if backup=True)
   └── cp FILE FILE.backup.TIMESTAMP

7. WRITE FILE
   └── Write content to file path
   └── Set permissions (mode)
   └── Set owner (chown)
   └── Needs sudo if needs_sudo=True

8. POST-COMMAND (if specified)
   └── Run post_command (e.g., systemctl restart)
   └── Verify command succeeded
```

### Error handling

| Step | Failure | Recovery |
|------|---------|----------|
| Condition check | Condition not met | Skip template, log why |
| Input validation | Invalid value | Show error, ask user to fix |
| Template render | Missing variable | Error — recipe bug |
| Output validation | Invalid JSON/YAML | Show parse error, ask user to fix inputs |
| Backup | Can't backup (permissions) | Warn, proceed with caution |
| Write file | Permission denied | Need sudo, or wrong path |
| Post-command | Service restart fails | Show error, suggest manual check |

---

## Config File Locations

### Standard locations per tool

| Tool | Config file | Format |
|------|-----------|--------|
| Docker | `/etc/docker/daemon.json` | JSON |
| journald | `/etc/systemd/journald.conf.d/*.conf` | INI |
| logrotate | `/etc/logrotate.d/TOOL` | custom (logrotate syntax) |
| nginx | `/etc/nginx/nginx.conf`, `/etc/nginx/sites-available/` | custom |
| sshd | `/etc/ssh/sshd_config` | key-value |
| Prometheus | `/etc/prometheus/prometheus.yml` | YAML |
| Grafana | `/etc/grafana/grafana.ini` | INI |
| rsyslog | `/etc/rsyslog.d/TOOL.conf` | custom |

### Drop-in directories

Many services support "drop-in" config files:

| Service | Drop-in dir | Priority |
|---------|------------|---------|
| journald | `/etc/systemd/journald.conf.d/` | Overrides main conf |
| systemd units | `/etc/systemd/system/SERVICE.d/` | Extends unit |
| logrotate | `/etc/logrotate.d/` | One file per tool |
| rsyslog | `/etc/rsyslog.d/` | Loaded alphabetically |
| nginx | `/etc/nginx/conf.d/` | Loaded alphabetically |

**Drop-in advantage:** We write a SEPARATE file, never editing
the main config. This is safer—our file can be removed cleanly.

---

## Shell Profile Configuration

### Special case: PATH and environment

Some tools need PATH or environment variable additions:

```python
"shell_config": {
    "type": "shell_profile",
    "lines": [
        'export PATH="$HOME/.cargo/bin:$PATH"',
        'eval "$(rustup completions bash)"',
    ],
    "target": "auto",  # auto-detect .bashrc, .zshrc, .profile
}
```

This is documented in detail in domain-shells §profile files.

---

## Conditions

### Available conditions

| Condition | What it checks | Source |
|-----------|---------------|--------|
| `has_systemd` | `capabilities.has_systemd == True` | Fast profile |
| `has_openrc` | `init_system.type == "openrc"` | Phase 4 profile |
| `has_docker` | `shutil.which("docker")` | Binary check |
| `is_root` | `os.geteuid() == 0` | Runtime |
| `file_exists:PATH` | `os.path.isfile(PATH)` | Runtime |
| `not_container` | `container.in_container == False` | Fast profile |

### Condition evaluation

```python
def _evaluate_condition(condition: str, profile: dict) -> bool:
    if condition == "has_systemd":
        return profile["capabilities"]["has_systemd"]
    if condition == "has_openrc":
        return profile.get("init_system", {}).get("type") == "openrc"
    if condition.startswith("file_exists:"):
        path = condition.split(":", 1)[1]
        return os.path.isfile(path)
    # ... etc
```

---

## Edge Cases

| Case | Impact | Handling |
|------|--------|---------|
| File already exists | Overwrite could lose custom config | Backup before write (backup=True) |
| No permission to write | Config write fails | Check permissions before writing |
| Drop-in dir doesn't exist | Write fails | Create dir with `mkdir -p` |
| Invalid template output | Broken config → service crash | Format-aware validation before write |
| Post-command fails | Service doesn't reload | Show error, don't rollback file |
| Container: no systemd | journald config irrelevant | Condition check skips it |
| Read-only filesystem | Write fails | Detect read-only, skip config |
| Conflicting configs | Multiple drop-in files conflict | Include precedence documentation |
| Config references missing path | Service fails to start | Validate paths exist |

---

## Phase Roadmap

| Phase | Config file capability |
|-------|----------------------|
| Phase 2 | No config file management |
| Phase 3 | Basic Docker daemon.json (hardcoded, no inputs) |
| Phase 4 | Input framework for user-provided values |
| Phase 8 | Full template system: all features above |

---

## Traceability

| Topic | Source |
|-------|--------|
| Input types (select, number, path) | scope-expansion §2.2 |
| Variable substitution in commands | scope-expansion §2.2 |
| Client + server validation | scope-expansion §2.2 |
| Docker daemon.json example | scope-expansion §2.2 (post_install) |
| journald config template | scope-expansion §2.12 |
| logrotate config template | scope-expansion §2.12 |
| config_templates in recipe shape | scope-expansion §unified recipe |
| Shell profile config | scope-expansion §2.6, domain-shells |
| has_systemd condition | arch-system-model §capabilities |
| Service restart after config | domain-services §systemd commands |
| Phase 8 roadmap | scope-expansion §Phase 8 |
