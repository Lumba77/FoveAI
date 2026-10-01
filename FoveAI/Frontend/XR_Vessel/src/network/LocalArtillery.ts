import { localMemory } from './LocalMemory';

export class LocalArtillery {
  private audioWorker: Worker | null = null;
  private isInitializing: boolean = false;
  private isReady: boolean = false;

  constructor() {}

  public async ensureInitialized() {
    if (this.isReady) return;
    if (this.isInitializing) {
        // Wait for current init
        while (this.isInitializing) {
            await new Promise(r => setTimeout(r, 100));
        }
        return;
    }

    this.isInitializing = true;
    console.log('[SoundForge] Lazy-loading AI engine...');
    
    try {
        await new Promise<void>((resolve, reject) => {
            this.audioWorker = new Worker(new URL('./AudioWorker.ts', import.meta.url), { type: 'module' });
            
            const timeout = setTimeout(() => reject(new Error('SoundForge Init Timeout')), 30000);

            this.audioWorker.onmessage = (event) => {
                const { type, message } = event.data;
                if (type === 'ready') {
                    clearTimeout(timeout);
                    this.isReady = true;
                    resolve();
                } else if (type === 'error') {
                    clearTimeout(timeout);
                    reject(new Error(message));
                }
            };

            this.audioWorker.postMessage({ type: 'init' });
        });
        console.log('[SoundForge] AI engine online.');
    } catch (err) {
        console.error('[SoundForge] Initialization failed:', err);
        throw err;
    } finally {
        this.isInitializing = false;
    }
  }

  public async generateSound(prompt: string, category: string = 'expressive'): Promise<string> {
    try {
        await this.ensureInitialized();
        if (!this.audioWorker) throw new Error('Worker missing');

        console.log(`[SoundForge] Forging: ${prompt}`);
        
        return await new Promise<string>((resolve, reject) => {
            const resultHandler = async (event: MessageEvent) => {
                if (event.data.type === 'result' && event.data.prompt === prompt) {
                    this.audioWorker?.removeEventListener('message', resultHandler);
                    const base64 = event.data.base64;
                    
                    if (base64) {
                        await localMemory.soundboard.add({
                            label: prompt,
                            category,
                            base64,
                            timestamp: Date.now()
                        });
                        resolve(base64);
                    } else {
                        reject(new Error('Empty audio buffer'));
                    }
                } else if (event.data.type === 'error') {
                    this.audioWorker?.removeEventListener('message', resultHandler);
                    reject(new Error(event.data.message));
                }
            };

            this.audioWorker?.addEventListener('message', resultHandler);
            this.audioWorker?.postMessage({ type: 'generate', prompt });
        });
    } catch (err) {
        console.warn('[SoundForge] Generation failed:', err);
        return ''; 
    }
  }

  public async imagine(prompt: string): Promise<string> {
    console.log('[LocalArtillery] Imagining placeholder:', prompt);
    return ""; 
  }
}

export const localArtillery = new LocalArtillery();
