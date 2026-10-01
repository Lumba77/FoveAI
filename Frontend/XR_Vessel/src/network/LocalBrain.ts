/**
 * LocalBrain — Cloud-First Inference Router (OMEGA_173)
 *
 * WebLLM local inference has been removed. RTX 4060 (8GB VRAM) cannot run a useful
 * local LLM while also handling VR rendering, Stable Audio, and torch synthesis.
 *
 * Architecture: Direct Cloud (Ollama Cloud) → Soul Proxy (local GGUF fallback)
 * Privacy mode: OpenRouter / Venice (no data logging)
 * Deep thought: glm-5.1-cloud or equivalent reasoning model
 */

import { localMemory } from './LocalMemory';
import { localArtillery } from './LocalArtillery';

// Response quality guard — detects broken/crystallised output from under-initialized models
function isBrokenResponse(text: string): boolean {
    if (!text || !text.trim()) return true;
    const lower = text.trim().toLowerCase();
    const brokenPatterns = [
        'crystallized', 'crystalized', 'crystallising', 'crystallizing',
        'thoughts haven', 'thoughts havent', 'connection stabilising',
        'connection stabilizing', 'central mind is warming', 'try again in a moment',
        'neural link stabilising', 'neural link stabilizing',
        'waiting for the user', 'waiting for user', 'waiting to speak',
    ];
    return brokenPatterns.some(p => lower.includes(p));
}

export class LocalBrain {
    public isReady = true; // Cloud is always "ready" — no model download needed

    private activePersona: string = 'Normal';

    constructor() {
        console.log('[LocalBrain] Cloud-first mode (WebLLM removed — GPU reserved for VR/audio)');
    }

    public setPersona(persona: string) {
        this.activePersona = persona;
        console.log(`[LocalBrain] Persona: ${persona}`);
    }

    /**
     * Process user input through the cloud pipeline.
     * This is a convenience wrapper — main.ts fetchSoulFallback is the primary path.
     * Kept for backward compatibility with any code that calls localBrain.processInput().
     */
    async processInput(userInput: string, spatialContext: string): Promise<string> {
        await localMemory.addMessage('user', userInput);

        const payload = {
            model: 'auto', // Smart proxy will route this via Foveated Memory
            messages: [
                { role: 'system', content: spatialContext || 'XR Vessel Cloud' },
                { role: 'user', content: userInput }
            ],
            stream: false
        };

        const targetUrl = '/v1/chat/completions';

        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 300000);
            const response = await fetch(targetUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
                signal: controller.signal,
            });
            clearTimeout(timeoutId);

            if (response.ok) {
                const data = await response.json();
                const reply = data.choices?.[0]?.message?.content || null;
                if (reply && !isBrokenResponse(reply)) {
                    const processed = await this.interceptToolCalls(reply);
                    await localMemory.addMessage('assistant', processed);
                    return processed;
                }
            } else {
                console.warn(`[LocalBrain] Proxy returned ${response.status}:`, await response.text());
            }
        } catch (err) {
            console.warn(`[LocalBrain] Foveated proxy failed:`, err);
        }

        return 'Cloud inference unavailable. Please check your connection settings.';
    }

    /**
     * Intercept bracket-token tool calls from LLM responses.
     * Handles: [GENERATE_SOUND], [WALK], [MOVE_TO], [GESTURE], [MICRO], [EMOTION]
     */
    public async interceptToolCalls(text: string): Promise<string> {
        let responseText = text;

        // Intercept Sound (global — remove ALL occurrences)
        const soundMatches = [...responseText.matchAll(/\[GENERATE_SOUND: "(.*?)"\]/g)];
        for (const match of soundMatches) {
            localArtillery.generateSound(match[1]).then(base64 => {
                window.dispatchEvent(new CustomEvent('foveai_play_sound', { detail: base64 }));
            });
        }
        responseText = responseText.replace(/\[GENERATE_SOUND: ".*?"\]/g, '').trim();

        // Intercept Walk (global)
        const walkMatches = [...responseText.matchAll(/\[WALK: ([\d.]+)\]/g)];
        for (const match of walkMatches) {
            const meters = parseFloat(match[1]);
            (window as any).foveaiAvatar?.walkForward(meters);
        }
        responseText = responseText.replace(/\[WALK: [\d.]+\]/g, '').trim();

        // Intercept MoveTo (global)
        const moveMatches = [...responseText.matchAll(/\[MOVE_TO: ([\d.-]+), ([\d.-]+)\]/g)];
        for (const match of moveMatches) {
            const x = parseFloat(match[1]);
            const z = parseFloat(match[2]);
            (window as any).foveaiAvatar?.setDestination(new (window as any).THREE.Vector3(x, -0.8, z));
        }
        responseText = responseText.replace(/\[MOVE_TO: [\d.-]+, [\d.-]+\]/g, '').trim();

        // Intercept Gesture (global)
        const gestureMatches = [...responseText.matchAll(/\[GESTURE: "(.*?)"\]/g)];
        for (const match of gestureMatches) {
            (window as any).foveaiAvatar?.playCategory(match[1]);
        }
        responseText = responseText.replace(/\[GESTURE: ".*?"\]/g, '').trim();

        // Intercept Micro-Gesture (global)
        const microMatches = [...responseText.matchAll(/\[MICRO: "(.*?)"\]/g)];
        for (const match of microMatches) {
            (window as any).foveaiAvatar?.triggerMicroGesture(match[1]);
        }
        responseText = responseText.replace(/\[MICRO: ".*?"\]/g, '').trim();

        // Intercept Emotion (global — only last emotion wins)
        const emotionMatches = [...responseText.matchAll(/\[EMOTION: "(.*?)"\]/g)];
        if (emotionMatches.length > 0) {
            const lastEmotion = emotionMatches[emotionMatches.length - 1][1];
            (window as any).foveaiAvatar?.setEmotionalState(lastEmotion);
        }
        responseText = responseText.replace(/\[EMOTION: ".*?"\]/g, '').trim();

        return responseText;
    }
}

export const localBrain = (window as any).__FoveAI_LOCAL_BRAIN__ || new LocalBrain();
(window as any).__FoveAI_LOCAL_BRAIN__ = localBrain;