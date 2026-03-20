# 13 — Version Constraint Resolution

> **Document**: 13 of 37
> **Milestone**: M7 — Direction & constraint resolution
> **Status**: Draft

---

## 1. Purpose

Version constraint resolution answers: **given a module's code and dependencies, what is the minimum (or maximum) language version it can support?**

This is different from detection (which finds specific features). Constraint resolution is the AGGREGATION layer — it takes all findings and computes the actual version boundaries.

---

## 2. Version Floor and Ceiling

### 2.1 Code floor

The minimum language version required by the module's OWN code:

```
Module: core
Features used:
  - datetime.UTC (3.11+)
  - StrEnum (3.11+)
  - f-strings (3.6+)
  - walrus operator (3.8+)
  - from __future__ import annotations (3.7+) → makes PEP 604 safe

Code floor: 3.11 (determined by datetime.UTC and StrEnum)
```

After fixes:
```
Features used (after fixing datetime.UTC and StrEnum):
  - f-strings (3.6+)
  - walrus operator (3.8+)
  - from __future__ import annotations (3.7+)

Code floor: 3.8 (determined by walrus operator)
```

### 2.2 Dependency floor

The minimum language version required by the module's DEPENDENCIES:

```
Module: core
Dependencies:
  - flask>=2.0         → requires Python >=3.7
  - pydantic>=2.0      → requires Python >=3.8
  - cryptography>=41.0 → requires Python >=3.7
  - pyyaml>=6.0        → requires Python >=3.7

Dependency floor: 3.8 (determined by pydantic)
```

### 2.3 Effective floor

The actual minimum version is the MAXIMUM of code floor and dependency floor:

```
Code floor: 3.8 (after fixes)
Dependency floor: 3.8 (pydantic)
Effective floor: 3.8

Target: 3.8 ✅ — achievable
```

If the dependency floor is HIGHER than the target:
```
Code floor: 3.8 (after fixes)
Dependency floor: 3.9 (hypothetical — some package needs 3.9)
Effective floor: 3.9

Target: 3.8 ❌ — NOT achievable without changing dependencies
```

### 2.4 Transitive floor

The effective floor considering transitive project dependencies:

```
Module: web
Web code floor: 3.8
Web dependency floor: 3.8
Web effective floor: 3.8

But web imports core:
Core code floor: 3.11 (unfixed)
Core effective floor: 3.11

Web transitive floor: max(3.8, 3.11) = 3.11

Target: 3.8 ❌ — blocked by core
After fixing core: web transitive floor = max(3.8, 3.8) = 3.8 ✅
```

---

## 3. Computing the Floor

```python
class VersionResolver:
    """Compute version constraints for a module."""

    def __init__(
        self,
        detection_engine: DetectionEngine,
        dep_analyzer: DependencyAnalyzer,
        import_resolver: ImportResolver,
        registry: FeatureRegistry,
    ):
        ...

    def compute_code_floor(
        self,
        module_dir: Path,
        language: str,
    ) -> CodeFloor:
        """Compute the minimum version required by the module's code.

        1. Run detection engine on all files
        2. Find the highest 'introduced' version among all findings
        3. That's the code floor
        """

    def compute_dependency_floor(
        self,
        module_dir: Path,
        language: str,
    ) -> DependencyFloor:
        """Compute the minimum version required by dependencies.

        1. Read dependency manifest (requirements.txt, package.json, etc.)
        2. Query package registries for version constraints
        3. Find the highest minimum version among all dependencies
        """

    def compute_effective_floor(
        self,
        module_dir: Path,
        language: str,
    ) -> EffectiveFloor:
        """Compute the actual minimum version.

        max(code_floor, dependency_floor)
        """

    def compute_transitive_floor(
        self,
        module_dir: Path,
        language: str,
        project_root: Path,
        modules: list[ModuleConfig],
    ) -> TransitiveFloor:
        """Compute the minimum version considering transitive dependencies.

        1. Build import graph
        2. Find all dependency modules
        3. Compute effective floor for each
        4. Return max of all floors
        """

    def is_target_achievable(
        self,
        module_name: str,
        target_version: str,
        language: str,
        project_root: Path,
    ) -> TargetAssessment:
        """Can the target version be achieved?

        Returns:
          - achievable: bool
          - blockers: what prevents it (code features, deps, transitive deps)
          - effort: estimated fixes needed
          - recommendation: suggested actions
        """
```

### 3.1 Data models

```python
@dataclass
class CodeFloor:
    version: str                    # "3.11"
    determining_features: list[FeatureUsage]  # What sets the floor
    total_features_above: int       # How many features are above a hypothetical target
    fixable_count: int              # How many can be auto-fixed
    manual_count: int               # How many need manual fixes

@dataclass
class FeatureUsage:
    feature_id: str                 # "python.stdlib.datetime_utc"
    version: str                    # "3.11"
    occurrence_count: int           # How many times it appears
    files: list[str]                # Which files
    fix_available: bool
    fix_strategy: str

@dataclass
class DependencyFloor:
    version: str                    # "3.8"
    determining_packages: list[PackageConstraint]
    all_compatible: bool            # Are all deps compatible with target?
    incompatible_packages: list[PackageConstraint]

@dataclass
class PackageConstraint:
    package: str                    # "pydantic"
    installed_version: str          # "2.5.0"
    requires_python: str            # ">=3.8"
    min_python: str                 # "3.8"
    compatible_with_target: bool    # True if target >= min_python

@dataclass
class EffectiveFloor:
    version: str                    # max(code, dep)
    code_floor: CodeFloor
    dependency_floor: DependencyFloor
    determined_by: str              # "code" or "dependency"

@dataclass
class TransitiveFloor:
    version: str                    # max(effective, all transitive)
    effective_floor: EffectiveFloor
    transitive_modules: dict[str, EffectiveFloor]  # module → its floor
    blocking_modules: list[str]     # Modules whose floor > target

@dataclass
class TargetAssessment:
    target: str
    achievable: bool
    current_floor: TransitiveFloor
    gap: str | None                 # "3.11 → 3.8" or None if achievable

    # What needs to happen
    code_fixes_needed: int
    code_fixes_auto: int
    code_fixes_manual: int
    dep_changes_needed: int
    transitive_fixes_needed: int
    blocking_modules: list[str]

    recommendation: str             # Human-readable recommendation
```

---

## 4. Version Comparison

### 4.1 Per-language version parsing

Each language has its own version format:

```python
class VersionParser:
    """Parse and compare versions per language."""

    @staticmethod
    def parse(language: str, version_str: str) -> VersionTuple:
        """Parse a version string into a comparable tuple.

        Python: "3.8" → (3, 8)
        JavaScript: "ES2020" → (2020,) or Node "18" → (18,)
        Go: "1.21" → (1, 21)
        Rust: "1.75.0" → (1, 75, 0)
        Java: "17" → (17,)
        Ruby: "3.2" → (3, 2)
        C#: "12" → (12,)
        PHP: "8.2" → (8, 2)
        Elixir: "1.15" → (1, 15)
        """

    @staticmethod
    def compare(language: str, a: str, b: str) -> int:
        """Compare two versions. Returns -1, 0, or 1."""

    @staticmethod
    def is_above(language: str, version: str, target: str) -> bool:
        """Is version strictly above target?"""
```

### 4.2 Edge cases in version comparison

**Python**: `3.8` < `3.9` < `3.10` < `3.11` (numeric, not lexicographic — "3.10" > "3.9")

**JavaScript**: Mixed format — ES year (`ES2020`) and Node version (`18`). These are different version spaces. The system must know which is being used based on the project's context (browser vs Node.js).

**Rust**: Versions AND editions. `1.75.0` is a release version. `edition2021` is a language edition. Both affect feature availability. A feature might require "edition 2021 AND Rust 1.65+".

**Java**: Major versions only (`11`, `17`, `21`). But some features were preview in one version and stable in the next (`records`: preview in 14, stable in 16).

---

## 5. Constraint Conflict Resolution

### 5.1 Code vs target conflict

```
Code uses datetime.UTC (3.11+)
Target: 3.8

Resolution options:
  a. Fix the code (replace datetime.UTC → timezone.utc)
  b. Raise the target to 3.11
  c. Abandon the downgrade
```

The system presents these options. It does NOT auto-resolve. The user decides.

### 5.2 Dependency vs target conflict

```
pydantic 2.x requires Python >=3.8
Target: 3.7

Resolution options:
  a. Downgrade pydantic to 1.x (supports 3.7)
  b. Raise the target to 3.8
  c. Remove pydantic dependency
```

### 5.3 Transitive vs target conflict

```
Module web targets 3.8
Module core's floor is 3.11 (datetime.UTC)

Resolution options:
  a. Fix core first (run core's version plan)
  b. Raise web's target to 3.11
  c. Remove web's dependency on core (unlikely)
```

### 5.4 Multiple conflicts

When there are multiple conflicts, present them ordered by impact:

```
Target: 3.8

Blockers (ordered by fix effort):
  1. datetime.UTC in 14 files (core) — auto-fixable, ~2 minutes
  2. StrEnum in 1 file (core) — manual fix, ~10 minutes
  3. pydantic 2.x needs 3.8 — already compatible ✅
  4. tomllib in 2 files (core) — auto-fixable, ~1 minute

Total effort: 17 auto-fixes + 1 manual fix
Estimated time: ~15 minutes
```

---

## 6. Version Ceiling (Upgrade Direction)

For upgrade, the system computes the version CEILING — the highest version the code can safely target:

```
Module: core
Current code floor: 3.8
Backports in use:
  - tomli (backport of 3.11 tomllib)
  - backports.strenum (backport of 3.11 StrEnum)

If removing backports:
  - Need tomllib → requires 3.11
  - Need StrEnum → requires 3.11
  - removeprefix workaround → simplifiable at 3.9

Upgrade ceiling: 3.13 (latest stable)
Modernization available at each version:
  3.9: removeprefix, removesuffix, dict |
  3.10: match/case, union types X | Y, parenthesized context managers
  3.11: tomllib native, StrEnum native, datetime.UTC, except*
  3.12: type statement, override decorator
  3.13: ...
```

---

## 7. Pre-Plan Assessment

Before creating a version plan, run a full assessment:

```python
def assess_version_change(
    self,
    module_name: str,
    current_version: str | None,
    target_version: str,
    direction: str,
    project_root: Path,
) -> VersionChangeAssessment:
    """Full assessment before creating a version plan.

    Returns:
      - Is it achievable?
      - What needs to change? (code, deps, transitive)
      - Estimated effort
      - Recommended plan steps
      - Blocking modules (if any)
      - Risk assessment
    """
```

This assessment is shown to the user BEFORE they commit to a plan. They can see the scope, effort, and blockers before starting.

```
═══════════════════════════════════════════════════
Version Change Assessment
Module: web (src/ui/web)
Direction: downgrade 3.11 → 3.8
═══════════════════════════════════════════════════

Achievable: YES (after fixing dependencies)

Code changes needed:
  1 file: datetime.UTC → timezone.utc (auto-fix)

Dependency changes: none

Transitive blockers:
  ⚠️ Module 'core' needs fixing first (14 files)
  Recommended: run core's version plan before web's

Estimated effort:
  Core: 14 auto-fixes + 1 manual (~15 min)
  Web: 1 auto-fix (~1 min)
  Total: ~16 minutes

Risk: LOW
  All fixes except StrEnum are mechanical replacements.
  StrEnum requires manual rewrite — review carefully.

Proceed with plan creation? [Y/n]
═══════════════════════════════════════════════════
```

---

## 8. Integration Points

### 8.1 With Detection Engine (Document 03)
- Code floor computation uses detection results
- Feature list feeds into floor calculation

### 8.2 With Dependency Analysis (Document 14)
- Dependency floor from package registry queries
- Incompatible packages listed in assessment

### 8.3 With Import Resolver (Document 04)
- Transitive floor uses import graph
- Module dependency chain determines blocker order

### 8.4 With Project-Wide Analysis (Document 08)
- Project-level floor computation across all modules
- Module fix ordering based on floors

### 8.5 With Lifecycle (Document 06)
- Assessment runs before plan creation
- BLOCKED state uses floor/blocker information
- Target achievability checked before starting steps
