---
description: README quality standard and creation process for domain packages
---

# README Standard

## Quality Bar

Every domain package (backend service, route group, frontend script group,
CLI domain) MUST have a README.md that meets this standard:

- **Minimum 450 lines** — anything less needs a justification
- **Exception**: domains with ≤ 3 small files (< 200 lines each) may have
  shorter READMEs, but must still cover all required sections

## The Standard (reference examples)

| README | Lines | Why it's the standard |
|--------|-------|----------------------|
| `core/services/audit/README.md` | 530 | Multi-layer pipeline, ASCII diagrams, data shapes |
| `core/services/tool_install/data/recipes/README.md` | 562 | Full model reference, advanced features, adding new items |
| `core/services/tool_install/data/remediation_handlers/README.md` | 643 | Layer architecture, 10 feature showcases, design decisions |

## Required Sections

Every README MUST include these sections (adapt naming to the domain):

### 1. Title + Summary Block (5-10 lines)
```markdown
# Domain Name

> **X files. Y lines. One-sentence purpose.**
>
> 2-3 sentences explaining what this domain does and why it exists.
```

### 2. How It Works (50-150 lines)
- ASCII diagrams showing data flow or processing pipeline
- Explain the mental model — how a developer should think about this domain
- If multi-layered, show layers with visual hierarchy
- Show key decision points and branching logic

### 3. File Map (10-30 lines)
```
domain/
├── __init__.py      Purpose (line count)
├── module_a.py      Purpose (line count)
├── module_b.py      Purpose (line count)
└── README.md        This file
```

### 4. Per-File Documentation (100-300 lines)
For each file in the domain:
- **Section header** with file name, role, and line count
- **Function table**: `| Function | What It Does |`
- If the file has complex logic, show a mini flow diagram
- If the file has important data structures, show their shape

### 5. Dependency Graph (10-30 lines)
```
module_a.py    ← standalone
    ↑
module_b.py    ← imports from module_a
    ↑
module_c.py    ← imports from module_a + module_b
```

### 6. Consumers (10-30 lines)
```
| Layer | Module | What It Uses |
|-------|--------|-------------|
| Routes | routes/domain.py | function_a, function_b |
| CLI | cli/domain.py | function_c |
| Services | other_service.py | function_d |
```

### 7. Design Decisions (20-60 lines)
- **Why X instead of Y?** — explain non-obvious choices
- **Why is file Z so large?** — justify any file over 500 lines
- **Why this split?** — explain the domain boundary rationale

### 8. Domain-Specific Sections (varies)
Depending on the domain, add:
- **API Endpoints** table (for route domains)
- **Data Shapes** with example dicts/JSON (for data-heavy domains)
- **Advanced Feature Showcase** with real code examples (for complex domains)
- **Adding New Items** step-by-step (for extensible domains)
- **Backward Compatibility** notes (for refactored domains)

## Process

// turbo-all

1. List all files in the domain:
   ```
   ls -la <domain_path>/
   wc -l <domain_path>/*.py  # or *.html
   ```

2. Read EVERY file's to understand:
   - What functions/classes exist
   - How they relate to each other
   - What the internal comments say

3. For files with complex logic, read the actual code (view_file)
   to understand flow, not just signatures

4. Identify consumers by grepping for imports:
   ```
   grep -r "from.*<domain>" src/ --include="*.py" -l
   ```

5. Write the README following the required sections above

6. Verify line count ≥ 450:
   ```
   wc -l <domain_path>/README.md
   ```

## Anti-Patterns (DO NOT)

- ❌ Generic summaries that could apply to any domain
- ❌ Copying function signatures without explaining what they do
- ❌ Skipping the "How It Works" section (the most important one)
- ❌ Omitting ASCII diagrams — they're mandatory for complex flows
- ❌ Writing "see code for details" instead of documenting
- ❌ Listing files without line counts
- ❌ Skipping design decisions — they're the most valuable section
- ❌ Using vague function descriptions like "handles X" or "manages Y"

## Tracking

After creating each README:
1. Update `02-progress-tracker.md` to mark the domain's doc status
2. Below-standard READMEs (< 450 lines) must be rewritten, not patched