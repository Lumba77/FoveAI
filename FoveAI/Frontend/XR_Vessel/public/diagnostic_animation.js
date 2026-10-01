
(function() {
    console.log("%c--- FoveAI AVATAR DIAGNOSTIC ---", "color: #39ff14; font-weight: bold; font-size: 14px;");
    
    const avatar = window.foveaiAvatar || window.avatarManager;
    if (!avatar) {
        console.error("❌ Avatar Manager not found on window.foveaiAvatar or window.avatarManager");
        return;
    }

    console.log("✅ Avatar Manager found");
    
    if (!avatar.vrm) {
        console.error("❌ VRM not loaded in Avatar Manager");
    } else {
        console.log("✅ VRM loaded:", avatar.vrm.meta?.name || "unnamed");
        console.log("   Scene visible:", avatar.vrm.scene.visible);
        console.log("   Position:", avatar.vrm.scene.position.toArray());
    }

    if (!avatar.mixer) {
        console.error("❌ AnimationMixer not found");
    } else {
        console.log("✅ AnimationMixer exists");
        console.log("   Stats:", avatar.mixer.stats);
    }

    if (avatar.currentAction) {
        const action = avatar.currentAction;
        const clip = action.getClip();
        console.log("✅ Current Action:", clip.name);
        console.log("   Is Running:", action.isRunning());
        console.log("   Weight:", action.getEffectiveWeight());
        console.log("   Time:", action.time);
        console.log("   Loop Mode:", action.loop === 1 ? "LoopRepeat" : "LoopOnce");
    } else {
        console.warn("⚠️ No currentAction playing");
    }

    if (avatar.idleAction) {
        console.log("✅ Idle Action found:", avatar.idleAction.getClip().name);
        console.log("   Is Running:", avatar.idleAction.isRunning());
    } else {
        console.warn("⚠️ No idleAction found");
    }

    if (avatar.getTposeStatus) {
        const status = avatar.getTposeStatus();
        console.log("%c--- T-POSE STATUS ---", "color: #ff007f; font-weight: bold;");
        console.log("   Is Critical:", status.isCritical ? "🚨 YES" : "✅ NO");
        console.log("   Error Count:", status.errorCount);
        console.log("   Detection Timer:", status.detectionTimer.toFixed(2), "s");
    }

    console.log("%c--- RECOMMENDATIONS ---", "color: #00f3ff; font-weight: bold;");
    if (!avatar.currentAction || !avatar.currentAction.isRunning()) {
        console.log("👉 Suggestion: Run 'window.foveaiAvatar.nuclearReset()' to force idle recovery.");
    } else if (avatar.getTposeStatus && avatar.getTposeStatus().isCritical) {
        console.log("👉 Suggestion: T-pose detected! Run 'window.foveaiAvatar.nuclearReset()' or check bone rotations.");
    } else {
        console.log("👉 Everything seems configured correctly. If still T-posing, check bone retargeting in FBX/BVH.");
    }
})();
