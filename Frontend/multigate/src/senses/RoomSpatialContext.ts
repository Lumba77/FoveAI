import * as THREE from 'three';

export class RoomSpatialContext {
  constructor() {}

  public getHeadsetSnapshot(renderer: THREE.WebGLRenderer): any {
    const session = renderer.xr.getSession();
    if (!session) return { xr_active: false };

    const camera = renderer.xr.getCamera();
    const pos = camera.position;
    const fwd = new THREE.Vector3(0, 0, -1).applyQuaternion(camera.quaternion);
    
    const flat = new THREE.Vector3(fwd.x, 0, fwd.z).normalize();
    const yawDeg = Math.atan2(flat.x, flat.z) * (180 / Math.PI);

    return {
      version: 2,
      xr_active: true,
      headset: {
        position_m: [pos.x, pos.y, pos.z],
        forward_flat: [flat.x, flat.y, flat.z],
        yaw_deg: yawDeg,
      },
      entities: [], // TODO: Track virtual objects if needed
      cameras: [],
      summary: "WebXR Mixed Reality Session",
    };
  }
}
