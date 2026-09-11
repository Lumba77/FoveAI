/**
    * VOICE CLONE - Sample user's voice and speak as them.
        * Uses XTTSv2 or Piper with just 6 seconds of audio sample.
 *
 * The avatar can answer the user's phone, respond to voicemails,
    * or perform assistant tasks using the user's own voice (with consent).
        *
 * Models: XTTSv2(coqui / XTTS - v2 on HF Hub), Piper with custom voice,
 * ElevenLabs(API, highest quality), PlayHT(API)
    */
export interface VoiceSample { base64: string; duration: number; source: string; }
export interface VoiceProfile { name: string; samples: VoiceSample[]; model: 'xttsv2' | 'piper' | 'elevenlabs'; }

const envProcess = typeof globalThis !== 'undefined' ? (globalThis as any).process : undefined;
const HF_TOKEN = envProcess?.env?.HF_TOKEN || '';

export class VoiceClone {
    private profiles: Map<string, VoiceProfile> = new Map();
    private userProfile: VoiceProfile | null = null;
    private log: (m: string, c: string) => void;

    constructor(logFn?: (m: string, c: string) => void) {
        this.log = logFn || ((m, c) => console.log('[VoiceClone] ' + m));
    }

    /**
     * Record voice sample from microphone.
     * Just 6 seconds is enough for XTTSv2 voice cloning.
     */
    async recordSample(durationSec = 6): Promise<VoiceSample | null> {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            const recorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
            const chunks: Blob[] = [];
            recorder.ondataavailable = e => chunks.push(e.data);
            recorder.start();

            return new Promise(resolve => {
                setTimeout(async () => {
                    recorder.stop();
                    stream.getTracks().forEach(t => t.stop());
                    const blob = new Blob(chunks, { type: 'audio/webm' });
                    const reader = new FileReader();
                    reader.onload = () => {
                        const b64 = (reader.result as string).split(',')[1] || '';
                        resolve({ base64: b64, duration: durationSec, source: 'microphone' });
                    };
                    reader.readAsDataURL(blob);
                }, durationSec * 1000);
            });
        } catch (e: any) {
            this.log('Mic access denied: ' + e.message, '#f80');
            return null;
        }
    }

    /** Create user's voice profile from samples. */
    async createProfile(name: string, model: VoiceProfile['model'] = 'xttsv2'): Promise<VoiceProfile | null> {
        const sample = await this.recordSample(6);
        if (!sample) return null;
        const profile = { name, samples: [sample], model };
        this.userProfile = profile;
        this.profiles.set(name, profile);
        this.log('Voice profile created: ' + name + ' (' + model + ')', '#0f0');
        return profile;
    }

    /** Synthesize speech in user's cloned voice. */
    async speak(text: string, useUserVoice = true): Promise<string | null> {
        const profile = useUserVoice ? this.userProfile : null;
        if (!profile) return this.speakDefault(text);

        try {
            const r = await fetch('/api/voice/clone', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    text,
                    voiceProfile: profile.name,
                    model: profile.model,
                    samples: profile.samples.map(s => s.base64),
                }),
            });
            if (r.ok) {
                const data = await r.json();
                return data.audioBase64 || null; // Play via Audio element
            }
        } catch { }
        return this.speakDefault(text);
    }

    /** Fallback: default Piper Amy voice (no cloning needed). */
    async speakDefault(text: string): Promise<string | null> {
        try {
            const r = await fetch('/api/mouth/tts', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text, voice: 'piper_amy' }),
            });
            if (r.ok) return (await r.json()).audioBase64 || null;
        } catch { }
        return null;
    }

    /** Answer a call using cloned voice. */
    async answerCall(text: string): Promise<string | null> {
        return this.speak(text, true);
    }

    getContext(): string {
        if (this.userProfile) {
            return `[VOICE CLONE] User voice profile "${this.userProfile.name}" ready (${this.userProfile.model}). Can speak as the user.`;
        }
        return '[VOICE CLONE] No voice profile yet. Call createProfile() to sample 6s of audio.';
    }
}
