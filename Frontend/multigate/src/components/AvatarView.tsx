import React, { useEffect, useRef, useState } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { AvatarManager } from '../avatar/AvatarManager';
import * as THREE from 'three';

function AvatarScene({ avatarManager, url }: { avatarManager: AvatarManager, url: string }) {
    const { scene, camera } = useThree();
    const [loaded, setLoaded] = useState(false);

    useEffect(() => {
        let isMounted = true;
        // Basic lighting for VRM
        const ambient = new THREE.AmbientLight(0xffffff, 0.8);
        const dir = new THREE.DirectionalLight(0xffffff, 1.2);
        dir.position.set(2, 5, 2);
        scene.add(ambient, dir);

        console.log("Loading Avatar:", url);
        avatarManager.loadAvatar(url, scene).then(() => {
            if (isMounted) setLoaded(true);
        }).catch(err => {
            console.error("Failed to load avatar:", err);
        });

        return () => {
            isMounted = false;
            avatarManager.sweepScene();
            scene.remove(ambient, dir);
        };
    }, [url, scene, avatarManager]);

    useFrame((state, delta) => {
        if (loaded) {
            avatarManager.update(delta, state.camera);
        }
    });

    return null;
}

export function AvatarView({ mode = 'still' }: { mode?: 'still' | 'video' }) {
    const avatarRef = useRef<AvatarManager | null>(null);
    if (!avatarRef.current) {
        avatarRef.current = new AvatarManager();
    }

    return (
        <div style={{ 
            width: '100%', 
            height: '100%', 
            position: 'relative', 
            zIndex: 10 
        }}>
            {mode === 'still' ? (
                <img src="/avatars/jen_still.png" alt="Jen" className="ai-avatar-image" onError={(e) => (e.currentTarget.src = '/avatars/fallback.png')} />
            ) : (
                <Canvas camera={{ position: [0, 1.4, 1.0], fov: 40 }}>
                    <AvatarScene 
                        avatarManager={avatarRef.current} 
                        url="/avatars/alicechan.vrm" 
                    />
                </Canvas>
            )}
        </div>
    );
}
