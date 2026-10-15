export declare const VISEMES: string[];
export declare function envelope(prev: number, energy: number, attack?: number, release?: number): number;
export declare function visemeAt(tSec: number, energy: number, seed?: number): { name: string; value: number } | null;
export declare function breathing(tSec: number, rate?: number): number;
export declare function weightShift(tSec: number): { x: number; roll: number };
export declare function headIdle(tSec: number): { yaw: number; pitch: number; roll: number };
export declare function talkBody(tSec: number, energy: number): { nod: number; pitch: number; torso: number; hand: number };
export declare function blinkAt(tSec: number, seed?: number): number;
export declare function isSpeaking(env: number, threshold?: number): boolean;
export interface MorphBinding { mesh: any; index: number }
export declare const MORPH_ALIASES: Record<string, string[]>;
export declare function resolveMorphBindings(root: any, target: string): MorphBinding[];
export declare function applyMorph(root: any, target: string, value: number): number;
