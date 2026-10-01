import fs from 'fs';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { VRMLoaderPlugin } from '@pixiv/three-vrm';

// Function to inspect VRM
async function inspectVRM() {
    console.log("Inspecting alicechan.vrm...");
    try {
        // Just read the binary and try to parse the JSON chunk to find animation names
        const buffer = fs.readFileSync('public/alicechan.vrm');
        const magic = buffer.readUInt32LE(0);
        if (magic !== 0x46546C67) { // 'glTF'
            console.log("Not a valid GLB/VRM file.");
            return;
        }

        const version = buffer.readUInt32LE(4);
        const length = buffer.readUInt32LE(8);
        
        let chunkLength = buffer.readUInt32LE(12);
        let chunkType = buffer.readUInt32LE(16);
        
        if (chunkType === 0x4E4F534A) { // 'JSON'
            const jsonBuffer = buffer.slice(20, 20 + chunkLength);
            const jsonString = jsonBuffer.toString('utf8');
            const gltf = JSON.parse(jsonString);
            
            if (gltf.animations) {
                console.log(`Found ${gltf.animations.length} animations in the GLTF JSON chunk:`);
                gltf.animations.forEach((anim, i) => {
                    console.log(`  [${i}] ${anim.name}`);
                });
            } else {
                console.log("No built-in animations array found in GLTF JSON.");
            }
            
            if (gltf.extensions && gltf.extensions.VRMC_vrm && gltf.extensions.VRMC_vrm.expressions) {
                console.log("VRM Expressions available.");
            }
            
        } else {
            console.log("First chunk is not JSON.");
        }
        
    } catch (e) {
        console.error("Failed to inspect:", e);
    }
}

inspectVRM();
