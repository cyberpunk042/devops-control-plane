# Compat V2 — Detection Quality Investigation

> The scan produces 4974 findings for module "core". Of those, 2493 are info/no_fix_needed
> (correctly filtered). Of the remaining 2481 "actionable" findings, the vast majority
> are FALSE POSITIVES from broad detection rules.

---

## The Numbers

```
Total findings:     4974
Info/no_fix_needed: 2493 (correctly filtered by M11)
Actionable:         2481

Of those 2481 "actionable":
  False positives:  ~2300 (from broad detection rules)
  Real findings:    ~180  (actually need fixing)
```

---

## Root Cause: Detection Rules Can't Express What They Need

### Problem 1: func_attr matches ANY object (35 entries)

Detection rule `{func_attr: 'compile'}` matches ANY `.compile()` call — not just
`re.compile()`. Same for `.walk()`, `.match()`, `.glob()`, `.relative_to()`, etc.

**Worst offenders:**
- `re.compile()` → 3 entries × 476 files = **1,428 false positives**
- `.relative_to()` → 188 false positives (matches Path AND any other object)
- `.match()` → 146 false positives (matches re.match, str.match, etc.)
- `.glob()` → 65 false positives (matches Path.glob which existed since 3.4)
- `.walk()` → 62 false positives (matches os.walk which existed since forever)

**What's missing in the engine:** `func_attr` checks `node.func.attr` but doesn't
check what `node.func.value` resolves to. The engine needs a `value_id` check on
Call nodes — "method name is X AND the object is Y".

### Problem 2: BinOp matches ALL operators (6 entries)

`{op_type: 'BitOr'}` matches ALL `|` operators. `dict | dict` is Python 3.9,
but `int | int` is bitwise OR (every version), `set | set` is set union (every version).

**53+ false positives per entry.** The engine can't distinguish dict merge from
bitwise OR — it would need type inference which AST alone can't provide.

### Problem 3: func_id matches without checking kwargs (8 entries)

`{func_id: 'dataclass'}` matches every `@dataclass` decorator. The FEATURES are
specific keyword arguments: `slots=True` (3.10), `kw_only=True` (3.10),
`match_args=True` (3.10), `frozen + slots` (3.10).

**217+ false positives.** The engine has NO support for checking keyword arguments.

### Problem 4: func_id matches without checking object (4 entries)

`{func_id: 'field'}` matches every `field()` call — `dataclasses.field()`,
`pydantic.Field()`, `attrs.field()`. The feature is `dataclasses.field(kw_only=True)`.

---

## What the Engine Currently Supports (python_backend.py matchers)

```
names_contains    — Import/ImportFrom: name in import list (GOOD)
value_type        — Attribute: check value node type
value_id          — Attribute: check value is Name with specific id (GOOD)
value_id_in       — Attribute/Subscript: value Name.id in list (GOOD)
op_type           — BinOp: check operator type (TOO BROAD for |)
func_attr         — Call: check method name (TOO BROAD without object check)
func_id           — Call: check function name (TOO BROAD without kwargs check)
has_posonlyargs   — FunctionDef: positional-only params (GOOD)
id                — Name: check identifier (GOOD)
has_guard         — match_case: check guard (GOOD)
has_type_params   — FunctionDef/ClassDef: PEP 695 (GOOD)
has_complex_decorator — FunctionDef: complex decorator syntax (GOOD)
```

## What the Engine NEEDS

### N1: `has_keyword` — Check if a Call has a specific keyword argument

```python
# Detection rule:
{func_id: 'dataclass', has_keyword: 'slots'}

# Matches:
@dataclass(slots=True)    ✓
@dataclass(kw_only=True)  ✗ (different keyword)
@dataclass                ✗ (no keywords)
```

Implementation: check `node.keywords` for a keyword with `.arg == expected`.

### N2: `func_value_id` — Check the object a method is called on

```python
# Detection rule:
{func_attr: 'compile', func_value_id: 're'}

# Matches:
re.compile(pattern)       ✓
something.compile()       ✗
Pattern.compile()         ✗
```

Implementation: check `node.func.value` is `ast.Name` with `.id == expected`.

### N3: `func_value_attr` — Check the object chain for method calls

```python
# Detection rule:
{func_attr: 'walk', func_value_attr: 'Path'}

# Would help distinguish:
Path('.').walk()          ✓ (Python 3.12)
os.walk('.')              ✗ (Python 2+)
```

Note: this is imprecise without type inference. `some_var.walk()` where
`some_var` is a Path wouldn't be caught. But it eliminates the obvious
false positives where the object is a direct name reference.

### N4: `operand_type_hint` — Context for BinOp (limited)

For `dict | dict`, the engine can't know the types of the operands from AST alone.
But it CAN check context: if the `|` appears in a type annotation context, it's a
union type (Python 3.10). If it's in runtime code, it could be dict merge (3.9),
bitwise OR (any version), or set union (any version).

This is inherently imprecise. The best approach: change these entries from `error`
to `info` severity, or require the detection to see `dict(...)  | dict(...)` or
a variable known to be a dict from nearby type hints.

---

## Fix Plan

### Phase 1: Add engine matchers (N1 + N2)

Add `has_keyword` and `func_value_id` to `python_backend.py`:

```python
if key == "has_keyword":
    # Call node: check if a specific keyword argument is present
    keywords = getattr(node, "keywords", [])
    return any(kw.arg == expected for kw in keywords)

if key == "func_value_id":
    # Call node: check what object the method is called on
    func = getattr(node, "func", None)
    if isinstance(func, ast.Attribute):
        val = func.value
        return isinstance(val, ast.Name) and val.id == expected
    return False
```

### Phase 2: Fix the 35 broad database entries

Update each entry to use the new matchers:

**re entries** (3 entries, 1428 false positives):
```yaml
# Before (wrong):
detection: {primary: {ast_type: Call, match: {func_attr: compile}}}

# After (correct — or remove entirely, since the feature is in the regex
# PATTERN string, not in the compile() call. AST can't detect pattern syntax):
# → REMOVE these entries. They can't be detected via AST.
#   The feature is the CONTENT of the string argument, not the function call.
```

**Path entries** (8 entries, ~650 false positives):
```yaml
# Before (wrong):
detection: {primary: {ast_type: Call, match: {func_attr: walk}}}

# After (better — still imprecise but eliminates os.walk):
detection: {primary: {ast_type: Call, match: {func_attr: walk, func_value_id: Path}}}
# OR use the import-based detection as an alternative:
# alternatives: [{ast_type: ImportFrom, match: {names_contains: walk}}]
```

**dataclass entries** (4 entries, 217+ false positives):
```yaml
# Before (wrong):
detection: {primary: {ast_type: Call, match: {func_id: dataclass}}}

# After (correct):
detection: {primary: {ast_type: Call, match: {func_id: dataclass, has_keyword: slots}}}
```

**field entries** (1 entry, 217 false positives):
```yaml
# Before (wrong):
detection: {primary: {ast_type: Call, match: {func_id: field}}}

# After:
detection: {primary: {ast_type: Call, match: {func_id: field, has_keyword: kw_only}}}
```

**BinOp | entries** (3 entries, 53+ false positives each):
These can't be fixed with AST alone — type inference needed.
→ Downgrade to `severity: info` or add context check (annotation vs runtime).

### Phase 3: Fix the fix strategies

Many entries that COULD be auto-fixed are marked `manual`:
- `Path.is_relative_to()` → could check with try/except or os.path
- `str.removeprefix/removesuffix` → can be rewritten with slicing (already have entries for this)
- `zip(strict=True)` → could remove the kwarg and add manual length check

Review each `manual` entry and upgrade to `rewrite_expression` where a safe
mechanical transform exists.

### Phase 4: Remove undetectable entries

Some features CANNOT be detected via AST:
- `re possessive quantifiers` — feature is in regex pattern strings
- `re atomic groups` — same
- `Path.match() case sensitivity` — behavioral change, not syntax change
- `datetime.fromisoformat() improvements` — behavioral, accepts more formats

These should be removed from detection or moved to a "manual audit checklist"
that's shown separately, not mixed with AST-detectable findings.

---

## Expected Impact

After all phases:
- Module "core" findings: ~4974 → ~200 (real, actionable)
- False positive rate: ~95% → <5%
- Auto-fixable coverage: ~8% → ~60%+
- Manual entries: 162 → ~30 (truly manual only)

---

## Files Changed

### Phase 1 (engine):
- `src/core/services/compat/backends/python_backend.py` — add `has_keyword`, `func_value_id`

### Phase 2 (database):
- `src/core/services/compat/database/entries/python/*.yml` — fix 35+ entries

### Phase 3 (fix strategies):
- `src/core/services/compat/database/entries/python/*.yml` — upgrade manual → auto where possible

### Phase 4 (cleanup):
- Remove or recategorize undetectable entries
