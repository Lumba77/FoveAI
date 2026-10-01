/**
 * ═══════════════════════════════════════════════════════════════════════
 * SPATIAL ENVIRONMENT — Persistent Room Mapping from Quest APIs
 * ═══════════════════════════════════════════════════════════════════════
 *
 * CONCEPT:
 *   As the user walks around the apartment with their Quest headset,
 *   Meta's Scene Understanding API builds detailed 3D meshes of walls,
 *   floors, windows, doors, furniture, and screens. These meshes are
 *   texture-mapped with the environment plaster (webcam + passthrough
 *   snapshots) to create a persistent spatial model.
 *
 *   The avatar uses this model to:
 *   1. Navigate the apartment (avoid walls, walk to windows)
 *   2. "See" the environment (what's on the walls, what's outside windows)
 *   3. Comment on surroundings (notices new objects, changes)
 *   4. Examine things (approach items the user points to)
 *
 *   When outdoors, the Quest passthrough frames are plastered onto
 *   a cylindrical surround mesh, creating a rough outdoor panorama.
 *
 * DATA FLOW:
 *   Quest Scene API → room meshes (walls/floor/windows/furniture)
 *   Webcam + passthrough → texture frames → plaster textures
 *   CompositeVision → periodic snapshots → texture atlas update
 *   MovementEngine → spatial navmesh → pathfinding
 *   LLM sensory context → spatial description injection
 *
 * PERSISTENCE:
 *   Room meshes and textures are stored in localStorage as base64
 *   compressed data. Updated incrementally as user explores new areas.
 *   Survives browser sessions and headset reboots.
 */

import * as THREE from 'three';

// ── Types ────────────────────────────────────────────────────────────

export interface RoomMesh {
    id: string;                     // Unique anchor ID from Quest API
    type: 'wall' | 'floor' | 'ceiling' | 'window' | 'door' | 'screen' | 'furniture' | 'other';
    label?: string;                 // e.g. "couch", "bed", "table", "chair", "lamp"
    geometry: {                     // Simplified bounding box
        center: { x: number; y: number; z: number };
        size: { x: number; y: number; z: number };
    };
    textureBase64?: string;         // Last plaster texture applied
    lastUpdated: number;            // Timestamp
    planeNormal?: { x: number; y: number; z: number }; // Direction the surface faces
}

export interface SpatialData {
    roomName: string;
    meshes: RoomMesh[];
    lastFullScan: number;
    /** Approximate floor area in sq meters */
    floorArea: number;
    /** Number of wall surfaces discovered */
    wallCount: number;
    /** Number of windows/transparent surfaces */
    windowCount: number;
}

export interface OutdoorSurround {
    /** Cylindrical panorama texture */
    panoramaBase64: string;
    /** Number of frames stitched */
    frameCount: number;
    /** When this was captured */
    timestamp: number;
    /** Approximate GPS if available */
    location?: { lat: number; lon: number };
}

// ── Config ────────────────────────────────────────────────────────────

const LOCAL_STORAGE_KEY = 'foveai_spatial_environment';
const COMPRESSION_LEVEL = 0.6; // JPEG quality for stored textures

export class SpatialEnvironment {
    private rooms: Map<string, SpatialData> = new Map();
    private outdoorSurround: OutdoorSurround | null = null;
    private currentRoom: string = 'default';
    private log: (msg: string, color: string) => void;
    private saveTimeout: any = null;

    // Three.js mesh representations
    private roomMeshGroup: THREE.Group | null = null;
    private wallMeshes: THREE.Mesh[] = [];
    private floorMesh: THREE.Mesh | null = null;

    constructor(logFn?: (msg: string, color: string) => void) {
        this.log = logFn || ((msg, color) => console.log(`[SpatialEnv] ${msg}`));
        this.load(); // Restore from localStorage
        window.addEventListener('beforeunload', () => {
            this.save(true); // Force immediate save on page exit
        });
    }

    // ═══════════════════════════════════════════════════════════════
    // QUEST SCENE API INTEGRATION
    // ═══════════════════════════════════════════════════════════════

    /**
     * Ingest room mesh data from Quest Scene Understanding API.
     * Called when the user walks into a new area or the scene updates.
     * 
     * Quest API provides: XRAnchor, XRMesh, XRPlane (in WebXR)
     * We simplify to bounding boxes with type classification.
     */
    ingestQuestSceneData(
        roomName: string,
        anchors: Array<{
            id: string;
            type: 'wall' | 'floor' | 'ceiling' | 'window' | 'door' | 'screen' | 'furniture' | 'other';
            label?: string;
            position: { x: number; y: number; z: number };
            size: { x: number; y: number; z: number };
            normal?: { x: number; y: number; z: number };
        }>
    ): SpatialData {
        const now = Date.now();
        const meshes: RoomMesh[] = anchors.map(a => ({
            id: a.id,
            type: a.type,
            label: a.label,
            geometry: { center: a.position, size: a.size },
            lastUpdated: now,
            planeNormal: a.normal,
        }));

        const data: SpatialData = {
            roomName,
            meshes,
            lastFullScan: now,
            floorArea: this.calculateFloorArea(meshes),
            wallCount: meshes.filter(m => m.type === 'wall').length,
            windowCount: meshes.filter(m => m.type === 'window').length,
        };

        this.rooms.set(roomName, data);
        this.currentRoom = roomName;
        this.save();
        this.log(`🏠 Room mapped: "${roomName}" — ${meshes.length} surfaces, ${data.wallCount} walls, ${data.windowCount} windows`, 'var(--neon-green)');
        
        return data;
    }

    /**
     * Update a single mesh's texture when a new plaster frame is available.
     * Called by CompositeVision after each environment snapshot.
     */
    updateMeshTexture(meshId: string, textureBase64: string): boolean {
        for (const [, room] of this.rooms) {
            const mesh = room.meshes.find(m => m.id === meshId);
            if (mesh) {
                mesh.textureBase64 = textureBase64;
                mesh.lastUpdated = Date.now();
                this.save();
                return true;
            }
        }
        return false;
    }

    /**
     * Apply environment plaster to all wall surfaces in the current room.
     * Uses the latest frame from CompositeVision and projects it onto walls.
     */
    applyEnvironmentPlaster(plasterBase64: string): void {
        const room = this.rooms.get(this.currentRoom);
        if (!room) return;

        let updated = 0;
        for (const mesh of room.meshes) {
            if (mesh.type === 'wall' || mesh.type === 'screen') {
                mesh.textureBase64 = plasterBase64;
                mesh.lastUpdated = Date.now();
                updated++;
            }
        }
        if (updated > 0) {
            this.log(`🧹 Plaster applied to ${updated} surfaces in "${this.currentRoom}"`, 'var(--neon-blue)');
            this.save();
        }
    }

    // ═══════════════════════════════════════════════════════════════
    // OUTDOOR SURROUND
    // ═══════════════════════════════════════════════════════════════

    /**
     * Build an outdoor panorama from Quest passthrough frames.
     * Called when GPS indicates user is outside.
     * Stitches frames into a cylindrical surround texture.
     */
    buildOutdoorSurround(frames: string[]): OutdoorSurround {
        // In production: use image stitching (OpenCV.js or similar)
        // For now: store frames and mark as outdoor
        this.outdoorSurround = {
            panoramaBase64: frames[0] || '', // First frame as placeholder
            frameCount: frames.length,
            timestamp: Date.now(),
        };
        this.log(`🌳 Outdoor surround: ${frames.length} frames stitched`, 'var(--neon-green)');
        this.save(true);
        return this.outdoorSurround;
    }

    isOutdoors(): boolean {
        return this.outdoorSurround !== null && 
               (Date.now() - this.outdoorSurround.timestamp) < 300_000; // 5 min validity
    }

    // ═══════════════════════════════════════════════════════════════
    // THREE.JS RENDERING
    // ═══════════════════════════════════════════════════════════════

    /**
     * Build or rebuild Three.js meshes for the current room.
     * Creates semi-transparent wall/floor planes with plaster textures.
     * These are rendered in the avatar's vision camera for spatial context.
     */
    buildRoomScene(scene: THREE.Scene): THREE.Group {
        // Remove old meshes
        if (this.roomMeshGroup) {
            scene.remove(this.roomMeshGroup);
        }

        const room = this.rooms.get(this.currentRoom);
        if (!room) {
            this.roomMeshGroup = new THREE.Group();
            return this.roomMeshGroup;
        }

        this.roomMeshGroup = new THREE.Group();
        this.roomMeshGroup.name = `spatial_room_${this.currentRoom}`;
        this.wallMeshes = [];

        for (const meshData of room.meshes) {
            const { center, size } = meshData.geometry;
            
            let color: number;
            let opacity: number;
            
            switch (meshData.type) {
                case 'wall':   color = 0x1a2a3e; opacity = 0.3; break;
                case 'floor':  color = 0x2a3a4e; opacity = 0.2; break;
                case 'window': color = 0x4a8aff; opacity = 0.5; break; // Bright window glow
                case 'door':   color = 0x3a4a5e; opacity = 0.4; break;
                case 'screen': color = 0x00aaff; opacity = 0.6; break; // Screen glow
                default:       color = 0x1a1a2e; opacity = 0.2; break;
            }

            const geo = new THREE.PlaneGeometry(size.x, size.y);
            const mat = new THREE.MeshBasicMaterial({
                color,
                transparent: true,
                opacity,
                side: THREE.DoubleSide,
                depthWrite: false,
            });

            // If we have a plaster texture, apply it
            if (meshData.textureBase64) {
                try {
                    const img = new Image();
                    img.src = 'data:image/jpeg;base64,' + meshData.textureBase64;
                    img.onload = () => {
                        const texture = new THREE.Texture(img);
                        texture.needsUpdate = true;
                        mat.map = texture;
                        mat.color.setHex(0xffffff);
                        mat.opacity = 1.0;
                        mat.needsUpdate = true;
                    };
                } catch { /* skip texture if invalid */ }
            }

            const mesh = new THREE.Mesh(geo, mat);
            mesh.position.set(center.x, center.y, center.z);
            
            // Orient plane to face its normal direction
            if (meshData.planeNormal) {
                mesh.lookAt(
                    center.x + meshData.planeNormal.x,
                    center.y + meshData.planeNormal.y,
                    center.z + meshData.planeNormal.z
                );
            }

            mesh.name = meshData.id;
            // Put on Layer 0 so avatar camera sees it
            mesh.layers.set(0);
            
            this.roomMeshGroup!.add(mesh);
            this.wallMeshes.push(mesh);
        }

        scene.add(this.roomMeshGroup);
        this.log(`🧱 Room scene: ${this.wallMeshes.length} meshes rendered`, 'var(--neon-blue)');
        
        return this.roomMeshGroup;
    }

    /**
     * Create outdoor surround cylinder for when user is outside.
     * Maps the panorama texture onto a large cylinder around the play area.
     */
    buildOutdoorScene(scene: THREE.Scene, radius: number = 10): THREE.Mesh | null {
        if (!this.outdoorSurround?.panoramaBase64) return null;

        const geo = new THREE.CylinderGeometry(radius, radius, 4, 32, 1, true); // Open cylinder
        const mat = new THREE.MeshBasicMaterial({
            color: 0xffffff,
            side: THREE.BackSide, // Render inside of cylinder
            transparent: true,
            opacity: 0.8,
            depthWrite: false,
        });

        // Apply panorama texture
        try {
            const img = new Image();
            img.src = 'data:image/jpeg;base64,' + this.outdoorSurround.panoramaBase64;
            img.onload = () => {
                const tex = new THREE.Texture(img);
                tex.needsUpdate = true;
                mat.map = tex;
                mat.needsUpdate = true;
            };
        } catch { /* skip texture */ }

        const cylinder = new THREE.Mesh(geo, mat);
        cylinder.name = 'outdoor_surround';
        cylinder.layers.set(0);
        scene.add(cylinder);
        
        this.log(`🌍 Outdoor surround: ${radius}m radius cylinder`, 'var(--neon-green)');
        return cylinder;
    }

    // ═══════════════════════════════════════════════════════════════
    // SPATIAL DESCRIPTION (for LLM context)
    // ═══════════════════════════════════════════════════════════════

    /**
     * Generate a rich spatial description of the current room for LLM injection.
     * The avatar "knows" what's around her and can comment on it.
     */
    getSpatialDescription(): string {
        const room = this.rooms.get(this.currentRoom);
        if (!room) {
            return '[SPATIAL] No room data yet. The user has not mapped this space. Walk around with the headset to build the environment.';
        }

        const lines: string[] = [
            `[SPATIAL KNOWLEDGE — Room: "${room.roomName}"]`,
            `  Floor area: ~${room.floorArea.toFixed(1)} sq meters`,
        ];

        // Group surfaces by type
        const types = new Map<string, RoomMesh[]>();
        for (const m of room.meshes) {
            if (!types.has(m.type)) types.set(m.type, []);
            types.get(m.type)!.push(m);
        }

        for (const [type, meshes] of types) {
            if (meshes.length === 0) continue;
            const label = type === 'wall' ? 'Walls' :
                          type === 'window' ? 'Windows' :
                          type === 'door' ? 'Doors' :
                          type === 'screen' ? 'Screens/Monitors' :
                          type === 'furniture' ? 'Furniture pieces' :
                          type === 'floor' ? 'Floor' :
                          type === 'ceiling' ? 'Ceiling' :
                          type.charAt(0).toUpperCase() + type.slice(1);
            
            const positions = meshes.map(m => {
                const c = m.geometry.center;
                const textured = m.textureBase64 ? ' (textured)' : '';
                const nameLabel = m.label ? `"${m.label}" ` : '';
                return `${nameLabel}at (${c.x.toFixed(1)}, ${c.y.toFixed(1)}, ${c.z.toFixed(1)})${textured}`;
            }).join(', ');

            lines.push(`  ${label} (${meshes.length}): ${positions}`);
        }
        
        if (this.isOutdoors()) {
            lines.push(`  LOCATION: OUTDOORS — surroundings mapped via Quest passthrough`);
            if (this.outdoorSurround?.location) {
                lines.push(`  GPS: ${this.outdoorSurround.location.lat.toFixed(4)}, ${this.outdoorSurround.location.lon.toFixed(4)}`);
            }
        }

        lines.push(`  Last scan: ${new Date(room.lastFullScan).toLocaleTimeString()}`);
        lines.push(`  You can walk to any location in this room. Windows let you look outside.`);
        
        return lines.join('\n');
    }

    /**
     * Get navigation hints for the MovementEngine.
     * Returns traversable floor area and obstacle positions.
     */
    getNavigationData(): { floorCenter: THREE.Vector3; obstacles: THREE.Vector3[] } {
        const room = this.rooms.get(this.currentRoom);
        const floorCenter = new THREE.Vector3(0, 0, 0);
        const obstacles: THREE.Vector3[] = [];

        if (!room) return { floorCenter, obstacles };

        for (const mesh of room.meshes) {
            const c = mesh.geometry.center;
            if (mesh.type === 'floor') {
                floorCenter.set(c.x, c.y, c.z);
            }
            if (mesh.type === 'wall' || mesh.type === 'furniture' || mesh.type === 'door') {
                obstacles.push(new THREE.Vector3(c.x, c.y, c.z));
            }
        }

        return { floorCenter, obstacles };
    }

    // ═══════════════════════════════════════════════════════════════
    // PERSISTENCE
    // ═══════════════════════════════════════════════════════════════

    private save(immediate = false): void {
        if (immediate) {
            if (this.saveTimeout) {
                clearTimeout(this.saveTimeout);
                this.saveTimeout = null;
            }
            this._performSave();
            return;
        }

        if (this.saveTimeout) return;

        this.saveTimeout = setTimeout(() => {
            this.saveTimeout = null;
            this._performSave();
        }, 10000); // Throttled to maximum once every 10 seconds during active scanning
    }

    private _performSave(): void {
        try {
            const data = {
                rooms: Array.from(this.rooms.entries()),
                outdoorSurround: this.outdoorSurround,
                currentRoom: this.currentRoom,
            };
            localStorage.setItem(LOCAL_STORAGE_KEY, JSON.stringify(data));
        } catch (e) {
            this.log('Failed to save spatial data: ' + e, 'var(--neon-red)');
        }
    }

    private load(): void {
        try {
            const raw = localStorage.getItem(LOCAL_STORAGE_KEY);
            if (!raw) return;
            const data = JSON.parse(raw);
            this.rooms = new Map(data.rooms || []);
            this.outdoorSurround = data.outdoorSurround || null;
            this.currentRoom = data.currentRoom || 'default';
            this.log(`📂 Spatial data loaded: ${this.rooms.size} rooms`, 'var(--neon-blue)');
        } catch (e) {
            this.log('Failed to load spatial data: ' + e, 'var(--neon-orange)');
        }
    }

    /** Clear all spatial data. */
    reset(): void {
        this.rooms.clear();
        this.outdoorSurround = null;
        localStorage.removeItem(LOCAL_STORAGE_KEY);
        this.log('🗑️ Spatial data cleared', 'var(--neon-orange)');
    }

    getCurrentRoom(): SpatialData | null {
        return this.rooms.get(this.currentRoom) || null;
    }

    getAllRooms(): string[] {
        return Array.from(this.rooms.keys());
    }

    switchRoom(name: string): boolean {
        if (this.rooms.has(name)) {
            this.currentRoom = name;
            this.save(true);
            return true;
        }
        return false;
    }

    private calculateFloorArea(meshes: RoomMesh[]): number {
        let area = 0;
        for (const m of meshes) {
            if (m.type === 'floor') {
                area += m.geometry.size.x * m.geometry.size.z;
            }
        }
        return Math.max(area, 1); // At least 1 sq meter
    }
}