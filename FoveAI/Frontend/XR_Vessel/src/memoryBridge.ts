/**
 * memoryBridge.ts — Browser Cleanse Resilience Module
 * 
 * Browsers can clear localStorage at any time (user clears data, storage pressure,
 * ITP, Incognito exit). This module:
 * 
 * 1. On boot: restores localStorage from the Memory server if keys are missing
 * 2. Periodically: backs up critical localStorage keys to the Memory server
 * 3. On change: debounced push of changed keys to the server
 * 
 * This ensures a WebXR app survives browser cleanses — the user's preferences,
 * voice settings, dashboard state, and conversation context persist across sessions.
 */

// Critical keys to back up / restore (add more as needed)
const CRITICAL_KEYS = [
    'foveai_preferred_voice',
    'foveai_double_grip_steering',
    'foveai_double_trigger_haptics',
    'foveai_dashboard_expanded',
    'foveai_active_tab',
    'foveai_privacy_mode',
    'foveai_deep_thought',
    'foveai_user_name',
    'foveai_boot_count',
    'foveai_last_session',
];

const BACKUP_ENDPOINT = '/api/memory/backup';
const RESTORE_ENDPOINT = '/api/memory/restore';
const SYNC_INTERVAL_MS = 60_000; // Backup every 60s
const DEBOUNCE_MS = 3_000; // 3s debounce on change-driven push

let _debounceTimer: ReturnType<typeof setTimeout> | null = null;
let _lastSyncTime = 0;

/**
 * Collect all critical localStorage values into a snapshot object.
 */
function collectSnapshot(): Record<string, string> {
    const snap: Record<string, string> = {};
    for (const key of CRITICAL_KEYS) {
        const val = localStorage.getItem(key);
        if (val !== null) {
            snap[key] = val;
        }
    }
    return snap;
}

/**
 * Push current localStorage snapshot to the Memory server.
 */
async function pushBackup(): Promise<void> {
    const snapshot = collectSnapshot();
    if (Object.keys(snapshot).length === 0) return;

    try {
        const resp = await fetch(BACKUP_ENDPOINT, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ source: 'xr_vessel', keys: snapshot }),
        });
        if (resp.ok) {
            _lastSyncTime = Date.now();
            console.log('[memoryBridge] Backup pushed OK');
        } else {
            console.warn('[memoryBridge] Backup failed:', resp.status);
        }
    } catch (err) {
        console.warn('[memoryBridge] Backup error:', err);
    }
}

/**
 * Restore localStorage from the Memory server.
 * Only sets keys that are currently missing (empty after browser cleanse).
 */
async function pullRestore(): Promise<boolean> {
    try {
        const resp = await fetch(RESTORE_ENDPOINT, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ source: 'xr_vessel' }),
        });
        if (!resp.ok) {
            console.warn('[memoryBridge] Restore failed:', resp.status);
            return false;
        }
        const data = await resp.json();
        const keys = data.keys || {};
        let restored = 0;
        for (const [key, value] of Object.entries(keys) as [string, string][]) {
            // Only restore if the key is currently missing (browser was cleansed)
            if (localStorage.getItem(key) === null) {
                localStorage.setItem(key, value);
                restored++;
                console.log(`[memoryBridge] Restored: ${key}`);
            }
        }
        if (restored > 0) {
            console.log(`[memoryBridge] Restored ${restored} keys from server`);
        } else {
            console.log('[memoryBridge] No keys needed restoration');
        }
        return restored > 0;
    } catch (err) {
        console.warn('[memoryBridge] Restore error:', err);
        return false;
    }
}

/**
 * Schedule a debounced backup after a localStorage change.
 */
function scheduleDebouncedBackup(): void {
    if (_debounceTimer) clearTimeout(_debounceTimer);
    _debounceTimer = setTimeout(pushBackup, DEBOUNCE_MS);
}

// --- AUTO-INIT ON IMPORT ---

// 1. On boot: try to restore from server if localStorage looks empty
(async () => {
    // Quick heuristic: if more than half of critical keys are missing, assume cleanse
    const missingCount = CRITICAL_KEYS.filter(k => localStorage.getItem(k) === null).length;
    const likelyCleansed = missingCount > CRITICAL_KEYS.length / 2;
    
    if (likelyCleansed) {
        console.log('[memoryBridge] Browser cleanse detected — restoring from server...');
        await pullRestore();
    } else {
        console.log('[memoryBridge] localStorage intact, skipping restore');
    }
})();

// 2. Periodic backup every 60s
setInterval(pushBackup, SYNC_INTERVAL_MS);

// 3. Listen for localStorage changes and debounced-push
// storage event fires when localStorage is modified from another tab/window
window.addEventListener('storage', (e) => {
    if (e.key && CRITICAL_KEYS.includes(e.key)) {
        scheduleDebouncedBackup();
    }
});

// Also hook setItem to catch same-tab changes
const _origSetItem = localStorage.setItem.bind(localStorage);
localStorage.setItem = function(key: string, value: string) {
    _origSetItem(key, value);
    if (CRITICAL_KEYS.includes(key)) {
        scheduleDebouncedBackup();
    }
};

// 4. Push backup on page unload (beforeunload)
window.addEventListener('beforeunload', () => {
    // Use sendBeacon for reliability during page unload
    const snapshot = collectSnapshot();
    if (Object.keys(snapshot).length > 0) {
        try {
            navigator.sendBeacon(BACKUP_ENDPOINT, JSON.stringify({
                source: 'xr_vessel',
                keys: snapshot,
            }));
        } catch {
            // Fallback: synchronous fetch (best effort)
            try {
                fetch(BACKUP_ENDPOINT, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ source: 'xr_vessel', keys: snapshot }),
                    keepalive: true,
                });
            } catch {}
        }
    }
});

console.log('[memoryBridge] Initialized — watching', CRITICAL_KEYS.length, 'critical keys');

export { pushBackup, pullRestore, CRITICAL_KEYS };