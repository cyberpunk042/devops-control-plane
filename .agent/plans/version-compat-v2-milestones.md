# Version Compatibility System v2 — Complete Redesign

> **Status**: In Progress
> **Scope**: Replace the entire module_upgrade/automation system
> **Scale**: 10 milestones, 37 spec documents, all 10 supported languages, all directions

---

## Document Index

### Architecture (M1–M3)
| # | Document | Path | Status |
|---|----------|------|--------|
| 1 | System architecture overview | `.agent/plans/compat-v2/01-system-architecture.md` | draft |
| 2 | Feature database schema & format | `.agent/plans/compat-v2/02-feature-database-schema.md` | draft |
| 3 | AST detection engine design | `.agent/plans/compat-v2/03-ast-detection-engine.md` | draft |
| 4 | Import chain resolver design | `.agent/plans/compat-v2/04-import-chain-resolver.md` | draft |
| 5 | Detection-fix coupling spec | `.agent/plans/compat-v2/05-detection-fix-coupling.md` | draft |

### Execution & Lifecycle (M4–M6)
| # | Document | Path | Status |
|---|----------|------|--------|
| 6 | Step lifecycle state machine spec | `.agent/plans/compat-v2/06-step-lifecycle-state-machine.md` | draft |
| 7 | Verification loop spec | `.agent/plans/compat-v2/07-verification-loop.md` | draft |
| 8 | Project-wide analysis spec | `.agent/plans/compat-v2/08-project-wide-analysis.md` | draft |
| 9 | Batch execution & orchestration spec | `.agent/plans/compat-v2/09-batch-execution.md` | draft |
| 10 | Rollback & undo spec | `.agent/plans/compat-v2/10-rollback-undo.md` | draft |

### Direction & Resolution (M7)
| # | Document | Path | Status |
|---|----------|------|--------|
| 11 | Upgrade direction spec | `.agent/plans/compat-v2/11-upgrade-direction.md` | draft |
| 12 | Downgrade direction spec | `.agent/plans/compat-v2/12-downgrade-direction.md` | draft |
| 13 | Version constraint resolution | `.agent/plans/compat-v2/13-version-constraint-resolution.md` | draft |
| 14 | Dependency analysis spec | `.agent/plans/compat-v2/14-dependency-analysis.md` | draft |

### Fix System (M8)
| # | Document | Path | Status |
|---|----------|------|--------|
| 15 | Fix transform catalog | `.agent/plans/compat-v2/15-fix-transform-catalog.md` | draft |
| 16 | Fix verification protocol | `.agent/plans/compat-v2/16-fix-verification-protocol.md` | draft |
| 17 | Backport & polyfill registry | `.agent/plans/compat-v2/17-backport-polyfill-registry.md` | draft |
| 18 | Error classification taxonomy | `.agent/plans/compat-v2/18-error-classification.md` | draft |

### Language Modules (M9)
| # | Document | Path | Status |
|---|----------|------|--------|
| 19 | Python language module | `.agent/plans/compat-v2/19-lang-python.md` | draft |
| 20 | JavaScript/TypeScript language module | `.agent/plans/compat-v2/20-lang-javascript-typescript.md` | draft |
| 21 | Go language module | `.agent/plans/compat-v2/21-lang-go.md` | draft |
| 22 | Rust language module | `.agent/plans/compat-v2/22-lang-rust.md` | draft |
| 23 | Ruby language module | `.agent/plans/compat-v2/23-lang-ruby.md` | draft |
| 24 | Java language module | `.agent/plans/compat-v2/24-lang-java.md` | draft |
| 25 | C#/.NET language module | `.agent/plans/compat-v2/25-lang-csharp.md` | draft |
| 26 | PHP language module | `.agent/plans/compat-v2/26-lang-php.md` | draft |
| 27 | Elixir language module | `.agent/plans/compat-v2/27-lang-elixir.md` | draft |

### Edge Cases (M9)
| # | Document | Path | Status |
|---|----------|------|--------|
| 28 | Edge case framework spec | `.agent/plans/compat-v2/28-edge-case-framework.md` | draft |
| 29 | Multi-language plugin architecture | `.agent/plans/compat-v2/29-multi-language-plugin-arch.md` | draft |

### Integration & UX (M10)
| # | Document | Path | Status |
|---|----------|------|--------|
| 30 | API & endpoint design | `.agent/plans/compat-v2/30-api-endpoint-design.md` | draft |
| 31 | Web UI integration | `.agent/plans/compat-v2/31-web-ui-integration.md` | draft |
| 32 | CLI integration | `.agent/plans/compat-v2/32-cli-integration.md` | draft |
| 33 | Audit trail & history spec | `.agent/plans/compat-v2/33-audit-trail.md` | draft |
| 34 | Configuration & settings spec | `.agent/plans/compat-v2/34-configuration-settings.md` | draft |

### Validation & Migration
| # | Document | Path | Status |
|---|----------|------|--------|
| 35 | Test plan & validation strategy | `.agent/plans/compat-v2/35-test-plan.md` | draft |
| 36 | Migration plan (v1 → v2) | `.agent/plans/compat-v2/36-migration-plan.md` | draft |
| 37 | Contributor guide | `.agent/plans/compat-v2/37-contributor-guide.md` | draft |

---

## Milestones

| Milestone | Focus | Documents |
|-----------|-------|-----------|
| M1 | Feature database & data model | 1, 2 |
| M2 | AST detection engine | 3, 29 |
| M3 | Import chain resolution | 4, 8 |
| M4 | Detection-fix coupling | 5, 15, 16 |
| M5 | Step lifecycle & state machine | 6, 9, 10 |
| M6 | Verification loop | 7, 17, 18 |
| M7 | Direction & constraint resolution | 11, 12, 13, 14 |
| M8 | Fix system | 15, 16, 17, 18 |
| M9 | Language modules & edge cases | 19–29 |
| M10 | Integration & UX | 30–34 |
| — | Validation & migration | 35–37 |

---

## Supported Languages

Python, JavaScript, TypeScript, Go, Rust, Ruby, Java, C#/.NET, PHP, Elixir

---

## Principles

1. Never guess — AST, not regex
2. Never disconnect — detection and fix are one unit
3. Never lie — step state reflects reality
4. Never silo — follow import chains across boundaries
5. Never skip verification — every fix proves itself
6. Never auto-mark — only verified success marks done
