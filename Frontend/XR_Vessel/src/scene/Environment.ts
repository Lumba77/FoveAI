import * as THREE from 'three';

export class Environment {
  public scene: THREE.Scene;
  public camera: THREE.PerspectiveCamera;
  public renderer: THREE.WebGLRenderer;

  constructor() {
    // Prevent duplicate rendering canvases (HMR & double-boot safety)
    const existingCanvases = document.querySelectorAll('canvas');
    existingCanvases.forEach(canvas => {
        if (canvas.parentNode === document.body || canvas.style.position === 'fixed') {
            canvas.parentNode?.removeChild(canvas);
        }
    });

    this.scene = new THREE.Scene();
    
    // Camera setup
    this.camera = new THREE.PerspectiveCamera(70, window.innerWidth / window.innerHeight, 0.01, 20);
    
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true }); // Enable alpha for Passthrough + snapshot support
    this.renderer.setPixelRatio(window.devicePixelRatio);
    this.renderer.setSize(window.innerWidth, window.innerHeight);
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.setClearColor(0x02050a, 0); // Transparent by default
    
    this.renderer.domElement.style.position = 'fixed';
    this.renderer.domElement.style.top = '0';
    this.renderer.domElement.style.left = '0';
    this.renderer.domElement.style.width = '100%';
    this.renderer.domElement.style.height = '100%';
    this.renderer.domElement.style.zIndex = '1';
    
    document.body.appendChild(this.renderer.domElement);

    this.setupLighting();
    this.setupHelpers();
    
    window.addEventListener('resize', () => this.onWindowResize());
  }

  private setupLighting() {
    const ambientLight = new THREE.HemisphereLight(0xffffff, 0xbbbbff, 1);
    this.scene.add(ambientLight);

    const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8);
    directionalLight.position.set(0.5, 1, 0.25);
    this.scene.add(directionalLight);
  }

  private setupHelpers() {
    // Ground Plane for visibility in VR (fully transparent to avoid blocking passthrough)
    const floorGeo = new THREE.PlaneGeometry(20, 20);
    const floorMat = new THREE.MeshStandardMaterial({ 
        color: 0x111111, 
        roughness: 0.8,
        metalness: 0.2,
        transparent: true,
        opacity: 0.0
    });
    const floor = new THREE.Mesh(floorGeo, floorMat);
    floor.rotation.x = -Math.PI / 2;
    floor.position.y = -0.8; // Align with avatar floor
    this.scene.add(floor);

    // Subtle floor grid
    const gridHelper = new THREE.GridHelper(20, 20, 0x00f3ff, 0x222222);
    gridHelper.position.y = -0.79;
    gridHelper.material.opacity = 0.15;
    gridHelper.material.transparent = true;
    this.scene.add(gridHelper);
  }

  private onWindowResize() {
    this.camera.aspect = window.innerWidth / window.innerHeight;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(window.innerWidth, window.innerHeight);
  }

  public render(callback: () => void) {
    this.renderer.setAnimationLoop(callback);
  }

  public setImmersiveMode(mode: 'vr' | 'ar' | 'desktop') {
    const isAR = mode === 'ar';
    const isVR = mode === 'vr';
    const isDesktop = mode === 'desktop';

    // Toggle background transparency (allow passthrough in both AR and VR)
    if (isAR || isVR) {
      this.renderer.setClearColor(0x000000, 0); // Fully transparent to expose Quest 3 passthrough cameras
    } else {
      this.renderer.setClearColor(0x02050a, 1.0); // Desktop stays dark
    }

    // Toggle visibility of environment helpers
    this.scene.traverse((obj) => {
      if (obj instanceof THREE.GridHelper) {
        obj.visible = !isAR;
      }
      if (obj instanceof THREE.Mesh && obj.geometry instanceof THREE.PlaneGeometry) {
        if (obj.name !== 'spatial_portal') {
          obj.visible = !isAR;
        }
      }
    });

    console.log(`[Environment] Immersive Mode set to: ${mode}`);
  }

  public setHUDMode(enabled: boolean) {
      if (enabled) {
          this.renderer.setClearColor(0x000000, 0); // Fully transparent
          this.scene.traverse((obj) => {
              if (obj instanceof THREE.GridHelper || (obj instanceof THREE.Mesh && obj.geometry instanceof THREE.PlaneGeometry)) {
                  obj.visible = false;
              }
          });
      } else {
          this.renderer.setClearColor(0x02050a, 1.0);
      }
  }
}
