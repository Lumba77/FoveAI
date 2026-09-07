/**
 * ═══════════════════════════════════════════════════════
 * LINTER FEEDBACK — File Edit Diagnostics Tracker
 * ═══════════════════════════════════════════════════════
 *
 * Tracks files touched during a session and runs linters (eslint/ruff)
 * to provide PASSED/FAILED status for the Agent HUD.
 *
 * Supported linters:
 * - JavaScript/TypeScript: eslint
 * - Python: ruff (preferred) or flake8 (fallback)
 */

'use strict';

const { spawn } = require('child_process');
const path = require('path');

// Session-level file tracking
const sessionFiles = new Map(); // sessionId -> Set of file paths
const sessionDiagnostics = new Map(); // sessionId -> Array of {file, status, message}

/**
 * Register a file as touched during the current session.
 * @param {string} sessionId 
 * @param {string} filePath 
 */
function trackFile(sessionId, filePath) {
    if (!sessionFiles.has(sessionId)) {
        sessionFiles.set(sessionId, new Set());
    }
    sessionFiles.get(sessionId).add(filePath);
}

/**
 * Run linter on a single file and return diagnostics.
 * @param {string} filePath 
 * @returns {Promise<{status: 'clean'|'error', message: string}>}
 */
async function lintFile(filePath) {
    const ext = path.extname(filePath).toLowerCase();
    
    try {
        if (ext === '.js' || ext === '.jsx' || ext === '.ts' || ext === '.tsx') {
            return await lintJavaScript(filePath);
        } else if (ext === '.py') {
            return await lintPython(filePath);
        } else {
            return { status: 'clean', message: 'No linter for this file type' };
        }
    } catch (err) {
        return { status: 'error', message: err.message };
    }
}

/**
 * Run eslint on JavaScript/TypeScript files.
 * @param {string} filePath 
 * @returns {Promise<{status: 'clean'|'error', message: string}>}
 */
async function lintJavaScript(filePath) {
    return new Promise((resolve) => {
        const child = spawn('npx', ['eslint', '--format', 'json', filePath], {
            stdio: ['pipe', 'pipe', 'pipe'],
            shell: true
        });

        let stdout = '';
        let stderr = '';

        child.stdout.on('data', (chunk) => { stdout += chunk.toString(); });
        child.stderr.on('data', (chunk) => { stderr += chunk.toString(); });

        child.on('close', (code) => {
            if (code === 0) {
                resolve({ status: 'clean', message: 'No linting errors' });
            } else {
                try {
                    const results = JSON.parse(stdout);
                    const errorCount = results.reduce((sum, r) => sum + (r.errorCount || 0), 0);
                    const warningCount = results.reduce((sum, r) => sum + (r.warningCount || 0), 0);
                    resolve({ 
                        status: 'error', 
                        message: `${errorCount} errors, ${warningCount} warnings` 
                    });
                } catch {
                    resolve({ status: 'error', message: stderr || 'Linting failed' });
                }
            }
        });

        child.on('error', () => {
            // eslint not available, treat as clean
            resolve({ status: 'clean', message: 'eslint not available' });
        });
    });
}

/**
 * Run ruff (or flake8 fallback) on Python files.
 * @param {string} filePath 
 * @returns {Promise<{status: 'clean'|'error', message: string}>}
 */
async function lintPython(filePath) {
    // Try ruff first
    try {
        return await lintRuff(filePath);
    } catch {
        // Fallback to flake8
        return await lintFlake8(filePath);
    }
}

/**
 * Run ruff on Python files.
 * @param {string} filePath 
 * @returns {Promise<{status: 'clean'|'error', message: string}>}
 */
async function lintRuff(filePath) {
    return new Promise((resolve) => {
        const child = spawn('ruff', ['check', filePath], {
            stdio: ['pipe', 'pipe', 'pipe']
        });

        let stdout = '';
        let stderr = '';

        child.stdout.on('data', (chunk) => { stdout += chunk.toString(); });
        child.stderr.on('data', (chunk) => { stderr += chunk.toString(); });

        child.on('close', (code) => {
            if (code === 0) {
                resolve({ status: 'clean', message: 'No linting errors' });
            } else {
                const lineCount = stdout.trim().split('\n').length;
                resolve({ status: 'error', message: `${lineCount} issues found` });
            }
        });

        child.on('error', () => {
            throw new Error('ruff not available');
        });
    });
}

/**
 * Run flake8 on Python files (fallback).
 * @param {string} filePath 
 * @returns {Promise<{status: 'clean'|'error', message: string}>}
 */
async function lintFlake8(filePath) {
    return new Promise((resolve) => {
        const child = spawn('flake8', [filePath], {
            stdio: ['pipe', 'pipe', 'pipe']
        });

        let stdout = '';
        let stderr = '';

        child.stdout.on('data', (chunk) => { stdout += chunk.toString(); });
        child.stderr.on('data', (chunk) => { stderr += chunk.toString(); });

        child.on('close', (code) => {
            if (code === 0) {
                resolve({ status: 'clean', message: 'No linting errors' });
            } else {
                const lineCount = stdout.trim().split('\n').length;
                resolve({ status: 'error', message: `${lineCount} issues found` });
            }
        });

        child.on('error', () => {
            resolve({ status: 'clean', message: 'flake8 not available' });
        });
    });
}

/**
 * Run linters on all tracked files for a session.
 * @param {string} sessionId 
 * @returns {Promise<Array<{file: string, status: 'clean'|'error', message: string}>>}
 */
async function lintSession(sessionId) {
    const files = sessionFiles.get(sessionId);
    if (!files || files.size === 0) {
        return [];
    }

    const diagnostics = [];
    for (const filePath of files) {
        const result = await lintFile(filePath);
        diagnostics.push({
            file: path.basename(filePath),
            status: result.status,
            message: result.message
        });
    }

    // Cache diagnostics for the session
    sessionDiagnostics.set(sessionId, diagnostics);
    return diagnostics;
}

/**
 * Get cached diagnostics for a session.
 * @param {string} sessionId 
 * @returns {Array<{file: string, status: 'clean'|'error', message: string}>}
 */
function getSessionDiagnostics(sessionId) {
    return sessionDiagnostics.get(sessionId) || [];
}

/**
 * Clear tracking for a session (call on session end).
 * @param {string} sessionId 
 */
function clearSession(sessionId) {
    sessionFiles.delete(sessionId);
    sessionDiagnostics.delete(sessionId);
}

module.exports = {
    trackFile,
    lintFile,
    lintSession,
    getSessionDiagnostics,
    clearSession
};