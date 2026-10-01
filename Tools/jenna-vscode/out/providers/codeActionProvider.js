"use strict";
/**
 * codeActionProvider.ts — Lightbulb & QuickFix provider for Jenna (LUMAX Agent)
 *
 * Registers QuickFix actions on errors/warnings so users can click the lightbulb
 * or "Send to Agent" menu item and immediately forward problem tracebacks & context to Jenna.
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
exports.JennaCodeActionProvider = void 0;
exports.registerCodeActionProvider = registerCodeActionProvider;
const vscode = __importStar(require("vscode"));
class JennaCodeActionProvider {
    static providedCodeActionKinds = [
        vscode.CodeActionKind.QuickFix
    ];
    provideCodeActions(document, range, context, _token) {
        if (!context.diagnostics || context.diagnostics.length === 0) {
            return [];
        }
        const actions = [];
        // 1. Action for specific diagnostic under cursor
        for (const diagnostic of context.diagnostics) {
            const title = `🤖 Send to Jenna AI: "${diagnostic.message.slice(0, 45)}..."`;
            const action = new vscode.CodeAction(title, vscode.CodeActionKind.QuickFix);
            action.command = {
                command: 'jenna.sendProblemToAgent',
                title: title,
                arguments: [document, range, [diagnostic]]
            };
            action.isPreferred = true;
            actions.push(action);
        }
        // 2. Action to send all diagnostics in file to Jenna
        if (context.diagnostics.length > 1) {
            const allTitle = `🤖 Send all ${context.diagnostics.length} problems in file to Jenna AI`;
            const allAction = new vscode.CodeAction(allTitle, vscode.CodeActionKind.QuickFix);
            allAction.command = {
                command: 'jenna.sendAllProblemsToAgent',
                title: allTitle,
                arguments: [document, context.diagnostics]
            };
            actions.push(allAction);
        }
        return actions;
    }
}
exports.JennaCodeActionProvider = JennaCodeActionProvider;
function registerCodeActionProvider(context, chatProvider) {
    // Register CodeAction provider for all languages
    context.subscriptions.push(vscode.languages.registerCodeActionsProvider('*', new JennaCodeActionProvider(), {
        providedCodeActionKinds: JennaCodeActionProvider.providedCodeActionKinds
    }));
    // Command 1: Send single problem to Jenna
    context.subscriptions.push(vscode.commands.registerCommand('jenna.sendProblemToAgent', async (document, _range, diagnostics) => {
        // Focus Jenna sidebar view
        await vscode.commands.executeCommand('jennaChat.focus');
        const activeDoc = document || vscode.window.activeTextEditor?.document;
        if (!activeDoc) {
            vscode.window.showWarningMessage('No active document found to inspect problem.');
            return;
        }
        const diags = diagnostics || vscode.languages.getDiagnostics(activeDoc.uri);
        if (!diags || diags.length === 0) {
            vscode.window.showInformationMessage('No active diagnostics found in document.');
            return;
        }
        const firstDiag = diags[0];
        const lineText = activeDoc.lineAt(firstDiag.range.start.line).text.trim();
        const relativePath = vscode.workspace.asRelativePath(activeDoc.uri);
        const prompt = `Please help fix this code problem in \`${relativePath}:${firstDiag.range.start.line + 1}\`:\n` +
            `**Diagnostic Error:** \`${firstDiag.message}\` (Code: ${firstDiag.code || 'N/A'})\n` +
            `**Source Line:** \`${lineText}\`\n\n` +
            `Could you investigate and provide the corrected code?`;
        chatProvider.handleUserPrompt(prompt);
    }));
    // Command 2: Send all problems in workspace to Jenna
    context.subscriptions.push(vscode.commands.registerCommand('jenna.sendAllProblemsToAgent', async (_document, _diagnostics) => {
        await vscode.commands.executeCommand('jennaChat.focus');
        const allDiagnostics = vscode.languages.getDiagnostics();
        let totalCount = 0;
        const problemSummaryLines = [];
        for (const [uri, diags] of allDiagnostics) {
            if (diags.length === 0)
                continue;
            const relPath = vscode.workspace.asRelativePath(uri);
            for (const d of diags.slice(0, 10)) { // limit to top 10 to fit prompt nicely
                totalCount++;
                problemSummaryLines.push(`- \`${relPath}:${d.range.start.line + 1}\`: ${d.message}`);
            }
        }
        if (totalCount === 0) {
            vscode.window.showInformationMessage('No active problems found in workspace!');
            return;
        }
        const prompt = `Please inspect and fix the following ${totalCount} problem(s) in the workspace:\n\n` +
            problemSummaryLines.join('\n') +
            `\n\nPlease systematically resolve these issues to bring the Problems Panel to 0 errors.`;
        chatProvider.handleUserPrompt(prompt);
    }));
}
//# sourceMappingURL=codeActionProvider.js.map