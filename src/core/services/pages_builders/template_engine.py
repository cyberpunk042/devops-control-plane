"""
Template engine for Docusaurus page builder.

Processes template files with two mechanisms:
  1. Conditional blocks:  // __IF_FEATURE_xxx__ / // __IF_NOT_FEATURE_xxx__ / // __ENDIF__
  2. Placeholder substitution:  __PLACEHOLDER_NAME__

The template files live in templates/docusaurus/ and are real TypeScript/CSS/JSON
files that editors can syntax-highlight and validate. The conditional comment
syntax is invisible to TypeScript — it's just comments that the engine strips
or keeps based on feature flags.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


# ── Template directory ──────────────────────────────────────────────

TEMPLATES_DIR = Path(__file__).parent / "templates" / "docusaurus"


# ── Feature Registry ───────────────────────────────────────────────
#
# Every configurable feature is declared here. The UI reads this to
# render the configuration wizard; the scaffold reads it to process
# templates and inject dependencies.

FEATURES: dict[str, dict[str, Any]] = {
    # ── Content Features ────────────────────────────────────────
    "mermaid": {
        "label": "🧜 Mermaid Diagrams",
        "description": "Render flowcharts, sequence diagrams, and more",
        "category": "content",
        "default": True,
        "deps": {"@docusaurus/theme-mermaid": "3.9.2"},
    },
    "gfm": {
        "label": "📊 GFM Support",
        "description": "GitHub Flavored Markdown — tables, strikethrough, autolinks",
        "category": "content",
        "default": True,
        "deps": {"remark-gfm": "^4.0.0"},
    },
    "math": {
        "label": "🔢 Math / KaTeX",
        "description": "LaTeX math equations with KaTeX rendering",
        "category": "content",
        "default": True,
        "deps": {
            "remark-math": "^6.0.0",
            "rehype-katex": "^7.0.0",
            "katex": "^0.16.0",
        },
    },
    "prism_extra": {
        "label": "📝 Extended Languages",
        "description": "Syntax highlighting for Java, Rust, Go, PHP, Ruby, SQL, and more",
        "category": "content",
        "default": True,
        "deps": {},
    },

    # ── Site Features ───────────────────────────────────────────
    "search": {
        "label": "🔍 Local Search",
        "description": "Full-text search — no external service needed",
        "category": "features",
        "default": False,
        "deps": {"@easyops-cn/docusaurus-search-local": "0.52.2"},
    },
    "pwa": {
        "label": "📱 PWA Support",
        "description": "Installable progressive web app with offline support",
        "category": "features",
        "default": False,
        "deps": {"@docusaurus/plugin-pwa": "3.9.2"},
    },
    "dark_mode": {
        "label": "🌙 Dark Mode Default",
        "description": "Start in dark mode (users can still toggle)",
        "category": "appearance",
        "default": True,
        "deps": {},
    },
    "github": {
        "label": "🔗 GitHub Link",
        "description": "Show repository link in navbar (auto-detected from git)",
        "category": "identity",
        "default": True,
        "deps": {},
    },
    "prism_theme": {
        "label": "🎨 Prism Theme",
        "description": "Code syntax highlighting theme (select light/dark pair)",
        "category": "appearance",
        "default": False,
        "deps": {},
        "options": {
            "github/dracula": "GitHub Light / Dracula Dark (default)",
            "vsLight/vsDark": "VS Code Light / VS Code Dark",
            "oneLight/oneDark": "One Light / One Dark Pro",
            "github/nightOwl": "GitHub Light / Night Owl Dark",
            "github/oceanicNext": "GitHub Light / Oceanic Next Dark",
        },
    },
    "google_translate": {
        "label": "🌐 Google Translate",
        "description": "Auto-translate button in navbar — supports 100+ languages",
        "category": "features",
        "default": True,
        "deps": {},
    },

    # ── Build Features ──────────────────────────────────────────
    "faster": {
        "label": "⚡ Faster Builds",
        "description": "Rust-based bundler (Rspack) — 2-5x faster builds",
        "category": "build",
        "default": True,
        "deps_dev": {"@docusaurus/faster": "3.9.2"},
    },

    # ── Advanced: Remark Plugins ────────────────────────────────
    "remark_tabs": {
        "label": "📑 Tabs Directive",
        "description": "Custom :::tabs / ::tab remark directive for tabbed content",
        "category": "advanced",
        "default": False,
        "deps": {},
        "requires_plugin": "remark-tabs",
    },
    "remark_system_viewer": {
        "label": "🔭 System Viewer",
        "description": "Embed system-viewer components in markdown",
        "category": "advanced",
        "default": False,
        "deps": {},
        "requires_plugin": "remark-system-viewer",
    },
    "remark_audit_data": {
        "label": "📊 Audit Data Directive",
        "description": "Embed scoped audit data in documentation via :::audit-data",
        "category": "advanced",
        "default": True,
        "deps": {},
        "requires_plugin": "remark-audit-data",
    },
    "peek": {
        "label": "🔗 Peek Links",
        "description": "Auto-link file references in docs to source locations",
        "category": "features",
        "default": False,
        "deps": {},
    },
}

# Ordered categories for UI rendering
FEATURE_CATEGORIES = [
    ("content", "Content Features"),
    ("features", "Site Features"),
    ("appearance", "Appearance"),
    ("identity", "Identity"),
    ("build", "Build Options"),
    ("advanced", "Advanced Plugins"),
]


# ── Template Processing ────────────────────────────────────────────


def process_template(
    content: str,
    features: dict[str, bool],
    placeholders: dict[str, str],
) -> str:
    """Process a template file with conditional blocks and placeholders.

    Conditional blocks use comment syntax that doesn't break the host language:

        // __IF_FEATURE_xxx__
        ... included only if feature 'xxx' is enabled ...
        // __ENDIF__

        // __IF_NOT_FEATURE_xxx__
        ... included only if feature 'xxx' is DISABLED ...
        // __ENDIF__

    Blocks can be nested. Processing is done iteratively from innermost out.

    Placeholders are simple string replacement:
        __SITE_TITLE__  →  replaced with value from placeholders dict
    """
    # Process conditional blocks (innermost first via iteration)
    # We loop until no more blocks are found, which handles nesting.
    changed = True
    while changed:
        changed = False

        # __IF_FEATURE_xxx__   (include if enabled)
        def _replace_if(m: re.Match) -> str:
            nonlocal changed
            changed = True
            feat_key = m.group(1)
            body = m.group(2)
            if features.get(feat_key, False):
                return body
            return ""

        content = re.sub(
            r"//\s*__IF_FEATURE_(\w+)__\s*\n(.*?)//\s*__ENDIF__\s*\n",
            _replace_if,
            content,
            flags=re.DOTALL,
        )

        # __IF_NOT_FEATURE_xxx__   (include if disabled)
        def _replace_if_not(m: re.Match) -> str:
            nonlocal changed
            changed = True
            feat_key = m.group(1)
            body = m.group(2)
            if not features.get(feat_key, False):
                return body
            return ""

        content = re.sub(
            r"//\s*__IF_NOT_FEATURE_(\w+)__\s*\n(.*?)//\s*__ENDIF__\s*\n",
            _replace_if_not,
            content,
            flags=re.DOTALL,
        )

    # Substitute placeholders
    for key, value in placeholders.items():
        content = content.replace(key, value)

    # Clean up empty lines left by removed blocks (max 2 consecutive)
    content = re.sub(r"\n{3,}", "\n\n", content)

    return content


def process_docusaurus_config(
    features: dict[str, bool],
    placeholders: dict[str, str],
    *,
    navbar_items: list[dict[str, str]] | None = None,
    extra_rehype: list[str] | None = None,
) -> str:
    """Process the docusaurus.config.ts template with full slot + conditional handling.

    This extends process_template by also resolving __SLOT__ markers for
    remark/rehype plugin arrays, which can't be cleanly expressed as nested
    conditionals. The slots are filled programmatically based on features.

    Args:
        navbar_items: Additional navbar items (list of dicts with label, href/to, position).
        extra_rehype: Additional rehype plugin require() strings.
    """
    tmpl_path = TEMPLATES_DIR / "config" / "docusaurus.config.ts.tmpl"
    content = tmpl_path.read_text(encoding="utf-8")

    # ── Build remark plugins array ──
    remark_items: list[str] = []
    if features.get("gfm"):
        remark_items.append("            [require('remark-gfm'), {}],")
    if features.get("math"):
        remark_items.append("            [require('remark-math'), {}],")
    if features.get("remark_audit_data"):
        remark_items.append("            require('./src/plugins/remark-audit-data'),")

    if remark_items:
        remark_block = "          remarkPlugins: [\n" + "\n".join(remark_items) + "\n          ],"
    else:
        remark_block = ""

    # ── Build rehype plugins array ──
    rehype_items: list[str] = []
    if features.get("math"):
        rehype_items.append("            [require('rehype-katex'), { strict: false }],")
    if extra_rehype:
        for plugin_str in extra_rehype:
            rehype_items.append(f"            {plugin_str},")

    if rehype_items:
        rehype_block = "          rehypePlugins: [\n" + "\n".join(rehype_items) + "\n          ],"
    else:
        rehype_block = ""

    # ── Build beforeDefaultRemarkPlugins array ──
    before_items: list[str] = []
    if features.get("remark_tabs"):
        before_items.append("            require('./src/plugins/remark-tabs'),")
    if features.get("remark_system_viewer"):
        before_items.append("            require('./src/plugins/remark-system-viewer'),")

    if before_items:
        before_block = "          beforeDefaultRemarkPlugins: [\n" + "\n".join(before_items) + "\n          ],"
    else:
        before_block = ""

    # ── Build navbar items ──
    navbar_block = ""
    if navbar_items:
        items: list[str] = []
        for item in navbar_items:
            label = item.get("label", "Link")
            position = item.get("position", "right")
            if item.get("type") == "html":
                value = item.get("value", "")
                items.append(
                    f"        {{\n"
                    f"          type: 'html',\n"
                    f"          position: '{position}',\n"
                    f"          value: `{value}`,\n"
                    f"        }},"
                )
            elif "href" in item:
                items.append(
                    f"        {{\n"
                    f"          href: '{item['href']}',\n"
                    f"          label: '{label}',\n"
                    f"          position: '{position}',\n"
                    f"        }},"
                )
            elif "to" in item:
                items.append(
                    f"        {{\n"
                    f"          to: '{item['to']}',\n"
                    f"          label: '{label}',\n"
                    f"          position: '{position}',\n"
                    f"        }},"
                )
        if items:
            navbar_block = "\n".join(items)

    # ── Replace slots ──
    content = re.sub(r"\s*//\s*__SLOT_REMARK_PLUGINS__\s*", "\n" + remark_block + "\n" if remark_block else "\n", content)
    content = re.sub(r"\s*//\s*__SLOT_REHYPE_PLUGINS__\s*", "\n" + rehype_block + "\n" if rehype_block else "\n", content)
    content = re.sub(r"\s*//\s*__SLOT_BEFORE_REMARK_PLUGINS__\s*", "\n" + before_block + "\n" if before_block else "\n", content)
    content = re.sub(r"\s*//\s*__SLOT_NAVBAR_ITEMS__\s*", "\n" + navbar_block + "\n" if navbar_block else "\n", content)

    # ── Process standard conditionals and placeholders ──
    content = process_template(content, features, placeholders)

    return content


def process_sidebars(
    extra_sidebars: dict[str, str] | None = None,
) -> str:
    """Process the sidebars.ts template with optional extra sidebars.

    Args:
        extra_sidebars: Dict of {sidebarId: dirName} for additional sidebars.
            e.g. {"api": "api", "guides": "guides"}
    """
    tmpl_path = TEMPLATES_DIR / "config" / "sidebars.ts.tmpl"
    content = tmpl_path.read_text(encoding="utf-8")

    sidebar_block = ""
    if extra_sidebars:
        items: list[str] = []
        for sid, dirname in extra_sidebars.items():
            items.append(
                f"  {sid}: [{{type: 'autogenerated', dirName: '{dirname}'}}],"
            )
        sidebar_block = "\n".join(items)

    content = re.sub(
        r"\s*//\s*__SLOT_EXTRA_SIDEBARS__\s*",
        "\n" + sidebar_block + "\n" if sidebar_block else "\n",
        content,
    )

    return content


def build_package_json(
    segment_name: str,
    features: dict[str, bool],
    *,
    extra_packages: dict[str, str] | None = None,
) -> str:
    """Build package.json content from the template + feature deps.

    JSON can't have conditional blocks, so we load the base template
    and inject feature-specific dependencies programmatically.

    Args:
        extra_packages: Additional npm packages to include (name: version).
    """
    tmpl_path = TEMPLATES_DIR / "config" / "package.json.tmpl"
    pkg = json.loads(tmpl_path.read_text(encoding="utf-8"))

    pkg["name"] = f"pages-{segment_name}"

    deps = pkg.setdefault("dependencies", {})
    dev_deps = pkg.setdefault("devDependencies", {})

    for feat_key, enabled in features.items():
        if not enabled:
            continue
        feat_def = FEATURES.get(feat_key, {})
        for dep_name, dep_ver in feat_def.get("deps", {}).items():
            deps[dep_name] = dep_ver
        for dep_name, dep_ver in feat_def.get("deps_dev", {}).items():
            dev_deps[dep_name] = dep_ver

    # Add user-specified extra packages
    if extra_packages:
        for dep_name, dep_ver in extra_packages.items():
            deps[dep_name] = dep_ver

    # Sort deps for deterministic output
    pkg["dependencies"] = dict(sorted(deps.items()))
    if dev_deps:
        pkg["devDependencies"] = dict(sorted(dev_deps.items()))
    else:
        pkg.pop("devDependencies", None)

    return json.dumps(pkg, indent=2) + "\n"


def build_custom_css(user_css: str = "") -> str:
    """Build custom.css from the template + user custom CSS.

    The template has a __USER_CSS_MARKER__ that we append user CSS after.
    """
    tmpl_path = TEMPLATES_DIR / "css" / "custom.css.tmpl"
    base = tmpl_path.read_text(encoding="utf-8")

    if user_css.strip():
        base += f"\n{user_css.strip()}\n"

    return base


def compute_build_hash(*contents: str) -> str:
    """Compute a short hash from one or more content strings.

    Used for cache invalidation — injected into Root.tsx as __BUILD_HASH__.
    """
    h = hashlib.sha256()
    for c in contents:
        h.update(c.encode("utf-8"))
    return h.hexdigest()[:12]


def resolve_features(user_features: dict[str, bool] | None = None) -> dict[str, bool]:
    """Merge user feature selections with defaults.

    Returns a complete dict of all features with their resolved state.
    """
    result: dict[str, bool] = {}
    for key, feat_def in FEATURES.items():
        if user_features and key in user_features:
            result[key] = user_features[key]
        else:
            result[key] = feat_def["default"]
    return result
