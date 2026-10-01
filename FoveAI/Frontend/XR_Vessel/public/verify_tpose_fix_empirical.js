
/**
 * EMPIRICAL VERIFICATION SCRIPT
 * This script verifies the T-pose fix by checking bone rotations in the procedural idle.
 */

async function verifyTPoseFix() {
    console.log('--- STARTING EMPIRICAL VERIFICATION ---');
    
    // 1. Check if AvatarManager is available
    if (!window.foveaiAvatar) {
        console.error('FAILED: AvatarManager (foveaiAvatar) not found on window object.');
        return;
    }
    const avatar = window.foveaiAvatar;

    // 2. Check if VRM is loaded
    if (!avatar.vrm) {
        console.error('FAILED: VRM model not loaded in AvatarManager.');
        return;
    }
    const humanoid = avatar.vrm.humanoid;

    // 3. Inspect Procedural Idle Posing
    console.log('Step 1: Inspecting Procedural Idle Posing...');
    const clip = avatar.createProceduralIdleClip();
    if (!clip) {
        console.error('FAILED: Could not generate procedural idle clip.');
        return;
    }

    const leftArmTrack = clip.tracks.find(t => t.name.includes('leftUpperArm.quaternion'));
    const rightArmTrack = clip.tracks.find(t => t.name.includes('rightUpperArm.quaternion'));

    if (leftArmTrack && rightArmTrack) {
        console.log('✓ Procedural Idle contains arm tracks.');
        
        // Extract sample quaternion values from the track
        // Values are [x, y, z, w]
        const lVals = leftArmTrack.values.slice(0, 4);
        const rVals = rightArmTrack.values.slice(0, 4);
        
        const lQuat = new THREE.Quaternion(lVals[0], lVals[1], lVals[2], lVals[3]);
        const rQuat = new THREE.Quaternion(rVals[0], rVals[1], rVals[2], rVals[3]);
        
        const lEuler = new THREE.Euler().setFromQuaternion(lQuat);
        const rEuler = new THREE.Euler().setFromQuaternion(rQuat);

        console.log(`Left Arm Z-Rotation: ${lEuler.z.toFixed(2)} rad`);
        console.log(`Right Arm Z-Rotation: ${rEuler.z.toFixed(2)} rad`);

        if (Math.abs(lEuler.z) > 1.0 && Math.abs(rEuler.z) > 1.0) {
            console.log('SUCCESS: Arms are posed DOWN in procedural idle (not T-pose).');
        } else {
            console.error('FAILED: Arms are still in T-pose positions (rotation near 0).');
        }
    } else {
        console.error('FAILED: Procedural idle is missing arm tracks.');
    }

    // 4. Verify BVH Loader Protection
    console.log('Step 2: Verifying BVH Loader HTML Protection...');
    const corruptedUrl = '/Animations/BVH/neutral_idle.bvh'; // Known corrupted file
    const bvhResult = await avatar.playAnimation(corruptedUrl);
    
    // We expect this to fail gracefully or not play a BVH action
    // In our logs we should see "[BVH Loader] INVALID BVH FILE"
    console.log('Check browser console for: "[BVH Loader] INVALID BVH FILE: ... is actually an HTML page"');

    // 5. Check T-Pose Warning System status
    const status = avatar.getTposeStatus();
    console.log('T-Pose Warning System Status:', status);
    
    if (status.isCritical) {
        console.warn('WARNING: T-Pose system still reports critical state. Checking reasons...');
        const diagnostics = avatar.tposeWarningSystem.getDiagnostics();
        console.log('Diagnostics:', diagnostics.status.detectionTimer, diagnostics.bonePositions);
    } else {
        console.log('✓ T-Pose Warning System is clear.');
    }

    console.log('--- VERIFICATION COMPLETE ---');
}

// Attach to window for easy manual trigger if needed
window.runEmpiricalVerification = verifyTPoseFix;
verifyTPoseFix();
