/**
 * VADEngine.js
 * Extracted from XR_Vessel Dashboard.ts
 * Provides Voice Activity Detection and MediaRecorder-based STT targeting /api/soul/stt
 */

export class VADEngine {
    constructor(options = {}) {
        this.mediaStream = null;
        this.mediaRecorder = null;
        this.audioChunks = [];
        this.audioContext = null;
        this.audioSourceNode = null;
        this.analyser = null;
        this.vadInterval = null;
        
        this.isListening = false;
        this.isUserEditing = false;
        this.isPaused = false;
        
        // Options
        this.onStart = options.onStart || null;
        this.onStop = options.onStop || null;
        this.onResult = options.onResult || null;
        this.onError = options.onError || null;
        this.onLog = options.onLog || console.log;
        
        // VAD Constants
        this.SPEECH_THRESHOLD = 0.025;
        this.SILENCE_THRESHOLD = 0.004;
        this.SILENCE_DURATION_MS = 1200;
        
        // Track editing state
        const chatInput = document.getElementById('speech-text');
        if (chatInput) {
            chatInput.addEventListener('input', () => { this.isUserEditing = true; });
            chatInput.addEventListener('blur', () => { this.isUserEditing = false; });
            chatInput.addEventListener('focus', () => { this.isUserEditing = true; });
        }
    }

    async startListening() {
        if (this.isListening) return;
        
        try {
            // Check for cached stream
            const cachedStream = window.foveaiCachedMicStream;
            if (cachedStream && cachedStream.active) {
                this.mediaStream = cachedStream;
                this.onLog('[VAD] Using pre-cached microphone stream');
            } else {
                this.mediaStream = await navigator.mediaDevices.getUserMedia({ 
                    audio: { 
                        echoCancellation: true, 
                        noiseSuppression: true, 
                        autoGainControl: true 
                    } 
                });

                // Workaround to keep mic alive in Oculus Browser
                try {
                    const aud = new Audio();
                    aud.srcObject = this.mediaStream;
                    aud.muted = true;
                    aud.play().catch(e => console.warn('[VAD] Workaround audio play failed:', e));
                    window.foveaiWorkaroundAudio = aud;
                } catch (err) {
                    console.warn('[VAD] Workaround audio setup failed:', err);
                }
            }

            // Fallback for Safari/iOS that don't support Opus
            const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') 
                ? 'audio/webm;codecs=opus' 
                : (MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : 'audio/mp4');

            this.mediaRecorder = new MediaRecorder(this.mediaStream, { mimeType });
            this.audioChunks = [];
            const recordingStartTime = Date.now();

            this.mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    this.audioChunks.push(event.data);
                }
            };

            this.mediaRecorder.onstop = async () => {
                const recordingDurationMs = Date.now() - recordingStartTime;
                const audioBlob = new Blob(this.audioChunks, { type: mimeType });
                
                // Guard against hallucinations on near-silent clips
                if (recordingDurationMs < 800 || audioBlob.size < 3000) {
                    this.onLog(`[VAD] Clip too short (${recordingDurationMs}ms, ${audioBlob.size}B) — skipping STT`);
                } else {
                    await this.transcribe(audioBlob, mimeType);
                }
                
                const cachedStream = window.foveaiCachedMicStream;
                if (this.mediaStream && this.mediaStream !== cachedStream) {
                    this.mediaStream.getTracks().forEach(t => t.stop());
                }
                this.mediaStream = null;
                
                if (this.onStop) this.onStop();
            };

            this.mediaRecorder.start();
            this.isListening = true;
            this.startVAD(this.mediaStream);
            
            if (this.onStart) this.onStart();
            this.onLog('[MIC] Listening (MediaRecorder + VAD)...');

        } catch (err) {
            this.onLog(`[VAD] MediaRecorder start failed: ${err}`);
            this.isListening = false;
            if (this.onError) this.onError(err);
        }
    }

    stopListening() {
        if (!this.isListening) return;
        this.isListening = false;
        
        this.stopVAD();
        if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
            this.mediaRecorder.stop();
        }
    }

    startVAD(stream) {
        try {
            this.stopVAD();

            const AudioContextClass = window.AudioContext || window.webkitAudioContext;
            if (!AudioContextClass) return;

            let ctx = window.foveaiAudioContext;
            if (!ctx || ctx.state === 'closed') {
                ctx = new AudioContextClass();
                window.foveaiAudioContext = ctx;
            }
            this.audioContext = ctx;

            if (ctx.state === 'suspended') {
                ctx.resume().catch(err => console.warn('[VAD] Shared AudioContext resume failed:', err));
            }

            const source = ctx.createMediaStreamSource(stream);
            this.audioSourceNode = source;
            const analyserNode = ctx.createAnalyser();
            analyserNode.fftSize = 512;
            source.connect(analyserNode);
            this.analyser = analyserNode;

            const bufferLength = analyserNode.frequencyBinCount;
            const dataArray = new Float32Array(bufferLength);

            let hasSpoken = false;
            let silenceStart = 0;

            this.vadInterval = setInterval(() => {
                if (!this.analyser || !this.isListening || this.isPaused) return;

                this.analyser.getFloatTimeDomainData(dataArray);

                let sumSquares = 0;
                for (let i = 0; i < bufferLength; i++) {
                    sumSquares += dataArray[i] * dataArray[i];
                }
                const rms = Math.sqrt(sumSquares / bufferLength);

                if (rms > this.SPEECH_THRESHOLD) {
                    if (!hasSpoken) {
                        hasSpoken = true;
                        this.onLog('[VAD] Speech detected...');
                    }
                    silenceStart = 0;
                } else if (rms < this.SILENCE_THRESHOLD && hasSpoken) {
                    if (silenceStart === 0) {
                        silenceStart = Date.now();
                    } else if (Date.now() - silenceStart > this.SILENCE_DURATION_MS) {
                        if (this.isUserEditing) {
                            silenceStart = Date.now();
                            return;
                        }
                        this.onLog('[VAD] Silence detected. Auto-stopping...');
                        this.stopListening();
                    }
                } else if (hasSpoken) {
                    silenceStart = 0;
                }
            }, 100);
        } catch (e) {
            console.warn('[VAD] Failed to initialize Web Audio VAD:', e);
        }
    }

    pauseVAD() {
        this.isPaused = true;
    }

    resumeVAD() {
        this.isPaused = false;
    }

    stopVAD() {
        if (this.vadInterval) {
            clearInterval(this.vadInterval);
            this.vadInterval = null;
        }
        if (this.audioSourceNode) {
            try { this.audioSourceNode.disconnect(); } catch (e) {}
            this.audioSourceNode = null;
        }
        if (this.analyser) {
            try { this.analyser.disconnect(); } catch (e) {}
            this.analyser = null;
        }
        this.audioContext = null; 
    }

    async transcribe(audioBlob, mimeType) {
        try {
            const base64data = await new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onloadend = () => {
                    resolve(reader.result.split(',')[1]);
                };
                reader.onerror = reject;
                reader.readAsDataURL(audioBlob);
            });

            const response = await fetch('/api/soul/stt', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    audio_base64: base64data,
                    format: mimeType,
                    filename: 'recording.webm'
                })
            });

            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            
            const data = await response.json();
            if (data.text) {
                if (this.onResult) this.onResult(data.text);
            } else {
                console.warn('[VAD] Transcribe returned empty text or failed:', data);
                if (this.onError) this.onError('Empty response');
            }
        } catch (error) {
            console.error('[VAD] Failed to transcribe via Soul:', error);
            if (this.onError) this.onError(error.message);
        }
    }
}

window.VADEngine = VADEngine;
