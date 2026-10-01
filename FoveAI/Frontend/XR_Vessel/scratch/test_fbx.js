import fs from 'fs';
import * as THREE from 'three';
import { FBXLoader } from 'three/examples/jsm/loaders/FBXLoader.js';

// Create a mock DOM for three.js headless
global.window = {};
global.document = {};
global.self = global.window;

const toArrayBuffer = (buffer) => {
    const ab = new ArrayBuffer(buffer.length);
    const view = new Uint8Array(ab);
    for (let i = 0; i < buffer.length; ++i) {
        view[i] = buffer[i];
    }
    return ab;
};

async function testFBX() {
    console.log("Loading Arnold_Idle.fbx...");
    const buffer = fs.readFileSync('public/Animations/FBX/Arnold_Idle.fbx');
    const arrayBuffer = toArrayBuffer(buffer);
    
    const loader = new FBXLoader();
    try {
        const asset = loader.parse(arrayBuffer, '');
        const clip = asset.animations[0];
        if (!clip) {
            console.log("No animation found");
            return;
        }
        
        console.log(`Clip duration: ${clip.duration}, Tracks: ${clip.tracks.length}`);
        let mapped = 0;
        clip.tracks.forEach(track => {
            const trackSplitted = track.name.split('.');
            const fbxBoneName = trackSplitted[0];
            const normalizedName = fbxBoneName.toLowerCase().replace(/[^a-z0-9]/g, '');
            console.log(`Track: ${track.name} -> Normalized: ${normalizedName}`);
        });
    } catch (e) {
        console.error("Failed to parse FBX:", e);
    }
}

testFBX();