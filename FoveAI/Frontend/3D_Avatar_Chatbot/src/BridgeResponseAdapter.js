/**
 * BridgeResponseAdapter — single parsing layer for all VR client responses.
 *
 * Accepts any of:
 *   - plain string
 *   - standard OpenAI response (choices[0].message.content)
 *   - enriched OllaBridge response (x_attachments, x_avatar_directives, x_persona_context)
 *   - legacy JSON-wrapped text ({"type":"final","text":"..."})
 *
 * Returns one normalised shape:
 *   { text, attachments, avatar_directives, persona_context, meta }
 */

/**
 * @typedef {Object} NormalizedAttachment
 * @property {string} type - e.g. "image"
 * @property {string} name - display label
 * @property {string} url - URL to fetch the media
 * @property {string} [delivery] - "url" or "base64"
 * @property {string} [mime] - MIME type
 */

/**
 * @typedef {Object} NormalizedResponse
 * @property {string} text - clean display text
 * @property {NormalizedAttachment[]} attachments - media attachments
 * @property {Object} avatar_directives - per-turn directives (emotion, pose, gesture)
 * @property {Object|null} persona_context - persona context if returned inline
 * @property {Object} meta - pass-through metadata (model, usage, etc.)
 */

const _SHOW_TAG_RE = /\[show:[^\]]+\]/gi;
const _EMOTION_TAG_RE = /\[emotion:([a-zA-Z0-9_-]+)\]/i;

/**
 * Parses inline tags from text (e.g., [emotion:happy]) into directives
 * and returns the cleaned text.
 */
function _extractInlineDirectives(text, existingDirectives = {}) {
    let cleanText = text;
    const directives = { ...existingDirectives };

    const match = _EMOTION_TAG_RE.exec(text);
    if (match) {
        directives.emotion = match[1].toLowerCase();
        // Strip the tag from the spoken text
        cleanText = cleanText.replace(_EMOTION_TAG_RE, '').trim();
    }

    return { cleanText, directives };
}

/**
 * Try to unwrap legacy {"type":"final","text":"..."} wrappers.
 * @param {string} text
 * @returns {string}
 */
function _unwrapLegacyJson(text) {
    const trimmed = (text || '').trim();
    if (!trimmed.startsWith('{')) return text;
    try {
        const parsed = JSON.parse(trimmed);
        if (parsed && typeof parsed === 'object' && typeof parsed.text === 'string') {
            return parsed.text;
        }
    } catch (_) {
        // not JSON — return original
    }
    return text;
}

/**
 * Normalize any response shape into a consistent internal format.
 *
 * @param {string|Object} raw - raw response from sendMessage or sendMessageStructured
 * @returns {NormalizedResponse}
 */
function normalizeResponse(raw) {
    // Plain string
    if (typeof raw === 'string') {
        let text = _unwrapLegacyJson(raw);
        text = text
            .replace(_SHOW_TAG_RE, '')
            .replace(/\n{3,}/g, '\n\n')
            .trim();
        
        const { cleanText, directives } = _extractInlineDirectives(text);

        return {
            text: cleanText,
            attachments: [],
            avatar_directives: directives,
            persona_context: null,
            meta: {},
        };
    }

    // Object response (OpenAI or enriched)
    if (raw && typeof raw === 'object') {
        let text = '';

        // Extract text from choices array
        const choices = raw.choices || [];
        if (choices.length > 0) {
            const msg = choices[0].message || choices[0];
            text = (msg.content || msg.text || '').trim();
        } else if (typeof raw.content === 'string') {
            text = raw.content;
        } else if (typeof raw.text === 'string') {
            text = raw.text;
        } else if (raw.error) {
            const errMsg = typeof raw.error === 'string' ? raw.error : (raw.error.message || JSON.stringify(raw.error));
            text = `[Backend Error]: ${errMsg}`;
        }

        // Unwrap legacy JSON and strip [show:] if still present
        text = _unwrapLegacyJson(text);
        text = text
            .replace(_SHOW_TAG_RE, '')
            .replace(/\n{3,}/g, '\n\n')
            .trim();

        // Extract enriched fields
        const attachments = Array.isArray(raw.x_attachments) ? raw.x_attachments : [];
        let directives = raw.x_avatar_directives || raw.x_directives || {};
        const personaContext = raw.x_persona_context || null;

        // Extract inline tags like [emotion:happy] and clean the text
        const extracted = _extractInlineDirectives(text, directives);
        text = extracted.cleanText;
        directives = extracted.directives;

        return {
            text: text || '(The AI model generated an empty response. This can happen if the context limit is exceeded.)',
            attachments,
            avatar_directives: directives,
            persona_context: personaContext,
            meta: {
                model: raw.model || '',
                id: raw.id || '',
                usage: raw.usage || null,
            },
        };
    }

    // Fallback
    return {
        text: String(raw ?? ''),
        attachments: [],
        avatar_directives: {},
        persona_context: null,
        meta: {},
    };
}

// Make available globally for non-module scripts
if (typeof window !== 'undefined') {
    window.BridgeResponseAdapter = { normalizeResponse };
}
