"""
Config file editors — modify pyproject.toml, setup.py, setup.cfg.

Each handler supports preview (show what would change) and execute
(write the file). Pattern reused from the existing module-fix-floor endpoint.
"""

from __future__ import annotations

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
