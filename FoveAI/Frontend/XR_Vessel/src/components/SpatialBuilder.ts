import * as THREE from 'three';
import ThreeMeshUI from 'three-mesh-ui';

interface SpatialComponent {
    type: string;
    attributes: Record<string, any>;
    children: SpatialComponent[];
}

export class SpatialMachineBuilder {
    private scene: THREE.Scene;
    private rootContainer: any | null = null;
    private currentUrl: string = '';
    
    constructor(scene: THREE.Scene) {
        this.scene = scene;
    }

    async transpileUrl(url: string, position: THREE.Vector3, rotation: THREE.Euler) {
        console.log(`[SpatialMachine] Transpiling ${url}...`);
        
        try {
            const response = await fetch('http://localhost:8010/spatial/transpile', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url })
            });
            
            if (!response.ok) throw new Error('Failed to transpile URL');
            const data = await response.json();
            
            this.currentUrl = data.url;
            this.buildSpatialGeometry(data.spatial_tree, position, rotation);
            
        } catch (error) {
            console.error('[SpatialMachine] Transpile error:', error);
        }
    }

    private buildSpatialGeometry(tree: SpatialComponent, position: THREE.Vector3, rotation: THREE.Euler) {
        // Remove old container if it exists
        if (this.rootContainer) {
            this.scene.remove(this.rootContainer);
            this.rootContainer = null;
        }

        // Create the root spatial tablet
        this.rootContainer = new ThreeMeshUI.Block({
            width: 1.2,
            height: 0.8,
            padding: 0.05,
            justifyContent: 'start',
            alignContent: 'left',
            fontFamily: '/Roboto-msdf.json',
            fontTexture: '/Roboto-msdf.png',
            backgroundColor: new THREE.Color(0x1a1a1a),
            backgroundOpacity: 0.9,
            borderRadius: 0.05
        });

        this.rootContainer.position.copy(position);
        this.rootContainer.rotation.copy(rotation);
        
        // Add Title Bar
        const titleBar = new ThreeMeshUI.Block({
            width: 1.1,
            height: 0.1,
            justifyContent: 'center',
            backgroundColor: new THREE.Color(0x333333),
            backgroundOpacity: 1,
            margin: 0.02
        });
        titleBar.add(new ThreeMeshUI.Text({ content: this.currentUrl, fontSize: 0.04 }));
        this.rootContainer.add(titleBar);

        // Scrollable content area
        const contentContainer = new ThreeMeshUI.Block({
            width: 1.1,
            height: 0.6,
            justifyContent: 'start',
            alignContent: 'left',
            backgroundOpacity: 0
        });

        // Recursively build children
        tree.children.forEach(child => {
            const uiElement = this.createUIElement(child);
            if (uiElement) {
                contentContainer.add(uiElement);
            }
        });

        this.rootContainer.add(contentContainer);
        this.scene.add(this.rootContainer);
    }

    private createUIElement(node: SpatialComponent): any {
        if (node.type === 'Null') return null;

        if (node.type === 'Text') {
            const content = node.attributes.content || '';
            if (!content) return null;
            return new ThreeMeshUI.Text({ 
                content: content + ' ', 
                fontSize: 0.035,
                fontColor: new THREE.Color(0xffffff) 
            });
        }

        if (node.type === 'Block') {
            // Determine styling based on attributes
            let bgColor = 0x000000;
            let bgOpacity = 0.0;
            let padding = 0.01;
            let margin = 0.01;
            let isInteractive = false;
            
            if (node.attributes.isHeader) {
                // Header formatting
                margin = 0.03;
            } else if (node.attributes.isLink || node.attributes.isButton) {
                bgColor = 0x00f3ff;
                bgOpacity = 0.2;
                padding = 0.02;
                isInteractive = true;
            }

            const block = new ThreeMeshUI.Block({
                width: 1.0, // Force wrap
                height: 0.2, // Default height, required by TS
                padding: padding,
                margin: margin,
                justifyContent: 'start',
                alignContent: 'left',
                backgroundColor: new THREE.Color(bgColor),
                backgroundOpacity: bgOpacity,
                contentDirection: 'row'
            });

            // If interactive, add hover/click states
            if (isInteractive) {
                // We add it to the global mesh array so the raycaster can hit it
                if ((window as any).foveaiUiMeshes) {
                    (window as any).foveaiUiMeshes.push(block);
                }

                (block as any).setupState({
                    state: 'hovered',
                    attributes: { offset: 0.02, backgroundColor: new THREE.Color(0x39ff14), backgroundOpacity: 0.4 }
                });
                
                (block as any).setupState({
                    state: 'idle',
                    attributes: { offset: 0, backgroundColor: new THREE.Color(bgColor), backgroundOpacity: bgOpacity }
                });
                
                (block as any).setupState({
                    state: 'selected',
                    attributes: { offset: -0.01, backgroundColor: new THREE.Color(0xff00ff) },
                    onSet: () => {
                        // Trigger Navigation
                        const href = node.attributes.href;
                        if (href) {
                            console.log(`[SpatialMachine] Navigating to: ${href}`);
                            // If relative, resolve it
                            let nextUrl = href;
                            if (href.startsWith('/')) {
                                const urlObj = new URL(this.currentUrl);
                                nextUrl = `${urlObj.protocol}//${urlObj.host}${href}`;
                            } else if (!href.startsWith('http')) {
                                const urlObj = new URL(this.currentUrl);
                                nextUrl = `${urlObj.protocol}//${urlObj.host}/${href}`;
                            }
                            
                            this.transpileUrl(nextUrl, this.rootContainer.position, this.rootContainer.rotation);
                        }
                    }
                });
            }

            // Recursively build children
            node.children.forEach(child => {
                const childEl = this.createUIElement(child);
                if (childEl) block.add(childEl);
            });
            
            return block;
        }

        return null;
    }
}
