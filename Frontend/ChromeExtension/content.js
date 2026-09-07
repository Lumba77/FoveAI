/**
 * FoveAI Life Bridge — Content Script (Vessel-side)
 * 
 * Injected into the FoveAI WebXR Vessel pages.
 * Bridges communication between the Vessel's LocalMemory and the Extension's background worker.
 */

console.log("[FoveAI Life Bridge] Content script injected into Vessel.");

// Listen for messages from the Extension background worker
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  switch (request.action) {
    case 'trigger_memory_sync':
      // Extension is requesting a memory sync from the Vessel
      triggerVesselMemorySync();
      sendResponse({ success: true });
      break;

    case 'sync_memory':
      // Legacy: External data incoming (calendar, email, etc.)
      dispatchExternalData(request);
      sendResponse({ success: true });
      break;

    default:
      break;
  }
});

// Listen for memory data from the Vessel page (via CustomEvent)
window.addEventListener('foveai_memory_sync_request', (event) => {
  // The Vessel is asking to sync data to the Extension
  const data = event.detail;
  if (data) {
    chrome.runtime.sendMessage({
      action: 'memory_sync',
      data: data
    }, (response) => {
      if (response?.success) {
        window.dispatchEvent(new CustomEvent('foveai_memory_sync_complete', {
          detail: { success: true, timestamp: response.timestamp }
        }));
      }
    });
  }
});

// Listen for memory restore requests from the Vessel
window.addEventListener('foveai_memory_restore_request', () => {
  chrome.runtime.sendMessage({ action: 'memory_restore' }, (response) => {
    if (response?.success && response?.data) {
      window.dispatchEvent(new CustomEvent('foveai_memory_restore_data', {
        detail: response.data
      }));
    }
  });
});

// Listen for memory status requests from the Vessel
window.addEventListener('foveai_memory_status_request', () => {
  chrome.runtime.sendMessage({ action: 'memory_status' }, (response) => {
    window.dispatchEvent(new CustomEvent('foveai_memory_status_result', {
      detail: response
    }));
  });
});

/**
 * Trigger the Vessel to send its memory data to the Extension.
 * Dispatches an event that LocalMemory.ts listens for.
 */
function triggerVesselMemorySync() {
  window.dispatchEvent(new CustomEvent('foveai_extension_sync_trigger'));
}

/**
 * Dispatch external data (calendar, email) into the Vessel.
 */
function dispatchExternalData(request) {
  window.dispatchEvent(new CustomEvent('foveai_external_memory_sync', {
    detail: request.detail || {
      source: request.source || "External",
      content: request.content || "No content"
    }
  }));
}

console.log("[FoveAI Life Bridge] Content script ready. Memory bridge active.");