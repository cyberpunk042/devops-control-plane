# 10 — Rollback & Undo Spec

> **Document**: 10 of 37
> **Milestone**: M5 — Step lifecycle & state machine
> **Status**: Draft

---

## 1. Purpose

The rollback system guarantees that no fix leaves the codebase in a worse state than before. If a fix breaks something — fails verification, introduces syntax errors, causes import failures — the file is restored to its pre-fix state automatically.

V1 had no rollback. A bad fix stayed in the file. The user had to manually undo changes or use git.

---

## 2. Rollback Levels

### 2.1 Fix-level rollback

Automatic. When a single fix fails verification, the entire file is rolled back to its pre-fix snapshot. This is the most common rollback.

### 2.2 File-level rollback

Automatic. When multiple fixes are applied to one file and ANY fix fails verification, ALL fixes to that file are rolled back. You can't keep fix A and rollback fix B in the same file — they may interact.

### 2.3 Step-level rollback

Semi-automatic. When a step applies fixes to multiple files and some files fail verification:
- Successfully verified files: keep the fixes
- Failed files: roll back those files
- Step state: FAILED (with details about which files succeeded and which rolled back)

The user can then choose to:
- Retry the step (re-runs fixes on the rolled-back files)
- Skip the step
- Manually fix the remaining files

### 2.4 Plan-level rollback

Manual. User-triggered. "Undo all changes made by this version plan." Restores ALL files modified by the plan to their pre-plan state.

Requires: git integration. The plan records the git commit hash at the start. Plan-level rollback is `git checkout <start_hash> -- <modified_files>`.

---

## 3. Snapshot Mechanism

### 3.1 File snapshots

```python
class SnapshotManager:
    """Manage file snapshots for rollback."""

    def __init__(self, project_root: Path):
        self._project_root = project_root
        self._snapshots: dict[str, FileSnapshot] = {}

    def take(self, file_path: Path) -> str:
        """Take a snapshot of a file before modification.

        Returns snapshot ID for later rollback.
        Stores the full file content in memory.
        """

    def rollback(self, snapshot_id: str) -> bool:
        """Restore a file to its snapshot state.

        Writes the original content back to the file.
        Returns True if successful.
        """

    def rollback_file(self, file_path: Path) -> bool:
        """Rollback the most recent snapshot for a file."""

    def discard(self, snapshot_id: str) -> None:
        """Discard a snapshot (fix was verified, no rollback needed).

        Frees the memory used by the snapshot content.
        """

    def discard_all(self) -> None:
        """Discard all snapshots (all fixes verified)."""

    def active_snapshots(self) -> list[str]:
        """List files with active (undiscarded) snapshots."""


@dataclass
class FileSnapshot:
    snapshot_id: str
    file_path: str
    original_content: str       # Full file content at snapshot time
    original_mtime: float       # Modification time at snapshot
    original_hash: str          # Content hash for verification
    taken_at: str               # ISO timestamp
    discarded: bool = False
```

### 3.2 Snapshot lifecycle

```
1. Before fix:
   snapshot_id = snapshot_manager.take(file_path)
   → File content stored in memory

2. Apply fix:
   fix_engine.apply_transform(file_path, ...)
   → File is modified on disk

3. Verify fix:
   verification = verifier.verify_fix(file_path, ...)

4a. Verification passes:
    snapshot_manager.discard(snapshot_id)
    → Snapshot memory freed
    → Fix is permanent

4b. Verification fails:
    snapshot_manager.rollback(snapshot_id)
    → Original content written back to disk
    → File is exactly as it was before the fix
    → Fix is fully undone
```

### 3.3 Snapshot storage

Snapshots are held in memory during a fix session. For large modules with many files, this could use significant memory:

| Files | Avg file size | Memory |
|-------|---------------|--------|
| 10 | 5KB | 50KB |
| 100 | 5KB | 500KB |
| 500 | 10KB | 5MB |
| 1000 | 10KB | 10MB |

10MB is acceptable. For very large modules, snapshots could be written to a temp directory within the project (`.compat-rollback/`), but in-memory is the default.

---

## 4. Git Integration

### 4.1 Plan start marker

When a version plan begins execution, record the current git state:

```python
def mark_plan_start(
    module_name: str,
    project_root: Path,
) -> PlanStartMarker:
    """Record git state at plan start for plan-level rollback.

    Returns:
        PlanStartMarker with commit hash and status
    """
    commit_hash = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True, text=True,
        cwd=str(project_root),
    ).stdout.strip()

    has_uncommitted = bool(subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True, text=True,
        cwd=str(project_root),
    ).stdout.strip())

    return PlanStartMarker(
        module_name=module_name,
        commit_hash=commit_hash,
        had_uncommitted_changes=has_uncommitted,
        started_at=datetime.now(timezone.utc).isoformat(),
    )
```

### 4.2 Tracking modified files

Every file modified by the plan is recorded:

```python
@dataclass
class PlanModificationLog:
    module_name: str
    start_marker: PlanStartMarker
    modified_files: list[FileModification]

@dataclass
class FileModification:
    file_path: str
    step_id: str                # Which step modified it
    modification_type: str      # "fix_applied", "config_updated", "file_created"
    timestamp: str
    snapshot_hash: str          # Hash of original content
```

### 4.3 Plan-level rollback

```python
def rollback_plan(
    module_name: str,
    modification_log: PlanModificationLog,
    project_root: Path,
) -> PlanRollbackResult:
    """Rollback all changes made by a version plan.

    For each modified file:
    1. If file existed before plan → restore via git checkout
    2. If file was created by plan → delete it
    3. Update plan steps → all back to PENDING

    Uses git to restore files to their state at plan start.
    """
    results = []
    for mod in modification_log.modified_files:
        file_path = project_root / mod.file_path
        if mod.modification_type == "file_created":
            # File was created by the plan — delete it
            if file_path.exists():
                file_path.unlink()
                results.append(("deleted", mod.file_path))
        else:
            # File was modified — restore from git
            subprocess.run(
                ["git", "checkout", modification_log.start_marker.commit_hash, "--", mod.file_path],
                cwd=str(project_root),
            )
            results.append(("restored", mod.file_path))

    return PlanRollbackResult(
        module_name=module_name,
        files_restored=len([r for r in results if r[0] == "restored"]),
        files_deleted=len([r for r in results if r[0] == "deleted"]),
        results=results,
    )
```

---

## 5. Rollback Reporting

### 5.1 Fix-level rollback report

```
Fix: python.stdlib.datetime_utc in src/core/models/action.py
Applied: replace_import_and_usages
Verification: FAILED
  ❌ Re-detection: datetime.UTC still found at line 15
  → Transform did not handle "from datetime import UTC as utc_alias"
Rollback: ✅ File restored to original state
```

### 5.2 Step-level rollback report

```
Step: Fix incompatible code (14 files)
Results:
  ✅ src/core/models/action.py — fixed and verified
  ✅ src/core/models/state.py — fixed and verified
  ❌ src/core/engine/executor.py — fix failed, ROLLED BACK
     → StrEnum fix not available (manual only)
  ✅ src/core/observability/health.py — fixed and verified
  ... 10 more verified

Summary: 13/14 files fixed, 1 rolled back
Step state: FAILED (1 file could not be fixed)
```

### 5.3 Plan-level rollback report

```
Plan rollback: core (Python 3.8 downgrade)
Files restored: 13 (to commit abc1234)
Files deleted: 3 (test scaffolds created by plan)
Plan state: all steps reset to PENDING
```

---

## 6. Edge Cases

### 6.1 File modified between snapshot and rollback

If a file is modified externally (by the user, by another process) between snapshot and rollback:

```python
def rollback(self, snapshot_id: str) -> bool:
    snapshot = self._snapshots[snapshot_id]
    current_content = Path(snapshot.file_path).read_text()
    current_hash = hash(current_content)

    if current_hash != hash_of_fixed_content:
        # File was modified AFTER the fix — don't overwrite user changes
        logger.warning(
            "File %s was modified after fix. Rollback may overwrite changes.",
            snapshot.file_path,
        )
        # Still rollback — the fix was wrong, original is safer
        # But record that external changes existed
```

Decision: rollback anyway. The fix was wrong. Better to restore the original and let the user re-apply their changes than to leave a broken fix in place.

### 6.2 File deleted between snapshot and rollback

If the file was deleted (by the user or another process):
- Recreate it from the snapshot content
- Warn the user

### 6.3 Snapshot for a new file

If the fix creates a NEW file (not common — most fixes modify existing files):
- Snapshot is empty (file didn't exist before)
- Rollback = delete the file

### 6.4 Multiple fixes to the same file

When multiple fixes target the same file:
1. ONE snapshot taken (before the first fix)
2. All fixes applied in sequence
3. Verification runs once on the final result
4. If verification fails → rollback to the single snapshot (before ALL fixes)
5. All fixes are undone together

### 6.5 Concurrent modification by another plan

If module A's plan and module B's plan both need to fix the same file (very rare — modules usually have separate file sets):
- The second plan to touch the file sees a conflict
- Conflict resolution: refuse to fix, report "file was recently modified by another plan"
- User must coordinate

---

## 7. Integration Points

### 7.1 With Fix Engine (Document 05)
- Fix engine calls snapshot_manager.take() before modifying files
- Fix engine calls snapshot_manager.rollback() when verification fails
- Fix engine calls snapshot_manager.discard() when verification passes

### 7.2 With Verification (Document 07)
- Verification failure triggers rollback
- Verification report includes rollback status

### 7.3 With Lifecycle (Document 06)
- Rollback events feed into step state
- Rolled-back fixes → step is FAILED
- Plan-level rollback → all steps reset to PENDING

### 7.4 With UI (Document 31)
- UI shows "Undo plan" button (plan-level rollback)
- Fix results show rollback status per file
- Rolled-back files highlighted in the plan modal
