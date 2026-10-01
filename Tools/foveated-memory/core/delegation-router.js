/**
 * ═══════════════════════════════════════════════════════
 * 2-STEP DELEGATION ROUTER
 * ═══════════════════════════════════════════════════════
 *
 * Offloads the main model's multitasking load by delegating
 * work to specialist model copies running in parallel.
 *
 * Step 1 — DELEGATOR (no.2-smart-router_gguf, 1B, fast):
 *   Classifies incoming work into one of seven specialist roles
 *   and extracts the essential task essence + critical context.
 *
 * Step 2 — SPECIALISTS (parallel model copies, role-prompted):
 *   Each specialist handles its assigned workload with a
 *   role-specific system prompt. Multiple tasks run via
 *   Promise.all to share the load across model copies.
 *
 * The delegator model is specially trained for seven task types
 * (code, research, creative, summarize, plan, data, general) and
 * is a summarization specialist — perfectly suited to identify
 * what the main model should delegate vs. handle itself.
 *
 * Env gating:
 *   LUMAX_DELEGATION_ENABLED=true (default on)
 *   LUMAX_DELEGATOR_MODEL   — the classifying model (default no.2-smart-router_gguf)
 *   LUMAX_SPECIALIST_MODEL  — the specialist model copy (default = delegator)
 *   LUMAX_DELEGATE_THRESHOLD — min chars before delegating (default 2000)
 */

'use strict';

const fetch = globalThis.fetch || require('node-fetch');

// ── Config ──────────────────────────────────────────────────────────────────
const DELEGATION_ENABLED = process.env.LUMAX_DELEGATION_ENABLED !== '0' && process.env.LUMAX_DELEGATION_ENABLED !== 'false';
const DELEGATOR_MODEL    = process.env.LUMAX_DELEGATOR_MODEL || 'no.2-smart-router_gguf';
const SPECIALIST_MODEL   = process.env.LUMAX_SPECIALIST_MODEL || DELEGATOR_MODEL;
const DELEGATE_THRESHOLD = parseInt(process.env.LUMAX_DELEGATE_THRESHOLD || '2000', 10);
let   LM_STUDIO_URL      = process.env.LM_STUDIO_URL || 'http://127.0.0.1:7272';

// Load balancing between two router models for specialist execution
const ROUTER_MODELS = ['smart-router_gguf', 'no.2-smart-router_gguf'];

// The seven specialist roles the delegator is trained to classify into.
// Each has a role-specific system prompt that turns a model copy into a specialist.
const SPECIALIST_ROLES = {
    code:      'You are a CODE SPECIALIST. Produce precise, working, production-grade code. Focus on correctness, edge cases, and idiomatic patterns. Be concise.',
    research:  'You are a RESEARCH SPECIALIST. Gather, synthesize, and reason over information. Cite key facts and surface uncertainties. Be rigorous.',
    creative:  'You are a CREATIVE SPECIALIST. Generate original, imaginative, well-structured creative work. Match the requested tone and voice.',
    summarize: 'You are a SUMMARIZATION SPECIALIST. Dense-summarize preserving ALL facts, decisions, file refs, and tone. Strip filler — "air between words". NEVER invent information.',
    plan:      'You are a PLANNING SPECIALIST. Break work into clear, ordered, actionable steps with dependencies and acceptance criteria.',
    data:      'You are a DATA SPECIALIST. Work with data, formats, and transformations. Be precise about structure and edge cases.',
    general:   'You are a GENERAL SPECIALIST. Handle the task competently and concisely, preserving all important context.'
};

// ── LLM call helper ─────────────────────────────────────────────────────────
async function callLLM(messages, model, maxTokens = 2048, temperature = 0.2) {
    const res = await fetch(`${LM_STUDIO_URL}/v1/chat/completions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model, messages, temperature, max_tokens: maxTokens, stream: false }),
        signal: (() => { const c = new AbortController(); setTimeout(() => c.abort(), 45000); return c.signal; })()
    });
    if (!res.ok) throw new Error(`LLM ${res.status}: ${(await res.text()).slice(0, 200)}`);
    const data = await res.json();
    return data.choices?.[0]?.message?.content || '';
}

// ── Step 1: Delegator — classify + extract essence ─────────────────────────
async function delegate(messages) {
    // Build a compact context for the delegator (last few turns only)
    const recent = messages.slice(-4).map(m => `${m.role}: ${typeof m.content === 'string' ? m.content.slice(0, 2000) : JSON.stringify(m.content).slice(0, 2000)}`).join('\n\n');

    const prompt = `You are a Context Delegation Router. Classify the following work into ONE of these seven specialist roles: code, research, creative, summarize, plan, data, general.
Then extract the essential task essence and critical context needed to complete it.

Respond in EXACT JSON format, no markdown fences, no explanations:
{"role":"<one of the seven>","task":"<concise task statement>","critical_context":"<only the critical facts/files/constraints needed>"}

WORK TO CLASSIFY:
${recent}`;

    try {
        const raw = await callLLM([{ role: 'user', content: prompt }], DELEGATOR_MODEL, 800, 0.1);
        const jsonMatch = raw.match(/\{[\s\S]*\}/);
        if (!jsonMatch) throw new Error('Delegator returned no JSON');
        const parsed = JSON.parse(jsonMatch[0]);
        const role = SPECIALIST_ROLES[parsed.role] ? parsed.role : 'general';
        return { role, task: parsed.task || '', criticalContext: parsed.critical_context || '' };
    } catch (e) {
        console.warn(`[Delegation] Delegator failed (${e.message}) — falling back to general`);
        return { role: 'general', task: '', criticalContext: '' };
    }
}

// ── Step 2: Specialists — execute in parallel ──────────────────────────────
async function runSpecialist(delegation) {
    const rolePrompt = SPECIALIST_ROLES[delegation.role] || SPECIALIST_ROLES.general;
    const task = delegation.task || delegation.criticalContext || '';
    const prompt = `${rolePrompt}\n\nTASK:\n${task}\n\nCRITICAL CONTEXT:\n${delegation.criticalContext || '(none provided)'}\n\nComplete the task. Output ONLY the result.`;

    // Load balancing between two router models for specialist execution
    const specialistModel = ROUTER_MODELS[Math.floor(Math.random() * ROUTER_MODELS.length)];
    console.log(`[Delegation] Load balancing selected specialist model: ${specialistModel}`);

    try {
        const result = await callLLM([{ role: 'user', content: prompt }], specialistModel, 4096, 0.3);
        return { role: delegation.role, result };
    } catch (e) {
        console.warn(`[Delegation] Specialist (${delegation.role}) failed: ${e.message}`);
        return { role: delegation.role, result: '' };
    }
}

// ── Main entry: 2-step delegation pipeline ─────────────────────────────────
async function delegateMessages(messages, lmStudioUrl) {
    if (!DELEGATION_ENABLED) return messages;
    if (lmStudioUrl) LM_STUDIO_URL = lmStudioUrl; // allow override

    const lastUser = [...messages].reverse().find(m => m.role === 'user');
    if (!lastUser) return messages;
    const text = typeof lastUser.content === 'string' ? lastUser.content : '';
    if (text.length < DELEGATE_THRESHOLD) return messages; // only delegate substantial work

    console.log(`[Delegation] 🚀 Delegating ${text.length} char task via ${DELEGATOR_MODEL} → specialist ${SPECIALIST_MODEL}`);

    // Step 1: delegator classifies
    const delegation = await delegate(messages);
    if (!delegation.task && !delegation.criticalContext) {
        console.log('[Delegation] ⏭️ Delegator returned nothing useful — passing through');
        return messages;
    }

    // Step 2: specialist executes (single specialist for now — the delegator
    // identified the single dominant role; multi-role fan-out can be added later)
    const specialistResult = await runSpecialist(delegation);
    if (!specialistResult.result) {
        console.log('[Delegation] ⏭️ Specialist returned nothing — passing through');
        return messages;
    }

    console.log(`[Delegation] ✅ Specialist (${delegation.role}) produced ${specialistResult.result.length} chars`);

    // Replace the last user message content with delegator handoff + specialist result,
    // so the main model sees the delegation summary instead of the raw massive dump.
    const handoffMarker = `[DELEGATED:${delegation.role}] The main model delegated this task to a specialist. Summary of what was requested and produced:\n\nTASK: ${delegation.task}\n\nSPECIALIST RESULT:\n${specialistResult.result}`;

    const output = messages.map((m, i) => {
        // Only replace the last user message that triggered delegation
        if (m === lastUser && i === messages.length - 1) {
            return { ...m, content: handoffMarker };
        }
        return m;
    });

    return output;
}

module.exports = { delegateMessages, SPECIALIST_ROLES, DELEGATOR_MODEL, SPECIALIST_MODEL };