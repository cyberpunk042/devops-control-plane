# K8s Wizard — Configure Step Deep Plan

## STATUS: Active plan for focused implementation

---

## 0. WHAT EXISTS TODAY vs WHAT SHOULD EXIST

### Current state (as of Phase 2 "done"):

The configure step has three rendering paths:
- **Compose-based path**: Per-service card with checkbox + 4 editable fields (image, port, replicas, service type). One `<details>` block titled "Advanced Settings" showing READ-ONLY displays of healthcheck, resources, env keys, volumes, deps.
- **Module-based path**: Per-module card with checkbox + 4 editable fields. No advanced settings at all.
- **Manual path**: Single card with name + image + port + replicas + service type.

Infrastructure services: Radio buttons (StatefulSet / Managed / Skip) with NO conditional panels. Clicking a radio does nothing visible.

Cluster settings: Namespace text input, output dir text input, ingress checkbox, configmap checkbox. No reveal logic.

**collect()**: Gathers basic fields only. Advanced settings are never collected because they aren't editable.

**TL;DR: The step looks like a form, but it's a facade. 80% of the planned functionality is missing.**

---

## 1. SUB-FEATURES — ORDERED BY IMPLEMENTATION PRIORITY

Each sub-feature is a self-contained unit of work that can be implemented, tested, and verified independently. Dependencies are noted.

### 1A. Application Service Card — Primary Row Enhancement

**What changes:** Add Update Strategy select to the primary row.

**Compose data available:**
- No direct compose equivalent (compose doesn't have K8s strategy concepts)

**UI controls:**
```
Current:   [Image ──────────────] [Port] [Replicas] [Service Type ▾]
Enhanced:  [Image ──────────────] [Port] [Replicas] [Service Type ▾] [Strategy ▾]
```

**Strategy select options:**
| Value | Label | Description |
|-------|-------|-------------|
| `RollingUpdate` | RollingUpdate (default) | Zero-downtime, gradual rollout |
| `Recreate` | Recreate | Kill all → start all (for stateful single-instance) |

**Pre-fill logic:**
- Default: `RollingUpdate` always (safe default)
- If compose service has `deploy.replicas: 1` → suggest `Recreate` (single instance, likely stateful)
- If compose service uses named volumes with data → suggest `Recreate` (data consistency)

**When `RollingUpdate` selected:** Show inline sub-fields:
```
maxSurge [1]   maxUnavailable [1]
```
**When `Recreate` selected:** No sub-fields.

**Grid change:** `3fr 1fr 1fr 1fr` → `3fr 1fr 1fr 1fr 1fr` (5 columns). Or better: 2-row grid:
```
Row 1: [Image ──────────────────────────] [Port]
Row 2: [Replicas] [Service Type ▾] [Strategy ▾] [maxSurge?] [maxUnavail?]
```

**collect():**
```javascript
strategy: _sel(`k8s-svc-strategy-${i}`) || 'RollingUpdate',
maxSurge: strategy === 'RollingUpdate' ? (_val(`k8s-svc-maxsurge-${i}`) || '1') : null,
maxUnavailable: strategy === 'RollingUpdate' ? (_val(`k8s-svc-maxunavail-${i}`) || '1') : null,
```

**Backend:** `generate_k8s_wizard` Deployment spec doesn't include strategy. The `_DEPLOYMENT_TEMPLATE` hardcodes `RollingUpdate` with `maxUnavailable: 1, maxSurge: 1`. The wizard will need to generate YAML that includes the strategy block.

**Dependencies:** None. Self-contained.

---

### 1B. Application Service Card — `<details>` Resource Limits

**What changes:** Replace read-only resource display with editable inputs.

**Compose data available:**
```python
svc["deploy"] = {
    "replicas": int | None,
    "cpu_limit": str | None,      # e.g. "500m", "1.0"
    "memory_limit": str | None,   # e.g. "256Mi", "1Gi"
    "cpu_request": str | None,    # e.g. "100m"
    "memory_request": str | None, # e.g. "128Mi"
}
```

**UI controls:**
```
▸ Resource Limits
  ┌─────────────────────────────────────────────────────────┐
  │ CPU              Memory                                  │
  │ Request [100m ]  Request [128Mi ]                        │
  │ Limit   [500m ]  Limit   [256Mi ]                        │
  └─────────────────────────────────────────────────────────┘
```

4-cell grid:
- `k8s-svc-cpu-req-{i}` — text input, placeholder "100m"
- `k8s-svc-cpu-lim-{i}` — text input, placeholder "500m"
- `k8s-svc-mem-req-{i}` — text input, placeholder "128Mi"
- `k8s-svc-mem-lim-{i}` — text input, placeholder "256Mi"

**Pre-fill logic:**
1. If compose `deploy.cpu_limit` exists → fill `cpu-lim`
2. If compose `deploy.cpu_request` exists → fill `cpu-req`; else if `cpu_limit` exists → fill with `cpu_limit` (K8s defaults requests to limits)
3. Same for memory
4. If no compose deploy block → leave ALL empty (placeholders only)
5. Empty = "not set" = omit from manifest (let K8s defaults apply)

**K8s value format rules:**
- CPU: millicores string, e.g. `"100m"` = 0.1 CPU, `"1"` = 1 CPU, `"1500m"` = 1.5 CPU
- Memory: bytes with suffix, e.g. `"128Mi"`, `"1Gi"`, `"256M"` (Mi = mebibytes, M = megabytes)

**Validation:**
- If limit is set, request should be ≤ limit (warn, don't block)
- Values must be valid K8s resource quantity format (regex: `/^\d+(\.\d+)?(m|Mi|Gi|Ki|M|G|K)?$/`)
- Empty is valid (omit from manifest)

**collect():**
```javascript
resources: {
    cpu_request: _val(`k8s-svc-cpu-req-${i}`) || null,
    cpu_limit: _val(`k8s-svc-cpu-lim-${i}`) || null,
    memory_request: _val(`k8s-svc-mem-req-${i}`) || null,
    memory_limit: _val(`k8s-svc-mem-lim-${i}`) || null,
}
```
Store as `svc.resources` in the services array.

**Review display:**
```
🔧 Resources: api     CPU 100m–500m / Mem 128Mi–256Mi     [create]
```
Only show if any resource value is set.

**Backend compatibility:**
- `generate_k8s_wizard` already supports `spec.cpu_limit`, `spec.memory_limit`, `spec.cpu_request`, `spec.memory_request` ✅
- `_DEPLOYMENT_TEMPLATE` hardcodes `100m/500m CPU, 128Mi/256Mi mem` — wizard should use `generate_k8s_wizard` instead

**Dependencies:** None. Self-contained.

---

### 1C. Application Service Card — `<details>` Health Checks

**What changes:** Replace read-only compose healthcheck with editable K8s probe configuration.

**Compose data available:**
```python
svc["healthcheck"] = {
    "test": str | None,       # e.g. "curl -f http://localhost:8080/health || exit 1"
    "interval": str | None,   # e.g. "30s"
    "timeout": str | None,    # e.g. "10s"
    "retries": int | None,    # e.g. 3
}
```

**K8s probe types (what we generate):**
```yaml
# HTTP GET probe
livenessProbe:
  httpGet:
    path: /health
    port: 8080
  initialDelaySeconds: 10
  periodSeconds: 15
  failureThreshold: 3
  timeoutSeconds: 5

# TCP Socket probe
readinessProbe:
  tcpSocket:
    port: 8080
  initialDelaySeconds: 5
  periodSeconds: 5

# Exec probe
livenessProbe:
  exec:
    command: ["sh", "-c", "pg_isready -U postgres"]
  initialDelaySeconds: 10
```

**Compose → K8s translation logic:**
This is the complex part. Compose healthcheck `test` string needs parsing:

```javascript
function _parseComposeHealthcheck(hc, port) {
    if (!hc || !hc.test) return { type: 'http', path: '/health', port: port };

    const test = hc.test;

    // Pattern: "curl -f http://localhost:PORT/PATH"
    const curlMatch = test.match(/curl\s+.*http[s]?:\/\/localhost:?(\d+)?(\/\S*)?/i);
    if (curlMatch) {
        return {
            type: 'http',
            path: curlMatch[2] || '/health',
            port: parseInt(curlMatch[1]) || port,
        };
    }

    // Pattern: "wget --spider http://localhost:PORT/PATH"
    const wgetMatch = test.match(/wget\s+.*http[s]?:\/\/localhost:?(\d+)?(\/\S*)?/i);
    if (wgetMatch) {
        return {
            type: 'http',
            path: wgetMatch[2] || '/health',
            port: parseInt(wgetMatch[1]) || port,
        };
    }

    // Pattern: "pg_isready" / "mysqladmin ping" / "redis-cli ping"
    if (/pg_isready|mysqladmin\s+ping|redis-cli\s+ping|mongo.*--eval/.test(test)) {
        return { type: 'exec', command: test };
    }

    // Pattern: "nc -z localhost PORT" / generic TCP check
    const tcpMatch = test.match(/nc\s+-z\s+\S+\s+(\d+)/);
    if (tcpMatch) {
        return { type: 'tcp', port: parseInt(tcpMatch[1]) || port };
    }

    // Fallback: exec with the raw command
    return { type: 'exec', command: test };
}
```

**Compose interval → K8s fields translation:**
```
compose.interval (e.g. "30s") → periodSeconds: 30
compose.timeout  (e.g. "10s") → timeoutSeconds: 10
compose.retries  (e.g. 3)     → failureThreshold: 3
No compose equivalent         → initialDelaySeconds: 10 (reasonable default)
```

**UI controls:**
```
▸ Health Checks
  ┌─────────────────────────────────────────────────────────┐
  │ ☑ Enable readiness probe                                │
  │   Type [HTTP GET ▾]  Path [/health]  Port [8080]        │
  │   Initial delay [5 ]s  Period [5 ]s  Timeout [3 ]s      │
  │                                                          │
  │ ☑ Enable liveness probe                                 │
  │   Type [HTTP GET ▾]  Path [/health]  Port [8080]        │
  │   Initial delay [10]s  Period [15]s  Failure threshold [3]│
  │                                                          │
  │   💡 Pre-filled from: curl -f http://localhost:8080/health│
  └─────────────────────────────────────────────────────────┘
```

**Per-probe controls (6 fields × 2 probes = 12 fields per service):**

Readiness probe:
- `k8s-svc-ready-enable-{i}` — checkbox (default: checked if compose healthcheck exists OR always checked)
- `k8s-svc-ready-type-{i}` — select: `http` | `tcp` | `exec`
- `k8s-svc-ready-path-{i}` — text, shown only for `http` type
- `k8s-svc-ready-port-{i}` — number, shown for `http` and `tcp`
- `k8s-svc-ready-delay-{i}` — number (initialDelaySeconds), default 5
- `k8s-svc-ready-period-{i}` — number (periodSeconds), default 5
- `k8s-svc-ready-timeout-{i}` — number (timeoutSeconds), default 3
- `k8s-svc-ready-cmd-{i}` — text, shown only for `exec` type

Liveness probe:
- `k8s-svc-live-enable-{i}` — checkbox
- `k8s-svc-live-type-{i}` — select
- `k8s-svc-live-path-{i}` — text
- `k8s-svc-live-port-{i}` — number
- `k8s-svc-live-delay-{i}` — number, default 10
- `k8s-svc-live-period-{i}` — number, default 15
- `k8s-svc-live-threshold-{i}` — number (failureThreshold), default 3
- `k8s-svc-live-cmd-{i}` — text

**Probe type select onchange:** show/hide path+port inputs vs command input:
```javascript
onchange="var t=this.value;
  var p=document.getElementById('k8s-svc-ready-path-row-${i}');
  var c=document.getElementById('k8s-svc-ready-cmd-row-${i}');
  if(p)p.style.display=t==='http'?'grid':'none';
  if(c)c.style.display=t==='exec'?'block':'none';
  var portEl=document.getElementById('k8s-svc-ready-port-${i}');
  if(portEl)portEl.parentElement.style.display=(t==='http'||t==='tcp')?'block':'none';"
```

**Pre-fill from compose:**
1. Parse compose healthcheck → get type, path, port
2. Apply to BOTH readiness AND liveness probes (compose doesn't distinguish)
3. For readiness: initialDelay=5, period=5 (fast, for traffic routing)
4. For liveness: initialDelay=10, period=compose.interval (slower, for restart decisions)
5. If no compose healthcheck: enable both probes anyway with defaults (http, /health, service port)

**collect():**
```javascript
probes: {
    readiness: readyEnabled ? {
        type: _sel(`k8s-svc-ready-type-${i}`),
        path: type === 'http' ? _val(`k8s-svc-ready-path-${i}`) : null,
        port: type !== 'exec' ? parseInt(_val(`k8s-svc-ready-port-${i}`)) : null,
        command: type === 'exec' ? _val(`k8s-svc-ready-cmd-${i}`) : null,
        initialDelaySeconds: parseInt(_val(`k8s-svc-ready-delay-${i}`)) || 5,
        periodSeconds: parseInt(_val(`k8s-svc-ready-period-${i}`)) || 5,
        timeoutSeconds: parseInt(_val(`k8s-svc-ready-timeout-${i}`)) || 3,
    } : null,
    liveness: liveEnabled ? {
        type: _sel(`k8s-svc-live-type-${i}`),
        path: ...,
        port: ...,
        command: ...,
        initialDelaySeconds: ...,
        periodSeconds: ...,
        failureThreshold: parseInt(_val(`k8s-svc-live-threshold-${i}`)) || 3,
    } : null,
}
```

**Validation:**
- If HTTP probe: path must start with `/`
- If TCP probe: port must be > 0
- If exec: command must not be empty
- initialDelay > 0, period > 0

**Review display:**
```
🏥 Probes: api     readiness: HTTP /health :8080 / liveness: HTTP /health :8080     [create]
```

**Backend compatibility:**
- `generate_k8s_wizard` does NOT include probes in Deployment spec. Would need enhancement, OR we generate raw YAML in the preview step.
- `_DEPLOYMENT_TEMPLATE` hardcodes `/health` probes but only uses `{port}`.

**Dependencies:** None directly. But interacts with the port field (probe port defaults to service port).

---

### 1D. Application Service Card — `<details>` Environment Variables

**STATUS: REVISED — Proper K8s environment management architecture**

**What changes:** Replace read-only chip display (and the naive two-textarea approach)
with a per-variable row interface giving the user full control over injection type.

---

#### K8s Environment Management — The Three Native Mechanisms

In Kubernetes, container configuration injection has three first-class patterns:

1. **ConfigMap** — Non-sensitive configuration as a dedicated K8s resource.
   Updated independently of Deployment. Referenced via `envFrom` or `configMapKeyRef`.
   Values can be literal (committed) or `${VAR}` substitution (resolved at deploy time).

2. **Secret** — Sensitive data as a dedicated K8s resource with tighter RBAC.
   Manifest contains `${VAR_NAME}` references — real values are NEVER in git.
   CI injects actual values at deploy time via `envsubst`, Skaffold, or Helm.

3. **Inline env** — Direct `value:` in the Deployment spec. Simple but inflexible.
   Couples config to workload definition. Change requires redeploying.

The standard Deployment pattern uses `envFrom` for bulk injection:
```yaml
spec:
  containers:
    - name: api
      envFrom:
        - configMapRef:
            name: api-config
        - secretRef:
            name: api-secrets
```

The ConfigMap checkbox in Cluster Settings is **removed** — ConfigMap and Secret
resources are generated automatically based on per-variable injection choices.

---

#### Per-Variable Injection Types (User Choice)

Each environment variable gets **three injection options**:

| Type | Icon | Value in manifest | Where it lives | Use when |
|------|------|-------------------|----------------|----------|
| **Hardcoded** | 📋 | Literal value | ConfigMap `data:` | Non-sensitive, same across envs. `PORT=3000` |
| **Variable** | 🔄 | `${VAR_NAME}` | ConfigMap `data:` | Non-sensitive but env-dependent. `NODE_ENV`, `LOG_LEVEL` |
| **Secret** | 🔒 | `${VAR_NAME}` | Secret `stringData:` | Sensitive. `DATABASE_PASSWORD`, `API_KEY` |

For **Variable** and **Secret** types, the user can also customize the
substitution variable name. Default: `${KEY_NAME}`. User can change to
`${CUSTOM_NAME}` if the CI secret has a different name than the env var key.

---

#### Compose Data Available

```python
svc["environment"] = {str: str}  # Already a normalized dict from docker_ops
```

#### Secret Classification

Uses the canonical `_SECRET_PATTERNS` from `vault_env_ops.py` / `secrets_ops.py`:
```javascript
const _SECRET_PATTERNS = [
    'key', 'secret', 'token', 'password', 'passwd', 'pass',
    'credential', 'auth', 'api_key', 'apikey', 'private',
    'jwt', 'cert', 'certificate', 'signing',
];
const _isSecretKey = (key) => {
    const lower = key.toLowerCase();
    return _SECRET_PATTERNS.some(p => lower.includes(p));
};
```
Same algorithm as backend — substring match on lowercased key name.

---

#### UI Design — Per-Variable Row Interface

```
▸ Environment Variables (8 from Compose)
  ┌──────────────────────────────────────────────────────────────────────┐
  │                                                                      │
  │ 📌 Multi-env project: values shown are defaults.                     │
  │    Use "Variable" for values that differ across dev/staging/prod.    │
  │                                                                      │
  │ Key               Value              Var Name          Injection     │
  │ ────────────────  ──────────────────  ──────────────── ───────────── │
  │ [PORT           ] [3000            ]                   [📋 Hardcoded ▾] │
  │ [LOG_LEVEL      ] [info            ]                   [📋 Hardcoded ▾] │
  │ [NODE_ENV       ] [production      ] [${NODE_ENV}    ] [🔄 Variable  ▾] │
  │ [DB_HOST        ] [postgres        ]                   [📋 Hardcoded ▾] │
  │ [DB_NAME        ] [myapp           ]                   [📋 Hardcoded ▾] │
  │ [DB_PASSWORD    ] [••••••••        ] [${DB_PASSWORD} ] [🔒 Secret    ▾] ✕│
  │ [API_KEY        ] [••••••••        ] [${API_KEY}     ] [🔒 Secret    ▾] ✕│
  │ [JWT_SECRET     ] [••••••••        ] [${JWT_SECRET}  ] [🔒 Secret    ▾] ✕│
  │                                                                      │
  │ [+ Add variable]                                                     │
  │                                                                      │
  │ ─── Summary ───────────────────────────────────────────────────────  │
  │ 📋 ConfigMap api-config: 4 hardcoded, 1 variable (${VAR})           │
  │ 🔒 Secret api-secrets: 3 keys (values via ${VAR} at deploy time)    │
  │ Deployment: envFrom → configMapRef + secretRef                       │
  └──────────────────────────────────────────────────────────────────────┘
```

**Column layout (4-column grid):**
```
[Key: 2fr] [Value: 2fr] [VarName: 1.5fr] [Type: 1.2fr] [✕]
```

**Multi-env banner:** Only shown when `configData.environments.length > 1`.
Hidden for single-env projects.

---

#### Per-Row Behavior by Injection Type

**When `📋 Hardcoded` selected:**
- Key: editable text input
- Value: editable text input, shows literal value
- Var Name column: hidden (no substitution)
- This value goes as-is into ConfigMap: `PORT: "3000"`

**When `🔄 Variable` selected:**
- Key: editable text input
- Value: editable text input, shows default/base value (reference for user)
- Var Name: editable text input, defaults to `${KEY_NAME}`, user can customize
- ConfigMap will contain: `NODE_ENV: "${NODE_ENV}"` — resolved at deploy time

**When `🔒 Secret` selected:**
- Key: editable text input
- Value: masked (•••) or dimmed, shows compose value for reference but NOT used in manifest
- Var Name: editable text input, defaults to `${KEY_NAME}`, user can customize
- Secret will contain: `DB_PASSWORD: "${DB_PASSWORD}"` — resolved at deploy time
- Slightly different visual treatment (muted background or left border) to distinguish

**Var Name column visibility:**
- Hidden when type is `Hardcoded` (no substitution needed)
- Shown when type is `Variable` or `Secret`
- Implemented via `onchange` handler on the type select toggling display

---

#### Pre-fill Logic

1. Parse compose `environment` dict into var list
2. For each key, classify using `_isSecretKey()`:
   - Returns `true` → default injection type: **Secret**
   - Returns `false` → default injection type depends on env mode:
     - **Single-env project** (0-1 environments): **Hardcoded**
     - **Multi-env project** (2+ environments):
       - Known env-dependent keys (`NODE_ENV`, `APP_ENV`, `LOG_LEVEL`, `DEBUG`,
         `ENVIRONMENT`, `STAGE`) → **Variable**
       - Everything else → **Hardcoded**
3. Var Name: defaults to `${KEY_NAME}` for Variable/Secret types
4. Value: compose value as-is
5. User can override EVERYTHING — full control per variable

```javascript
const _ENV_DEPENDENT_KEYS = new Set([
    'node_env', 'app_env', 'environment', 'env',
    'log_level', 'debug', 'stage', 'deploy_env',
]);

function _defaultInjectionType(key, isMultiEnv) {
    if (_isSecretKey(key)) return 'secret';
    if (isMultiEnv && _ENV_DEPENDENT_KEYS.has(key.toLowerCase())) return 'variable';
    return 'hardcoded';
}
```

---

#### IDs Per Row

For service index `i`, variable index `j`:
- `k8s-svc-env-key-${i}-${j}` — key name text input
- `k8s-svc-env-val-${i}-${j}` — value text input
- `k8s-svc-env-var-${i}-${j}` — substitution variable name text input
- `k8s-svc-env-type-${i}-${j}` — injection type select
- `k8s-svc-env-varbox-${i}-${j}` — container div for var name (toggled by type)

Add variable button: `k8s-svc-env-add-${i}`
Variable list container: `k8s-svc-env-list-${i}`

---

#### Type Select `onchange` Handler

```javascript
onchange="((sel) => {
    const j = sel.dataset.j, i = sel.dataset.i;
    const varBox = document.getElementById('k8s-svc-env-varbox-' + i + '-' + j);
    const valEl = document.getElementById('k8s-svc-env-val-' + i + '-' + j);
    const isSubst = sel.value !== 'hardcoded';
    if (varBox) varBox.style.display = isSubst ? '' : 'none';
    // For secret: dim the value field
    if (valEl) {
        valEl.style.opacity = sel.value === 'secret' ? '0.4' : '1';
        valEl.type = sel.value === 'secret' ? 'password' : 'text';
    }
    // Update summary
    _updateEnvSummary(i);
})(this)"
```

---

#### Add Variable Handler

```javascript
function _addEnvVar(i) {
    const list = document.getElementById('k8s-svc-env-list-' + i);
    if (!list) return;
    const j = list.children.length;  // next index
    const row = document.createElement('div');
    row.className = 'k8s-env-row';
    row.innerHTML = _envRowHtml(i, j, '', '', 'hardcoded', '');
    list.appendChild(row);
}
```

---

#### collect() Output

```javascript
svc.envVars = [];
const list = document.getElementById(`k8s-svc-env-list-${i}`);
if (list) {
    for (let j = 0; j < list.children.length; j++) {
        const key = _val(`k8s-svc-env-key-${i}-${j}`);
        if (!key) continue;  // skip empty rows
        const type = _sel(`k8s-svc-env-type-${i}-${j}`) || 'hardcoded';
        const value = _val(`k8s-svc-env-val-${i}-${j}`) || '';
        const varName = (type !== 'hardcoded')
            ? (_val(`k8s-svc-env-var-${i}-${j}`) || '${' + key + '}')
            : null;
        svc.envVars.push({ key, type, value, varName });
    }
}
```

Produces per service:
```javascript
svc.envVars = [
    { key: "PORT",       type: "hardcoded", value: "3000",       varName: null },
    { key: "NODE_ENV",   type: "variable",  value: "production", varName: "${NODE_ENV}" },
    { key: "DB_PASSWORD",type: "secret",    value: "changeme",   varName: "${DB_PASSWORD}" },
    { key: "API_KEY",    type: "secret",    value: "",           varName: "${API_KEY}" },
]
```

---

#### What Gets Generated (Downstream — Backend)

From `svc.envVars`, the backend generates **three resources per service** (if applicable):

**1. ConfigMap** (if any hardcoded or variable-typed vars exist):
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: api-config
  namespace: default
data:
  PORT: "3000"                    # hardcoded — literal value
  LOG_LEVEL: "info"               # hardcoded — literal value
  NODE_ENV: "${NODE_ENV}"         # variable — substituted at deploy time
```

**2. Secret** (if any secret-typed vars exist):
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: api-secrets
  namespace: default
type: Opaque
stringData:
  DB_PASSWORD: "${DB_PASSWORD}"   # substituted at deploy time by CI
  API_KEY: "${API_KEY}"           # substituted at deploy time by CI
```

**3. Deployment** — container spec gets `envFrom` references:
```yaml
envFrom:
  - configMapRef:
      name: api-config
  - secretRef:
      name: api-secrets
```

The `envFrom` pattern (bulk injection) is the default. No individual
`valueFrom` entries unless the user needs key renaming (future enhancement).

**4. Multi-env + Kustomize** (if project has >1 environment):
- Base ConfigMap in `base/` with default values
- Per-env overlay patches that override variable-typed ConfigMap entries
  with environment-specific literal values
- Secret manifest stays the same (always `${VAR}` — CI supplies per-env values)

---

#### Review Step Display

```
📋 ConfigMap: api-config    4 hardcoded + 1 variable (${VAR})     [create]
🔒 Secret: api-secrets      3 keys (values via ${VAR} at deploy)  [create]
```

If no config vars → skip ConfigMap line. If no secret vars → skip Secret line.

---

#### Backend Compatibility — Changes Needed

Current `generate_k8s_wizard` status:
- ❌ Does NOT generate ConfigMap from env vars (only from explicit `spec.data`)
- ❌ Does NOT generate Secret resources
- ❌ Does NOT add `envFrom` to Deployment container spec
- ✅ Supports `spec.env` → inline env (but we want `envFrom` instead)

**Required backend additions:**
1. From `svc.envVars` → build ConfigMap resource with classified data
2. From `svc.envVars` → build Secret resource with `${VAR}` substitution values
3. In Deployment container spec → add `envFrom` refs instead of inline `env`
4. If multi-env: generate Kustomize overlay structure for ConfigMap patches

These changes happen when we implement this sub-feature. The data structure
from `collect()` contains everything the backend needs.

---

#### Dependencies

- **Removes** the `k8s-configmap` checkbox from Cluster Settings (ConfigMap is now
  auto-generated per service based on env var types, not a global toggle)
- Interacts with namespace from Cluster Settings (ConfigMap/Secret metadata.namespace)
- Multi-env awareness needs `configData.environments` from detect step
- Backend `generate_k8s_wizard` needs enhancement for ConfigMap, Secret, and envFrom
- Forward-compatible with Skaffold (optional feature, last in K8s config):
  when Skaffold enabled, it handles `${VAR}` substitution natively instead of `envsubst`

---

#### Skaffold Note

Skaffold integration is planned as the **last feature** in K8s configuration.
When enabled, Skaffold handles variable substitution natively via its
`envTemplate` and profile system. The per-variable data structure is identical
regardless of whether Skaffold is used — only the output format changes.
This will likely require a detect-step enhancement to check for Skaffold
configuration and offer it as an option in Cluster Settings.

---

### 1E. Application Service Card — `<details>` Volume Mounts

**What changes:** Replace read-only volume strings with checkboxes + editable mount paths + volume type selection.

**Compose data available:**
```python
svc["volumes"] = [str]  # e.g. ["./data:/app/data", "postgres-data:/var/lib/postgresql/data"]
```

**Compose volume types (from string format):**
```
"./data:/app/data"           → bind mount (host path : container path)
"postgres-data:/data"        → named volume (volume name : container path)
"/tmp/cache:/cache"          → absolute host path : container path
"mydata:/data:ro"            → named volume, read-only
```

**K8s volume concepts (translation target):**

| Compose type | K8s equivalent | Fields needed |
|-------------|---------------|---------------|
| Named volume | PersistentVolumeClaim | PVC name, size, access mode, storage class |
| Bind mount (`./src:/app/src`) | Skip (dev-only) OR emptyDir | None or just mount path |
| Bind mount (data dir) | PersistentVolumeClaim | PVC name, size, access mode |
| Read-only bind mount | ConfigMap mount or PVC (readOnly) | Depends on content |

**Volume classification heuristic:**
```javascript
function _classifyVolume(volStr) {
    const parts = volStr.split(':');
    const source = parts[0];
    const target = parts[1] || source;
    const flags = parts[2] || '';

    // Named volume (no path separator)
    if (!source.includes('/') && !source.startsWith('.')) {
        return { type: 'named', name: source, mountPath: target, readOnly: flags.includes('ro') };
    }

    // Bind mount — dev source (contains ./src, ./app, ./node_modules, etc.)
    if (/^\.\/(src|app|lib|pkg|cmd|internal|components|pages)/.test(source)) {
        return { type: 'dev-bind', source, mountPath: target, skip: true };
    }

    // Bind mount — data directory
    if (/^\.\/(data|db|storage|uploads|logs|backup)/.test(source) || /^\//.test(source)) {
        return { type: 'data-bind', source, mountPath: target, readOnly: flags.includes('ro') };
    }

    // Default: treat as dev bind (skip by default)
    return { type: 'dev-bind', source, mountPath: target, skip: true };
}
```

**UI controls:**
```
▸ Volume Mounts (3 from Compose)
  ┌─────────────────────────────────────────────────────────┐
  │ ☑ postgres-data → /var/lib/postgresql/data               │
  │   K8s type: [PVC ▾]  Size: [10Gi]  Access: [ReadWriteOnce ▾] │
  │                                                          │
  │ ☑ ./data → /app/data                                     │
  │   K8s type: [PVC ▾]  Size: [5Gi]  Access: [ReadWriteOnce ▾] │
  │                                                          │
  │ ☐ ./src → /app/src                    ⚠️ dev-only (skipped) │
  │                                                          │
  │ [+ Add volume mount]                                     │
  └─────────────────────────────────────────────────────────┘
```

**Per-volume controls:**
- `k8s-svc-vol-chk-{i}-{j}` — checkbox (checked=include, unchecked=skip)
- `k8s-svc-vol-path-{i}-{j}` — text input for mount path (pre-filled from compose)
- `k8s-svc-vol-type-{i}-{j}` — select: `pvc` | `emptyDir` | `hostPath` | `configmap`
- `k8s-svc-vol-size-{i}-{j}` — text input, shown only for `pvc`, e.g. "10Gi"
- `k8s-svc-vol-access-{i}-{j}` — select (for PVC): `ReadWriteOnce` | `ReadWriteMany` | `ReadOnlyMany`

**Pre-fill logic:**
1. Parse each compose volume string with `_classifyVolume()`
2. Named volumes → checked, type=PVC, size=10Gi (reasonable default)
3. Data bind mounts → checked, type=PVC, size=5Gi
4. Dev bind mounts → UNchecked, type=emptyDir, with "⚠️ dev-only" note
5. Mount path from compose target

**Type select onchange:**
- PVC: show size + access mode inputs
- emptyDir: show nothing (K8s manages)
- hostPath: show source path input (and ⚠️ warning about security)
- configmap: show configmap name input + items list

**collect():**
```javascript
volumes: parsedVolumes.filter((v, j) => {
    const chk = document.getElementById(`k8s-svc-vol-chk-${i}-${j}`);
    return chk && chk.checked;
}).map((v, j) => ({
    mountPath: _val(`k8s-svc-vol-path-${i}-${j}`) || v.mountPath,
    type: _sel(`k8s-svc-vol-type-${i}-${j}`) || 'pvc',
    size: _val(`k8s-svc-vol-size-${i}-${j}`) || null,
    accessMode: _sel(`k8s-svc-vol-access-${i}-${j}`) || 'ReadWriteOnce',
    name: v.name || `${svcName}-data-${j}`,
}))
```

**Manifest output:** Each PVC volume generates:
1. A `PersistentVolumeClaim` resource (separate file)
2. A `volumes:` entry in the Deployment pod spec
3. A `volumeMounts:` entry in the container spec

**Backend compatibility:**
- `generate_k8s_wizard` does NOT support volumes/PVCs. Would need a `PersistentVolumeClaim` kind handler.
- For now: volumes config is collected for the preview step; manifest YAML is generated client-side or via enhanced backend.

**Dependencies:**
- Named volumes from compose may also appear in infrastructure services (e.g. postgres-data)
- PVC names must be unique across all services

---

### 2A. Infrastructure Service Card — StatefulSet Reveal Panel

**What changes:** When "StatefulSet" radio is selected, show a configuration panel below the radios.

**Compose data available for infra services:**
```python
svc = {
    "name": "postgres",
    "image": "postgres:16-alpine",
    "ports": [{"host": 5432, "container": 5432, "protocol": "tcp"}],
    "environment": {"POSTGRES_DB": "app", "POSTGRES_USER": "app", "POSTGRES_PASSWORD": "secret"},
    "volumes": ["postgres-data:/var/lib/postgresql/data"],
    "healthcheck": {"test": "pg_isready -U app", ...},
}
```

**UI when "StatefulSet" selected:**
```
┌─ 🗄️ postgres ── postgres ── :5432 ── 💾1 ──────────────┐
│                                                          │
│ ○ StatefulSet (self-managed)  ● ← selected               │
│ ○ Managed (external)                                      │
│ ○ Skip                                                    │
│                                                          │
│ ┌─ StatefulSet Configuration ─────────────────────────┐  │
│ │ Image    [postgres:16-alpine ]  Port [5432]          │  │
│ │ Replicas [1]                                         │  │
│ │                                                      │  │
│ │ ▸ Persistent Storage                                 │  │
│ │   PVC Name     [postgres-data   ]                    │  │
│ │   Size         [10Gi            ]                    │  │
│ │   Access Mode  [ReadWriteOnce ▾ ]                    │  │
│ │   Mount Path   [/var/lib/postgresql/data]             │  │
│ │                                                      │  │
│ │ ▸ Environment (4 from Compose)                       │  │
│ │   ┌────────────────────────────────────────────────┐ │  │
│ │   │ POSTGRES_DB=app                                 │ │  │
│ │   │ POSTGRES_USER=app                               │ │  │
│ │   │ POSTGRES_PASSWORD=secret                        │ │  │
│ │   └────────────────────────────────────────────────┘ │  │
│ │                                                      │  │
│ │ ☑ Create headless Service (for DNS discovery)        │  │
│ └──────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

**Controls:**
- `k8s-infra-img-{i}` — text input, pre-filled from compose image
- `k8s-infra-port-{i}` — number input, pre-filled from compose port
- `k8s-infra-replicas-{i}` — number input, default 1
- `k8s-infra-pvc-name-{i}` — text, pre-filled from compose named volume or `{name}-data`
- `k8s-infra-pvc-size-{i}` — text, default "10Gi"
- `k8s-infra-pvc-access-{i}` — select: ReadWriteOnce (default)
- `k8s-infra-pvc-mount-{i}` — text, pre-filled from compose volume mount path
- `k8s-infra-env-{i}` — textarea, pre-filled from compose environment
- `k8s-infra-headless-{i}` — checkbox, default checked

**Radio onchange handler:**
```javascript
onchange="var panel=document.getElementById('k8s-infra-panel-${i}');
  var tfCta=document.getElementById('k8s-infra-tf-${i}');
  panel.style.display=this.value==='statefulset'?'block':'none';
  tfCta.style.display=this.value==='managed'?'block':'none';"
```
This requires ALL THREE radio inputs to have this handler.

**Generates (when StatefulSet):**
1. `StatefulSet` manifest (image, ports, env, volumeClaimTemplates)
2. `PersistentVolumeClaim` (if not using volumeClaimTemplates)
3. Headless `Service` (if checkbox checked) — `clusterIP: None`

**collect():**
```javascript
infraDecisions.push({
    name: infraSvcs[i].name,
    kind: 'StatefulSet',
    image: _val(`k8s-infra-img-${i}`) || infraSvcs[i].image,
    port: parseInt(_val(`k8s-infra-port-${i}`)) || '',
    replicas: parseInt(_val(`k8s-infra-replicas-${i}`)) || 1,
    pvc: {
        name: _val(`k8s-infra-pvc-name-${i}`) || `${name}-data`,
        size: _val(`k8s-infra-pvc-size-${i}`) || '10Gi',
        accessMode: _sel(`k8s-infra-pvc-access-${i}`) || 'ReadWriteOnce',
        mountPath: _val(`k8s-infra-pvc-mount-${i}`) || '',
    },
    environment: _parseEnv(`k8s-infra-env-${i}`),
    headlessService: document.getElementById(`k8s-infra-headless-${i}`)?.checked ?? true,
    _compose: infraSvcs[i],
});
```

**Dependencies:**
- PVC names must not conflict with app service PVCs
- Headless service adds an extra resource to the review step

---

### 2B. Infrastructure Service Card — Managed Reveal Panel

**What changes:** When "Managed" radio is selected, show a CTA panel with env var connection hints.

**UI when "Managed" selected:**
```
┌─ 🗄️ postgres ── postgres ── :5432 ──────────────────────┐
│                                                          │
│ ○ StatefulSet                                             │
│ ○ Managed (external)  ● ← selected                       │
│ ○ Skip                                                    │
│                                                          │
│ ┌─ Managed Service ──────────────────────────────────┐   │
│ │ 💡 This service will be provisioned externally      │   │
│ │    (e.g. AWS RDS, CloudSQL, ElastiCache).           │   │
│ │                                                     │   │
│ │ Connection env vars to set in your app:             │   │
│ │    DB_HOST → (your RDS endpoint)                    │   │
│ │    DB_PASSWORD → (from secrets manager)             │   │
│ │                                                     │   │
│ │ Set up Terraform to provision this → [Terraform ▸]  │   │
│ └─────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────┘
```

**Logic:**
1. Look at the app services' env vars for keys that reference this infra service name
   - e.g. if infra service is `postgres`, find app env vars containing `POSTGRES`, `DB_HOST`, `DATABASE_URL`
2. Show those as "connection env vars"
3. Terraform CTA → `wizardModalClose(); setTimeout(openTerraformSetupWizard, 300)`

**No collect needed** — managed services generate no K8s resources.

**Dependencies:**
- Cross-references app service env vars (needs 1D to be done first for env var data to be available)
- References Terraform wizard

---

### 3A. Cluster Settings — Live Namespace Dropdown

**What changes:** Replace plain text input with a select populated from `/api/k8s/namespaces` (if cluster connected), with "custom" option that reveals a text input.

**API available:**
```python
k8s_namespaces() → {"ok": True, "namespaces": [{"name": str, "status": str, "age": str}, ...]}
```

**UI:**
```
Namespace  [default       ▾]    ← populated from cluster + "custom..." option
           [custom-ns      ]    ← text input, shown only when "custom..." selected
```

**Fallback (no cluster):** Just a text input (like now), since we can't query namespaces.

**Pre-fill:** Smart default from project environments (already done).

**Implementation note:** The detect step already has `data._k8s` which tells us if `cluster_connected` is true. If connected, make an async call to `/api/k8s/namespaces` in the render. If not, skip and show text input.

**Dependencies:** Needs cluster connection info from detect step.

---

### 3B. Cluster Settings — Per-Environment Namespaces

**What changes:** Add "Create separate namespace per environment" checkbox with per-env namespace inputs.

**API available:**
```python
k8s_env_namespaces(project_root) → {
    "environments": [{"name": str, "namespace": str, "has_overlay": bool, "overlay_path": str}, ...]
}
```

**UI:**
```
☑ Create separate namespace per environment
  ┌──────────────────────────────────────────────────────┐
  │ development → [devops-control-plane-development ]     │
  │ production  → [devops-control-plane-production  ]     │
  │                                                       │
  │ ☑ Generate Namespace manifests                        │
  └──────────────────────────────────────────────────────┘
```

**When checked:** Generates a `Namespace` resource per env AND duplicates all app manifests per namespace (or uses Kustomize overlays).

**collect():**
```javascript
perEnvNamespaces: checked ? envs.map((e, j) => ({
    env: e.name,
    namespace: _val(`k8s-ns-env-${j}`) || `${appName}-${e.name}`,
})) : null,
```

**Dependencies:** Needs environment data from detect step (`data._envs`).

---

### 3C. Cluster Settings — Ingress Reveal Panel

**What changes:** When Ingress checkbox is checked, show per-service host configuration + controller select + TLS toggle.

**UI when Ingress checked:**
```
☑ Generate Ingress manifest
  ┌──────────────────────────────────────────────────────┐
  │ Services with external access:                        │
  │ ☑ api   host: [api.example.com    ]                   │
  │ ☑ web   host: [example.com        ]                   │
  │ ☐ worker (no external access)                         │
  │                                                       │
  │ Controller  [nginx-ingress ▾]                         │
  │ ☑ Include TLS section (cert-manager annotations)      │
  └──────────────────────────────────────────────────────┘
```

**Per-service controls:**
- `k8s-ingress-svc-{i}` — checkbox (include in ingress)
- `k8s-ingress-host-{i}` — text input for host
- `k8s-ingress-controller` — select: `nginx` | `traefik` | `haproxy` | `other`
- `k8s-ingress-tls` — checkbox

**Pre-fill host:**
- From GitHub repo: `{svcName}.{ghRepo.name}.example.com` or just `example.com`
- First service → root domain, subsequent services → subdomain

**Dependencies:**
- Needs app services list from collect (services must be collected first)
- Ingress references service names and ports

---

### 3D. Cluster Settings — Output Format Selection

**What changes:** Add radio group for output format.

**UI:**
```
Output Format
  ● Raw manifests in k8s/ directory    ← default
  ○ Helm chart scaffold                ← if Helm detected
  ○ Kustomize overlays                 ← if Kustomize detected
```

**Conditional display:**
- "Helm chart scaffold" only shown if `data._k8s.has_helm_chart` or Helm is installed
- "Kustomize overlays" only shown if `data._k8s.has_kustomize` or kustomize binary available

**When Helm selected:** Different generation path — scaffold Chart.yaml, values.yaml, templates/
**When Kustomize selected:** Different generation path — base + per-env overlays

**collect():**
```javascript
outputFormat: document.querySelector('input[name="k8s-output-format"]:checked')?.value || 'raw',
```

**Dependencies:**
- Needs K8s status from detect step to know if Helm/Kustomize exists
- Changes the entire generation path in the preview step

---

## 2. DATA STRUCTURES — WHAT collect() PRODUCES

### Full `data._services[i]` shape after all sub-features:

```javascript
{
    // Primary (1A)
    name: "api",
    kind: "Deployment",
    image: "ghcr.io/user/api:latest",
    port: 8000,
    replicas: 2,
    serviceType: "ClusterIP",
    strategy: "RollingUpdate",
    maxSurge: "1",
    maxUnavailable: "1",

    // Resources (1B)
    resources: {
        cpu_request: "100m",
        cpu_limit: "500m",
        memory_request: "128Mi",
        memory_limit: "256Mi",
    },

    // Probes (1C)
    probes: {
        readiness: {
            type: "http",
            path: "/health",
            port: 8000,
            initialDelaySeconds: 5,
            periodSeconds: 5,
            timeoutSeconds: 3,
        },
        liveness: {
            type: "http",
            path: "/health",
            port: 8000,
            initialDelaySeconds: 10,
            periodSeconds: 15,
            failureThreshold: 3,
        },
    },

    // Environment (1D) — per-variable injection control
    envVars: [
        { key: "PORT",        type: "hardcoded", value: "3000",       varName: null },
        { key: "LOG_LEVEL",   type: "hardcoded", value: "info",       varName: null },
        { key: "NODE_ENV",    type: "variable",  value: "production", varName: "${NODE_ENV}" },
        { key: "DB_HOST",     type: "hardcoded", value: "postgres",   varName: null },
        { key: "DB_PASSWORD", type: "secret",    value: "",           varName: "${DB_PASSWORD}" },
        { key: "API_KEY",     type: "secret",    value: "",           varName: "${API_KEY}" },
    ],
    // Generated resource names (derived from envVars at collect time)
    _configMapName: "api-config",    // if any hardcoded/variable vars
    _secretName: "api-secrets",      // if any secret vars

    // Volumes (1E)
    volumes: [
        {
            mountPath: "/app/data",
            type: "pvc",
            size: "5Gi",
            accessMode: "ReadWriteOnce",
            name: "api-data",
        },
    ],

    // Compose source reference
    _compose: { /* original compose service detail */ },
}
```

### Full `data._infraDecisions[i]` shape:

```javascript
{
    name: "postgres",
    kind: "StatefulSet",         // or "Managed"
    image: "postgres:16-alpine",
    port: 5432,
    replicas: 1,
    pvc: {
        name: "postgres-data",
        size: "10Gi",
        accessMode: "ReadWriteOnce",
        mountPath: "/var/lib/postgresql/data",
    },
    envVars: [
        { key: "POSTGRES_DB",       type: "hardcoded", value: "app",    varName: null },
        { key: "POSTGRES_USER",     type: "hardcoded", value: "app",    varName: null },
        { key: "POSTGRES_PASSWORD", type: "secret",    value: "",       varName: "${POSTGRES_PASSWORD}" },
    ],
    headlessService: true,
    _compose: { /* original */ },
}
```

### Full cluster settings:

```javascript
{
    namespace: "default",
    output_dir: "k8s/",
    outputFormat: "raw",          // "raw" | "helm" | "kustomize"
    ingress: true,
    ingressConfig: {
        services: [
            { name: "api", host: "api.example.com", enabled: true },
            { name: "web", host: "example.com", enabled: true },
        ],
        controller: "nginx",
        tls: true,
    },
    // configmap checkbox REMOVED — ConfigMap/Secret auto-generated per service from envVars
    perEnvNamespaces: [
        { env: "development", namespace: "app-development" },
        { env: "production", namespace: "app-production" },
    ],
}
```

---

## 3. IMPLEMENTATION ORDER — BY VALUE AND DEPENDENCY

```
Solo features (no deps, highest value):
  1B. Resource Limits        ← simple, high value, backend supports it
  1A. Strategy Select        ← simple, quick win

After 1A + 1B:
  1C. Health Checks          ← medium complexity, compose translation logic
  2A. Infra StatefulSet      ← complex, but self-contained

Higher complexity (per-variable UI, multi-env awareness):
  1D. Environment Variables  ← HIGH complexity, per-var row UI, injection types,
                                ${VAR} substitution, ConfigMap+Secret generation,
                                multi-env awareness, removes ConfigMap checkbox
  2B. Infra Managed          ← easy, needs env var cross-ref from 1D

After 1D:
  1E. Volume Mounts          ← complex, PVC generation, volume classification

After all app/infra cards:
  3A. Namespace Dropdown     ← needs cluster connection, async API call
  3C. Ingress Reveal         ← needs service list from collect
  3B. Per-Env Namespaces     ← needs env data + namespace API
  3D. Output Format          ← changes entire generation path, do last

Last (optional feature, detect-step changes needed):
  Skaffold integration       ← optional dev experience toggle, detect enhancement
```

**Recommended first implementation: 1B (Resource Limits)**
- Self-contained
- 4 input fields + pre-fill + collect + validation
- Backend `generate_k8s_wizard` already supports it
- High user-visible value
- Proves the pattern for all other `<details>` sections

---

## 4. PATTERN: HOW EACH `<details>` SECTION IS STRUCTURED

Every advanced setting follows this pattern:

```javascript
// 1. Parse compose data into defaults
const defaults = _extractFromCompose(svc);

// 2. Render <details> with editable fields pre-filled from defaults
html += `<details style="margin-top:0.3rem">
    <summary style="cursor:pointer;font-size:0.72rem;color:var(--accent);user-select:none;padding:0.15rem 0">
        ▸ Section Title ${count ? `(${count})` : ''}
    </summary>
    <div style="display:grid;grid-template-columns:...;gap:0.4rem;margin-top:0.3rem">
        <!-- editable inputs with IDs k8s-svc-FIELD-{i} -->
    </div>
</details>`;

// 3. collect() reads each field by ID
svc.fieldGroup = {
    field1: _val(`k8s-svc-field1-${i}`) || null,
    field2: _val(`k8s-svc-field2-${i}`) || null,
};

// 4. validate() checks values
if (svc.fieldGroup.field1 && !validFormat(svc.fieldGroup.field1)) {
    return `Invalid format for field1 in ${svc.name}`;
}

// 5. Review step shows a summary row
items.push({
    icon: '🔧',
    label: `Section: ${svc.name}`,
    value: summarize(svc.fieldGroup),
    badge: 'create',
    badgeCls: 'ready',
});
```

This pattern is exactly what the Docker wizard uses for its `<details>` sections.

---

## 5. BACKEND ENHANCEMENT NEEDED (for complete flow)

The `generate_k8s_wizard` function currently supports:
- ✅ Deployment (image, port, replicas, cpu/memory limits, env vars)
- ✅ Service (port, type, selector)
- ✅ ConfigMap (data dict — but not from envVars classification)
- ✅ Ingress (host, port, service)
- ✅ Namespace
- ❌ StatefulSet (no handler)
- ❌ PersistentVolumeClaim (no handler)
- ❌ Secret (no handler)
- ❌ Deployment strategy (not in spec handler)
- ❌ Deployment probes (not in spec handler)
- ❌ Deployment volumeMounts (not in spec handler)
- ❌ Deployment `envFrom` (currently uses inline `env`, need `envFrom` for ConfigMap/Secret refs)
- ❌ Headless Service (no clusterIP: None)
- ❌ ConfigMap from envVars (need to build from classified env var array)

**Required additions to `generate_k8s_wizard`:**
1. Add `strategy` to Deployment spec builder
2. Add probes (readinessProbe, livenessProbe) to Deployment spec builder
3. Add volumeMounts to container spec + volumes to pod spec
4. Add StatefulSet kind handler (like Deployment but with volumeClaimTemplates)
5. Add PersistentVolumeClaim kind handler
6. Add Secret kind handler (stringData with `${VAR}` substitution values)
7. Add headless Service variant (clusterIP: None for StatefulSet)
8. Build ConfigMap from envVars classification (hardcoded → literal, variable → `${VAR}`)
9. Build Secret from envVars classification (secret → `${VAR}` substitution)
10. Replace inline `env:` with `envFrom:` references to ConfigMap + Secret
11. (Multi-env) Generate Kustomize overlay structure for per-env ConfigMap patches

These are NOT needed for Phase 2 (Configure step UI). They're needed for Phase 3 (Preview) when we generate actual YAML.

---

## 6. WHAT I WILL IMPLEMENT FIRST

**Sub-feature 1B: Resource Limits** — one complete, polished implementation.

This proves the full pattern:
1. ✅ Compose pre-fill (deploy.cpu_limit, etc.)
2. ✅ Editable inputs (4 fields)
3. ✅ Proper defaults (empty = omit)
4. ✅ K8s unit format
5. ✅ collect() into data._services[i].resources
6. ✅ validate() for format + limits ≥ requests
7. ✅ Review display
8. ✅ Backend compatible (generate_k8s_wizard already supports it)

After that's solid, I'll do 1A (Strategy), then 1C (Health Checks), then 1D (Env Vars), etc.
One at a time. Each one done right.
