"use strict";
/**
 * editApplicator.ts — Applies AI code blocks to active editor.
 * Extracts code from markdown code fences, writes to cursor or selection.
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
exports.EditApplicator = void 0;
const vscode = __importStar(require("vscode"));
class EditApplicator {
    _post;
    constructor(_post) {
        this._post = _post;
    }
    applyEdit(text) {
        const editor = vscode.window.activeTextEditor;
        if (!editor || !text) {
            vscode.window.showWarningMessage('No active editor');
            return;
        }
        let code = text;
        const m = text.match(/`(?:\w+)?\n([\s\S]*?)`/);
        if (m)
            code = m[1];
        editor.edit(eb => {
            if (!editor.selection.isEmpty)
                eb.replace(editor.selection, code);
            else
                eb.insert(editor.selection.active, code);
        }).then(s => { if (s)
            this._post({ type: 'status_update', status: { online: true, loading: false, message: 'Edit applied' } }); });
    }
}
exports.EditApplicator = EditApplicator;
//# sourceMappingURL=editApplicator.js.map