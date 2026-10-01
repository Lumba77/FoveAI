import * as THREE from 'three';

export class MultiVision {
  constructor() {}

  public captureView(renderer: THREE.WebGLRenderer): Promise<string> {
    return new Promise((resolve) => {
      // Ensure the scene is rendered before capturing
      renderer.domElement.toBlob((blob) => {
        if (blob) {
          const reader = new FileReader();
          reader.readAsDataURL(blob);
          reader.onloadend = () => {
            const base64 = (reader.result as string).split(',')[1];
            resolve(base64);
          };
        }
      }, 'image/jpeg', 0.8);
    });
  }
}
