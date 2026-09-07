import fs from 'fs';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { VRMLoaderPlugin } from '@pixiv/three-vrm';

// Create a minimal mock for GLTFLoader to work in node
const toArrayBuffer = (buffer) => {
    const ab = new ArrayBuffer(buffer.length);
    const view = new Uint8Array(ab);
    for (let i = 0; i < buffer.length; ++i) {
        view[i] = buffer[i];
    }
    return ab;
};

async function checkVRMBones() {
    console.log("Loading alicechan.vrm manually to check bone structures...");
    
    // Instead of using GLTFLoader, let's just parse the GLB structure manually 
    // to check the extensions.VRM.humanoid.humanBones
    const buffer = fs.readFileSync('public/alicechan.vrm');
    
    let chunkLength = buffer.readUInt32LE(12);
    let chunkType = buffer.readUInt32LE(16);
    
    if (chunkType === 0x4E4F534A) { // 'JSON'
        const jsonBuffer = buffer.slice(20, 20 + chunkLength);
        const jsonString = jsonBuffer.toString('utf8');
        const gltf = JSON.parse(jsonString);
        
        console.log("Found GLTF JSON!");
        
        const vrm0 = gltf.extensions?.VRM;
        const vrm1 = gltf.extensions?.VRMC_vrm;
        
        let humanBones = [];
        if (vrm0) {
            console.log("Model is VRM 0.0");
            humanBones = vrm0.humanoid?.humanBones || [];
            humanBones.forEach(b => {
                const nodeIndex = b.node;
                const node = gltf.nodes[nodeIndex];
                console.log(`Bone: ${b.bone} -> Node: ${node.name} (ID: ${nodeIndex})`);
            });
        } else if (vrm1) {
            console.log("Model is VRM 1.0");
            const bonesObj = vrm1.humanoid?.humanBones || {};
            for (const [boneName, b] of Object.entries(bonesObj)) {
                const nodeIndex = b.node;
                const node = gltf.nodes[nodeIndex];
                console.log(`Bone: ${boneName} -> Node: ${node.name} (ID: ${nodeIndex})`);
            }
        } else {
            console.log("No VRM extension found!");
        }
        
    }
}

checkVRMBones();
