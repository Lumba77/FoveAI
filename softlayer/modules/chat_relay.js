// ── chat_relay.js — 4-Way XR Chat Panel ─────────────────────────────────────
// Renders a floating holographic chat panel in the XR scene showing
// messages from all 4 participants: user, jen, devin, antigravity.
//
// Connects to the chat relay WebSocket on port 8407.
// Color-coded per speaker, auto-scrolling, billboard-facing camera.
//
// API:
//   FoveAI.chatRelay.toggle()      — show/hide the chat panel
//   FoveAI.chatRelay.send(text)    — send a message (as "user")
//   FoveAI.chatRelay.clear()       — clear the panel
//   FoveAI.chatRelay.setPosition(x,y,z) — move the panel
//
// SoftLayer params:
//   chatRelay.enabled     — true/false (default: true)
//   chatRelay.port        — relay port (default: 8407)
//   chatRelay.maxLines    — max visible lines (default: 12)
//   chatRelay.opacity     — panel opacity 0-1 (default: 0.85)
//   chatRelay.fontSize    — text size (default: 0.08)

FoveAI.setParam("chatRelay.enabled", true);
FoveAI.setParam("chatRelay.port", 8407);
FoveAI.setParam("chatRelay.maxLines", 12);
FoveAI.setParam("chatRelay.opacity", 0.85);
FoveAI.setParam("chatRelay.fontSize", 0.08);

// ── Speaker colors (hex) ──
var SPEAKER_COLORS = {
    user:        "#ffffff",  // white
    jen:         "#44ff44",  // green
    devin:       "#4488ff",  // blue
    antigravity: "#ffaa22",  // orange
    unknown:     "#ff44ff",  // magenta
};

var _ws = null;
var _messages = [];
var _panel = null;
var _panelGroup = null;
var _lineMeshes = [];
var _visible = true;
var _reconnectTimer = null;
var _scene = null;
var _camera = null;

function _getScene() {
    if (_scene) return _scene;
    _scene = (typeof window !== "undefined") && (window.foveaiScene || (window.FoveAI && window.FoveAI.scene));
    return _scene;
}

function _getCamera() {
    if (_camera) return _camera;
    _camera = (typeof window !== "undefined") && (window.foveaiCamera || (window.FoveAI && window.FoveAI.camera));
    return _camera;
}

function chatRelay_onLoad() {
    FoveAI.log("chat_relay module loaded — connecting to relay...");
    _connectRelay();
    _buildPanel();
}

// ── Connect to the WebSocket relay ──
function _connectRelay() {
    var port = FoveAI.getParam("chatRelay.port") || 8407;
    try {
        _ws = new WebSocket("ws://127.0.0.1:" + port + "/ws");

        _ws.onopen = function() {
            FoveAI.log("chat_relay: connected to ws://127.0.0.1:" + port);
        };

        _ws.onmessage = function(event) {
            try {
                var data = JSON.parse(event.data);
                if (data.type === "history") {
                    _messages = data.messages || [];
                } else if (data.type === "chat") {
                    _messages.push(data);
                    var maxLines = FoveAI.getParam("chatRelay.maxLines") || 12;
                    while (_messages.length > maxLines * 2) {
                        _messages.shift();
                    }
                }
                _refreshPanel();
            } catch (e) {
                // ignore parse errors
            }
        };

        _ws.onclose = function() {
            FoveAI.log("chat_relay: disconnected, will retry in 3s...");
            _ws = null;
            if (_reconnectTimer) clearTimeout(_reconnectTimer);
            _reconnectTimer = setTimeout(_connectRelay, 3000);
        };

        _ws.onerror = function() {
            // onclose will handle reconnect
        };
    } catch (e) {
        FoveAI.log("chat_relay: connection failed — " + (e.message || e));
        if (_reconnectTimer) clearTimeout(_reconnectTimer);
        _reconnectTimer = setTimeout(_connectRelay, 3000);
    }
}

// ── Build the 3D panel ──
function _buildPanel() {
    var scene = _getScene();
    if (!scene || typeof THREE === "undefined") {
        FoveAI.log("chat_relay: THREE/scene not available, panel deferred (will retry)");
        setTimeout(_buildPanel, 2000);
        return;
    }

    var opacity = FoveAI.getParam("chatRelay.opacity") || 0.85;
    var fontSize = FoveAI.getParam("chatRelay.fontSize") || 0.08;
    var maxLines = FoveAI.getParam("chatRelay.maxLines") || 12;

    _panelGroup = new THREE.Group();

    // Background plane (semi-transparent dark panel)
    var bgGeo = new THREE.PlaneGeometry(3.0, maxLines * fontSize * 2.2 + 0.3);
    var bgMat = new THREE.MeshBasicMaterial({
        color: 0x000022,
        transparent: true,
        opacity: opacity * 0.7,
        side: THREE.DoubleSide,
        depthTest: false,
    });
    _panel = new THREE.Mesh(bgGeo, bgMat);
    _panel.renderOrder = 999;
    _panelGroup.add(_panel);

    // Position: floating in front, slightly above eye level, to the left
    _panelGroup.position.set(-2.5, 1.6, -3.0);
    _panelGroup.visible = _visible;

    scene.add(_panelGroup);
    FoveAI.log("chat_relay: panel built (" + maxLines + " lines)");
}

// ── Create a text texture from a message ──
function _makeLineTexture(speaker, text) {
    var canvas = document.createElement("canvas");
    canvas.width = 1024;
    canvas.height = 64;
    var ctx = canvas.getContext("2d");

    // Transparent background
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Speaker name in their color
    var color = SPEAKER_COLORS[speaker] || SPEAKER_COLORS.unknown;
    ctx.font = "bold 28px monospace";
    ctx.fillStyle = color;
    ctx.textAlign = "left";
    ctx.textBaseline = "middle";

    var speakerText = speaker + ":";
    ctx.fillText(speakerText, 10, 32);

    // Message text in light gray
    ctx.font = "24px monospace";
    ctx.fillStyle = "#dddddd";
    var msgText = text.length > 55 ? text.substring(0, 52) + "..." : text;
    ctx.fillText(msgText, 10 + ctx.measureText(speakerText).width + 10, 32);

    return new THREE.CanvasTexture(canvas);
}

// ── Refresh the panel content ──
function _refreshPanel() {
    if (!_panelGroup || typeof THREE === "undefined") return;

    // Remove old line meshes
    for (var i = 0; i < _lineMeshes.length; i++) {
        _panelGroup.remove(_lineMeshes[i]);
        if (_lineMeshes[i].material.map) _lineMeshes[i].material.map.dispose();
        _lineMeshes[i].material.dispose();
        _lineMeshes[i].geometry.dispose();
    }
    _lineMeshes = [];

    var fontSize = FoveAI.getParam("chatRelay.fontSize") || 0.08;
    var maxLines = FoveAI.getParam("chatRelay.maxLines") || 12;
    var recent = _messages.slice(-maxLines);

    for (var j = 0; j < recent.length; j++) {
        var msg = recent[j];
        var speaker = msg.from || "unknown";
        var text = msg.text || "";

        var texture = _makeLineTexture(speaker, text);
        var lineGeo = new THREE.PlaneGeometry(2.8, fontSize * 1.5);
        var lineMat = new THREE.MeshBasicMaterial({
            map: texture,
            transparent: true,
            side: THREE.DoubleSide,
            depthTest: false,
        });
        var lineMesh = new THREE.Mesh(lineGeo, lineMat);
        lineMesh.renderOrder = 1000 + j;

        // Stack lines from top
        var y = (maxLines * fontSize * 2.2 + 0.3) / 2 - fontSize * 1.5 - j * fontSize * 2.0;
        lineMesh.position.set(0, y, 0.01);
        _panelGroup.add(lineMesh);
        _lineMeshes.push(lineMesh);
    }
}

// ── Public API ──

FoveAI.chatRelay = FoveAI.chatRelay || {};

FoveAI.chatRelay.toggle = function() {
    _visible = !_visible;
    if (_panelGroup) _panelGroup.visible = _visible;
    FoveAI.log("chat_relay: " + (_visible ? "visible" : "hidden"));
};

FoveAI.chatRelay.send = function(text) {
    if (_ws && _ws.readyState === WebSocket.OPEN) {
        var msg = { type: "chat", from: "user", text: text };
        _ws.send(JSON.stringify(msg));
    } else {
        FoveAI.log("chat_relay: not connected, cannot send");
    }
};

FoveAI.chatRelay.clear = function() {
    _messages = [];
    _refreshPanel();
    FoveAI.log("chat_relay: cleared");
};

FoveAI.chatRelay.setPosition = function(x, y, z) {
    if (_panelGroup) {
        _panelGroup.position.set(x, y, z);
    }
};

FoveAI.chatRelay.isVisible = function() {
    return _visible;
};

// ── Lifecycle hooks ──

function chatRelay_onUpdate(dt) {
    // Billboard: make panel face the camera
    if (_panelGroup && _visible) {
        var cam = _getCamera();
        if (cam) {
            _panelGroup.lookAt(cam.position);
        }
    }
}

function chatRelay_onUnload() {
    if (_ws) {
        _ws.onclose = null; // prevent reconnect
        _ws.close();
        _ws = null;
    }
    if (_reconnectTimer) {
        clearTimeout(_reconnectTimer);
        _reconnectTimer = null;
    }
    if (_panelGroup) {
        var scene = _getScene();
        if (scene && _panelGroup.parent) {
            scene.remove(_panelGroup);
        }
    }
    _lineMeshes = [];
    _panel = null;
    _panelGroup = null;
    FoveAI.log("chat_relay: unloaded");
}
