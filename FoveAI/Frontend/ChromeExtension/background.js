/**
 * FoveAI Life Bridge — Background Service Worker
 * 
 * Upgraded from mock calendar dispatcher to full memory persistence bridge:
 * - chrome.storage.local: Stores memory snapshots (survives "Clear site data")
 * - chrome.storage.sync: Cross-device sync via Google account
 * - Offscreen document: Keeps WebVM alive when tab is closed
 * - Message handler: Routes memory_sync/memory_restore between Vessel and storage
 */

// --- Prevent Service Worker Suspension (Manifest V3) ---
let keepAliveInterval = null;
function startKeepAlive() {
  if (keepAliveInterval) return;
  keepAliveInterval = setInterval(() => {
    chrome.storage.local.get('foveai_memory_snapshot', () => {
      // Reading storage keeps the service worker alive
    });
  }, 25000); // Every 25 seconds
}
startKeepAlive();

// --- Memory Sync Handler ---
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  switch (request.action) {
    case 'memory_sync':
      handleMemorySync(request.data, sendResponse);
      return true; // async response

    case 'memory_restore':
      handleMemoryRestore(sendResponse);
      return true;

    case 'memory_status':
      handleMemoryStatus(sendResponse);
      return true;

    case 'memory_clear':
      handleMemoryClear(sendResponse);
      return true;

    default:
      break;
  }
});

/**
 * Store a memory snapshot in chrome.storage.local.
 * This survives "Clear site data" because it's extension-scoped storage.
 */
async function handleMemorySync(data, sendResponse) {
  try {
    const snapshot = {
      data: data,
      timestamp: Date.now(),
      version: 1
    };

    // Store in local storage (large capacity, same device)
    await chrome.storage.local.set({ foveai_memory_snapshot: snapshot });

    // Store lightweight metadata in sync storage (cross-device via Google account)
    // chrome.storage.sync has 100KB limit, so only metadata
    const syncMeta = {
      last_sync: Date.now(),
      message_count: data.messages?.length || 0,
      entity_count: data.entities?.length || 0,
      relation_count: data.relations?.length || 0
    };
    await chrome.storage.sync.set({ foveai_memory_meta: syncMeta });

    sendResponse({ success: true, timestamp: Date.now() });
  } catch (e) {
    console.error('[Life Bridge] Memory sync failed:', e);
    sendResponse({ success: false, error: e.message });
  }
}

/**
 * Restore the last memory snapshot from chrome.storage.local.
 */
async function handleMemoryRestore(sendResponse) {
  try {
    const result = await chrome.storage.local.get('foveai_memory_snapshot');
    
    if (result.foveai_memory_snapshot) {
      sendResponse({
        success: true,
        data: result.foveai_memory_snapshot.data,
        timestamp: result.foveai_memory_snapshot.timestamp
      });
    } else {
      sendResponse({ success: false, reason: 'No snapshot available' });
    }
  } catch (e) {
    console.error('[Life Bridge] Memory restore failed:', e);
    sendResponse({ success: false, error: e.message });
  }
}

/**
 * Return status of stored memory.
 */
async function handleMemoryStatus(sendResponse) {
  try {
    const [localResult, syncResult] = await Promise.all([
      chrome.storage.local.get('foveai_memory_snapshot'),
      chrome.storage.sync.get('foveai_memory_meta')
    ]);

    const snapshot = localResult.foveai_memory_snapshot;
    const meta = syncResult.foveai_memory_meta;

    sendResponse({
      success: true,
      has_snapshot: !!snapshot,
      snapshot_timestamp: snapshot?.timestamp || null,
      sync_meta: meta || null,
      storage_bytes: snapshot ? JSON.stringify(snapshot).length : 0
    });
  } catch (e) {
    sendResponse({ success: false, error: e.message });
  }
}

/**
 * Clear all stored memory data.
 */
async function handleMemoryClear(sendResponse) {
  try {
    await chrome.storage.local.remove('foveai_memory_snapshot');
    await chrome.storage.sync.remove('foveai_memory_meta');
    sendResponse({ success: true });
  } catch (e) {
    sendResponse({ success: false, error: e.message });
  }
}

// --- Content Script Message Relay ---
// Allow content scripts to relay messages from the Vessel page
chrome.runtime.onConnect.addListener((port) => {
  port.onMessage.addListener((msg) => {
    if (msg.action === 'memory_sync' || msg.action === 'memory_restore') {
      // Relay to our own handler
      chrome.runtime.sendMessage(msg, (response) => {
        port.postMessage(response);
      });
    }
  });
});

// --- Periodic Auto-Sync Trigger ---
// Check if the Vessel tab is open and request a memory sync every 60 seconds
setInterval(async () => {
  try {
    const tabs = await chrome.tabs.query({ url: ['http://localhost:*/*', 'https://foveai.1um6a.se/*'] });
    if (tabs.length > 0) {
      // Vessel is open — request a memory sync from the content script
      for (const tab of tabs) {
        try {
          // Must await the Promise — chrome.tabs.sendMessage returns a Promise in MV3
          // Without await, the rejection is unhandled and bubbles to global error handler
          await chrome.tabs.sendMessage(tab.id, { action: 'trigger_memory_sync' }).catch(() => {});
        } catch (e) {
          // Tab may have been closed — "Receiving end does not exist" is expected
        }
      }
    }
  } catch (e) {
    // Silently ignore
  }
}, 60000);

console.log('[FoveAI Life Bridge] Service worker active. Memory persistence ready.');