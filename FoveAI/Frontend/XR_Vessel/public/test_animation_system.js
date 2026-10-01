// Test script to verify animation system is working
// Run this in the browser console to test avatar animations

console.log('=== FoveAI Animation System Test ===');

// Check if avatar manager is available
if (typeof window.foveaiAvatar === 'undefined') {
    console.warn('Avatar manager not found. Waiting for initialization...');
    setTimeout(() => {
        if (window.foveaiAvatar) {
            console.log('Avatar manager loaded!');
            testAnimationSystem();
        } else {
            console.error('Avatar manager failed to load after timeout');
        }
    }, 5000);
} else {
    testAnimationSystem();
}

function testAnimationSystem() {
    const avatar = window.foveaiAvatar;
    
    if (!avatar) {
        console.error('Avatar manager not available');
        return;
    }
    
    console.log('Testing avatar animation system...');
    
    // Test 1: Check if VRM is loaded
    if (!avatar.vrm) {
        console.error('VRM model not loaded');
        return;
    }
    console.log('✓ VRM model loaded');
    
    // Test 2: Check if mixer is available
    if (!avatar.mixer) {
        console.error('Animation mixer not available');
        return;
    }
    console.log('✓ Animation mixer available');
    
    // Test 3: Try to play a simple animation
    console.log('Testing animation playback...');
    
    // Try to play an idle animation
    avatar.playCategory('Idle', true, 0.3)
        .then(() => {
            console.log('✓ Idle animation playing successfully');
        })
        .catch((error) => {
            console.warn('Idle animation failed, trying nuclear reset...', error);
            // Try nuclear reset as fallback
            avatar.nuclearReset();
            setTimeout(() => {
                avatar.playCategory('Idle', true, 0.1)
                    .then(() => console.log('✓ Idle animation playing after reset'))
                    .catch(() => console.error('All animation attempts failed'));
            }, 1000);
        });
    
    // Test 4: Check procedural animations
    console.log('Testing procedural animations...');
    const chest = avatar.vrm.humanoid?.getRawBoneNode('chest');
    const hips = avatar.vrm.humanoid?.getRawBoneNode('hips');
    
    if (chest || hips) {
        console.log('✓ Procedural animation bones accessible');
    } else {
        console.warn('Procedural animation bones not accessible');
    }
    
    console.log('=== Animation System Test Complete ===');
}

// Auto-run the test
// testAnimationSystem(); // Disabled to prevent automatic animation cycling
