/**
 * [NEXUS OVERHAUL] XR Holographic DOM Projector
 * Renders the HTML UI (like Quick Prompts) into a 3D texture using html2canvas.
 * Anchors it to the left controller.
 */

window.XRHologram = {
    mesh: null,
    controller: null,
    isVisible: false,
    lastXPress: false,
    
    init: function(scene, renderer) {
        if (!window.html2canvas) {
            console.warn("[XRHologram] html2canvas not found! Cannot build hologram.");
            return;
        }

        this.scene = scene;
        this.renderer = renderer;

        // Create the 3D Slate
        const geometry = new THREE.PlaneGeometry(0.3, 0.4); // 30cm x 40cm
        const material = new THREE.MeshBasicMaterial({ 
            color: 0xffffff, 
            transparent: true, 
            opacity: 0.9,
            side: THREE.DoubleSide
        });
        
        this.mesh = new THREE.Mesh(geometry, material);
        // Anchor to wrist (offset slightly)
        this.mesh.position.set(0, 0.1, -0.1); 
        this.mesh.rotation.x = -Math.PI / 4; // Tilted towards face
        this.mesh.visible = false;

        // Get Left Controller (usually controller 0)
        this.controller = renderer.xr.getController(0);
        if (this.controller) {
            this.controller.add(this.mesh);
            
            // Setup Raycaster for clicking
            this.raycaster = new THREE.Raycaster();
            this.tempMatrix = new THREE.Matrix4();
            
            // Listen to trigger clicks on the right controller (usually 1)
            this.rightController = renderer.xr.getController(1);
            if (this.rightController) {
                this.rightController.addEventListener("select", () => this.onTriggerPulled());
            }
            scene.add(this.controller);
        }

        // Start animation loop to poll gamepad
        this.pollGamepad();
    },

    onTriggerPulled: function() {
        if (!this.isVisible || !this.rightController) return;
        
        this.tempMatrix.identity().extractRotation(this.rightController.matrixWorld);
        this.raycaster.ray.origin.setFromMatrixPosition(this.rightController.matrixWorld);
        this.raycaster.ray.direction.set(0, 0, -1).applyMatrix4(this.tempMatrix);
        
        const intersects = this.raycaster.intersectObject(this.mesh);
        if (intersects.length > 0) {
            const uv = intersects[0].uv;
            console.log("[XRHologram] Clicked at UV:", uv);
            
            // Map UV to DOM coordinates
            const uiElement = document.getElementById('quick-prompts-ui');
            if (uiElement) {
                const rect = uiElement.getBoundingClientRect();
                const x = rect.left + (uv.x * rect.width);
                const y = rect.top + ((1 - uv.y) * rect.height); // UV Y is inverted
                
                console.log("[XRHologram] Synthetic click at", x, y);
                // Dispatch synthetic click
                const target = document.elementFromPoint(x, y);
                if (target) {
                    target.click();
                    // Visual feedback
                    this.mesh.material.color.setHex(0x00ff00);
                    setTimeout(() => this.mesh.material.color.setHex(0xffffff), 200);
                }
            }
        }
    },
    toggleHologram: async function() {
        this.isVisible = !this.isVisible;
        this.mesh.visible = this.isVisible;

        if (this.isVisible) {
            // Re-render the UI
            const uiElement = document.getElementById('quick-prompts-ui');
            if (uiElement) {
                // Temporarily show to capture
                const oldDisplay = uiElement.style.display;
                uiElement.style.display = 'flex';
                
                try {
                    const canvas = await window.html2canvas(uiElement, {
                        backgroundColor: 'rgba(0,0,0,0.8)',
                        scale: 2 // High res
                    });
                    
                    const texture = new THREE.CanvasTexture(canvas);
                    this.mesh.material.map = texture;
                    this.mesh.material.needsUpdate = true;
                } catch (e) {
                    console.error("[XRHologram] Canvas rendering failed", e);
                }
                
                // Hide again if it was hidden
                uiElement.style.display = oldDisplay;
            }
        }
    },

    pollGamepad: function() {
        const checkGamepad = () => {
            if (this.renderer.xr.isPresenting) {
                const gamepads = navigator.getGamepads();
                // Find left controller (usually gamepad 0 or matches XR controller)
                for (let i = 0; i < gamepads.length; i++) {
                    const gp = gamepads[i];
                    if (gp && gp.mapping === 'xr-standard' && gp.hand === 'left') {
                        // Button 3 or 4 is usually X or Y on Oculus Touch
                        const xPressed = gp.buttons[3]?.pressed || gp.buttons[4]?.pressed || gp.buttons[2]?.pressed;
                        
                        if (xPressed && !this.lastXPress) {
                            console.log("[XRHologram] 'X' Button Pressed! Toggling Hologram...");
                            this.toggleHologram();
                        }
                        this.lastXPress = xPressed;
                    }
                }
            }
            requestAnimationFrame(checkGamepad);
        };
        checkGamepad();
    }
};
