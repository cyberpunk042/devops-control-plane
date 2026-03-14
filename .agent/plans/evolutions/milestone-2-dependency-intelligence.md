# Milestone 2 — Dependency Intelligence
> Status: SCAFFOLDED — not yet discussed in detail

---

## Goal
Make the project's own dependencies first-class citizens of the platform.
Detect what the project needs, manage it at the right scope, stream it live, remediate issues.

---

## Evolutions included

### E1 — Dependency-Aware Package Management with Live Observability
- Detect dependency manifests (requirements.txt, package.json, go.mod, Cargo.toml, etc.)
- Tree-select operation scope: Global → Group → Package
- Run native commands per group (pip install -r, npm install, go mod download)
- Stream output live via SSE
- Detect warnings/errors during install
- Surface remediations via existing remediation system

### E10 — Dependency Graph & Impact Analysis
- Model relationships between modules and their dependencies
- Blast radius analysis: "upgrading X affects these 4 modules"
- Visual graph of inter-module dependencies
- Informs tree-select operations (E1) with impact context before acting

---

## What this milestone does NOT include
- Tool installation (that's M3 — different concern: system tools vs. project packages)
- Promotion or env management (M4)

---

## Dependencies
- M1: timeline events for package operations; security view for CVE signals on packages

## Unlocks
- M3: dependency graph informs stack upgrade impact analysis
- M4: package state feeds the readiness score and changelog

---

## Open questions
- [ ] Where does the dependency tree UI live? New tab or inside existing packages section?
- [ ] How does the graph visualization work? (mermaid? d3? something else?)
- [ ] How do we handle monorepos with multiple package.json files?
- [ ] What is the rollback mechanism per ecosystem? (pip: requirements.txt snapshot, npm: package-lock.json restore, etc.)
- [ ] How deep does the graph go? Direct deps only or transitive?
- [ ] How does the remediation system get extended for ecosystem-specific issues?

---

## Rough scope estimate
- E1: Backend (manifest scanner, native command executor, stream parser) + Frontend (tree-select UI, SSE live feed)
- E10: Backend (graph builder, impact analyzer) + Frontend (graph visualization)
- Both share the manifest scanner as a foundation
