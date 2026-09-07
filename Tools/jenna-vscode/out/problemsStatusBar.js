"use strict";
/**
 * problemsStatusBar.ts — "Send Problems → Agent" Status Bar Button
 *
 * Creates a persistent left-aligned status bar item that:
 * - Shows live problem count (errors + warnings) updated in real-time
 * - Clicking it sends ALL problems directly to the Antigravity agent chat
 * - Falls back to Jenna sidebar + clipboard if Antigravity is unavailable
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
exports.ProblemsStatusBar = void 0;
const vscode = __importStar(require("vscode"));
class ProblemsStatusBar {
    item;
    disposables = [];
    constructor(context) {
        // Left-aligned, high priority so it appears near the left side of the status bar
        // The ID ensures VS Code remembers the item's visibility and doesn't hide it
        this.item = vscode.window.createStatusBarItem('FoveAI.sendProblems', vscode.StatusBarAlignment.Left, 950);
        this.item.command = 'jenna.sendAllProblemsToAgent';
        this.item.name = 'FoveAI: Send Problems to Agent';
        // Initial render
        this._updateCount();
        // Listen for diagnostic changes and re-render
        const diagListener = vscode.languages.onDidChangeDiagnostics(() => {
            this._updateCount();
        });
        this.disposables.push(diagListener);
        context.subscriptions.push(this.item, diagListener);
        this.item.show();
    }
    _updateCount() {
        const all = vscode.languages.getDiagnostics();
        let errors = 0;
        let warnings = 0;
        for (const [, diags] of all) {
            for (const d of diags) {
                if (d.severity === vscode.DiagnosticSeverity.Error)
                    errors++;
                else if (d.severity === vscode.DiagnosticSeverity.Warning)
                    warnings++;
            }
        }
        const total = errors + warnings;
        if (total === 0) {
            // Always visible — show a clean/ready state
            this.item.text = '$(check) 0 Problems';
            this.item.tooltip = 'FoveAI: No errors — click to send problems to Agent';
            this.item.backgroundColor = undefined;
            this.item.color = undefined;
        }
        else {
            const parts = [];
            if (errors > 0)
                parts.push(`$(error) ${errors}`);
            if (warnings > 0)
                parts.push(`$(warning) ${warnings}`);
            this.item.text = `${parts.join('  ')} → Agent`;
            this.item.tooltip = `FoveAI: ${total} problem(s) — click to send ALL to AI Agent for diagnosis`;
            this.item.backgroundColor = errors > 0
                ? new vscode.ThemeColor('statusBarItem.errorBackground')
                : new vscode.ThemeColor('statusBarItem.warningBackground');
            this.item.color = undefined;
        }
    }
    dispose() {
        this.item.dispose();
        this.disposables.forEach(d => d.dispose());
    }
}
exports.ProblemsStatusBar = ProblemsStatusBar;
//# sourceMappingURL=problemsStatusBar.js.map