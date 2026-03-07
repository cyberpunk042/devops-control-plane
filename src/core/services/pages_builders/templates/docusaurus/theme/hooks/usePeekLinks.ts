import { useEffect } from 'react';
import { useLocation } from '@docusaurus/router';

// Peek index is generated at build time by the Python pipeline.
// It maps doc-relative paths to their resolved references.
// @ts-ignore — JSON module import
import peekIndex from '@site/src/peek-index.json';

const IS_LOCAL = typeof window !== 'undefined' && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1');
const _RAW_REPO = '__REPO_URL__';
const _RAW_BASE = '__BASE_URL__';
const _RAW_ADMIN = '__ADMIN_URL__';
const REPO_URL = _RAW_REPO.startsWith('__') ? '' : _RAW_REPO;
const BASE_URL = _RAW_BASE.startsWith('__') ? '/' : _RAW_BASE;
const ADMIN_URL = _RAW_ADMIN.startsWith('__') ? '' : _RAW_ADMIN;

/**
 * Returns the current peek mode: 'dev' routes to Content Vault,
 * 'live' routes to GitHub. Default: dev when localhost, live when published.
 * The dev badge toggle sets window.__peekMode to override.
 */
function _peekMode(): 'dev' | 'live' {
    if (typeof window !== 'undefined' && (window as any).__peekMode) {
        return (window as any).__peekMode;
    }
    return IS_LOCAL ? 'dev' : 'live';
}

/**
 * Open a hash route in the admin panel via Tab Mesh (SPA routing + focus)
 * or fall back to window.open if the mesh is not available.
 *
 * @param hash  Hash route including '#', e.g. '#content/docs/vault.py@preview'
 */
function _openInAdmin(hash: string): void {
    if (window.TabMesh) {
        window.TabMesh.navigateTo('admin', hash);
    } else {
        window.open(`${ADMIN_URL || location.origin}/${hash}`, '_blank');
    }
}

interface OutlineItem {
    text: string;
    line: number;
    kind: string;   // 'heading' | 'function' | 'class'
    level?: number; // heading level (1-3)
}

interface PeekRef {
    text: string;
    resolved_path: string;
    line_number: number | null;
    is_directory: boolean;
    resolved?: boolean;
    outline?: OutlineItem[];
    doc_url?: string;
}

let _peekTooltipEl: HTMLElement | null = null;
let _peekPreviewEl: HTMLElement | null = null;

function _dismissPeekTooltip(): void {
    if (_peekTooltipEl) {
        _peekTooltipEl.remove();
        _peekTooltipEl = null;
    }
}

let _peekHistoryPushed = false;
let _peekLineObserver: IntersectionObserver | null = null;
let _peekCurrentLine = 0;

function _closePeekPreview(): void {
    if (_peekLineObserver) {
        _peekLineObserver.disconnect();
        _peekLineObserver = null;
    }
    if (_peekPreviewEl) {
        _peekPreviewEl.remove();
        _peekPreviewEl = null;
    }
    _peekCurrentLine = 0;
    if (_peekHistoryPushed) {
        _peekHistoryPushed = false;
    }
}

function _closePeekPreviewViaHistory(): void {
    if (_peekLineObserver) {
        _peekLineObserver.disconnect();
        _peekLineObserver = null;
    }
    if (_peekPreviewEl) {
        _peekPreviewEl.remove();
        _peekPreviewEl = null;
    }
    _peekCurrentLine = 0;
    if (_peekHistoryPushed) {
        _peekHistoryPushed = false;
        history.back();
    }
}

// ── Monaco CDN lazy loader ──
const MONACO_CDN = 'https://cdn.jsdelivr.net/npm/monaco-editor@0.45.0/min';
let _monacoLoaded = false;
let _monacoLoadPromise: Promise<void> | null = null;

function _loadMonaco(): Promise<void> {
    if (_monacoLoaded) return Promise.resolve();
    if (_monacoLoadPromise) return _monacoLoadPromise;
    _monacoLoadPromise = new Promise<void>((resolve, reject) => {
        const script = document.createElement('script');
        script.src = `${MONACO_CDN}/vs/loader.js`;
        script.onload = () => {
            (window as any).require.config({ paths: { vs: `${MONACO_CDN}/vs` } });
            (window as any).require(['vs/editor/editor.main'], () => {
                _monacoLoaded = true;
                resolve();
            });
        };
        script.onerror = reject;
        document.head.appendChild(script);
    });
    return _monacoLoadPromise;
}

// ── Marked CDN lazy loader ──
const MARKED_CDN = 'https://cdn.jsdelivr.net/npm/marked@12.0.0/marked.min.js';
let _markedLoaded = false;
let _markedLoadPromise: Promise<void> | null = null;

function _loadMarked(): Promise<void> {
    if (_markedLoaded) return Promise.resolve();
    if (_markedLoadPromise) return _markedLoadPromise;
    _markedLoadPromise = new Promise<void>((resolve, reject) => {
        const script = document.createElement('script');
        script.src = MARKED_CDN;
        script.onload = () => { _markedLoaded = true; resolve(); };
        script.onerror = reject;
        document.head.appendChild(script);
    });
    return _markedLoadPromise;
}

// ── Language map for Monaco ──
const LANG_MAP: Record<string, string> = {
    py: 'python', ts: 'typescript', tsx: 'typescript', js: 'javascript',
    jsx: 'javascript', yml: 'yaml', yaml: 'yaml', json: 'json',
    sh: 'shell', bash: 'shell', css: 'css', html: 'html',
    md: 'markdown', mdx: 'markdown', toml: 'ini', sql: 'sql',
    go: 'go', rs: 'rust', tf: 'hcl', Dockerfile: 'dockerfile',
};

// ── Popstate listener for history-based peek closing ──
if (typeof window !== 'undefined') {
    window.addEventListener('popstate', () => {
        if (_peekPreviewEl) {
            _closePeekPreview();
        }
    });
}


function _esc(s: string): string {
    const div = document.createElement('div');
    div.textContent = s;
    return div.innerHTML;
}

function _renderOutline(outline: OutlineItem[] | undefined, ref: PeekRef): string {
    if (!outline || outline.length === 0) return '<div class="peek-tooltip__outline" data-peek-outline></div>';

    const resolvedPath = ref.resolved_path;
    const parentDir = resolvedPath.substring(0, resolvedPath.lastIndexOf('/'));

    const icons: Record<string, any> = {
        heading: { 1: '▸', 2: '·', 3: '·' },
        class: '🔷',
        function: 'ƒ',
    };

    const items = outline
        .map((item) => {
            const isIndented = (item.kind === 'heading' && (item.level || 1) >= 2) ||
                (item.kind === 'function');
            const weight = isIndented ? '' : 'font-weight:500;';
            const indent = isIndented ? 'padding-left:0.6rem;' : '';

            let icon: string;
            if (item.kind === 'heading') {
                icon = icons.heading[item.level || 1] || '·';
            } else {
                icon = icons[item.kind] || '·';
            }

            const lineParam = item.line ? ':' + item.line : '';

            return `<div class="peek-tooltip__outline-row" style="display:flex;align-items:center;gap:0.25rem;${indent}${weight}padding:1px 0" data-line="${item.line || 0}" data-heading-text="${_esc(item.text)}">
                <span style="font-size:0.7rem;color:var(--ifm-color-secondary-darkest, #999);flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;cursor:pointer" class="peek-outline-text">
                    ${icon} ${_esc(item.text)}
                </span>
                <span class="peek-tooltip__outline-actions" style="display:flex;gap:2px;flex-shrink:0">
                    <button class="peek-outline-act" title="Preview at line ${item.line || ''}" data-action="preview" data-line="${item.line || 0}">\ud83d\udc41</button>
                    <button class="peek-outline-act" title="Open at line ${item.line || ''}" data-action="open" data-line="${item.line || 0}">\ud83d\udcc4</button>
                    ${parentDir ? '<button class="peek-outline-act" title="Browse folder" data-action="browse" data-line="0">\ud83d\udcc2</button>' : ''}
                    <button class="peek-outline-act" title="New tab" data-action="newtab" data-line="${item.line || 0}">\u2197</button>
                </span>
            </div>`;
        })
        .join('');
    return `<div class="peek-tooltip__outline" data-peek-outline>${items}</div>`;
}

/**
 * Docusaurus hook — auto-annotate file references as peek links.
 *
 * On each page navigation:
 *   1. Maps the current URL to a peek index key
 *   2. Looks up resolved references for that page
 *   3. Walks DOM text nodes and wraps matches in interactive spans
 *   4. Click opens tooltip with actions (Open link / GitHub link)
 *   5. Cleans up on navigation (SPA route change)
 */
// Track whether the effect has run before (survives SPA navigation, resets on refresh)
let _peekLastPageKey = '';

export function usePeekLinks(): void {
    const location = useLocation();

    useEffect(() => {
        const pageKey = locationToDocPath(location.pathname);
        const allRefs: PeekRef[] | undefined = (peekIndex as Record<string, PeekRef[]>)[pageKey];

        // Dev/Live mode toggle badge — in the top navbar, like admin panel.
        if (IS_LOCAL) {
            const existingMode = document.querySelector('.peek-mode-badge');
            if (existingMode) existingMode.remove();

            const modeBadge = document.createElement('span');
            modeBadge.className = 'peek-mode-badge';
            const currentMode = _peekMode();
            document.body.setAttribute('data-peek-mode', currentMode);
            modeBadge.innerHTML = `<span class="peek-mode-badge__icon">${currentMode === 'dev' ? '🔧' : '🌐'}</span><span class="peek-mode-badge__label">${currentMode === 'dev' ? 'Dev' : 'Live'}</span>`;
            modeBadge.title = `Peek mode: ${currentMode}. Click to toggle.`;
            modeBadge.style.cursor = 'pointer';
            modeBadge.addEventListener('click', () => {
                const next = _peekMode() === 'dev' ? 'live' : 'dev';
                (window as any).__peekMode = next;
                document.body.setAttribute('data-peek-mode', next);
                modeBadge.innerHTML = `<span class="peek-mode-badge__icon">${next === 'dev' ? '🔧' : '🌐'}</span><span class="peek-mode-badge__label">${next === 'dev' ? 'Dev' : 'Live'}</span>`;
                modeBadge.title = `Peek mode: ${next}. Click to toggle.`;
            });
            const navRight = document.querySelector('.navbar__items--right');
            if (navRight) {
                navRight.prepend(modeBadge);
            }
        }

        if (!allRefs || allRefs.length === 0) return;

        // Split into resolved and unresolved
        const resolved = allRefs.filter((r) => r.resolved !== false);
        const unresolved = allRefs.filter((r) => r.resolved === false);

        // ── Content-change-aware annotation ──
        // Two cases:
        //   Initial load / refresh: SSR content is already correct → annotate immediately
        //   SPA navigation: old page content still in DOM → wait for content swap
        //
        // We use _peekLastPageKey to distinguish. On first render (or same-page
        // reload after F5), oldFingerprint is empty → skip content-change check.
        // On SPA nav to a DIFFERENT page, capture fingerprint of old content
        // and wait until it changes.
        const isSpaNavToDifferentPage = _peekLastPageKey !== '' && _peekLastPageKey !== pageKey;
        _peekLastPageKey = pageKey;

        let cancelled = false;
        let observer: MutationObserver | null = null;
        let rafId = 0;

        // Only fingerprint when navigating between different pages (SPA)
        const oldContainer = document.querySelector('.markdown');
        const oldFingerprint = isSpaNavToDifferentPage && oldContainer
            ? (oldContainer.textContent || '').trim().substring(0, 80)
            : '';

        function _doAnnotate(): void {
            if (cancelled) return;
            const container = document.querySelector('.markdown');
            if (!container) return;
            // Guard: don't annotate if already done (idempotency)
            if (container.querySelector('.peek-link')) return;

            if (resolved.length > 0) {
                annotatePeekRefs(container as HTMLElement, resolved);
            }
            if (unresolved.length > 0) {
                annotateUnresolvedRefs(container as HTMLElement, unresolved);
            }

            // Show annotation count badge
            const totalAnnotated = container.querySelectorAll('.peek-link').length;
            if (totalAnnotated > 0) {
                const existing = document.querySelector('.peek-status');
                if (existing) existing.remove();

                const badge = document.createElement('div');
                badge.className = 'peek-status';
                badge.innerHTML = `<span class="peek-status__icon">🔗</span><span class="peek-status__count">${totalAnnotated} ref${totalAnnotated !== 1 ? 's' : ''}</span>`;
                document.body.appendChild(badge);

                // Fade to subtle after 2s
                setTimeout(() => { badge.classList.add('peek-status--subtle'); }, 2000);
            }
        }

        function _isContentReady(): boolean {
            const container = document.querySelector('.markdown');
            if (!container) return false;
            const text = (container.textContent || '').trim();
            if (text.length < 20) return false;
            // If we had old content, ensure the new content is DIFFERENT
            // (proves React has actually swapped the page)
            if (oldFingerprint && text.substring(0, 80) === oldFingerprint) {
                return false;  // Still showing old page content
            }
            return true;
        }

        // Wait for React to paint, then start detection
        rafId = requestAnimationFrame(() => {
            if (cancelled) return;

            // Immediate check (works for SSR / initial load)
            if (_isContentReady()) {
                _doAnnotate();
                return;
            }

            // MutationObserver: watch for DOM changes until new content appears
            observer = new MutationObserver(() => {
                if (cancelled) return;
                if (_isContentReady()) {
                    const container = document.querySelector('.markdown');
                    if (container && !container.querySelector('.peek-link')) {
                        _doAnnotate();
                    }
                    if (observer) { observer.disconnect(); observer = null; }
                }
            });
            // Observe the stable Docusaurus root — <article> can be
            // replaced entirely during SPA navigation which detaches
            // any observer watching it.
            const root = document.getElementById('__docusaurus')
                || document.body;
            observer.observe(root, { childList: true, subtree: true });
        });

        return () => {
            cancelled = true;
            if (rafId) cancelAnimationFrame(rafId);
            if (observer) { observer.disconnect(); observer = null; }
            _dismissPeekTooltip();
            // Remove annotation count badge
            const badge = document.querySelector('.peek-status');
            if (badge) badge.remove();
            // Remove mode badge
            const modeBadge = document.querySelector('.peek-mode-badge');
            if (modeBadge) modeBadge.remove();
            // Clean up peek links on navigation
            const container = document.querySelector('.markdown');
            if (container) {
                container.querySelectorAll('span.peek-link').forEach((el) => {
                    const text = el.textContent || '';
                    el.replaceWith(document.createTextNode(text));
                });
            }
        };
    }, [location.pathname]);
}

/**
 * Map a Docusaurus URL path to the peek index key.
 *
 * Handles:
 *   - baseUrl stripping (e.g. /pages/site/code-docs/)
 *   - routeBasePath: '/' (no /docs prefix) or '/docs'
 *   - directory pages → index.mdx
 */
function locationToDocPath(pathname: string): string {
    let path = pathname.replace(/\/$/, '');

    // Strategy: progressively strip URL prefixes and check against
    // the peek index keys. This handles any baseUrl / routeBasePath
    // combination without needing build-time injection.
    const idx = peekIndex as Record<string, PeekRef[]>;

    // Split into segments and try from each starting point
    const segments = path.split('/').filter(Boolean);
    for (let start = 0; start < segments.length; start++) {
        const candidate = segments.slice(start).join('/');
        // Try as-is (e.g. "core/services/audit.mdx")
        if (idx[candidate + '.mdx']) return candidate + '.mdx';
        // Try as directory index (e.g. "core/services/audit/index.mdx")
        if (idx[candidate + '/index.mdx']) return candidate + '/index.mdx';
    }

    // Root page
    if (idx['index.mdx']) return 'index.mdx';

    // Fallback to legacy logic
    const docsIdx = path.indexOf('/docs');
    if (docsIdx >= 0) {
        path = path.substring(docsIdx + '/docs'.length);
    }
    if (path.startsWith('/')) path = path.substring(1);
    if (!path) return 'index.mdx';
    return path + '.mdx';
}

/**
 * Walk DOM text nodes and wrap matching resolved file references in spans.
 */
function annotatePeekRefs(container: HTMLElement, refs: PeekRef[]): void {
    const refMap = new Map<string, PeekRef>();
    for (const ref of refs) {
        refMap.set(ref.text, ref);
    }
    const sortedTexts = [...refMap.keys()].sort((a, b) => b.length - a.length);

    const escaped = sortedTexts.map((t) =>
        t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    );
    if (escaped.length === 0) return;
    const pattern = new RegExp('(' + escaped.join('|') + ')', 'g');

    const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
    const textNodes: Text[] = [];
    let node: Node | null;
    while ((node = walker.nextNode())) {
        textNodes.push(node as Text);
    }

    for (const textNode of textNodes) {
        if (textNode.parentElement?.closest('a')) continue;
        if (textNode.parentElement?.closest('.peek-link')) continue;

        const text = textNode.textContent || '';
        if (!pattern.test(text)) continue;
        pattern.lastIndex = 0;

        const frag = document.createDocumentFragment();
        let lastIndex = 0;
        let match: RegExpExecArray | null;

        while ((match = pattern.exec(text)) !== null) {
            const matchedText = match[1];
            const ref = refMap.get(matchedText);
            if (!ref) continue;

            // Skip if this match is a substring inside a longer path.
            // e.g. "content" matching inside "core/services/content/crypto.py"
            const charBefore = match.index > 0 ? text[match.index - 1] : '';
            const charAfter = text[match.index + matchedText.length] || '';
            if (!matchedText.includes('/') && (charBefore === '/' || charAfter === '/')) {
                continue;
            }

            if (match.index > lastIndex) {
                frag.appendChild(document.createTextNode(text.substring(lastIndex, match.index)));
            }

            const span = document.createElement('span');
            span.className = 'peek-link' + (ref.is_directory ? ' peek-link--directory' : '');
            span.textContent = matchedText;
            span.setAttribute('data-peek-path', ref.resolved_path);
            span.setAttribute('data-peek-dir', ref.is_directory ? '1' : '0');
            if (ref.line_number) span.setAttribute('data-peek-line', String(ref.line_number));
            span.setAttribute('tabindex', '0');
            span.setAttribute('role', 'button');
            span.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                // A6: Find nearest source line from DOM context
                const container = span.closest('.markdown') as HTMLElement;
                const contextLine = container ? _findNearestSourceLine(span, container) : 0;
                const enrichedRef = contextLine > 0 && !ref.line_number
                    ? { ...ref, line_number: contextLine }
                    : ref;
                showPeekTooltip(enrichedRef, span);
            });
            frag.appendChild(span);
            lastIndex = match.index + matchedText.length;
        }

        if (lastIndex < text.length) {
            frag.appendChild(document.createTextNode(text.substring(lastIndex)));
        }

        if (lastIndex > 0) {
            textNode.parentNode?.replaceChild(frag, textNode);
        }
    }
}

/**
 * Walk DOM text nodes and wrap unresolved file references.
 */
function annotateUnresolvedRefs(container: HTMLElement, refs: PeekRef[]): void {
    const refMap = new Map<string, PeekRef>();
    for (const ref of refs) {
        refMap.set(ref.text, ref);
    }
    const sortedTexts = [...refMap.keys()].sort((a, b) => b.length - a.length);

    const escaped = sortedTexts.map((t) =>
        t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    );
    if (escaped.length === 0) return;
    const pattern = new RegExp('(' + escaped.join('|') + ')', 'g');

    const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
    const textNodes: Text[] = [];
    let node: Node | null;
    while ((node = walker.nextNode())) {
        textNodes.push(node as Text);
    }

    for (const textNode of textNodes) {
        if (textNode.parentElement?.closest('a')) continue;
        if (textNode.parentElement?.closest('.peek-link')) continue;

        const text = textNode.textContent || '';
        if (!pattern.test(text)) continue;
        pattern.lastIndex = 0;

        const frag = document.createDocumentFragment();
        let lastIndex = 0;
        let match: RegExpExecArray | null;

        while ((match = pattern.exec(text)) !== null) {
            const matchedText = match[1];
            const ref = refMap.get(matchedText);
            if (!ref) continue;

            // Skip if substring inside a longer path
            const charBefore = match.index > 0 ? text[match.index - 1] : '';
            const charAfter = text[match.index + matchedText.length] || '';
            if (!matchedText.includes('/') && (charBefore === '/' || charAfter === '/')) {
                continue;
            }

            if (match.index > lastIndex) {
                frag.appendChild(document.createTextNode(text.substring(lastIndex, match.index)));
            }

            const span = document.createElement('span');
            span.className = 'peek-link peek-link--unresolved';
            span.textContent = matchedText;
            span.setAttribute('tabindex', '0');
            span.setAttribute('role', 'button');
            span.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                showUnresolvedTooltip(ref, span);
            });
            frag.appendChild(span);
            lastIndex = match.index + matchedText.length;
        }

        if (lastIndex < text.length) {
            frag.appendChild(document.createTextNode(text.substring(lastIndex)));
        }

        if (lastIndex > 0) {
            textNode.parentNode?.replaceChild(frag, textNode);
        }
    }
}

/**
 * Show tooltip for a resolved peek reference.
 */
function showPeekTooltip(ref: PeekRef, anchorEl: HTMLElement): void {
    _dismissPeekTooltip();

    const tooltip = document.createElement('div');
    tooltip.className = 'peek-tooltip';

    const icon = ref.is_directory ? '📁' : '📄';
    const pathDisplay = ref.resolved_path + (ref.line_number ? ':' + ref.line_number : '');

    // File type info
    const ext = !ref.is_directory && ref.resolved_path.includes('.')
        ? '.' + ref.resolved_path.split('.').pop()
        : '';
    const parentDir = ref.resolved_path.substring(0, ref.resolved_path.lastIndexOf('/')) || '/';
    const dirName = ref.is_directory ? ref.resolved_path.split('/').filter(Boolean).pop() || '' : '';

    // NOTE: All URLs are resolved at click time via _resolveAction / _peekMode().
    // No pre-computed href variables needed here.

    // ── Info row (type tag + context) ──
    let infoHtml = '<div class="peek-tooltip__info">';
    if (ref.is_directory) {
        infoHtml += '<span class="peek-tooltip__tag peek-tooltip__tag--dir">Directory</span>';
        infoHtml += `<span class="peek-tooltip__context">${_esc(dirName)}</span>`;
    } else {
        if (ext) {
            infoHtml += `<span class="peek-tooltip__tag">${_esc(ext)}</span>`;
        }
        if (ref.line_number) {
            infoHtml += `<span class="peek-tooltip__context">Line ${ref.line_number}</span>`;
        }
    }
    infoHtml += '</div>';

    // ── Action buttons (mode-aware labels) ──
    const mode = _peekMode();
    const target = mode === 'dev' ? 'Vault' : 'GitHub';
    let actionsHtml = '<div class="peek-tooltip__actions">';

    // Primary: Open Page if internal doc exists
    if (ref.doc_url) {
        actionsHtml += '<button class="peek-tooltip__btn peek-tooltip__btn--primary" data-action="navigate">📖 Open Page</button>';
    }

    // Preview always available (inline, no external nav)
    actionsHtml += `<button class="peek-tooltip__btn${ref.doc_url ? '' : ' peek-tooltip__btn--primary'}" data-action="preview">👁 Preview</button>`;

    // Open: dev → Vault @preview, live → GitHub blob
    actionsHtml += `<button class="peek-tooltip__btn" data-action="open">${ref.is_directory ? '📂' : '📄'} Open in ${target}</button>`;

    // Edit (files only)
    if (!ref.is_directory) {
        actionsHtml += `<button class="peek-tooltip__btn" data-action="edit">✏️ Edit in ${target}</button>`;
    }

    // Directory-specific: Browse Docs (if has doc_url — equivalent of Smart browse)
    if (ref.is_directory && ref.doc_url) {
        actionsHtml += `<button class="peek-tooltip__btn" data-action="browse-docs">📖 Browse Docs</button>`;
    }

    // New Tab
    actionsHtml += `<button class="peek-tooltip__btn" data-action="newtab">↗ New Tab (${target})</button>`;

    actionsHtml += '</div>';

    // ── Assemble tooltip ──
    tooltip.innerHTML = `
        <div class="peek-tooltip__header">
            <span class="peek-tooltip__icon">${icon}</span>
            <span class="peek-tooltip__path">${_esc(pathDisplay)}</span>
            <button class="peek-tooltip__close" title="Dismiss">✕</button>
        </div>
        ${infoHtml}
        ${_renderOutline(ref.outline, ref)}
        ${actionsHtml}
    `;

    // ── Mode-aware action resolver ──
    const _resolveAction = (action: string): void => {
        const mode = _peekMode();
        const parentDir = ref.resolved_path.substring(0, ref.resolved_path.lastIndexOf('/'));
        const docPageHref = ref.doc_url ? BASE_URL + ref.doc_url : '';

        if (action === 'navigate') {
            _dismissPeekTooltip();
            if (docPageHref) {
                window.location.href = docPageHref;
            }
        } else if (action === 'preview') {
            _dismissPeekTooltip();
            _openPeekPreview(ref);
        } else if (action === 'open') {
            _dismissPeekTooltip();
            if (mode === 'dev') {
                // Directories → folder browser; files → preview
                if (ref.is_directory) {
                    _openInAdmin(`#content/docs/${ref.resolved_path}`);
                } else {
                    _openInAdmin(`#content/docs/${ref.resolved_path}@preview`);
                }
            } else if (REPO_URL) {
                const ghPath = ref.is_directory ? 'tree' : 'blob';
                window.open(`${REPO_URL}/${ghPath}/main/${ref.resolved_path}`, '_blank');
            }
        } else if (action === 'edit') {
            _dismissPeekTooltip();
            if (mode === 'dev') {
                _openInAdmin(`#content/docs/${ref.resolved_path}@edit`);
            } else if (REPO_URL) {
                window.open(`${REPO_URL}/edit/main/${ref.resolved_path}`, '_blank');
            }
        } else if (action === 'browse') {
            _dismissPeekTooltip();
            if (mode === 'dev') {
                _openInAdmin(`#content/docs/${parentDir || ref.resolved_path}`);
            } else if (REPO_URL) {
                window.open(`${REPO_URL}/tree/main/${parentDir || ref.resolved_path}`, '_blank');
            }
        } else if (action === 'newtab') {
            _dismissPeekTooltip();
            if (docPageHref) {
                window.open(docPageHref, '_blank');
            } else if (mode === 'dev') {
                if (ref.is_directory) {
                    _openInAdmin(`#content/docs/${ref.resolved_path}`);
                } else {
                    _openInAdmin(`#content/docs/${ref.resolved_path}@preview`);
                }
            } else if (REPO_URL) {
                const ghPath = ref.is_directory ? 'tree' : 'blob';
                window.open(`${REPO_URL}/${ghPath}/main/${ref.resolved_path}`, '_blank');
            }
        } else if (action === 'browse-docs') {
            // Equivalent of Content Vault's Smart Browse
            _dismissPeekTooltip();
            if (docPageHref) {
                window.location.href = docPageHref;
            }
        }
    };

    // Wire main action buttons
    tooltip.querySelectorAll('.peek-tooltip__actions [data-action]').forEach((btn) => {
        (btn as HTMLElement).addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            const action = (btn as HTMLElement).dataset.action!;

            _resolveAction(action);
        });
    });

    // Wire per-row outline action buttons (line-aware)
    tooltip.querySelectorAll('.peek-outline-act').forEach((btn) => {
        (btn as HTMLElement).addEventListener('click', (e) => {
            e.stopPropagation();
            const action = (btn as HTMLElement).dataset.action!;
            const line = parseInt((btn as HTMLElement).dataset.line || '0', 10);
            const mode = _peekMode();
            const parentDir = ref.resolved_path.substring(0, ref.resolved_path.lastIndexOf('/'));

            _dismissPeekTooltip();
            if (action === 'preview') {
                const previewRef: PeekRef = { ...ref, line_number: line || ref.line_number };
                _openPeekPreview(previewRef);
            } else if (action === 'open') {
                const lineHash = line > 0 ? '#L' + line : '';
                if (ref.doc_url) {
                    // File is a page in this site — navigate in-tab (SPA)
                    const headingText = (btn.closest('.peek-tooltip__outline-row') as HTMLElement)
                        ?.dataset.headingText || '';
                    const anchor = headingText
                        ? '#' + headingText.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '')
                        : '';
                    window.location.href = BASE_URL + ref.doc_url + anchor;
                } else if (mode === 'dev') {
                    _openInAdmin(`#content/docs/${ref.resolved_path}@preview` + (line > 0 ? ':' + line : ''));
                } else if (REPO_URL) {
                    window.open(`${REPO_URL}/blob/main/${ref.resolved_path}${lineHash}`, '_blank');
                }
            } else if (action === 'browse') {
                if (mode === 'dev') {
                    _openInAdmin(`#content/docs/${parentDir || ref.resolved_path}`);
                } else if (REPO_URL) {
                    window.open(`${REPO_URL}/tree/main/${parentDir || ref.resolved_path}`, '_blank');
                }
            } else if (action === 'newtab') {
                const lineHash = line > 0 ? '#L' + line : '';
                if (ref.doc_url) {
                    window.open(BASE_URL + ref.doc_url, '_blank');
                } else if (mode === 'dev') {
                    _openInAdmin(`#content/docs/${ref.resolved_path}@preview` + (line > 0 ? ':' + line : ''));
                } else if (REPO_URL) {
                    window.open(`${REPO_URL}/blob/main/${ref.resolved_path}${lineHash}`, '_blank');
                }
            }
        });
    });

    // Wire clickable outline text (navigate to doc page with anchor or open preview at line)
    tooltip.querySelectorAll('.peek-outline-text').forEach((textEl) => {
        (textEl as HTMLElement).addEventListener('click', (e) => {
            e.stopPropagation();
            const row = (textEl as HTMLElement).closest('.peek-tooltip__outline-row') as HTMLElement;
            if (!row) return;
            const headingText = row.dataset.headingText || '';
            const line = parseInt(row.dataset.line || '0', 10);

            _dismissPeekTooltip();
            const isMarkdown = /\.(md|mdx)$/i.test(ref.resolved_path);
            if (ref.doc_url && headingText && isMarkdown) {
                // Navigate to doc page with heading anchor (markdown files only)
                const anchor = headingText.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
                window.location.href = BASE_URL + ref.doc_url + '#' + anchor;
            } else {
                // Code files: open preview at that line
                const previewRef: PeekRef = { ...ref, line_number: line || ref.line_number };
                _openPeekPreview(previewRef);
            }
        });
    });

    _wireTooltip(tooltip, anchorEl);

    // B4: Async outline fallback — if no outline in peek-index, fetch headings
    const outlineEl = tooltip.querySelector('[data-peek-outline]') as HTMLElement | null;
    if (outlineEl && (!ref.outline || ref.outline.length === 0)) {
        _peekFetchOutlineAsync(outlineEl, ref, tooltip, anchorEl);
    }
}


/**
 * Show tooltip for an unresolved reference.
 */
function showUnresolvedTooltip(ref: PeekRef, anchorEl: HTMLElement): void {
    _dismissPeekTooltip();

    const tooltip = document.createElement('div');
    tooltip.className = 'peek-tooltip';

    tooltip.innerHTML = `
        <div class="peek-tooltip__header">
            <span class="peek-tooltip__icon">⚠️</span>
            <span class="peek-tooltip__path">${_esc(ref.text)}</span>
            <button class="peek-tooltip__close" title="Dismiss">✕</button>
        </div>
        <div class="peek-tooltip__label" style="color: var(--ifm-color-warning-dark, #ffb74d)">Not found in project</div>
    `;

    _wireTooltip(tooltip, anchorEl);
}

/**
 * Shared tooltip wiring: close button, positioning, dismiss handlers.
 */
function _wireTooltip(tooltip: HTMLElement, anchorEl: HTMLElement): void {
    tooltip.querySelector('.peek-tooltip__close')!.addEventListener('click', (e) => {
        e.stopPropagation();
        _dismissPeekTooltip();
    });

    document.body.appendChild(tooltip);
    _peekTooltipEl = tooltip;

    // Position near anchor
    _peekPositionTooltip(tooltip, anchorEl);

    // Dismiss on outside click
    setTimeout(() => {
        const outsideHandler = (e: MouseEvent) => {
            if (_peekTooltipEl && !_peekTooltipEl.contains(e.target as Node)) {
                _dismissPeekTooltip();
                document.removeEventListener('click', outsideHandler);
            }
        };
        document.addEventListener('click', outsideHandler);
    }, 50);

    // Dismiss on Escape
    const escHandler = (e: KeyboardEvent) => {
        if (e.key === 'Escape') {
            _dismissPeekTooltip();
            document.removeEventListener('keydown', escHandler);
        }
    };
    document.addEventListener('keydown', escHandler);
}

/**
 * Position (or re-position) a peek tooltip near its anchor element.
 * Exact match of Content Vault's _peekPositionTooltip.
 */
function _peekPositionTooltip(tooltip: HTMLElement, anchorEl: HTMLElement): void {
    const rect = anchorEl.getBoundingClientRect();
    const tooltipRect = tooltip.getBoundingClientRect();
    const viewH = window.innerHeight;
    const viewW = window.innerWidth;

    let top = rect.bottom + 6;
    let left = rect.left;

    // Flip above if not enough space below
    if (top + tooltipRect.height > viewH - 10) {
        top = rect.top - tooltipRect.height - 6;
    }
    // Keep within viewport horizontally
    if (left + tooltipRect.width > viewW - 10) {
        left = viewW - tooltipRect.width - 10;
    }
    if (left < 10) left = 10;

    tooltip.style.top = top + 'px';
    tooltip.style.left = left + 'px';
    tooltip.style.opacity = '1';
    tooltip.style.transform = 'translateY(0)';
}

/**
 * Find the nearest source line number from a DOM element's position.
 * Walks up ancestors and backward through siblings to find the closest
 * element with a data-source-line attribute.
 * Exact match of Content Vault's _findNearestSourceLine.
 */
function _findNearestSourceLine(element: HTMLElement, container: HTMLElement): number {
    // 1. Check the element itself and its ancestors (up to container)
    let el: HTMLElement | null = element;
    while (el && el !== container) {
        if (el.hasAttribute && el.hasAttribute('data-source-line')) {
            return parseInt(el.getAttribute('data-source-line')!, 10);
        }
        el = el.parentElement;
    }

    // 2. Walk backward through preceding siblings/elements
    el = element;
    while (el && el !== container) {
        let prev = el.previousElementSibling as HTMLElement | null;
        while (prev) {
            if (prev.hasAttribute && prev.hasAttribute('data-source-line')) {
                return parseInt(prev.getAttribute('data-source-line')!, 10);
            }
            const inner = prev.querySelectorAll ? prev.querySelectorAll('[data-source-line]') : [];
            if (inner.length > 0) {
                return parseInt((inner[inner.length - 1] as HTMLElement).getAttribute('data-source-line')!, 10);
            }
            prev = prev.previousElementSibling as HTMLElement | null;
        }
        el = el.parentElement;
    }
    return 0;
}

/**
 * Open a peek preview overlay.
 *
 * Content strategy:
 * - Internal doc page (has doc_url): fetch rendered page from the site itself
 * - Markdown files: local → admin API; published → GitHub raw + marked CDN
 * - Source code: local → admin API; published → GitHub raw + Monaco CDN
 * - Directories: tabbed README + listing view
 */
async function _openPeekPreview(ref: PeekRef): Promise<void> {
    _closePeekPreview();

    const previewPath = ref.is_directory
        ? ref.resolved_path.replace(/\/$/, '') + '/README.md'
        : ref.resolved_path;

    const icon = ref.is_directory ? '📁' : '📄';
    const pathDisplay = ref.resolved_path + (ref.line_number ? ':' + ref.line_number : '');

    // ── Create overlay ──
    const overlay = document.createElement('div');
    overlay.className = 'peek-preview-overlay';
    const _pvMode = _peekMode();
    const _pvTarget = _pvMode === 'dev' ? 'Vault' : 'GitHub';

    overlay.innerHTML = `
        <div class="peek-preview-box">
            <div class="peek-preview-header">
                <span class="peek-preview-header__icon">${icon}</span>
                <span class="peek-preview-header__path">${_esc(pathDisplay)}</span>
                ${ref.line_number ? `<span class="peek-preview-header__line">Line ${ref.line_number}</span>` : '<span class="peek-preview-header__line"></span>'}
                <button class="peek-preview-header__action" data-action="jump" title="Jump to ${_pvTarget}">\u2197 Jump to ${_pvTarget}</button>
                ${!ref.is_directory ? `<button class="peek-preview-header__action" data-action="edit" title="Edit in ${_pvTarget}">\u270f\ufe0f Edit in ${_pvTarget}</button>` : ''}
                ${ref.is_directory ? '<button class="peek-preview-header__action" data-action="open-readme" title="Open README">\ud83d\udcc4 Open README</button>' : ''}
                <button class="peek-preview-header__close" title="Close (Esc)">\u2715</button>
            </div>
            <div class="peek-preview-body">
                <div class="peek-preview-loading"><span class="peek-spinner"></span> Loading\u2026</div>
            </div>
        </div>
    `;

    // ── Close handlers ──
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) _closePeekPreviewViaHistory();
    });
    overlay.querySelector('.peek-preview-header__close')!.addEventListener('click', () => _closePeekPreviewViaHistory());

    // Wire "Open README" button for directories
    const openReadmeBtn = overlay.querySelector('[data-action="open-readme"]');
    if (openReadmeBtn && ref.is_directory) {
        openReadmeBtn.addEventListener('click', () => {
            const readmePath = ref.resolved_path.replace(/\/$/, '') + '/README.md';
            const currentLine = _peekCurrentLine || ref.line_number || 0;
            _closePeekPreview();
            const m = _peekMode();
            if (m === 'dev') {
                _openInAdmin(`#content/docs/${readmePath}@preview` + (currentLine > 0 ? ':' + currentLine : ''));
            } else if (REPO_URL) {
                window.open(`${REPO_URL}/blob/main/${readmePath}`, '_blank');
            }
        });
    }

    // Wire Jump button — resolves URL at click time via _peekMode()
    const jumpBtn = overlay.querySelector('[data-action="jump"]');
    if (jumpBtn) {
        jumpBtn.addEventListener('click', () => {
            const m = _peekMode();
            const liveLine = _peekCurrentLine || ref.line_number || 0;
            _closePeekPreview();
            if (m === 'dev') {
                _openInAdmin(`#content/docs/${ref.resolved_path}@preview` + (liveLine > 0 ? ':' + liveLine : ''));
            } else if (REPO_URL) {
                window.open(`${REPO_URL}/blob/main/${ref.resolved_path}${liveLine > 0 ? '#L' + liveLine : ''}`, '_blank');
            } else if (ref.doc_url) {
                // Fallback: navigate to docs page if no source viewer available
                window.location.href = BASE_URL + ref.doc_url;
            }
        });
    }

    // Wire Edit button — resolves URL at click time via _peekMode()
    const editBtn = overlay.querySelector('[data-action="edit"]');
    if (editBtn) {
        editBtn.addEventListener('click', () => {
            const m = _peekMode();
            const liveLine = _peekCurrentLine || ref.line_number || 0;
            _closePeekPreview();
            if (m === 'dev') {
                _openInAdmin(`#content/docs/${ref.resolved_path}@edit` + (liveLine > 0 ? ':' + liveLine : ''));
            } else if (REPO_URL) {
                window.open(`${REPO_URL}/edit/main/${ref.resolved_path}`, '_blank');
            }
        });
    }
    const escHandler = (e: KeyboardEvent) => {
        if (e.key === 'Escape') {
            _closePeekPreviewViaHistory();
            document.removeEventListener('keydown', escHandler);
        }
    };
    document.addEventListener('keydown', escHandler);

    document.body.appendChild(overlay);
    _peekPreviewEl = overlay;

    // ── History integration — Back button closes peek ──
    history.pushState({ peek: true, path: ref.resolved_path }, '', window.location.href);
    _peekHistoryPushed = true;

    const body = overlay.querySelector('.peek-preview-body') as HTMLElement;

    try {
        if (ref.is_directory) {
            await _previewDirectory(ref, body);
        } else if (ref.doc_url && _peekMode() === 'live' && /\.(md|mdx)$/i.test(ref.resolved_path)) {
            // Only show docs page preview for markdown refs that have their own page.
            // Python/source files with doc_url (ancestor match) should use source preview.
            await _previewInternalDoc(ref, body);
        } else if (_peekMode() === 'dev') {
            await _previewViaLocalAPI(previewPath, ref, body);
        } else {
            await _previewViaGitHub(previewPath, ref, body);
        }
    } catch (e: any) {
        body.innerHTML = `<div class="peek-preview-loading" style="color:var(--ifm-color-danger, #f44336)">❌ ${_esc(e.message || String(e))}</div>`;
    }
}

/** Preview a directory with tabbed README + listing view. */
async function _previewDirectory(ref: PeekRef, body: HTMLElement): Promise<void> {
    const dirPath = ref.resolved_path.replace(/\/$/, '');
    const readmePath = dirPath + '/README.md';

    let readmeHtml = '';
    let hasReadme = false;

    try {
        if (ref.doc_url) {
            const resp = await fetch(BASE_URL + ref.doc_url);
            if (resp.ok) {
                const doc = new DOMParser().parseFromString(await resp.text(), 'text/html');
                const content = doc.querySelector('.markdown');
                if (content) { readmeHtml = `<div class="markdown">${content.innerHTML}</div>`; hasReadme = true; }
            }
        } else if (IS_LOCAL) {
            const resp = await fetch(`${ADMIN_URL}/api/content/preview?path=${encodeURIComponent(readmePath)}`);
            if (resp.ok) {
                const data = await resp.json();
                readmeHtml = `<div class="markdown">${data.preview_content || _esc(data.content || '')}</div>`;
                hasReadme = true;
            }
        } else if (REPO_URL) {
            const rawBase = REPO_URL.replace('github.com', 'raw.githubusercontent.com');
            const resp = await fetch(`${rawBase}/main/${readmePath}`);
            if (resp.ok) {
                await _loadMarked();
                readmeHtml = `<div class="markdown">${(window as any).marked.parse(await resp.text())}</div>`;
                hasReadme = true;
            }
        }
    } catch { /* README not available */ }

    // Build listing from build-time dir_listing data
    const listing = (ref as any).dir_listing as Array<{ name: string; is_dir: boolean; size: number | null }> | undefined;
    let listingHtml = '<div style="padding:0.5rem 0">';
    if (!listing || listing.length === 0) {
        listingHtml += '<div style="padding:1rem;color:var(--ifm-color-content-secondary);text-align:center">📁 No listing data available</div>';
    } else {
        for (const item of listing.filter(i => i.is_dir)) {
            const itemPath = dirPath + '/' + item.name;
            listingHtml += `<div class="peek-listing-item" data-path="${_esc(itemPath)}" data-is-dir="1" style="cursor:pointer"><span>📁</span><span style="color:var(--ifm-color-primary);font-weight:500">${_esc(item.name)}</span></div>`;
        }
        for (const item of listing.filter(i => !i.is_dir)) {
            const itemPath = dirPath + '/' + item.name;
            const sz = item.size != null ? (item.size > 1024 ? (item.size / 1024).toFixed(1) + ' KB' : item.size + ' B') : '';
            listingHtml += `<div class="peek-listing-item" data-path="${_esc(itemPath)}" data-is-dir="0" style="cursor:pointer"><span>📄</span><span>${_esc(item.name)}</span>${sz ? `<span style="color:var(--ifm-color-content-secondary);font-size:0.75rem;margin-left:auto">${sz}</span>` : ''}</div>`;
        }
    }
    listingHtml += '</div>';

    const defaultTab = hasReadme ? 'readme' : 'listing';
    body.innerHTML = `
        <div class="peek-dir-tabs">
            ${hasReadme ? `<button class="peek-dir-tab${defaultTab === 'readme' ? ' active' : ''}" data-tab="readme">📖 README</button>` : ''}
            <button class="peek-dir-tab${defaultTab === 'listing' ? ' active' : ''}" data-tab="listing">📂 Listing ${listing ? `<span style="font-size:0.7rem;opacity:0.7">(${listing.length})</span>` : ''}</button>
        </div>
        <div class="peek-dir-content" data-tab-content="readme" style="display:${defaultTab === 'readme' ? 'block' : 'none'}">${readmeHtml}</div>
        <div class="peek-dir-content" data-tab-content="listing" style="display:${defaultTab === 'listing' ? 'block' : 'none'}">${listingHtml}</div>
    `;

    body.querySelectorAll('.peek-dir-tab').forEach((tab) => {
        tab.addEventListener('click', () => {
            const target = (tab as HTMLElement).dataset.tab;
            body.querySelectorAll('.peek-dir-tab').forEach((t) => t.classList.toggle('active', (t as HTMLElement).dataset.tab === target));
            body.querySelectorAll('.peek-dir-content').forEach((c) => {
                (c as HTMLElement).style.display = (c as HTMLElement).dataset.tabContent === target ? 'block' : 'none';
            });
        });
    });

    // Wire clickable listing items
    body.querySelectorAll('.peek-listing-item[data-path]').forEach((el) => {
        (el as HTMLElement).addEventListener('click', () => {
            const itemPath = (el as HTMLElement).dataset.path!;
            const isDir = (el as HTMLElement).dataset.isDir === '1';
            // Create a synthetic PeekRef for the clicked item
            const itemRef: PeekRef = {
                text: itemPath.split('/').pop() || itemPath,
                resolved_path: itemPath,
                line_number: null,
                is_directory: isDir,
                resolved: true,
            };
            _closePeekPreview();
            _openPeekPreview(itemRef);
        });
    });

    // Map headings and observe scroll in README tab
    if (hasReadme) {
        const readmeRendered = body.querySelector('[data-tab-content="readme"] .markdown') as HTMLElement;
        if (readmeRendered && _peekPreviewEl) {
            const readmeSource = await _fetchReadmeSource(readmePath);
            if (readmeSource) {
                _mapHeadingsToSourceLines(readmeRendered, readmeSource);
                _peekObserveLines(readmeRendered, body, _peekPreviewEl);
                if (ref.line_number && ref.line_number > 0) {
                    _peekScrollToLine(readmeRendered, ref.line_number, body);
                }
            }
        }
    }
}

/** Preview an internal doc page by fetching its rendered HTML from the site. */
async function _previewInternalDoc(ref: PeekRef, body: HTMLElement): Promise<void> {
    const resp = await fetch(BASE_URL + ref.doc_url);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const doc = new DOMParser().parseFromString(await resp.text(), 'text/html');
    const content = doc.querySelector('.markdown');

    if (content) {
        body.innerHTML = '';
        const rendered = document.createElement('div');
        rendered.className = 'markdown';
        rendered.innerHTML = content.innerHTML;
        body.appendChild(rendered);

        // Heading-to-source mapping + scroll observation
        if (_peekPreviewEl) {
            // Try to get the raw source for heading mapping
            const rawSource = await _fetchRawSource(ref.resolved_path);
            if (rawSource) {
                _mapHeadingsToSourceLines(rendered, rawSource);
            }
            _peekObserveLines(rendered, body, _peekPreviewEl);
            if (ref.line_number && ref.line_number > 0) {
                _peekScrollToLine(rendered, ref.line_number, body);
            }
        }
    } else {
        body.innerHTML = '<div class="peek-preview-loading" style="color:var(--ifm-color-warning-dark)">⚠️ Could not extract page content</div>';
    }
}

/** Preview via local admin API (localhost:8000). */
async function _previewViaLocalAPI(previewPath: string, ref: PeekRef, body: HTMLElement): Promise<void> {
    const resp = await fetch(`${ADMIN_URL}/api/content/preview?path=${encodeURIComponent(previewPath)}`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();

    if (data.type === 'markdown') {
        const sourceText = data.content || '';
        body.innerHTML = `<div class="markdown">${data.preview_content || _esc(data.content)}</div>`;
        const rendered = body.querySelector('.markdown') as HTMLElement;
        if (rendered && _peekPreviewEl) {
            _mapHeadingsToSourceLines(rendered, sourceText);
            _peekObserveLines(rendered, body, _peekPreviewEl);
            if (ref.line_number && ref.line_number > 0) {
                _peekScrollToLine(rendered, ref.line_number, body);
            }
        }
    } else if (data.type === 'image') {
        body.innerHTML = `<div style="text-align:center;padding:1rem"><img src="${data.url}" alt="${_esc(previewPath)}" style="max-width:100%;max-height:70vh;border-radius:8px"></div>`;
    } else if (data.type === 'binary') {
        body.innerHTML = `<div class="peek-preview-loading">📦 Binary file — cannot preview</div>`;
    } else {
        await _renderMonaco(data.content || '', previewPath, ref.line_number, body);
    }

    if (data.truncated) {
        body.insertAdjacentHTML('beforeend', `<p style="color:var(--ifm-color-warning-dark);font-size:0.8rem;padding:0.5rem">⚠️ File truncated</p>`);
    }
}

/** Preview via GitHub raw content (published site). */
async function _previewViaGitHub(previewPath: string, ref: PeekRef, body: HTMLElement): Promise<void> {
    const repoBase = REPO_URL ? REPO_URL.replace('github.com', 'raw.githubusercontent.com') : '';
    if (!repoBase) throw new Error('No repository URL configured');

    const ext = previewPath.split('.').pop()?.toLowerCase() || '';
    const imageExts = ['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp', 'ico', 'bmp'];

    // Image preview — display directly without fetching as text
    if (imageExts.includes(ext)) {
        const imgUrl = `${repoBase}/main/${previewPath}`;
        body.innerHTML = `<div style="text-align:center;padding:1rem"><img src="${imgUrl}" alt="${_esc(previewPath)}" style="max-width:100%;max-height:70vh;border-radius:8px"></div>`;
        return;
    }

    const resp = await fetch(`${repoBase}/main/${previewPath}`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const content = await resp.text();

    if (ext === 'md' || ext === 'mdx') {
        await _loadMarked();
        const sourceText = content;
        body.innerHTML = `<div class="markdown">${(window as any).marked.parse(content)}</div>`;
        const rendered = body.querySelector('.markdown') as HTMLElement;
        if (rendered && _peekPreviewEl) {
            _mapHeadingsToSourceLines(rendered, sourceText);
            _peekObserveLines(rendered, body, _peekPreviewEl);
            if (ref.line_number && ref.line_number > 0) {
                _peekScrollToLine(rendered, ref.line_number, body);
            }
        }
    } else {
        // Binary detection: check for null bytes in first 512 chars
        const sample = content.substring(0, 512);
        if (sample.includes('\0')) {
            body.innerHTML = `<div class="peek-preview-loading">📦 Binary file — cannot preview</div>`;
        } else {
            await _renderMonaco(content, previewPath, ref.line_number, body);
        }
    }
}

/** Render source code using Monaco editor (CDN). Falls back to plain <pre> if Monaco fails. */
async function _renderMonaco(content: string, filePath: string, lineNumber: number | null, body: HTMLElement): Promise<void> {
    try {
        await _loadMonaco();
    } catch {
        body.innerHTML = `<pre style="margin:0;overflow:auto;font-size:0.82rem;line-height:1.6;padding:1rem"><code>${_esc(content)}</code></pre>`;
        return;
    }

    const container = document.createElement('div');
    container.style.width = '100%';
    container.style.height = '100%';
    container.style.minHeight = '400px';
    body.innerHTML = '';
    body.appendChild(container);

    const ext = filePath.split('.').pop() || '';
    const monaco = (window as any).monaco;
    const editor = monaco.editor.create(container, {
        value: content,
        language: LANG_MAP[ext] || 'plaintext',
        theme: 'vs-dark',
        readOnly: true,
        minimap: { enabled: false },
        scrollBeyondLastLine: false,
        fontSize: 13,
        lineNumbers: 'on',
        renderLineHighlight: 'line',
        automaticLayout: true,
    });

    if (lineNumber && lineNumber > 0) {
        editor.revealLineInCenter(lineNumber);
        editor.setPosition({ lineNumber, column: 1 });
    }

    // ── Live line tracking — update header badge on scroll ──
    const lineBadge = _peekPreviewEl?.querySelector('.peek-preview-header__line') as HTMLElement | null;
    editor.onDidChangeCursorPosition((e: any) => {
        const currentLine = e.position.lineNumber;
        _peekCurrentLine = currentLine;
        if (lineBadge) {
            lineBadge.textContent = `Line ${currentLine}`;
        } else if (_peekPreviewEl) {
            // Create line badge if not present
            const closeBtn = _peekPreviewEl.querySelector('.peek-preview-header__close');
            if (closeBtn) {
                const badge = document.createElement('span');
                badge.className = 'peek-preview-header__line';
                badge.textContent = `Line ${currentLine}`;
                closeBtn.insertAdjacentElement('beforebegin', badge);
            }
        }
    });
}

// ── Heading-to-Source Mapping ──────────────────────────────────────

/**
 * Strip inline markdown formatting for heading comparison.
 * Matches Content Vault's _stripInlineMarkdown exactly.
 */
function _stripInlineMarkdown(text: string): string {
    return text
        .replace(/`([^`]*)`/g, '$1')        // `code`  → code
        .replace(/\*\*([^*]*)\*\*/g, '$1')   // **bold** → bold
        .replace(/\*([^*]*)\*/g, '$1')       // *italic* → italic
        .replace(/~~([^~]*)~~/g, '$1')       // ~~strike~~ → strike
        .replace(/<[^>]+>/g, '')             // <tags>  → remove
        .trim();
}

/**
 * Map rendered headings (h1-h6) to their source line numbers.
 * Searches the source text for the heading text and assigns
 * `data-source-line` attributes on the rendered heading elements.
 * Strips inline markdown before comparison so that headings like
 * ### `context.py` — Title match correctly.
 */
function _mapHeadingsToSourceLines(rendered: HTMLElement, sourceText: string): void {
    const headings = rendered.querySelectorAll('h1, h2, h3, h4, h5, h6');
    if (headings.length === 0) return;

    const sourceLines = sourceText.split('\n');
    let searchFrom = 0;

    headings.forEach((heading) => {
        const text = (heading.textContent || '').trim().toLowerCase();
        if (!text) return;

        // Search for a markdown heading line matching this text
        for (let i = searchFrom; i < sourceLines.length; i++) {
            const line = sourceLines[i].trim();
            const m = line.match(/^#{1,6}\s+(.+)/);
            if (m && _stripInlineMarkdown(m[1]).toLowerCase() === text) {
                (heading as HTMLElement).setAttribute('data-source-line', String(i + 1));
                searchFrom = i + 1;
                break;
            }
        }
    });
}

// ── IntersectionObserver for Line Tracking ──────────────────────────

/**
 * Set up an IntersectionObserver for heading tracking in the peek preview.
 * Tracks which heading is at the top of the scrollable body and updates
 * the header line indicator in real-time.
 */
function _peekObserveLines(rendered: HTMLElement, scrollBody: HTMLElement, overlay: HTMLElement): void {
    if (_peekLineObserver) {
        _peekLineObserver.disconnect();
        _peekLineObserver = null;
    }
    const headings = rendered.querySelectorAll('[data-source-line]');
    if (headings.length === 0) return;

    const lineEl = overlay.querySelector('.peek-preview-header__line') as HTMLElement | null;

    _peekLineObserver = new IntersectionObserver((entries) => {
        let topEntry: IntersectionObserverEntry | null = null;
        for (const entry of entries) {
            if (entry.isIntersecting) {
                if (!topEntry || entry.boundingClientRect.top < topEntry.boundingClientRect.top) {
                    topEntry = entry;
                }
            }
        }
        if (topEntry) {
            const srcLine = parseInt((topEntry.target as HTMLElement).getAttribute('data-source-line') || '0', 10);
            if (srcLine > 0) {
                // Update header line indicator
                if (lineEl) lineEl.textContent = 'Line ' + srcLine;
                // Visual: highlight tracked heading
                rendered.querySelectorAll('.peek-heading-tracked').forEach(
                    el => el.classList.remove('peek-heading-tracked')
                );
                topEntry.target.classList.add('peek-heading-tracked');
                // Store for Jump-to action
                _peekCurrentLine = srcLine;
            }
        }
    }, {
        root: scrollBody,
        rootMargin: '-5% 0px -85% 0px',
        threshold: 0,
    });

    headings.forEach(h => _peekLineObserver!.observe(h));

    // Click-to-focus handler (matches Content Vault _contentPreviewClickHandler)
    rendered.addEventListener('click', (e: Event) => {
        const target = e.target as HTMLElement;
        // Don't interfere with links or peek tooltips
        if (target.closest('a') || target.closest('.peek-link') || target.closest('.peek-tooltip')) return;

        const line = _findNearestSourceLine(target, rendered);
        if (line > 0) {
            // Highlight the owning heading
            rendered.querySelectorAll('.peek-heading-tracked').forEach(
                el => el.classList.remove('peek-heading-tracked')
            );
            const heading = rendered.querySelector(`[data-source-line="${line}"]`);
            if (heading) heading.classList.add('peek-heading-tracked');
            // Update header line indicator
            if (lineEl) lineEl.textContent = 'Line ' + line;
            _peekCurrentLine = line;
        } else {
            // Clicked before first heading
            if (lineEl) lineEl.textContent = 'Line 1';
            _peekCurrentLine = 1;
        }
    });
}

// ── Scroll to Source Line ──────────────────────────────────────────

/**
 * Scroll the peek preview body to a heading nearest the given source line.
 */
function _peekScrollToLine(rendered: HTMLElement, targetLine: number, scrollContainer: HTMLElement): void {
    if (!targetLine || targetLine <= 0) return;
    const headings = rendered.querySelectorAll('[data-source-line]');
    if (headings.length === 0) return;

    let best: Element | null = null;
    let bestDist = Infinity;

    headings.forEach(h => {
        const srcLine = parseInt((h as HTMLElement).getAttribute('data-source-line') || '0', 10);
        const dist = Math.abs(srcLine - targetLine);
        if (dist < bestDist) {
            bestDist = dist;
            best = h;
        }
    });

    if (best) {
        setTimeout(() => {
            (best as HTMLElement).scrollIntoView({ behavior: 'smooth', block: 'start' });
            // Visual highlight
            (best as HTMLElement).style.transition = 'background 0.3s';
            (best as HTMLElement).style.background = 'rgba(100, 181, 246, 0.15)';
            setTimeout(() => { (best as HTMLElement).style.background = ''; }, 2000);
        }, 200);
    }
}

// ── Raw Source Fetchers ────────────────────────────────────────────

/** Fetch raw source text for heading mapping (best-effort). */
async function _fetchRawSource(resolvedPath: string): Promise<string | null> {
    try {
        if (IS_LOCAL) {
            const resp = await fetch(`${ADMIN_URL}/api/content/preview?path=${encodeURIComponent(resolvedPath)}`);
            if (resp.ok) {
                const data = await resp.json();
                return data.content || null;
            }
        } else if (REPO_URL) {
            const rawBase = REPO_URL.replace('github.com', 'raw.githubusercontent.com');
            const resp = await fetch(`${rawBase}/main/${resolvedPath}`);
            if (resp.ok) return await resp.text();
        }
    } catch { /* best effort */ }
    return null;
}

/** Fetch raw README source for directory heading mapping. */
async function _fetchReadmeSource(readmePath: string): Promise<string | null> {
    try {
        if (IS_LOCAL) {
            const resp = await fetch(`${ADMIN_URL}/api/content/preview?path=${encodeURIComponent(readmePath)}`);
            if (resp.ok) {
                const data = await resp.json();
                return data.content || null;
            }
        } else if (REPO_URL) {
            const rawBase = REPO_URL.replace('github.com', 'raw.githubusercontent.com');
            const resp = await fetch(`${rawBase}/main/${readmePath}`);
            if (resp.ok) return await resp.text();
        }
    } catch { /* best effort */ }
    return null;
}

// ── Async Outline Fallback (B4) ───────────────────────────────────

/**
 * Fetch outline headings asynchronously when not available in peek-index.
 * Tries to extract h1/h2 from the internal doc page HTML, or from raw source.
 * On success, renders the outline and re-positions the tooltip (B8).
 */
async function _peekFetchOutlineAsync(
    outlineEl: HTMLElement,
    ref: PeekRef,
    tooltip: HTMLElement,
    anchorEl: HTMLElement,
): Promise<void> {
    try {
        let headings: OutlineItem[] | null = null;

        // Strategy 1: If ref has doc_url AND is a markdown file, fetch the rendered page headings.
        // Skip for source files — their doc_url is just the nearest ancestor, not their own page.
        if (ref.doc_url && /\.(md|mdx)$/i.test(ref.resolved_path)) {
            const resp = await fetch(BASE_URL + ref.doc_url);
            if (resp.ok) {
                const doc = new DOMParser().parseFromString(await resp.text(), 'text/html');
                const hElements = doc.querySelectorAll('.markdown h1, .markdown h2, .markdown h3');
                if (hElements.length > 0) {
                    headings = [];
                    hElements.forEach((h, idx) => {
                        const level = parseInt(h.tagName.substring(1), 10);
                        headings!.push({
                            text: (h.textContent || '').trim(),
                            line: idx + 1,
                            kind: 'heading',
                            level,
                        });
                    });
                }
            }
        }

        // Strategy 2: Fetch raw source and extract markdown headings
        if (!headings) {
            const lookupPath = ref.is_directory
                ? ref.resolved_path.replace(/\/$/, '') + '/README.md'
                : ref.resolved_path;
            const rawSource = await _fetchRawSource(lookupPath);
            if (rawSource) {
                headings = [];
                const lines = rawSource.split('\n');
                lines.forEach((line, idx) => {
                    const m = line.match(/^(#{1,3})\s+(.+)/);
                    if (m) {
                        headings!.push({
                            text: m[2].trim(),
                            line: idx + 1,
                            kind: 'heading',
                            level: m[1].length,
                        });
                    }
                });
                if (headings.length === 0) headings = null;
            }
        }

        // Check tooltip is still visible
        if (!_peekTooltipEl || _peekTooltipEl !== tooltip) return;

        if (headings && headings.length > 0) {
            const resolvedPath = ref.resolved_path;
            const parentDir = resolvedPath.substring(0, resolvedPath.lastIndexOf('/'));
            outlineEl.innerHTML = headings.map(item => {
                const isIndented = (item.level || 1) >= 2;
                const indent = isIndented ? 'padding-left:0.6rem;' : '';
                const weight = isIndented ? '' : 'font-weight:500;';
                const icon = item.level === 1 ? '▸' : '·';

                return `<div class="peek-tooltip__outline-row" style="display:flex;align-items:center;gap:0.25rem;${indent}${weight}padding:1px 0" data-line="${item.line}" data-heading-text="${_esc(item.text)}">
                    <span style="font-size:0.7rem;color:var(--ifm-color-secondary-darkest, #999);flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;cursor:pointer" class="peek-outline-text">
                        ${icon} ${_esc(item.text)}
                    </span>
                    <span class="peek-tooltip__outline-actions" style="display:flex;gap:2px;flex-shrink:0">
                        <button class="peek-outline-act" title="Preview at line ${item.line || ''}" data-action="preview" data-line="${item.line || 0}">\ud83d\udc41</button>
                        <button class="peek-outline-act" title="Open at line ${item.line || ''}" data-action="open" data-line="${item.line || 0}">\ud83d\udcc4</button>
                        ${parentDir ? '<button class="peek-outline-act" title="Browse folder" data-action="browse" data-line="0">\ud83d\udcc2</button>' : ''}
                        <button class="peek-outline-act" title="New tab" data-action="newtab" data-line="${item.line || 0}">\u2197</button>
                    </span>
                </div>`;
            }).join('');

            // Wire async outline text clicks
            outlineEl.querySelectorAll('.peek-outline-text').forEach((textEl) => {
                (textEl as HTMLElement).addEventListener('click', (e) => {
                    e.stopPropagation();
                    const row = (textEl as HTMLElement).closest('.peek-tooltip__outline-row') as HTMLElement;
                    if (!row) return;
                    const headingText = row.dataset.headingText || '';
                    const line = parseInt(row.dataset.line || '0', 10);

                    _dismissPeekTooltip();
                    if (ref.doc_url && headingText) {
                        const anchor = headingText.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
                        window.location.href = BASE_URL + ref.doc_url + '#' + anchor;
                    } else {
                        const previewRef: PeekRef = { ...ref, line_number: line || ref.line_number };
                        _openPeekPreview(previewRef);
                    }
                });
            });

            // Wire async outline action buttons
            outlineEl.querySelectorAll('.peek-outline-act').forEach((btn) => {
                (btn as HTMLElement).addEventListener('click', (e) => {
                    e.stopPropagation();
                    const action = (btn as HTMLElement).dataset.action!;
                    const line = parseInt((btn as HTMLElement).dataset.line || '0', 10);
                    const mode = _peekMode();
                    const pDir = ref.resolved_path.substring(0, ref.resolved_path.lastIndexOf('/'));

                    _dismissPeekTooltip();
                    if (action === 'preview') {
                        const previewRef: PeekRef = { ...ref, line_number: line || ref.line_number };
                        _openPeekPreview(previewRef);
                    } else if (action === 'open') {
                        if (mode === 'dev') {
                            _openInAdmin(`#content/docs/${ref.resolved_path}@preview` + (line > 0 ? ':' + line : ''));
                        } else if (REPO_URL) {
                            window.open(`${REPO_URL}/blob/main/${ref.resolved_path}${line > 0 ? '#L' + line : ''}`, '_blank');
                        }
                    } else if (action === 'browse') {
                        if (mode === 'dev') {
                            _openInAdmin(`#content/docs/${pDir || ref.resolved_path}`);
                        } else if (REPO_URL) {
                            window.open(`${REPO_URL}/tree/main/${pDir || ref.resolved_path}`, '_blank');
                        }
                    } else if (action === 'newtab') {
                        if (ref.doc_url) {
                            window.open(BASE_URL + ref.doc_url, '_blank');
                        } else if (mode === 'dev') {
                            _openInAdmin(`#content/docs/${ref.resolved_path}@preview` + (line > 0 ? ':' + line : ''));
                        } else if (REPO_URL) {
                            window.open(`${REPO_URL}/blob/main/${ref.resolved_path}${line > 0 ? '#L' + line : ''}`, '_blank');
                        }
                    }
                });
            });

            // B8: Re-position tooltip since content changed size
            _peekPositionTooltip(tooltip, anchorEl);
        } else {
            // No outline found by any strategy — show hint
            const ext = ref.resolved_path.split('.').pop()?.toLowerCase() || '';
            const hint = ext === 'py' ? 'No symbols — shim / re-export module'
                : ext === '' ? 'Empty directory'
                    : 'No outline available';
            outlineEl.innerHTML = `<div style="font-size:0.7rem;color:var(--ifm-color-content-secondary, #888);padding:2px 0;font-style:italic">${hint}</div>`;
            _peekPositionTooltip(tooltip, anchorEl);
        }
    } catch {
        // Silently ignore — outline is optional enrichment
    }
}

// ── Pending Annotation (A3) ─────────────────────────────────────

/**
 * Annotate pending references with pulsing underline.
 * Equivalent of Content Vault's _annotatePendingPeek.
 * Shows a "Resolving…" tooltip on click.
 */
function _annotatePendingPeek(container: HTMLElement, pendingTexts: string[]): void {
    if (pendingTexts.length === 0) return;

    const escaped = pendingTexts.map(t =>
        t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    );
    const pattern = new RegExp('\\b(' + escaped.join('|') + ')\\b', 'g');

    const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
    const textNodes: Text[] = [];
    let node: Node | null;
    while ((node = walker.nextNode())) {
        textNodes.push(node as Text);
    }

    for (const textNode of textNodes) {
        if (textNode.parentElement?.closest('a')) continue;
        if (textNode.parentElement?.closest('.peek-link')) continue;

        const text = textNode.textContent || '';
        if (!pattern.test(text)) continue;
        pattern.lastIndex = 0;

        const frag = document.createDocumentFragment();
        let lastIndex = 0;
        let match: RegExpExecArray | null;

        while ((match = pattern.exec(text)) !== null) {
            const matchedText = match[1];
            if (match.index > lastIndex) {
                frag.appendChild(document.createTextNode(text.substring(lastIndex, match.index)));
            }

            const span = document.createElement('span');
            span.className = 'peek-link peek-link--pending';
            span.textContent = matchedText;
            span.setAttribute('data-peek-pending', '1');
            span.setAttribute('tabindex', '0');
            span.setAttribute('role', 'button');
            span.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                _showPendingTooltip(matchedText, span);
            });
            frag.appendChild(span);
            lastIndex = match.index + matchedText.length;
        }

        if (lastIndex < text.length) {
            frag.appendChild(document.createTextNode(text.substring(lastIndex)));
        }

        if (lastIndex > 0) {
            textNode.parentNode?.replaceChild(frag, textNode);
        }
    }
}

/** Show a "Resolving…" tooltip for pending annotations. */
function _showPendingTooltip(text: string, anchorEl: HTMLElement): void {
    _dismissPeekTooltip();

    const tooltip = document.createElement('div');
    tooltip.className = 'peek-tooltip';
    tooltip.innerHTML = `
        <div class="peek-tooltip__header">
            <span class="peek-tooltip__icon">⏳</span>
            <span class="peek-tooltip__path">${_esc(text)}</span>
            <button class="peek-tooltip__close" title="Dismiss">✕</button>
        </div>
        <div class="peek-tooltip__label" style="color: var(--ifm-color-primary-lightest, #90caf9)">Resolving…</div>
    `;

    _wireTooltip(tooltip, anchorEl);
}
