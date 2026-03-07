import { useEffect } from 'react';

/**
 * Tab Mesh — Docusaurus side.
 *
 * Mirrors the admin panel's _tab_mesh.html:
 *   - Registers the Service Worker (sw.js)
 *   - Joins the BroadcastChannel mesh (devops-tab-mesh)
 *   - Broadcasts presence (join/ping/leave/state)
 *   - Handles navigate + kill + inspect messages
 *   - Exposes window.TabMesh for use by usePeekLinks
 *
 * This hook has NO dependencies and should be called once from Root.tsx.
 */

/* ── Types ─────────────────────────────────────────────────────────── */

interface MeshCapabilities {
    broadcastChannel: boolean;
    serviceWorker: boolean;
    cryptoUUID: boolean;
    visibilityAPI: boolean;
}

interface TabIdentity {
    id: string;
    tabType: 'admin' | 'site';
    siteName: string | null;
    url: string;
    hash: string;
    title: string;
    ts: number;
    alive: boolean;
}

interface RegistryEntry {
    id: string;
    tabType: string;
    siteName: string | null;
    url: string;
    hash: string;
    title: string;
    lastSeen: number;
    alive: boolean;
}

interface MeshMessage {
    type: string;
    id: string;
    ts: number;
    tabType?: string;
    siteName?: string | null;
    url?: string;
    hash?: string;
    title?: string;
    targetId?: string;
    reason?: string;
    respondingTo?: string;
    state?: Record<string, unknown>;
}

declare global {
    interface Window {
        TabMesh?: {
            id: string;
            identity: TabIdentity;
            registry: Map<string, RegistryEntry>;
            tombstones: Array<RegistryEntry & { diedAt: number; reason: string }>;
            capabilities: MeshCapabilities;
            swState: string;
            navigateTo: (targetType: string, hash: string) => void;
            kill: (targetId: string, reason?: string) => void;
            inspect: (targetId: string) => void;
        };
    }
}

/* ── Constants ─────────────────────────────────────────────────────── */

const HEARTBEAT_MS = 5000;
const PRUNE_TIMEOUT = 15000;
const TOMBSTONE_TTL = 60000;

/* ── Helpers ───────────────────────────────────────────────────────── */

function detectCaps(): MeshCapabilities {
    return {
        broadcastChannel: typeof BroadcastChannel !== 'undefined',
        serviceWorker: typeof navigator !== 'undefined' && 'serviceWorker' in navigator,
        cryptoUUID: typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function',
        visibilityAPI: typeof document !== 'undefined' && typeof document.hidden !== 'undefined',
    };
}

function generateId(caps: MeshCapabilities): string {
    if (caps.cryptoUUID) return crypto.randomUUID();
    return 'tab-' + Math.random().toString(36).substring(2, 10) +
        '-' + Date.now().toString(36);
}

function detectTabType(): 'admin' | 'site' {
    if (location.pathname.startsWith('/pages/site/')) return 'site';
    return 'admin';
}

function detectSiteName(): string | null {
    const m = location.pathname.match(/^\/pages\/site\/([^/]+)/);
    return m ? m[1] : null;
}

function computeBreadcrumb(identity: TabIdentity): string {
    if (identity.tabType === 'admin') {
        const hash = location.hash.replace('#', '');
        if (!hash) return 'Admin \u203a Dashboard';
        const parts = hash.split('/');
        const tab = parts[0];
        const rest = parts.slice(1);
        if (rest.length === 0) return 'Admin \u203a ' + capitalize(tab);

        let lastSeg = rest[rest.length - 1] || '';
        let action = '';
        if (lastSeg.includes('@')) {
            const at = lastSeg.split('@');
            lastSeg = at[0];
            action = at[1] || '';
        }
        const fileName = lastSeg.split('/').pop() || lastSeg;
        let crumb = 'Admin \u203a ' + capitalize(tab);
        if (fileName && fileName !== tab) crumb += ' \u203a ' + fileName;
        if (action) crumb += ' (' + action + ')';
        return crumb;
    }

    // Site tab
    const siteName = identity.siteName;
    const m = location.pathname.match(/^\/pages\/site\/[^/]+\/(.*)/);
    if (!m) return siteName || 'Site';
    const path = m[1].replace(/\/$/, '');
    const pathParts = path.split('/').filter(Boolean);
    if (pathParts.length === 0) return siteName || 'Site';
    const tail = pathParts.slice(-2).join(' \u203a ');
    return (siteName || 'Site') + ' \u203a ' + tail;
}

function capitalize(s: string): string {
    if (!s) return '';
    return s.charAt(0).toUpperCase() + s.slice(1);
}

/* ── The hook ──────────────────────────────────────────────────────── */

export function useTabMesh(): void {
    useEffect(() => {
        // ── Capability detection (client-side only) ────────
        const caps = detectCaps();

        // ── Identity ───────────────────────────────────────────
        const tabId = generateId(caps);
        const identity: TabIdentity = {
            id: tabId,
            tabType: detectTabType(),
            siteName: detectSiteName(),
            url: location.href,
            hash: location.hash,
            title: '',
            ts: Date.now(),
            alive: true,
        };
        identity.title = computeBreadcrumb(identity);

        // ── Registry ───────────────────────────────────────────
        const registry = new Map<string, RegistryEntry>();
        const tombstones: Array<RegistryEntry & { diedAt: number; reason: string }> = [];

        function pruneRegistry(): void {
            const now = Date.now();
            for (const [id, entry] of registry) {
                if (id === tabId) continue;
                if (now - entry.lastSeen > PRUNE_TIMEOUT) {
                    tombstones.push({ ...entry, diedAt: now, reason: 'timeout' });
                    registry.delete(id);
                }
            }
            while (tombstones.length > 0 && Date.now() - tombstones[0].diedAt > TOMBSTONE_TTL) {
                tombstones.shift();
            }
        }

        function upsertEntry(msg: MeshMessage): void {
            registry.set(msg.id, {
                id: msg.id,
                tabType: msg.tabType || 'unknown',
                siteName: msg.siteName ?? null,
                url: msg.url || '',
                hash: msg.hash || '',
                title: msg.title || '',
                lastSeen: msg.ts || Date.now(),
                alive: true,
            });
        }

        // Add self
        upsertEntry({
            type: 'self',
            id: tabId,
            tabType: identity.tabType,
            siteName: identity.siteName,
            url: identity.url,
            hash: location.hash,
            title: identity.title,
            ts: Date.now(),
        });

        // ── BroadcastChannel ───────────────────────────────────
        let bc: BroadcastChannel | null = null;

        function broadcast(msg: Record<string, unknown>): void {
            if (!bc) return;
            try { bc.postMessage(msg); } catch (_) { /* closed */ }
        }

        function sendJoin(): void {
            broadcast({
                type: 'join', id: tabId,
                tabType: identity.tabType, siteName: identity.siteName,
                url: identity.url, hash: location.hash,
                title: identity.title, ts: Date.now(),
            });
        }

        function sendRoster(): void {
            broadcast({
                type: 'roster', id: tabId,
                tabType: identity.tabType, siteName: identity.siteName,
                url: identity.url, hash: location.hash,
                title: identity.title, ts: Date.now(),
            });
        }

        function sendPing(): void {
            identity.hash = location.hash;
            identity.title = computeBreadcrumb(identity);
            broadcast({
                type: 'ping', id: tabId,
                hash: location.hash, title: identity.title,
                ts: Date.now(),
            });
            pruneRegistry();
        }

        function sendState(): void {
            identity.hash = location.hash;
            identity.title = computeBreadcrumb(identity);
            broadcast({
                type: 'state', id: tabId,
                hash: location.hash, title: identity.title,
                ts: Date.now(),
            });
        }

        function sendLeave(): void {
            broadcast({ type: 'leave', id: tabId, ts: Date.now() });
        }

        // ── Title flash ────────────────────────────────────────
        let titleFlashInterval: ReturnType<typeof setInterval> | null = null;
        let titleFlashTimeout: ReturnType<typeof setTimeout> | null = null;

        function stopTitleFlash(): void {
            if (titleFlashInterval) { clearInterval(titleFlashInterval); titleFlashInterval = null; }
            if (titleFlashTimeout) { clearTimeout(titleFlashTimeout); titleFlashTimeout = null; }
            document.title = computeBreadcrumb(identity);
            document.removeEventListener('visibilitychange', onVisibility);
        }

        function startTitleFlash(): void {
            stopTitleFlash();
            const crumb = computeBreadcrumb(identity);
            let showFlash = true;
            titleFlashInterval = setInterval(() => {
                document.title = showFlash ? '\u26a1 Navigate here' : crumb;
                showFlash = !showFlash;
            }, 800);
            titleFlashTimeout = setTimeout(stopTitleFlash, 10000);
            document.addEventListener('visibilitychange', onVisibility);
        }

        function onVisibility(): void {
            if (!document.hidden) stopTitleFlash();
        }

        // ── Kill overlay ───────────────────────────────────────
        function renderKillOverlay(reason: string): void {
            const overlay = document.createElement('div');
            overlay.id = 'tab-mesh-kill-overlay';
            overlay.style.cssText = [
                'position:fixed', 'top:0', 'left:0',
                'width:100vw', 'height:100vh',
                'z-index:999999',
                'display:flex', 'align-items:center', 'justify-content:center',
                'background:rgba(0,0,0,0.85)',
                'backdrop-filter:blur(8px)',
                '-webkit-backdrop-filter:blur(8px)',
                'pointer-events:all',
            ].join(';');

            const safeReason = reason.replace(/</g, '&lt;').replace(/>/g, '&gt;');
            overlay.innerHTML = `
                <div style="
                    background:#1a1a2e;border:1px solid #333;border-radius:12px;
                    padding:2.5rem;max-width:420px;text-align:center;
                    color:#e0e0e0;font-family:system-ui,sans-serif;
                    box-shadow:0 24px 48px rgba(0,0,0,0.4);
                ">
                    <div style="font-size:2.5rem;margin-bottom:1rem;">\u26d4</div>
                    <h2 style="margin:0 0 0.5rem;font-size:1.1rem;font-weight:600;">
                        Session Terminated
                    </h2>
                    <p style="color:#888;font-size:0.82rem;line-height:1.5;margin:0.5rem 0 1.5rem;">
                        This tab was closed remotely from the admin debug panel.
                    </p>
                    <p style="color:#888;font-size:0.72rem;margin:0 0 1.5rem;padding:0.5rem;
                        background:rgba(255,255,255,0.05);border-radius:6px;">
                        Reason: ${safeReason}
                    </p>
                    <button onclick="location.reload()" style="
                        background:#6366f1;color:#fff;border:none;border-radius:8px;
                        padding:0.6rem 1.5rem;font-size:0.85rem;font-weight:500;cursor:pointer;
                    ">\ud83d\udd04 Refresh to Reload</button>
                </div>
            `;
            document.body.appendChild(overlay);
        }

        // ── Message handler ────────────────────────────────────
        function handleMessage(e: MessageEvent): void {
            const msg = e.data as MeshMessage;
            if (!msg || !msg.type || !msg.id) return;
            if (msg.id === tabId) return;

            switch (msg.type) {
                case 'join':
                    upsertEntry(msg);
                    sendRoster();
                    break;
                case 'roster':
                    upsertEntry(msg);
                    break;
                case 'ping':
                    if (registry.has(msg.id)) {
                        const entry = registry.get(msg.id)!;
                        entry.lastSeen = msg.ts || Date.now();
                        entry.hash = msg.hash || entry.hash;
                        entry.title = msg.title || entry.title;
                    } else {
                        upsertEntry(msg);
                    }
                    break;
                case 'state':
                    if (registry.has(msg.id)) {
                        const entry = registry.get(msg.id)!;
                        entry.hash = msg.hash || entry.hash;
                        entry.title = msg.title || entry.title;
                        entry.lastSeen = msg.ts || Date.now();
                    }
                    break;
                case 'leave':
                    if (registry.has(msg.id)) {
                        const entry = registry.get(msg.id)!;
                        tombstones.push({ ...entry, diedAt: Date.now(), reason: 'closed' });
                        registry.delete(msg.id);
                    }
                    break;
                case 'navigate':
                    if (msg.targetId === tabId) {
                        // For site tabs: navigate to the URL directly
                        if (msg.hash && msg.hash.startsWith('#')) {
                            location.hash = msg.hash;
                        } else if (msg.hash) {
                            location.href = msg.hash;
                        }
                        startTitleFlash();
                        try { window.focus(); } catch (_) { /* no activation */ }
                        sendState();
                    }
                    break;
                case 'kill':
                    if (msg.targetId === tabId) {
                        identity.alive = false;
                        if (heartbeatInterval) { clearInterval(heartbeatInterval); heartbeatInterval = null; }
                        sendLeave();
                        if (bc) { try { bc.close(); } catch (_) { } bc = null; }
                        renderKillOverlay(msg.reason || 'Session terminated remotely');
                    }
                    break;
                case 'inspect':
                    if (msg.targetId === tabId) {
                        broadcast({
                            type: 'dump', id: tabId, respondingTo: msg.id,
                            state: {
                                tabType: identity.tabType, siteName: identity.siteName,
                                url: location.href, hash: location.hash,
                                title: computeBreadcrumb(identity), alive: identity.alive,
                                uptime: Math.round((Date.now() - bootTime) / 1000),
                                swState, bcReady: !!bc, caps, registrySize: registry.size,
                            },
                            ts: Date.now(),
                        });
                    }
                    break;
                case 'dump':
                    window.dispatchEvent(new CustomEvent('tab-mesh:dump', { detail: msg }));
                    break;
            }
        }

        // ── Service Worker ─────────────────────────────────────
        let swState = 'unavailable';

        /**
         * Send a message to the SW via controller.postMessage().
         * MUST use controller (not registration.active) — user activation
         * only propagates through controller, which client.focus() needs.
         */
        function swMessage(msg: Record<string, unknown>): Promise<unknown> {
            return new Promise((resolve) => {
                if (swState !== 'active' || !navigator.serviceWorker.controller) {
                    resolve(null);
                    return;
                }
                const channel = new MessageChannel();
                const timer = setTimeout(() => resolve(null), 2000);
                channel.port1.onmessage = (ev: MessageEvent) => {
                    clearTimeout(timer);
                    resolve(ev.data);
                };
                navigator.serviceWorker.controller.postMessage(msg, [channel.port2]);
            });
        }

        async function registerSW(): Promise<void> {
            if (!caps.serviceWorker) { swState = 'unavailable'; return; }
            swState = 'registering';
            try {
                const reg = await navigator.serviceWorker.register('/sw.js', { scope: '/' });
                const sw = reg.active || reg.waiting || reg.installing;
                if (sw && sw.state === 'activated') {
                    swState = 'active';
                } else if (sw) {
                    swState = sw.state;
                    sw.addEventListener('statechange', () => {
                        if (sw.state === 'activated') swState = 'active';
                    });
                }
                navigator.serviceWorker.ready.then(() => { swState = 'active'; });
            } catch (err) {
                swState = 'error';
                console.warn('[TabMesh] SW registration failed:', (err as Error).message);
            }
        }

        // ── navigateTo ─────────────────────────────────────────
        function navigateTo(targetType: string, hash: string): void {
            let matchTabType = 'admin';
            let matchSiteName: string | null = null;
            if (targetType.startsWith('site:')) {
                matchTabType = 'site';
                matchSiteName = targetType.substring(5);
            } else if (targetType === 'site') {
                matchTabType = 'site';
            }

            let target: RegistryEntry | null = null;
            let targetId: string | null = null;
            let bestLastSeen = 0;

            for (const [id, entry] of registry) {
                if (id === tabId) continue;
                if (entry.tabType !== matchTabType) continue;
                if (matchSiteName && entry.siteName !== matchSiteName) continue;
                if (entry.lastSeen > bestLastSeen) {
                    target = entry;
                    targetId = id;
                    bestLastSeen = entry.lastSeen;
                }
            }

            if (target && targetId) {
                broadcast({
                    type: 'navigate', id: tabId, targetId,
                    hash, ts: Date.now(),
                });
                const urlMatch = matchTabType === 'admin'
                    ? '/'
                    : '/pages/site/' + (matchSiteName || '');
                swMessage({
                    type: 'FOCUS_TAB', urlMatch,
                    urlExclude: location.href,
                });
            } else {
                let fullUrl: string;
                if (matchTabType === 'admin') {
                    fullUrl = location.origin + '/' + hash;
                } else {
                    fullUrl = hash.startsWith('http') ? hash : location.origin + hash;
                }
                if (swState === 'active' && navigator.serviceWorker.controller) {
                    swMessage({ type: 'OPEN_TAB', url: fullUrl });
                } else {
                    window.open(fullUrl, '_blank');
                }
            }
        }

        // ── kill / inspect ─────────────────────────────────────
        function kill(tid: string, reason?: string): void {
            broadcast({
                type: 'kill', id: tabId, targetId: tid,
                reason: reason || 'Manual kill from debug panel',
                ts: Date.now(),
            });
            if (registry.has(tid)) {
                const entry = registry.get(tid)!;
                tombstones.push({ ...entry, diedAt: Date.now(), reason: 'killed' });
                registry.delete(tid);
            }
        }

        function inspect(tid: string): void {
            broadcast({ type: 'inspect', id: tabId, targetId: tid, ts: Date.now() });
        }

        // ── Boot ───────────────────────────────────────────────
        const bootTime = Date.now();
        let heartbeatInterval: ReturnType<typeof setInterval> | null = null;

        // Register SW
        registerSW();

        // Set up BC
        if (caps.broadcastChannel) {
            try {
                bc = new BroadcastChannel('devops-tab-mesh');
                bc.onmessage = handleMessage;
            } catch (err) {
                console.warn('[TabMesh] BC failed:', (err as Error).message);
                bc = null;
            }
        }

        // Announce
        sendJoin();

        // Heartbeat
        heartbeatInterval = setInterval(sendPing, HEARTBEAT_MS);

        // Route change listeners
        window.addEventListener('hashchange', sendState);
        window.addEventListener('popstate', sendState);
        window.addEventListener('beforeunload', sendLeave);

        // Set window name for cross-tab window.open() targeting
        if (identity.tabType === 'admin') {
            window.name = 'devops-admin';
        } else if (identity.siteName) {
            window.name = 'devops-site-' + identity.siteName;
        }

        // Expose public API
        window.TabMesh = {
            id: tabId,
            identity,
            registry,
            tombstones,
            capabilities: caps,
            get swState() { return swState; },
            navigateTo,
            kill,
            inspect,
        };

        // ── Cleanup on unmount ─────────────────────────────────
        return () => {
            sendLeave();
            if (heartbeatInterval) clearInterval(heartbeatInterval);
            if (bc) { try { bc.close(); } catch (_) { } }
            stopTitleFlash();
            window.removeEventListener('hashchange', sendState);
            window.removeEventListener('popstate', sendState);
            window.removeEventListener('beforeunload', sendLeave);
            delete window.TabMesh;
        };
    }, []);
}
