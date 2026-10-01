/**
 * IMPULSE MANAGER
 * This system fetches "subconscious" thought instructions (JSON) from the Director
 * and injects them directly into Jen's cognitive loop as physical actions.
 */
export class ImpulseManager {
    private pollInterval: number = 3000; // Check for new impulses every 3 seconds
    private isActive: boolean = false;
    private lastImpulseId: string | null = null;

    constructor() {}

    public start() {
        if (this.isActive) return;
        this.isActive = true;
        console.log('[Impulse] Subconscious Link Online.');
        this.poll();
    }

    public stop() {
        this.isActive = false;
    }

    private async poll() {
        if (!this.isActive) return;

        try {
            // Fetch the latest impulse from the local Director node
            // Note: In a production environment, this might be a POST with state,
            // but for OMEGA_076 we fetch a local JSON injection.
            const response = await fetch('/impulses.json?t=' + Date.now());
            if (response.ok) {
                const data = await response.json();
                
                if (data && data.id !== this.lastImpulseId) {
                    this.lastImpulseId = data.id;
                    this.injectImpulse(data.instruction);
                }
            }
        } catch (err) {
            // Silently fail to prevent console spam if Director is offline
        }

        setTimeout(() => this.poll(), this.pollInterval);
    }

    private async injectImpulse(instruction: string) {
        if (!instruction) return;
        
        console.log(`[Impulse] Subconscious Injection: "${instruction}"`);
        (window as any).log?.(`[Subconscious] ${instruction}`, 'var(--neon-pink)');

        // Route the instruction directly through the Brain's interceptor
        // This allows [WALK: 5], [GESTURE: "Happy"], etc. to fire physically
        // Lazy-load LocalBrain to keep it code-split
        try {
            const { localBrain } = await import('./LocalBrain');
            if (localBrain && (localBrain as any).interceptToolCalls) {
                await (localBrain as any).interceptToolCalls(instruction);
            }
        } catch (err) {
            console.warn('[Impulse] Failed to load LocalBrain for impulse:', err);
        }
    }
}

export const impulseManager = new ImpulseManager();
