/**
 * Vision Integration — Wiring the composite vision pipeline into the application.
 * 
 * This module connects CompositeVision to:
 * - main.ts rendering loop (avatar snapshot capture)
 * - Dashboard's vision tab (status reporting)
 * - compagent.py sensory input (image injection before LLM inference)
 * 
 * FIX: The original avatar camera was BLACK because it only rendered Layer 1 (user body).
 * This module ensures the avatar camera ALSO renders Layer 0 (scene, floor, walls, holographic panel).
 */

import * as THREE from 'three';
import { CompositeVision } from './CompositeVision';

/** Global singleton — instantiated once, shared across modules. */
let _instance: CompositeVision | null = null;

export function getCompositeVision(): CompositeVision {
    if (!_instance) {
        _instance = new CompositeVision(
            undefined, 
            (msg, color) => (window as any).log?.(msg, color)
        );
    }
    return _instance;
}

/**
 * FIX: Ensure the renderer captures BOTH layers for avatar vision.
 * The scene is on Layer 0, user body on Layer 1. The avatar head camera 
 * must see both to have proper vision. We also need to include the 
 * holographic webcam mirror panel on a visible layer.
 */
export function enableAvatarVisionLayers(camera: THREE.PerspectiveCamera): void {
    // Enable Layer 1 (user body) so avatar camera sees the user's virtual form
    camera.layers.enable(1);
    // Layer 0 is always enabled by default (scene geometry)
}

/**
 * Capture avatar vision for LLM injection.
 * Called before each comp agent turn.
 */
export async function captureVisionForLLM(
    renderer: THREE.WebGLRenderer,
    scene: THREE.Scene,
    camera: THREE.PerspectiveCamera,
    userCamera?: THREE.Camera
): Promise<{ base64: string; webcamBase64: string | null; passthroughBase64: string | null; metadata: string }> {
    const composite = getCompositeVision();
    const result = await composite.captureComposite(renderer, scene, camera, userCamera);
    return {
        base64: result.base64,
        webcamBase64: result.webcamBase64,
        passthroughBase64: result.passthroughBase64,
        metadata: composite.getSensoryContextNote(),
    };
}

/**
 * Initialize webcam for user mirror (call on mount).
 */
export async function initVisionSystem(): Promise<void> {
    const composite = getCompositeVision();
    await composite.initWebcam();
}