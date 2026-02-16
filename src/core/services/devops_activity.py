"""
DevOps activity log — scan history and user-initiated event recording.

Maintains a JSON-based activity log at ``.state/audit_activity.json``
for the Debugging → Audit Log tab.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_ACTIVITY_FILE = ".state/audit_activity.json"
_ACTIVITY_MAX = 200  # keep last N entries


# ── Helpers ─────────────────────────────────────────────────────────


def _card_label(key: str) -> str:
    """Look up the display label for a card key."""
    from src.core.data import get_registry
    return get_registry().card_labels.get(key, key)


def _activity_path(project_root: Path) -> Path:
    return project_root / _ACTIVITY_FILE


def _extract_summary(card_key: str, data: dict) -> str:
    """Extract a one-line summary from the scan result for display."""
    if "error" in data and isinstance(data["error"], str):
        return f"Error: {data['error'][:100]}"

    # Audit-specific summaries
    if card_key == "audit:l2:risks":
        findings = data.get("findings", [])
        by_sev = {}
        for f in findings:
            s = f.get("severity", "info")
            by_sev[s] = by_sev.get(s, 0) + 1
        parts = [f"{c} {s}" for s, c in sorted(by_sev.items(), key=lambda x: {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}.get(x[0], 5))]
        return f"{len(findings)} findings ({', '.join(parts)})" if parts else f"{len(findings)} findings"

    if card_key in ("audit:scores", "audit:scores:enriched"):
        cx = data.get("complexity", {})
        qu = data.get("quality", {})
        cx_score = cx.get("score", "?")
        qu_score = qu.get("score", "?")
        enriched = qu.get("enriched", False)
        tag = " (L2 enriched)" if enriched else ""
        return f"Complexity {cx_score}/10 · Quality {qu_score}/10{tag}"

    if card_key == "audit:system":
        os_info = data.get("os", {})
        if isinstance(os_info, dict):
            os_name = os_info.get("distro", os_info.get("system", "?"))
        else:
            os_name = str(os_info)
        py = data.get("python_version", data.get("python", {}).get("version", "?"))
        tools = data.get("tools", [])
        available = sum(1 for t in tools if t.get("available"))
        return f"{os_name} · Python {py} · {available}/{len(tools)} tools available"

    if card_key == "audit:deps":
        deps = data.get("dependencies", data.get("packages", []))
        eco = data.get("ecosystems", {})
        eco_count = sum(1 for v in eco.values() if v > 0)
        if isinstance(deps, list):
            return f"{len(deps)} dependencies across {eco_count} ecosystem(s)"
        return "completed"

    if card_key == "audit:structure":
        modules = data.get("modules", [])
        entry_count = len(data.get("entrypoints", []))
        infra_parts = []
        if data.get("has_docker"): infra_parts.append("Docker")
        if data.get("has_ci"): infra_parts.append("CI")
        if data.get("has_iac"): infra_parts.append("IaC")
        infra = ", ".join(infra_parts) if infra_parts else "none"
        return f"{len(modules)} module(s) · {entry_count} entrypoint(s) · infra: {infra}"

    if card_key == "audit:clients":
        clients = data.get("clients", [])
        categories = {}
        for c in clients:
            cat = c.get("category", "other")
            categories[cat] = categories.get(cat, 0) + 1
        parts = [f"{v} {k}" for k, v in categories.items()]
        return f"{len(clients)} client(s) ({', '.join(parts)})" if parts else f"{len(clients)} client(s)"

    if card_key == "audit:l2:quality":
        summary = data.get("summary", {})
        score = summary.get("overall_score", "?")
        hotspots = data.get("hotspots", [])
        return f"Score: {score}/10 · {len(hotspots)} hotspot(s)"

    if card_key == "audit:l2:repo":
        health = data.get("health", {})
        score = health.get("score", "?")
        commits = data.get("commits", {}).get("total", "?")
        return f"Score: {score}/10 · {commits} commit(s)"

    if card_key == "audit:l2:structure":
        modules = data.get("modules", [])
        graph = data.get("import_graph", {})
        edges = len(graph.get("edges", []))
        return f"{len(modules)} module(s) · {edges} import edge(s)"

    # DevOps card summaries
    if card_key == "testing":
        stats = data.get("stats", {})
        test_files = stats.get("test_files", 0)
        functions = stats.get("test_functions", 0)
        frameworks = data.get("frameworks", [])
        fw_names = ", ".join(f.get("name", "?") for f in frameworks)
        base = f"{test_files} test files, {functions} functions"
        return f"{base} ({fw_names})" if fw_names else base

    if card_key == "security":
        findings = data.get("findings", [])
        count = data.get("finding_count", len(findings))
        posture = data.get("posture", {})
        score = posture.get("score")
        grade = posture.get("grade", "")
        parts = [f"{count} issues"]
        if score is not None:
            parts.append(f"Score: {score}")
        if grade:
            parts.append(f"({grade})")
        return " · ".join(parts)

    if card_key == "quality":
        tools = data.get("tools", [])
        names = [t.get("name", t.get("id", "?")) for t in tools if t.get("cli_available")]
        return f"{len(names)} tool(s) available: {', '.join(names[:5])}" if names else "No tools detected"

    if card_key == "packages":
        managers = data.get("managers", [])
        names = [m.get("name", "?") for m in managers if isinstance(m, dict)]
        return f"{len(managers)} manager(s): {', '.join(names)}" if names else "No package managers"

    if card_key == "env":
        envs = data.get("environments", [])
        active_env = next((e.get("name", "?") for e in envs if isinstance(e, dict) and e.get("active")), "—")
        return f"{len(envs)} environment(s), active: {active_env}"

    if card_key == "docs":
        readme = data.get("readme", {})
        has_readme = readme.get("exists") if isinstance(readme, dict) else bool(readme)
        changelog = data.get("changelog", {})
        has_cl = changelog.get("exists") if isinstance(changelog, dict) else bool(changelog)
        parts = []
        parts.append("README ✓" if has_readme else "README ✗")
        parts.append("CHANGELOG ✓" if has_cl else "CHANGELOG ✗")
        doc_dirs = data.get("doc_dirs", [])
        if doc_dirs:
            parts.append(f"{len(doc_dirs)} doc dir(s)")
        return " · ".join(parts)

    if card_key == "k8s":
        manifests = data.get("manifests", data.get("resources", []))
        if isinstance(manifests, list):
            return f"{len(manifests)} manifest(s)"
        return "completed"

    if card_key == "terraform":
        resources = data.get("resources", [])
        if isinstance(resources, list):
            return f"{len(resources)} resource(s)"
        return "completed"

    # Integration cards
    if card_key == "git":
        branch = data.get("branch", "?")
        ahead = data.get("ahead", 0)
        behind = data.get("behind", 0)
        changes = data.get("total_changes", 0)
        return f"Branch: {branch} · ↑{ahead} ↓{behind} · {changes} changed"

    if card_key == "github":
        repo = data.get("repo", data.get("full_name", "?"))
        return f"Repo: {repo}"

    if card_key == "ci":
        total = data.get("total_workflows", 0)
        providers = data.get("providers", [])
        prov_names = ", ".join(p.get("name", "?") for p in providers if isinstance(p, dict))
        base = f"{total} workflow(s)"
        return f"{base} ({prov_names})" if prov_names else base

    if card_key == "docker":
        dockerfiles = data.get("dockerfiles", [])
        services = data.get("compose_services", [])
        parts = [f"{len(dockerfiles)} Dockerfile(s)"]
        if services:
            parts.append(f"{len(services)} service(s)")
        return " · ".join(parts)

    if card_key == "dns":
        records = data.get("records", data.get("providers", []))
        return f"{len(records)} record(s)/provider(s)" if isinstance(records, list) else "completed"

    if card_key == "pages":
        segments = data.get("segments", [])
        return f"{len(segments)} segment(s)" if isinstance(segments, list) else "completed"

    if card_key == "gh-pulls":
        pulls = data.get("pulls", [])
        return f"{len(pulls)} open PR(s)" if isinstance(pulls, list) else "completed"

    if card_key == "gh-runs":
        runs = data.get("runs", [])
        if isinstance(runs, list) and runs:
            latest = runs[0]
            return f"{len(runs)} run(s) · latest: {latest.get('conclusion', latest.get('status', '?'))}"
        return "0 runs"

    if card_key == "gh-workflows":
        workflows = data.get("workflows", [])
        names = ", ".join(w.get("name", "?") for w in workflows if isinstance(w, dict))
        return f"{len(workflows)} workflow(s): {names}" if names else f"{len(workflows)} workflow(s)"

    if card_key == "project-status":
        progress = data.get("progress", {})
        complete = progress.get("complete", 0)
        total = progress.get("total", 0)
        pct = progress.get("percent", 0)
        return f"{complete}/{total} integrations ready ({pct}%)"

    if card_key == "wiz:detect":
        tools = data.get("tools", {})
        files = data.get("files", {})
        tool_ok = sum(1 for v in tools.values() if v)
        file_ok = sum(1 for v in files.values() if v)
        return f"{tool_ok}/{len(tools)} tools · {file_ok}/{len(files)} file markers"

    # Generic — try to find any count-like key
    for key in ("total", "count", "items"):
        if key in data:
            return f"{data[key]} {key}"

    return "completed"


def _extract_detail(card_key: str, data: dict) -> dict | None:
    """Extract key metrics from scan data for rich rendering in the UI.

    Returns a compact dict of the most important fields, or None if
    nothing useful can be extracted.  Kept small to avoid bloating
    the activity log file.
    """
    if "error" in data and isinstance(data["error"], str):
        return None

    if card_key == "audit:system":
        tools = data.get("tools", [])
        available = [t.get("id", "?") for t in tools if t.get("available")]
        missing = [t.get("id", "?") for t in tools if not t.get("available")]
        os_info = data.get("os", {})
        if isinstance(os_info, dict):
            os_str = os_info.get("distro", os_info.get("system", "?"))
        else:
            os_str = str(os_info)
        d: dict = {
            "os": os_str,
            "python": data.get("python_version", data.get("python", {}).get("version", "?")),
            "tools_available": ", ".join(available) if available else "none",
        }
        if missing:
            d["tools_missing"] = ", ".join(missing)
        venv = data.get("venv", {})
        if venv.get("in_venv"):
            d["venv"] = venv.get("path", "active")
        modules = data.get("modules", [])
        if modules:
            d["modules"] = ", ".join(m.get("name", "?") for m in modules[:8])
        return d

    if card_key == "audit:deps":
        eco = data.get("ecosystems", {})
        eco_active = {k: v for k, v in eco.items() if v > 0}
        deps = data.get("dependencies", [])
        categories = data.get("categories", {})
        d = {}
        if eco_active:
            d["ecosystems"] = ", ".join(f"{k} ({v})" for k, v in eco_active.items())
        if isinstance(deps, list):
            d["total_deps"] = str(len(deps))
        if categories:
            d["categories"] = ", ".join(f"{k}: {v}" for k, v in categories.items() if v > 0)
        crossovers = data.get("crossovers", [])
        if crossovers:
            d["crossovers"] = ", ".join(crossovers[:5])
        return d or None

    if card_key == "audit:structure":
        modules = data.get("modules", [])
        d = {}
        if modules:
            d["modules"] = ", ".join(m.get("name", "?") for m in modules[:10])
        entry_pts = data.get("entrypoints", [])
        if entry_pts:
            d["entrypoints"] = ", ".join(
                (ep.get("path", ep.get("name", "?")) if isinstance(ep, dict) else str(ep))
                for ep in entry_pts[:8]
            )
        for flag, label in [("has_docker", "Docker"), ("has_ci", "CI/CD"), ("has_iac", "IaC"), ("has_docs", "Docs"), ("has_tests", "Tests")]:
            if data.get(flag):
                d[label.lower()] = "✓ detected"
        return d or None

    if card_key == "audit:clients":
        clients = data.get("clients", [])
        if not clients:
            return None
        d = {}
        for c in clients[:10]:
            name = c.get("name", "?")
            cat = c.get("category", "")
            d[name] = cat
        return d

    if card_key in ("audit:scores", "audit:scores:enriched"):
        cx = data.get("complexity", {})
        qu = data.get("quality", {})
        d = {
            "complexity_score": f"{cx.get('score', '?')}/10",
            "quality_score": f"{qu.get('score', '?')}/10",
        }
        cx_bd = cx.get("breakdown", {})
        for k, item in cx_bd.items():
            d[f"cx_{k}"] = f"{item.get('score', '?')}/10"
        qu_bd = qu.get("breakdown", {})
        for k, item in qu_bd.items():
            d[f"qu_{k}"] = f"{item.get('score', '?')}/10"
        trend = data.get("trend", {})
        if trend.get("complexity_trend"):
            d["trend"] = f"cx: {trend['complexity_trend']} (Δ{trend.get('complexity_delta', 0)}), qu: {trend.get('quality_trend', '?')} (Δ{trend.get('quality_delta', 0)})"
        return d

    if card_key == "audit:l2:quality":
        summary = data.get("summary", {})
        d = {"overall_score": f"{summary.get('overall_score', '?')}/10"}
        naming = data.get("naming", {})
        if naming.get("score") is not None:
            d["naming_score"] = f"{naming['score']}/10"
        hotspots = data.get("hotspots", [])
        if hotspots:
            d["hotspots"] = ", ".join(h.get("file", "?") for h in hotspots[:5])
        return d

    if card_key == "audit:l2:repo":
        health = data.get("health", {})
        d = {"repo_score": f"{health.get('score', '?')}/10"}
        commits = data.get("commits", {})
        if commits.get("total"):
            d["total_commits"] = str(commits["total"])
        large = data.get("large_files", [])
        if isinstance(large, list) and large:
            d["large_files"] = ", ".join(f.get("path", "?") if isinstance(f, dict) else str(f) for f in large[:5])
        return d

    if card_key == "audit:l2:risks":
        findings = data.get("findings", [])
        if not findings:
            return {"findings": "0 — clean"}
        by_sev: dict = {}
        for f in findings:
            s = f.get("severity", "info")
            by_sev[s] = by_sev.get(s, 0) + 1
        d = {}
        for s in ("critical", "high", "medium", "low", "info"):
            if s in by_sev:
                d[s] = str(by_sev[s])
        # Top findings
        for f in findings[:3]:
            d[f.get("title", "finding")] = f.get("severity", "?")
        return d

    if card_key == "audit:l2:structure":
        modules = data.get("modules", [])
        graph = data.get("import_graph", {})
        d = {}
        if modules:
            d["modules"] = ", ".join(m.get("name", "?") for m in modules[:8])
        ext_deps = graph.get("external_deps", {})
        if ext_deps:
            d["external_deps"] = str(len(ext_deps))
        edges = graph.get("edges", [])
        if edges:
            d["import_edges"] = str(len(edges))
        return d or None

    # ── DevOps cards — based on actual devops_cache.json shapes ────────

    if card_key == "security":
        findings = data.get("findings", [])
        posture = data.get("posture", {})
        d = {}
        score = posture.get("score")
        if score is not None:
            d["score"] = f"{score}/100"
        grade = posture.get("grade", "")
        if grade:
            d["grade"] = grade
        d["findings"] = str(data.get("finding_count", len(findings)))
        checks = posture.get("checks", [])
        for c in checks[:6]:
            name = c.get("name", "?")
            passed = c.get("passed", False)
            cscore = c.get("score")
            val = "✓" if passed else "✗"
            if cscore is not None:
                val += f" ({int(cscore * 100)}%)"
            d[name] = val
        return d

    if card_key == "testing":
        stats = data.get("stats", {})
        d = {
            "test_files": str(stats.get("test_files", 0)),
            "test_functions": str(stats.get("test_functions", 0)),
            "test_classes": str(stats.get("test_classes", 0)),
        }
        frameworks = data.get("frameworks", [])
        if frameworks:
            d["frameworks"] = ", ".join(f.get("name", "?") for f in frameworks)
        coverage = data.get("coverage_tools", [])
        if coverage:
            d["coverage"] = ", ".join(c.get("name", "?") for c in coverage)
        ratio = stats.get("test_ratio")
        if ratio is not None:
            d["test_ratio"] = f"{ratio:.1%}" if isinstance(ratio, float) else str(ratio)
        return d

    if card_key == "quality":
        tools = data.get("tools", [])
        d = {}
        for t in tools:
            name = t.get("name", t.get("id", "?"))
            available = t.get("cli_available", False)
            config = t.get("config_file", "")
            status = "✓" if available else "✗ not installed"
            if config:
                status += f" ({config})"
            d[name] = status
        return d or {"tools": "none detected"}

    if card_key == "packages":
        managers = data.get("managers", [])
        d = {"total_managers": str(data.get("total_managers", len(managers)))}
        for m in managers[:5]:
            if not isinstance(m, dict):
                continue
            name = m.get("name", m.get("id", "?"))
            parts = []
            dep_files = m.get("dependency_files", [])
            if dep_files:
                parts.append(", ".join(dep_files))
            if m.get("has_lock"):
                parts.append("lock ✓")
            elif m.get("lock_files") == []:
                parts.append("no lock file")
            d[name] = " · ".join(parts) if parts else "detected"
        return d

    if card_key == "env":
        envs = data.get("environments", [])
        d = {"environments": str(len(envs))}
        for e in envs[:5]:
            if not isinstance(e, dict):
                continue
            name = e.get("name", "?")
            parts = []
            if e.get("active"):
                parts.append("active")
            vs = e.get("vault_state", "")
            if vs:
                parts.append(f"vault: {vs}")
            lk = e.get("local_keys", 0)
            ghs = e.get("gh_secrets", 0)
            ghv = e.get("gh_variables", 0)
            parts.append(f"{lk} local, {ghs} GH secrets, {ghv} GH vars")
            if not e.get("in_sync"):
                parts.append("⚠ out of sync")
            d[name] = " · ".join(parts)
        env_files = data.get("env_files", [])
        if env_files:
            names = []
            for f in env_files[:5]:
                if isinstance(f, dict):
                    n = f.get("name", "?")
                    vc = f.get("var_count", "")
                    names.append(f"{n} ({vc} vars)" if vc else n)
                else:
                    names.append(str(f))
            d["env_files"] = ", ".join(names)
        return d

    if card_key == "docs":
        d = {}
        readme = data.get("readme", {})
        if isinstance(readme, dict):
            if readme.get("exists"):
                d["readme"] = readme.get("path", "✓")
                lines = readme.get("lines")
                if lines:
                    d["readme_lines"] = str(lines)
            else:
                d["readme"] = "✗ missing"
        changelog = data.get("changelog", {})
        if isinstance(changelog, dict):
            d["changelog"] = changelog.get("path", "✓") if changelog.get("exists") else "✗ missing"
        elif isinstance(changelog, bool):
            d["changelog"] = "✓" if changelog else "✗ missing"
        license_ = data.get("license", {})
        if isinstance(license_, dict):
            d["license"] = license_.get("path", "✓") if license_.get("exists") else "✗ missing"
        elif isinstance(license_, bool):
            d["license"] = "✓" if license_ else "✗ missing"
        contrib = data.get("contributing", {})
        if isinstance(contrib, dict) and contrib.get("exists"):
            d["contributing"] = contrib.get("path", "✓")
        doc_dirs = data.get("doc_dirs", [])
        if doc_dirs:
            parts = []
            for dd in doc_dirs[:5]:
                if isinstance(dd, dict):
                    parts.append(f"{dd.get('name', '?')} ({dd.get('doc_count', dd.get('file_count', '?'))} files)")
                else:
                    parts.append(str(dd))
            d["doc_dirs"] = ", ".join(parts)
        return d or {"docs": "none detected"}

    if card_key == "git":
        commit = data.get("last_commit", {})
        d = {
            "branch": data.get("branch", "?"),
            "commit": data.get("commit", "?"),
            "staged": str(data.get("staged_count", 0)),
            "modified": str(data.get("modified_count", 0)),
            "untracked": str(data.get("untracked_count", 0)),
            "ahead": str(data.get("ahead", 0)),
            "behind": str(data.get("behind", 0)),
        }
        remote = data.get("remote_url", "")
        if remote:
            d["remote"] = remote
        if isinstance(commit, dict) and commit.get("message"):
            d["last_commit"] = commit["message"][:80]
        return d

    if card_key == "github":
        d = {}
        if data.get("available"):
            d["cli"] = "✓ available"
        if data.get("authenticated"):
            d["auth"] = "✓ logged in"
        repo = data.get("repo", "")
        if repo:
            d["repo"] = repo
        version = data.get("version", "")
        if version:
            d["version"] = version
        return d or {"status": "not available"}

    if card_key == "ci":
        providers = data.get("providers", [])
        total = data.get("total_workflows", 0)
        d = {"total_workflows": str(total)}
        for p in (providers if isinstance(providers, list) else [])[:5]:
            if isinstance(p, dict):
                d[p.get("name", p.get("id", "?"))] = f"{p.get('workflows', 0)} workflow(s)"
        return d

    if card_key == "docker":
        d = {}
        d["docker"] = "✓ available" if data.get("available") else "✗ not available"
        version = data.get("version", "")
        if version:
            d["version"] = version.replace("Docker version ", "").split(",")[0]
        if data.get("compose_available"):
            d["compose"] = f"✓ (v{data.get('compose_version', '?').split(',')[0]})"
        dockerfiles = data.get("dockerfiles", [])
        if dockerfiles:
            d["dockerfiles"] = ", ".join(dockerfiles[:5])
        services = data.get("compose_services", [])
        if services:
            d["services"] = ", ".join(services[:8])
        return d

    if card_key == "k8s":
        d = {}
        kubectl = data.get("kubectl", {})
        if kubectl.get("available"):
            d["kubectl"] = "✓ available"
        dirs = data.get("manifest_dirs", [])
        if dirs:
            d["manifest_dirs"] = ", ".join(dirs[:5])
        manifests = data.get("manifests", [])
        d["manifest_files"] = str(len(manifests))
        for mf in manifests[:5]:
            if isinstance(mf, dict):
                resources = mf.get("resources", [])
                kinds = ", ".join(r.get("kind", "?") for r in resources[:3])
                d[mf.get("path", "?")] = kinds or f"{mf.get('count', 0)} resource(s)"
        return d

    if card_key == "terraform":
        d = {}
        cli = data.get("cli", {})
        if cli.get("available"):
            d["cli"] = f"✓ v{cli.get('version', '?')}"
        d["has_terraform"] = "✓" if data.get("has_terraform") else "✗ no config"
        resources = data.get("resources", [])
        d["resources"] = str(len(resources))
        if data.get("initialized"):
            d["initialized"] = "✓"
        backend = data.get("backend")
        if backend:
            d["backend"] = str(backend)
        return d

    if card_key == "dns":
        d = {}
        providers = data.get("providers", [])
        records = data.get("records", [])
        d["providers"] = str(len(providers) if isinstance(providers, list) else 0)
        d["records"] = str(len(records) if isinstance(records, list) else 0)
        domains = data.get("domains", [])
        if isinstance(domains, list) and domains:
            d["domains"] = ", ".join(str(dm) for dm in domains[:5])
        cdn = data.get("cdn", data.get("cdn_provider", ""))
        if cdn:
            d["cdn"] = str(cdn)
        return d

    if card_key == "pages":
        segments = data.get("segments", [])
        d = {"segments": str(len(segments) if isinstance(segments, list) else 0)}
        for s in (segments if isinstance(segments, list) else [])[:5]:
            if isinstance(s, dict):
                d[s.get("name", s.get("path", "?"))] = s.get("type", "segment")
        builder = data.get("builder", "")
        if builder:
            d["builder"] = str(builder)
        return d

    if card_key == "project-status":
        integrations = data.get("integrations", {})
        progress = data.get("progress", {})
        d = {}
        if progress:
            d["progress"] = f"{progress.get('complete', 0)}/{progress.get('total', 0)} ({progress.get('percent', 0)}%)"
        for k, v in integrations.items():
            if isinstance(v, dict):
                d[k] = v.get("status", "?")
        return d or None

    if card_key in ("gh-pulls", "gh-runs", "gh-workflows"):
        items_key = card_key.split("-")[-1]  # pulls, runs, workflows
        items = data.get(items_key, [])
        d = {items_key: str(len(items))}
        for item in (items if isinstance(items, list) else [])[:5]:
            if isinstance(item, dict):
                name = item.get("name", item.get("title", "?"))
                status = item.get("status", item.get("state", item.get("conclusion", "?")))
                d[name] = status
        return d

    # Generic fallback: extract any top-level scalar fields
    d = {}
    for k, v in data.items():
        if isinstance(v, (str, int, float, bool)) and k not in ("_cache", "_meta"):
            d[k] = str(v)
        if len(d) >= 10:
            break
    return d or None


# ── Recording ───────────────────────────────────────────────────────


def record_scan_activity(
    project_root: Path,
    card_key: str,
    status: str,
    elapsed_s: float,
    data: dict,
    error_msg: str = "",
    *,
    bust: bool = False,
) -> None:
    """Record a scan computation in the activity log."""
    import datetime

    detail = _extract_detail(card_key, data) if status == "ok" else None

    entry = {
        "ts": time.time(),
        "iso": datetime.datetime.now(datetime.UTC).isoformat(),
        "card": card_key,
        "label": _card_label(card_key),
        "status": status,
        "duration_s": elapsed_s,
        "summary": _extract_summary(card_key, data) if status == "ok" else error_msg,
        "bust": bust,
    }
    if detail:
        entry["detail"] = detail

    path = _activity_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing
    entries: list[dict] = []
    if path.exists():
        try:
            entries = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            entries = []

    entries.append(entry)

    # Trim to max
    if len(entries) > _ACTIVITY_MAX:
        entries = entries[-_ACTIVITY_MAX:]

    try:
        path.write_text(json.dumps(entries, default=str), encoding="utf-8")
    except IOError as e:
        logger.warning("Failed to write audit activity: %s", e)


def record_event(
    project_root: Path,
    label: str,
    summary: str,
    *,
    detail: dict | None = None,
    card: str = "event",
    action: str | None = None,
    target: str | None = None,
    before_state: dict | None = None,
    after_state: dict | None = None,
) -> None:
    """Record a user-initiated action in the audit activity log.

    Unlike ``record_scan_activity`` (scan computations), this logs
    arbitrary events like finding dismissals, so they appear
    in the Debugging → Audit Log tab.

    Optional audit fields (when provided, enrich the log entry):
        action       — verb: created, modified, deleted, renamed, etc.
        target       — what was acted on (file path, resource name)
        before_state — state before the change (size, lines, hash, etc.)
        after_state  — state after the change
    """
    import datetime

    entry = {
        "ts": time.time(),
        "iso": datetime.datetime.now(datetime.UTC).isoformat(),
        "card": card,
        "label": label,
        "status": "ok",
        "duration_s": 0,
        "summary": summary,
        "bust": False,
    }
    if detail:
        entry["detail"] = detail
    if action:
        entry["action"] = action
    if target:
        entry["target"] = target
    if before_state:
        entry["before"] = before_state
    if after_state:
        entry["after"] = after_state

    path = _activity_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)

    entries: list[dict] = []
    if path.exists():
        try:
            entries = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            entries = []

    entries.append(entry)
    if len(entries) > _ACTIVITY_MAX:
        entries = entries[-_ACTIVITY_MAX:]

    try:
        path.write_text(json.dumps(entries, default=str), encoding="utf-8")
    except IOError as e:
        logger.warning("Failed to write audit event: %s", e)


# ── Loading ─────────────────────────────────────────────────────────


def load_activity(project_root: Path, n: int = 50) -> list[dict]:
    """Load the latest N audit scan activity entries.

    If no activity file exists yet but cached data does, seed
    the activity log from existing cache metadata so the user
    sees historical scan info rather than an empty log.
    """
    import datetime

    path = _activity_path(project_root)
    entries: list[dict] = []

    if path.exists():
        try:
            entries = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            entries = []

    # ── Seed from cache if empty ────────────────────────────────
    if not entries:
        from src.core.services.devops_cache import _load_cache

        cache = _load_cache(project_root)
        if cache:
            for card_key, entry in cache.items():
                cached_at = entry.get("cached_at", 0)
                elapsed = entry.get("elapsed_s", 0)
                if not cached_at:
                    continue
                iso = datetime.datetime.fromtimestamp(
                    cached_at, tz=datetime.UTC
                ).isoformat()
                entries.append({
                    "ts": cached_at,
                    "iso": iso,
                    "card": card_key,
                    "label": _card_label(card_key),
                    "status": "ok",
                    "duration_s": elapsed,
                    "summary": "loaded from cache (historical)",
                    "bust": False,
                })
            # Sort by timestamp
            entries.sort(key=lambda e: e.get("ts", 0))
            # Persist the seeded data
            if entries:
                try:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(
                        json.dumps(entries, default=str), encoding="utf-8"
                    )
                except IOError:
                    pass

    return entries[-n:]
