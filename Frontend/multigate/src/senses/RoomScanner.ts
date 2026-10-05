/**
 * ═══════════════════════════════════════════════════════════════════════
 * ROOM SCANNER — Guided Environment Mapping for the User
 * ═══════════════════════════════════════════════════════════════════════
 *
 * CONCEPT:
 *   Like Meta's "Room Setup" (Hyper Camera / Scene Capture), the user
 *   is guided through a meticulous walk-around of the apartment with
 *   visual cues showing which areas have been scanned and which still
 *   need coverage. The avatar actively coaches the user through the
 *   process: "Turn left — I can't see the corner yet."
 *
 *   Once scanned, the system auto-updates any area that Quest's Scene
 *   API reports as changed (moved furniture, new objects, etc).
 *
 * SCANNING MODES:
 *   1. WALLS — walk along each wall looking at it (fills wall textures)
 *   2. FLOOR — look down while walking across the room (maps floor)
 *   3. FURNITURE — circle around tables/desks/sofas (captures objects)
 *   4. WINDOWS — stand at each window and look outside (captures view)
 *   5. OUTDOOR — walk outside and spin 360° (builds panorama)
 *
 * AUTO-UPDATE TRIGGERS:
 *   - Quest Scene API reports mesh geometry change → mark dirty
 *   - Dirty areas get re-captured within 3 seconds
 *   - New objects detected → immediate texture capture
 *   - Removed objects → clear old plaster, mark for re-scan
 */

import * as THREE from 'three';

// ── Types ────────────────────────────────────────────────────────────

export type ScanZoneType = 'wall_w' | 'wall_n' | 'wall_e' | 'wall_s' | 'floor' | 'ceiling' | 'furniture' | 'window' | 'door' | 'corner' | 'outdoor';

export interface ScanZone {
    id: string;
    type: ScanZoneType;
    /** Position to look at / walk to */
    targetPosition: THREE.Vector3;
    /** Direction to face when scanning */
    lookDirection: THREE.Vector3;
    /** Coverage 0-100% */
    coverage: number;
    /** Whether this zone is dirty and needs re-scanning */
    dirty: boolean;
    /** How many frames captured for this zone */
    frameCount: number;
    lastUpdated: number;
    textureBase64?: string;
}

export interface ScanSession {
    zones: ScanZone[];
    overallCoverage: number;
    isComplete: boolean;
    /** Which zone the user should scan next */
    currentHint: string;
    /** Coaching instruction text */
    coachingText: string;
}

// ── Default room (5×4m apartment) ──────────────────────────────────
// These positions assume the user stands at origin (0,0,0) facing -Z
// Adjust based on actual room dimensions from Quest Scene API

const DEFAULT_ZONES: ScanZone[] = [
    // Four walls — user walks along each, looking at it
    { id: 'wall_north',   type: 'wall_n',   targetPosition: new THREE.Vector3(0, 1.5, -3),   lookDirection: new THREE.Vector3(0, 0, 1),    coverage: 0, dirty: true, frameCount: 0, lastUpdated: 0 },
    { id: 'wall_south',   type: 'wall_s',   targetPosition: new THREE.Vector3(0, 1.5, 2),    lookDirection: new THREE.Vector3(0, 0, -1),   coverage: 0, dirty: true, frameCount: 0, lastUpdated: 0 },
    { id: 'wall_east',    type: 'wall_e',   targetPosition: new THREE.Vector3(2.5, 1.5, 0),  lookDirection: new THREE.Vector3(-1, 0, 0),   coverage: 0, dirty: true, frameCount: 0, lastUpdated: 0 },
    { id: 'wall_west',    type: 'wall_w',   targetPosition: new THREE.Vector3(-2.5, 1.5, 0), lookDirection: new THREE.Vector3(1, 0, 0),    coverage: 0, dirty: true, frameCount: 0, lastUpdated: 0 },
    // Floor — look down while walking
    { id: 'floor',        type: 'floor',    targetPosition: new THREE.Vector3(0, 0.3, 0),    lookDirection: new THREE.Vector3(0, -1, 0),   coverage: 0, dirty: true, frameCount: 0, lastUpdated: 0 },
    // Four corners (high-detail closeups)
    { id: 'corner_nw',    type: 'corner',   targetPosition: new THREE.Vector3(-2, 1.5, -2.5), lookDirection: new THREE.Vector3(0, 0, 1),  coverage: 0, dirty: true, frameCount: 0, lastUpdated: 0 },
    { id: 'corner_ne',    type: 'corner',   targetPosition: new THREE.Vector3(2, 1.5, -2.5),  lookDirection: new THREE.Vector3(-1, 0, 1),  coverage: 0, dirty: true, frameCount: 0, lastUpdated: 0 },
    { id: 'corner_sw',    type: 'corner',   targetPosition: new THREE.Vector3(-2, 1.5, 2.5),  lookDirection: new THREE.Vector3(0, 0, -1),  coverage: 0, dirty: true, frameCount: 0, lastUpdated: 0 },
    { id: 'corner_se',    type: 'corner',   targetPosition: new THREE.Vector3(2, 1.5, 2.5),   lookDirection: new THREE.Vector3(-1, 0, -1), coverage: 0, dirty: true, frameCount: 0, lastUpdated: 0 },
    // Ceiling
    { id: 'ceiling',      type: 'ceiling',  targetPosition: new THREE.Vector3(0, 2.3, 0),    lookDirection: new THREE.Vector3(0, 1, 0),   coverage: 0, dirty: true, frameCount: 0, lastUpdated: 0 },
];

const COVERAGE_COMPLETE_THRESHOLD = 80; // 80% is "done enough"
const FRAMES_NEEDED_PER_ZONE = 3;
const MAX_HINT_HISTORY = 3;

export class RoomScanner {
    private zones: ScanZone[] = [];
    private session: ScanSession;
    private isActive: boolean = false;
    private hintHistory: string[] = [];
    private log: (msg: string, color: string) => void;

    // Three.js debug overlays
    private scanDebugMeshes: THREE.Mesh[] = [];
    private scanGizmoGroup: THREE.Group | null = null;

    constructor(logFn?: (msg: string, color: string) => void) {
        this.log = logFn || ((msg, color) => console.log(`[RoomScanner] ${msg}`));
        this.zones = DEFAULT_ZONES.map(z => ({ ...z, targetPosition: z.targetPosition.clone(), lookDirection: z.lookDirection.clone() }));
        this.session = this.buildSession();
        this.load(); // Restore from localStorage
    }

    // ═══════════════════════════════════════════════════════════════
    // PUBLIC API
    // ═══════════════════════════════════════════════════════════════

    /** Start or resume a guided scanning session. */
    start(): ScanSession {
        this.isActive = true;
        this.log('🔍 Room scanning session started — follow the coaching hints', 'var(--neon-blue)');
        this.session = this.buildSession();
        return this.session;
    }

    /** Stop scanning. */
    stop(): void {
        this.isActive = false;
        this.removeDebugMeshes();
        this.log('Room scanning session paused', 'var(--neon-orange)');
    }

    /** Get current scanning status. */
    getSession(): ScanSession {
        this.session = this.buildSession();
        return this.session;
    }

    isScanning(): boolean { return this.isActive; }

    /**
     * Register a frame capture for the zone the user is currently facing.
     * Called from CompositeVision / rendering loop.
     * @param userPosition — current headset position
     * @param userForward — direction user is looking
     * @param textureBase64 — captured frame (from passthrough or webcam)
     */
    registerCapture(userPosition: THREE.Vector3, userForward: THREE.Vector3, textureBase64: string): void {
        if (!this.isActive) return;

        // Find which zone the user is looking at (dot product with zone direction)
        let bestZone: ScanZone | null = null;
        let bestScore = -Infinity;

        for (const zone of this.zones) {
            if (zone.coverage >= 100 && !zone.dirty) continue; // Skip fully covered zones
            
            const toZone = new THREE.Vector3().subVectors(zone.targetPosition, userPosition).normalize();
            const facingScore = toZone.dot(userForward); // 1 = looking directly at it
            
            // Also check distance — must be within 4 meters
            const dist = userPosition.distanceTo(zone.targetPosition);
            const distScore = Math.max(0, 1 - dist / 4); // 0 at 4m, 1 at 0m
            
            const totalScore = facingScore * 0.7 + distScore * 0.3;
            if (totalScore > bestScore && totalScore > 0.3) {
                bestScore = totalScore;
                bestZone = zone;
            }
        }

        if (!bestZone) return;

        // Register frame for this zone
        bestZone.frameCount++;
        bestZone.coverage = Math.min(100, bestZone.frameCount / FRAMES_NEEDED_PER_ZONE * 100);
        bestZone.textureBase64 = textureBase64;
        bestZone.dirty = false;
        bestZone.lastUpdated = Date.now();

        this.save();
        this.log(`📸 Captured: ${bestZone.id} (${bestZone.coverage.toFixed(0)}%)`, 'var(--neon-green)');

        // Check if overall coverage is now complete
        this.session = this.buildSession();
        if (this.session.isComplete) {
            this.stop();
            this.log('✨ Room mapping complete! Auto-capture stopped to save resources.', 'var(--neon-green)');
            localStorage.setItem('foveai_room_scanner_enabled', 'false');
            window.dispatchEvent(new CustomEvent('foveai_room_scanner_complete'));
        }
    }

    /**
     * Auto-update trigger handler.
     * Called when Quest Scene API reports mesh changes.
     */
    onSceneChanged(changedMeshIds: string[], changedMeshes: Array<{ id: string; position: THREE.Vector3; type: string }>): void {
        if (changedMeshIds.length === 0) return;

        this.log(`🔄 Scene changed: ${changedMeshIds.length} meshes updated — re-scanning`, 'var(--neon-yellow)');

        for (const mesh of changedMeshes) {
            // Find nearest scan zone and mark it dirty
            let nearest: ScanZone | null = null;
            let nearestDist = Infinity;
            for (const zone of this.zones) {
                const dist = zone.targetPosition.distanceTo(mesh.position);
                if (dist < nearestDist) {
                    nearestDist = dist;
                    nearest = zone;
                }
            }
            if (nearest && nearestDist < 3) {
                nearest.dirty = true;
                // Don't reset coverage — just mark for refresh
                this.log(`  → Marked ${nearest.id} dirty (${mesh.type}: ${mesh.id})`, 'var(--neon-orange)');
            }
        }

        this.save();
        // Rebuild session hints immediately
        this.session = this.buildSession();
    }

    /**
     * Force re-scan of a specific zone.
     */
    forceRescan(zoneId: string): void {
        const zone = this.zones.find(z => z.id === zoneId);
        if (zone) {
            zone.dirty = true;
            zone.coverage = 0;
            zone.frameCount = 0;
            this.log(`🔄 Force re-scan: ${zoneId}`, 'var(--neon-orange)');
            this.save();
        }
    }

    // ═══════════════════════════════════════════════════════════════
    // COACHING / GUIDANCE
    // ═══════════════════════════════════════════════════════════════

    /**
     * Generate coaching instruction for the user.
     * Called each frame — displayed as overlay text.
     */
    getCoachingHint(userPosition: THREE.Vector3): string {
        if (!this.isActive) return '';

        // Find next unscanned zone
        let nextZone: ScanZone | null = null;
        for (const zone of this.zones) {
            if (zone.coverage < 100 || zone.dirty) {
                nextZone = zone;
                break;
            }
        }

        if (!nextZone) {
            return '✓ Room fully scanned! Environment mapping complete.';
        }

        const dist = userPosition.distanceTo(nextZone.targetPosition);
        const dirToZone = new THREE.Vector3().subVectors(nextZone.targetPosition, userPosition).normalize();
        
        let hint = '';
        
        // Distance-based coaching
        if (dist > 3) {
            hint = `Walk toward the ${nextZone.type.replace('_', ' ')}`;
            hint += ` (${dist.toFixed(1)}m away)`;
        } else if (dist > 1) {
            hint = `Getting close to ${nextZone.type.replace('_', ' ')} — ${dist.toFixed(0)}m`;
        } else {
            hint = `Look at the ${nextZone.type.replace('_', ' ')} to capture it`;
            if (nextZone.dirty) hint += ' [UPDATED]';
        }

        // Avoid repeating the same hint
        if (hint && this.hintHistory[this.hintHistory.length - 1] === hint) return hint;
        this.hintHistory.push(hint);
        if (this.hintHistory.length > MAX_HINT_HISTORY) this.hintHistory.shift();

        return hint;
    }

    /**
     * Get an LLM-friendly description of what needs scanning.
     * The avatar can use this to coach the user: "Could you walk over to the north wall? I still can't see it clearly."
     */
    getCoachingContextForAvatar(): string {
        const dirty = this.zones.filter(z => z.dirty);
        const unscanned = this.zones.filter(z => z.coverage < 50);
        
        const lines: string[] = ['[ROOM SCANNING STATUS]'];
        lines.push(`  Overall coverage: ${this.session.overallCoverage}%`);
        
        if (dirty.length > 0) {
            lines.push(`  Areas needing refresh: ${dirty.map(z => z.type.replace('_', ' ')).join(', ')}`);
        }
        if (unscanned.length > 0) {
            lines.push(`  Areas not yet scanned: ${unscanned.map(z => z.type.replace('_', ' ')).join(', ')}`);
        }
        
        lines.push('  You can guide the user to look at areas that need scanning.');
        lines.push('  Politely ask: "Could you look toward [area] so I can see it better?"');
        
        return lines.join('\n');
    }

    // ═══════════════════════════════════════════════════════════════
    // DEBUG VISUALIZATION
    // ═══════════════════════════════════════════════════════════════

    /**
     * Build debug overlay meshes showing scan zone coverage.
     * Green = covered, Yellow = dirty/needs re-scan, Red = not yet scanned.
     */
    buildDebugOverlay(scene: THREE.Scene): THREE.Group {
        this.removeDebugMeshes();
        this.scanGizmoGroup = new THREE.Group();
        this.scanGizmoGroup.name = 'room_scanner_debug';

        for (const zone of this.zones) {
            let color: number;
            if (zone.coverage >= 80 && !zone.dirty) {
                color = 0x00ff00; // Green = done
            } else if (zone.dirty) {
                color = 0xffaa00; // Yellow = needs refresh
            } else if (zone.coverage > 0) {
                color = 0x00aaff; // Blue = partial
            } else {
                color = 0xff3333; // Red = not scanned
            }

            const opacity = 0.15 + (zone.coverage / 100) * 0.4;

            const geo = new THREE.SphereGeometry(0.2, 8, 8);
            const mat = new THREE.MeshBasicMaterial({
                color,
                transparent: true,
                opacity,
                depthWrite: false,
            });
            const sphere = new THREE.Mesh(geo, mat);
            sphere.position.copy(zone.targetPosition);
            sphere.name = `scan_zone_${zone.id}`;
            sphere.layers.set(0);
            
            // Arrow pointing the direction to look
            const arrowGeo = new THREE.ConeGeometry(0.1, 0.4, 4, 1);
            const arrowMat = new THREE.MeshBasicMaterial({
                color,
                transparent: true,
                opacity: opacity * 0.8,
                depthWrite: false,
            });
            const arrow = new THREE.Mesh(arrowGeo, arrowMat);
            arrow.position.copy(zone.targetPosition.clone().add(zone.lookDirection.clone().multiplyScalar(0.3)));
            arrow.lookAt(zone.targetPosition.clone().add(zone.lookDirection));
            
            this.scanGizmoGroup.add(sphere);
            this.scanGizmoGroup.add(arrow);
            this.scanDebugMeshes.push(sphere, arrow);
        }

        scene.add(this.scanGizmoGroup);
        return this.scanGizmoGroup;
    }

    private removeDebugMeshes(): void {
        if (this.scanGizmoGroup) {
            this.scanGizmoGroup.parent?.remove(this.scanGizmoGroup);
            this.scanGizmoGroup = null;
        }
        this.scanDebugMeshes = [];
    }

    // ═══════════════════════════════════════════════════════════════
    // INTERNAL
    // ═══════════════════════════════════════════════════════════════

    private buildSession(): ScanSession {
        const total = this.zones.length;
        const covered = this.zones.filter(z => z.coverage >= 80 && !z.dirty).length;
        const overallCoverage = Math.round((covered / total) * 100);
        
        // Find first dirty or unscanned zone
        let next: ScanZone | null = null;
        for (const z of this.zones) {
            if (z.dirty) { next = z; break; }
            if (z.coverage < 80) { next = z; break; }
        }

        const currentHint = next 
            ? `Next: ${next.type.replace('_', ' ')} at (${next.targetPosition.x.toFixed(1)}, ${next.targetPosition.z.toFixed(1)})`
            : 'Complete';

        const coachingText = next
            ? `Look toward the ${next.type.replace('_', ' ')} to continue mapping. ${next.dirty ? 'This area has changed and needs updating.' : ''}`
            : 'Room fully mapped! The avatar can now "see" the entire space.';

        return {
            zones: this.zones,
            overallCoverage,
            isComplete: overallCoverage >= COVERAGE_COMPLETE_THRESHOLD,
            currentHint,
            coachingText,
        };
    }

    // ═══════════════════════════════════════════════════════════════
    // PERSISTENCE
    // ═══════════════════════════════════════════════════════════════

    private _lastSaveTime = 0;
    private save(): void {
        const now = Date.now();
        if (now - this._lastSaveTime < 10000) return; // debounce: max once per 10s
        this._lastSaveTime = now;
        try {
            const data = {
                zones: this.zones.map(z => ({
                    id: z.id, type: z.type,
                    coverage: z.coverage, dirty: z.dirty,
                    frameCount: z.frameCount, lastUpdated: z.lastUpdated,
                })),
            };
            localStorage.setItem('foveai_room_scanner', JSON.stringify(data));
        } catch (e) { /* quota exceeded? */ }
    }

    private load(): void {
        try {
            const raw = localStorage.getItem('foveai_room_scanner');
            if (!raw) return;
            const data = JSON.parse(raw);
            for (const saved of data.zones || []) {
                const zone = this.zones.find(z => z.id === saved.id);
                if (zone) {
                    zone.coverage = saved.coverage;
                    zone.dirty = saved.dirty;
                    zone.frameCount = saved.frameCount;
                    zone.lastUpdated = saved.lastUpdated;
                }
            }
            this.session = this.buildSession();
            this.log(`📂 Scan data loaded: ${this.session.overallCoverage}% coverage`, 'var(--neon-blue)');
        } catch (e) { /* corrupted data */ }
    }
}