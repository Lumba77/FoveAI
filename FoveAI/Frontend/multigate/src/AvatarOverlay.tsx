import { useEffect, useState } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { VRMLoaderPlugin, VRM } from '@pixiv/three-vrm';

function AvatarModel({ url, talking }: { url: string, talking: boolean }) {
  const [vrm, setVrm] = useState<VRM | null>(null);

  useEffect(() => {
    const loader = new GLTFLoader();
    loader.register((parser) => new VRMLoaderPlugin(parser));
    
    loader.load(url, (gltf) => {
      const loadedVrm = gltf.userData.vrm;
      
      // Face the camera
      loadedVrm.scene.rotation.y = Math.PI; 
      
      // Turn off frustum culling for VRMs to prevent them disappearing
      loadedVrm.scene.traverse((obj: any) => {
        obj.frustumCulled = false;
      });

      setVrm(loadedVrm);
    }, undefined, (error) => {
      console.error('Failed to load VRM:', error);
    });
  }, [url]);

  useFrame((state, delta) => {
    if (vrm) {
      vrm.update(delta);
      
      // Simple idle breathing animation
      const s = Math.sin(state.clock.elapsedTime * 1.5);
      // Move chest/spine slightly
      const spine = vrm.humanoid?.getNormalizedBoneNode('spine');
      if (spine) {
         spine.rotation.x = s * 0.02;
      }
      
      // Simple mouth animation when talking
      if (talking) {
         const t = Math.sin(state.clock.elapsedTime * 15) * 0.5 + 0.5;
         vrm.expressionManager?.setValue('aa', t);
      } else {
         vrm.expressionManager?.setValue('aa', 0);
      }
    }
  });

  if (!vrm) return null;
  // Position so feet are at the bottom of the canvas
  return <primitive object={vrm.scene} position={[0, -1.3, 0]} />;
}

export default function AvatarOverlay({ show = false, talking = false }) {
  if (!show) return null;

  return (
    <div style={{
      position: 'absolute',
      bottom: '100px', // Rest right on top of the chat input wrapper
      right: '40px',   // Float on the right side
      width: '280px',
      height: '420px',
      pointerEvents: 'none',
      zIndex: 1000,
      opacity: 0.95
    }}>
      <Canvas camera={{ position: [0, 0.2, 1.8], fov: 45 }} gl={{ alpha: true }}>
        <ambientLight intensity={1.5} />
        <directionalLight position={[1, 2, 1]} intensity={2} />
        <AvatarModel url="/avatar.vrm" talking={talking} />
      </Canvas>
    </div>
  );
}
