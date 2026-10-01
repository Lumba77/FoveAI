import { localMemory } from '../network/LocalMemory';
import { BracketParser } from '../senses/BracketParser';
import { soundboardRegistry } from '../senses/SoundboardRegistry';

// Speech recognition interface (browser API)
interface SpeechRecognitionEvent extends Event {
    results: SpeechRecognitionResultList;
}

interface SpeechRecognitionResultList {
    length: number;
    item(index: number): SpeechRecognitionResult;
    [index: number]: SpeechRecognitionResult;
}

interface SpeechRecognitionResult {
    length: number;
    item(index: number): SpeechRecognitionAlternative;
    [index: number]: SpeechRecognitionAlternative;
    isFinal: boolean;
}

interface SpeechRecognitionAlternative {
    transcript: string;
    confidence: number;
}

interface SpeechRecognitionError extends Event {
    error: string;
    message: string;
}

interface SpeechRecognition extends EventTarget {
    continuous: boolean;
    interimResults: boolean;
    lang: string;
    onstart: () => void;
    onend: () => void;
    onresult: (event: SpeechRecognitionEvent) => void;
    onerror: (event: SpeechRecognitionError) => void;
    start(): void;
    stop(): void;
}

declare global {
    interface Window {
        SpeechRecognition: new () => SpeechRecognition;
        webkitSpeechRecognition: new () => SpeechRecognition;
    }
}

export class VideoChat {
    private container: HTMLElement;
    private videoElement: HTMLVideoElement | null = null;
    private peerConnection: RTCPeerConnection | null = null;
    private localStream: MediaStream | null = null;
    private remoteStream: MediaStream | null = null;
    private isActive: boolean = false;
    private isVideoEnabled: boolean = true;
    private isAudioEnabled: boolean = true;

    constructor() {
        this.container = document.createElement('div');
        this.container.id = 'foveai-videochat';
        this.container.className = 'hidden';
        (window as any).foveaiVideoChat = this;
        this.applyStyles();
        this.render();

        // Connect to Antigravity IDE bridge
        try {
            const agyStream = new EventSource('/api/agy/stream');
            agyStream.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    if (data.message) {
                        this.speakWithMouthTTS(data.message, undefined, 'neutral', undefined, 'antigravity');
                    }
                } catch(e) {}
            };
        } catch(e) {}
    }

    public toggle() {
        if (this.isActive) {
            this.stop();
        } else {
            this.start();
        }
    }

    public start() {
        if (this.isActive) return;
        
        this.isActive = true;
        this.container.classList.remove('hidden');

        // Minimize Dashboard for immersion
        if ((window as any).foveaiDashboard) {
            (window as any).foveaiDashboard.toggle(false);
        }

        // Trigger Avatar Zoom
        if ((window as any).avatarManager) {
            (window as any).avatarManager.setZoom(true);
        }
        
        // Request media access
        this.requestMediaAccess().then(success => {
            if (success) {
                this.log('Vessel Link: Immersive Video Active', '#39ff14');
                this.renderUIState();
            } else {
                this.log('Media access denied', '#ff007f');
                this.stop();
            }
        });
    }

    public stop() {
        this.isActive = false;
        this.container.classList.add('hidden');

        // Trigger Avatar Zoom Out
        if ((window as any).avatarManager) {
            (window as any).avatarManager.setZoom(false);
        }

        this.cleanup();
        this.log('Video chat ended', '#ffaa00');
    }

    private async requestMediaAccess(): Promise<boolean> {
        try {
            this.localStream = await navigator.mediaDevices.getUserMedia({
                video: true,
                audio: true
            });
            
            if (this.videoElement) {
                this.videoElement.srcObject = this.localStream;
                this.videoElement.muted = true; // Prevent feedback
                this.videoElement.play().catch(e => console.warn('[VideoChat] Video play interrupted:', e));
            }            
            return true;
        } catch (err) {
            console.error('[VideoChat] Media access error:', err);
            return false;
        }
    }

    private cleanup() {
        if (this.localStream) {
            this.localStream.getTracks().forEach(track => track.stop());
            this.localStream = null;
        }
        if (this.peerConnection) {
            this.peerConnection.close();
            this.peerConnection = null;
        }
        if (this.remoteStream) {
            this.remoteStream.getTracks().forEach(track => track.stop());
            this.remoteStream = null;
        }
    }

    private log(msg: string, color: string) {
        (window as any).log?.(msg, color);
    }

    private applyStyles() {
        const style = document.createElement('style');
        style.textContent = `
            #foveai-videochat {
                position: fixed;
                top: 0;
                left: 0;
                width: 100vw;
                height: 100vh;
                background: transparent;
                border: none;
                z-index: 9999;
                overflow: hidden;
                pointer-events: none;
                display: flex;
                flex-direction: column;
            }

            #foveai-videochat.hidden {
                display: none;
            }

            .main-vessel {
                position: relative;
                flex: 1;
                width: 100%;
                height: 100%;
                background: transparent;
                display: flex;
                align-items: center;
                justify-content: center;
                pointer-events: none;
            }

            /* The PiP container for the user camera */
            .user-pip {
                position: absolute;
                top: 20px;
                right: 20px;
                width: 120px;
                height: 90px;
                background: #02050a;
                border: 1px solid var(--neon-pink);
                border-radius: 4px;
                overflow: hidden;
                z-index: 100;
                pointer-events: auto;
                box-shadow: 0 0 15px rgba(255, 0, 127, 0.2);
            }

            .vessel-label {
                position: absolute;
                top: 5px;
                left: 5px;
                font-family: 'Orbitron', sans-serif;
                font-size: 8px;
                color: var(--neon-blue);
                background: rgba(0, 0, 0, 0.6);
                padding: 1px 4px;
                border-radius: 2px;
                letter-spacing: 1px;
                z-index: 10;
            }

            #local-video {
                width: 100%;
                height: 100%;
                background: #000;
                object-fit: cover;
                transform: scaleX(-1);
            }

            #local-video {
                width: 100%;
                height: 100%;
                background: #000;
                object-fit: cover;
                transform: scaleX(-1);
            }

            /* We hide the remote video element because we look at the 3D avatar instead */
            #remote-video {
                display: none;
            }

            .video-controls {
                position: absolute;
                bottom: 5px;
                left: 0;
                width: 100%;
                display: flex;
                justify-content: center;
                gap: 5px;
                pointer-events: none;
                padding: 2px;
            }

            .vc-btn {
                width: 38px;
                height: 38px;
                border-radius: 50%;
                border: 1px solid var(--neon-blue);
                background: rgba(0, 243, 255, 0.1);
                color: var(--neon-blue);
                cursor: pointer;
                font-family: 'Orbitron', monospace;
                font-weight: bold;
                font-size: 0.7rem;
                display: flex;
                align-items: center;
                justify-content: center;
                transition: all 0.3s ease;
                pointer-events: auto;
                box-shadow: 0 0 10px rgba(0, 243, 255, 0.3);
                text-shadow: 0 0 5px rgba(0, 243, 255, 0.6);
            }

            .vc-btn:hover {
                background: var(--neon-blue);
                color: #000;
                box-shadow: 0 0 15px var(--neon-blue);
            }

            .vc-btn.end {
                border-color: var(--neon-pink);
                color: var(--neon-pink);
                background: rgba(255, 0, 127, 0.1);
                box-shadow: 0 0 10px rgba(255, 0, 127, 0.3);
                text-shadow: 0 0 5px rgba(255, 0, 127, 0.6);
            }
        `;
        document.head.appendChild(style);
    }

    private render() {
        this.container.innerHTML = `
            <div class="main-vessel">
                <div class="vessel-label">IDENTITY: JEN</div>
                <!-- Main scene is visible through transparency -->
                
                <div class="user-pip">
                    <div class="vessel-label" style="color:var(--neon-pink)">USER</div>
                    <video id="local-video" autoplay playsinline muted></video>
                </div>
            </div>
            
            <div class="video-controls">
                <button class="vc-btn mute" id="btn-mute-audio" title="Mute Audio">
                    <span id="icon-mute">[MIC]</span>
                </button>
                <button class="vc-btn" id="btn-toggle-video" title="Toggle Video">
                    <span id="icon-video">[CAM]</span>
                </button>
                <button class="vc-btn end" id="btn-end-call" title="End Call">
                    <span>[END]</span>
                </button>
            </div>
            
            <video id="remote-video" style="display:none"></video>
        `;

        this.videoElement = this.container.querySelector('#local-video') as HTMLVideoElement;

        const btnMute = this.container.querySelector('#btn-mute-audio');
        const btnVideo = this.container.querySelector('#btn-toggle-video');
        const btnEnd = this.container.querySelector('#btn-end-call');

        btnMute?.addEventListener('click', () => this.toggleAudio());
        btnVideo?.addEventListener('click', () => this.toggleVideo());
        btnEnd?.addEventListener('click', () => this.stop());

        this.log('VideoChat HUD initialized (PiP)', '#00f3ff');
    }

    private renderUIState() {
        const dot = this.container.querySelector('#vc-status-dot') as HTMLElement;
        const text = this.container.querySelector('#vc-status-text') as HTMLElement;
        const iconMute = this.container.querySelector('#icon-mute') as HTMLElement;
        const iconVideo = this.container.querySelector('#icon-video') as HTMLElement;

        if (dot) {
            dot.classList.add('active');
            dot.style.background = this.isAudioEnabled ? 'var(--neon-green)' : '#f00';
        }
        if (text) text.innerText = this.isAudioEnabled ? 'ONLINE' : 'MUTED';
        if (iconMute) iconMute.innerText = this.isAudioEnabled ? '[MIC]' : '[MUT]';
        if (iconVideo) iconVideo.innerText = this.isVideoEnabled ? '[CAM]' : '[OFF]';
    }

    private toggleAudio() {
        if (!this.localStream) return;
        
        const audioTrack = this.localStream.getAudioTracks()[0];
        if (audioTrack) {
            audioTrack.enabled = !audioTrack.enabled;
            this.isAudioEnabled = audioTrack.enabled;
            this.renderUIState();
        }
    }

    private toggleVideo() {
        if (!this.localStream) return;
        
        const videoTrack = this.localStream.getVideoTracks()[0];
        if (videoTrack) {
            videoTrack.enabled = !videoTrack.enabled;
            this.isVideoEnabled = videoTrack.enabled;
            this.renderUIState();
        }
    }

    public getElement() {
        return this.container;
    }

    // Connection methods for peer-to-peer
    public async createOffer() {
        if (!this.peerConnection) {
            this.setupPeerConnection();
        }
        
        if (this.peerConnection) {
            const offer = await this.peerConnection.createOffer();
            await this.peerConnection.setLocalDescription(offer);
            return offer;
        }
        return null;
    }

    public async answerOffer(offer: RTCSessionDescriptionInit) {
        if (!this.peerConnection) {
            this.setupPeerConnection();
        }
        
        if (this.peerConnection) {
            await this.peerConnection.setRemoteDescription(offer);
            const answer = await this.peerConnection.createAnswer();
            await this.peerConnection.setLocalDescription(answer);
            return answer;
        }
        return null;
    }

    public async acceptAnswer(answer: RTCSessionDescriptionInit) {
        if (this.peerConnection) {
            await this.peerConnection.setRemoteDescription(answer);
        }
    }

    private setupPeerConnection() {
        this.peerConnection = new RTCPeerConnection({
            iceServers: [
                { urls: 'stun:stun.l.google.com:19302' },
                { urls: 'stun:stun1.l.google.com:19302' }
            ]
        });

        // Send local stream
        if (this.localStream) {
            this.localStream.getTracks().forEach(track => {
                this.peerConnection?.addTrack(track, this.localStream!);
            });
        }

        // Receive remote stream
        this.peerConnection.ontrack = (event) => {
            if (!this.remoteStream) {
                this.remoteStream = new MediaStream();
            }
            this.remoteStream.addTrack(event.track);
            
            const remoteVideo = document.querySelector('#remote-video') as HTMLVideoElement;
            if (remoteVideo) {
                remoteVideo.srcObject = this.remoteStream;
            }
        };

        // ICE candidate handling
        this.peerConnection.onicecandidate = (event) => {
            if (event.candidate) {
                this.log('ICE candidate generated', '#ffaa00');
            }
        };

        this.peerConnection.onconnectionstatechange = () => {
            if (this.peerConnection?.connectionState === 'connected') {
                this.log('Video chat connected', '#39ff14');
            } else if (this.peerConnection?.connectionState === 'disconnected') {
                this.log('Connection lost', '#ff007f');
            }
        };
    }

    public getLocalStream() {
        return this.localStream;
    }

    public isVideoChatActive() {
        return this.isActive;
    }

    // ========== VOCAL INPUT/OUTPUT FEATURES ==========

    private speechRecognition: SpeechRecognition | null = null;
    private audioContext: AudioContext | null = null;
    private speechSynthesis: SpeechSynthesis | null = null;
    private transcriptDisplay: HTMLElement | null = null;
    private mediaRecorder: MediaRecorder | null = null;
    private audioChunks: Blob[] = [];
    private mediaStream: MediaStream | null = null;
    private useMediaRecorderSTT: boolean = false;

    public async initializeVocalInput() {
        const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
        
        if (!SpeechRecognition) {
            this.log('Speech recognition not available -- will use MediaRecorder + Soul STT fallback', '#ffaa00');
            this.useMediaRecorderSTT = true;
            return;
        }
        this.useMediaRecorderSTT = false;

        try {
            this.speechRecognition = new SpeechRecognition();
            if (this.speechRecognition) {
                this.speechRecognition.continuous = false;
                this.speechRecognition.interimResults = false;
                this.speechRecognition.lang = 'en-US';

                this.speechRecognition.onstart = () => {
                    this.log('Listening for voice input...', '#39ff14');
                };

                this.speechRecognition.onend = () => {
                    this.log('Stopped listening', '#ffaa00');
                };

                this.speechRecognition.onresult = (event: SpeechRecognitionEvent) => {
                    const transcript = event.results[0][0].transcript;
                    this.log(`Voice input: "${transcript}"`, '#00f3ff');
                    this.onVoiceTranscriptReceived(transcript);
                };

                this.speechRecognition.onerror = (event: SpeechRecognitionError) => {
                    this.log(`Speech recognition error: ${event.error}`, '#ff007f');
                };
            }
        } catch (e) {
            this.log('Failed to initialize speech recognition', '#ff007f');
            console.error('[VideoChat] Speech init error:', e);
        }
    }

    public startListening() {
        if (this.useMediaRecorderSTT || !this.speechRecognition) {
            // Fallback: MediaRecorder + Soul STT (Quest 3)
            this.startMediaRecorderSTT();
        } else {
            this.speechRecognition.start();
        }
    }

    public stopListening() {
        if (this.useMediaRecorderSTT || !this.speechRecognition) {
            // MediaRecorder path: stop recording, transcription in onstop
            if (this.mediaRecorder && this.mediaRecorder.state === 'recording') {
                this.mediaRecorder.stop();
            }
        } else {
            this.speechRecognition.stop();
        }
    }

    private async startMediaRecorderSTT() {
        try {
            // Use cached mic stream from XR entry gesture if available
            const cachedStream = (window as any).foveaiCachedMicStream as MediaStream | null;
            if (cachedStream && cachedStream.active) {
                this.mediaStream = cachedStream;
                this.log('Using pre-cached microphone stream', 'var(--neon-blue)');
            } else {
                this.mediaStream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
                
                // WORKAROUND: Keep mic stream active/alive in Chromium/Android/Oculus Browser
                try {
                    const aud = new Audio();
                    aud.srcObject = this.mediaStream;
                    aud.muted = true;
                    aud.play().catch(e => console.warn('[VideoChat-Fresh] Workaround audio play failed:', e));
                    (window as any).foveaiWorkaroundAudio = aud;
                } catch (err) {
                    console.warn('[VideoChat-Fresh] Workaround audio setup failed:', err);
                }
            }
            this.mediaRecorder = new MediaRecorder(this.mediaStream);
            this.audioChunks = [];

            this.mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    this.audioChunks.push(event.data);
                }
            };

            this.mediaRecorder.onstop = async () => {
                const audioBlob = new Blob(this.audioChunks, { type: 'audio/webm' });
                await this.transcribeViaSoul(audioBlob);
                // Don't kill the cached mic stream — it's shared with XR Push-to-Talk
                const cachedStream = (window as any).foveaiCachedMicStream as MediaStream | null;
                if (this.mediaStream && this.mediaStream !== cachedStream) {
                    this.mediaStream.getTracks().forEach(t => t.stop());
                }
                this.mediaStream = null;
            };

            this.mediaRecorder.start();
            this.log('[MIC] Listening (MediaRecorder)...', '#39ff14');
        } catch (err) {
            this.log(`MediaRecorder STT failed: ${err}`, '#ff007f');
        }
    }

    private async transcribeViaSoul(audioBlob: Blob) {
        try {
            const base64data = await new Promise<string>((resolve, reject) => {
                const reader = new FileReader();
                reader.onloadend = () => {
                    const result = reader.result as string;
                    resolve(result.split(',')[1]);
                };
                reader.onerror = reject;
                reader.readAsDataURL(audioBlob);
            });

            const response = await fetch('/api/soul/stt', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    audio_base64: base64data,
                    format: 'audio/webm',
                    filename: 'recording.webm'
                })
            });
            if (response.ok) {
                const data = await response.json();
                const transcript = data.text || data.transcript || '';
                if (transcript) {
                    this.log(`[MIC] Heard: "${transcript}"`, 'var(--neon-blue)');
                    this.onVoiceTranscriptReceived(transcript);
                } else if (data.error) {
                    this.log(`STT Proxy Error: ${data.error}`, '#ff007f');
                } else {
                    this.log('STT: No speech detected', '#ffaa00');
                }
            } else {
                this.log(`STT endpoint returned ${response.status}`, '#ff007f');
            }
        } catch (err) {
            this.log(`STT transcription failed: ${err}`, '#ff007f');
        }
    }

    private _isSpeaking: boolean = false;
    private _speechQueue: Array<{ text: string; onEnd?: () => void; voice?: 'jen' | 'antigravity' }> = [];

    public get isSpeaking(): boolean {
        return this._isSpeaking;
    }

    private _speakAbort: AbortController | null = null;

    /** Cancel any in-progress TTS and reset speaking state */
    public cancelSpeech() {
        // Clear speech queue on cancellation
        this._speechQueue = [];

        // Abort in-flight TTS fetch requests
        if (this._speakAbort) {
            this._speakAbort.abort();
            this._speakAbort = null;
        }
        // Cancel browser SpeechSynthesis if active
        if (this.speechSynthesis) {
            this.speechSynthesis.cancel();
        }
        // Stop any audio playing through AuralAwareness (the AudioBuffer player)
        // This is critical — without it, old TTS audio keeps playing even after
        // the fetch is aborted, causing overlapping voices
        window.dispatchEvent(new CustomEvent('foveai_stop_sound'));
        this._isSpeaking = false;
    }

    // Timer for estimated onEnd fallback (safety net if foveai_tts_ended never fires)
    private _speakEndTimer: ReturnType<typeof setTimeout> | null = null;

    public isVoiceOutputEnabled: boolean = localStorage.getItem('foveai_voice_speech') !== 'false';

    public speak(text: string, onEnd?: () => void, voice?: 'jen' | 'antigravity') {
        if (!this.isVoiceOutputEnabled) {
            onEnd?.();
            return;
        }
        if (this._isSpeaking) {
            this.log(`[TTS] Queuing speech: "${text.substring(0, 30)}..."`, 'var(--neon-blue)');
            this._speechQueue.push({ text, onEnd, voice });
            return;
        }

        this._executeSpeak(text, onEnd, voice);
    }

    private _executeSpeak(text: string, onEnd?: () => void, voice?: 'jen' | 'antigravity') {
        // Stop any currently playing audio before starting new speech to prevent overlapping/double-voices
        window.dispatchEvent(new CustomEvent('foveai_stop_sound'));

        // Turn off VAD listening when Jen starts speaking to prevent self-triggering
        if ((window as any).foveaiDashboard?.isListening) {
            this.log('[TTS] Stopping active microphone VAD during speech output', 'var(--neon-blue)');
            (window as any).foveaiDashboard.stopListening();
        }

        this._isSpeaking = true;
        this._speakAbort = new AbortController();
        const abortSignal = this._speakAbort.signal;

        // Clear any previous end timer
        if (this._speakEndTimer) {
            clearTimeout(this._speakEndTimer);
            this._speakEndTimer = null;
        }

        // Clean up previous tts_ended listener
        if ((this as any)._ttsEndedHandler) {
            window.removeEventListener('foveai_tts_ended', (this as any)._ttsEndedHandler);
        }

        // Wrap onEnd to always reset speaking state + play next queued message
        const wrappedOnEnd = () => {
            if (this._speakEndTimer) { clearTimeout(this._speakEndTimer); this._speakEndTimer = null; }
            window.removeEventListener('foveai_tts_ended', (this as any)._ttsEndedHandler);
            if (onEnd) {
                try { onEnd(); } catch (_) {}
            }
            this._executeNextSpeech();
        };

        // Listen for actual audio completion from AuralAwareness
        (this as any)._ttsEndedHandler = () => { wrappedOnEnd(); };
        window.addEventListener('foveai_tts_ended', (this as any)._ttsEndedHandler as EventListener, { once: true });

        // Pre-process: convert bare soundboard tags like <hmm_thoughtful> to <flavour:hmm_thoughtful>
        // LLMs sometimes generate bare tags without the audio:/flavour: prefix
        let processedText = text;
        try {
            const knownTags = soundboardRegistry.getAllTags();
            for (const tag of knownTags) {
                const escaped = tag.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
                // Only convert bare <tag> if not already using a prefixed form
                const prefixedPattern = new RegExp(`<(?:audio|flavour|emotion|request):${escaped}>`);
                if (!prefixedPattern.test(processedText)) {
                    const barePattern = new RegExp(`<${escaped}>`, 'g');
                    if (barePattern.test(processedText)) {
                        this.log(`[SND] Bare tag converted: <${tag}> -> <flavour:${tag}>`, '#ffaa00');
                    }
                    processedText = processedText.replace(barePattern, `<flavour:${tag}>`);
                }
            }
        } catch (_) { /* keep original text on error */ }

        // Ensure audio pipeline is unlocked before playing soundboard sounds (Quest 3)
        try {
            const foveaiAudio = (window as any).foveaiAudio;
            if (foveaiAudio && foveaiAudio.unlockAudio) foveaiAudio.unlockAudio();
        } catch (_) {}

        // Parse bracket tokens from brain text before TTS
        const parsed = BracketParser.parse(processedText);

        // Fire soundboard events for audio brackets (instant, bypasses TTS)
        for (const token of parsed.tokens) {
            if (token.type === 'audio') {
                // Auto-promote unknown audio tags to generation requests (model may invent tags)
                if (!soundboardRegistry.has(token.tag)) {
                    this.log(`[SND→GEN] Unknown tag <audio:${token.tag}> — auto-generating via Stable Audio`, 'var(--neon-pink)');
                    soundboardRegistry.handleRequest(token.tag);
                } else {
                    this.log(`[SND] Soundboard: <audio:${token.tag}>`, 'var(--neon-blue)');
                    soundboardRegistry.play(token.tag);
                }
            }
            if (token.type === 'micro') {
                // Dispatch micro-gesture event for AvatarManager
                window.dispatchEvent(new CustomEvent('foveai_micro_gesture', {
                    detail: { gesture: token.tag, params: token.params }
                }));
            }
            if (token.type === 'emotion') {
                // Skip 'neutral' — it's a no-op (avatar is already neutral)
                if (token.tag === 'neutral') { /* skip */ }
                else {
                    // Dispatch BlendShape event so avatar face reflects the emotion
                    const emotionBlendShapes: Record<string, Record<string, number>> = {
                        happy:     { happy: 0.7, mouthSmile: 0.5 },
                        excited:   { happy: 0.8, surprised: 0.3 },
                        sad:       { sad: 0.6 },
                        angry:     { angry: 0.6 },
                        surprised: { surprised: 0.7, eyeWide: 0.5, mouthOpen: 0.3 },
                        fearful:   { surprised: 0.5, sad: 0.3 },
                        content:   { relaxed: 0.5, mouthSmile: 0.3 },
                        curious:   { thinking: 0.4, eyeSquint: 0.2 },
                        concerned: { sad: 0.3, thinking: 0.3 },
                    };
                    const shapes = emotionBlendShapes[token.tag] || {};
                    const duration = token.params.duration ? parseInt(token.params.duration) : 2000;
                    window.dispatchEvent(new CustomEvent('foveai_blendshape_trigger', {
                        detail: { tag: token.tag, blendShapes: shapes, duration }
                    }));
                }
            }
            if (token.type === 'flavour') {
                // Kokoro flavouring: play soundboard clip softly alongside TTS for emotional colouring
                this.log(`[FLV] Flavour: <flavour:${token.tag}>`, 'var(--neon-pink)');
                soundboardRegistry.playSoft(token.tag);
            }
            if (token.type === 'request') {
                const tagLower = token.tag.toLowerCase();
                if (tagLower.includes('dev_snapshot') || tagLower.includes('developer_snapshot')) {
                    this.log(`[SNAP] Developer requested viewport snapshot: <request:${token.tag}>`, 'var(--neon-blue)');
                    window.dispatchEvent(new CustomEvent('foveai_voice_snapshot', { detail: { text: 'dev' } }));
                } else if (tagLower.includes('webcam_snapshot') || tagLower.includes('webcam')) {
                    this.log(`[SNAP] Jen requested a webcam snapshot: <request:${token.tag}>`, 'var(--neon-blue)');
                    window.dispatchEvent(new CustomEvent('foveai_voice_snapshot', { detail: { text: 'webcam' } }));
                } else if (tagLower.includes('snapshot') || tagLower.includes('picture') || tagLower.includes('photo')) {
                    this.log(`[SNAP] Jen requested a viewpoint snapshot: <request:${token.tag}>`, 'var(--neon-blue)');
                    window.dispatchEvent(new CustomEvent('foveai_voice_snapshot', { detail: { text: 'avatar' } }));
                } else {
                    // Jen requests a new sound to be generated and added to her soundboard
                    this.log(`[GEN] Generate: <request:${token.tag}>`, 'var(--neon-pink)');
                    soundboardRegistry.handleRequest(token.tag);
                }
            }
            if (token.type === 'dev') {
                // Jen requests to deploy J-Aider to execute codebase modifications
                this.log(`[DEV] J-Aider requested: <dev:${token.tag}>`, 'var(--neon-blue)');
                window.dispatchEvent(new CustomEvent('foveai_aider_request', {
                    detail: { instruction: token.tag }
                }));
            }
        }

        // Determine speaker voice profile (defaulting to active persona in global state)
        const speakerVoice = voice || (((window as any).foveaiBrainState?.activePersonaId === 'coder' || (window as any).foveaiBrainState?.activePersonaId === 'antigravity') ? 'antigravity' : 'jen');

        // TTS chain: MOUTH (Kokoro :8004) first — it's the working endpoint.
        // Soul TTS proxy (/api/soul/tts) is tried as fallback if MOUTH fails.
        // Pass wrappedOnEnd to reset _isSpeaking when speech finishes, and
        // abortSignal to cancel in-flight fetch if new speech starts.
        this.speakWithMouthTTS(parsed.cleanText, wrappedOnEnd, parsed.primaryEmotion, abortSignal, speakerVoice);
    }

    private _executeNextSpeech() {
        if (this._speechQueue.length > 0) {
            const next = this._speechQueue.shift()!;
            this.log(`[TTS] Playing queued speech: "${next.text.substring(0, 30)}..."`, 'var(--neon-blue)');
            this._executeSpeak(next.text, next.onEnd, next.voice);
        } else {
            this._isSpeaking = false;
            // Restart VAD after all queued messages finish playing
            if ((window as any).foveaiDashboard && !(window as any).foveaiDashboard.isListening) {
                this.log('[TTS] All queued speech finished. Restarting VAD.', 'var(--neon-green)');
                (window as any).foveaiDashboard.startListening();
            }
        }
    }

    private async speakWithSoulTTS(text: string, onEnd?: () => void, emotion?: string, signal?: AbortSignal, voice?: 'jen' | 'antigravity') {
        // Soul TTS proxy (/api/soul/tts) — fallback when MOUTH endpoints are unreachable.
        // This endpoint may not be proxied in all deployments; MOUTH is preferred.
        try {
            if (signal?.aborted) return;
            const response = await fetch('/api/soul/tts', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text, style: emotion, emotion }),
                signal
            });

            if (signal?.aborted) return;

            if (response.ok) {
                const contentType = response.headers.get('content-type') || '';
                this.log(`Soul TTS: response content-type=${contentType}`, 'var(--neon-blue)');

                // If the response is JSON, it's an error/status message — NOT audio
                if (contentType.includes('application/json')) {
                    const jsonData = await response.json();
                    this.log(`Soul TTS: JSON response (not audio): ${JSON.stringify(jsonData).substring(0, 200)}`, '#ffaa00');
                    this.speakWithBrowserVoice(text, onEnd, emotion);
                    return;
                }

                if (signal?.aborted) return;
                const audioBlob = await response.blob();
                if (signal?.aborted) return;

                this.log(`Soul TTS: received ${audioBlob.size} bytes, type=${audioBlob.type}`, 'var(--neon-blue)');

                // Sanity check: real audio must be at least 44 bytes (WAV header)
                if (audioBlob.size < 44) {
                    this.log(`Soul TTS: payload too small (${audioBlob.size}B) -- not valid audio`, '#ff007f');
                    this.speakWithBrowserVoice(text, onEnd);
                    return;
                }

                const reader = new FileReader();
                reader.onload = () => {
                    if (signal?.aborted) return;
                    const base64 = (reader.result as string).split(',')[1];
                    if (base64) {
                        this.log(`Soul TTS: dispatching ${base64.length} chars to AuralAwareness`, 'var(--neon-blue)');
                        window.dispatchEvent(new CustomEvent('foveai_play_sound', { detail: { base64, voice: voice || 'jen' } }));
                    } else {
                        this.log('Soul TTS: base64 conversion returned empty', '#ff007f');
                    }
                    this.log('Speaking (Soul TTS)', '#39ff14');
                    // onEnd is handled by foveai_tts_ended event from AuralAwareness
                    // Safety net: if foveai_tts_ended never fires (e.g. decode error), fire after generous timeout
                    const wordCount = text.split(/\s+/).length;
                    const safetyMs = Math.max(5000, (wordCount / 100) * 60000) + 3000;
                    this._speakEndTimer = setTimeout(() => {
                        this.log('[TTS] Safety timeout — foveai_tts_ended never fired', '#ffaa00');
                        if (onEnd) onEnd();
                    }, safetyMs);
                };
                reader.readAsDataURL(audioBlob);
                return;
            } else {
                this.log(`Soul TTS: HTTP ${response.status} -- falling back to browser voice`, '#ffaa00');
            }
        } catch (err) {
            if (signal?.aborted) return;
            this.log(`Soul TTS fetch failed: ${err}`, '#ffaa00');
        }
        this.speakWithBrowserVoice(text, onEnd, emotion);
    }

    /**
     * Direct MOUTH service TTS fallback — bypasses Soul proxy.
     * Both endpoints route to Kokoro TTS on MOUTH (port 8004) via xr_app.py proxy.
     */
    private async speakWithMouthTTS(text: string, onEnd?: () => void, emotion?: string, signal?: AbortSignal, voice?: 'jen' | 'antigravity') {
        const endpoints = [
            '/api/mouth/tts',           // Primary — proxied to Kokoro on MOUTH :8004
            '/api/kokoro/tts',          // Alias — same upstream (Kokoro on MOUTH :8004)
        ];

        for (const endpoint of endpoints) {
            try {
                if (signal?.aborted) return;
                this.log(`Mouth TTS: trying ${endpoint}...`, 'var(--neon-blue)');
                const response = await fetch(endpoint, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ text, style: emotion, emotion }),
                    signal
                });

                if (signal?.aborted) return;

                if (!response.ok) {
                    this.log(`Mouth TTS: ${endpoint} returned HTTP ${response.status}`, '#ffaa00');
                    continue;
                }

                const contentType = response.headers.get('content-type') || '';
                if (contentType.includes('application/json')) {
                    const jsonData = await response.json();
                    this.log(`Mouth TTS: JSON response from ${endpoint}: ${JSON.stringify(jsonData).substring(0, 100)}`, '#ffaa00');
                    continue; // Try next endpoint
                }

                if (signal?.aborted) return;
                const audioBlob = await response.blob();
                if (signal?.aborted) return;

                if (audioBlob.size < 44) {
                    this.log(`Mouth TTS: payload too small from ${endpoint}`, '#ff007f');
                    continue;
                }

                this.log(`Mouth TTS: received ${audioBlob.size} bytes from ${endpoint}`, '#39ff14');
                const reader = new FileReader();
                reader.onload = () => {
                    if (signal?.aborted) return;
                    const base64 = (reader.result as string).split(',')[1];
                    if (base64) {
                        window.dispatchEvent(new CustomEvent('foveai_play_sound', { detail: { base64, voice: voice || 'jen' } }));
                        this.log('Speaking (Mouth TTS)', '#39ff14');
                        // onEnd is handled by foveai_tts_ended event from AuralAwareness
                        // Safety net: if foveai_tts_ended never fires, fire after generous timeout
                        const wordCount = text.split(/\s+/).length;
                        const safetyMs = Math.max(5000, (wordCount / 100) * 60000) + 3000;
                        this._speakEndTimer = setTimeout(() => {
                            this.log('[TTS] Safety timeout — foveai_tts_ended never fired', '#ffaa00');
                            if (onEnd) onEnd();
                        }, safetyMs);
                    }
                };
                reader.readAsDataURL(audioBlob);
                return; // Success — don't try more endpoints
            } catch (err) {
                if (signal?.aborted) return;
                this.log(`Mouth TTS: ${endpoint} failed: ${err}`, '#ffaa00');
            }
        }

        // All MOUTH endpoints failed — try Soul TTS proxy, then browser voice
        this.log('Mouth TTS: all endpoints failed -- trying Soul TTS proxy', '#ffaa00');
        this.speakWithSoulTTS(text, onEnd, emotion, signal, voice);
    }

    private speakWithBrowserVoice(text: string, onEnd?: () => void, emotion?: string) {
        // Aggressive SpeechSynthesis detection — Quest 3 Chrome may expose it
        // under different conditions or after a delay
        if (!this.speechSynthesis) {
            this.speechSynthesis = window.speechSynthesis
                || (window as any).speechSynthesis
                || (window as any).webkitSpeechSynthesis
                || null;
        }

        if (!this.speechSynthesis) {
            this.log('Browser SpeechSynthesis not available -- using tone fallback', '#ffaa00');
            this.speakWithToneFallback(text, onEnd, emotion);
            return;
        }

        // Quest 3 / Chrome: voices load asynchronously — getVoices() returns [] on first call.
        // We must wait for the 'voiceschanged' event before speaking.
        // GUARD: prevent double-speak from both voiceschanged event and safety timeout
        let hasSpoken = false;
        const trySpeak = () => {
            if (hasSpoken) return; // Prevent double-speak from voiceschanged + timeout
            hasSpoken = true;

            const voices = this.speechSynthesis!.getVoices();
            this.log(`Browser voice: ${voices.length} voices available, speaking: "${text.substring(0, 40)}..."`, 'var(--neon-blue)');

            // Emotional voice modulation for browser SpeechSynthesis
            const emotionMap: Record<string, { pitch: number; rate: number }> = {
                happy:      { pitch: 1.2, rate: 1.1 },
                excited:    { pitch: 1.3, rate: 1.15 },
                sad:        { pitch: 0.85, rate: 0.9 },
                angry:      { pitch: 1.1, rate: 1.2 },
                surprised:  { pitch: 1.25, rate: 1.1 },
                fearful:    { pitch: 1.15, rate: 1.15 },
                content:    { pitch: 1.0, rate: 0.95 },
                neutral:   { pitch: 1.0, rate: 1.0 },
            };
            const voiceStyle = emotionMap[emotion || ''] || emotionMap.neutral;
            this.log(`Browser voice: emotion=${emotion || 'neutral'}, pitch=${voiceStyle.pitch}, rate=${voiceStyle.rate}`, 'var(--neon-blue)');

            const utterance = new SpeechSynthesisUtterance(text);
            utterance.lang = 'en-US';
            utterance.rate = voiceStyle.rate;
            utterance.pitch = voiceStyle.pitch;

            // Prefer English voice if available
            if (voices.length > 0) {
                const preferred = voices.find(v => v.lang.startsWith('en') && v.name.toLowerCase().includes('female'))
                    || voices.find(v => v.lang.startsWith('en') && !v.localService)
                    || voices.find(v => v.lang.startsWith('en'))
                    || voices[0];
                if (preferred) {
                    utterance.voice = preferred;
                    this.log(`Browser voice: using "${preferred.name}" (${preferred.lang})`, 'var(--neon-blue)');
                }
            }

            utterance.onend = () => {
                this.log('Finished speaking (browser voice)', '#39ff14');
                if (onEnd) onEnd();
            };

            utterance.onerror = (event: SpeechSynthesisErrorEvent) => {
                // "interrupted" and "canceled" are NOT real failures — they occur when
                // cancel() is called before a new utterance (Chrome bug). Don't fall back to tone.
                if (event.error === 'interrupted' || event.error === 'canceled') {
                    this.log(`Speech ${event.error} (normal — utterance replaced)`, '#ffaa00');
                    return;
                }
                this.log(`Speech error: ${event.error} -- falling back to tone`, '#ff007f');
                this.speakWithToneFallback(text, onEnd, emotion);
            };

            // Chrome bug: speechSynthesis can freeze if not cancelled before new utterance
            this.speechSynthesis!.cancel();
            this.speechSynthesis!.speak(utterance);
        };

        const voices = this.speechSynthesis.getVoices();
        if (voices.length > 0) {
            // Voices already loaded — speak immediately
            trySpeak();
        } else {
            // Wait for voices to load (Quest 3 / Chrome async loading)
            this.log('Browser voice: waiting for voices to load...', '#ffaa00');
            const onVoicesReady = () => {
                this.speechSynthesis!.removeEventListener('voiceschanged', onVoicesReady);
                trySpeak();
            };
            this.speechSynthesis.addEventListener('voiceschanged', onVoicesReady);
            // Safety timeout: try speaking anyway after 2s even if no voices event fires
            setTimeout(() => {
                this.speechSynthesis!.removeEventListener('voiceschanged', onVoicesReady);
                if (hasSpoken) return; // Already spoke via voiceschanged — don't double-speak
                const v = this.speechSynthesis!.getVoices();
                if (v.length === 0) {
                    this.log('Browser voice: no voices loaded after 2s -- using tone fallback', '#ff007f');
                    this.speakWithToneFallback(text, onEnd, emotion);
                } else {
                    trySpeak();
                }
            }, 2000);
        }
    }

    /**
     * Absolute last-resort fallback: generates an audible tone pattern
     * using Web Audio API so the user at least hears *something* from Jen.
     * The tone pattern varies by emotion to convey intent.
     */
    private speakWithToneFallback(text: string, onEnd?: () => void, emotion?: string) {
        try {
            const ctx = new (window.AudioContext || (window as any).webkitAudioContext)();
            if (ctx.state === 'suspended') ctx.resume();

            // Emotion → tone pattern mapping
            const patterns: Record<string, { freq: number; type: OscillatorType; notes: number[]; gap: number }> = {
                happy:     { freq: 520, type: 'triangle', notes: [0, 4, 7, 12], gap: 120 },
                excited:   { freq: 600, type: 'square',   notes: [0, 4, 7, 12, 16], gap: 80 },
                sad:       { freq: 300, type: 'sine',     notes: [0, -1, -3], gap: 200 },
                surprised: { freq: 480, type: 'sawtooth', notes: [0, 7, 0, 7], gap: 100 },
                neutral:   { freq: 400, type: 'sine',     notes: [0, 3, 7], gap: 150 },
            };
            const pat = patterns[emotion || ''] || patterns.neutral;
            const baseFreq = pat.freq;
            // Scale note count by text length — longer text = more notes (capped)
            const noteCount = Math.min(pat.notes.length, Math.max(3, Math.ceil(text.split(/\s+/).length / 3)));

            let noteIdx = 0;
            const playNextNote = () => {
                if (noteIdx >= noteCount) {
                    if (onEnd) onEnd();
                    return;
                }
                const semitone = pat.notes[noteIdx % pat.notes.length];
                const freq = baseFreq * Math.pow(2, semitone / 12);
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();
                osc.type = pat.type;
                osc.frequency.setValueAtTime(freq, ctx.currentTime);
                gain.gain.setValueAtTime(0.12, ctx.currentTime);
                gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + pat.gap / 1000);
                osc.connect(gain);
                gain.connect(ctx.destination);
                osc.start(ctx.currentTime);
                osc.stop(ctx.currentTime + pat.gap / 1000);
                noteIdx++;
                setTimeout(playNextNote, pat.gap);
            };

            this.log(`Tone fallback: playing ${noteCount} notes (${emotion || 'neutral'})`, '#ffaa00');
            playNextNote();
        } catch (err) {
            this.log(`Tone fallback failed: ${err}`, '#ff007f');
            if (onEnd) onEnd();
        }
    }

    private onVoiceTranscriptReceived(transcript: string) {
        this.log(`Voice received: ${transcript}`, '#00f3ff');
        
        // Intercept voice snapshot commands ("Lumax snap", "take a picture", etc.)
        const lower = transcript.toLowerCase();
        if (lower.includes('snap') || lower.includes('take a picture')) {
            this.log('[VOICE] Voice snapshot command matched. Triggering spatial capture...', 'var(--neon-green)');
            window.dispatchEvent(new CustomEvent('foveai_voice_snapshot', { detail: { text: transcript } }));
            return;
        }

        // Route through Dashboard's cloud-first message handler instead of LocalBrain
        const dashboard = (window as any).foveaiDashboard;
        if (dashboard && typeof dashboard.sendMessage === 'function') {
            dashboard.sendMessage(transcript);
        } else {
            this.log('Voice routing: Dashboard not available, message dropped', '#ff007f');
        }
    }

    // ========== AVATAR EXIT ANIMATION (CRAWLING FROM SCREEN) ==========

    public triggerAvatarExit() {
        this.log('Triggering avatar exit animation...', '#ffaa00');

        // Fade out video chat
        this.container.style.opacity = '0';
        setTimeout(() => {
            this.container.style.display = 'none';
            this.isActive = false;

            // Trigger avatar crawl animation
            if ((window as any).avatarManager) {
                (window as any).avatarManager.playCategory('crawl', true, 0.5);
                this.log('Avatar animation started: crawl', '#39ff14');
            }
        }, 500);
    }

    // ========== GETTERS FOR EXTERNAL ACCESS ==========

    public getVideoChatElement(): HTMLElement {
        return this.container;
    }

    public hasVocalInputSupport(): boolean {
        return this.speechRecognition !== null;
    }
}
