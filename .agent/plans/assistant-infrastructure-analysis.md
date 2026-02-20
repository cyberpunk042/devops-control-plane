# Assistant Infrastructure — Needs & Solution Analysis

> **Purpose:** Analyze what each layer of the assistant SYSTEM needs and what
> design options exist. This is about the assistant as a GENERIC INFRASTRUCTURE —
> not per-page content, not specific field guidance.
>
> **Reference:** assistant-realization.md (the 9 layers, the base requirements, the anti-patterns)

---

## Layer 1: Foundation — Detection, Context Resolution, Positioning

### What this layer needs

The foundation must:
- Detect ALL user interactions generically (focus, hover, click, input, scroll, expand/collapse, idle)
- Resolve ANY focused element to its full context hierarchy
- Position the output aligned with the focused element
- Work in ANY scroll container (wizard body, modal body, any future container)

### Design decisions

**Event handling:**
- Delegated event listeners on the nearest scroll ancestor
- Priority order: focus > click > hover > scroll > idle
- Debounce hover (200ms), throttle scroll (100ms), no debounce for focus/click
- Focus events cancel pending hover/scroll timers

**Context resolution:**
- Walk DOM ancestors from the focused element upward
- Look for `data-guide-context` (or equivalent semantic attribute) on ancestor elements
- Build a context path array: `['wizard', 'modules', 'module-0']` or `['docker-setup', 'configure', 'containers', 'web', 'port']`
- The assistant doesn't hardcode what these contexts mean — it just reads the DOM

**Hierarchy depth detection:**
- Every annotated element declares its level type: `step`, `section`, `instance`, `field`
- The focused element's level type determines the depth of the current interaction
- Deeper depth → more specific assistance. Shallower → more overview.

**Positioning:**
- The output block must align vertically with the focused element
- Use `getBoundingClientRect()` relative to the scroll container
- Update position on scroll (same scroll context → natural, OR sync via rAF)
- Smooth transition when focus changes (CSS transition on transform)

**Scroll context:**
- The sidebar and content must share the same scroll parent
- OR the sidebar is position:sticky with the output block dynamically positioned via transform
- Decision needed: shared scroll vs sticky+transform. Tradeoff: shared scroll is simpler but requires layout change; sticky+transform is more flexible but more JS.

### Open questions for this layer
1. Which approach for scroll sync: shared scroll container or sticky+transform?
2. What's the attribute naming convention for context annotations? (`data-guide-*` or something else?)

---

## Layer 2: Information Architecture — What gets shown, structured how

### What this layer needs

Given a context path and depth level, determine:
- What CATEGORY of information is appropriate (orientation, guidance, validation, recommendation, progress, warning)
- What AMOUNT of information is appropriate (one line, a paragraph, a mini-panel)
- What PRIORITY information has (critical warning > recommendation > orientation)

### Design decisions

**Depth-scaled output:**
- Step level → orientation + progress. "You're on step 2 of 6."
- Section level → section-specific summary. Depends on what the section contains.
- Instance level → instance-specific status. What needs attention for this item.
- Field level → field-specific assistance. Most specific, most actionable.

**Category priority:**
When multiple categories are relevant, show highest priority first:
1. Error/warning (something is wrong or conflicting)
2. Required action (something must be done before proceeding)
3. Recommendation (suggested value or setting)
4. Guidance (next step, direction)
5. Orientation (where you are, what this is)

Low-priority content is omitted if higher-priority content exists — NOT stacked below it.

**Output structure:**
Since the base says "one piece of output, not divided into multiple parts":
- The output is a single cohesive block
- Information is layered WITHIN the block by visual hierarchy (size, weight, color) — but not divided into separate cards/panels
- Think of it as a paragraph or a short, structured message — not as a UI panel with sections

### Open questions for this layer
1. When NO element is focused (idle state) — what does the output show? Step-level orientation? Or collapse to nothing?
2. Maximum word count / line count for the output block?

---

## Layer 3: Content Intelligence — Transforming data into assistance

### What this layer needs

This is the CRITICAL layer — the one that differentiates an assistant from a data dump.

The content intelligence layer must:
- Know the difference between DATA and ASSISTANCE
- Transform raw state into actionable output
- Be GENERIC — work with any content type, not hardcoded per field

### Design decisions

**Data vs Assistance:**
- DATA: "Port is empty. Flask default is 5000. cli uses 8000."
- ASSISTANCE: this layer must produce something BEYOND restating the data. It must ADD VALUE.

What does "adding value" mean concretely?
- **Synthesis** — combining multiple data points into an insight ("5000 is available and standard for Flask")
- **Prioritization** — showing what matters most right now, hiding noise
- **Actionability** — not just telling, but offering to DO
- **Anticipation** — knowing what the user will need NEXT even before they ask
- **Simplification** — reducing complex choices to simple recommendations

**How to achieve this generically:**
The assistant can't have hardcoded intelligence for every field. Instead, the content layer needs a PROTOCOL — a way for each context to declare:
- What assistance it can provide
- What data it needs to provide it
- What actions are available

This could be:
- **Attribute-based:** DOM elements carry `data-guide-recommend="5000"` `data-guide-reason="Flask default"` `data-guide-conflict-check="port"`
- **Registry-based:** JavaScript registers guide handlers per context type
- **Hybrid:** DOM attributes for simple cases, JS handlers for complex logic (relationships, validation, cross-element checks)

The hybrid approach seems right:
- Simple guidance (labels, descriptions, recommendations) → DOM attributes
- Complex intelligence (conflict detection, dependency analysis, cross-element validation) → registered JS functions

### Key insight
The content intelligence is NOT a static catalogue of messages. It's a PROTOCOL that contexts implement. The engine calls the protocol, the context provides the intelligence. This keeps the engine generic and the intelligence specific but extensible.

### Open questions
1. Should the protocol be DOM-first (attributes) or JS-first (registry)?
2. How do we handle contexts that don't implement the protocol? (graceful fallback vs silent)

---

## Layer 4: Visual Design — How the output looks

### What this layer needs

The output must:
- Look like it belongs in the app (not a foreign widget)
- Be readable at sidebar width (~280px)
- Have clear visual hierarchy within its compact space
- Use existing design tokens (CSS variables, color conventions)

### Design decisions

**Integration with admin.css:**
- Use existing CSS variables: `--bg-inset`, `--border-subtle`, `--accent`, `--text-primary`, `--text-muted`, etc.
- Use existing font sizes and families
- Status colors: `--success` (green), `--warning` (amber), `--error` (red)
- Border radius: match existing cards (8px)

**Output block styling:**
- Subtle background (not a heavy card — use `--bg-inset` or even transparent)
- Thin left border in accent color to connect visually to the focus indicator
- Compact typography: 0.78-0.85rem for body, 0.7rem for metadata
- No heavy borders or drop shadows — the output should be LIGHT and QUIET, not competing with the content

**Content within the output:**
- Primary text: the main assistance message (bold or normal weight)
- Secondary text: supporting context (muted color, smaller)
- Action elements: styled as subtle inline buttons (accent color, small)
- Status indicators: use existing ✓ ⚠ ✗ patterns with color

**The output should feel like a whisper, not a shout.** It's helping, not demanding attention.

### Open questions
1. Should the output have an explicit container (card-like) or float as text against a transparent background?
2. Should action buttons look like app buttons (`.btn` class) or have their own lighter style?

---

## Layer 5: Interaction Design — How the user engages

### What this layer needs

The output must:
- Offer actionable elements where applicable (apply recommendation, navigate)
- NOT steal focus from the form
- Support keyboard users (but not require keyboard)
- Handle the interaction lifecycle (click action → result → update output)

### Design decisions

**Focus management:**
- CRITICAL: clicking an action button in the assistant must NOT blur the form field
- Use `mousedown` + `preventDefault()` instead of `click` for action buttons
- After an action is performed, return focus to the original field

**Action types (generic):**
- `apply` — set a value on the target element
- `navigate` — scroll to and focus another element
- `trigger` — call an existing app function
- `expand` — show more detail within the output block
- `dismiss` — acknowledge and hide the current guidance

**No action required:**
- Many assistant outputs will have NO actions — just information
- Actions are an enhancement, not a requirement
- The output works as pure guidance even without interactive elements

### Open questions
1. Are actions part of the base implementation or a later enhancement?
2. Should actions be defined by the content protocol (each context declares its available actions)?

---

## Layer 6: Behavioral Design — Animations and transitions

### What this layer needs

The output must:
- Appear smoothly (not pop abruptly)
- Transition smoothly between positions (when focus moves)
- Update content smoothly (when the assistance changes)
- Handle rapid changes without flicker

### Design decisions

**Position transitions:**
- CSS `transition: transform 200ms ease-out` for position changes
- When focus moves, the block glides to the new Y position

**Content transitions:**
- Opacity transition: fade out old content (100ms), fade in new content (100ms)
- Total content change takes ~200ms — fast enough to feel responsive
- If the same content stays (e.g., scrolling without changing focus), no transition

**Debounce and stability:**
- Don't update on every scroll pixel — throttle to 100ms
- Don't flash different content during hover → focus transitions — focus always wins
- If a content transition is in progress and new content arrives, cancel the old and start fresh (no queuing)

**Entry/exit animations:**
- When the assistant first activates → slide in from side + fade in
- When deactivating → fade out
- These are one-time animations, not per-content-change

### Open questions
1. Any specific easing function preference for position transitions?
2. Should the output fade between contexts (step → step) or hard-switch?

---

## Layer 7: Integration — Connecting to app capabilities

### What this layer needs

The assistant must be able to:
- Read current values from form elements
- Set values on form elements (auto-fill)
- Trigger existing app functions (wizardDetect, wizardAddEnv, etc.)
- Navigate/scroll to specific elements
- Read async data (vault status, detection results)

### Design decisions

**Form integration:**
- Read values: `element.value`, `element.checked`, `element.selectedIndex`
- Set values: `element.value = x; element.dispatchEvent(new Event('input'))` — must trigger existing change handlers
- The assistant doesn't touch internal state — it operates through the DOM, just like a user would

**Function integration:**
- Actions that trigger app functions need references to those functions
- Options: direct `window.*` calls, or a registered action map
- A registered action map is cleaner: `guideActions.register('wizard.detect', wizardDetect)`
- BUT this adds coupling. Direct window calls are simpler for the base version.

**Navigation:**
- Scroll to element: `element.scrollIntoView({ behavior: 'smooth', block: 'center' })`
- Focus element: `element.focus()` after scroll
- This is generic — works with any element

**Data reading:**
- For async data (vault status, API results): the content intelligence layer can call existing API functions
- The assistant doesn't build its own data layer — it reads what the app already has

### Open questions
1. Direct window calls for base version, registered action map for later?
2. Should the assistant cache API results or always read fresh?

---

## Layer 8: State Management — Memory and adaptation

### What this layer needs

The assistant must:
- Know what it has already shown (don't repeat the same guidance)
- Track user interaction speed (fast = experienced, slow = more help)
- Track completion status within the current context
- Persist across context transitions within the same session

### Design decisions

**Scope of state:**
- Session-level: user experience level, assistant preference, visited contexts
- Context-level: what guidance has been shown, which elements are complete
- Element-level: last value seen, last interaction timestamp

**State storage:**
- In-memory object during the session
- No localStorage for base version (avoid complexity)
- State is lost on page reload — acceptable for V1

**Adaptation logic (base version):**
- Track time between interactions
- If user moves fast (< 2s between focuses) → reduce output verbosity
- If user lingers (> 5s on a field) → increase verbosity, maybe offer more detail
- This is a FUTURE enhancement — not required for base

**Completion tracking:**
- The assistant can observe which fields have values
- Required: knowing which fields exist in the current context
- This is derived from the DOM annotations, not hardcoded

### Open questions
1. How much state management is in the base version vs later?
2. Should experience level adaptation be explicit (user picks "beginner/expert") or implicit (detected from behavior)?

---

## Layer 9: Lifecycle — Start, transition, end

### What this layer needs

The assistant must:
- Activate when the user enters an assisted context
- Deactivate when they leave
- Handle context transitions (step change, modal open/close)
- Handle nested contexts (modal opened from within a wizard step)
- Respect user on/off preference

### Design decisions

**Activation triggers:**
- Wizard tab selected → activates for wizard context
- Setup modal opened (any integration) → activates for that modal's context
- Tab switch away from wizard → deactivates
- Modal closed → deactivates modal context (reverts to wizard if wizard is active)

**Context stacking:**
- Contexts can be nested: wizard > step > Docker modal > configure step
- When a modal opens, the assistant pushes the modal context on top
- When the modal closes, it pops back to the previous context
- This is a simple stack (push/pop), not complex routing

**Deactivation behavior:**
- On deactivate: output fades out, event listeners removed (or paused)
- State for that context is preserved in memory (in case user returns)

**User preference:**
- Toggle in settings (tutorialGuide or similar)  
- When off: engine doesn't initialize, no event listeners, no output
- Can be toggled on/off at any time without page reload

### Open questions
1. Should the assistant auto-activate on first wizard visit (onboarding) even if the preference is off?
2. Context stacking: is a simple array stack sufficient, or do we need a more complex state machine?

---

## Summary of Design Decisions Needed

| Layer | Key Decision | Options |
|-------|-------------|---------|
| 1. Foundation | Scroll sync approach | Shared container vs sticky+transform |
| 1. Foundation | Context attribute naming | `data-guide-context` vs other |
| 2. Info Architecture | Idle state behavior | Show step overview vs collapse |
| 3. Content Intelligence | Protocol approach | DOM attributes vs JS registry vs hybrid |
| 4. Visual Design | Output container style | Card-like vs transparent float |
| 5. Interaction | Actions in base version? | Base with actions vs actions later |
| 6. Behavior | Content transition style | Crossfade vs slide vs instant |
| 7. Integration | Function references | Direct window.* vs registered map |
| 8. State | Base version scope | Minimal vs full state management |
| 9. Lifecycle | Context model | Simple stack vs state machine |

These decisions need to be made before any code is written. Each affects the others — positioning affects visual design, content intelligence affects information architecture, lifecycle affects state management.
