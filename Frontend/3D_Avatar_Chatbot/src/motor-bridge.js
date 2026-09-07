/**
 * MotorBridge (Consolidated) — Unified Motor Cortex Bridge
 *
 * Listens to the local motor daemon's SSE publish stream and bridges those intents
 * directly into the LumaxIntegrationLayer, which handles movement, emotion, and
 * gesture execution on the 3D_Avatar_Chatbot's avatar.
 *
 * INTEGRATION POINTS:
 *   - Motor Cortex (port 8110): SSE stream for walk, emotion, gesture
 *   - LumaxIntegrationLayer: Behavior state machine, movement engine, emotion system
 *   - ViewerEngine: Animation loop integration via NEXUS_VIEWER (single loop)
 *   - Soul Core (port 8000): /compagent/stream for cognitive loop
 *
 * ANIMATION LOOP NOTE:
 *   This bridge does NOT drive its own animation loop. The ViewerEngine's
 *   setAnimationLoop is the single source of truth. The integration layer's
 *   update() is called from ViewerEngine.animate() at line 1208.
 *   This prevents double-update (once from rAF, once from setAnimationLoop).
 *
 * PORTED FROM: XR_Vessel MovementEngine + AvatarManager behavior system
 */

class MotorBridge {
    constructor(motorBusUrl = '/api/proxy/8110/motor/subscribe') {
        this.motorBusUrl = motorBusUrl;
        this.eventSource = null;
        this.isConnected = false;
        this.reconnectTimer = null;
        this.integrationLayer = null;
        
        console.log('[MotorBridge] Consolidated bridge initialized for 3D_Avatar_Chatbot');
    }

    /**
     * Connect to the Motor Cortex SSE stream.
     * Uses the LumaxIntegrationLayer if available, otherwise falls back to direct handling.
     * NOTE: Does NOT start its own animation loop — ViewerEngine.setAnimationLoop is the
     * single source of truth. The integration layer's update() is called from there.
     */
    connect() {
        if (this.eventSource) {
            this.eventSource.close();
        }

        // Get or wait for integration layer
        this.integrationLayer = window.FoveAI_INTEGRATION;
        if (!this.integrationLayer) {
            console.log('[MotorBridge] Waiting for LumaxIntegrationLayer...');
            window.addEventListener('foveai_integration_ready', () => {
                this.integrationLayer = window.FoveAI_INTEGRATION;
                console.log('[MotorBridge] Integration layer ready');
            });
        }

        console.log(`[MotorBridge] Connecting to motor bus: ${this.motorBusUrl}`);
        this.eventSource = new EventSource(this.motorBusUrl);

        this.eventSource.onopen = () => {
            console.log('[MotorBridge] Connected to motor cortex bus.');
            this.isConnected = true;
            if (this.reconnectTimer) {
                clearTimeout(this.reconnectTimer);
                this.reconnectTimer = null;
            }
            // Animation loop is driven by ViewerEngine.setAnimationLoop — no rAF here
            console.log('[MotorBridge] SSE connected. Integration layer update runs via ViewerEngine loop.');
        };

        this.eventSource.addEventListener('trigger_micro_gesture', (event) => {
            try {
                const data = JSON.parse(event.data);
                this.handleGesture(data.gesture || data.name);
            } catch (e) {
                console.error('[MotorBridge] Failed to parse gesture event:', e);
            }
        });

        this.eventSource.addEventListener('change_emotion', (event) => {
            try {
                const data = JSON.parse(event.data);
                this.handleEmotion(data.emotion || data.name, data.intensity);
            } catch (e) {
                console.error('[MotorBridge] Failed to parse emotion event:', e);
            }
        });

        this.eventSource.addEventListener('walk_to_target', (event) => {
            try {
                const data = JSON.parse(event.data);
                this.handleLocomotion(data);
            } catch (e) {
                console.error('[MotorBridge] Failed to parse walk_to_target event:', e);
            }
        });

        this.eventSource.addEventListener('walk_forward', (event) => {
            try {
                const data = JSON.parse(event.data);
                this.handleWalkForward(data);
            } catch (e) {
                console.error('[MotorBridge] Failed to parse walk_forward event:', e);
            }
        });

        this.eventSource.onerror = (err) => {
            console.warn('[MotorBridge] SSE connection error. Reconnecting in 5s...', err);
            this.isConnected = false;
            this.eventSource.close();
            
            if (!this.reconnectTimer) {
                this.reconnectTimer = setTimeout(() => this.connect(), 5000);
            }
        };
    }

    /**
     * REMOVED: _startAnimationLoop()
     *
     * The integration layer's update() is now called from ViewerEngine.animate()
     * via window.FoveAI_INTEGRATION?.update?.(dt, this.camera) at line 1208.
     *
     * Having a separate requestAnimationFrame loop here caused the integration
     * layer to update TWICE per frame — once from this rAF, once from
     * ViewerEngine's setAnimationLoop. This consolidation fixes that.
     *
     * See ViewerEngine.js animate() method for the single animation loop.
     */

    /**
     * Handle a gesture command from the motor cortex.
     * Routes through integration layer for state machine, or falls back to direct animation.
     * @param {string} gestureName - Name of the gesture to execute
     */
    handleGesture(gestureName) {
        if (!gestureName) return;
        console.log(`[MotorBridge] Executing gesture: ${gestureName}`);

        // Route through integration layer
        if (this.integrationLayer && this.integrationLayer.initialized) {
            this.integrationLayer.queueMicroGesture(gestureName);
            return;
        }

        // Fallback: direct animation via AnimationResolver
        if (window.NEXUS_ANIMATION_RESOLVER && typeof window.NEXUS_ANIMATION_RESOLVER.play === 'function') {
            window.NEXUS_ANIMATION_RESOLVER.play(gestureName);
        } else {
            console.warn('[MotorBridge] NEXUS_ANIMATION_RESOLVER not available for gesture:', gestureName);
        }
    }

    /**
     * Handle an emotion command from the motor cortex.
     * Routes through integration layer for VRM expression + state machine.
     * @param {string} emotionName - Name of the emotion
     * @param {number} intensity - Intensity 0-1
     */
    handleEmotion(emotionName, intensity = 1.0) {
        if (!emotionName) return;
        console.log(`[MotorBridge] Changing emotion: ${emotionName} (${intensity})`);

        // Route through integration layer
        if (this.integrationLayer && this.integrationLayer.initialized) {
            this.integrationLayer.setEmotion(emotionName, intensity);
            return;
        }

        // Fallback: direct VRM expression
        try {
            const vrmLoader = window.NEXUS_VIEWER?.avatarManager?.vrmLoader;
            if (vrmLoader && typeof vrmLoader.setExpression === 'function') {
                ['happy', 'angry', 'sad', 'relaxed', 'surprised'].forEach(emo => vrmLoader.setExpression(emo, 0));
                
                const vrmEmoMap = {
                    'joy': 'happy', 'happy': 'happy',
                    'anger': 'angry', 'angry': 'angry',
                    'sorrow': 'sad', 'sad': 'sad',
                    'fun': 'relaxed', 'relaxed': 'relaxed',
                    'surprise': 'surprised', 'surprised': 'surprised',
                    'neutral': 'neutral'
                };
                
                const mappedEmo = vrmEmoMap[emotionName.toLowerCase()] || emotionName.toLowerCase();
                vrmLoader.setExpression(mappedEmo, intensity);
            }
        } catch (e) {
            console.warn('[MotorBridge] Failed to apply emotion via vrmLoader:', e);
        }
    }

    /**
     * Handle a locomotion command from the motor cortex.
     * Routes through integration layer's movement engine.
     * @param {Object} data - Locomotion data {target, distance}
     */
    handleLocomotion(data) {
        console.log(`[MotorBridge] Locomotion requested:`, data);

        // Route through integration layer
        if (this.integrationLayer && this.integrationLayer.initialized) {
            const target = data.target || 'user';
            const distance = data.distance || 1.0;

            if (target === 'user' || target === 'player') {
                const camera = window.NEXUS_VIEWER?.camera;
                if (camera) {
                    const dir = new THREE.Vector3();
                    camera.getWorldDirection(dir);
                    dir.y = 0;
                    dir.normalize();
                    const targetPos = camera.position.clone().add(dir.clone().multiplyScalar(-distance));
                    this.integrationLayer.commandMoveTo(targetPos);
                }
            } else if (target === 'home') {
                this.integrationLayer.commandReturnHome();
            } else {
                const coords = target.split(',').map(Number);
                if (coords.length >= 2 && !isNaN(coords[0]) && !isNaN(coords[1])) {
                    this.integrationLayer.commandMoveTo(new THREE.Vector3(coords[0], 0, coords[1]));
                }
            }
            return;
        }

        // Fallback: direct AvatarLocomotionSystem
        if (window.AvatarLocomotionSystem && typeof window.AvatarLocomotionSystem.walkTo === 'function') {
            window.AvatarLocomotionSystem.walkTo(data.target || 'user', data.distance);
        }
    }

    /**
     * Handle a walk_forward command from the motor cortex.
     * @param {Object} data - Walk data {distance}
     */
    handleWalkForward(data) {
        const distance = data.distance || 0.5;
        console.log(`[MotorBridge] Walk forward: ${distance}m`);

        if (this.integrationLayer && this.integrationLayer.initialized) {
            this.integrationLayer.commandWalkForward(distance);
        }
    }

    /**
     * Wire the integration layer to the ViewerEngine after avatar load.
     * Called automatically when NEXUS_VIEWER loads an avatar.
     */
    wireToViewerEngine() {
        const checkViewer = () => {
            const viewer = window.NEXUS_VIEWER;
            if (viewer && viewer.avatarManager && viewer.avatarManager.vrm) {
                const vrm = viewer.avatarManager.vrm;
                const avatarRoot = viewer.avatarManager.avatarRoot || vrm.scene;
                const mixer = viewer.avatarManager.mixer;

                if (this.integrationLayer) {
                    this.integrationLayer.init(avatarRoot, vrm, mixer);
                    console.log('[MotorBridge] Integration layer wired to ViewerEngine');
                }
                return true;
            }
            return false;
        };

        // Try immediately, then retry until avatar is loaded
        if (!checkViewer()) {
            const interval = setInterval(() => {
                if (checkViewer()) {
                    clearInterval(interval);
                }
            }, 500);
            // Stop checking after 30 seconds
            setTimeout(() => clearInterval(interval), 30000);
        }
    }

    /**
     * Disconnect from the motor cortex and clean up.
     */
    disconnect() {
        if (this.eventSource) {
            this.eventSource.close();
            this.isConnected = false;
        }
        if (this.integrationLayer) {
            this.integrationLayer.dispose();
        }
    }
}

window.MotorBridge = MotorBridge;

// Auto-initialize
window.addEventListener('DOMContentLoaded', () => {
    const motorUrl = 'http://127.0.0.1:8110/motor/subscribe';
    const bridge = new MotorBridge(motorUrl);
    window.nexusMotorBridge = bridge;
    
    // Connect to motor cortex
    bridge.connect();
    
    // Wire to viewer engine when it becomes available
    bridge.wireToViewerEngine();
    
    // Also listen for viewer ready event
    window.addEventListener('nexus_viewer_ready', () => {
        bridge.wireToViewerEngine();
    });
    
    console.log('[MotorBridge] Auto-initialized');
});