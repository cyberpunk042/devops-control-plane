# E10 Chunk 4 — Wire Everything + Final Validation

> Connect all new handlers to wizard, update all recipes, validate coverage.
> Depends on: Chunks 1 + 2 + 3 complete.
> Architecture: `.agent/docs/E10-wizard-automation-architecture.md`
> Status: READY FOR PLANNING

---

## What This Chunk Delivers

Everything from chunks 1-3 connected end-to-end:
- Dep checkers wired through wizard for the alternatives flow
- Subprocess ops wired through wizard for streaming output
- All recipes updated with correct automation_ids
- Final automation coverage audit

---

## Execution Steps

### Step 1: Connect dep checkers to wizard alternatives flow

When `update_deps_interactive` (or language-specific variant) is triggered:
1. Wizard phase 1: run the dep compat checker → get incompatible list
2. Wizard phase 2: for each incompatible dep, query alternatives from registry
3. Frontend shows alternatives per dep, user picks
4. Wizard phase 3: apply chosen versions to dependency file

### Step 2: Connect subprocess ops to wizard

When `run_go_mod_tidy` / `run_bundle_update` / etc. is triggered:
1. Wizard shows command preview + working directory
2. User confirms
3. Wizard streams subprocess output
4. Handle success/failure

### Step 3: Final recipe audit

Ensure every step that CAN be automated IS marked automatable with correct automation_id.
Run the automation coverage audit script.

### Step 4: Test all languages end-to-end

For each language:
1. Create a plan → verify intelligent checklist generated
2. Click automate on each automatable step → verify it works
3. Verify wizard opens for complex steps
4. Verify inline preview works for simple steps

### Step 5: Update documentation

- Update `README.md` with new handlers
- Update architecture doc with final coverage numbers

---

## Verification Checklist

| Language | Config Edit | Dep Check | Dep Alternatives | Subprocess | CI Scan | Rescan |
|----------|------------|-----------|-----------------|------------|---------|--------|
| Python | ✅ pyproject/setup.py/cfg | ✅ PyPI | ✅ PyPI alternatives | N/A | ✅ | ✅ |
| Node | ✅ package.json | ✅ npm | ✅ npm alternatives | N/A | ✅ | ✅ |
| Go | ✅ go.mod | ✅ crates | ✅ crates alternatives | ✅ go mod tidy | ✅ | ✅ |
| Rust | ✅ Cargo.toml | ✅ crates.io | ✅ crates alternatives | N/A | ✅ | ✅ |
| Ruby | ✅ Gemfile | ✅ rubygems | ✅ rubygems alternatives | ✅ bundle update | ✅ | ✅ |
| Java | ✅ pom.xml/gradle | 📋 manual | 📋 manual | N/A | ✅ | ✅ |
| C# | ✅ .csproj | 📋 manual | 📋 manual | ✅ dotnet restore | ✅ | ✅ |
| PHP | ✅ composer.json | ✅ packagist | ✅ packagist alternatives | ✅ composer update | ✅ | ✅ |
| Elixir | ✅ mix.exs | ✅ hex.pm | ✅ hex alternatives | ✅ mix deps.get | ✅ | ✅ |

Java and C# dep checking remains manual (Maven API lacks version info, NuGet is complex).
Everything else is automated.

---

## Files Summary

| Action | File | Est. Lines |
|--------|------|-----------|
| EDIT | `automation/wizard.py` | +80 (dep alternatives + subprocess integration) |
| EDIT | Recipe JSON files | ~30 total |
| EDIT | `README.md` | +50 |

**Total edits:** ~160 lines
