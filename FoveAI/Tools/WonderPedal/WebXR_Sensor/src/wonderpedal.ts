import { createSystem, Types, createComponent } from '@iwsdk/core';
import * as THREE from 'three';

// A simple component to mark our pedal entity
export const WonderPedal = createComponent('WonderPedal', {
    type: { type: Types.String, default: 'kick' }
});

export class WonderPedalSystem extends createSystem({
    pedals: { required: [WonderPedal] }
}) {
    private ws: WebSocket | null = null;
    
    // Tracking state for the Knees
    private lastRightKneeY: number = 0;
    private lastLeftKneeY: number = 0;
    private maxRightVelocity: number = 0;
    private maxLeftVelocity: number = 0;
    private isRightFalling: boolean = false;
    private isLeftFalling: boolean = false;
    private rightCooldown: number = 0;
    private leftCooldown: number = 0;
    private VELOCITY_THRESHOLD: number = 0.15; // meters per second (lowered for sensitivity)
    
    // Jen AR Entity State
    private jenOrb: THREE.Mesh | null = null;
    private jenGlow: number = 0;
    private recognition: any = null;

    init() {
        console.log("WonderPedal Body Tracking System Initializing...");
        this.spawnVirtualPedal();
        this.spawnJenOrb();
        this.connectToBridge();
        this.setupSpeechRecognition();
    }

    spawnVirtualPedal() {
        const geometry = new THREE.BoxGeometry(0.15, 0.05, 0.25);
        
        // Sleek brushed metal and rubber/dark mesh grip
        const metalMaterial = new THREE.MeshStandardMaterial({ 
            color: 0x333333, 
            roughness: 0.4, 
            metalness: 0.8 
        });
        
        const rubberGripMaterial = new THREE.MeshStandardMaterial({ 
            color: 0x111111, 
            roughness: 0.9, 
            metalness: 0.1 
        });

        const materials = [
            metalMaterial,      // right
            metalMaterial,      // left
            rubberGripMaterial, // top (sturdy grip)
            metalMaterial,      // bottom
            metalMaterial,      // front
            metalMaterial,      // back
        ];

        const mesh = new THREE.Mesh(geometry, materials);
        const entity = this.world.createTransformEntity(mesh);
        entity.object3D!.position.set(0, 0.025, -0.4); 
        
        entity.addComponent(WonderPedal, { type: 'kick' });
        console.log("Sleek Dark Virtual Pedal Mesh Spawned in AR Space.");
    }

    spawnJenOrb() {
        const geometry = new THREE.SphereGeometry(0.1, 32, 32);
        const material = new THREE.MeshBasicMaterial({ 
            color: 0x00FFFF, 
            transparent: true,
            opacity: 0.8
        });
        this.jenOrb = new THREE.Mesh(geometry, material);
        const entity = this.world.createTransformEntity(this.jenOrb);
        // Float her near the drum kit
        entity.object3D!.position.set(0.5, 1.2, -0.6); 
        console.log("Jen Orb Spawned in AR Space.");
    }

    setupSpeechRecognition() {
        const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
        if (SpeechRecognition) {
            this.recognition = new SpeechRecognition();
            this.recognition.continuous = true;
            this.recognition.interimResults = false;
            
            this.recognition.onresult = (event: any) => {
                const transcript = event.results[event.results.length - 1][0].transcript.trim();
                console.log("[Jen AR] Heard:", transcript);
                if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                    this.ws.send(JSON.stringify({ speech: transcript }));
                    // Make her blink when listening
                    if (this.jenOrb) {
                        (this.jenOrb.material as THREE.MeshBasicMaterial).color.setHex(0xFF00FF);
                    }
                }
            };
            
            this.recognition.onend = () => {
                // Keep her listening forever
                this.recognition.start();
            };
            
            this.recognition.start();
            console.log("[Jen AR] Ears online (Speech Recognition started).");
        } else {
            console.warn("Speech Recognition API not supported in this browser.");
        }
    }

    connectToBridge() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws`;
        this.ws = new WebSocket(wsUrl);
        this.ws.onopen = () => console.log(`Connected to Wonder Pedal Bridge at ${wsUrl}`);
        this.ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.jen_reply) {
                    console.log("[Jen AR] Speaking:", data.jen_reply);
                    const utterance = new SpeechSynthesisUtterance(data.jen_reply);
                    utterance.pitch = 1.2;
                    utterance.rate = 1.1;
                    
                    // Reset orb color to cyan and speak
                    if (this.jenOrb) {
                        (this.jenOrb.material as THREE.MeshBasicMaterial).color.setHex(0x00FFFF);
                    }
                    window.speechSynthesis.speak(utterance);
                }
            } catch (e) {
                console.error("Error parsing websocket message", e);
            }
        };
        this.ws.onclose = () => console.log("Disconnected from Bridge.");
    }

    sendTrigger(type: string) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({ trigger: type }));
            
            this.queries.pedals.entities.forEach(entity => {
                const mesh = entity.object3D as THREE.Mesh;
                if (mesh) {
                    mesh.position.y -= 0.02; 
                    setTimeout(() => { mesh.position.y += 0.02; }, 100);
                }
            });
        }
    }

    update(delta: number) {
        if (this.rightCooldown > 0) this.rightCooldown -= delta;
        if (this.leftCooldown > 0) this.leftCooldown -= delta;

        // Animate Jen Orb breathing
        if (this.jenOrb) {
            this.jenGlow += delta * 2;
            const scale = 1.0 + Math.sin(this.jenGlow) * 0.1;
            this.jenOrb.scale.set(scale, scale, scale);
            this.jenOrb.position.y = 1.2 + Math.sin(this.jenGlow * 0.5) * 0.05;
        }

        const session = this.world.xrSession as any;
        const frame = this.world.renderer.xr.getFrame() as any;
        const refSpace = this.world.renderer.xr.getReferenceSpace() as any;

        if (!session || !frame || !refSpace) return;

        // Experimental WebXR Body Tracking API
        let bodyInputSource = null;
        for (const source of session.inputSources) {
            // Some implementations expose body via an input source
            if (source.body) {
                bodyInputSource = source;
                break;
            }
        }

        // Check if frame.body exists (WebXR spec proposal) or if it's attached to an input source
        const bodyTracker = frame.body || (bodyInputSource ? bodyInputSource.body : null);

        if (bodyTracker) {
            // Get Right Knee / Lower Leg
            const rightKneeJoint = bodyTracker.get('right-lower-leg') || bodyTracker.get('right-upper-leg') || bodyTracker.get('right-foot');
            if (rightKneeJoint) {
                const pose = frame.getJointPose(rightKneeJoint, refSpace);
                if (pose) {
                    const currentY = pose.transform.position.y;
                    this.processVelocity(currentY, delta, 'right');
                }
            }

            // Get Left Knee / Lower Leg
            const leftKneeJoint = bodyTracker.get('left-lower-leg') || bodyTracker.get('left-upper-leg') || bodyTracker.get('left-foot');
            if (leftKneeJoint) {
                const pose = frame.getJointPose(leftKneeJoint, refSpace);
                if (pose) {
                    const currentY = pose.transform.position.y;
                    this.processVelocity(currentY, delta, 'left');
                }
            }
        }
    }

    processVelocity(currentY: number, delta: number, side: 'right' | 'left') {
        const isRight = side === 'right';
        const lastY = isRight ? this.lastRightKneeY : this.lastLeftKneeY;
        let maxVelocity = isRight ? this.maxRightVelocity : this.maxLeftVelocity;
        let isFalling = isRight ? this.isRightFalling : this.isLeftFalling;
        const cooldown = isRight ? this.rightCooldown : this.leftCooldown;

        if (lastY > 0 && delta > 0 && cooldown <= 0) {
            const velocity = (currentY - lastY) / delta;
            
            if (velocity < -0.05) {
                isFalling = true;
                if (Math.abs(velocity) > maxVelocity) {
                    maxVelocity = Math.abs(velocity);
                }
            } else if (velocity >= 0 && isFalling) {
                // Bounce detected!
                if (maxVelocity > this.VELOCITY_THRESHOLD) {
                    console.log(`[Body Tracking] ${side.toUpperCase()} KNEE STRIKE! Velocity: ${maxVelocity.toFixed(2)}`);
                    this.sendTrigger(isRight ? 'kick' : 'hihat');
                    if (isRight) this.rightCooldown = 0.2;
                    else this.leftCooldown = 0.2;
                }
                isFalling = false;
                maxVelocity = 0;
            }
        }

        if (isRight) {
            this.lastRightKneeY = currentY;
            this.maxRightVelocity = maxVelocity;
            this.isRightFalling = isFalling;
        } else {
            this.lastLeftKneeY = currentY;
            this.maxLeftVelocity = maxVelocity;
            this.isLeftFalling = isFalling;
        }
    }
}

window.addEventListener('keydown', (e) => {
    if (e.code === 'Space') {
        const event = new CustomEvent('pedalTrigger', { detail: 'kick' });
        window.dispatchEvent(event);
    }
});
