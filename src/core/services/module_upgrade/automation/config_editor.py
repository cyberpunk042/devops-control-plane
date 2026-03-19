"""
Config file editors — modify version config files for all languages.

Each handler supports preview (show what would change) and execute
(write the file). Pattern reused from the existing module-fix-floor endpoint.

Python: pyproject.toml, setup.py, setup.cfg
Node:   package.json (engines.node)
Go:     go.mod (go directive)
Rust:   Cargo.toml (rust-version)
Ruby:   Gemfile (ruby version) + .ruby-version
Java:   pom.xml / build.gradle (source/target)
C#:     *.csproj (TargetFramework)
PHP:    composer.json (require.php)
Elixir: mix.exs (elixir version)
"""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..context import UpgradeContext

logger = logging.getLogger(__name__)


def handle_edit_pyproject_requires_python(ctx: UpgradeContext, mode: str) -> dict:
    """Edit requires-python in pyproject.toml.

    Preview: shows old → new value and file path.
    Execute: writes the modified file.
    """
    target_path = ctx.project_root / ctx.module_path / "pyproject.toml"
    rel_path = str(target_path.relative_to(ctx.project_root))

    if target_path.is_file():
        content = target_path.read_text(encoding="utf-8")
        old_match = re.search(r'requires-python\s*=\s*"([^"]*)"', content)
        old_value = old_match.group(1) if old_match else None
        new_value = f">={ctx.target_floor}"

        if old_match:
            new_content = re.sub(
                r'requires-python\s*=\s*"[^"]*"',
                f'requires-python = "{new_value}"',
                content,
            )
        else:
            # Add requires-python under [project] section
            new_content = content.rstrip() + f'\nrequires-python = "{new_value}"\n'
        is_new = False
    else:
        # Create minimal pyproject.toml
        old_value = None
        new_value = f">={ctx.target_floor}"
        new_content = (
            f"[project]\n"
            f'name = "{ctx.module_name}"\n'
            f'requires-python = "{new_value}"\n'
        )
        is_new = True

    if mode == "preview":
        return {
            "ok": True,
            "can_apply": True,
            "preview_type": "diff",
            "summary": f"{'Create' if is_new else 'Update'} {rel_path}",
            "file": rel_path,
            "old_value": old_value or "(not set)",
            "new_value": new_value,
            "is_new": is_new,
        }

    # Execute
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(new_content, encoding="utf-8")

    return {
        "ok": True,
        "summary": f"{'Created' if is_new else 'Updated'} {rel_path}",
        "file": rel_path,
        "old_value": old_value or "(not set)",
        "new_value": new_value,
    }


def handle_edit_setup_py_python_requires(ctx: UpgradeContext, mode: str) -> dict:
    """Edit python_requires in setup.py.

    Finds the python_requires argument in the setup() call and replaces
    the version constraint. Handles both keyword-style and string-style values.

    Preview: shows old → new value.
    Execute: writes the modified file.
    """
    target_path = ctx.project_root / ctx.module_path / "setup.py"
    rel_path = str(target_path.relative_to(ctx.project_root))

    if not target_path.is_file():
        return {"ok": False, "error": f"setup.py not found at {rel_path}"}

    content = target_path.read_text(encoding="utf-8")
    new_value = f">={ctx.target_floor}"

    # Match python_requires=">=X.Y" or python_requires='>=X.Y'
    pattern = re.compile(
        r"""(python_requires\s*=\s*)(['"])([^'"]*)\2""",
    )
    match = pattern.search(content)

    if match:
        old_value = match.group(3)
        quote = match.group(2)
        new_content = (
            content[:match.start()]
            + f"{match.group(1)}{quote}{new_value}{quote}"
            + content[match.end():]
        )
    else:
        # No python_requires found — try to add it inside setup() call
        old_value = "(not set)"
        # Find setup( and add python_requires as first keyword arg
        setup_match = re.search(r"setup\s*\(", content)
        if setup_match:
            insert_pos = setup_match.end()
            new_content = (
                content[:insert_pos]
                + f'\n    python_requires=">={ctx.target_floor}",'
                + content[insert_pos:]
            )
        else:
            return {"ok": False, "error": "Could not find setup() call in setup.py"}

    if mode == "preview":
        return {
            "ok": True,
            "can_apply": True,
            "preview_type": "diff",
            "summary": f"Update {rel_path}",
            "file": rel_path,
            "old_value": old_value,
            "new_value": new_value,
        }

    # Execute
    target_path.write_text(new_content, encoding="utf-8")

    return {
        "ok": True,
        "summary": f"Updated {rel_path}",
        "file": rel_path,
        "old_value": old_value,
        "new_value": new_value,
    }


def handle_edit_setup_cfg_python_requires(ctx: UpgradeContext, mode: str) -> dict:
    """Edit python_requires in setup.cfg [options] section.

    Finds or adds the python_requires key under [options].

    Preview: shows old → new value.
    Execute: writes the modified file.
    """
    target_path = ctx.project_root / ctx.module_path / "setup.cfg"
    rel_path = str(target_path.relative_to(ctx.project_root))

    if not target_path.is_file():
        return {"ok": False, "error": f"setup.cfg not found at {rel_path}"}

    content = target_path.read_text(encoding="utf-8")
    new_value = f">={ctx.target_floor}"

    # Match python_requires = >=X.Y under [options]
    pattern = re.compile(
        r"(python_requires\s*=\s*)(.*)",
    )
    match = pattern.search(content)

    if match:
        old_value = match.group(2).strip()
        new_content = (
            content[:match.start()]
            + f"python_requires = {new_value}"
            + content[match.end():]
        )
    else:
        old_value = "(not set)"
        # Find [options] section and add python_requires
        options_match = re.search(r"^\[options\]\s*$", content, re.MULTILINE)
        if options_match:
            insert_pos = options_match.end()
            new_content = (
                content[:insert_pos]
                + f"\npython_requires = {new_value}"
                + content[insert_pos:]
            )
        else:
            # No [options] section — add it
            new_content = content.rstrip() + f"\n\n[options]\npython_requires = {new_value}\n"

    if mode == "preview":
        return {
            "ok": True,
            "can_apply": True,
            "preview_type": "diff",
            "summary": f"Update {rel_path}",
            "file": rel_path,
            "old_value": old_value,
            "new_value": new_value,
        }

    # Execute
    target_path.write_text(new_content, encoding="utf-8")

    return {
        "ok": True,
        "summary": f"Updated {rel_path}",
        "file": rel_path,
        "old_value": old_value,
        "new_value": new_value,
    }


# ══════════════════════════════════════════════════════════════════
# NON-PYTHON LANGUAGE HANDLERS
# ══════════════════════════════════════════════════════════════════


def handle_edit_package_json_engines(ctx: UpgradeContext, mode: str) -> dict:
    """Edit engines.node in package.json."""
    target_path = ctx.project_root / ctx.module_path / "package.json"
    rel_path = str(target_path.relative_to(ctx.project_root))

    if not target_path.is_file():
        return {"ok": False, "error": f"package.json not found at {rel_path}"}

    content = target_path.read_text(encoding="utf-8")
    data = json.loads(content)

    old_value = data.get("engines", {}).get("node", "(not set)")
    new_value = f">={ctx.target_floor}"

    if mode == "preview":
        return {
            "ok": True, "can_apply": True, "preview_type": "diff",
            "summary": f"Update {rel_path}", "file": rel_path,
            "old_value": old_value, "new_value": new_value,
        }

    data.setdefault("engines", {})["node"] = new_value
    target_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
    )
    return {
        "ok": True, "summary": f"Updated {rel_path}", "file": rel_path,
        "old_value": old_value, "new_value": new_value,
    }


def handle_edit_go_mod_directive(ctx: UpgradeContext, mode: str) -> dict:
    """Edit the go directive in go.mod."""
    target_path = ctx.project_root / ctx.module_path / "go.mod"
    rel_path = str(target_path.relative_to(ctx.project_root))

    if not target_path.is_file():
        return {"ok": False, "error": f"go.mod not found at {rel_path}"}

    content = target_path.read_text(encoding="utf-8")
    match = re.search(r"^go\s+(\S+)", content, re.MULTILINE)

    old_value = match.group(1) if match else "(not set)"
    new_value = ctx.target_floor

    if match:
        new_content = content[:match.start()] + f"go {new_value}" + content[match.end():]
    else:
        new_content = content.rstrip() + f"\ngo {new_value}\n"

    if mode == "preview":
        return {
            "ok": True, "can_apply": True, "preview_type": "diff",
            "summary": f"Update {rel_path}", "file": rel_path,
            "old_value": f"go {old_value}", "new_value": f"go {new_value}",
        }

    target_path.write_text(new_content, encoding="utf-8")
    return {
        "ok": True, "summary": f"Updated {rel_path}", "file": rel_path,
        "old_value": old_value, "new_value": new_value,
    }


def handle_edit_cargo_toml_rust_version(ctx: UpgradeContext, mode: str) -> dict:
    """Edit rust-version in Cargo.toml."""
    target_path = ctx.project_root / ctx.module_path / "Cargo.toml"
    rel_path = str(target_path.relative_to(ctx.project_root))

    if not target_path.is_file():
        return {"ok": False, "error": f"Cargo.toml not found at {rel_path}"}

    content = target_path.read_text(encoding="utf-8")
    match = re.search(r'rust-version\s*=\s*"([^"]*)"', content)

    old_value = match.group(1) if match else "(not set)"
    new_value = ctx.target_floor

    if match:
        new_content = re.sub(r'rust-version\s*=\s*"[^"]*"', f'rust-version = "{new_value}"', content)
    else:
        pkg_match = re.search(r"^\[package\]\s*$", content, re.MULTILINE)
        if pkg_match:
            new_content = content[:pkg_match.end()] + f'\nrust-version = "{new_value}"' + content[pkg_match.end():]
        else:
            new_content = content.rstrip() + f'\nrust-version = "{new_value}"\n'

    if mode == "preview":
        return {
            "ok": True, "can_apply": True, "preview_type": "diff",
            "summary": f"Update {rel_path}", "file": rel_path,
            "old_value": old_value, "new_value": new_value,
        }

    target_path.write_text(new_content, encoding="utf-8")
    return {
        "ok": True, "summary": f"Updated {rel_path}", "file": rel_path,
        "old_value": old_value, "new_value": new_value,
    }


def handle_edit_gemfile_ruby_version(ctx: UpgradeContext, mode: str) -> dict:
    """Edit ruby version in Gemfile and .ruby-version."""
    module_dir = ctx.project_root / ctx.module_path
    gemfile_path = module_dir / "Gemfile"
    rv_path = module_dir / ".ruby-version"
    new_value = ctx.target_floor
    old_value = "(not set)"
    files_changed = []

    gemfile_new = None
    if gemfile_path.is_file():
        gc = gemfile_path.read_text(encoding="utf-8")
        m = re.search(r"""ruby\s+['"]([^'"]+)['"]""", gc)
        if m:
            old_value = m.group(1)
        gemfile_new = re.sub(r"""ruby\s+['"][^'"]+['"]""", f'ruby "{new_value}"', gc) if m else gc.rstrip() + f'\nruby "{new_value}"\n'
        files_changed.append(str(gemfile_path.relative_to(ctx.project_root)))

    if rv_path.is_file():
        rv_old = rv_path.read_text(encoding="utf-8").strip()
        if old_value == "(not set)":
            old_value = rv_old
        files_changed.append(str(rv_path.relative_to(ctx.project_root)))

    if not files_changed:
        return {"ok": False, "error": "No Gemfile or .ruby-version found"}

    if mode == "preview":
        return {
            "ok": True, "can_apply": True, "preview_type": "diff",
            "summary": f"Update {', '.join(files_changed)}", "file": ", ".join(files_changed),
            "old_value": old_value, "new_value": new_value,
        }

    if gemfile_new:
        gemfile_path.write_text(gemfile_new, encoding="utf-8")
    rv_path.write_text(new_value + "\n", encoding="utf-8")
    return {
        "ok": True, "summary": f"Updated {', '.join(files_changed)}", "file": ", ".join(files_changed),
        "old_value": old_value, "new_value": new_value,
    }


def handle_edit_pom_java_version(ctx: UpgradeContext, mode: str) -> dict:
    """Edit Java version in pom.xml or build.gradle."""
    module_dir = ctx.project_root / ctx.module_path
    pom = module_dir / "pom.xml"
    gradle = module_dir / "build.gradle"
    nv = ctx.target_floor

    if pom.is_file():
        return _edit_xml_version(pom, ctx.project_root, nv, mode,
            [r"(<maven\.compiler\.source>)([^<]*)(</)", r"(<maven\.compiler\.target>)([^<]*)(</)", r"(<java\.version>)([^<]*)(</java\.version>)"],
            "maven.compiler.source/target")
    elif gradle.is_file():
        return _edit_gradle_version(gradle, ctx.project_root, nv, mode)
    return {"ok": False, "error": "No pom.xml or build.gradle found"}


def _edit_xml_version(path, project_root, new_value, mode, patterns, desc):
    rel = str(path.relative_to(project_root))
    content = path.read_text(encoding="utf-8")
    olds, nc = [], content
    for p in patterns:
        m = re.search(p, nc)
        if m:
            olds.append(m.group(2))
            nc = re.sub(p, rf"\g<1>{new_value}\g<3>", nc)
    if not olds:
        return {"ok": True, "can_apply": False, "preview_type": "info",
                "summary": f"No {desc} found", "detail": f"Add the version property manually."}
    if mode == "preview":
        return {"ok": True, "can_apply": True, "preview_type": "diff",
                "summary": f"Update {rel}", "file": rel, "old_value": olds[0], "new_value": new_value}
    path.write_text(nc, encoding="utf-8")
    return {"ok": True, "summary": f"Updated {rel}", "file": rel, "old_value": olds[0], "new_value": new_value}


def _edit_gradle_version(path, project_root, new_value, mode):
    rel = str(path.relative_to(project_root))
    content = path.read_text(encoding="utf-8")
    olds, nc = [], content
    for p in [r"(sourceCompatibility\s*=\s*['\"]?)(\d+(?:\.\d+)?)", r"(targetCompatibility\s*=\s*['\"]?)(\d+(?:\.\d+)?)"]:
        m = re.search(p, nc)
        if m:
            olds.append(m.group(2))
            nc = re.sub(p, rf"\g<1>{new_value}", nc)
    if not olds:
        return {"ok": True, "can_apply": False, "preview_type": "info",
                "summary": "No sourceCompatibility found", "detail": f"Add sourceCompatibility = '{new_value}' to build.gradle."}
    if mode == "preview":
        return {"ok": True, "can_apply": True, "preview_type": "diff",
                "summary": f"Update {rel}", "file": rel, "old_value": olds[0], "new_value": new_value}
    path.write_text(nc, encoding="utf-8")
    return {"ok": True, "summary": f"Updated {rel}", "file": rel, "old_value": olds[0], "new_value": new_value}


def handle_edit_csproj_target(ctx: UpgradeContext, mode: str) -> dict:
    """Edit TargetFramework in *.csproj."""
    csproj_files = list((ctx.project_root / ctx.module_path).glob("*.csproj"))
    if not csproj_files:
        return {"ok": False, "error": "No .csproj file found"}

    path = csproj_files[0]
    rel = str(path.relative_to(ctx.project_root))
    content = path.read_text(encoding="utf-8")
    m = re.search(r"(<TargetFramework>)([^<]*)(</TargetFramework>)", content)
    new_tfm = f"net{ctx.target_floor}"
    old = m.group(2) if m else "(not set)"

    if not m:
        return {"ok": True, "can_apply": False, "preview_type": "info",
                "summary": "No TargetFramework found", "detail": f"Add <TargetFramework>{new_tfm}</TargetFramework> to .csproj."}

    nc = re.sub(r"(<TargetFramework>)[^<]*(</TargetFramework>)", rf"\g<1>{new_tfm}\g<2>", content)
    if mode == "preview":
        return {"ok": True, "can_apply": True, "preview_type": "diff",
                "summary": f"Update {rel}", "file": rel, "old_value": old, "new_value": new_tfm}
    path.write_text(nc, encoding="utf-8")
    return {"ok": True, "summary": f"Updated {rel}", "file": rel, "old_value": old, "new_value": new_tfm}


def handle_edit_composer_php_version(ctx: UpgradeContext, mode: str) -> dict:
    """Edit require.php in composer.json."""
    path = ctx.project_root / ctx.module_path / "composer.json"
    rel = str(path.relative_to(ctx.project_root))
    if not path.is_file():
        return {"ok": False, "error": f"composer.json not found at {rel}"}

    data = json.loads(path.read_text(encoding="utf-8"))
    old = data.get("require", {}).get("php", "(not set)")
    nv = f">={ctx.target_floor}"

    if mode == "preview":
        return {"ok": True, "can_apply": True, "preview_type": "diff",
                "summary": f"Update {rel}", "file": rel, "old_value": old, "new_value": nv}

    data.setdefault("require", {})["php"] = nv
    path.write_text(json.dumps(data, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"ok": True, "summary": f"Updated {rel}", "file": rel, "old_value": old, "new_value": nv}


def handle_edit_mix_elixir_version(ctx: UpgradeContext, mode: str) -> dict:
    """Edit elixir version in mix.exs."""
    path = ctx.project_root / ctx.module_path / "mix.exs"
    rel = str(path.relative_to(ctx.project_root))
    if not path.is_file():
        return {"ok": False, "error": f"mix.exs not found at {rel}"}

    content = path.read_text(encoding="utf-8")
    m = re.search(r"""(elixir:\s*")(~>\s*[\d.]+|>=\s*[\d.]+)(")""", content)
    old = m.group(2) if m else "(not set)"
    nv = f"~> {ctx.target_floor}"

    if not m:
        return {"ok": True, "can_apply": False, "preview_type": "info",
                "summary": "No elixir version found in mix.exs",
                "detail": f'Add elixir: "~> {ctx.target_floor}" to your mix.exs project/0.'}

    nc = re.sub(r"""(elixir:\s*")(~>\s*[\d.]+|>=\s*[\d.]+)(")""", rf"\g<1>{nv}\g<3>", content)
    if mode == "preview":
        return {"ok": True, "can_apply": True, "preview_type": "diff",
                "summary": f"Update {rel}", "file": rel, "old_value": old, "new_value": nv}
    path.write_text(nc, encoding="utf-8")
    return {"ok": True, "summary": f"Updated {rel}", "file": rel, "old_value": old, "new_value": nv}


# ══════════════════════════════════════════════════════════════════
# PYPROJECT.TOML GENERATION
# ══════════════════════════════════════════════════════════════════


def handle_generate_module_toml(ctx: UpgradeContext, mode: str) -> dict:
    """Generate or update pyproject.toml for the module.

    Preview: shows what would be generated.
    Execute: writes the file.
    """
    module_dir = ctx.project_root / ctx.module_path
    toml_path = module_dir / "pyproject.toml"
    rel_path = str(toml_path.relative_to(ctx.project_root))
    is_new = not toml_path.is_file()

    # Read existing deps from requirements.txt
    deps = []
    req_file = module_dir / "requirements.txt"
    if req_file.is_file():
        for line in req_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("-"):
                deps.append(line)

    # Build content
    requires_python = f">={ctx.target_floor}" if ctx.target_floor else ""
    name = ctx.module_name
    lines = ["[project]", f'name = "{name}"', 'version = "0.1.0"']
    if requires_python:
        lines.append(f'requires-python = "{requires_python}"')
    if deps:
        lines.append("dependencies = [")
        for d in deps:
            lines.append(f'    "{d}",')
        lines.append("]")
    lines.append("")
    content = "\n".join(lines)

    if mode == "preview":
        return {
            "ok": True,
            "can_apply": True,
            "preview_type": "diff",
            "summary": f"{'Create' if is_new else 'Update'} {rel_path}",
            "file": rel_path,
            "old_value": "(new file)" if is_new else "(existing)",
            "new_value": f"pyproject.toml with requires-python {requires_python}",
        }

    module_dir.mkdir(parents=True, exist_ok=True)
    toml_path.write_text(content, encoding="utf-8")
    return {
        "ok": True,
        "summary": f"{'Created' if is_new else 'Updated'} {rel_path}",
        "file": rel_path,
    }
