# Tool Install v2 — Phase 4: Decision Trees & Choice UI

## Context

Phases 2-3 handle SIMPLE recipes — tools where the resolver picks
the install method automatically (no user input needed). Phase 4
adds DECISION TREES — recipes where the user must make choices
(Docker CE vs docker.io, GPU driver version, Node version, etc.).

### Dependencies

```
Phase 2.3 (resolver)    ── provides: resolve_install_plan() (single-pass)
Phase 3 (frontend)      ── provides: showStepModal(), streamSSE()
Phase 4 (THIS)           ── provides: two-pass resolver, choice UI, input UI
```

### Domains consumed

| Domain | What Phase 4 uses |
|--------|------------------|
| domain-choices | Decision tree architecture, choice types, branching |
| domain-inputs | User input types, validation, templates |
| domain-version-selection | Dynamic version lists, constraints |
| domain-disabled-options | Available/disabled with reasons |
| domain-network | Network-dependent options |

---

## What Changes from Phase 3

### Phase 3: automatic resolution

```
Recipe → Resolver → Plan → Execute
         (no user)
```

### Phase 4: two-pass resolution

```
Recipe → Pass 1 → Choices → User picks → Pass 2 → Plan → Execute
         (what to ask)       (frontend)     (resolve with answers)
```

---

## Two-Pass Resolver

### Pass 1: Extract choices

```python
def resolve_choices(tool: str, profile: dict) -> dict:
    """First pass — extract choices the user must make.

    Returns:
        {
            "tool": "docker",
            "choices": [...],   # Questions for the user
            "inputs": [...],    # Free-form inputs
            "defaults": {...},  # Pre-selected defaults
        }
    """
    recipe = TOOL_RECIPES.get(tool)
    if not recipe:
        return {"error": f"No recipe for '{tool}'"}

    choices = []
    inputs = []
    defaults = {}

    # Extract choices from recipe
    if "choices" in recipe:
        for choice in recipe["choices"]:
            resolved = _resolve_choice(choice, profile)
            choices.append(resolved)
            if resolved.get("default"):
                defaults[choice["id"]] = resolved["default"]

    # Extract inputs from recipe
    if "inputs" in recipe:
        for inp in recipe["inputs"]:
            if _input_condition_met(inp, profile):
                inputs.append(inp)

    # If no choices needed, return empty
    if not choices and not inputs:
        return {"tool": tool, "choices": [], "inputs": [],
                "auto_resolve": True}

    return {
        "tool": tool,
        "choices": choices,
        "inputs": inputs,
        "defaults": defaults,
    }
```

### Pass 2: Resolve with answers

```python
def resolve_install_plan_with_choices(
    tool: str,
    profile: dict,
    answers: dict,
) -> dict:
    """Second pass — resolve plan using user's choice answers.

    Args:
        tool: Tool name
        profile: System profile
        answers: {"choice_id": "selected_value", "input_id": "user_value"}

    Returns:
        Install plan (same format as Phase 2.3)
    """
    recipe = TOOL_RECIPES.get(tool)
    if not recipe:
        return {"error": f"No recipe for '{tool}'"}

    # Apply choices to recipe
    resolved_recipe = _apply_choices(recipe, answers)

    # Apply inputs (template substitution)
    resolved_recipe = _apply_inputs(resolved_recipe, answers)

    # Now resolve as normal (single-pass)
    return resolve_install_plan_from_recipe(
        tool, resolved_recipe, profile,
    )
```

---

## Choice Types

### From domain-choices

| Type | Example | UI widget |
|------|---------|-----------|
| `select_one` | Docker CE vs docker.io | Radio buttons |
| `select_version` | kubectl version | Dropdown with version list |
| `toggle` | Enable Docker BuildKit? | Toggle switch |
| `select_multi` | MkDocs plugins to install | Checkboxes |

### Choice schema

```python
{
    "id": "docker_variant",
    "type": "select_one",
    "label": "Docker Package",
    "description": "Which Docker package to install",
    "options": [
        {
            "value": "docker.io",
            "label": "docker.io (Debian community)",
            "description": "Simpler install, Debian-maintained",
            "available": True,
            "default": True,
        },
        {
            "value": "docker-ce",
            "label": "Docker CE (Official)",
            "description": "Latest features, Docker-maintained repo",
            "available": True,
            "requires": {"network": ["download.docker.com"]},
        },
        {
            "value": "podman",
            "label": "Podman (Docker alternative)",
            "description": "Daemonless container engine",
            "available": True,
        },
    ],
}
```

### Version selection choice

```python
{
    "id": "kubectl_version",
    "type": "select_version",
    "label": "kubectl Version",
    "description": "Must be within ±1 minor of your cluster",
    "version_source": {
        "type": "github_tags",
        "repo": "kubernetes/kubernetes",
        "pattern": r"^v(\d+\.\d+\.\d+)$",
        "filter": "stable",  # no alpha/beta/rc
    },
    "constraint": {
        "type": "cluster_compat",
        "rule": "±1 minor of cluster version",
    },
    "default_strategy": "latest_stable",
}
```

---

## Disabled Options

### From domain-disabled-options

Options are NEVER removed. They are shown disabled with reasons.

```python
def _resolve_choice(choice: dict, profile: dict) -> dict:
    """Resolve a choice — mark options as available/disabled."""
    resolved_options = []

    for opt in choice["options"]:
        available = True
        disabled_reason = None
        enable_hint = None

        # Check network requirements
        if "requires" in opt:
            net = opt["requires"].get("network", [])
            for endpoint in net:
                if not _can_reach(endpoint, profile):
                    available = False
                    disabled_reason = f"Cannot reach {endpoint}"
                    enable_hint = "Check network/proxy settings"
                    break

        # Check platform requirements
        if "requires" in opt:
            platforms = opt["requires"].get("platforms", [])
            if platforms and profile["distro_family"] not in platforms:
                available = False
                disabled_reason = f"Not available on {profile['distro_family']}"

        # Check binary requirements
        if "requires" in opt:
            for binary in opt["requires"].get("binaries", []):
                if not shutil.which(binary):
                    available = False
                    disabled_reason = f"Requires {binary}"
                    enable_hint = f"Install {binary} first"
                    break

        resolved_options.append({
            **opt,
            "available": available,
            "disabled_reason": disabled_reason,
            "enable_hint": enable_hint,
        })

    return {**choice, "options": resolved_options}
```

---

## Input Types

### From domain-inputs

| Type | Example | Validation |
|------|---------|-----------|
| `text` | Custom install path | Non-empty, path exists |
| `password` | sudo password | Non-empty |
| `number` | Port number | Range check |
| `select` | Shell type | Enum check |

### Input schema

```python
{
    "id": "install_dir",
    "type": "text",
    "label": "Install Directory",
    "description": "Where to install the binary",
    "default": "~/.local/bin",
    "placeholder": "/usr/local/bin",
    "validation": {
        "required": True,
        "pattern": r"^[/~].*",
        "message": "Must be an absolute path",
    },
    "condition": {
        "choice": "install_method",
        "equals": "binary",
    },
}
```

### Template substitution

```python
# Input values are substituted into commands
"command": ["wget", "-O", "{install_dir}/hugo", "{download_url}"]

# After substitution:
"command": ["wget", "-O", "/usr/local/bin/hugo",
            "https://github.com/.../hugo_0.128.0_linux-amd64.tar.gz"]
```

---

## Choice UI

### Frontend: showChoiceModal()

```javascript
/**
 * Show a choice modal before install.
 * On submit, resolves plan with answers and shows step modal.
 */
async function showChoiceModal(choiceData, options = {}) {
    document.getElementById('choice-modal')?.remove();

    const modal = document.createElement('div');
    modal.id = 'choice-modal';
    modal.className = 'modal-overlay';

    modal.innerHTML = `
        <div class="modal-content choice-modal-content">
            <div class="modal-header">
                <h3>⚙️ Configure ${choiceData.tool}</h3>
                <button class="modal-close"
                    onclick="document.getElementById('choice-modal')?.remove()">✕</button>
            </div>
            <div class="modal-body">
                ${choiceData.choices.map(c => _renderChoice(c, choiceData.defaults)).join('')}
                ${choiceData.inputs.map(i => _renderInput(i)).join('')}
            </div>
            <div class="modal-footer">
                <button class="btn btn-secondary"
                    onclick="document.getElementById('choice-modal')?.remove()">Cancel</button>
                <button class="btn btn-primary" id="choice-modal-go">
                    Continue →
                </button>
            </div>
        </div>
    `;

    document.body.appendChild(modal);

    document.getElementById('choice-modal-go').addEventListener('click', async () => {
        const answers = _collectAnswers(choiceData);
        document.getElementById('choice-modal')?.remove();

        // Resolve plan with answers
        const planResp = await fetch('/audit/install-plan', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({tool: choiceData.tool, answers}),
        });
        const plan = await planResp.json();

        // Show step modal
        showStepModal(plan, options);
    });
}
```

### Choice renderers

```javascript
function _renderChoice(choice, defaults) {
    if (choice.type === 'select_one') {
        return `
            <div class="choice-group">
                <label class="choice-label">${choice.label}</label>
                <p class="choice-desc">${choice.description || ''}</p>
                <div class="choice-options">
                    ${choice.options.map(opt => `
                        <label class="choice-option ${opt.available ? '' : 'disabled'}"
                               title="${opt.disabled_reason || ''}">
                            <input type="radio" name="${choice.id}"
                                   value="${opt.value}"
                                   ${opt.value === defaults[choice.id] ? 'checked' : ''}
                                   ${opt.available ? '' : 'disabled'} />
                            <div class="choice-option-content">
                                <span class="choice-option-label">${opt.label}</span>
                                <span class="choice-option-desc">${opt.description || ''}</span>
                                ${opt.disabled_reason ? `
                                    <span class="choice-disabled-reason">
                                        ⚠️ ${opt.disabled_reason}
                                        ${opt.enable_hint ? `— ${opt.enable_hint}` : ''}
                                    </span>
                                ` : ''}
                            </div>
                        </label>
                    `).join('')}
                </div>
            </div>
        `;
    }
    if (choice.type === 'toggle') {
        return `
            <div class="choice-group">
                <label class="choice-toggle">
                    <input type="checkbox" name="${choice.id}"
                           ${defaults[choice.id] ? 'checked' : ''} />
                    <span>${choice.label}</span>
                </label>
                <p class="choice-desc">${choice.description || ''}</p>
            </div>
        `;
    }
    if (choice.type === 'select_version') {
        return `
            <div class="choice-group">
                <label class="choice-label">${choice.label}</label>
                <p class="choice-desc">${choice.description || ''}</p>
                <select name="${choice.id}" class="choice-version-select">
                    ${choice.versions ? choice.versions.map(v => `
                        <option value="${v.value}"
                                ${v.default ? 'selected' : ''}
                                ${v.available ? '' : 'disabled'}>
                            ${v.label} ${v.tag || ''}
                        </option>
                    `).join('') : '<option>Loading versions...</option>'}
                </select>
            </div>
        `;
    }
    return '';
}
```

---

## Integrated Flow

### Full flow with choices

```
1. User clicks "Install Docker"
2. Frontend: POST /audit/resolve-choices {tool: "docker"}
3. Backend: resolve_choices("docker", profile) → choices
4. Frontend: showChoiceModal(choices)
5. User picks: docker-ce, enable BuildKit
6. Frontend: POST /audit/install-plan {tool: "docker", answers: {...}}
7. Backend: resolve_install_plan_with_choices("docker", profile, answers) → plan
8. Frontend: showStepModal(plan)
9. User enters sudo password, clicks Install
10. Frontend: POST /audit/execute-plan {tool: "docker", sudo_password: "..."}
11. Backend: execute_plan() → SSE stream
12. Frontend: updates step rows in real-time
```

### Auto-resolve (no choices needed)

```
1. User clicks "Install ruff"
2. Frontend: POST /audit/resolve-choices {tool: "ruff"}
3. Backend: returns {auto_resolve: true}
4. Frontend: SKIPS choice modal
5. Frontend: POST /audit/install-plan {tool: "ruff"}
6. Continue as Phase 3 flow (showStepModal directly)
```

---

## New Backend Endpoints

### POST /audit/resolve-choices

```python
@app.post("/audit/resolve-choices")
def resolve_tool_choices():
    """First pass — get choices for a tool."""
    tool = request.json.get("tool")
    profile = get_system_profile()
    return jsonify(resolve_choices(tool, profile))
```

### POST /audit/install-plan (updated)

```python
@app.post("/audit/install-plan")
def get_install_plan():
    """Get install plan — with or without choice answers."""
    tool = request.json.get("tool")
    answers = request.json.get("answers", {})
    profile = get_system_profile()

    if answers:
        plan = resolve_install_plan_with_choices(tool, profile, answers)
    else:
        plan = resolve_install_plan(tool, profile)

    return jsonify(plan)
```

---

## Example: Docker Recipe with Choices

```python
"docker": {
    "label": "Docker",
    "category": "container",
    "choices": [
        {
            "id": "variant",
            "type": "select_one",
            "label": "Docker Package",
            "options": [
                {
                    "value": "docker.io",
                    "label": "docker.io (Debian community)",
                    "default": True,
                    "available": True,
                },
                {
                    "value": "docker-ce",
                    "label": "Docker CE (Official)",
                    "requires": {"network": ["download.docker.com"]},
                },
                {
                    "value": "podman",
                    "label": "Podman (alternative)",
                },
            ],
        },
        {
            "id": "buildkit",
            "type": "toggle",
            "label": "Enable BuildKit",
            "default": True,
            "description": "Modern build engine with caching",
        },
    ],
    "install": {
        "docker.io": {
            "debian": ["apt-get", "install", "-y", "docker.io"],
        },
        "docker-ce": {
            "debian": {
                "repo_setup": [...],  # GPG key + apt source
                "command": ["apt-get", "install", "-y",
                            "docker-ce", "docker-ce-cli", "containerd.io"],
            },
        },
        "podman": {
            "debian": ["apt-get", "install", "-y", "podman"],
        },
    },
    "post_install": {
        "docker.io": [
            {"label": "Start Docker", "command": ["systemctl", "start", "docker"],
             "needs_sudo": True,
             "condition": {"has_systemd": True}},
            {"label": "Enable Docker", "command": ["systemctl", "enable", "docker"],
             "needs_sudo": True,
             "condition": {"has_systemd": True}},
        ],
        "podman": [],  # No daemon needed
    },
    "needs_sudo": {"docker.io": True, "docker-ce": True, "podman": True},
    "verify": {"docker.io": ["docker", "--version"],
               "docker-ce": ["docker", "--version"],
               "podman": ["podman", "--version"]},
}
```

---

## Branching Logic

### How choices affect the plan

```python
def _apply_choices(recipe: dict, answers: dict) -> dict:
    """Apply user's choices to produce a flat recipe."""
    resolved = dict(recipe)

    for choice in recipe.get("choices", []):
        cid = choice["id"]
        answer = answers.get(cid, choice.get("default"))

        if answer is None:
            continue

        # Branch install command
        if cid in recipe.get("install", {}):
            resolved["install"] = recipe["install"][answer]

        # Branch post_install
        if cid in recipe.get("post_install", {}):
            resolved["post_install"] = recipe["post_install"][answer]

        # Branch verify
        if cid in recipe.get("verify", {}):
            resolved["verify"] = recipe["verify"][answer]

        # Branch needs_sudo
        if cid in recipe.get("needs_sudo", {}):
            resolved["needs_sudo"] = recipe["needs_sudo"][answer]

    return resolved
```

---

## Files Touched

| File | Changes |
|------|---------|
| `tool_install.py` | Add resolve_choices(), resolve_install_plan_with_choices(), _apply_choices(), _apply_inputs(), _resolve_choice(). Add choices to complex TOOL_RECIPES entries. |
| `routes_audit.py` | Add POST /audit/resolve-choices. Update POST /audit/install-plan to accept answers. |
| `_globals.html` | Add showChoiceModal(), choice renderers, _collectAnswers(). |
| `_globals.html` (CSS) | Add choice modal styles. |

---

## Edge Cases

| Case | Impact | Handling |
|------|--------|---------|
| No choices needed | Extra modal for nothing | auto_resolve: true → skip to step modal |
| All options disabled | User can't pick anything | Show "No options available" + reasons |
| Dynamic versions API fails | Empty version dropdown | Show error, offer manual input |
| Choice depends on another choice | Cascading selects | Phase 4b: dependent choice refresh |
| User picks disabled option | Shouldn't happen | Frontend disables input, backend validates |
| Network check slow | Modal takes long to show | Show modal immediately, load network checks async |
| Toggle changes plan length | User surprised | Show plan preview after choices |

---

## Traceability

| Topic | Source |
|-------|--------|
| Decision tree architecture | domain-choices §decision tree |
| Choice types (4 types) | domain-choices §choice types |
| Disabled options pattern | domain-disabled-options §always-present |
| Version selection sources | domain-version-selection §dynamic |
| Input validation | domain-inputs §validation |
| Template substitution | domain-inputs §template substitution |
| Network-gated options | domain-network §requires.network |
| Two-pass resolver | scope-expansion §Phase 4 |
| Docker variant example | scope-expansion §docker choices |
