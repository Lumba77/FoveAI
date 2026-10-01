class HitTestManager {
    constructor(renderer, scene, camera, avatarRoot) {
        this.renderer = renderer;
        this.scene = scene;
        this.camera = camera;
        this.avatarRoot = avatarRoot;

        this.hitTestSource = null;
        this.hitTestSourceRequested = false;

        this.reticle = new THREE.Mesh(
            new THREE.RingGeometry(0.15, 0.2, 32).rotateX(-Math.PI / 2),
            new THREE.MeshBasicMaterial({ color: 0x00f3ff })
        );
        this.reticle.matrixAutoUpdate = false;
        this.reticle.visible = false;
        this.scene.add(this.reticle);

        this.controller = this.renderer.xr.getController(0);
        this.controller.addEventListener('select', this.onSelect.bind(this));
        this.scene.add(this.controller);
    }

    onSelect() {
        if (this.reticle.visible && this.avatarRoot) {
            // Place the avatar at the hit position
            this.avatarRoot.position.setFromMatrixPosition(this.reticle.matrix);
            // Hide the reticle after placement to lock the position
            this.reticle.visible = false;
            
            // Optionally, we could stop requesting hit test source here 
            // if we only want to place the avatar once.
            if (window.showMessage) {
                window.showMessage('Avatar Placed!', 'success');
            }
        }
    }

    update(frame) {
        if (!frame) return;

        const referenceSpace = this.renderer.xr.getReferenceSpace();
        const session = this.renderer.xr.getSession();

        if (this.hitTestSourceRequested === false) {
            session.requestReferenceSpace('viewer').then((viewerSpace) => {
                session.requestHitTestSource({ space: viewerSpace }).then((source) => {
                    this.hitTestSource = source;
                });
            });
            session.addEventListener('end', () => {
                this.hitTestSourceRequested = false;
                this.hitTestSource = null;
                this.reticle.visible = false;
            });
            this.hitTestSourceRequested = true;
        }

        if (this.hitTestSource) {
            const hitTestResults = frame.getHitTestResults(this.hitTestSource);
            if (hitTestResults.length > 0) {
                const hit = hitTestResults[0];
                const pose = hit.getPose(referenceSpace);

                // Only show reticle and update its position if we haven't already placed the avatar
                // To allow repositioning, we always keep the reticle active if we want.
                this.reticle.visible = true;
                this.reticle.matrix.fromArray(pose.transform.matrix);
            } else {
                this.reticle.visible = false;
            }
        }
    }
}

window.NexusHitTestManager = HitTestManager;
