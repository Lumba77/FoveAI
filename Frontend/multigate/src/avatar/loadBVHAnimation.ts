import * as THREE from 'three';
import { BVHLoader } from 'three/examples/jsm/loaders/BVHLoader.js';
import { VRM } from '@pixiv/three-vrm';

const bvhVRMRigMap: Record<string, string> = {
    // Standard BVH (Mixamo, CMU) — lowercase
    'hip': 'hips',
    'abdomen': 'spine',
    'chest': 'chest',
    'neck': 'neck',
    'head': 'head',
    'lCollar': 'leftShoulder',
    'lShldr': 'leftUpperArm',
    'lForeArm': 'leftLowerArm',
    'lHand': 'leftHand',
    'rCollar': 'rightShoulder',
    'rShldr': 'rightUpperArm',
    'rForeArm': 'rightLowerArm',
    'rHand': 'rightHand',
    'lThigh': 'leftUpperLeg',
    'lShin': 'leftLowerLeg',
    'lFoot': 'leftFoot',
    'lToe': 'leftToes',
    'rThigh': 'rightUpperLeg',
    'rShin': 'rightLowerLeg',
    'rFoot': 'rightFoot',
    'rToe': 'rightToes',
    // Bandai-Namco Research — PascalCase
    'Hips': 'hips',
    'Spine': 'spine',
    'Chest': 'chest',
    'UpperChest': 'upperChest',
    'Neck': 'neck',
    'Head': 'head',
    'Shoulder_L': 'leftShoulder',
    'UpperArm_L': 'leftUpperArm',
    'LowerArm_L': 'leftLowerArm',
    'Hand_L': 'leftHand',
    'Shoulder_R': 'rightShoulder',
    'UpperArm_R': 'rightUpperArm',
    'LowerArm_R': 'rightLowerArm',
    'Hand_R': 'rightHand',
    'UpperLeg_L': 'leftUpperLeg',
    'LowerLeg_L': 'leftLowerLeg',
    'Foot_L': 'leftFoot',
    'Toe_L': 'leftToes',
    'UpperLeg_R': 'rightUpperLeg',
    'LowerLeg_R': 'rightLowerLeg',
    'Foot_R': 'rightFoot',
    'Toe_R': 'rightToes',
    'joint_Root': 'hips',
};

/** Case-insensitive lookup: exact match first, then fallback */
function resolveBVHBoneName(bvhBoneName: string): string | null {
    if (bvhVRMRigMap[bvhBoneName]) return bvhVRMRigMap[bvhBoneName];
    const lower = bvhBoneName.toLowerCase();
    for (const [key, value] of Object.entries(bvhVRMRigMap)) {
        if (key.toLowerCase() === lower) return value;
    }
    return null;
}

export async function loadBVHAnimation(url: string, vrm: VRM): Promise<THREE.AnimationClip | null> {
    console.log(`[BVH Loader] ATTEMPTING TO LOAD: ${url}`);
    
    try {
        const response = await fetch(url);
        const text = await response.text();
        
        // SAFETY CHECK: Ensure we didn't get a 404 HTML page or error redirect
        if (text.includes('<!DOCTYPE') || text.includes('<html') || text.trim().startsWith('{')) {
            console.error(`[BVH Loader] INVALID CONTENT DETECTED for ${url}. Aborting parse.`);
            return null;
        }

        const loader = new BVHLoader();
        const result = loader.parse(text);
        const clip = result.clip;
        
        if (!clip || !result.skeleton) return null;

        const tracks: THREE.KeyframeTrack[] = [];
        let mappedCount = 0;


        // (hips height auto-mapping removed — computed scale was never applied)

        clip.tracks.forEach((track) => {
            const trackSplitted = track.name.split('.');
            const bvhBoneName = trackSplitted[0];
            const vrmBoneName = resolveBVHBoneName(bvhBoneName);
            const bvhNode = result.skeleton.bones.find((b: any) => b.name === bvhBoneName);

            if (vrmBoneName && vrm.humanoid && bvhNode) {
                // BVH files often match raw VRM bones better than normalized math
                const vrmNode = vrm.humanoid.getRawBoneNode(vrmBoneName as any) || vrm.humanoid.getNormalizedBoneNode(vrmBoneName as any);
                if (vrmNode) {
                    mappedCount++;
                    const vrmNodeName = vrmNode.name;
                    let propertyName = trackSplitted[1].toLowerCase();

                    if (propertyName.includes('rotation') || propertyName.includes('quaternion')) {
                        propertyName = 'quaternion';
                    } else if (propertyName.includes('position') || propertyName.includes('translation')) {
                        // FORCE DISABLE ALL POSITION TRACKS to prevent flying off scene!
                        return; 
                    }

                    const trackName = `${vrmNodeName}.${propertyName}`;
                    
                    if (track instanceof THREE.QuaternionKeyframeTrack || propertyName === 'quaternion') {
                        // Push raw BVH rotation to raw VRM bone (no complex math, to stop limbs twisting)
                        tracks.push(new THREE.QuaternionKeyframeTrack(trackName, track.times, track.values));
                    }
                }
            }
        });

        console.log(`[BVH Loader] Mapped ${mappedCount}/${clip.tracks.length} tracks for ${url}`);
        if (tracks.length === 0) return null;

        return new THREE.AnimationClip('RetargetedBVH', clip.duration, tracks);
    } catch (e) {
        console.error(`[BVH Loader] ERROR: ${url}`, e);
        return null;
    }
}
