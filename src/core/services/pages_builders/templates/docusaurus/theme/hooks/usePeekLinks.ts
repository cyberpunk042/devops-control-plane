import { useEffect } from 'react';
import { useLocation } from '@docusaurus/router';

// Peek index is generated at build time by the Python pipeline.
// It maps doc-relative paths to their resolved references.
// @ts-ignore — JSON module import
import peekIndex from '@site/src/peek-index.json';

const IS_LOCAL = typeof window !== 'undefined' && window.location.hostname === 'localhost';
const REPO_URL = '__REPO_URL__';
const BASE_URL = '__BASE_URL__';

interface PeekRef {
    text: string;
    resolved_path: string;
    line_number: number | null;
    is_directory: boolean;
    resolved?: boolean;
    outline?: string[];
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

function _closePeekPreview(): void {
    if (_peekPreviewEl) {
        _peekPreviewEl.remove();
        _peekPreviewEl = null;
    }
    if (_peekHistoryPushed) {
        _peekHistoryPushed = false;
    }
}

function _closePeekPreviewViaHistory(): void {
    if (_peekPreviewEl) {
        _peekPreviewEl.remove();
        _peekPreviewEl = null;
    }
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

function _renderOutline(outline: string[] | undefined, docUrl?: string): string {
    if (!outline || outline.length === 0) return '';
    const items = outline
        .map((item) => {
            if (docUrl) {
                const anchor = item.replace(/^#+\s*/, '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
                const href = BASE_URL + docUrl + '#' + anchor;
                return `<a class="peek-tooltip__outline-item peek-tooltip__outline-item--link" href="${href}">${_esc(item)}</a>`;
            }
            return `<div class="peek-tooltip__outline-item">${_esc(item)}</div>`;
        })
        .join('');
    return `<div class="peek-tooltip__outline">${items}</div>`;
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
export function usePeekLinks(): void {
    const location = useLocation();

    useEffect(() => {
        const pageKey = locationToDocPath(location.pathname);
        const allRefs: PeekRef[] | undefined = (peekIndex as Record<string, PeekRef[]>)[pageKey];
        if (!allRefs || allRefs.length === 0) return;

        // Split into resolved and unresolved
        const resolved = allRefs.filter((r) => r.resolved !== false);
        const unresolved = allRefs.filter((r) => r.resolved === false);

        // Small delay to let MDX content render
        const timer = setTimeout(() => {
            const container = document.querySelector('.markdown');
            if (!container) return;
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
        }, 100);

        return () => {
            clearTimeout(timer);
            _dismissPeekTooltip();
            // Remove annotation count badge
            const badge = document.querySelector('.peek-status');
            if (badge) badge.remove();
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
        if (textNode.parentElement?.closest('pre')) continue;

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

            if (match.index > lastIndex) {
                frag.appendChild(document.createTextNode(text.substring(lastIndex, match.index)));
            }

            const span = document.createElement('span');
            span.className = 'peek-link' + (ref.is_directory ? ' peek-link--directory' : '');
            span.textContent = matchedText;
            span.setAttribute('tabindex', '0');
            span.setAttribute('role', 'button');
            span.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                showPeekTooltip(ref, span);
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
        if (textNode.parentElement?.closest('pre')) continue;

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

    // Build URLs
    const lineAnchor = ref.line_number ? ':' + ref.line_number : '';
    const localHref = `http://localhost:8000/#content/docs/${ref.resolved_path}@preview${lineAnchor}`;
    const githubHref = REPO_URL
        ? `${REPO_URL}/blob/main/${ref.resolved_path}${ref.line_number ? '#L' + ref.line_number : ''}`
        : '';
    const githubEditHref = REPO_URL
        ? `${REPO_URL}/edit/main/${ref.resolved_path}`
        : '';
    const docPageHref = ref.doc_url ? BASE_URL + ref.doc_url : '';

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

    // ── Action buttons (context-aware) ──
    let actionsHtml = '<div class="peek-tooltip__actions">';

    if (docPageHref) {
        // Internal doc page — primary is navigate within site
        actionsHtml += `<a class="peek-tooltip__btn peek-tooltip__btn--primary" href="${docPageHref}" data-action="navigate">📖 Open Page</a>`;
        actionsHtml += '<button class="peek-tooltip__btn" data-action="preview">👁 Preview</button>';
    } else {
        // External ref — primary is preview
        actionsHtml += '<button class="peek-tooltip__btn peek-tooltip__btn--primary" data-action="preview">👁 Preview</button>';
    }

    if (IS_LOCAL) {
        actionsHtml += `<a class="peek-tooltip__btn" href="${localHref}">${ref.is_directory ? '📂 Browse' : '📄 Open'} in Vault</a>`;
    }
    if (githubHref) {
        actionsHtml += `<a class="peek-tooltip__btn" href="${githubHref}" target="_blank" rel="noopener">↗ GitHub</a>`;
    }
    if (!IS_LOCAL && githubEditHref && !ref.is_directory) {
        actionsHtml += `<a class="peek-tooltip__btn" href="${githubEditHref}" target="_blank" rel="noopener">✏️ Edit</a>`;
    }

    actionsHtml += '</div>';

    // ── Assemble tooltip ──
    tooltip.innerHTML = `
        <div class="peek-tooltip__header">
            <span class="peek-tooltip__icon">${icon}</span>
            <span class="peek-tooltip__path">${_esc(pathDisplay)}</span>
            <button class="peek-tooltip__close" title="Dismiss">✕</button>
        </div>
        ${infoHtml}
        ${_renderOutline(ref.outline, ref.doc_url)}
        ${actionsHtml}
    `;

    // Wire preview button
    const previewBtn = tooltip.querySelector('[data-action="preview"]');
    if (previewBtn) {
        previewBtn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            _dismissPeekTooltip();
            _openPeekPreview(ref);
        });
    }

    _wireTooltip(tooltip, anchorEl);
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
    const rect = anchorEl.getBoundingClientRect();
    const tooltipRect = tooltip.getBoundingClientRect();
    const viewH = window.innerHeight;
    const viewW = window.innerWidth;

    let top = rect.bottom + 6;
    let left = rect.left;

    if (top + tooltipRect.height > viewH - 10) {
        top = rect.top - tooltipRect.height - 6;
    }
    if (left + tooltipRect.width > viewW - 10) {
        left = viewW - tooltipRect.width - 10;
    }
    if (left < 10) left = 10;

    tooltip.style.top = top + 'px';
    tooltip.style.left = left + 'px';
    tooltip.style.opacity = '1';
    tooltip.style.transform = 'translateY(0)';

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

    // ── Header action URLs ──
    const docPageHref = ref.doc_url ? BASE_URL + ref.doc_url : '';
    const jumpHref = docPageHref
        ? docPageHref
        : IS_LOCAL
            ? `http://localhost:8000/#content/docs/${ref.resolved_path}@preview`
            : REPO_URL
                ? `${REPO_URL}/blob/main/${ref.resolved_path}${ref.line_number ? '#L' + ref.line_number : ''}`
                : '';
    const jumpLabel = docPageHref ? '📖 Open Page' : IS_LOCAL ? '↗ Vault' : '↗ GitHub';
    const jumpTarget = (docPageHref || IS_LOCAL) ? '_self' : '_blank';
    const editHref = IS_LOCAL
        ? `http://localhost:8000/#content/docs/${ref.resolved_path}@edit`
        : REPO_URL ? `${REPO_URL}/edit/main/${ref.resolved_path}` : '';

    // ── Create overlay ──
    const overlay = document.createElement('div');
    overlay.className = 'peek-preview-overlay';

    overlay.innerHTML = `
        <div class="peek-preview-box">
            <div class="peek-preview-header">
                <span class="peek-preview-header__icon">${icon}</span>
                <span class="peek-preview-header__path">${_esc(pathDisplay)}</span>
                ${ref.line_number ? `<span class="peek-preview-header__line">Line ${ref.line_number}</span>` : ''}
                ${jumpHref ? `<a class="peek-preview-header__action" href="${jumpHref}" target="${jumpTarget}" rel="noopener" title="${_esc(jumpLabel)}">${jumpLabel}</a>` : ''}
                ${editHref && !ref.is_directory ? `<a class="peek-preview-header__action" href="${editHref}" target="${IS_LOCAL ? '_self' : '_blank'}" rel="noopener" title="Edit">✏️ Edit</a>` : ''}
                <button class="peek-preview-header__close" title="Close (Esc)">✕</button>
            </div>
            <div class="peek-preview-body">
                <div class="peek-preview-loading"><span class="peek-spinner"></span> Loading…</div>
            </div>
        </div>
    `;

    // ── Close handlers ──
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) _closePeekPreviewViaHistory();
    });
    overlay.querySelector('.peek-preview-header__close')!.addEventListener('click', () => _closePeekPreviewViaHistory());
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
        } else if (ref.doc_url && !IS_LOCAL) {
            await _previewInternalDoc(ref, body);
        } else if (IS_LOCAL) {
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
            const resp = await fetch(`http://localhost:8000/api/content/preview?path=${encodeURIComponent(readmePath)}`);
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
            listingHtml += `<div class="peek-listing-item"><span>📁</span><span style="color:var(--ifm-color-primary);font-weight:500">${_esc(item.name)}</span></div>`;
        }
        for (const item of listing.filter(i => !i.is_dir)) {
            const sz = item.size != null ? (item.size > 1024 ? (item.size / 1024).toFixed(1) + ' KB' : item.size + ' B') : '';
            listingHtml += `<div class="peek-listing-item"><span>📄</span><span>${_esc(item.name)}</span>${sz ? `<span style="color:var(--ifm-color-content-secondary);font-size:0.75rem;margin-left:auto">${sz}</span>` : ''}</div>`;
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

        if (ref.line_number && ref.line_number > 0) {
            const headings = rendered.querySelectorAll('h1, h2, h3, h4');
            const idx = Math.min(Math.floor(ref.line_number / 20), headings.length - 1);
            if (idx >= 0 && headings[idx]) headings[idx].scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    } else {
        body.innerHTML = '<div class="peek-preview-loading" style="color:var(--ifm-color-warning-dark)">⚠️ Could not extract page content</div>';
    }
}

/** Preview via local admin API (localhost:8000). */
async function _previewViaLocalAPI(previewPath: string, ref: PeekRef, body: HTMLElement): Promise<void> {
    const resp = await fetch(`http://localhost:8000/api/content/preview?path=${encodeURIComponent(previewPath)}`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();

    if (data.type === 'markdown') {
        body.innerHTML = `<div class="markdown">${data.preview_content || _esc(data.content)}</div>`;
    } else if (data.type === 'image') {
        body.innerHTML = `<div style="text-align:center;padding:1rem"><img src="${data.url}" alt="${_esc(previewPath)}" style="max-width:100%;max-height:70vh;border-radius:8px"></div>`;
    } else {
        await _renderMonaco(data.content || '', previewPath, ref.line_number, body);
    }
}

/** Preview via GitHub raw content (published site). */
async function _previewViaGitHub(previewPath: string, ref: PeekRef, body: HTMLElement): Promise<void> {
    const repoBase = REPO_URL ? REPO_URL.replace('github.com', 'raw.githubusercontent.com') : '';
    if (!repoBase) throw new Error('No repository URL configured');
    const resp = await fetch(`${repoBase}/main/${previewPath}`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const content = await resp.text();
    const ext = previewPath.split('.').pop() || '';

    if (ext === 'md' || ext === 'mdx') {
        await _loadMarked();
        body.innerHTML = `<div class="markdown">${(window as any).marked.parse(content)}</div>`;
    } else {
        await _renderMonaco(content, previewPath, ref.line_number, body);
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




