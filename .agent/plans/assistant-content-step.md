# Assistant — wizard/content Implementation Plan

> Step 4: 📁 Content Folders
>
> **No engine evolution required** — the existing variant engine, dynamic
> children, and `childTemplate` mechanisms from the secrets step are
> sufficient.  This plan covers the catalogue entry and content strategy.

---

## Phase 1: No Engine Changes Needed ✅

The content step uses:

- **Dynamic children** (`childTemplate`) for the folder list
  — same mechanism as modules list and env vault list.
- **Static section** with `variants` for infrastructure dirs
  — each infra row can have exists/auto-created variants using
  `textContains` conditions on the status label.
- **`hasSelector`** for checking "suggested" badges via
  `[style*="suggested"]` or by text content.

All of these are already implemented in the engine from the
secrets step work.

---

## Phase 2: Catalogue — wizard/content Context

### DOM Map

The content step renders this DOM structure after the API call:

```
#wizard-body
├── div (flex header)
│   ├── h2: "📁 Content Folders"
│   └── button: "🔄 Rescan"                    ← calls renderWizard()
├── p: intro text
├── #wiz-content-folders                        ← top-level wrapper
│   ├── #wiz-content-list                       ← dynamic parent (selectable folders)
│   │   ├── label (one per folder)              ← dynamic child
│   │   │   ├── input[type="checkbox"]
│   │   │   ├── div: { name + badge, file count }
│   │   │   └── span[data-folder-status]: "✅ Active" / "—"
│   │   └── ...
│   ├── p: hint text (💡 Selected folders / Explore All)
│   └── #wiz-content-infra                      ← static section
│       ├── div: "🏗️ Content Infrastructure" label
│       ├── p: "managed automatically…" hint
│       └── #wiz-content-infra-list             ← dynamic parent (infra dirs)
│           ├── div (one per infra dir)         ← dynamic child
│           │   ├── span: icon
│           │   ├── code: dir name (e.g. ".ledger")
│           │   ├── span: "shared" / "local" badge
│           │   ├── span: description text
│           │   └── span: "✅ N files" / "⬜ auto-created"
│           └── ...
```

### Catalogue Tree

```json
{
    "context": "wizard/content",
    "title": "Content Folders",
    "icon": "📁",
    "content": "...",
    "children": [
        {
            "id": "content-list",
            "selector": "#wiz-content-list",
            "dynamic": true,
            "childTemplate": {
                "selector": "#wiz-content-list > label",
                "nameSelector": "div > div:first-child",
                "variants": [
                    { "when": { "textContains": "Active" }, ... },
                    { "when": { "textContains": "suggested" }, ... },
                    // Fallback: unchecked, not suggested
                ]
            }
        },
        {
            "id": "content-infra",
            "selector": "#wiz-content-infra",
            "separator": true,
            "dynamic": true,
            "childTemplate": {
                "selector": "#wiz-content-infra-list > div",
                "nameSelector": "code",
                "variants": [
                    // Per-role variants matched by dir name text
                    { "when": { "textContains": ".ledger" }, ... },
                    { "when": { "textContains": ".state" }, ... },
                    { "when": { "textContains": ".backup" }, ... },
                    { "when": { "textContains": ".large" }, ... },
                    { "when": { "textContains": ".pages" }, ... },
                    // Existence state (fallback)
                    { "when": { "textContains": "files" }, ... },
                    { "when": { "textContains": "auto-created" }, ... }
                ]
            }
        }
    ]
}
```

### Content Strategy — What the assistant says

#### Step context (no hover)

Sets the stage. Explains what content management means in the control
plane — it's not just files, it's a managed ecosystem with encryption,
backups, large file optimization, and shared data via the ledger.

> "This step lets you choose which folders appear in the 📁 Content tab —
> your workspace for browsing, previewing, encrypting, and archiving
> project files.
>
> Below the folders, you'll see the infrastructure directories that the
> control plane manages automatically. These track your chat history,
> audit traces, backups, and optimized large files — they're created on
> demand as you use the system."

#### 📁 Content List (section hover)

Explains what "content folder" means — a directory whose files are
browsable, uploadable, encryptable, and archivable via the Content tab.

> "Select the folders you want to manage through the Content tab. Each
> selected folder becomes browsable with preview, encryption, download,
> and archive capabilities.
>
> You can also browse any project folder using 🗂 Explore All in the
> Content tab — this selection just controls the default folder tabs."

#### Dynamic folder row variants

**✅ Active:** Folder is selected for content management.

> "This folder is managed — it'll appear as a tab in the 📁 Content view
> where you can browse, upload, encrypt, and back up files."

**suggested (unchecked):** Detected as a common content folder name.

> "This looks like a good candidate for content management — it matches a
> common content folder pattern. Check the box to include it."

**Fallback (unchecked, not suggested):**

> "A project directory. Check the box to include it in the Content tab —
> you'll get browsing, preview, encryption, and archive capabilities."

#### 🏗️ Content Infrastructure (section hover)

Explains the automatic infrastructure layer. These are not user-selected
— they're system-managed directories that appear as features are used.

> "These directories are created and maintained by the control plane.
> They're gitignored and never need manual management — the system handles
> creation, population, and cleanup.
>
> Think of them as internal storage layers: the ledger shares data via
> git branches, .state keeps local caches, .backup holds archives, .large
> optimizes oversized files, and .pages stores generated site builds."

#### Dynamic infra row variants (per-role, 5 roles)

Matched by dir name (`.ledger`, `.state`, etc.) in text content:

**.ledger:** Git worktree for shared data.

> "The ledger is a separate git branch checked out as a worktree. It
> stores chat threads, execution traces, and saved audit snapshots —
> shared with collaborators via git push/pull.
>
> Badge: 'shared' means this data syncs with your remote repository."

**.state:** Local ephemeral cache.

> "Local-only storage for preferences, pending audits, execution runs,
> trace recordings, and cached scan results. None of this leaves your
> machine — it's gitignored.
>
> This is almost certainly present by now — the control plane creates it
> the first time any feature needs local persistence."

**.backup:** Archive storage.

> "Backup archives created via the Content tab's Archive view — compressed
> snapshots of folders you choose to protect. Can live at any level.
>
> Badge: 'local' means these stay on disk. For off-machine protection,
> use the release artifact upload."

**.large:** Optimized large files.

> "When files over 2 MB are uploaded through the Content tab, they're
> automatically moved here. The .large directory is gitignored, but
> files appear virtually in their parent folder.
>
> For sharing, large files can be uploaded to GitHub release artifacts.
> The .large dir can exist at any folder level — not just inside
> configured content folders."

**.pages:** Generated site output.

> "Output from the Pages pipeline — your generated Docusaurus site,
> build artifacts, and static assets. Rebuilt on each deploy.
>
> This is a build output, not something you edit directly."

#### Existence state variants (fallback)

**"files" in text → exists:** Dir exists with content.

> "This infrastructure directory is active and has content. It's managed
> automatically — you don't need to interact with it directly."

**"auto-created" in text → not yet created:** Dir doesn't exist yet.

> "This directory hasn't been created yet. It'll appear automatically the
> first time a feature needs it — no manual setup required."

---

## Phase 3: Resolvers

Register resolvers in `_wizard_init.html` for the content step:

```javascript
// When activating wizard/content:
window._assistant.resolvers.folderCount = function() {
    return document.querySelectorAll('#wiz-content-list > label').length;
};
window._assistant.resolvers.activeFolderCount = function() {
    return document.querySelectorAll(
        '#wiz-content-list > label input:checked'
    ).length;
};
```

These enable dynamic text like "You've selected {{activeFolderCount}} of
{{folderCount}} folders."

**Decision:** Add these if the content text uses the template vars.
For the initial version, we may not need them — the content doesn't
reference folder counts dynamically.

---

## Implementation Order

1. ✅ **Backend: `include_hidden` param** — added to
   `detect_content_folders`, returns infrastructure dirs tagged with
   `type: "infrastructure"`, `role`, `icon`, `description`, etc.
2. ✅ **Route: `?include_hidden=true`** — query param on
   `/config/content-folders`, passes to backend
3. ✅ **Frontend: content step** — splits results into selectable
   folders + infrastructure section, adds config loading guard +
   rescan button
4. 🔲 **Catalogue: wizard/content** — author full JSON entry with
   2 sections (content-list + content-infra), role variants
5. 🔲 **Test** — verify all sections, folder toggle, infra display

---

## Risks

| Risk | Mitigation |
|------|------------|
| `nameSelector` on label rows | Folder names are in `div > div:first-child` (font-weight:500). May need adjustment if the badge interferes with name extraction |
| Infrastructure dirs always listed | Even if `include_hidden=false` is called (other consumers), infra dirs don't appear — only the wizard uses `?include_hidden=true` |
| `.large` at any level | Root-level scan only checks for `.large` directly under project root. Per-folder `.large` is visible in the Content tab itself |
| No engine changes | Confirmed — all mechanisms from the secrets step work here. `childTemplate` + `variants` + `textContains` are sufficient |
