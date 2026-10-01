/**
 * ═══════════════════════════════════════════════════════
 * THE LUMAX HARNESS — Cognitive Mode Injection
 * ═══════════════════════════════════════════════════════
 *
 * This module is responsible for wrapping stateless cloud/local
 * models in a persistent, fact-injecting proxy layer.
 * 
 * It interfaces with the existing relational-memory graph to
 * extract the highest-energy facts and injects them into the
 * System Prompt based on the active Cognitive Mode.
 */

'use strict';

const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');

const HARNESS_DB_PATH = path.resolve(__dirname, '../memory_data/harness_facts.json');

// Initialize the fact vault if it doesn't exist
if (!fs.existsSync(HARNESS_DB_PATH)) {
    fs.writeFileSync(HARNESS_DB_PATH, JSON.stringify({ facts: [], rules: [], preferences: [] }, null, 2));
}

/**
 * Reads the current harness facts from disk.
 */
function getHarnessData() {
    try {
        return JSON.parse(fs.readFileSync(HARNESS_DB_PATH, 'utf8'));
    } catch (err) {
        return { facts: [], rules: [], preferences: [] };
    }
}

/**
 * Saves harness facts to disk.
 */
function saveHarnessData(data) {
    fs.writeFileSync(HARNESS_DB_PATH, JSON.stringify(data, null, 2));
}

const fetch = require('node-fetch');

/**
 * Background auto-distillation: Extracts permanent facts from a raw chat log.
 * Instructs the smart-router to auto-translate Swedish (or any lang) into English facts.
 * @param {string} rawChatText - The raw text of the recent conversation
 */
async function extractFacts(rawChatText) {
    console.log('[LUMAX Harness] Auto-distillation triggered in background.');
    
    // We use the local LM Studio endpoint (7272) and the user's custom smart-router model.
    const url = 'http://127.0.0.1:7272/v1/chat/completions';
    
    const prompt = `You are the LUMAX Cognitive Harness. Your job is to observe the following conversation and extract permanent facts, rules, or preferences about the user and the codebase.
CRITICAL RULES:
1. Output ONLY a raw JSON object with this exact structure: {"facts": ["...", "..."], "rules": ["...", "..."], "preferences": ["...", "..."]}
2. If the user is speaking Swedish (or any non-English language), you MUST translate the extracted facts into English. The entire JSON output must be in English to ensure global context uniformity.

Conversation Log:
${rawChatText}`;

    try {
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                model: 'smart-router_gguf',
                messages: [
                    { role: 'system', content: 'You are a strict data extractor. You must output a raw JSON object and nothing else. DO NOT output conversational text. DO NOT output markdown. Your response MUST begin with { and end with }.' },
                    { role: 'user', content: prompt }
                ],
                temperature: 0.1,
                max_tokens: 500
            })
        });

        if (!response.ok) {
            throw new Error(`Upstream returned ${response.status}`);
        }

        const data = await response.json();
        let content = data.choices[0].message.content.trim();
        console.log('[LUMAX Harness] Raw Model Output:', content);
        
        // Smart-router sometimes adds conversational text before or after the JSON.
        // Extract everything between the first '{' and the last '}'.
        const firstBrace = content.indexOf('{');
        const lastBrace = content.lastIndexOf('}');
        if (firstBrace !== -1 && lastBrace !== -1 && lastBrace >= firstBrace) {
            content = content.substring(firstBrace, lastBrace + 1);
        } else {
            throw new Error('No valid JSON object found in model output.');
        }

        const newFacts = JSON.parse(content);
        const currentData = getHarnessData();

        // Merge and deduplicate
        const merged = {
            facts: [...new Set([...currentData.facts, ...(newFacts.facts || [])])],
            rules: [...new Set([...currentData.rules, ...(newFacts.rules || [])])],
            preferences: [...new Set([...currentData.preferences, ...(newFacts.preferences || [])])]
        };

        saveHarnessData(merged);
        console.log('[LUMAX Harness] Successfully distilled and saved new facts (Auto-translated to English).');

    } catch (err) {
        console.warn('[LUMAX Harness] Distillation failed (is LM Studio running smart-router?):', err.message);
    }
}

/**
 * Injects the LUMAX Harness into the messages array before sending to the model.
 * 
 * @param {Array} messages - The standard OpenAI-format messages array
 * @param {string} cognitiveMode - 'cloud', 'local', or specialized like 'app_dev'
 * @returns {Array} - The modified messages array with injected harness
 */
function injectHarness(messages, cognitiveMode = 'cloud') {
    if (!messages || messages.length === 0) return messages;

    const harnessData = getHarnessData();
    let injectedContext = `<LUMAX_HARNESS_ACTIVE>\n`;
    injectedContext += `[COGNITIVE_MODE]: ${cognitiveMode.toUpperCase()}\n\n`;

    // Dynamic Context Injection based on Mode
    if (cognitiveMode === 'cloud') {
        injectedContext += `--- DEEP CONTEXT & RULES ---\n`;
        injectedContext += harnessData.rules.map(r => `• ${r}`).join('\n') + '\n';
        injectedContext += harnessData.preferences.map(p => `• ${p}`).join('\n') + '\n';
        injectedContext += harnessData.facts.map(f => `• ${f}`).join('\n') + '\n';
    } 
    else if (cognitiveMode === 'local') {
        injectedContext += `--- HIGH-PRIORITY RULES (TOKEN SAVER) ---\n`;
        // Only inject the absolute most critical rules to save tokens on small local models
        injectedContext += harnessData.rules.slice(0, 3).map(r => `• ${r}`).join('\n') + '\n';
    }
    else if (cognitiveMode === 'app_dev') {
        injectedContext += `--- APP DEV OPTIMIZED HARNESS ---\n`;
        // Inject facts specifically tagged or related to development
        injectedContext += harnessData.facts.filter(f => f.includes('dev') || f.includes('code')).map(f => `• ${f}`).join('\n') + '\n';
    }

    injectedContext += `</LUMAX_HARNESS_ACTIVE>\n\n`;

    // Ensure the first message is a system prompt
    if (messages[0].role === 'system') {
        messages[0].content = injectedContext + messages[0].content;
    } else {
        messages.unshift({
            role: 'system',
            content: injectedContext + "You are operating under the LUMAX Harness."
        });
    }

    console.log(`[LUMAX Harness] Successfully injected ${cognitiveMode.toUpperCase()} harness into context window.`);
    return messages;
}

module.exports = {
    injectHarness,
    extractFacts,
    getHarnessData,
    saveHarnessData
};
