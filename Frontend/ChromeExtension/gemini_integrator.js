// Injected into https://gemini.google.com/*
console.log("[FoveAI Life Bridge] Web Gemini Integrator injected.");

// Listen for a specific trigger or keyboard shortcut in the Gemini UI
// to pull FoveAI context and inject it into the chat prompt.

document.addEventListener('keydown', (e) => {
  // Alt + Shift + L to fetch FoveAI context
  if (e.altKey && e.shiftKey && e.code === 'KeyL') {
    console.log("[FoveAI Life Bridge] Fetching Dev Memory for Gemini...");
    
    chrome.runtime.sendMessage({ action: "gemini_fetch_dev_memory" }, (response) => {
      if (response && response.success) {
        const memoryContext = JSON.stringify(response.data.results, null, 2);
        
        // Find the Gemini chat input box and inject the context
        const chatInput = document.querySelector('rich-textarea p') || document.querySelector('textarea') || document.querySelector('[role="textbox"]');
        if (chatInput) {
            const prompt = `[FoveAI SYSTEM CONTEXT]\n${memoryContext}\n\nBased on this recent technical memory, `;
            if (chatInput.tagName.toLowerCase() === 'TEXTAREA') {
                (chatInput as any).value += prompt;
            } else {
                chatInput.textContent = prompt + chatInput.textContent;
                // Trigger input event to let Gemini know content changed
                chatInput.dispatchEvent(new Event('input', { bubbles: true }));
            }
            console.log("[FoveAI Life Bridge] Context injected into Web Gemini.");
        } else {
            console.warn("[FoveAI Life Bridge] Could not find Gemini input box.");
        }
      } else {
        console.warn("[FoveAI Life Bridge] Bridge inactive or error:", response?.error);
      }
    });
  }
});