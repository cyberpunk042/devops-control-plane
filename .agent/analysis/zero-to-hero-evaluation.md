# Evaluation: "0 to Hero" User Journey

> **Date**: 2026-02-12
> **Scenario**: New user creates a project and configures it fully using devops-control-plane

---

## The User Journey (as-designed)

### Phase 1: Installation

```
git clone … && cd devops-control-plane
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

**Status**: ✅ Works. Well-documented in QUICKSTART.md.

### Phase 2: CLI Quick Check

```
./manage.sh status    # See project overview
./manage.sh detect    # Find modules
./manage.sh health    # Check system health
```

**Status**: ✅ Works. Good first touch to verify installation.

### Phase 3: Launch Web Dashboard

```
./manage.sh web
# Opens http://127.0.0.1:8000
```

**Status**: ✅ Works. Live-reload with SPACE, graceful shutdown with Ctrl+C.

### Phase 4: Setup Wizard (🧙 Tab)

The wizard is the **primary onboarding path**. It has 6 steps:

| Step | What it does | Status |
|------|-------------|--------|
| 1. Welcome | Project name, description, repository | ✅ Works |
| 2. Modules | Scan + confirm detected modules, assign stacks | ⚠️ Needs eval |
| 3. Secrets | Configure environments, vault passphrase, encryption keys | ⚠️ Needs eval |
| 4. Content | Configure content folders (docs, media, etc.) | ⚠️ Needs eval |
| 5. Integrations | GitHub, CI/CD, Docker, K8s, Terraform sub-wizards | ⚠️ Needs eval |
| 6. Review | Summary + generate project.yml | ⚠️ Needs eval |

**Output**: Writes `project.yml` with all configuration.

### Phase 5: Secrets Setup (🔐 Tab)

After the wizard, the user needs to:
1. Create a vault passphrase
2. Set up `.env` files for each environment
3. Add secret keys (API keys, tokens, etc.)
4. Optionally sync to GitHub environment secrets

**Status**: ⚠️ The secrets flow exists but the UX path from wizard → secrets is unclear.

### Phase 6: Content Setup (📁 Tab)

If the user has docs/media:
1. Browse configured content folders
2. Set up encryption key for sensitive files
3. Organize into archive if needed

**Status**: ⚠️ Content tab exists and is feature-rich, but the "first-time" experience isn't guided.

### Phase 7: Integrations (🔌 Tab)

Connect external services:
1. **Git** — verify branch status, initial commit
2. **GitHub** — authenticate, link repo
3. **CI/CD** — generate workflow files
4. **Docker** — generate Dockerfile/Compose
5. **K8s** — generate manifests
6. **Terraform** — generate configs
7. **Pages** — set up documentation site

**Status**: ⚠️ All cards exist. The "generate" modals provide scaffolding. But the user path is not guided — you have to discover each card manually.

### Phase 8: DevOps (🛠 Tab)

Health checks and operations:
1. **Security** — scan for vulnerabilities
2. **Testing** — run test suites
3. **Quality** — linting, formatting
4. **Packages** — dependency audit
5. **DNS** — domain checks
6. **K8s/Terraform** — validate configs

**Status**: ⚠️ Cards exist but many are "scan summaries" that depend on having real infrastructure first. A new project won't get much value here initially.

### Phase 9: Audit (🔍 Tab — in Debugging)

Code health analysis:
1. System profile
2. Dependency audit
3. Code structure analysis
4. Import graph

**Status**: ⚠️ Works but is a "health check" not an "onboarding" step.

---

## Identified Gaps

### 🔴 Critical Gaps

1. **No `init` command** — There's no `./manage.sh init` or `./manage.sh new <project-name>` to scaffold a new project. The tool assumes you're adopting it into an existing repo. A "0 to hero" user needs:
   - Create project directory
   - Initialize git repo
   - Create initial `project.yml`
   - Set up virtual environment
   - Scaffold basic structure

2. **No guided flow between tabs** — The wizard generates `project.yml` but then the user is dropped into the dashboard with no guidance on what to do next. There's no "next steps" prompt, no progress tracker across tabs.

3. **DevOps tab broken** — The `_devops.html` file was in the middle of a modal refactoring when we started the split. The split preserved the broken code. Syntax errors from mismatched braces may still be present in the child files.

### 🟡 Medium Gaps

4. **QUICKSTART.md is tool-developer focused** — It shows how to run the CLI, not how to set up a brand new project. It assumes the user already has a `project.yml` and modules.

5. **No "empty state" experience** — When cards have no data (no Docker, no K8s, no Terraform), the user sees "not detected" messages. These should offer actionable "Get Started" buttons or links to the wizard's integration sub-wizards.

6. **Wizard → Integration sub-wizards are deep** — The wizard Step 5 (Integrations) has Docker, K8s, Terraform, CI/CD sub-wizards that can generate config files. But these are nested UI that users may not discover. The Integrations TAB also has generate modals. **Duplication** between wizard sub-wizards and Integrations tab generate modals.

7. **No project template system** — A "0 to hero" user might want to start from a template (e.g., "Python web app" or "Node.js microservice"). There's no template catalog or scaffolding system beyond the wizard.

### 🟢 Minor Gaps

8. **Tab ordering for new users** — The tab order is Dashboard → Wizard → Secrets → Commands → Content → Integrations → DevOps → Audit → Debugging. A new user should see Wizard first, not Dashboard (which is empty on first launch).

9. **No onboarding interstitial** — When the dashboard launches for the first time (no `project.yml`), it could show a prominent "Welcome! Let's set up your project →" overlay instead of empty cards.

10. **Missing docs** — No `DEVOPS.md` or `INTEGRATIONS.md` docs. The QUICKSTART doesn't cover the wizard flow at all.

---

## The "Second Scenario" Question

You mentioned "those two scenarios." I've mapped **Scenario 1: New project from scratch**. 

What's Scenario 2? Some possibilities:
- **Existing project adoption** — user has a repo with code, wants to add devops-control-plane
- **Team onboarding** — new team member joins an already-configured project
- **Migration** — moving from another DevOps tool to this one

Please clarify so I can evaluate that path too.

---

## Recommendations (prioritized for "0 to hero")

### Immediate (enable the flow)

1. **Fix `_devops.html` syntax** — The split preserved broken code. Need to verify brace matching in child files.
2. **Add first-launch detection** — If no `project.yml` exists, auto-navigate to Wizard tab with a welcome message.
3. **Add "Next Steps" to wizard completion** — After saving `project.yml`, show a modal with recommended next steps.

### Short-term (improve the experience)

4. **Create `./manage.sh init`** — Scaffold a new project directory with initial structure.
5. **Rewrite QUICKSTART.md** — Two paths: "New project" and "Existing project."
6. **Empty state CTAs** — Each card's "not detected" message should have an actionable button.

### Medium-term (polish)

7. **Progress tracker** — A persistent "setup progress" indicator showing which areas are configured.
8. **Project templates** — Starter templates for common project types.
9. **Consolidated docs** — Create `DEVOPS.md` and `INTEGRATIONS.md`.
