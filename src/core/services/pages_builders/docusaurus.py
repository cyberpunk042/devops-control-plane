"""
Docusaurus builder — React-based documentation framework.

Pipeline stages:
  1. source     — Copy source files, filter hidden dirs/files
  2. transform  — MD → MDX (admonitions, frontmatter, link rewriting, rename)
  3. scaffold   — Generate config from templates + feature registry
  4. install    — npm install (cached — skips if package.json unchanged)
  5. build      — npx docusaurus build (with smart skip + Rspack recovery)

Build Intelligence (Phase 4):
  - Content hash skip: hashes workspace files, skips build if unchanged
  - Cache management: clears .docusaurus/ on CSS/theme/config changes
  - Rspack segfault recovery: retries on exit 139 (SIGSEGV)
  - NODE_OPTIONS: configurable memory limit (default 4GB)
  - Clean build: wipe caches via segment config flag

Uses a template-based scaffold: real TypeScript/CSS/JSON template files
with conditional blocks (// __IF_FEATURE_xxx__) processed by the template
engine. Features are defined in the feature registry (template_engine.py),
not hardcoded as booleans.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from collections.abc import Generator
from pathlib import Path

from .base import (
    BuilderInfo,
    LogStream,
    PageBuilder,
    SegmentConfig,
    StageInfo,
)
from .docusaurus_transforms import (
    convert_admonitions,
    enrich_frontmatter,
    escape_jsx_angles,
    rewrite_links,
)
from .template_engine import (
    FEATURES,
    TEMPLATES_DIR,
    build_custom_css,
    build_package_json,
    compute_build_hash,
    process_docusaurus_config,
    process_sidebars,
    process_template,
    resolve_features,
)


class DocusaurusBuilder(PageBuilder):
    """Build docs with Docusaurus v3 + MD → MDX transform pipeline."""

    def info(self) -> BuilderInfo:
        return BuilderInfo(
            name="docusaurus",
            label="Docusaurus",
            requires=["npx"],
            description="React-based docs framework with MDX support. Requires Node.js.",
            install_hint="Install Node.js 18+: https://nodejs.org",
            install_cmd=["npm", "install", "-g", "npx"],
        )

    # ── Pipeline stages ─────────────────────────────────────────────

    def pipeline_stages(self) -> list[StageInfo]:
        return [
            StageInfo("source", "Resolve Source",
                      "Copy source files, exclude hidden dirs"),
            StageInfo("transform", "MD → MDX Transform",
                      "Convert admonitions, enrich frontmatter, rewrite links"),
            StageInfo("scaffold", "Generate Config",
                      "Create docusaurus.config.js, sidebars, CSS, package.json"),
            StageInfo("install", "npm install",
                      "Install Node.js dependencies (cached)"),
            StageInfo("build", "Docusaurus Build",
                      "Run npx docusaurus build"),
        ]

    def run_stage(
        self,
        stage: str,
        segment: SegmentConfig,
        workspace: Path,
    ) -> LogStream:
        if stage == "source":
            yield from self._stage_source(segment, workspace)
        elif stage == "transform":
            yield from self._stage_transform(segment, workspace)
        elif stage == "scaffold":
            yield from self._stage_scaffold(segment, workspace)
        elif stage == "install":
            yield from self._stage_install(segment, workspace)
        elif stage == "build":
            yield from self._stage_build(segment, workspace)
        else:
            raise RuntimeError(f"Unknown stage: {stage}")

    # ── Stage 1: Source ──────────────────────────────────────────────

    def _stage_source(self, segment: SegmentConfig, workspace: Path) -> LogStream:
        """Copy source files into workspace/docs/, excluding hidden dirs."""
        source = Path(segment.source).resolve()
        docs_dir = workspace / "docs"

        # Clean and recreate docs dir
        if docs_dir.exists():
            shutil.rmtree(docs_dir)
        docs_dir.mkdir(parents=True)

        yield f"Source: {source}"

        file_count = 0
        skip_count = 0

        if source.is_dir():
            for src_file in sorted(source.rglob("*")):
                rel = src_file.relative_to(source)

                # Skip hidden directories and their contents
                parts = rel.parts
                if any(p.startswith(".") for p in parts):
                    skip_count += 1
                    continue
                if any(p == "__pycache__" for p in parts):
                    skip_count += 1
                    continue

                dst_file = docs_dir / rel

                if src_file.is_dir():
                    dst_file.mkdir(parents=True, exist_ok=True)
                    continue

                # Copy file
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(src_file), str(dst_file))
                file_count += 1

            yield f"Copied {file_count} files (skipped {skip_count} hidden)"
        else:
            # Source dir doesn't exist (standalone smart folder) — skip copy
            docs_dir.mkdir(parents=True, exist_ok=True)
            yield f"Virtual source (standalone smart folder)"

        # Ensure a root index page exists — Docusaurus needs it for the landing
        index_candidates = [
            docs_dir / "index.md",
            docs_dir / "index.mdx",
            docs_dir / "intro.md",
            docs_dir / "intro.mdx",
            docs_dir / "README.md",
        ]
        if not any(c.exists() for c in index_candidates):
            title = segment.config.get("title", segment.name.title())
            # Build a simple index from top-level .md files
            links = []
            for f in sorted(docs_dir.glob("*.md")):
                name = f.stem
                label = name.replace("_", " ").replace("-", " ").title()
                links.append(f"- [{label}](./{name}.md)")

            index_content = (
                "---\n"
                f"title: {title}\n"
                "slug: /\n"
                "sidebar_position: 1\n"
                "---\n\n"
                f"# {title}\n\n"
                f"Welcome to **{title}** documentation.\n\n"
            )
            if links:
                index_content += "## Contents\n\n" + "\n".join(links) + "\n"

            (docs_dir / "index.md").write_text(index_content, encoding="utf-8")
            yield "Generated docs/index.md (landing page)"

        # ── Smart folder staging ─────────────────────────────────────
        # If any smart folders target this segment's source folder,
        # copy their discovered files into docs/<smart_folder_name>/
        try:
            from src.core.services.config_ops import read_config
            from src.core.services import smart_folders as sf

            # Find the project root (walk up from source path)
            project_root = source
            for parent in [source] + list(source.parents):
                if (parent / "project.yml").is_file():
                    project_root = parent
                    break

            cfg = read_config(project_root).get("config", {})
            smart_list = cfg.get("smart_folders", [])
            modules = cfg.get("modules", [])

            # The segment source relative to project root
            seg_source_rel = str(source.relative_to(project_root))

            for smart in smart_list:
                target = smart.get("target", "")
                name = smart.get("name", "")
                if not target or not name:
                    continue
                # Match if segment source equals the target folder,
                # or if this is a standalone smart folder (target == name)
                # and the segment source is the smart folder name
                is_standalone = (target == name)
                if seg_source_rel != target and seg_source_rel != name:
                    continue

                # Discover and resolve
                files = sf.discover(project_root, smart.get("sources", []))
                if not files:
                    continue

                resolved = sf.resolve(project_root, smart, modules)

                # Standalone: files go directly into docs_dir (root of the site)
                # Targeted: files go into docs_dir/<name>/ (subfolder of parent site)
                staging_root = docs_dir if is_standalone else docs_dir / name
                staging_root.mkdir(parents=True, exist_ok=True)
                sf_count = 0

                for group in resolved.get("groups", []):
                    mod_name = group["module"]
                    tree = group["tree"]

                    def _copy_tree_files(node, dest_dir):
                        nonlocal sf_count
                        dest_dir.mkdir(parents=True, exist_ok=True)
                        for f in node.get("files", []):
                            src = project_root / f["source_path"]
                            dst = dest_dir / f["name"]
                            if src.is_file():
                                shutil.copy2(str(src), str(dst))
                                sf_count += 1
                        for child in node.get("children", []):
                            _copy_tree_files(child, dest_dir / child["name"])

                    _copy_tree_files(tree, staging_root / mod_name)

                if sf_count > 0:
                    yield f"📂 Smart folder '{name}': staged {sf_count} docs from code"

                # ── Run enrichment pipeline ──────────────────────────
                from src.core.services.pages_builders.smart_folder_enrichment import enrich
                enrich_logs = enrich(
                    docs_dir=docs_dir,
                    resolved=resolved,
                    modules=modules,
                    smart_folder=smart,
                )
                for log_line in enrich_logs:
                    yield log_line

                # ── Precompute audit data for remark plugin ──────────
                try:
                    from src.core.services.pages_builders.audit_directive import (
                        precompute_audit_data,
                    )
                    audit_map = precompute_audit_data(
                        docs_dir=docs_dir,
                        project_root=project_root,
                        modules=modules,
                        smart_folders=smart_list,
                    )
                    if audit_map:
                        audit_path = workspace / "_audit_data.json"
                        audit_path.write_text(
                            json.dumps(audit_map, indent=2, default=str),
                            encoding="utf-8",
                        )
                        yield f"  📊 Pre-computed audit data for {len(audit_map)} file(s)"
                except Exception as exc:
                    log.warning("Audit directive precompute skipped: %s", exc)

        except Exception as e:
            yield f"⚠️ Smart folder staging skipped: {e}"

    # ── Stage 2: Transform ───────────────────────────────────────────

    def _stage_transform(self, segment: SegmentConfig, workspace: Path) -> LogStream:
        """Transform .md files → .mdx with admonitions, frontmatter, links."""
        docs_dir = workspace / "docs"
        if not docs_dir.is_dir():
            raise RuntimeError("Source files not found — run 'source' stage first")

        base_url = segment.config.get("base_url", "")
        transformed = 0
        skipped = 0

        # Process all .md files (not .mdx — those are already in target format)
        for md_file in sorted(docs_dir.rglob("*.md")):
            content = md_file.read_text(encoding="utf-8")
            original = content

            # Apply transforms
            content = convert_admonitions(content)
            content = enrich_frontmatter(content, md_file)
            content = rewrite_links(content, segment.path, base_url)
            content = escape_jsx_angles(content)

            # Write as .mdx
            mdx_path = md_file.with_suffix(".mdx")
            mdx_path.write_text(content, encoding="utf-8")

            # Remove the original .md (we've written the .mdx)
            if md_file.exists():
                md_file.unlink()

            rel = mdx_path.relative_to(docs_dir)
            if content != original:
                yield f"  ✎ {rel} (transformed)"
                transformed += 1
            else:
                yield f"  → {rel}"
                skipped += 1

        yield f"Transformed {transformed} files, renamed {skipped} (.md → .mdx)"

    # ── Stage 3: Scaffold ────────────────────────────────────────────

    def _stage_scaffold(self, segment: SegmentConfig, workspace: Path) -> LogStream:
        """Generate Docusaurus project files from templates + feature registry.

        Processes template files with conditional blocks based on enabled
        features, substitutes placeholders, and writes the result to the
        workspace. JSON-based files (package.json) are built programmatically
        since JSON doesn't support comments.
        """
        workspace.mkdir(parents=True, exist_ok=True)

        # ── Resolve features ──
        user_features = segment.config.get("features", {})
        features = resolve_features(user_features)
        enabled_names = [k for k, v in features.items() if v]
        yield f"Features: {', '.join(enabled_names) or 'none'}"

        # ── Gather placeholders ──
        site_title = segment.config.get("title", segment.name.title())
        site_tagline = segment.config.get("tagline", "Documentation")
        base_url = segment.config.get("base_url", f"/pages/site/{segment.name}/")
        site_url = segment.config.get("site_url", "https://example.com")
        repo_url = self._detect_repo_url(segment) if features.get("github") else ""
        footer_copyright = segment.config.get(
            "footer_copyright",
            f"Built with Docusaurus · Managed by DevOps Control Plane",
        )
        theme_color = segment.config.get("theme_color", "#6366f1")

        # Prism theme pair (format: "lightTheme/darkTheme")
        prism_pair = segment.config.get("prism_theme", "github/dracula")
        if "/" in prism_pair:
            prism_light, prism_dark = prism_pair.split("/", 1)
        else:
            prism_light, prism_dark = "github", "dracula"

        placeholders = {
            "__SITE_TITLE__": site_title,
            "__SITE_TAGLINE__": site_tagline,
            "__SITE_URL__": site_url,
            "__BASE_URL__": base_url,
            "__REPO_URL__": repo_url,
            "__FOOTER_COPYRIGHT__": footer_copyright,
            "__THEME_COLOR__": theme_color,
            "__PKG_NAME__": f"pages-{segment.name}",
            "__PRISM_LIGHT_THEME__": prism_light,
            "__PRISM_DARK_THEME__": prism_dark,
        }

        # ── 1. docusaurus.config.ts ──
        navbar_items = segment.config.get("navbar_items", None)

        # Auto-inject sibling segment links if no explicit navbar_items
        if navbar_items is None:
            try:
                import yaml
                # Derive project root from workspace path
                # workspace = project_root / .pages / segment_name
                project_root = workspace.parent.parent
                proj_yml = project_root / "project.yml"
                if proj_yml.is_file():
                    with open(proj_yml, encoding="utf-8") as f:
                        raw = yaml.safe_load(f) or {}
                    all_segments = raw.get("pages", {}).get("segments", [])
                    sibling_links = []
                    for seg in all_segments:
                        seg_name = seg.get("name", "")
                        if seg_name == segment.name:
                            continue  # Skip self
                        seg_title = seg.get("config", {}).get(
                            "title",
                            seg_name.replace("-", " ").replace("_", " ").title(),
                        )
                        # Use type: 'html' with a raw <a> tag to bypass
                        # Docusaurus SPA router — forces real page load
                        seg_url = f"/pages/site/{seg_name}/"
                        sibling_links.append({
                            "type": "html",
                            "value": f'<a href="{seg_url}" class="navbar__link">{seg_title}</a>',
                            "position": "left",
                        })
                    if sibling_links:
                        navbar_items = sibling_links
                        yield f"Navbar: added {len(sibling_links)} sibling segment link(s)"
            except Exception as e:
                log.warning("Failed to inject sibling segment links: %s", e)

        extra_rehype = segment.config.get("rehype_plugins", None)
        config_content = process_docusaurus_config(
            features, placeholders,
            navbar_items=navbar_items,
            extra_rehype=extra_rehype,
        )
        (workspace / "docusaurus.config.ts").write_text(config_content, encoding="utf-8")
        # Remove old .js config if present (we now generate .ts)
        old_js = workspace / "docusaurus.config.js"
        if old_js.exists():
            old_js.unlink()
        yield "Generated docusaurus.config.ts"

        # ── 2. sidebars.ts (with optional extra sidebars) ──
        extra_sidebars = segment.config.get("extra_sidebars", None)
        sidebars_content = process_sidebars(extra_sidebars)
        (workspace / "sidebars.ts").write_text(sidebars_content, encoding="utf-8")
        # Remove old .js sidebars if present
        old_sb = workspace / "sidebars.js"
        if old_sb.exists():
            old_sb.unlink()
        sb_count = 1 + (len(extra_sidebars) if extra_sidebars else 0)
        yield f"Generated sidebars.ts ({sb_count} sidebar{'s' if sb_count > 1 else ''})"

        # ── 3. tsconfig.json ──
        tsconfig_src = TEMPLATES_DIR / "config" / "tsconfig.json"
        shutil.copy2(str(tsconfig_src), str(workspace / "tsconfig.json"))
        yield "Generated tsconfig.json"

        # ── 4. package.json ──
        extra_packages = segment.config.get("extra_packages", None)
        pkg_content = build_package_json(
            segment.name, features, extra_packages=extra_packages,
        )
        (workspace / "package.json").write_text(pkg_content, encoding="utf-8")
        dep_count = len(json.loads(pkg_content).get("dependencies", {}))
        extra_count = len(extra_packages) if extra_packages else 0
        extra_msg = f" (+{extra_count} custom)" if extra_count else ""
        yield f"Generated package.json ({dep_count} deps{extra_msg})"

        # ── 5. Custom CSS ──
        css_dir = workspace / "src" / "css"
        css_dir.mkdir(parents=True, exist_ok=True)
        user_css = segment.config.get("custom_css", "")
        css_content = build_custom_css(user_css)
        (css_dir / "custom.css").write_text(css_content, encoding="utf-8")
        yield "Generated src/css/custom.css"


        # ── 5b. Google Translate components ──
        if features.get("google_translate"):
            # Copy LanguageSelector React component
            comp_src = TEMPLATES_DIR / "src" / "components" / "LanguageSelector.tsx"
            comp_dir = workspace / "src" / "components"
            comp_dir.mkdir(parents=True, exist_ok=True)
            if comp_src.exists():
                shutil.copy2(str(comp_src), str(comp_dir / "LanguageSelector.tsx"))
                yield "Copied src/components/LanguageSelector.tsx"
        else:
            # Clean up translation files if feature was disabled
            for cleanup_file in [
                workspace / "src" / "components" / "LanguageSelector.tsx",
                workspace / "src" / "google-translate.js",
            ]:
                if cleanup_file.exists():
                    cleanup_file.unlink()

        # ── 6. Theme (Root.tsx + hooks) ──
        # Root.tsx is ALWAYS regenerated from template (features may change).
        theme_dir = workspace / "src" / "theme"
        hooks_dir = theme_dir / "hooks"
        hooks_dir.mkdir(parents=True, exist_ok=True)

        root_tsx = theme_dir / "Root.tsx"
        tmpl_raw = (TEMPLATES_DIR / "theme" / "Root.tsx.tmpl").read_text(encoding="utf-8")
        build_hash = compute_build_hash(config_content, pkg_content, css_content)
        # Process conditionals first (handles __IF_FEATURE__ blocks)
        root_content = process_template(tmpl_raw, features, {"__BUILD_HASH__": build_hash})
        root_tsx.write_text(root_content, encoding="utf-8")
        yield f"Generated src/theme/Root.tsx (build hash {build_hash})"

        # Copy ALL hooks from template (always overwrite to match features)
        hooks_src = TEMPLATES_DIR / "theme" / "hooks"
        for hook_file in hooks_src.iterdir():
            if hook_file.is_file():
                dest = hooks_dir / hook_file.name
                shutil.copy2(str(hook_file), str(dest))
                yield f"Generated src/theme/hooks/{hook_file.name}"

        # ── 7. Plugins directory (for custom remark plugins) ──
        plugins_dir = workspace / "src" / "plugins"
        plugins_dir.mkdir(parents=True, exist_ok=True)

        # Copy plugin files for enabled features
        plugins_src = TEMPLATES_DIR / "src" / "plugins"
        if plugins_src.is_dir():
            for feat_key, enabled in features.items():
                if not enabled:
                    continue
                feat_def = FEATURES.get(feat_key, {})
                plugin_name = feat_def.get("requires_plugin")
                if not plugin_name:
                    continue
                # Look for the plugin file (.js or .mjs)
                for ext in (".js", ".mjs"):
                    src_file = plugins_src / f"{plugin_name}{ext}"
                    if src_file.is_file():
                        dest = plugins_dir / f"{plugin_name}{ext}"
                        shutil.copy2(str(src_file), str(dest))
                        yield f"Copied src/plugins/{plugin_name}{ext}"
                        break

        yield f"Scaffold complete — {len(enabled_names)} features enabled"

        # ── 8. Static assets (images, etc.) ──
        source_static = Path(segment.source) / "static"
        if source_static.is_dir():
            ws_static = workspace / "static"
            ws_static.mkdir(parents=True, exist_ok=True)
            static_count = 0
            for item in source_static.rglob("*"):
                if item.is_file():
                    rel = item.relative_to(source_static)
                    dest = ws_static / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(item), str(dest))
                    static_count += 1
            if static_count:
                yield f"Copied {static_count} static asset{'s' if static_count != 1 else ''} from {source_static.name}/"

    def _detect_repo_url(self, segment: SegmentConfig) -> str:
        """Try to detect the GitHub repo URL from project.yml or git config."""
        # Check segment config first
        repo = segment.config.get("repository", "")
        if repo:
            if not repo.startswith("http"):
                return f"https://{repo}"
            return repo

        # Try project.yml repository field
        try:
            import yaml
            source = Path(segment.source).resolve()
            for parent in [source] + list(source.parents):
                yml = parent / "project.yml"
                if yml.is_file():
                    data = yaml.safe_load(yml.read_text(encoding="utf-8"))
                    repo = data.get("repository", "")
                    if repo:
                        if not repo.startswith("http"):
                            return f"https://{repo}"
                        return repo
                    break
        except Exception:
            pass

        # Try git remote
        try:
            result = subprocess.run(
                ["git", "config", "--get", "remote.origin.url"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                url = result.stdout.strip()
                if url.startswith("git@"):
                    url = url.replace(":", "/").replace("git@", "https://")
                if url.endswith(".git"):
                    url = url[:-4]
                return url
        except Exception:
            pass

        return ""

    def _stage_install(self, segment: SegmentConfig, workspace: Path) -> LogStream:
        """Run npm install, with caching based on package.json hash."""
        pkg_path = workspace / "package.json"
        if not pkg_path.is_file():
            raise RuntimeError("package.json not found — run 'scaffold' stage first")

        # Check if we can skip (cache hit)
        pkg_hash = hashlib.sha256(pkg_path.read_bytes()).hexdigest()[:16]
        hash_file = workspace / ".pkg_hash"
        node_modules = workspace / "node_modules"

        if node_modules.is_dir() and hash_file.is_file():
            cached_hash = hash_file.read_text(encoding="utf-8").strip()
            if cached_hash == pkg_hash:
                yield "Dependencies cached — skipping npm install"
                return

        yield "Installing dependencies..."
        cmd = ["npm", "install", "--no-audit", "--no-fund", "--prefer-offline", "--loglevel", "info"]
        yield f"▶ {' '.join(cmd)}"

        proc = subprocess.Popen(
            cmd,
            cwd=str(workspace),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        # Capture output tail for error reporting
        output_tail: list[str] = []
        if proc.stdout:
            for line in proc.stdout:
                stripped = line.rstrip()
                output_tail.append(stripped)
                if len(output_tail) > 30:
                    output_tail.pop(0)
                yield stripped
        proc.wait()

        if proc.returncode != 0:
            # Include the last lines of npm output in the error so users see WHY
            err_lines = [l for l in output_tail if l.strip()][-10:]
            detail = "\n".join(err_lines) if err_lines else "(no output captured)"
            raise RuntimeError(
                f"npm install failed (exit code {proc.returncode})\n\n"
                f"Last output lines:\n{detail}"
            )

        # Write cache hash
        hash_file.write_text(pkg_hash, encoding="utf-8")
        yield "Dependencies installed"

    # ── Stage 5: Build ───────────────────────────────────────────────

    # ── Build Intelligence helpers ────────────────────────────────────

    def _compute_workspace_hash(self, workspace: Path) -> str:
        """Hash all content + config files in workspace for skip detection.

        Covers: docs/**/*.mdx, src/**/*.{ts,tsx,css}, config files.
        Returns a hex digest that changes when any input changes.
        """
        h = hashlib.sha256()
        extensions = {".mdx", ".md", ".ts", ".tsx", ".css", ".json"}
        targets = []

        for subdir in ["docs", "src"]:
            d = workspace / subdir
            if d.is_dir():
                for f in sorted(d.rglob("*")):
                    if f.is_file() and f.suffix in extensions:
                        targets.append(f)

        # Also include top-level config files
        for cfg in ["docusaurus.config.ts", "sidebars.ts", "package.json", "tsconfig.json"]:
            f = workspace / cfg
            if f.is_file():
                targets.append(f)

        for f in targets:
            h.update(f.read_bytes())

        return h.hexdigest()[:24]

    def _maybe_clear_caches(self, workspace: Path) -> list[str]:
        """Clear Docusaurus caches if config/CSS/theme changed since last build.

        Compares current config files against stored hashes. Clears
        .docusaurus/ when CSS or theme changes, and node_modules/.cache/
        when package.json changes.

        Returns list of log messages.
        """
        logs: list[str] = []
        cache_hash_file = workspace / ".cache_hash"

        # Compute hashes of cache-sensitive files
        sensitive_files = [
            workspace / "docusaurus.config.ts",
            workspace / "src" / "css" / "custom.css",
            workspace / "src" / "theme" / "Root.tsx",
            workspace / "package.json",
        ]
        h = hashlib.sha256()
        for f in sensitive_files:
            if f.is_file():
                h.update(f.read_bytes())
        current_hash = h.hexdigest()[:16]

        if cache_hash_file.is_file():
            old_hash = cache_hash_file.read_text(encoding="utf-8").strip()
            if old_hash != current_hash:
                # Something changed — clear Docusaurus cache
                docusaurus_cache = workspace / ".docusaurus"
                if docusaurus_cache.is_dir():
                    shutil.rmtree(docusaurus_cache)
                    logs.append("Cleared .docusaurus/ cache (config/CSS/theme changed)")

                # Clear node_modules cache too
                nm_cache = workspace / "node_modules" / ".cache"
                if nm_cache.is_dir():
                    shutil.rmtree(nm_cache)
                    logs.append("Cleared node_modules/.cache/")

                if not logs:
                    logs.append("Config/CSS changed — no caches to clear yet")
            else:
                logs.append("Cache hash unchanged — caches preserved")
        else:
            logs.append("First build — no cache to clear")

        cache_hash_file.write_text(current_hash, encoding="utf-8")
        return logs

    def _stage_build(self, segment: SegmentConfig, workspace: Path) -> LogStream:
        """Run npx docusaurus build with smart skip + Rspack recovery.

        Build Intelligence:
        - Content hash skip: skips entire build if workspace unchanged
        - Cache management: clears .docusaurus/ on config/CSS changes
        - Rspack segfault recovery: retries on exit 139 (SIGSEGV)
        - NODE_OPTIONS: configurable memory limit
        - Clean build: wipe caches if segment config has clean=True
        """
        import os as _os

        out_dir = workspace / "build"
        is_clean = segment.config.get("clean", False)
        features = segment.config.get("features", {})
        has_faster = features.get("faster", False)

        # ── Clean build: wipe caches ──
        if is_clean:
            for d in [".docusaurus", "node_modules/.cache"]:
                cache_dir = workspace / d
                if cache_dir.is_dir():
                    shutil.rmtree(cache_dir)
            yield "🧹 Clean build — caches cleared"
            # Remove the flag so it doesn't persist
            segment.config.pop("clean", None)
        else:
            # ── Cache management: detect config/CSS/theme changes ──
            for msg in self._maybe_clear_caches(workspace):
                yield msg

        # ── Content hash skip ──
        content_hash_file = workspace / ".content_hash"
        current_hash = self._compute_workspace_hash(workspace)

        if (
            not is_clean
            and out_dir.is_dir()
            and content_hash_file.is_file()
        ):
            old_hash = content_hash_file.read_text(encoding="utf-8").strip()
            if old_hash == current_hash:
                file_count = sum(1 for _ in out_dir.rglob("*") if _.is_file())
                yield f"⚡ Content unchanged — SKIPPING build ({file_count} files in build/)"
                return
            else:
                yield f"Content hash changed: {old_hash[:8]}… → {current_hash[:8]}…"

        # ── NODE_OPTIONS ──
        node_max_mem = segment.config.get("node_max_memory", 4096)
        node_options = f"--max-old-space-size={node_max_mem}"
        env = {
            **_os.environ,
            "FORCE_COLOR": "0",
            "CI": "true",
            "NODE_OPTIONS": node_options,
        }
        yield f"NODE_OPTIONS: {node_options}"

        # ── Build command ──
        build_mode = segment.config.pop("build_mode", "standard")
        cmd = ["npx", "docusaurus", "build", "--out-dir", str(out_dir)]
        if build_mode == "no-minify":
            cmd.append("--no-minify")
            yield f"Build mode: no-minify (faster, larger output)"
        yield f"▶ {' '.join(cmd)}"

        # ── Run build with real-time streaming ──
        lines, returncode = yield from self._stream_subprocess(cmd, workspace, env)

        # ── Rspack segfault recovery (exit 139 = 128 + SIGSEGV) ──
        if returncode == 139 and has_faster:
            yield "⚠️  Rspack segfault (SIGSEGV) detected — clearing caches and retrying…"
            for d in [".docusaurus", "node_modules/.cache"]:
                cache_dir = workspace / d
                if cache_dir.is_dir():
                    shutil.rmtree(cache_dir)

            lines, returncode = yield from self._stream_subprocess(cmd, workspace, env)

            if returncode == 139:
                yield "⚠️  Second segfault — disabling experimental_faster and retrying…"
                # Rewrite config to disable faster builds
                config_path = workspace / "docusaurus.config.ts"
                if config_path.is_file():
                    config_text = config_path.read_text(encoding="utf-8")
                    config_text = config_text.replace(
                        "experimental_faster: {",
                        "// experimental_faster: { /* disabled due to segfault */",
                    )
                    config_path.write_text(config_text, encoding="utf-8")
                    yield "Disabled experimental_faster in config"

                for d in [".docusaurus", "node_modules/.cache"]:
                    cache_dir = workspace / d
                    if cache_dir.is_dir():
                        shutil.rmtree(cache_dir)

                lines, returncode = yield from self._stream_subprocess(cmd, workspace, env)

        if returncode != 0:
            err_tail = [l for l in lines if l.strip()][-15:]
            detail = "\n".join(err_tail) if err_tail else "(no output captured)"
            raise RuntimeError(
                f"Docusaurus build failed (exit code {returncode})\n\n"
                f"Last output lines:\n{detail}"
            )

        # ── Save content hash for future skip detection ──
        content_hash_file.write_text(current_hash, encoding="utf-8")

        # Count output files
        if out_dir.is_dir():
            file_count = sum(1 for _ in out_dir.rglob("*") if _.is_file())
            yield f"Generated {file_count} files in build/"
        yield "Build complete"

    def _stream_subprocess(
        self,
        cmd: list[str],
        workspace: Path,
        env: dict[str, str],
    ) -> "Generator[str, None, tuple[list[str], int]]":
        """Stream subprocess output line by line (real-time SSE).

        Usage: lines, returncode = yield from self._stream_subprocess(...)

        Each line is yielded immediately to the SSE handler. At the end,
        the generator returns (output_lines, returncode) so the caller
        can inspect the result for retries/error reporting.
        """
        output_lines: list[str] = []
        proc = subprocess.Popen(
            cmd,
            cwd=str(workspace),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
        )
        if proc.stdout:
            for line in proc.stdout:
                stripped = line.rstrip()
                output_lines.append(stripped)
                yield stripped
        proc.wait()
        return output_lines, proc.returncode

    # ── Output dir ──────────────────────────────────────────────────

    def output_dir(self, workspace: Path) -> Path:
        return workspace / "build"

    # ── Preview (live dev server) ───────────────────────────────────

    def preview(
        self, segment: SegmentConfig, workspace: Path,
    ) -> tuple[subprocess.Popen, int]:
        """Start docusaurus dev server for live preview."""
        import random

        # Re-transform before preview
        for _line in self._stage_source(segment, workspace):
            pass
        for _line in self._stage_transform(segment, workspace):
            pass

        port = random.randint(8300, 8399)
        proc = subprocess.Popen(
            ["npx", "docusaurus", "start", "--port", str(port), "--no-open"],
            cwd=str(workspace),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        return proc, port

    # ── Transform helpers (delegated to docusaurus_transforms) ──────

    _convert_admonitions = staticmethod(convert_admonitions)
    _enrich_frontmatter = staticmethod(enrich_frontmatter)
    _rewrite_links = staticmethod(rewrite_links)
    _escape_jsx_angles = staticmethod(escape_jsx_angles)

