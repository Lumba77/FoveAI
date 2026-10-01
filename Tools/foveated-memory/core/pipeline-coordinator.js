/**
 * ═══════════════════════════════════════════════════════
 * 3-MODEL PIPELINE COORDINATOR
 * ═══════════════════════════════════════════════════════
 *
 * Orchestrates a three-model pipeline for intelligent message processing:
 *
 * MODEL 1 (Receiver - smart-router_gguf):
 *   - Always handles new incoming messages first
 *   - Performs initial message triage and classification
 *   - Routes to appropriate downstream models
 *   - Handles real-time routing decisions
 *
 * MODEL 2 (Delegator - no.2-smart-router_gguf):
 *   - Receives delegated tasks from receiver
 *   - Routes to specialist models or background processing
 *   - Manages task distribution and load balancing
 *   - Handles digestion and archiving decisions
 *
 * MODEL 3 (Summarizer - dedicated summarizer model):
 *   - Dedicated to summarization tasks
 *   - Handles background compression and token optimization
 *   - Processes long-term storage optimization
 *   - Works independently on summarization queue
 *
 * Pipeline Flow:
 *   1. New message → Receiver (Model 1)
 *   2. Receiver classifies → Delegator (Model 2) or direct to agent
 *   3. Delegator routes → Summarizer (Model 3) or background processing
 *   4. All three models can work in parallel on different tasks
 */

'use strict';

const fetch = globalThis.fetch || require('node-fetch');

// ── Config ──────────────────────────────────────────────────────────────────
const RECEIVER_MODELS = ['smart-router_gguf', 'no.2-smart-router_gguf']; // Load balanced
const DELEGATOR_MODELS = ['no.2-smart-router_gguf', 'smart-router_gguf']; // Load balanced  
const SUMMARIZER_MODEL = process.env.LUMAX_SUMMARIZER_MODEL || 'qwen3.5-4b-abliterated'; // Can be configured
// Singular aliases for use in pipeline result metadata (fixes ReferenceError)
const RECEIVER_MODEL = RECEIVER_MODELS[0];
const DELEGATOR_MODEL = DELEGATOR_MODELS[0];
const LM_STUDIO_URL = process.env.LM_STUDIO_URL || 'http://127.0.0.1:7272';

// Message classification thresholds
const CRITICAL_THRESHOLD = 1000; // chars - below this, always route to agent
const DELEGATION_THRESHOLD = 2000; // chars - above this, consider delegation

// Model availability tracking
const modelStatus = new Map();
const REQUEST_TIMEOUT = 30000; // 30 seconds for model response

// ── LLM call helper with automatic failover ─────────────────────────────────
async function callLLM(messages, model, maxTokens = 2048, temperature = 0.2, fallbackModels = []) {
    const modelsToTry = [model, ...fallbackModels];
    
    for (const currentModel of modelsToTry) {
        try {
            // Mark model as busy
            modelStatus.set(currentModel, { busy: true, since: Date.now() });
            
            const res = await fetch(`${LM_STUDIO_URL}/v1/chat/completions`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ model: currentModel, messages, temperature, max_tokens: maxTokens, stream: false }),
                signal: (() => { const c = new AbortController(); setTimeout(() => c.abort(), REQUEST_TIMEOUT); return c.signal; })()
            });
            
            if (!res.ok) throw new Error(`LLM ${res.status}: ${(await res.text()).slice(0, 200)}`);
            const data = await res.json();
            const result = data.choices?.[0]?.message?.content || '';
            
            // Mark model as available
            modelStatus.set(currentModel, { busy: false, lastSuccess: Date.now() });
            console.log(`[Pipeline] ${currentModel} responded successfully`);
            return result;
            
        } catch (e) {
            console.warn(`[Pipeline] ${currentModel} failed: ${e.message} - trying fallback`);
            // Mark model as potentially unavailable
            modelStatus.set(currentModel, { busy: false, lastError: e.message, errorTime: Date.now() });
            
            // Continue to next model in fallback list
            continue;
        }
    }
    
    // All models failed
    throw new Error(`All models failed: ${modelsToTry.join(', ')}`);
}

// ── Model 1: Receiver ───────────────────────────────────────────────────────
async function receiver(messages) {
    const lastUser = [...messages].reverse().find(m => m.role === 'user');
    if (!lastUser) return { action: 'pass', reason: 'No user message' };
    
    const text = typeof lastUser.content === 'string' ? lastUser.content : '';
    const textLength = text.length;

    // Quick classification without LLM call for simple cases
    if (textLength < CRITICAL_THRESHOLD) {
        return { 
            action: 'route_to_agent', 
            reason: `Short message (${textLength} chars) - direct routing`,
            model: RECEIVER_MODELS[0]
        };
    }

    // For longer messages, use Receiver to classify with automatic failover
    const prompt = `You are a Message Receiver. Classify this message into ONE of these actions:
1. "route_to_agent" - Critical/urgent message that needs immediate agent attention
2. "delegate" - Send to delegator for further routing and task distribution
3. "summarize" - Send directly to summarizer for compression

Respond in EXACT JSON format: {"action":"<action>","reason":"<brief explanation>"}

MESSAGE:
${text.slice(0, 3000)}`;

    try {
        // Try primary receiver model, then fallback to secondary
        const fallbackModels = RECEIVER_MODELS.slice(1);
        const raw = await callLLM([{ role: 'user', content: prompt }], RECEIVER_MODELS[0], 200, 0.1, fallbackModels);
        const jsonMatch = raw.match(/\{[\s\S]*\}/);
        if (!jsonMatch) throw new Error('No JSON returned');
        
        const parsed = JSON.parse(jsonMatch[0]);
        const validActions = ['route_to_agent', 'delegate', 'summarize'];
        const action = validActions.includes(parsed.action) ? parsed.action : 'route_to_agent';
        
        console.log(`[Pipeline] Receiver classified: ${action} - ${parsed.reason}`);
        return { action, reason: parsed.reason, model: RECEIVER_MODELS[0] };
    } catch (e) {
        console.warn(`[Pipeline] Receiver classification failed: ${e.message} - defaulting to route_to_agent`);
        return { action: 'route_to_agent', reason: 'Classification failed - safe default', model: RECEIVER_MODELS[0] };
    }
}

// ── Model 2: Delegator ─────────────────────────────────────────────────────
async function delegator(messages) {
    const lastUser = [...messages].reverse().find(m => m.role === 'user');
    if (!lastUser) return { action: 'pass', result: '' };
    
    const text = typeof lastUser.content === 'string' ? lastUser.content : '';

    const prompt = `You are a Task Delegator. Your job is to:
1. Analyze the task requirements
2. Decide if it needs summarization, background processing, or specialist handling
3. Route to the appropriate downstream model

Classify into ONE of these actions:
1. "summarize" - Send to dedicated summarizer for compression
2. "background" - Process as background task for archiving
3. "specialist" - Route to specialist model for specific task type

Respond in EXACT JSON format: {"action":"<action>","task_type":"<type>","reason":"<explanation>"}

TASK TO DELEGATE:
${text.slice(0, 3000)}`;

    try {
        // Try primary delegator model, then fallback to secondary
        const fallbackModels = DELEGATOR_MODELS.slice(1);
        const raw = await callLLM([{ role: 'user', content: prompt }], DELEGATOR_MODELS[0], 300, 0.1, fallbackModels);
        const jsonMatch = raw.match(/\{[\s\S]*\}/);
        if (!jsonMatch) throw new Error('No JSON returned');
        
        const parsed = JSON.parse(jsonMatch[0]);
        const validActions = ['summarize', 'background', 'specialist'];
        const action = validActions.includes(parsed.action) ? parsed.action : 'background';
        
        console.log(`[Pipeline] Delegator routed: ${action} - ${parsed.reason}`);
        return { 
            action, 
            taskType: parsed.task_type || 'general',
            reason: parsed.reason,
            model: DELEGATOR_MODELS[0]
        };
    } catch (e) {
        console.warn(`[Pipeline] Delegator failed: ${e.message} - defaulting to background`);
        return { action: 'background', reason: 'Delegation failed - safe default', model: DELEGATOR_MODELS[0] };
    }
}

// ── Model 3: Summarizer ─────────────────────────────────────────────────────
async function summarizer(messages) {
    const lastUser = [...messages].reverse().find(m => m.role === 'user');
    if (!lastUser) return { action: 'pass', result: '' };
    
    const text = typeof lastUser.content === 'string' ? lastUser.content : '';

    const prompt = `You are a Dedicated Summarizer. Your job is to:
1. Create dense, information-rich summaries
2. Extract key points and decisions
3. Preserve critical context and file references
4. Strip filler and redundant content
5. Optimize for token efficiency

Respond with structured summary in JSON format:
{"summary":"<concise dense summary>","key_points":["<point1>","<point2>"],"decisions":["<decision1>"],"file_refs":["<file1>"],"token_reduction":"<estimated %>"}

CONTENT TO SUMMARIZE:
${text.slice(0, 4000)}`;

    try {
        const raw = await callLLM([{ role: 'user', content: prompt }], SUMMARIZER_MODEL, 1500, 0.2);
        const jsonMatch = raw.match(/\{[\s\S]*\}/);
        if (!jsonMatch) throw new Error('No JSON returned');
        
        const parsed = JSON.parse(jsonMatch[0]);
        console.log(`[Pipeline] Summarizer processed: ${parsed.summary?.slice(0, 50)}... (${parsed.token_reduction || 'N/A'} reduction)`);
        
        return { 
            action: 'summarized', 
            result: parsed,
            model: SUMMARIZER_MODEL 
        };
    } catch (e) {
        console.warn(`[Pipeline] Summarizer failed: ${e.message}`);
        return { action: 'failed', reason: e.message, model: SUMMARIZER_MODEL };
    }
}

// ── Pipeline Coordinator ───────────────────────────────────────────────────
async function coordinatePipeline(messages) {
    console.log(`[Pipeline] Starting 3-model pipeline with ${messages.length} messages`);
    
    // Step 1: Receiver (Model 1) classifies the message
    const receiverDecision = await receiver(messages);
    
    switch (receiverDecision.action) {
        case 'route_to_agent':
            console.log(`[Pipeline] Routing directly to agent via ${receiverDecision.model}`);
            return { 
                messages, 
                pipeline: 'direct',
                reason: receiverDecision.reason,
                processed_by: [RECEIVER_MODEL]
            };
            
        case 'summarize':
            console.log(`[Pipeline] Receiver routed to summarizer`);
            const summaryResult = await summarizer(messages);
            return {
                messages: summaryResult.action === 'summarized' 
                    ? messages.map(m => m.role === 'user' && typeof m.content === 'string'
                        ? { ...m, content: `[SUMMARIZED]: ${summaryResult.result.summary}\n\nKEY POINTS:\n${summaryResult.result.key_points?.join('\n')}\n\nDECISIONS:\n${summaryResult.result.decisions?.join('\n')}` }
                        : m)
                    : messages,
                pipeline: 'summarized',
                reason: receiverDecision.reason,
                processed_by: [RECEIVER_MODEL, SUMMARIZER_MODEL],
                summary_result: summaryResult.result
            };
            
        case 'delegate':
            console.log(`[Pipeline] Receiver delegated to delegator`);
            const delegatorDecision = await delegator(messages);
            
            // Step 2: Delegator (Model 2) routes further
            switch (delegatorDecision.action) {
                case 'summarize':
                    console.log(`[Pipeline] Delegator routed to summarizer`);
                    const delegatedSummary = await summarizer(messages);
                    return {
                        messages: delegatedSummary.action === 'summarized' 
                            ? messages.map(m => m.role === 'user' && typeof m.content === 'string'
                                ? { ...m, content: `[DELEGATED-SUMMARIZED]: ${delegatedSummary.result.summary}\n\nKEY POINTS:\n${delegatedSummary.result.key_points?.join('\n')}` }
                                : m)
                            : messages,
                        pipeline: 'delegated-summarized',
                        reason: `${receiverDecision.reason} → ${delegatorDecision.reason}`,
                        processed_by: [RECEIVER_MODEL, DELEGATOR_MODEL, SUMMARIZER_MODEL],
                        summary_result: delegatedSummary.result
                    };
                    
                case 'background':
                    console.log(`[Pipeline] Delegator processed as background task`);
                    // Queue for background processing
                    queueBackgroundTask(messages);
                    return {
                        messages,
                        pipeline: 'background-queued',
                        reason: `${receiverDecision.reason} → ${delegatorDecision.reason}`,
                        processed_by: [RECEIVER_MODEL, DELEGATOR_MODEL],
                        note: 'Queued for background processing'
                    };
                    
                case 'specialist':
                    console.log(`[Pipeline] Delegator routed to specialist`);
                    // For now, pass through - specialist routing to be implemented
                    return {
                        messages,
                        pipeline: 'specialist',
                        reason: `${receiverDecision.reason} → ${delegatorDecision.reason}`,
                        processed_by: [RECEIVER_MODEL, DELEGATOR_MODEL],
                        note: 'Specialist routing to be implemented'
                    };
                    
                default:
                    return {
                        messages,
                        pipeline: 'delegator-fallback',
                        reason: delegatorDecision.reason,
                        processed_by: [RECEIVER_MODEL, DELEGATOR_MODEL]
                    };
            }
            
        default:
            return { messages, pipeline: 'pass', reason: receiverDecision.reason };
    }
}

// ── Background Task Queue ───────────────────────────────────────────────────
const backgroundQueue = [];
let isProcessing = false;

async function processBackgroundQueue() {
    if (isProcessing || backgroundQueue.length === 0) return;
    
    isProcessing = true;
    const task = backgroundQueue.shift();
    
    try {
        console.log(`[Pipeline] Processing background task: ${task.id}`);
        const result = await delegator(task.messages);
        task.resolve(result);
    } catch (e) {
        console.error(`[Pipeline] Background task failed: ${e.message}`);
        task.reject(e);
    } finally {
        isProcessing = false;
        // Process next item if any
        if (backgroundQueue.length > 0) {
            setTimeout(processBackgroundQueue, 100);
        }
    }
}

function queueBackgroundTask(messages) {
    return new Promise((resolve, reject) => {
        const task = { id: Date.now(), messages, resolve, reject };
        backgroundQueue.push(task);
        processBackgroundQueue();
    });
}

module.exports = {
    coordinatePipeline,
    receiver,
    delegator,
    summarizer,
    queueBackgroundTask,
    RECEIVER_MODELS,
    DELEGATOR_MODELS,
    SUMMARIZER_MODEL,
    getModelStatus: () => modelStatus
};
