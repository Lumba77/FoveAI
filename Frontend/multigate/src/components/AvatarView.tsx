import { useEffect, useRef, useState } from 'react';
import { useLipsync } from '../hooks/useLipsync';
import { AvatarPerformance } from '../avatar/AvatarPerformance';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { AvatarManager } from '../avatar/AvatarManager';
import * as THREE from 'three';

function AvatarScene({ avatarManager, url, vrmRef, isLive = false }:
    { avatarManager: AvatarManager; url: string; vrmRef?: React.MutableRefObject<any>; isLive?: boolean }) {
    const { scene } = useThree();
    const [loaded, setLoaded] = useState(false);

    useEffect(() => {
        let isMounted = true;
        const ambient = new THREE.AmbientLight(0xffffff, 0.8);
        const dir = new THREE.DirectionalLight(0xffffff, 1.2);
        dir.position.set(2, 5, 2);
        scene.add(ambient, dir);

        console.log("Loading Avatar:", url);
        avatarManager.externalPerformance = isLive;
        avatarManager.loadAvatar(url, scene).then(() => {
            if (vrmRef) vrmRef.current = (avatarManager as any).vrm ?? null;
            if (isMounted) setLoaded(true);
        }).catch(err => {
            console.error("Failed to load avatar:", err);
        });

        return () => {
            isMounted = false;
            avatarManager.sweepScene();
            scene.remove(ambient, dir);
        };
    }, [url, scene, avatarManager, vrmRef, isLive]);

    useFrame((state, delta) => {
        if (loaded) {
            avatarManager.update(delta, state.camera);
        }
    });

    return null;
}

const VIDEO_MODES = new Set(['Video PTT', 'Video VAD']);

export function AvatarView({ mode = 'still', avatarUrl = '/avatars/jen.vrm', stillSrc }:
    { mode?: 'still' | 'live' | 'video' | 'DICTATE' | 'Vocal PTT' | 'Vocal VAD' | 'Video PTT' | 'Video VAD';
      avatarUrl?: string;
      /* The AI's portrait. The still frame used to be a hardcoded file, so a
         picture uploaded through the portrait picker was fetched and then
         never displayed — the same face forever. */
      stillSrc?: string | null }) {
    const avatarRef = useRef<AvatarManager | null>(null);
    if (!avatarRef.current) {
        avatarRef.current = new AvatarManager();
    }

    const isVideoMode = VIDEO_MODES.has(mode as string) || mode === 'video';
    // 'live' = the rigged VRM performing (breath, blinks, visemes, body language)
    const isLiveMode = mode === 'live';
    const isStillMode = !isVideoMode && !isLiveMode;
    const vrmRef = useRef<any>(null);

    // lipsynced-still: subtle jaw-bounce while TTS plays (audio-driven)
    const { mouth } = useLipsync();
    const energyRef = useRef(0);
    energyRef.current = mouth;
    const mouthScale = 1 + mouth * 0.045;
    const mouthBright = 1 + mouth * 0.35;

    return (
        <div style={{ 
            width: '100%', 
            height: '100%', 
            position: 'relative', 
            zIndex: 10 
        }}>
            {isStillMode ? (
                <img src={stillSrc || '/avatars/jen_still.png'} alt="Jen" className="ai-avatar-image"
                     onError={(e) => {
                       // A broken persona URL must fall back to the built-in
                       // frame rather than showing a torn image.
                       if (e.currentTarget.src.endsWith('/avatars/fallback.png')) return;
                       e.currentTarget.src = '/avatars/fallback.png';
                     }}
                     style={{
                       transform: `scaleY(${mouthScale.toFixed(4)})`,
                       filter: `brightness(${mouthBright.toFixed(3)})`,
                       transformOrigin: '50% 22%',  /* jaw hinge ~ mouth height */
                       willChange: 'transform, filter',
                     }} />
            ) : (
                <Canvas camera={{ position: [0, 1.35, 0.85], fov: 38 }}>
                    <AvatarScene
                        avatarManager={avatarRef.current}
                        url={isLiveMode ? avatarUrl : '/avatars/alicechan.vrm'}
                        vrmRef={vrmRef}
                        isLive={isLiveMode}
                    />
                    {isLiveMode && (
                        <AvatarPerformance vrmRef={vrmRef} energyRef={energyRef} />
                    )}
                </Canvas>
            )}
            {isVideoMode && <div className="video-indicator">📹</div>}
        </div>
    );
}
