/**
 * Tab Mesh — Service Worker
 *
 * Provides LIST_TABS for diagnostic verification.
 * Tab focus is handled by CDP via the Flask backend — the SW
 * cannot focus tabs from message events (Chrome limitation).
 *
 * Messages accepted (page → SW):
 *   LIST_TABS  { type }
 *              → return all controlled window clients
 */

// ── Lifecycle ──────────────────────────────────────────────────────

self.addEventListener('install', () => {
    // Activate immediately — don't wait for existing tabs to close
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    // Claim all existing pages so matchAll() can find them immediately
    event.waitUntil(self.clients.claim());
});

// ── Message handler ────────────────────────────────────────────────

self.addEventListener('message', (event) => {
    const msg = event.data;
    if (!msg || !msg.type) return;

    const port = event.ports && event.ports[0];

    switch (msg.type) {
        case 'LIST_TABS':
            event.waitUntil(handleListTabs(port));
            break;
    }
});

// ── LIST_TABS ──────────────────────────────────────────────────────

async function handleListTabs(port) {
    try {
        const windows = await self.clients.matchAll({
            type: 'window',
            includeUncontrolled: true,
        });

        const tabs = windows.map((client) => ({
            url: client.url,
            id: client.id,
            focused: client.focused,
            visibilityState: client.visibilityState,
        }));

        respond(port, { type: 'TAB_LIST', tabs: tabs });
    } catch (err) {
        respond(port, { type: 'TAB_LIST', tabs: [], error: err.message });
    }
}

// ── Helpers ────────────────────────────────────────────────────────

/**
 * Send a response via MessageChannel port, or silently drop if no port.
 */
function respond(port, data) {
    if (port) {
        try {
            port.postMessage(data);
        } catch (_) {
            // Port may be closed if page navigated away
        }
    }
}
