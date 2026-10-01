'use strict';

/**
 * DesktopLocomotionPointer.js
 * ====================================================================
 * Listens for double-clicks on the 3D canvas when not in VR.
 * Casts a ray to the floor plane and commands the AvatarLocomotionSystem
 * to walk to that point.
 */
(function () {
    var THREE = window.THREE;
    if (!THREE) return;

    var raycaster = new THREE.Raycaster();
    var mouse = new THREE.Vector2();
    var floorPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0); // Y=0 plane
    var active = false;

    function onDoubleClick(event) {
        // Only run if locomotion is enabled
        var config = window.NEXUS_LOCOMOTION_CONFIG;
        if (!config || !config.isEnabled()) return;

        var viewer = window.NEXUS_VIEWER;
        if (!viewer || !viewer.camera || !viewer.renderer) return;

        // Skip if in VR
        if (viewer.renderer.xr && viewer.renderer.xr.isPresenting) return;

        var loco = window.NEXUS_LOCOMOTION;
        if (!loco || typeof loco.walkToPoint !== 'function') return;

        // Calculate mouse position in normalized device coordinates
        var rect = viewer.renderer.domElement.getBoundingClientRect();
        mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
        mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

        // Raycast
        raycaster.setFromCamera(mouse, viewer.camera);
        var intersectPoint = new THREE.Vector3();
        raycaster.ray.intersectPlane(floorPlane, intersectPoint);

        if (intersectPoint) {
            console.log('[DesktopLocomotionPointer] Walk to:', intersectPoint.x.toFixed(2), intersectPoint.z.toFixed(2));
            loco.walkToPoint(intersectPoint.x, intersectPoint.z);
            
            // Show a visual indicator (optional, but good for feedback)
            showClickIndicator(intersectPoint, viewer.scene);
        }
    }

    function showClickIndicator(pos, scene) {
        var geo = new THREE.RingGeometry(0.1, 0.15, 32);
        geo.rotateX(-Math.PI / 2);
        var mat = new THREE.MeshBasicMaterial({ color: 0x00ffaa, transparent: true, opacity: 0.8, side: THREE.DoubleSide });
        var mesh = new THREE.Mesh(geo, mat);
        mesh.position.copy(pos);
        mesh.position.y = 0.01; // slightly above floor to prevent z-fighting
        scene.add(mesh);

        // Simple animation
        var scale = 1;
        var start = performance.now();
        function animate() {
            var elapsed = performance.now() - start;
            if (elapsed > 500) {
                scene.remove(mesh);
                geo.dispose();
                mat.dispose();
                return;
            }
            var progress = elapsed / 500;
            mesh.scale.setScalar(1 + progress * 2);
            mat.opacity = 0.8 * (1 - progress);
            requestAnimationFrame(animate);
        }
        animate();
    }

    // Attach to viewer canvas once it's ready
    function init() {
        if (active) return;
        var viewer = window.NEXUS_VIEWER;
        if (viewer && viewer.renderer && viewer.renderer.domElement) {
            viewer.renderer.domElement.addEventListener('dblclick', onDoubleClick);
            active = true;
            console.log('[DesktopLocomotionPointer] Initialized 2D click-to-walk listener');
        } else {
            setTimeout(init, 500); // Retry
        }
    }

    // Start checking when DOM loads
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
