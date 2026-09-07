"use strict";
/**
 * inlineProvider.ts — Jenna Inline Ghost-Text Completions
 *
 * Registers an InlineCompletionItemProvider that sends the current file
 * context (prefix + suffix) to the Foveated Memory proxy and streams
 * back a code completion as ghost text.
 *
 * Debounced at 600ms to avoid hammering the proxy on every keystroke.
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
exports.registerInlineProvider = registerInlineProvider;
const vscode = __importStar(require("vscode"));
const DEBOUNCE_MS = 600;
const MAX_PREFIX_LINES = 40; // lines before cursor
const MAX_SUFFIX_LINES = 10; // lines after cursor
const MAX_COMPLETION_TOKENS = 120;
// Supported languages for inline completions
const ENABLED_LANGUAGES = new Set([
    'python', 'typescript', 'javascript', 'typescriptreact', 'javascriptreact',
    'go', 'rust', 'java', 'csharp', 'cpp', 'c', 'powershell', 'shellscript',
]);
function registerInlineProvider(context, client, workspaceId) {
    let debounceTimer = null;
    const provider = {
        async provideInlineCompletionItems(document, position, _context, token) {
            // Only trigger for enabled languages
            if (!ENABLED_LANGUAGES.has(document.languageId))
                return null;
            // Check config — user can disable inline completions
            const config = vscode.workspace.getConfiguration('jenna');
            if (!config.get('inlineCompletions', true))
                return null;
            // Debounce
            if (debounceTimer)
                clearTimeout(debounceTimer);
            await new Promise((resolve) => {
                debounceTimer = setTimeout(resolve, DEBOUNCE_MS);
            });
            if (token.isCancellationRequested)
                return null;
            // Build prefix (lines before cursor)
            const prefixStart = Math.max(0, position.line - MAX_PREFIX_LINES);
            const prefix = document.getText(new vscode.Range(prefixStart, 0, position.line, position.character));
            // Build suffix (lines after cursor)
            const suffixEnd = Math.min(document.lineCount - 1, position.line + MAX_SUFFIX_LINES);
            const suffix = document.getText(new vscode.Range(position.line, position.character, suffixEnd, 0));
            const fileName = document.fileName.split(/[\\/]/).pop() ?? '';
            const lang = document.languageId;
            const prompt = [
                `Complete the following ${lang} code in file \`${fileName}\`.`,
                `Return ONLY the completion text — no explanation, no markdown fences.`,
                `Prefix:\n${prefix}`,
                suffix ? `Suffix (what comes after):\n${suffix}` : '',
            ].filter(Boolean).join('\n\n');
            try {
                let completion = '';
                const stream = client.chat([{ role: 'user', content: prompt }], {
                    workspaceId,
                    model: vscode.workspace.getConfiguration('jenna').get('model', 'auto'),
                    stream: true,
                    maxTokens: MAX_COMPLETION_TOKENS,
                    temperature: 0.1, // low temp for completions
                });
                for await (const chunk of stream) {
                    if (token.isCancellationRequested)
                        return null;
                    completion += chunk;
                }
                completion = completion.trim();
                if (!completion)
                    return null;
                return {
                    items: [
                        new vscode.InlineCompletionItem(completion, new vscode.Range(position, position)),
                    ],
                };
            }
            catch {
                // Silently fail — don't show error toasts for inline completions
                return null;
            }
        },
    };
    const disposable = vscode.languages.registerInlineCompletionItemProvider({ pattern: '**' }, // all files — filtered by ENABLED_LANGUAGES above
    provider);
    context.subscriptions.push(disposable);
    return disposable;
}
//# sourceMappingURL=inlineProvider.js.map