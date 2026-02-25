"""
L1 Domain — DAG utilities (pure).

Functions for step dependency management, cycle detection,
and parallel execution safety.
No I/O, no subprocess.
"""

from __future__ import annotations


def _add_implicit_deps(steps: list[dict]) -> list[dict]:
    """Add implicit linear dependencies for steps missing ``depends_on``.

    If a step has no ``depends_on`` field, it gets an implicit
    dependency on the previous step. This preserves backward
    compatibility with linear plans.

    Also auto-generates ``id`` fields if missing.

    Args:
        steps: Mutable list of step dicts (modified in place).

    Returns:
        The same list, with ``id`` and ``depends_on`` populated.
    """
    for i, step in enumerate(steps):
        if "id" not in step:
            step["id"] = f"step_{i}"
        if "depends_on" not in step:
            step["depends_on"] = [steps[i - 1]["id"]] if i > 0 else []
    return steps


def _validate_dag(steps: list[dict]) -> list[str]:
    """Validate the step dependency DAG.

    Checks for:
    - Duplicate step IDs
    - References to non-existent step IDs
    - Cycles (Kahn's algorithm)

    Args:
        steps: Steps with ``id`` and ``depends_on`` populated.

    Returns:
        List of error strings (empty = valid).
    """
    errors: list[str] = []
    ids = {s["id"] for s in steps}

    # Duplicate IDs
    seen: set[str] = set()
    for s in steps:
        if s["id"] in seen:
            errors.append(f"Duplicate step ID: {s['id']}")
        seen.add(s["id"])

    # Missing refs
    for s in steps:
        for dep in s.get("depends_on", []):
            if dep not in ids:
                errors.append(
                    f"Step '{s['id']}' depends on unknown step '{dep}'"
                )

    if errors:
        return errors

    # Cycle detection (Kahn's algorithm)
    in_degree: dict[str, int] = {s["id"]: 0 for s in steps}
    for s in steps:
        for dep in s.get("depends_on", []):
            in_degree[s["id"]] += 1

    queue = [sid for sid, deg in in_degree.items() if deg == 0]
    processed = 0
    # Build adjacency: dep → list of steps that depend on it
    adj: dict[str, list[str]] = {s["id"]: [] for s in steps}
    for s in steps:
        for dep in s.get("depends_on", []):
            adj[dep].append(s["id"])

    while queue:
        node = queue.pop(0)
        processed += 1
        for successor in adj[node]:
            in_degree[successor] -= 1
            if in_degree[successor] == 0:
                queue.append(successor)

    if processed < len(steps):
        errors.append("Dependency cycle detected in plan steps")

    return errors


def _get_ready_steps(
    steps: list[dict],
    completed: set[str],
    running: set[str],
) -> list[dict]:
    """Find steps whose dependencies are all completed.

    Args:
        steps: All plan steps.
        completed: Set of completed step IDs.
        running: Set of currently running step IDs.

    Returns:
        Steps that are ready to execute.
    """
    ready: list[dict] = []
    done_or_running = completed | running
    for step in steps:
        sid = step["id"]
        if sid in done_or_running:
            continue
        deps = step.get("depends_on", [])
        if all(d in completed for d in deps):
            ready.append(step)
    return ready


def _get_step_pm(step: dict) -> str | None:
    """Extract the package manager from a step's command.

    Used to prevent parallel execution of steps that use the
    same package manager (which holds a lock).

    Returns:
        Package manager name, or None if not a PM step.
    """
    cmd = step.get("command", [])
    if not cmd:
        return None
    binary = cmd[0] if isinstance(cmd, list) else cmd.split()[0]
    if binary in ("apt-get", "apt", "dpkg"):
        return "apt"
    if binary in ("dnf", "yum"):
        return "dnf"
    if binary in ("apk",):
        return "apk"
    if binary in ("pacman",):
        return "pacman"
    if binary in ("zypper",):
        return "zypper"
    if binary in ("snap",):
        return "snap"
    if binary in ("brew",):
        return "brew"
    return None


def _enforce_parallel_safety(steps: list[dict]) -> list[dict]:
    """Filter parallel steps to avoid package manager lock conflicts.

    Same-PM steps are serialized: only the first from each PM group
    is kept. Non-PM steps can all run in parallel.

    Args:
        steps: Candidate steps for parallel execution.

    Returns:
        Subset of steps that are safe to run concurrently.
    """
    pm_seen: set[str] = set()
    safe: list[dict] = []

    for step in steps:
        pm = _get_step_pm(step)
        if pm:
            if pm in pm_seen:
                continue  # Skip — same PM already running
            pm_seen.add(pm)
        safe.append(step)

    return safe
