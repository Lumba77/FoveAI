import * as THREE from 'three';
import { FBXLoader } from 'three/examples/jsm/loaders/FBXLoader.js';
import { VRM } from '@pixiv/three-vrm';

const mixamoVRMRigMap: Record<string, string> = {
    'mixamorigHips': 'hips',
    'mixamorigSpine': 'spine',
    'mixamorigSpine1': 'chest',
    'mixamorigSpine2': 'upperChest',
    'mixamorigNeck': 'neck',
    'mixamorigHead': 'head',
    'mixamorigLeftShoulder': 'leftShoulder',
    'mixamorigLeftArm': 'leftUpperArm',
    'mixamorigLeftForeArm': 'leftLowerArm',
    'mixamorigLeftHand': 'leftHand',
    'mixamorigLeftHandThumb1': 'leftThumbMetacarpal',
    'mixamorigLeftHandThumb2': 'leftThumbProximal',
    'mixamorigLeftHandThumb3': 'leftThumbDistal',
    'mixamorigLeftHandIndex1': 'leftIndexProximal',
    'mixamorigLeftHandIndex2': 'leftIndexIntermediate',
    'mixamorigLeftHandIndex3': 'leftIndexDistal',
    'mixamorigLeftHandMiddle1': 'leftMiddleProximal',
    'mixamorigLeftHandMiddle2': 'leftMiddleIntermediate',
    'mixamorigLeftHandMiddle3': 'leftMiddleDistal',
    'mixamorigLeftHandRing1': 'leftRingProximal',
    'mixamorigLeftHandRing2': 'leftRingIntermediate',
    'mixamorigLeftHandRing3': 'leftRingDistal',
    'mixamorigLeftHandPinky1': 'leftLittleProximal',
    'mixamorigLeftHandPinky2': 'leftLittleIntermediate',
    'mixamorigLeftHandPinky3': 'leftLittleDistal',
    'mixamorigRightShoulder': 'rightShoulder',
    'mixamorigRightArm:': 'rightUpperArm',
    'mixamorigRightArm': 'rightUpperArm',
    'mixamorigRightForeArm': 'rightLowerArm',
    'mixamorigRightHand': 'rightHand',
    'mixamorigRightHandPinky1': 'rightLittleProximal',
    'mixamorigRightHandPinky2': 'rightLittleIntermediate',
    'mixamorigRightHandPinky3': 'rightLittleDistal',
    'mixamorigRightHandRing1': 'rightRingProximal',
    'mixamorigRightHandRing2': 'rightRingIntermediate',
    'mixamorigRightHandRing3': 'rightRingDistal',
    'mixamorigRightHandMiddle1': 'rightMiddleProximal',
    'mixamorigRightHandMiddle2': 'rightMiddleIntermediate',
    'mixamorigRightHandMiddle3': 'rightMiddleDistal',
    'mixamorigRightHandIndex1': 'rightIndexProximal',
    'mixamorigRightHandIndex2': 'rightIndexIntermediate',
    'mixamorigRightHandIndex3': 'rightIndexDistal',
    'mixamorigRightHandThumb1': 'rightThumbMetacarpal',
    'mixamorigRightHandThumb2': 'rightThumbProximal',
    'mixamorigRightHandThumb3': 'rightThumbDistal',
    'mixamorigLeftUpLeg': 'leftUpperLeg',
    'mixamorigLeftLeg': 'leftLowerLeg',
    'mixamorigLeftFoot': 'leftFoot',
    'mixamorigLeftToeBase': 'leftToes',
    'mixamorigRightUpLeg': 'rightUpperLeg',
    'mixamorigRightLeg': 'rightLowerLeg',
    'mixamorigRightFoot': 'rightFoot',
    'mixamorigRightToeBase': 'rightToes'
};

function findVRMBoneName(fbxBoneName: string): string | null {
    // Check exact Mixamo name first
    if (mixamoVRMRigMap[fbxBoneName]) {
        return mixamoVRMRigMap[fbxBoneName];
    }
    
    // Check ignoring namespace or case
    const lower = fbxBoneName.toLowerCase();
    for (const [key, value] of Object.entries(mixamoVRMRigMap)) {
        if (key.toLowerCase() === lower || lower.includes(key.toLowerCase().replace('mixamorig', ''))) {
            // Strict substring match: only if the name ends with the bone identifier
            const coreName = key.toLowerCase().replace('mixamorig', '');
            if (lower.endsWith(coreName)) return value;
        }
    }
    return null;
}

export async function loadMixamoAnimation(url: string, vrm: VRM): Promise<THREE.AnimationClip | null> {
    const loader = new FBXLoader();
    try {
        const asset = await loader.loadAsync(url);
        const clip = THREE.AnimationClip.findByName(asset.animations, 'mixamo.com') || asset.animations[0];
        
        if (!clip) return null;

        const tracks: THREE.KeyframeTrack[] = [];
        let mappedCount = 0;

        const restRotationInverse = new THREE.Quaternion();
        const parentRestWorldRotation = new THREE.Quaternion();
        const _quatA = new THREE.Quaternion();

        // Dynamically compute hips scale (Mixamo is usually in CM, VRM in Meters)
        let hipsPositionScale = 0.01;
        const mixamoHips = asset.getObjectByName('mixamorigHips') || asset.getObjectByName('Hips');
        if (mixamoHips && vrm.humanoid?.normalizedRestPose?.hips) {
            const motionHipsHeight = mixamoHips.position.y;
            const vrmHipsHeight = vrm.humanoid.normalizedRestPose.hips.position?.[1] ?? 1.0;
            if (motionHipsHeight > 0) hipsPositionScale = vrmHipsHeight / motionHipsHeight;
        }

        clip.tracks.forEach((track) => {
            const trackSplitted = track.name.split('.');
            const fbxBoneName = trackSplitted[0];
            const vrmBoneName = findVRMBoneName(fbxBoneName);
            const fbxNode = asset.getObjectByName(fbxBoneName);

            if (vrmBoneName && vrm.humanoid && fbxNode) {
                const vrmNode = vrm.humanoid.getNormalizedBoneNode(vrmBoneName as any);
                if (vrmNode) {
                    mappedCount++;
                    const vrmNodeName = vrmNode.name;
                    let propertyName = trackSplitted[1].toLowerCase();
                    
                    if (propertyName.includes('rotation') || propertyName.includes('quaternion')) {
                        propertyName = 'quaternion';
                    } else if (propertyName.includes('position') || propertyName.includes('translation')) {
                        propertyName = 'position';
                    } else if (propertyName.includes('scale')) {
                        propertyName = 'scale';
                    }

                    const trackName = `${vrmNodeName}.${propertyName}`;

                    // Extract FBX Rest Poses for Retargeting math
                    fbxNode.getWorldQuaternion(restRotationInverse).invert();
                    if (fbxNode.parent) {
                        fbxNode.parent.getWorldQuaternion(parentRestWorldRotation);
                    } else {
                        parentRestWorldRotation.identity();
                    }

                    if (track instanceof THREE.QuaternionKeyframeTrack || propertyName === 'quaternion') {
                        // Retarget the quaternion by transforming the FBX rotation into VRM Normalized space
                        for (let i = 0; i < track.values.length; i += 4) {
                            const flatQuaternion = track.values.slice(i, i + 4);
                            _quatA.fromArray(flatQuaternion as any);
                            // parentRestWorldRotation * TrackRotation * restRotationInverse
                            _quatA.premultiply(parentRestWorldRotation).multiply(restRotationInverse);
                            _quatA.toArray(track.values, i);
                        }
                        
                        // Handle possible VRM 0.0 model coordinate flip (Vrm 1.0 is default)
                        const isVrm0 = (vrm.meta as any)?.metaVersion === '0';
                        const finalValues = track.values.map((v, i) => (isVrm0 && i % 2 === 0 ? -v : v));

                        tracks.push(new THREE.QuaternionKeyframeTrack(trackName, track.times, finalValues as any));
                    } else if (propertyName === 'position') {
                        // FORCE DISABLE ALL POSITION TRACKS to prevent flying off scene!
                        // This forces animations to be "in-place", which is safest.
                        return;
                    }
                }
            }
        });

        console.log(`[FBX Loader] Retargeted ${mappedCount}/${clip.tracks.length} tracks to VRM for ${url}`);
        if (tracks.length === 0) return null;

        return new THREE.AnimationClip(clip.name || 'RetargetedFBX', clip.duration, tracks);
    } catch (e) {
        console.error('Failed to load FBX', e);
        return null;
    }
}
