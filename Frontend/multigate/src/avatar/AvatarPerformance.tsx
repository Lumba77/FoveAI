import { useRef } from 'react';
import * as THREE from 'three';
import { useFrame } from '@react-three/fiber';
import type { VRM } from '@pixiv/three-vrm';
import {
  applyMorph,
  blinkAt,
  breathing,
  envelope,
  headIdle,
  isSpeaking,
  talkBody,
  visemeAt,
  weightShift,
} from './performance';

/**
 * AvatarPerformance — makes a static rig actually perform.
 *
 * The vendored VRMs carry bones and preset expressions but no animation clips,
 * which is why nothing ever moved. This driver poses the rig procedurally every
 * frame: breathing, weight shift, idle head motion, natural blinks, speaking
 * nods, and amplitude-driven visemes from the TTS energy envelope.
 *
 * Feed it `energyRef` (0..1) — the same signal useLipsync listens to.
 */
export function AvatarPerformance({
  vrmRef,
  energyRef,
  lookAtRef,
  seed = 0,
  enabled = true,
}: {
  vrmRef: { current: VRM | null };
  energyRef?: { current: number };
  lookAtRef?: { current: { x: number; y: number; z: number } | null };
  seed?: number;
  enabled?: boolean;
}) {
  const env = useRef(0);
  const t0 = useRef<number | null>(null);
  const lookVec = useRef(new THREE.Vector3(0, 1.4, 1));

  useFrame((state) => {
    const vrm = vrmRef.current;
    if (!enabled || !vrm) return;
    if (t0.current === null) t0.current = state.clock.elapsedTime;
    const t = state.clock.elapsedTime - t0.current;

    const energy = energyRef?.current ?? 0;
    env.current = envelope(env.current, energy);
    const talking = isSpeaking(env.current);

    // ── mouth: viseme shapes driven by the speech envelope.
    // VRM 1.0 rigs answer through expressionManager; VRM 0.0 and plain GLBs
    // keep morphs under their own names, so write both paths.
    const expr = vrm.expressionManager;
    const vis = visemeAt(t, env.current, seed);
    const lid = blinkAt(t, seed) * (talking ? 0.25 : 1);
    if (expr) {
      for (const name of ['aa', 'ih', 'ou', 'ee', 'oh']) {
        try { expr.setValue(name, vis && vis.name === name ? vis.value : 0); } catch { /* absent */ }
      }
      for (const name of ['blink', 'blinkLeft', 'blinkRight']) {
        try { expr.setValue(name, lid); } catch { /* absent */ }
      }
    }
    for (const name of ['aa', 'ih', 'ou', 'ee', 'oh']) {
      applyMorph(vrm.scene, name, vis && vis.name === name ? vis.value : 0);
    }
    for (const name of ['blink', 'blinkLeft', 'blinkRight']) {
      applyMorph(vrm.scene, name, lid);
    }

    // ── bones: breath, sway, head, speaking emphasis
    const human = vrm.humanoid;
    if (!human) return;
    const get = (bone: string) => {
      try { return human.getNormalizedBoneNode(bone as never); } catch { return null; }
    };
    const rot = (bone: string, x: number, y: number, z: number) => {
      const node = get(bone);
      if (node) node.rotation.set(x, y, z);
    };

    const br = breathing(t);
    const sway = weightShift(t);
    const head = headIdle(t);
    const talk = talkBody(t, env.current);

    rot('hips', 0, sway.x, sway.roll);
    rot('spine', br * 0.012, sway.x * 0.4, -sway.roll * 0.5);
    rot('chest', br * 0.02 + talk.torso, sway.x * 0.3, 0);
    rot('neck', head.pitch * 0.4 + talk.nod * 0.5, head.yaw * 0.5, head.roll * 0.4);
    rot('head', head.pitch + talk.nod, head.yaw, head.roll);

    // small shoulder lift + hand gesture while speaking
    const arm = talk.hand;
    rot('leftShoulder', 0, 0, -0.02 - arm * 0.35);
    rot('rightShoulder', 0, 0, 0.02 + arm * 0.2);
    rot('leftUpperArm', -arm * 0.5, 0, -0.1 - arm * 0.25);
    rot('rightUpperArm', -arm * 0.2, 0, 0.1);

    // ── eyes: track the speaker / camera
    const target = lookAtRef?.current ?? null;
    if (target) {
      try {
        lookVec.current.set(target.x, target.y, target.z);
        vrm.lookAt?.lookAt(lookVec.current);
      } catch { /* lookAt is optional on some rigs */ }
    }
  });

  return null;
}