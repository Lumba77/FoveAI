import { pipeline, env } from '@huggingface/transformers';

// NUCLEAR FIX: Explicit CDN pathing to avoid local 404/redirects
env.allowLocalModels = false;
env.useBrowserCache = true;
env.remoteHost = 'https://huggingface.co';
env.remotePathTemplate = '{model}/resolve/{revision}/';

let synthesizer: any = null;

self.onmessage = async (event) => {
    const { type, prompt, voice, token } = event.data;

    if (type === 'init') {
        try {
            self.postMessage({ type: 'progress', status: 'Loading Sound Forge (Bark-Small)...' });
            
            const options: any = {
                device: 'webgpu',
                dtype: 'q8', 
            };
            // Only attach token if physically present
            if (token && typeof token === 'string') options.token = token;

            synthesizer = await pipeline('text-to-speech', 'onnx-community/bark-small', options);

            self.postMessage({ type: 'ready' });
        } catch (err: any) {
            self.postMessage({ type: 'error', message: err.message });
        }
    }

    if (type === 'generate') {
        if (!synthesizer) {
            self.postMessage({ type: 'error', message: 'Sound Forge not initialized' });
            return;
        }

        try {
            self.postMessage({ type: 'progress', status: 'Forging sound...' });
            
            const output = await synthesizer(prompt, {
                voice_preset: voice || 'v2/en_speaker_6', 
            });

            // ATOMIC CHECK: Ensure audio data exists before accessing .length
            if (!output || !output.audio) {
                throw new Error('Synthesizer returned null audio buffer');
            }

            // Convert Float32Array to base64 WAV
            const wavBuffer = encodeWAV(output.audio, output.sampling_rate);
            const base64 = arrayBufferToBase64(wavBuffer);

            self.postMessage({ 
                type: 'result', 
                base64: `data:audio/wav;base64,${base64}`, 
                prompt: prompt 
            });
        } catch (err: any) {
            self.postMessage({ type: 'error', message: err.message });
        }
    }
};

function arrayBufferToBase64(buffer: ArrayBuffer): string {
    if (!buffer) return '';
    let binary = '';
    const bytes = new Uint8Array(buffer);
    const len = bytes.byteLength;
    for (let i = 0; i < len; i++) {
        binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary);
}

function encodeWAV(samples: Float32Array, sampleRate: number): ArrayBuffer {
    if (!samples || samples.length === 0) return new ArrayBuffer(0);
    
    const buffer = new ArrayBuffer(44 + samples.length * 2);
    const view = new DataView(buffer);

    writeString(view, 0, 'RIFF');
    view.setUint32(4, 36 + samples.length * 2, true);
    writeString(view, 8, 'WAVE');
    writeString(view, 12, 'fmt ');
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, 1, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    writeString(view, 36, 'data');
    view.setUint32(40, samples.length * 2, true);

    floatTo16BitPCM(view, 44, samples);
    return buffer;
}

function floatTo16BitPCM(output: DataView, offset: number, input: Float32Array) {
    if (!input) return;
    for (let i = 0; i < input.length; i++, offset += 2) {
        const s = Math.max(-1, Math.min(1, input[i]));
        output.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
    }
}

function writeString(view: DataView, offset: number, string: string) {
    for (let i = 0; i < string.length; i++) {
        view.setUint8(offset + i, string.charCodeAt(i));
    }
}
