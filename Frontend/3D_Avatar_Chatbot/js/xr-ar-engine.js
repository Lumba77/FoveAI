/**
 * [NEXUS OVERHAUL] Director's Augmented Reality Engine
 * Handles magical XR effects: Soundscaping, Visual Thoughts, Holodeck
 */

window.DirectorAR = {
    scene: null,
    camera: null,
    avatar: null,
    audioListener: null,
    backgroundAudio: null,
    thoughtMesh: null,
    textureLoader: new THREE.TextureLoader(),

    init: function(scene, camera, avatarController) {
        this.scene = scene;
        this.camera = camera;
        this.avatar = avatarController?.vrm?.scene; // Try to hook onto the VRM scene if available

        // 1. Setup Audio Engine
        this.audioListener = new THREE.AudioListener();
        this.camera.add(this.audioListener);
        
        this.backgroundAudio = new THREE.Audio(this.audioListener);
        this.audioLoader = new THREE.AudioLoader();

        // 2. Setup Thought Bubble Mesh (Hidden initially)
        const geometry = new THREE.PlaneGeometry(0.8, 0.8);
        const material = new THREE.MeshBasicMaterial({ 
            color: 0xffffff, 
            transparent: true,
            opacity: 0.0, // Fade in later
            side: THREE.DoubleSide
        });
        this.thoughtMesh = new THREE.Mesh(geometry, material);
        this.scene.add(this.thoughtMesh);

        console.log("[DirectorAR] Engine Initialized.");
    },

    /**
     * SOUNDSCAPING
     * e.g., playSound('assets/audio/sad_strings.mp3')
     */
    playSound: function(url) {
        console.log("[DirectorAR] Playing Soundscape:", url);
        // Simple mock fallback if URL doesn't exist, we just simulate the fade
        if (!url || url.includes('placeholder')) {
            window.showMessage("Director Soundscape Triggered (Mock)", "info");
            return;
        }

        if (this.backgroundAudio.isPlaying) {
            this.backgroundAudio.stop();
        }

        this.audioLoader.load(url, (buffer) => {
            this.backgroundAudio.setBuffer(buffer);
            this.backgroundAudio.setLoop(true);
            this.backgroundAudio.setVolume(0.5);
            this.backgroundAudio.play();
        }, undefined, (err) => {
            console.warn("[DirectorAR] Audio load failed, likely missing asset:", url);
        });
    },

    /**
     * VISUAL THOUGHTS
     * Projects a hologram image next to the avatar's head.
     */
    showThought: function(imageUrl) {
        console.log("[DirectorAR] Showing Visual Thought:", imageUrl);
        
        this.textureLoader.load(imageUrl, (texture) => {
            this.thoughtMesh.material.map = texture;
            this.thoughtMesh.material.opacity = 0;
            this.thoughtMesh.material.needsUpdate = true;
            
            // Position it near the avatar's head, or 1.5m high in front of camera
            if (this.avatar) {
                const avatarPos = new THREE.Vector3();
                this.avatar.getWorldPosition(avatarPos);
                this.thoughtMesh.position.set(avatarPos.x + 0.6, avatarPos.y + 1.5, avatarPos.z + 0.2);
            } else {
                this.thoughtMesh.position.set(0.6, 1.5, -1.0);
            }

            // Simple fade-in animation
            let op = 0;
            const fadeIn = setInterval(() => {
                op += 0.05;
                if (op >= 0.9) {
                    clearInterval(fadeIn);
                    // Auto-hide after 10 seconds
                    setTimeout(() => this.hideThought(), 10000);
                }
                this.thoughtMesh.material.opacity = op;
            }, 50);

        }, undefined, (err) => {
            console.warn("[DirectorAR] Thought texture load failed:", err);
        });
    },

    hideThought: function() {
        let op = this.thoughtMesh.material.opacity;
        const fadeOut = setInterval(() => {
            op -= 0.05;
            if (op <= 0) {
                clearInterval(fadeOut);
                this.thoughtMesh.material.opacity = 0;
            }
            this.thoughtMesh.material.opacity = op;
        }, 50);
    },

    /**
     * HOLODECK
     * Swaps the 360 environment map/background.
     */
    holodeck: function(imageUrl) {
        console.log("[DirectorAR] Entering Holodeck Mode:", imageUrl);
        
        // Use a spherical equirectangular map for Holodeck
        this.textureLoader.load(imageUrl, (texture) => {
            texture.mapping = THREE.EquirectangularReflectionMapping;
            
            // Apply to scene background and environment lighting
            this.scene.background = texture;
            this.scene.environment = texture;
            
            window.showMessage("Holodeck Environment Loaded.", "info");
        }, undefined, (err) => {
            console.warn("[DirectorAR] Holodeck texture load failed:", err);
            // Fallback for visual testing if missing
            this.scene.background = new THREE.Color(0x1a0b2e); // Deep space purple
            window.showMessage("Holodeck Environment Activated (Fallback Space).", "info");
        });
    }
};
