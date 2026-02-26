# Phase 2.3 — Resolver Scenarios (55 scenarios)

Referenced from `tool-install-v2-phase2.3-resolver-engine.md` section 7.

Each scenario states: Input → Expected plan output → Why it matters.

Short notation:
- `P` = system profile
- `→ pkg(X)` = packages step with X
- `→ tool(X)` = tool step for X
- `→ post(X)` = post_install step for X
- `→ verify(X)` = verify step for X
- `sudo:Y/N` = plan needs_sudo flag

---

## Angle 1: Platform Variants (same tool, different systems)

### S01: git on Ubuntu (apt)
```
P: family=debian, pm=apt, snap=yes, systemd=yes, root=no
Tool: git (not installed)

Method: apt (primary pm match)
Batchable: yes

Plan: pkg(git) → verify(git --version)
sudo: Y
```

### S02: git on Fedora (dnf)
```
P: family=rhel, pm=dnf, snap=no, systemd=yes, root=no
Tool: git (not installed)

Method: dnf
Batchable: yes

Plan: pkg(git) → verify(git --version)
sudo: Y
```

### S03: git on Alpine (apk)
```
P: family=alpine, pm=apk, snap=no, systemd=no, root=yes
Tool: git (not installed)

Method: apk
Batchable: yes

Plan: pkg(git) → verify(git --version)
sudo: Y (apk needs root, but is_root=yes so execution strips sudo)
```

### S04: git on Arch (pacman)
```
P: family=arch, pm=pacman, snap=no, systemd=yes, root=no
Tool: git (not installed)

Method: pacman
Batchable: yes

Plan: pkg(git) → verify(git --version)
sudo: Y
```

### S05: git on SUSE (zypper)
```
P: family=suse, pm=zypper, snap=no, systemd=yes, root=no
Tool: git (not installed)

Method: zypper
Batchable: yes

Plan: pkg(git) → verify(git --version)
sudo: Y
```

### S06: git on macOS (brew)
```
P: family=macos, pm=brew, snap=no, systemd=no, root=no
Tool: git (not installed)

Method: brew
Batchable: yes (brew IS primary pm)

Plan: pkg(git) → verify(git --version)
sudo: N (brew never needs sudo)
```

### S07: kubectl on Ubuntu (has snap)
```
P: family=debian, pm=apt, snap=yes
Tool: kubectl (not installed), curl installed

Method: snap (prefer=[snap,brew,_default], snap available)

Plan: tool(snap install kubectl --classic) → verify(kubectl version --client)
sudo: Y (snap needs sudo)
```

### S08: kubectl on Fedora (no snap, no brew)
```
P: family=rhel, pm=dnf, snap=no
Tool: kubectl (not installed), curl installed

Method: _default (snap unavailable, brew not on PATH, _default fallback)

Plan: tool(bash -c 'curl ... && chmod +x kubectl && sudo mv ...') → verify(kubectl version --client)
sudo: Y (_default binary download needs sudo for /usr/local/bin)
```

### S09: kubectl on macOS (brew available)
```
P: family=macos, pm=brew, snap=no
Tool: kubectl (not installed)

Method: brew (prefer=[snap,brew,_default], snap unavail, brew on PATH)

Plan: tool(brew install kubectl) → verify(kubectl version --client)
sudo: N
```

### S10: kubectl on Alpine (no snap, no brew)
```
P: family=alpine, pm=apk, snap=no
Tool: kubectl (not installed), curl NOT installed

Method: _default (fallback)
curl batchable as apk package

Plan: pkg(curl) → tool(binary download) → verify(kubectl version --client)
sudo: Y
```

### S11: node on Ubuntu (snap available)
```
P: family=debian, pm=apt, snap=yes
Tool: node (not installed)

Method: snap (prefer not set, but snap available and recipe has snap key)
Actually: node recipe has apt,dnf,apk,brew,snap. No prefer list.
Resolution: apt in install → pick apt (step 2 of resolution order)

Plan: pkg(nodejs) → verify(node --version)
sudo: Y

WAIT — should node prefer snap over apt? The recipe doesn't have
a prefer list. Without prefer, the resolver picks the primary pm.
On Ubuntu, apt-get install nodejs gives an older version.
snap install node --classic gives the latest.

DECISION: Add prefer: ["snap", ...] to node recipe? Or leave it?
For now: no prefer → uses primary pm. If we want snap behavior,
add prefer list. This is a recipe design decision, not a resolver bug.
```

### S12: node on Alpine
```
P: family=alpine, pm=apk, snap=no
Tool: node (not installed)

Method: apk (primary pm match)

Plan: pkg(nodejs) → verify(node --version)
sudo: Y
```

### S13: terraform on Alpine (IMPOSSIBLE)
```
P: family=alpine, pm=apk, snap=no
Tool: terraform (not installed)

Method: None (recipe only has snap, brew — neither available)

Plan: ERROR
{error: "No install method available for Terraform on this system.",
 available_methods: ["snap", "brew"],
 suggestion: "Install snap or brew to enable Terraform installation."}
```

---

## Angle 2: Dependency Chain Depths

### S14: ruff — zero deps
```
P: any
Tool: ruff (not installed)

No deps.
Method: _default (pip)

Plan: tool(pip install ruff) → verify(ruff --version)
sudo: N
Steps: 2
```

### S15: eslint — one dep (npm)
```
P: family=debian, pm=apt
Tool: eslint (not installed), npm NOT installed

Dep chain: eslint → npm (batchable)

Plan: pkg(npm) → tool(npm install -g eslint) → verify(eslint --version)
sudo: Y
Steps: 3
```

### S16: helm — one dep (curl)
```
P: family=debian, pm=apt
Tool: helm (not installed), curl NOT installed

Dep chain: helm → curl (batchable)

Plan: pkg(curl) → tool(bash-curl helm script) → verify(helm version)
sudo: Y
Steps: 3
```

### S17: cargo-audit — two-deep chain + system packages
```
P: family=debian, pm=apt
Tool: cargo-audit, cargo NOT installed, curl NOT installed

Dep chain: cargo-audit → cargo → curl
System pkgs: pkg-config, libssl-dev

Plan: pkg(curl,pkg-config,libssl-dev)
    → tool(rustup)
    → tool(cargo install cargo-audit) [env-wrapped]
    → verify(cargo audit --version) [env-wrapped]
sudo: Y
Steps: 4
```

### S18: cargo-outdated — two-deep chain + MORE system packages
```
P: family=debian, pm=apt
Tool: cargo-outdated, cargo NOT installed, curl NOT installed

Dep chain: cargo-outdated → cargo → curl
System pkgs: pkg-config, libssl-dev, libcurl4-openssl-dev

Plan: pkg(curl,pkg-config,libssl-dev,libcurl4-openssl-dev)
    → tool(rustup)
    → tool(cargo install cargo-outdated) [env-wrapped]
    → verify(cargo outdated --version) [env-wrapped]
sudo: Y
Steps: 4
```

### S19: docker-compose — requires docker binary
```
P: family=debian, pm=apt, systemd=yes, root=no
Tool: docker-compose, docker NOT installed

docker-compose.requires.binaries = ["docker"]
docker is batchable (apt → docker.io)
docker-compose is batchable (apt → docker-compose-v2)

Both go into batch, but docker has post_install steps.

Plan: pkg(docker.io, docker-compose-v2)
    → post(systemctl start docker) [condition: has_systemd=T]
    → post(systemctl enable docker) [condition: has_systemd=T]
    → post(usermod -aG docker $USER) [condition: not_root=T]
    → verify(docker compose version)
sudo: Y
Steps: 5
```

---

## Angle 3: Dependency Already Satisfied

### S20: eslint — npm IS installed
```
P: family=debian, pm=apt
Tool: eslint (not installed), npm IS installed

_collect_deps("npm"): shutil.which("npm") → found → SKIP

Plan: tool(npm install -g eslint) → verify(eslint --version)
sudo: N (no package step needed)
Steps: 2
```

### S21: cargo-audit — cargo IS installed, packages installed
```
P: family=debian, pm=apt
Tool: cargo-audit, cargo installed, pkg-config installed, libssl-dev installed

All deps satisfied.

Plan: tool(cargo install cargo-audit) → verify(cargo audit --version)
sudo: N
Steps: 2
```

### S22: cargo-audit — cargo installed, packages MISSING
```
P: family=debian, pm=apt
Tool: cargo-audit, cargo installed, libssl-dev NOT installed

Plan: pkg(pkg-config,libssl-dev) → tool(cargo install cargo-audit)
    → verify(cargo audit --version)
sudo: Y
Steps: 3
```

### S23: cargo-audit — cargo NOT installed, curl IS installed
```
P: family=debian, pm=apt
Tool: cargo-audit, cargo NOT installed, curl IS installed

curl found → skip. System packages still needed.

Plan: pkg(pkg-config,libssl-dev)
    → tool(rustup)
    → tool(cargo install cargo-audit) [env-wrapped]
    → verify
sudo: Y
Steps: 4
```

### S24: helm — curl IS installed
```
P: family=debian, pm=apt
Tool: helm, curl IS installed

curl found → skip. No package step needed.

Plan: tool(bash-curl helm script) → verify(helm version)
sudo: Y (_default helm install writes to /usr/local/bin)
Steps: 2
```

### S25: tool already installed
```
P: any
Tool: git (IS installed)

shutil.which("git") → "/usr/bin/git"

Plan: {already_installed: true, steps: []}
sudo: N
Steps: 0
```

---

## Angle 4: Privilege & Root Context

### S26: pip tool as root
```
P: pm=apt, root=yes
Tool: ruff

Plan: tool(pip install ruff) → verify(ruff --version)
sudo: N (pip doesn't need sudo)
Steps: 2

Note: running as root doesn't change pip behavior (venv install).
```

### S27: system package as root
```
P: pm=apt, root=yes
Tool: jq

Plan: pkg(jq) → verify(jq --version)
sudo: Y (step says needs_sudo=True)

BUT: is_root=yes. Execution layer strips sudo prefix.
The PLAN still says needs_sudo because the resolver doesn't
know about root stripping — that's Phase 2.4's job.
Actually: should the resolver be root-aware?

DECISION: The resolver sets needs_sudo based on recipe.
The plan-level needs_sudo is True.
BUT if is_root=True, the plan adds: "sudo_note": "Running as root, sudo not required."
The frontend skips the password prompt.
```

### S28: sudo tool, no sudo available, not root
```
P: pm=apt, root=no, has_sudo=no
Tool: git

Plan: pkg(git) → verify(git --version)
sudo: Y
warning: "This plan requires sudo but sudo is not available on this system."

The plan is still generated — it's up to the caller to decide
what to do (show error, attempt anyway, etc.)
```

### S29: docker as root in container
```
P: pm=apt, root=yes, systemd=no, in_container=yes
Tool: docker

Plan: pkg(docker.io) → verify(docker --version)
sudo: Y (plan level)
post_install steps: ALL excluded
  has_systemd=no → skip start/enable
  not_root=no → skip group-add
Steps: 2
```

---

## Angle 5: Container Environments

### S30: git in Docker container (Debian-based, root)
```
P: family=debian, pm=apt, root=yes, systemd=no, container=yes

Tool: git

Plan: pkg(git) → verify(git --version)
sudo: Y (plan), but root strips sudo
Steps: 2
```

### S31: curl in Alpine container (root, no systemd)
```
P: family=alpine, pm=apk, root=yes, systemd=no, container=yes

Tool: curl

Plan: pkg(curl) → verify(curl --version)
sudo: Y
Steps: 2
```

### S32: cargo-audit in Fedora container
```
P: family=rhel, pm=dnf, root=yes, systemd=no, container=yes

Tool: cargo-audit, cargo NOT installed, curl installed

System packages (rhel): pkgconf-pkg-config, openssl-devel

Plan: pkg(pkgconf-pkg-config, openssl-devel)
    → tool(rustup)
    → tool(cargo install cargo-audit) [env-wrapped]
    → verify
sudo: Y
Steps: 4

Note: rhel package names differ from debian!
```

### S33: docker in Docker container (Docker-in-Docker)
```
P: family=debian, pm=apt, root=yes, systemd=no, container=yes

Tool: docker

Method: apt (docker.io)
post_install: ALL conditions fail
  has_systemd=no → skip service start/enable
  not_root=no → skip group-add

Plan: pkg(docker.io) → verify(docker --version)
sudo: Y
Steps: 2

WARNING: Docker-in-Docker typically requires mounting /var/run/docker.sock
or running a dind sidecar. The install succeeds but docker won't work
without proper container setup. The verify step (docker --version) will
pass but docker info would fail.
```

---

## Angle 6: Service Management Variations

### S34: docker on Ubuntu desktop (full post-install)
```
P: family=debian, pm=apt, systemd=yes, root=no, container=no

Plan: pkg(docker.io)
    → post(systemctl start docker) sudo:Y
    → post(systemctl enable docker) sudo:Y
    → post(usermod -aG docker $USER) sudo:Y
    → verify(docker --version)
sudo: Y
Steps: 5
```

### S35: docker on WSL1 (no systemd)
```
P: family=debian, pm=apt, systemd=no, root=no, container=no

post_install filtered:
  systemctl start → has_systemd=no → EXCLUDED
  systemctl enable → has_systemd=no → EXCLUDED
  usermod -aG → not_root=yes → INCLUDED

Plan: pkg(docker.io)
    → post(usermod -aG docker $USER) sudo:Y
    → verify(docker --version)
sudo: Y
Steps: 3

Note: Docker won't actually work without manually starting dockerd.
The plan is correct per our condition system but the user will need
to start dockerd manually on WSL1.
```

### S36: docker on WSL2 with systemd enabled
```
P: family=debian, pm=apt, systemd=yes, root=no, container=no

Same as S34 — full post-install. WSL2 with systemd=true in wsl.conf
behaves like native Linux.
```

### S37: docker on Fedora Server (systemd, not root)
```
P: family=rhel, pm=dnf, systemd=yes, root=no, container=no

Plan: pkg(docker)  [dnf package name, not docker.io]
    → post(systemctl start docker) sudo:Y
    → post(systemctl enable docker) sudo:Y
    → post(usermod -aG docker $USER) sudo:Y
    → verify(docker --version)
sudo: Y
Steps: 5
```

### S38: docker on Alpine (OpenRC, not systemd)
```
P: family=alpine, pm=apk, systemd=no, root=no, container=no

Alpine uses OpenRC not systemd.
has_systemd=no → skip systemctl steps
not_root=yes → include group-add

Plan: pkg(docker)
    → post(usermod -aG docker $USER) sudo:Y
    → verify(docker --version)
sudo: Y
Steps: 3

LIMITATION: Alpine needs `rc-update add docker` and `service docker start`
instead of systemctl. Our condition system only handles systemd.
OpenRC support would need a new condition: "has_openrc".
For Phase 2.3: document as known limitation.
```

---

## Angle 7: Post-Env Propagation

### S39: cargo then cargo-audit (env chain)
```
P: family=debian, pm=apt
cargo NOT installed, curl installed, system pkgs missing

After cargo step: accumulated_env = 'export PATH="$HOME/.cargo/bin:$PATH"'
cargo-audit step: wrapped with env
verify step: wrapped with env

Step 2 (tool): bash -c "curl ... | sh -s -- -y"    [NO wrapping]
Step 3 (tool): bash -c 'export PATH=... && cargo install cargo-audit' [WRAPPED]
Step 4 (verify): bash -c 'export PATH=... && cargo audit --version'   [WRAPPED]
```

### S40: cargo then cargo-audit AND cargo-outdated (shared env)
```
P: family=debian, pm=apt
Requesting BOTH cargo-audit and cargo-outdated (hypothetical batch)

_collect_deps processes both. cargo is visited ONCE (visited set).
Both cargo-audit and cargo-outdated get env-wrapped.

accumulated_env is the SAME for both — set once from cargo's post_env.
```

### S41: rustc (same recipe as cargo)
```
P: any
Tool: rustc (not installed)

cargo and rustc share the same install script (rustup).
rustc recipe is identical to cargo recipe.

Plan: tool(rustup) → verify(bash -c 'export PATH=... && rustc --version')
sudo: N

If cargo is ALREADY installed (rustup was already run),
rustc should also be installed. shutil.which("rustc") → found → skip.
```

### S42: tool with no post_env after cargo dep
```
P: family=debian, pm=apt
Tool: cargo-audit, cargo IS installed (on PATH)

cargo is found → skip → no post_env accumulated.
cargo-audit step is NOT wrapped.

Plan: pkg(pkg-config,libssl-dev) → tool(cargo install cargo-audit) → verify
No bash -c wrapping on step 2 or 3.
```

---

## Angle 8: Package Batching Logic

### S43: multiple system deps batch into one step
```
P: family=debian, pm=apt
Tool: cargo-outdated, nothing installed

Batch: curl (from cargo dep) + pkg-config + libssl-dev + libcurl4-openssl-dev

ONE apt-get call: apt-get install -y curl pkg-config libssl-dev libcurl4-openssl-dev
NOT four separate apt-get calls.
```

### S44: system dep already installed, not added to batch
```
P: family=debian, pm=apt
Tool: cargo-audit, curl installed, pkg-config installed, libssl-dev NOT installed

_is_pkg_installed("pkg-config") → True → skip
_is_pkg_installed("libssl-dev") → False → add

Batch: [libssl-dev] only.
```

### S45: ALL system packages installed, no packages step
```
P: family=debian, pm=apt
Tool: cargo-audit, cargo installed, all system pkgs installed

No batch_packages → packages step NOT emitted.

Plan: tool(cargo install cargo-audit) → verify
Steps: 2
```

### S46: batchable tool + batchable dep in same batch
```
P: family=debian, pm=apt
Tool: docker-compose, docker NOT installed

docker is batchable → docker.io added to batch
docker-compose is batchable → docker-compose-v2 added to batch

ONE apt-get call: apt-get install -y docker.io docker-compose-v2
```

### S47: non-batchable tool + batchable dep
```
P: family=debian, pm=apt
Tool: helm, curl NOT installed

curl is batchable → "curl" in batch
helm is NOT batchable (_default) → tool step

Plan: pkg(curl) → tool(helm bash-curl script) → verify
```

### S48: batchable tool with different pkg name (dig)
```
P: family=debian, pm=apt
Tool: dig

Recipe install.apt: ["apt-get", "install", "-y", "dnsutils"]
Extract package: "dnsutils" (NOT "dig")

Plan: pkg(dnsutils) → verify(dig -v)
sudo: Y

Note: tool ID is "dig", cli is "dig", but package name is "dnsutils".
The batch contains "dnsutils", the verify checks "dig".
```

### S49: brew packages are NOT sudo
```
P: family=macos, pm=brew
Tool: jq

Batchable: yes (brew is primary pm)

Plan: pkg(jq) → verify(jq --version)
sudo: N (brew exception in resolver)
```

---

## Angle 9: Error & Edge Conditions

### S50: unknown tool (no recipe)
```
Tool: "unknown-tool-xyz"

TOOL_RECIPES.get("unknown-tool-xyz") → None

Plan: {tool: "unknown-tool-xyz", error: "No recipe for 'unknown-tool-xyz'"}
```

### S51: empty tool string
```
Tool: ""

Endpoint returns 400: {error: "No tool specified"}
```

### S52: dep recipe missing from TOOL_RECIPES
```
Tool: cargo-audit
cargo-audit.requires.binaries = ["cargo"]
But TOOL_RECIPES has no "cargo" entry (hypothetical bug)

_collect_deps("cargo") → recipe not found → log warning → skip
cargo-audit step still created but cargo won't be installed.
Plan will likely fail at execution time.

Plan: pkg(pkg-config,libssl-dev)
    → tool(cargo install cargo-audit) [will fail — cargo missing]
    → verify

The resolver doesn't crash. It produces a plan that will fail gracefully.
```

### S53: circular dependency (hypothetical)
```
Tool A requires B, B requires A.

_collect_deps("A"):
  visited = {"A"}
  recurse into B
  _collect_deps("B"):
    visited = {"A", "B"}
    recurse into A
    _collect_deps("A"):
      "A" in visited → return (cycle broken)
    B added to tool_steps
  A added to tool_steps

Plan: tool(B) → tool(A) → verify(A)
Cycle doesn't cause crash. Order might be wrong but no infinite loop.
```

### S54: pick_install_method returns None for a DEP
```
P: family=alpine, pm=apk, snap=no
Tool: eslint
eslint.requires.binaries = ["npm"]
npm recipe has: apt, dnf, apk, brew, snap
npm.install.apk exists → pick "apk" → works fine

But if npm recipe ONLY had snap and brew (hypothetical):
_pick_install_method(npm, "apk", False) → None

The resolver should handle None method for a dep:
- Can't install npm → can't install eslint
- Error: "Cannot install dependency 'npm' — no method available."
```

---

## Angle 10: Update Plans

### S55: update command selection matches install method
```
P: family=debian, pm=apt
Tool: git (installed via apt, requesting update)

Install method would be: apt
Update command: apt-get install --only-upgrade -y git

The update endpoint picks the same method the install would use,
then looks up recipe.update[method].
```

### S56: update cargo tool
```
P: any
Tool: cargo-audit (installed, requesting update)

Install method would be: _default
Update command: cargo install cargo-audit (same as install — re-installs latest)
```

### S57: update snap tool
```
P: family=debian, pm=apt, snap=yes
Tool: kubectl (installed via snap, requesting update)

Install method: snap (from prefer list)
Update command: snap refresh kubectl
```

### S58: update pip tool
```
P: any
Tool: ruff (installed, requesting update)

Install method: _default
Update command: _PIP + ["install", "--upgrade", "ruff"]
```

### S59: update brew tool
```
P: family=macos, pm=brew
Tool: helm (installed via brew, requesting update)

Install method: brew
Update command: brew upgrade helm
```

---

## Summary Matrix

| # | Tool | Platform | Key angle | Steps | Sudo |
|---|------|----------|-----------|-------|------|
| 1 | git | Ubuntu | apt batchable | 2 | Y |
| 2 | git | Fedora | dnf batchable | 2 | Y |
| 3 | git | Alpine | apk batchable, root | 2 | Y |
| 4 | git | Arch | pacman batchable | 2 | Y |
| 5 | git | SUSE | zypper batchable | 2 | Y |
| 6 | git | macOS | brew, no sudo | 2 | N |
| 7 | kubectl | Ubuntu | snap preferred | 2 | Y |
| 8 | kubectl | Fedora | _default fallback | 2 | Y |
| 9 | kubectl | macOS | brew preferred | 2 | N |
| 10 | kubectl | Alpine | _default + pkg dep | 3 | Y |
| 11 | node | Ubuntu | apt vs snap decision | 2 | Y |
| 12 | node | Alpine | apk | 2 | Y |
| 13 | terraform | Alpine | IMPOSSIBLE | 0 | — |
| 14 | ruff | any | zero deps, no sudo | 2 | N |
| 15 | eslint | Ubuntu | one dep (npm) | 3 | Y |
| 16 | helm | Ubuntu | one dep (curl) | 3 | Y |
| 17 | cargo-audit | Ubuntu | deep chain + sys pkgs | 4 | Y |
| 18 | cargo-outdated | Ubuntu | deepest chain | 4 | Y |
| 19 | docker-compose | Ubuntu | requires docker binary | 5 | Y |
| 20 | eslint | Ubuntu | npm already installed | 2 | N |
| 21 | cargo-audit | Ubuntu | all deps satisfied | 2 | N |
| 22 | cargo-audit | Ubuntu | cargo yes, pkgs no | 3 | Y |
| 23 | cargo-audit | Ubuntu | cargo no, curl yes | 4 | Y |
| 24 | helm | Ubuntu | curl already installed | 2 | Y |
| 25 | git | any | already installed | 0 | N |
| 26 | ruff | any | running as root | 2 | N |
| 27 | jq | Ubuntu | root context | 2 | Y* |
| 28 | git | Ubuntu | no sudo available | 2 | Y⚠ |
| 29 | docker | Ubuntu | root in container | 2 | Y |
| 30 | git | Docker | Debian container, root | 2 | Y |
| 31 | curl | Docker | Alpine container | 2 | Y |
| 32 | cargo-audit | Docker | Fedora container, rhel pkgs | 4 | Y |
| 33 | docker | Docker | DinD, no post_install | 2 | Y |
| 34 | docker | Ubuntu | full post-install | 5 | Y |
| 35 | docker | WSL1 | no systemd | 3 | Y |
| 36 | docker | WSL2+sysd | full post-install | 5 | Y |
| 37 | docker | Fedora | dnf pkg name | 5 | Y |
| 38 | docker | Alpine | OpenRC limitation | 3 | Y |
| 39 | cargo-audit | Ubuntu | env propagation | 4 | Y |
| 40 | both cargo | Ubuntu | shared env, visited set | — | — |
| 41 | rustc | any | same as cargo install | 2 | N |
| 42 | cargo-audit | Ubuntu | cargo installed, no wrap | 3 | Y |
| 43 | cargo-outdated | Ubuntu | 4 pkgs in one batch | 4 | Y |
| 44 | cargo-audit | Ubuntu | partial pkgs installed | varies | Y |
| 45 | cargo-audit | Ubuntu | all pkgs installed | 2 | N |
| 46 | docker-compose | Ubuntu | 2 batchable in 1 call | 5 | Y |
| 47 | helm | Ubuntu | batch + non-batch mix | 3 | Y |
| 48 | dig | Ubuntu | pkg name ≠ tool name | 2 | Y |
| 49 | jq | macOS | brew no sudo | 2 | N |
| 50 | unknown | any | no recipe error | 0 | — |
| 51 | "" | any | empty input 400 | 0 | — |
| 52 | cargo-audit | any | missing dep recipe | 3⚠ | Y |
| 53 | hypothetical | any | circular dep | 2 | — |
| 54 | eslint | Alpine | dep method unavailable | 0 | — |
| 55-59 | various | various | update commands | 1 | varies |
