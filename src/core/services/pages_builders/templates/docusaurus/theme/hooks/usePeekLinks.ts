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
}

let _peekTooltipEl: HTMLElement | null = null;

function _dismissPeekTooltip(): void {
    if (_peekTooltipEl) {
        _peekTooltipEl.remove();
        _peekTooltipEl = null;
    }
}

function _esc(s: string): string {
    const div = document.createElement('div');
    div.textContent = s;
    return div.innerHTML;
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
 */
function locationToDocPath(pathname: string): string {
    let path = pathname.replace(/\/$/, '');

    const docsIdx = path.indexOf('/docs');
    if (docsIdx >= 0) {
        path = path.substring(docsIdx + '/docs'.length);
    }

    if (path.startsWith('/')) {
        path = path.substring(1);
    }

    if (!path) {
        path = 'index';
    }

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
            <div class="peek-tooltip__actions">
                ${IS_LOCAL
                ? `<a class="peek-tooltip__btn peek-tooltip__btn--primary" href="${localHref}">Browse in Vault</a>`
                : githubHref
                    ? `<a class="peek-tooltip__btn peek-tooltip__btn--primary" href="${githubHref}" target="_blank" rel="noopener">View on GitHub</a>`
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
            <div class="peek-tooltip__actions">
                ${IS_LOCAL
                ? `<a class="peek-tooltip__btn peek-tooltip__btn--primary" href="${localHref}">Open in Vault</a>`
                : ''
            }
                ${githubHref
                ? `<a class="peek-tooltip__btn${IS_LOCAL ? '' : ' peek-tooltip__btn--primary'}" href="${githubHref}" target="_blank" rel="noopener">View on GitHub</a>`
                : ''
            }
            </div>
        `;
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
