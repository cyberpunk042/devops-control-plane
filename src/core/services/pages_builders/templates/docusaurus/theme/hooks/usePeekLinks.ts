import { useEffect } from 'react';
import { useLocation } from '@docusaurus/router';

// Peek index is generated at build time by the Python pipeline.
// It maps doc-relative paths to their resolved references.
// @ts-ignore — JSON module import
import peekIndex from '@site/src/peek-index.json';

const IS_LOCAL = typeof window !== 'undefined' && window.location.hostname === 'localhost';
const REPO_URL = '__REPO_URL__';

interface PeekRef {
    text: string;
    resolved_path: string;
    line_number: number | null;
    is_directory: boolean;
    resolved?: boolean;
    outline?: string[];
}

let _peekTooltipEl: HTMLElement | null = null;
let _peekPreviewEl: HTMLElement | null = null;

function _dismissPeekTooltip(): void {
    if (_peekTooltipEl) {
        _peekTooltipEl.remove();
        _peekTooltipEl = null;
    }
}

function _closePeekPreview(): void {
    if (_peekPreviewEl) {
        _peekPreviewEl.remove();
        _peekPreviewEl = null;
    }
}

function _esc(s: string): string {
    const div = document.createElement('div');
    div.textContent = s;
    return div.innerHTML;
}

function _renderOutline(outline: string[] | undefined): string {
    if (!outline || outline.length === 0) return '';
    const items = outline
        .map((item) => `<div class="peek-tooltip__outline-item">${_esc(item)}</div>`)
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
        }, 100);

        return () => {
            clearTimeout(timer);
            _dismissPeekTooltip();
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
        if (textNode.parentElement?.closest('code')) continue;

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

    // Build link URL
    const lineAnchor = ref.line_number ? ':' + ref.line_number : '';
    const localHref = `http://localhost:8000/#content/docs/${ref.resolved_path}@preview${lineAnchor}`;
    const githubHref = REPO_URL
        ? `${REPO_URL}/blob/main/${ref.resolved_path}${ref.line_number ? '#L' + ref.line_number : ''}`
        : '';

    if (ref.is_directory) {
        tooltip.innerHTML = `
            <div class="peek-tooltip__header">
                <span class="peek-tooltip__icon">${icon}</span>
                <span class="peek-tooltip__path">${_esc(pathDisplay)}</span>
                <button class="peek-tooltip__close" title="Dismiss">✕</button>
            </div>
            <div class="peek-tooltip__label">Directory</div>
            ${_renderOutline(ref.outline)}
            <div class="peek-tooltip__actions">
                <button class="peek-tooltip__btn peek-tooltip__btn--primary" data-action="preview">👁 Preview</button>
                ${IS_LOCAL
                ? `<a class="peek-tooltip__btn" href="${localHref}">Browse in Vault</a>`
                : githubHref
                    ? `<a class="peek-tooltip__btn" href="${githubHref}" target="_blank" rel="noopener">View on GitHub</a>`
                    : ''
            }
            </div>
        `;
    } else {
        tooltip.innerHTML = `
            <div class="peek-tooltip__header">
                <span class="peek-tooltip__icon">${icon}</span>
                <span class="peek-tooltip__path">${_esc(pathDisplay)}</span>
                <button class="peek-tooltip__close" title="Dismiss">✕</button>
            </div>
            ${ref.line_number ? '<div class="peek-tooltip__label">Line ' + ref.line_number + '</div>' : ''}
            ${_renderOutline(ref.outline)}
            <div class="peek-tooltip__actions">
                <button class="peek-tooltip__btn peek-tooltip__btn--primary" data-action="preview">👁 Preview</button>
                ${IS_LOCAL
                ? `<a class="peek-tooltip__btn" href="${localHref}">Open in Vault</a>`
                : ''
            }
                ${githubHref
                ? `<a class="peek-tooltip__btn" href="${githubHref}" target="_blank" rel="noopener">View on GitHub</a>`
                : ''
            }
            </div>
        `;
    }

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
 * Local: fetches from localhost:8000 API.
 * Published: fetches raw content from GitHub.
 */
async function _openPeekPreview(ref: PeekRef): Promise<void> {
    _closePeekPreview();

    const previewPath = ref.is_directory
        ? ref.resolved_path.replace(/\/$/, '') + '/README.md'
        : ref.resolved_path;

    const icon = ref.is_directory ? '📁' : '📄';
    const pathDisplay = ref.resolved_path + (ref.line_number ? ':' + ref.line_number : '');

    // Create overlay
    const overlay = document.createElement('div');
    overlay.className = 'peek-preview-overlay';

    // Build jump URL: local → admin panel, published → GitHub blob view
    const lineAnchor = ref.line_number ? ':' + ref.line_number : '';
    const localJumpHref = `http://localhost:8000/#content/docs/${ref.resolved_path}@preview${lineAnchor}`;
    const githubBlobHref = REPO_URL
        ? `${REPO_URL}/blob/main/${ref.resolved_path}${ref.line_number ? '#L' + ref.line_number : ''}`
        : '';
    const jumpHref = IS_LOCAL ? localJumpHref : githubBlobHref;
    const jumpTarget = IS_LOCAL ? '_self' : '_blank';

    overlay.innerHTML = `
        <div class="peek-preview-box">
            <div class="peek-preview-header">
                <span class="peek-preview-header__icon">${icon}</span>
                <span class="peek-preview-header__path">${_esc(pathDisplay)}</span>
                ${ref.line_number ? `<span class="peek-preview-header__line">Line ${ref.line_number}</span>` : ''}
                ${jumpHref ? `<a class="peek-preview-header__action" href="${jumpHref}" target="${jumpTarget}" rel="noopener" title="Jump to file">↗ Jump to</a>` : ''}
                <button class="peek-preview-header__close" title="Close (Esc)">✕</button>
            </div>
            <div class="peek-preview-body">
                <div class="peek-preview-loading">Loading…</div>
            </div>
        </div>
    `;

    // Close handlers
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) _closePeekPreview();
    });
    overlay.querySelector('.peek-preview-header__close')!.addEventListener('click', () => _closePeekPreview());
    const escHandler = (e: KeyboardEvent) => {
        if (e.key === 'Escape') {
            _closePeekPreview();
            document.removeEventListener('keydown', escHandler);
        }
    };
    document.addEventListener('keydown', escHandler);

    document.body.appendChild(overlay);
    _peekPreviewEl = overlay;

    const body = overlay.querySelector('.peek-preview-body') as HTMLElement;

    try {
        let content: string;

        if (IS_LOCAL) {
            // Fetch from local admin API
            const resp = await fetch(`http://localhost:8000/api/content/preview?path=${encodeURIComponent(previewPath)}`);
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const data = await resp.json();

            if (data.type === 'markdown') {
                // Render as HTML — use preview_content if server already rendered it
                body.innerHTML = `<div class="markdown">${data.preview_content || _esc(data.content)}</div>`;
                return;
            }
            content = data.content || '';
        } else {
            // Fetch raw from GitHub
            const repoBase = REPO_URL ? REPO_URL.replace('github.com', 'raw.githubusercontent.com') : '';
            if (!repoBase) throw new Error('No repository URL configured');
            const rawUrl = `${repoBase}/main/${previewPath}`;
            const resp = await fetch(rawUrl);
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            content = await resp.text();
        }

        // Determine language from file extension for Prism highlighting
        const ext = previewPath.split('.').pop() || '';
        const langMap: Record<string, string> = {
            py: 'python', ts: 'typescript', tsx: 'tsx', js: 'javascript',
            jsx: 'jsx', yml: 'yaml', yaml: 'yaml', json: 'json',
            sh: 'bash', bash: 'bash', css: 'css', html: 'html',
            md: 'markdown', mdx: 'markdown', toml: 'toml', sql: 'sql',
            go: 'go', rs: 'rust', tf: 'hcl', Dockerfile: 'docker',
        };
        const lang = langMap[ext] || '';
        const langClass = lang ? ` language-${lang}` : '';

        body.innerHTML = `<pre style="margin:0;overflow:auto;max-height:70vh;font-size:0.82rem;line-height:1.6"><code class="${langClass}">${_esc(content)}</code></pre>`;

        // Try Prism highlighting if available
        if (typeof (window as any).Prism !== 'undefined') {
            const codeEl = body.querySelector('code');
            if (codeEl) (window as any).Prism.highlightElement(codeEl);
        }
    } catch (e: any) {
        body.innerHTML = `<div class="peek-preview-loading" style="color:var(--ifm-color-danger, #f44336)">❌ ${_esc(e.message || String(e))}</div>`;
    }
}
