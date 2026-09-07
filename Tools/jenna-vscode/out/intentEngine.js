"use strict";
/**
 * intentEngine.ts — Autonomous Intent Engine
 *
 * Takes raw user input → classifies intent → builds execution plan →
 * drives tool calls → reports results. Enables self-directed code
 * modification from vague voice commands.
 */
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.classifyIntent = classifyIntent;
exports.buildPlan = buildPlan;
exports.processUserIntent = processUserIntent;
const vscode = __importStar(require("vscode"));
const path = __importStar(require("path"));
const fs = __importStar(require("fs"));
const repoScanner_1 = require("./memory/repoScanner");
const INTENT_PATTERNS = [
    { type: 'scan', patterns: [/scan/i, /analyze (the )?(repo|codebase|project|folder)/i, /what.*(broken|missing|wrong)/i] },
    { type: 'edit_file', patterns: [/change|update|modify|fix|edit|rewrite|replace/i] },
    { type: 'create_file', patterns: [/create|new file|make (a|an)|generate|write.*file/i] },
    { type: 'refactor', patterns: [/refactor|restructure|clean.?up|organize|simplify/i] },
    { type: 'debug', patterns: [/bug|error|crash|broken|not work|fail|exception|issue/i] },
    { type: 'explain', patterns: [/explain|how does|what is|understand|tell me about/i] },
    { type: 'test', patterns: [/test|spec|coverage|assert/i] },
    { type: 'search', patterns: [/find|search|locate|where is/i] },
];
function classifyIntent(input) {
    const cleaned = input.replace(/[^\w\s]/g, ' ');
    const words = cleaned.split(/\s+/).filter(w => w.length > 2);
    const kw = words.join(' ');
    const scores = [];
    for (const { type, patterns } of INTENT_PATTERNS) {
        let score = 0;
        for (const p of patterns) {
            if (p.test(kw))
                score += p.source.length / 10;
            if (p.test(input))
                score += p.source.length / 15;
        }
        if (score > 0)
            scores.push({ type, score });
    }
    scores.sort((a, b) => b.score - a.score);
    const targets = [];
    const filePat = /`([^`]+\.[a-zA-Z]+)`|([a-zA-Z0-9_-]+\.[a-zA-Z]+)/g;
    let m;
    while ((m = filePat.exec(input)) !== null)
        targets.push(m[1] || m[2]);
    if (scores.length === 0)
        return { type: 'chat', confidence: 0.3, prompt: input, targets, userMessage: input };
    const top = scores[0];
    const confidence = Math.min(1, top.score / 20);
    let prompt = '';
    switch (top.type) {
        case 'edit_file':
            prompt = `I need to modify code based on: "${input}". `;
            if (targets.length)
                prompt += ` Files: ${targets.join(', ')}. `;
            prompt += 'First read the code, plan the edit, then produce replacement code.';
            break;
        case 'create_file':
            prompt = `I need to create new code: "${input}". Design with proper structure and exports.`;
            break;
        case 'refactor':
            prompt = `I need to refactor: "${input}". Identify duplication, extract functions, improve structure.`;
            break;
        case 'debug':
            prompt = `I need to debug: "${input}". Find root cause and produce a fix.`;
            break;
        case 'scan':
            prompt = `Scan and analyze: "${input}". Give assessment of codebase health and architecture.`;
            break;
        case 'explain':
            prompt = `Explain: "${input}" with thorough explanation and code examples.`;
            break;
        case 'test':
            prompt = `Write tests for: "${input}" covering edge cases, normal cases, and failure modes.`;
            break;
        default:
            prompt = input;
    }
    return { type: top.type, confidence, prompt, targets, userMessage: input };
}
async function buildPlan(intent) {
    const steps = [];
    const wsFolders = vscode.workspace.workspaceFolders;
    const wsRoot = wsFolders?.[0]?.uri.fsPath;
    switch (intent.type) {
        case 'scan':
            steps.push({ action: 'scan', description: 'Scan repo structure', done: false });
            steps.push({ action: 'analyze', description: 'Analyze results for patterns and issues', done: false });
            break;
        case 'edit_file':
            for (const t of intent.targets) {
                const fp = wsRoot ? path.resolve(wsRoot, t) : t;
                if (fs.existsSync(fp))
                    steps.push({ action: 'read', description: 'Read ' + t, file: t, done: false });
            }
            if (intent.targets.length === 0)
                steps.push({ action: 'search', description: 'Find relevant files', done: false });
            steps.push({ action: 'analyze', description: 'Analyze what needs to change', done: false });
            steps.push({ action: 'edit', description: 'Apply edit: ' + intent.userMessage.slice(0, 60), done: false });
            break;
        case 'create_file':
            steps.push({ action: 'analyze', description: 'Design new file structure', done: false });
            steps.push({ action: 'create', description: 'Create: ' + intent.userMessage.slice(0, 60), done: false });
            break;
        case 'debug':
            for (const t of intent.targets) {
                const fp = wsRoot ? path.resolve(wsRoot, t) : t;
                if (fs.existsSync(fp))
                    steps.push({ action: 'read', description: 'Read ' + t, file: t, done: false });
            }
            steps.push({ action: 'analyze', description: 'Root cause analysis', done: false });
            steps.push({ action: 'edit', description: 'Apply the fix', done: false });
            break;
        case 'refactor':
            for (const t of intent.targets) {
                steps.push({ action: 'read', description: 'Read ' + t, file: t, done: false });
            }
            steps.push({ action: 'analyze', description: 'Plan refactoring', done: false });
            steps.push({ action: 'edit', description: 'Apply refactoring', done: false });
            break;
        default:
            steps.push({ action: 'analyze', description: intent.prompt.slice(0, 100), done: false });
    }
    return { steps, summary: intent.type + ' — ' + intent.userMessage.slice(0, 100), userMessage: intent.userMessage };
}
async function processUserIntent(userInput, client, workspaceId, provider) {
    const intent = classifyIntent(userInput);
    const plan = await buildPlan(intent);
    const planStr = '**Intent**: ' + intent.type + ' (' + Math.round(intent.confidence * 100) + '%)\n**Plan**:\n' +
        plan.steps.map((s, i) => (i + 1) + '. ' + s.description).join('\n') +
        '\n\nProceed with step 1.';
    await provider.handleExternalChat(planStr);
    for (let i = 0; i < plan.steps.length; i++) {
        const step = plan.steps[i];
        if (step.action === 'scan') {
            const wsRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
            if (wsRoot) {
                const repo = await (0, repoScanner_1.scanRepo)(wsRoot, client, workspaceId);
                step.result = repo.digest;
            }
        }
        else if (step.action === 'read' && step.file) {
            const wsRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
            if (wsRoot) {
                try {
                    step.result = fs.readFileSync(path.resolve(wsRoot, step.file), 'utf8').slice(0, 15000);
                }
                catch { }
            }
        }
        else {
            await provider.handleExternalChat(step.prompt || step.description);
        }
        step.done = true;
        await new Promise(r => setTimeout(r, 300));
    }
}
//# sourceMappingURL=intentEngine.js.map