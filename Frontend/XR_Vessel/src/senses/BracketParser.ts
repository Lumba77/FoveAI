// ╔══════════════════════════════════════════════════════════════════════╗
// ║  NODE:001 — BracketParser: Self-Puppeteering Gateway                 ║
// ║  FILE: frontend/XR_Vessel/src/senses/BracketParser.ts                ║
// ║  STATUS: ACTIVE — Core pipeline functional                           ║
// ╠══════════════════════════════════════════════════════════════════════╣
// ║  WHAT IT IS:                                                         ║
// ║  Every bracket token Jen emits passes through here FIRST, before     ║
// ║  TTS or UI display. This is the nerve centre of self-puppeteering.   ║
// ║  Strip <think> blocks, parse typed tokens, dispatch body events.     ║
// ╠══════════════════════════════════════════════════════════════════════╣
// ║  SUPPORTED TAG TYPES → what they fire:                               ║
// ║  <audio:tag>       → soundboardRegistry.play()                       ║
// ║  <emotion:state>   → foveai_emotion_trigger → AvatarManager           ║
// ║  <micro:gesture>   → foveai_micro_gesture   → AvatarManager           ║
// ║  <flavour:tag>     → soundboard soft blend (25% vol)                 ║
// ║  <request:desc>    → /api/soundboard/generate (AI audio gen)         ║
// ║  <dev:instruction> → J-Aider delegation to AGY background agent      ║
// ║  <action:cmd>      → foveai_movement_command → MovementEngine         ║
// ║  <movement:cmd>    → foveai_movement_command → MovementEngine         ║
// ║  <mode:state>      → foveai_mode_change → AvatarManager.setSocialMode ║
// ║  <self:cmd>        → handled upstream in compagent.py / BracketParser║
// ╠══════════════════════════════════════════════════════════════════════╣
// ║  KNOWN ISSUES (as of OMEGA_296):                                     ║
// ║  [OPEN] No <code:read/write/exec> bracket type yet — CodeAgency      ║
// ║         must be called from JS runtime directly, not from LLM text.  ║
// ║         Add 'code' to BRACKET_REGEX and dispatch foveai_code_action   ║
// ║         to wire a clean LLM → file system path.                      ║
// ║  [OPEN] SIMPLE_BRACKET_REGEX fallback fires for ANY <word> that      ║
// ║         doesn't match a known type. This causes false-positive audio ║
// ║         events on HTML tags in Jen's output if she quotes HTML code. ║
// ║         Fix: narrow the fallback against a known soundboard tag list.║
// ╠══════════════════════════════════════════════════════════════════════╣
// ║  NEXT STEP for any model extending self-agency:                      ║
// ║  1. Add new tag type to BRACKET_REGEX alternation                    ║
// ║  2. Handle it in the replace() callback (lines ~69-140)              ║
// ║  3. Dispatch a 'foveai_<type>_<action>' CustomEvent on window         ║
// ║  4. Wire the listener in AvatarManager.ts constructor                ║
// ║  5. Add the tag syntax to VR_CODE_AGENCY_INSTRUCTIONS in MindCore.py ║
// ╚══════════════════════════════════════════════════════════════════════╝
export interface BracketToken {
    type: 'audio' | 'emotion' | 'micro' | 'flavour' | 'request' | 'dev' | 'action' | 'movement' | 'mode' | 'code' | 'animation' | 'pad';
    tag: string;
    fullMatch: string;
    params: Record<string, string>;
}

export interface ParsedText {
    cleanText: string;
    tokens: BracketToken[];
    primaryEmotion?: string;
}

export class BracketParser {
    // ── BRACKET TAG REGEX (The Sovereign Parser) ──
    private static readonly BRACKET_REGEX = /<(audio|emotion|micro|flavour|request|dev|action|movement|mode|code|animation|gesture|pad):([^>]+)>/g;
    // Movement-specific regex: parses <movement:walk_forward 2m>, <movement:move_to x=0 y=-0.8 z=1>, etc.
    private static readonly MOVEMENT_PARAM_REGEX = /(\w+)\s*(?:(\d+(?:\.\d+)?)m?|x=(-?\d+(?:\.\d+)?)\s*y=(-?\d+(?:\.\d+)?)\s*z=(-?\d+(?:\.\d+)?))?/;
    // Known movement commands
    private static readonly MOVEMENT_COMMANDS = new Set([
        'walk_forward', 'move_to', 'steer', 'steer_on', 'steer_off', 'stop', 'move_stop',
        'sit', 'stand_up', 'lay_down', 'kneel', 'interact',
    ]);
    // Known social mode commands
    private static readonly MODE_COMMANDS = new Set([
        'coexist', 'cowork', 'coop', 'rest', 'follow', 'intimate',
    ]);
    // Known mode command in <movement:> form
    private static readonly MOVEMENT_MODE_COMMANDS = new Set([
        'sit', 'stand_up', 'lay_down', 'kneel', 'follow',
    ]);
    // Fallback: match simple bracket forms like <sigh_content>, <hmm_thoughtful>, <soft_contented_sigh>
    // that models may generate without the type prefix. These default to 'audio' type.
    private static readonly SIMPLE_BRACKET_REGEX = /<([a-z][a-z0-9_]+)>/g;
    // Known emotion keywords that should be typed as <emotion:...> not <audio:...>
    private static readonly EMOTION_KEYWORDS = new Set([
        'happy', 'sad', 'surprised', 'curious', 'content', 'neutral', 'angry', 'fearful',
        'thinking', 'relaxed', 'excited', 'confused', 'worried', 'proud', 'embarrassed',
        'grateful', 'hopeful', 'lonely', 'nostalgic', 'peaceful', 'playful', 'proud',
    ]);

    static parse(text: string): ParsedText {
        if (!text) {
            return { cleanText: '', tokens: [] };
        }
        // Pre-parse: extract and strip <think>...</think> and <thought>...</thought> tags.
        // <think> is used by Qwen/DeepSeek models; <thought> is compagent's internal monologue format.
        // Both must be stripped BEFORE TTS — these are internal only and must never be spoken.
        let thinkText = '';
        const thinkMatch = text.match(/<think>([\s\S]*?)<\/think>/i);
        const thoughtMatch = !thinkMatch && text.match(/<thought>([\s\S]*?)<\/thought>/i);
        const anyThinkMatch = thinkMatch || thoughtMatch;
        if (anyThinkMatch) {
            thinkText = anyThinkMatch[1].trim();
            // Dispatch a thought event so that ThoughtToast / VR overlay displays it!
            window.dispatchEvent(new CustomEvent('foveai_thought_stream', { detail: { thought: thinkText } }));
        }
        const workingTextRaw = text
            .replace(/<think>[\s\S]*?<\/think>/gi, '')
            .replace(/<thought>[\s\S]*?<\/thought>/gi, '');
        // Convert any parenthetical (emotion: x) / (action: y) / (gesture: z) into bracket tags
        const workingText = workingTextRaw.replace(/\((emotion|action|gesture|movement|micro|mode):\s*([^)]+)\)/gi, '<$1:$2>');
        // Strip out direct <edit_file path="...">...</edit_file> blocks from clean text
        const workingTextNoEdits = workingText.replace(/<edit_file\s+path=["\']([^"\']+)["\']\s*>[\s\S]*?<\/edit_file>/gi, '');

        // Extract and strip 432Hz life pulse chord tags: <CHORD=C_MAJ7>, <CHORD=A_MINOR>, etc.
        const chordMatch = workingTextNoEdits.match(/<CHORD=([A-Z0-9_]+)>/i);
        if (chordMatch) {
            const chord = chordMatch[1].toUpperCase();
            window.dispatchEvent(new CustomEvent('foveai_chord_trigger', { detail: { chord } }));
        }

        // Strip swarm spark, defer, and chord directives so TTS never speaks them
        const workingTextCleaned = workingTextNoEdits
            .replace(/<CHORD=[A-Z0-9_]+>/gi, '')
            .replace(/<SPARK\s+source=["\'][^"\']+["\']\s*>/gi, '')
            .replace(/<DEFER\s+to=["\'][^"\']+["\']\s*>/gi, '');

        const tokens: BracketToken[] = [];
        let primaryEmotion: string | undefined;

        // First pass: match typed bracket tokens (e.g. <audio:sigh_content>)
        const cleanText = workingTextCleaned.replace(this.BRACKET_REGEX, (fullMatch, type, tagContent) => {
            const tag = tagContent.trim();
            const params: Record<string, string> = {};

            // Parse params if present (e.g. <emotion:happy intensity=0.8>)
            // Also handle quoted string arguments (e.g. <code:search "query text">)
            const parts = tag.split(/\s+/);
            const tagName = parts[0];

            for (let i = 1; i < parts.length; i++) {
                const eqIdx = parts[i].indexOf('=');
                if (eqIdx > 0) {
                    params[parts[i].substring(0, eqIdx)] = parts[i].substring(eqIdx + 1);
                }
            }

            // Extract quoted string argument for code-type tokens
            // e.g. <code:search "my search query"> → params.query = "my search query"
            // e.g. <code:read "path/to/file.ts"> → params.path = "path/to/file.ts"
            if (type === 'code' && Object.keys(params).length === 0) {
                const quotedMatch = tag.match(/^(\w+)\s+"([^"]+)"/);
                if (quotedMatch) {
                    const actionName = quotedMatch[1];
                    const quotedValue = quotedMatch[2];
                    // Map action name to the expected param key
                    if (actionName === 'search') {
                        params['query'] = quotedValue;
                    } else if (actionName === 'read') {
                        params['path'] = quotedValue;
                    } else if (actionName === 'exec') {
                        params['command'] = quotedValue;
                    } else if (actionName === 'write') {
                        params['path'] = quotedValue;
                    } else if (actionName === 'list_dir') {
                        params['dir'] = quotedValue;
                    }
                }
            }

            // Determine final type — movement commands within action type get routed as movement
            let finalType: BracketToken['type'] = type as BracketToken['type'];
            if (type === 'action' && this.MOVEMENT_COMMANDS.has(tagName)) {
                finalType = 'movement';
            }
            if (type === 'movement') {
                finalType = 'movement';
            }
            if (type === 'mode') {
                finalType = 'mode';
            }

            tokens.push({
                type: finalType,
                tag: tagName,
                fullMatch,
                params
            });

            if (type === 'emotion' || finalType === 'emotion') {
                primaryEmotion = tagName;
            }

            return '';
        });

        // Second pass: match simple bracket forms (e.g. <sigh_content>, <soft_contented_sigh>)
        // These are model-generated tokens without a type prefix. Default to 'audio',
        // but use 'emotion' if the tag matches a known emotion keyword.
        const finalText = cleanText.replace(this.SIMPLE_BRACKET_REGEX, (fullMatch, tagContent) => {
            // Skip if this was already matched as a typed token (would have been removed)
            // Also skip HTML-like tags and common false positives
            if (/^(div|span|p|br|b|i|em|a|img|script|style|code|pre|h[1-6]|ul|ol|li|table|tr|td|th|meta|link|head|body|html|input|form|button|svg|path|circle|rect|line|text)$/.test(tagContent)) {
                return fullMatch; // Leave HTML tags intact
            }

            // Determine type: emotion keywords → emotion, everything else → audio
            let type: 'audio' | 'emotion' | 'flavour' | 'request' | 'action' = 'audio';
            if (this.EMOTION_KEYWORDS.has(tagContent.toLowerCase())) {
                type = 'emotion';
                primaryEmotion = tagContent.toLowerCase();
            }

            tokens.push({
                type,
                tag: tagContent,
                fullMatch,
                params: {}
            });

            return ''; // Remove from text like typed tokens
        });

        // --- DISPATCH: Fire window events so AvatarManager + soundboard can react ---
        for (const token of tokens) {
            if (token.type === 'emotion') {
                // SELF-PUPPETEERING BRIDGE: <emotion:happy> → Jen plays Happy animation + face
                const intensity = parseFloat(token.params['intensity'] || token.params['weight'] || '1.0');
                window.dispatchEvent(new CustomEvent('foveai_emotion_trigger', {
                    detail: { emotion: token.tag, intensity }
                }));
            } else if (token.type === 'action') {
                // SELF-PUPPETEERING BRIDGE: <action:sit> → Jen sits down
                window.dispatchEvent(new CustomEvent('foveai_action_trigger', {
                    detail: { action: token.tag, params: token.params }
                }));
            } else if (token.type === 'movement') {
                // SELF-PUPPETEERING BRIDGE: <movement:walk_forward 2m> → Jen moves her body
                // Parse movement-specific parameter formats:
                //   walk_forward 2m  → { command: 'walk_forward', params: { meters: '2' } }
                //   move_to x=0 y=-0.8 z=1 → { command: 'move_to', params: { x: '0', y: '-0.8', z: '1' } }
                //   steer_on / steer_off → { command: 'steer', params: { enabled: 'true'/'false' } }
                const movementParams: Record<string, string> = { ...token.params };

                if (token.tag === 'walk_forward') {
                    // Extract numeric value from params or the first extra param
                    const rawParams = token.fullMatch.replace(/<movement:walk_forward\s*/, '').replace(/>$/, '').trim();
                    const metersMatch = rawParams.match(/(\d+(?:\.\d+)?)/);
                    if (metersMatch) {
                        movementParams['meters'] = metersMatch[1];
                    } else {
                        movementParams['meters'] = '1'; // default 1m
                    }
                } else if (token.tag === 'move_to') {
                    const rawParams = token.fullMatch.replace(/<movement:move_to\s*/, '').replace(/>$/, '').trim();
                    const coordsMatch = rawParams.match(/x=(-?\d+(?:\.\d+)?)\s*y=(-?\d+(?:\.\d+)?)\s*z=(-?\d+(?:\.\d+)?)/);
                    if (coordsMatch) {
                        movementParams['x'] = coordsMatch[1];
                        movementParams['y'] = coordsMatch[2];
                        movementParams['z'] = coordsMatch[3];
                    }
                } else if (token.tag === 'steer_on') {
                    movementParams['command'] = 'steer';
                    movementParams['enabled'] = 'true';
                } else if (token.tag === 'steer_off') {
                    movementParams['command'] = 'steer';
                    movementParams['enabled'] = 'false';
                } else if (token.tag === 'steer') {
                    movementParams['command'] = 'steer';
                    if (!movementParams['enabled']) {
                        movementParams['enabled'] = 'true';
                    }
                }

                const command = (token.tag === 'steer_on' || token.tag === 'steer_off') ? 'steer' : token.tag;

                window.dispatchEvent(new CustomEvent('foveai_movement_command', {
                    detail: { command, params: movementParams }
                }));
            } else if (token.type === 'mode') {
                // SOCIAL MODE BRIDGE: <mode:coexist>, <mode:cowork>, <mode:follow>, etc.
                const mode = token.tag;
                window.dispatchEvent(new CustomEvent('foveai_mode_change', {
                    detail: { mode, params: token.params }
                }));
            } else if (token.type === 'micro') {
                // Micro-gesture bridge
                window.dispatchEvent(new CustomEvent('foveai_micro_gesture', {
                    detail: { gesture: token.tag, params: token.params }
                }));
            } else if (token.type === 'code') {
                // CODE AGENCY BRIDGE: <code:search "query">, <code:read path>, <code:exec cmd>
                // Routes to CodeAgency.searchCode / readFile / exec via foveai_code_action event
                window.dispatchEvent(new CustomEvent('foveai_code_action', {
                    detail: { action: token.tag, params: token.params, fullMatch: token.fullMatch }
                }));
            } else if (token.type === 'animation') {
                // ANIMATION BRIDGE: <animation:Arnold_Victory> or <animation:Dancing02_HUMANIK_769>
                window.dispatchEvent(new CustomEvent('foveai_animation_trigger', {
                    detail: { name: token.tag, params: token.params }
                }));
            } else if (token.type === 'pad') {
                // VIRTUAL GAMEPAD BRIDGE: <pad:action> → Send to python gamepad UDP/WS 8403
                window.dispatchEvent(new CustomEvent('foveai_pad_action', {
                    detail: { action: token.tag, params: token.params }
                }));
                try {
                    const ws = new WebSocket(`ws://${location.host}/ws/xrl`);
                    ws.onopen = () => {
                        ws.send(JSON.stringify({ event: 'gamepad', action: token.tag }));
                        ws.close();
                    };
                    ws.onerror = (e) => console.error("Gamepad WS connection failed on port 8403", e);
                } catch (e) {
                    console.error("Failed to construct Gamepad WebSocket", e);
                }
            }
        }

        // --- SELF-AGENCY BRIDGE: Handle <self:search "query"> tokens ---
        // The LLM is instructed to use <self:search "query"> in MindCore.py (line 242)
        // These are NOT parsed by BRACKET_REGEX, so we handle them separately
        const selfSearchRegex = /<self:search\s+"([^"]+)"\s*\/?>/g;
        let selfMatch;
        while ((selfMatch = selfSearchRegex.exec(finalText)) !== null) {
            const query = selfMatch[1];
            window.dispatchEvent(new CustomEvent('foveai_code_action', {
                detail: { action: 'search', params: { query }, fullMatch: selfMatch[0] }
            }));
        }
        // Also handle <self:search query> (without quotes)
        const selfSearchNoQuoteRegex = /<self:search\s+([^>\s]+)\s*\/?>/g;
        while ((selfMatch = selfSearchNoQuoteRegex.exec(finalText)) !== null) {
            const query = selfMatch[1];
            window.dispatchEvent(new CustomEvent('foveai_code_action', {
                detail: { action: 'search', params: { query }, fullMatch: selfMatch[0] }
            }));
        }

        // Clean up extra whitespace left by removed tags
        const trimmedClean = finalText.replace(/\s+/g, ' ').trim();

        return { cleanText: trimmedClean, tokens, primaryEmotion };
    }

    /** Strip all bracket tags and think blocks from text (for display purposes). */
    static strip(text: string): string {
        if (!text) {
            return '';
        }
        // Pre-strip think and thought blocks (internal monologue — never display to user)
        const noThink = text
            .replace(/<think>[\s\S]*?<\/think>/gi, '')
            .replace(/<thought>[\s\S]*?<\/thought>/gi, '');
        // Strip edit_file blocks completely
        const noEdits = noThink.replace(/<edit_file\s+path=["\']([^"\']+)[\"\\']\s*>[\s\S]*?<\/edit_file>/gi, '');
        // Strip swarm tags
        const noSwarm = noEdits
            .replace(/<CHORD=[A-Z0-9_]+>/gi, '')
            .replace(/<SPARK\s+source=["\'][^"\']+["\']\s*>/gi, '')
            .replace(/<DEFER\s+to=["\'][^"\']+["\']\s*>/gi, '');
        // First strip typed tokens, then simple bracket forms
        const noTyped = noSwarm.replace(this.BRACKET_REGEX, '');
        const noSimple = noTyped.replace(this.SIMPLE_BRACKET_REGEX, (fullMatch, tagContent) => {
            // Skip HTML tags
            if (/^(div|span|p|br|b|i|em|a|img|script|style|code|pre|h[1-6]|ul|ol|li|table|tr|td|th|meta|link|head|body|html|input|form|button|svg|path|circle|rect|line|text)$/.test(tagContent)) {
                return fullMatch;
            }
            return '';
        });
        return noSimple.replace(/\s+/g, ' ').trim();
    }
}
