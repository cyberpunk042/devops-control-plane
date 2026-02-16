# Path 7: Modal Preview & UI Settings

> **Status**: Phase 7A+7B ✅ Implemented — ready for testing
> **Files created**: `_settings.html`, `_content_modal_preview.html`
> **Files modified**: `admin.css`, `_nav.html`, `_globals.html`, `_theme.html`, `dashboard.html`

---

## 1. Settings Infrastructure (Phase 7A ✅)

### Preferences Store (`_settings.html`)

All user preferences persisted in `localStorage('dcp_prefs')` as JSON:

```json
{
  "theme": "dark",
  "uiScale": "default",
  "density": "normal",
  "previewMode": "modal"
}
```

### UI Scale (Axis 1 — root font-size)

| Profile | Root font-size | vs Default |
|---|---|---|
| Compact | 12.75px (×0.85) | −15% |
| Default | 15px (×1.00) | baseline |
| Comfortable | 16.5px (×1.10) | +10% |
| Large | 18.75px (×1.25) | +25% |

### Density (Axis 2 — --space-* overrides)

| Profile | --space-sm | --space-md | --space-lg |
|---|---|---|---|
| Dense | 0.3rem | 0.7rem | 1rem |
| Normal | 0.5rem | 1rem | 1.5rem |
| Spacious | 0.65rem | 1.25rem | 1.85rem |

### Settings Panel

⚙️ gear icon in nav bar → dropdown panel with:
- Theme: Dark / Light
- UI Scale: Compact / Default / Comfortable / Large
- Density: Dense / Normal / Spacious
- Preview Mode: Modal / Navigate

### Migration

Legacy `localStorage('theme')` auto-migrated to `dcp_prefs.theme` on first load.

---

## 2. Modal Preview (Phase 7B ✅)

### Scope

Modal is for **cross-tab file links only** — when a user clicks a file link from
Audit, Integrations, DevOps, etc. The Content Vault's own file browser is unchanged.

### Behavior

1. `openFileInEditor()` checks `prefsGet('previewMode')`:
   - `'modal'` (default) + not already in Content tab → `openFileInModal(filePath)`
   - `'forward'` or already in Content tab → existing `switchTab(...)` behavior
2. Modal uses existing `modalOpen()` infrastructure with `.modal-box.preview` (85vw × 85vh)
3. Supports: markdown (rendered), text, image, video, audio, binary info
4. "Open in Content Tab" button for full editing/actions
5. Close returns to exact context — zero tab navigation

### Single Point of Change

Only `openFileInEditor()` was modified. All 15+ callers (integration cards, DevOps file links, audit links) automatically get modal behavior without any changes.

---

## 3. File Inventory

### New files
| File | Lines | Purpose |
|---|---|---|
| `scripts/_settings.html` | ~170 | Prefs store, settings panel, scale/density/theme application |
| `scripts/_content_modal_preview.html` | ~120 | Modal preview component |

### Modified files
| File | Change |
|---|---|
| `admin.css` | +115 lines: `.settings-gear`, `.settings-panel`, `.settings-btn`, `.modal-box.preview` |
| `partials/_nav.html` | +7 lines: gear icon + panel container |
| `scripts/_globals.html` | ~6 lines: modal guard in `openFileInEditor()` |
| `scripts/_theme.html` | Simplified: delegates to `_prefSetTheme()` from settings store |
| `dashboard.html` | +2 includes: `_settings.html`, `_content_modal_preview.html` |

### Unchanged (callers — no modification needed)
- All `_integrations_*.html` files
- `_devops.html`, `_audit.html`, etc.

---

## 4. Decisions Made

| Question | Decision |
|---|---|
| Default preview mode | `modal` — new behavior is default |
| Settings location | Gear icon dropdown in nav bar |
| Scope of modal | Cross-tab only, NOT Content Vault browser |
| Modal editing | Read-only peek, "Open in Content Tab" for edits |
| Scale implementation | Root font-size change (replicates browser zoom) |
| Density implementation | Override `--space-*` CSS custom properties |

---

## 5. Phase 7C: Polish (TODO)

- [ ] Test all integration file links open in modal
- [ ] Test scale/density/theme persistence across reload
- [ ] Test legacy theme migration
- [ ] Test settings panel close on outside click
- [ ] Verify no FOUC (flash of unstyled content) on load
