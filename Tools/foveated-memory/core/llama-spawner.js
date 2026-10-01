'use strict';

const { spawn, exec } = require('child_process');
const fs = require('fs');

let _child = null;
let _starting = false;
let _shouldRun = false;
let _lastError = null;
let _activeEngine = null; // 'lm-studio' or 'llama-server'

async function pingEngine(url) {
    try {
        const res = await fetch(`${url}/v1/models`, {
            signal: AbortSignal.timeout(1500)
        });
        if (res.ok) {
            const data = await res.json();
            return data.data && data.data.length > 0;
        }
    } catch (e) {
        return false;
    }
    return false;
}

async function checkLMStudio() {
    // LM Studio usually runs on 1234
    return await pingEngine('http://127.0.0.1:1234');
}

async function startServer(config) {
    if (!config.spawner || !config.spawner.enabled) return;
    
    _shouldRun = true;
    if (_child || _starting) return;
    
    _starting = true;
    _lastError = null;

    console.log(`[SmartEngine] Checking for active LM Studio on port 1234...`);
    const isLmsRunning = await checkLMStudio();
    
    if (isLmsRunning) {
        console.log(`[SmartEngine] LM Studio detected with loaded models! Routing traffic to LM Studio (Port 1234).`);
        _activeEngine = 'lm-studio';
        _starting = false;
        // Set an env var so server.js knows where to route
        process.env.ACTIVE_ENGINE_URL = 'http://127.0.0.1:1234';
        return;
    }

    console.log(`[SmartEngine] LM Studio not found or has no models. Falling back to internal llama-server...`);
    _activeEngine = 'llama-server';
    process.env.ACTIVE_ENGINE_URL = 'http://127.0.0.1:7272';
    
    const { bin_path, model_path, draft_model_path, port, context_size } = config.spawner;
    const args = [
        '-m', model_path,
        '--port', String(port),
        '-c', String(context_size || 8192)
    ];
    
    if (draft_model_path) {
        args.push('-md', draft_model_path);
    }

    console.log(`[LlamaSpawner] Starting server on port ${port}...`);
    
    _child = spawn(bin_path, args, {
        windowsHide: true,
        stdio: 'ignore' 
    });

    _child.on('error', (err) => {
        console.error('[LlamaSpawner] Spawn error:', err.message);
        _lastError = err.message;
        _starting = false;
        scheduleRestart(config);
    });

    _child.on('exit', (code, signal) => {
        console.log(`[LlamaSpawner] Server exited (code=${code}, signal=${signal})`);
        _child = null;
        _starting = false;
        scheduleRestart(config);
    });

    setTimeout(() => {
        if (_child) _starting = false;
    }, 2000);
}

function scheduleRestart(config) {
    if (!_shouldRun) return;
    console.log('[SmartEngine] Checking if we need to restart (LM Studio might have taken over)...');
    setTimeout(() => {
        startServer(config);
    }, 3000);
}

function stopServer() {
    _shouldRun = false;
    if (_child) {
        console.log('[LlamaSpawner] Shutting down server gracefully...');
        _child.kill('SIGINT');
        setTimeout(() => {
            if (_child) _child.kill('SIGKILL');
        }, 3000);
    }
}

async function getStatus(config) {
    const port = config?.spawner?.port || 7272;
    const health = {
        ok: false,
        loaded: false
    };

    if (_activeEngine === 'lm-studio') {
        const up = await checkLMStudio();
        return {
            enabled: config?.spawner?.enabled || false,
            running: up,
            engine: 'lm-studio',
            port: 1234,
            health: { ok: up, loaded: up }
        };
    }

    if (_child) {
        try {
            const res = await fetch(`http://127.0.0.1:${port}/health`, {
                signal: AbortSignal.timeout(2000)
            });
            if (res.ok) {
                const data = await res.json();
                health.ok = data.status === 'ok';
                health.loaded = true;
            }
        } catch (e) {
            health.error = e.message;
        }
    }

    return {
        enabled: config?.spawner?.enabled || false,
        running: !!_child,
        engine: 'llama-server',
        starting: _starting,
        lastError: _lastError,
        port: port,
        health
    };
}

module.exports = {
    startServer,
    stopServer,
    getStatus
};
