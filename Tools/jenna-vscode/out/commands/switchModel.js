"use strict";
/**
 * switchModel.ts — Jenna Model Switcher
 *
 * `Jenna: Switch Model` command — fetches available models from port 8400
 * (which proxies to Ollama/LM Studio) and lets you pick one via Quick Pick.
 * The selection is persisted to workspace settings.
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
exports.registerSwitchModel = registerSwitchModel;
const vscode = __importStar(require("vscode"));
function registerSwitchModel(context, _client, workspaceId) {
    const disposable = vscode.commands.registerCommand('jenna.switchModel', async () => {
        const config = vscode.workspace.getConfiguration('jenna');
        const baseUrl = config.get('foveatedMemoryUrl', 'http://127.0.0.1:8400');
        const current = config.get('model', 'auto');
        // Fetch available models from proxy
        let models = [];
        try {
            const resp = await fetch(`${baseUrl}/v1/models`, {
                headers: {
                    'Authorization': `Bearer ${workspaceId}`,
                },
                signal: AbortSignal.timeout(4000),
            });
            if (resp.ok) {
                const data = await resp.json();
                models = data.data ?? [];
            }
        }
        catch {
            // Fall through to manual entry
        }
        // Build Quick Pick items
        const items = [
            {
                label: '$(symbol-keyword) auto',
                description: 'Let the proxy decide (recommended)',
                detail: current === 'auto' ? '✓ Currently active' : undefined,
            },
            { label: '$(server) Gemma-4-12b-XRLF', description: 'Gemma-4-12b-XRLF' },
            { label: '$(server) Quwtpus-9B-XRLF', description: 'Quwtpus-9B-XRLF' },
            { label: '$(server) 4B-Super-Coder-XRLF', description: '4B-Super-Coder-XRLF' },
            ...models.map(m => ({
                label: `$(server) ${m.id}`,
                description: m.id,
                detail: current === m.id ? '✓ Currently active' : undefined,
            })),
            {
                label: '$(edit) Enter model name manually…',
                description: 'Type a model ID not listed above',
            },
        ];
        const picked = await vscode.window.showQuickPick(items, {
            title: '🧠 Jenna — Select Model',
            placeHolder: `Current: ${current}`,
        });
        if (!picked)
            return;
        let selectedModel;
        if (picked.label.includes('Enter model name manually')) {
            const manual = await vscode.window.showInputBox({
                prompt: 'Enter the exact model ID (e.g. qwen2.5-coder:7b)',
                value: current,
            });
            if (!manual?.trim())
                return;
            selectedModel = manual.trim();
        }
        else if (picked.label.includes('auto')) {
            selectedModel = 'auto';
        }
        else {
            selectedModel = picked.description ?? 'auto';
        }
        // Persist to workspace settings
        await config.update('model', selectedModel, vscode.ConfigurationTarget.Workspace);
        vscode.window.showInformationMessage(`Jenna: Model switched to → ${selectedModel}`);
    });
    context.subscriptions.push(disposable);
    return disposable;
}
//# sourceMappingURL=switchModel.js.map