/**
 * Turn a getUserMedia failure into an actionable sentence.
 * The two that account for nearly every report: an insecure origin (plain
 * http on a LAN address — the browser blocks the mic outright) and a denied
 * permission. Both used to fail silently.
 */
function describeMicFailure(err: unknown): string {
  const name = (err as { name?: string })?.name || 'Error';
  const msg = String((err as { message?: string })?.message || err);
  if (!window.isSecureContext) {
    return `this page is not a secure origin (${location.protocol}//${location.host}). ` +
      `Browsers block the microphone here. Use https://foveai.xarel.net or http://localhost.`;
  }
  switch (name) {
    case 'NotAllowedError':
    case 'SecurityError':
      return 'permission denied — allow the microphone for this site in the browser, then retry.';
    case 'NotFoundError':
    case 'OverconstrainedError':
      return 'no microphone found on this device. (A remote-desktop session often exposes none.)';
    case 'NotReadableError':
      return 'the microphone is busy in another application, or the session exposes no capture device.';
    default:
      return `${name}: ${msg}`;
  }
}

export class AuralAwareness {
  private mediaRecorder: MediaRecorder | null = null;
  private audioChunks: Blob[] = [];
  private isRecording: boolean = false;
  private mediaStream: MediaStream | null = null;
  private currentPlayId: number = 0;
  private selectedDeviceId: string = '';

  // Real-time analysis
  private audioContext: AudioContext | null = null;
  private analyser: AnalyserNode | null = null;
  private dataArray: Uint8Array | null = null;
  private source: MediaStreamAudioSourceNode | null = null;

  // Active audio tracking — needed to stop TTS audio when new speech starts
  private activeBufferSources: AudioBufferSourceNode[] = [];
  private activeGainNodes: GainNode[] = [];
  private activeAudioElements: HTMLAudioElement[] = [];

  constructor() {
      // Listen for incoming sound commands (from SoundForge or TTS)
      window.addEventListener('foveai_play_sound', ((e: CustomEvent) => {
          const detail = e.detail;
          if (typeof detail === 'string') {
              this.playBase64Audio(detail, 'jen');
          } else {
              this.playBase64Audio(detail.base64, detail.voice || 'jen');
          }
      }) as EventListener);

      // Stop all active audio when requested (e.g. new TTS cancelling old one)
      window.addEventListener('foveai_stop_sound', () => {
          this.stopAllAudio();
      });
  }

  /** Stop all currently playing TTS audio (buffer sources + HTML5 fallback) */
  public stopAllAudio() {
      // Cancel any in-flight playbacks
      this.currentPlayId++;

      // Stop Web Audio API buffer sources
      for (const src of this.activeBufferSources) {
          try { src.stop(0); } catch (_) { /* already stopped */ }
      }
      // Silence gain nodes immediately (prevents any residual audio)
      for (const gain of this.activeGainNodes) {
          try { gain.gain.setValueAtTime(0, this.audioContext?.currentTime ?? 0); } catch (_) {}
      }
      this.activeBufferSources = [];
      this.activeGainNodes = [];

      // Stop HTML5 audio elements
      for (const el of this.activeAudioElements) {
          try { el.pause(); el.currentTime = 0; } catch (_) {}
      }
      this.activeAudioElements = [];

      console.log('[AuralAwareness] All TTS audio stopped');
  }

  private getOrCreateAudioContext(): AudioContext {
      const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext;
      let ctx = (window as any).foveaiAudioContext;
      if (!ctx || ctx.state === 'closed') {
          ctx = new AudioContextClass();
          (window as any).foveaiAudioContext = ctx;
      }
      this.audioContext = ctx;
      return ctx;
  }

  /**
   * Unlock the AudioContext during a user gesture (e.g. clicking "Enter XR").
   * Quest 3 / Chrome requires this — AudioContext created outside a gesture
   * stays permanently suspended and produces no sound.
   */
  public async unlockAudio() {
      try {
          const ctx = this.getOrCreateAudioContext();
          if (ctx.state === 'suspended') {
              await ctx.resume();
              console.log('[AuralAwareness] AudioContext resumed after user gesture');
          }
          // Play a silent buffer to fully unlock the audio pipeline on Quest 3
          const buffer = ctx.createBuffer(1, 1, ctx.sampleRate);
          const source = ctx.createBufferSource();
          source.buffer = buffer;
          source.connect(ctx.destination);
          source.start(0);
          console.log('[AuralAwareness] Audio pipeline unlocked for XR');
      } catch (err) {
          console.error('[AuralAwareness] Audio unlock failed:', err);
      }
  }

  public async playBase64Audio(base64Data: string, voice: string = 'jen') {
      const playId = ++this.currentPlayId;
      try {
          const ctx = this.getOrCreateAudioContext();

          // Diagnostic: log AudioContext state (critical for Quest 3 debugging)
          console.log(`[AuralAwareness] AudioContext state: ${ctx.state}, voice: ${voice}`);

          if (ctx.state === 'suspended') {
              try {
                  await ctx.resume();
              } catch (resumeErr) {
                  if (playId !== this.currentPlayId) return;
                  console.warn('[AuralAwareness] AudioContext resume failed, falling back to HTML5 audio');
                  this.playWithAudioElement(base64Data, voice);
                  return;
              }
          }

          if (playId !== this.currentPlayId) return;

          // If still suspended after resume attempt, fall back
          if (ctx.state === 'suspended') {
              console.warn('[AuralAwareness] AudioContext still suspended, falling back to HTML5 audio');
              this.playWithAudioElement(base64Data, voice);
              return;
          }

          // Handle data URIs vs raw base64
          let base64 = base64Data;
          if (base64.startsWith('data:audio')) {
              base64 = base64.split(',')[1];
          }

          const binaryString = window.atob(base64);
          const len = binaryString.length;
          const bytes = new Uint8Array(len);
          for (let i = 0; i < len; i++) {
              bytes[i] = binaryString.charCodeAt(i);
          }

          const audioBuffer = await ctx.decodeAudioData(bytes.buffer);
          if (playId !== this.currentPlayId) {
              console.log('[AuralAwareness] playBase64Audio aborted: newer play initiated during decoding');
              return;
          }
          const source = ctx.createBufferSource();
          source.buffer = audioBuffer;

          // Add a GainNode at full volume to ensure audibility on Quest 3
          const gainNode = ctx.createGain();
          gainNode.gain.value = 1.0;

          // --- ADJUSTED REVERB: Ethereal developer voice vs clear assistant voice ---
          const reverbGain = ctx.createGain();
          // Antigravity (dev): 35% wet reverb, Jen: 15% wet reverb
          reverbGain.gain.value = voice === 'antigravity' ? 0.35 : 0.15;
          const dryGain = ctx.createGain();
          // Antigravity: 0.65 dry, Jen: 0.85 dry (clearer voice)
          dryGain.gain.value = voice === 'antigravity' ? 0.65 : 0.85;

          // Generate synthetic impulse response for a large, dark space
          const reverbLength = ctx.sampleRate * 2.5; // 2.5s reverb tail
          const impulseBuffer = ctx.createBuffer(2, reverbLength, ctx.sampleRate);
          for (let channel = 0; channel < 2; channel++) {
              const channelData = impulseBuffer.getChannelData(channel);
              for (let i = 0; i < reverbLength; i++) {
                  // Exponential decay with noise — sounds like a vast interior space
                  const decay = Math.pow(1 - i / reverbLength, 2.2);
                  channelData[i] = (Math.random() * 2 - 1) * decay * 0.4;
              }
          }
          const convolver = ctx.createConvolver();
          convolver.buffer = impulseBuffer;

          // Low-pass filter on reverb to make it sound distant (highs absorbed by distance)
          const reverbFilter = ctx.createBiquadFilter();
          reverbFilter.type = 'lowpass';
          reverbFilter.frequency.value = 2800;
          reverbFilter.Q.value = 0.5;

          // Pre-delay: 30ms gap before reverb starts (separates direct sound from reflections)
          const preDelay = ctx.createDelay(0.1);
          preDelay.delayTime.value = 0.03;

          // Routing: source -> dry path + wet path (pre-delay -> convolver -> LPF -> reverbGain)
          source.connect(dryGain);
          dryGain.connect(gainNode);

          source.connect(preDelay);
          preDelay.connect(convolver);
          convolver.connect(reverbFilter);
          reverbFilter.connect(reverbGain);
          reverbGain.connect(gainNode);

          gainNode.connect(ctx.destination);
          
          // Lip sync during PLAYBACK: the analyser used to be created only by
          // the mic path, so TTS playback published no energy at all and the
          // avatar never moved its mouth. Create it on demand here.
          const lipAnalyser = this.ensureAnalyser();
          if (lipAnalyser) {
              source.connect(lipAnalyser);
              this.startEnergyPublisher();
          }

          // Track source and gain so they can be stopped when new speech starts
          this.activeBufferSources.push(source);
          this.activeGainNodes.push(gainNode);
          source.onended = () => {
              const si = this.activeBufferSources.indexOf(source);
              if (si >= 0) this.activeBufferSources.splice(si, 1);
              const gi = this.activeGainNodes.indexOf(gainNode);
              if (gi >= 0) this.activeGainNodes.splice(gi, 1);
              // Wait for the 2.5s reverb tail to decay (e.g. 800ms) before notifying that speech ended
              // This prevents VAD from self-triggering on the echo tail.
              setTimeout(() => {
                  if (playId === this.currentPlayId) {
                      window.dispatchEvent(new CustomEvent('foveai_tts_ended'));
                  }
              }, 800);
          };

          source.start(0);
          console.log('[AuralAwareness] Playing generated audio via Web Audio API');
      } catch (err) {
          if (playId !== this.currentPlayId) return;
          console.error('[AuralAwareness] Web Audio playback failed, falling back to HTML5:', err);
          this.playWithAudioElement(base64Data, voice);
      }
  }

  /**
   * Fallback when playBase64Audio fails — decodes base64 as AudioBuffer
   * and plays through the same reverb chain. Never plays dry.
   * If AudioContext is completely unavailable, falls back to HTML5 <audio>.
   */
  private playWithAudioElement(base64Data: string, voice: string = 'jen') {
      const playId = ++this.currentPlayId;
      try {
          // PREFER: decode as AudioBuffer and play through reverb chain
          const ctx = this.getOrCreateAudioContext();
          if (ctx.state === 'suspended') {
              ctx.resume().catch(() => {});
          }
          if (playId !== this.currentPlayId) return;
          if (ctx.state === 'running') {
              let base64 = base64Data;
              if (base64.startsWith('data:audio')) {
                  base64 = base64.split(',')[1];
              }
              const binaryString = window.atob(base64);
              const bytes = new Uint8Array(binaryString.length);
              for (let i = 0; i < binaryString.length; i++) {
                  bytes[i] = binaryString.charCodeAt(i);
              }
              ctx.decodeAudioData(bytes.buffer, (audioBuffer) => {
                  if (playId !== this.currentPlayId) return;
                  // Same dreamy reverb chain as playBase64Audio
                  const source = ctx.createBufferSource();
                  source.buffer = audioBuffer;
                  const gainNode = ctx.createGain();
                  gainNode.gain.value = 1.0;

                  const reverbGain = ctx.createGain();
                  reverbGain.gain.value = voice === 'antigravity' ? 0.35 : 0.15;
                  const dryGain = ctx.createGain();
                  dryGain.gain.value = voice === 'antigravity' ? 0.65 : 0.85;

                  const reverbLength = ctx.sampleRate * 2.5;
                  const impulseBuffer = ctx.createBuffer(2, reverbLength, ctx.sampleRate);
                  for (let channel = 0; channel < 2; channel++) {
                      const channelData = impulseBuffer.getChannelData(channel);
                      for (let i = 0; i < reverbLength; i++) {
                          const decay = Math.pow(1 - i / reverbLength, 2.2);
                          channelData[i] = (Math.random() * 2 - 1) * decay * 0.4;
                      }
                  }
                  const convolver = ctx.createConvolver();
                  convolver.buffer = impulseBuffer;
                  const reverbFilter = ctx.createBiquadFilter();
                  reverbFilter.type = 'lowpass';
                  reverbFilter.frequency.value = 2800;
                  reverbFilter.Q.value = 0.5;
                  const preDelay = ctx.createDelay(0.1);
                  preDelay.delayTime.value = 0.03;

                  source.connect(dryGain);
                  dryGain.connect(gainNode);
                  source.connect(preDelay);
                  preDelay.connect(convolver);
                  convolver.connect(reverbFilter);
                  reverbFilter.connect(reverbGain);
                  reverbGain.connect(gainNode);
                  gainNode.connect(ctx.destination);
                  if (this.analyser) source.connect(this.analyser);

                  this.activeBufferSources.push(source);
                  this.activeGainNodes.push(gainNode);
                  source.onended = () => {
                      const si = this.activeBufferSources.indexOf(source);
                      if (si >= 0) this.activeBufferSources.splice(si, 1);
                      const gi = this.activeGainNodes.indexOf(gainNode);
                      if (gi >= 0) this.activeGainNodes.splice(gi, 1);
                      // Wait for the 2.5s reverb tail to decay (e.g. 800ms) before notifying that speech ended
                      setTimeout(() => {
                          if (playId === this.currentPlayId) {
                              window.dispatchEvent(new CustomEvent('foveai_tts_ended'));
                          }
                      }, 800);
                  };
                  source.start(0);
                  console.log('[AuralAwareness] Fallback: decoded as AudioBuffer with reverb');
              }, (decodeErr) => {
                  if (playId !== this.currentPlayId) return;
                  // decodeAudioData failed — last resort: HTML5 <audio> (dry but at least audible)
                  console.warn('[AuralAwareness] decodeAudioData failed, using raw HTML5:', decodeErr);
                  this._playRawHtml5(base64Data, playId);
              });
              return;
          }
          // AudioContext not running — last resort HTML5
          this._playRawHtml5(base64Data, playId);
      } catch (err) {
          if (playId !== this.currentPlayId) return;
          console.error('[AuralAwareness] Fallback playback error:', err);
          this._playRawHtml5(base64Data, playId);
      }
  }

  /** Absolute last resort: raw HTML5 <audio> element — no reverb but at least audible */
  private _playRawHtml5(base64Data: string, playId?: number) {
      if (playId !== undefined && playId !== this.currentPlayId) return;
      try {
          let dataUri = base64Data;
          if (!dataUri.startsWith('data:audio')) {
              dataUri = `data:audio/wav;base64,${base64Data}`;
          }
          const audioEl = new Audio(dataUri);
          audioEl.volume = 0.5;  // Lower volume since no reverb
          this.activeAudioElements.push(audioEl);
          audioEl.onended = () => {
              const idx = this.activeAudioElements.indexOf(audioEl);
              if (idx >= 0) this.activeAudioElements.splice(idx, 1);
              window.dispatchEvent(new CustomEvent('foveai_tts_ended'));
          };
          audioEl.play().catch(e => {
              console.error('[AuralAwareness] Raw HTML5 also failed:', e);
              const idx = this.activeAudioElements.indexOf(audioEl);
              if (idx >= 0) this.activeAudioElements.splice(idx, 1);
              window.dispatchEvent(new CustomEvent('foveai_tts_ended'));
          });
      } catch (err) {
          console.error('[AuralAwareness] Raw HTML5 error:', err);
      }
  }

  public async startRecording() {
    if (this.isRecording) return;

    try {
      const constraints: MediaTrackConstraints = {
        echoCancellation: true, noiseSuppression: true, autoGainControl: true,
      };
      if (this.selectedDeviceId) constraints.deviceId = { exact: this.selectedDeviceId };
      const stream = await navigator.mediaDevices.getUserMedia({ audio: constraints });
      console.log(`[AuralAwareness] capturing from: ${this.getActiveInputLabel()}`);
      
      this.mediaStream = stream;
      
      // Setup Analyser
      this.getOrCreateAudioContext();
      this.analyser = this.ensureAnalyser()!;
      this.analyser.fftSize = 256;
      this.source = this.audioContext!.createMediaStreamSource(stream);
      this.source.connect(this.analyser);
      this.dataArray = new Uint8Array(this.analyser.frequencyBinCount);

      this.mediaRecorder = new MediaRecorder(stream);
      this.audioChunks = [];

      this.mediaRecorder.ondataavailable = (event) => {
        this.audioChunks.push(event.data);
      };

      this.mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(this.audioChunks, { type: 'audio/wav' });
        const reader = new FileReader();
        reader.readAsDataURL(audioBlob);
        reader.onloadend = () => {
          const base64Audio = (reader.result as string).split(',')[1];
          // Send to SoulBridge
          this.dispatchAudio(base64Audio);
        };
      };

      this.mediaRecorder.start();
      this.isRecording = true;
      console.log('[AuralAwareness] Recording & Analysis started');
    } catch (err) {
      // A silent catch here is why "the mic never works" had no explanation for
      // years. Name the actual reason and surface it to the UI.
      const reason = describeMicFailure(err);
      console.error(`[AuralAwareness] Microphone unavailable — ${reason}`);
      window.dispatchEvent(new CustomEvent('foveai_mic_failed', { detail: { reason } }));
    }
  }

  /** Input devices the browser can actually see. Labels are empty until
   *  permission is granted, so callers should enumerate again after capture. */
  public async listInputs(): Promise<MediaDeviceInfo[]> {
    if (!navigator.mediaDevices?.enumerateDevices) return [];
    const devs = await navigator.mediaDevices.enumerateDevices();
    return devs.filter((d) => d.kind === 'audioinput');
  }

  /** The mic currently in use — the label is what makes "it listens to the
   *  wrong device" visible instead of a mystery. */
  public getActiveInputLabel(): string {
    return this.mediaStream?.getAudioTracks()[0]?.label || '(not capturing)';
  }

  /** Remember an explicitly chosen input and restart capture on it. */
  public async selectInput(deviceId: string): Promise<string> {
    this.selectedDeviceId = deviceId;
    const wasRecording = this.isRecording;
    this.cleanupCapture();
    if (wasRecording) await this.startRecording();
    return this.getActiveInputLabel();
  }

  public getChosenDeviceId(): string { return this.selectedDeviceId || ''; }

  /** Release the capture graph so switching devices cannot stack live nodes. */
  private cleanupCapture(): void {
    this.mediaStream?.getTracks().forEach((t) => t.stop());
    this.mediaStream = null;
    try { this.source?.disconnect(); } catch { /* already detached */ }
    this.source = null;
    this.analyser = null;
    this.isRecording = false;
  }

  public getContextState(): string { return this.audioContext?.state || 'none'; }

  /** Smoothed 0..1 mic level for a live meter. */
  public getInputLevel(): number {
    if (!this.analyser) return 0;
    return this.getVolume();
  }

  public getVolume(): number {
    if (!this.analyser || !this.dataArray) return 0;
    this.analyser.getByteFrequencyData(this.dataArray as any);
    
    let sum = 0;
    for (let i = 0; i < this.dataArray.length; i++) {
        sum += this.dataArray[i];
    }
    const average = sum / this.dataArray.length;
    return average / 128.0; // Normalized 0.0 - 1.0 (roughly)
  }

  public stopRecording() {
    if (!this.isRecording || !this.mediaRecorder) return;
    this.mediaRecorder.stop();
    this.isRecording = false;
    
    if (this.mediaStream) {
        try { this.mediaStream.getTracks().forEach(t => t.stop()); } catch (_) {}
        this.mediaStream = null;
    }
    if (this.source) {
        try { this.source.disconnect(); } catch (_) {}
        this.source = null;
    }
    if (this.analyser) {
        try { this.analyser.disconnect(); } catch (_) {}
        this.analyser = null;
    }
    this.audioContext = null;
    console.log('[AuralAwareness] Recording & Analysis stopped');
  }

  private dispatchAudio(base64: string) {
    window.dispatchEvent(new CustomEvent('foveai_audio_input', { detail: base64 }));
  }

  /** Returns the shared analyser, creating it on first use. */
  private ensureAnalyser(): AnalyserNode | null {
    if (this.analyser) return this.analyser;
    try {
      this.getOrCreateAudioContext();
      if (!this.audioContext) return null;
      this.analyser = this.audioContext.createAnalyser();
      this.analyser.fftSize = 256;
      this.dataArray = new Uint8Array(this.analyser.frequencyBinCount);
      return this.analyser;
    } catch (e) {
      console.warn('[Aural] analyser unavailable:', e);
      return null;
    }
  }

  /** Publishes playback/mic amplitude as 'foveai_tts_energy' events (~30fps)
      — feeds useLipsync for the talking still-image frames. */
  public startEnergyPublisher() {
      if ((this as any)._energyRaf) return;
      const loop = () => {
          (this as any)._energyRaf = requestAnimationFrame(loop);
          if (!this.analyser || !this.dataArray) return;
          this.analyser.getByteFrequencyData(this.dataArray as any);
          let sum = 0;
          for (const v of this.dataArray) sum += v;
          const energy = Math.min(1, sum / (this.dataArray.length * 140));
          window.dispatchEvent(new CustomEvent('foveai_tts_energy', { detail: { energy } }));
      };
      (this as any)._energyRaf = requestAnimationFrame(loop);
  }
}

/** One shared instance: the hook, the mic diagnostics and the recogniser
 *  must all read the same capture graph, or the meter lies. */
export const auralAwareness = new AuralAwareness();
