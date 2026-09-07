"""
Generate default soundboard WAV files for FoveAI.
Creates rich, layered emotional audio clips using advanced FM synthesis,
formant filtering, harmonic stacking, and reverb.

Output: frontend/XR_Vessel/public/soundboard/*.wav
"""
import wave
import struct
import math
import os
import random

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          'Frontend', 'XR_Vessel', 'public', 'soundboard')

SAMPLE_RATE = 44100

def generate_wav(filename, samples):
    """Write a list of float samples (-1.0 to 1.0) to a 16-bit WAV file."""
    filepath = os.path.join(OUTPUT_DIR, filename)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with wave.open(filepath, 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        for s in samples:
            clamped = max(-1.0, min(1.0, s))
            wf.writeframes(struct.pack('<h', int(clamped * 32767)))

def envelope(n, attack=0.01, decay=0.05, sustain_level=0.7, release=0.1):
    """ADSR envelope over n samples."""
    env = []
    a = int(SAMPLE_RATE * attack)
    d = int(SAMPLE_RATE * decay)
    s = n - a - d - int(SAMPLE_RATE * release)
    r = int(SAMPLE_RATE * release)
    for i in range(a):
        env.append(i / max(a, 1))
    for i in range(d):
        env.append(1.0 - (1.0 - sustain_level) * (i / max(d, 1)))
    for i in range(max(0, s)):
        env.append(sustain_level)
    for i in range(r):
        env.append(sustain_level * (1.0 - i / max(r, 1)))
    while len(env) < n:
        env.append(0)
    return env[:n]

def reverb(samples, decay=0.3, delays_ms=(37, 53, 79, 113, 157)):
    """Simple multi-tap echo reverb for spatial depth."""
    result = list(samples)
    for delay_ms in delays_ms:
        delay_samples = int(SAMPLE_RATE * delay_ms / 1000)
        amplitude = decay * (0.7 ** (delays_ms.index(delay_ms) + 1))
        for i in range(delay_samples, len(samples)):
            if i - delay_samples >= 0:
                result[i] += amplitude * samples[i - delay_samples]
    # Normalize
    peak = max(abs(s) for s in result) if result else 1.0
    if peak > 0.95:
        result = [s / peak * 0.9 for s in result]
    return result

def smooth_noise(duration_sec, amplitude=0.3, cutoff_freq=800):
    """Low-pass filtered noise (simulated via overlapping random walks)."""
    n = int(SAMPLE_RATE * duration_sec)
    raw = [random.random() * 2 - 1 for _ in range(n)]
    # Simple moving-average low-pass filter
    window = max(1, int(SAMPLE_RATE / cutoff_freq))
    filtered = []
    for i in range(n):
        start = max(0, i - window // 2)
        end = min(n, i + window // 2)
        filtered.append(sum(raw[start:end]) / (end - start))
    peak = max(abs(s) for s in filtered) if filtered else 1.0
    return [amplitude * s / peak for s in filtered]

def fm_synth(freq, duration_sec, mod_ratio=2.0, mod_depth=50, amplitude=0.6, attack=0.01, release=0.1):
    """FM synthesis — creates rich, dynamic tones."""
    n = int(SAMPLE_RATE * duration_sec)
    env = envelope(n, attack=attack, release=release, sustain_level=0.8)
    samples = []
    for i in range(n):
        t = i / SAMPLE_RATE
        modulator = math.sin(2 * math.pi * freq * mod_ratio * t) * mod_depth
        carrier = math.sin(2 * math.pi * (freq + modulator) * t)
        samples.append(amplitude * env[i] * carrier)
    return samples

def formant_voice(f0, duration_sec, formants, amplitude=0.5, attack=0.02, release=0.08):
    """Generate a vocal-like sound using formant synthesis.
    formants: list of (freq, bandwidth, amp) tuples."""
    n = int(SAMPLE_RATE * duration_sec)
    env = envelope(n, attack=attack, release=release, sustain_level=0.7)
    samples = []
    for i in range(n):
        t = i / SAMPLE_RATE
        # Glottal pulse: sawtooth-ish with some harmonics
        glottal = 0
        for h in range(1, 8):
            glottal += (1.0 / h) * math.sin(2 * math.pi * f0 * h * t)
        glottal *= 0.3
        # Apply formant resonances
        voiced = 0
        for f_freq, f_bw, f_amp in formants:
            # Resonance filter approximation
            resonance = f_amp * math.exp(-((f_freq - f_freq) ** 2) / (2 * (f_bw / 2) ** 2))
            # Filter the glottal source through formant
            formant_signal = resonance * math.sin(2 * math.pi * f_freq * t)
            voiced += formant_signal
        voiced += glottal * 0.3
        samples.append(amplitude * env[i] * (voiced + glottal * 0.2))
    return samples

# ===================== SOUND DEFINITIONS =====================

def gasp_subtle():
    """Quick inward gasp — shaped breath with formant coloring and reverb."""
    n = int(SAMPLE_RATE * 0.45)
    samples = []
    for i in range(n):
        t = i / SAMPLE_RATE
        # Sharp attack, quick exponential decay
        if t < 0.015:
            env = t / 0.015
        elif t < 0.08:
            env = 1.0 - 0.6 * (t - 0.015) / 0.065
        elif t < 0.25:
            env = 0.4 * math.exp(-(t - 0.08) * 8)
        else:
            env = 0.05 * math.exp(-(t - 0.25) * 15)
        # Layered: high breath + formant resonance
        breath = 0.35 * (random.random() * 2 - 1) * env
        formant1 = 0.25 * env * math.sin(2 * math.pi * 800 * t)
        formant2 = 0.15 * env * math.sin(2 * math.pi * 1400 * t)
        # Inhale pitch drop
        pitch_drop = 0.1 * env * math.sin(2 * math.pi * (500 - 200 * t) * t)
        samples.append(breath + formant1 + formant2 + pitch_drop)
    return reverb(samples, decay=0.2, delays_ms=(23, 47, 71))

def laugh_soft():
    """Soft chuckle — warm vocal bursts with FM color and room reverb."""
    samples = []
    # Three bursts: ha-ha-ha with decreasing amplitude
    burst_times = [0.0, 0.18, 0.33]
    burst_amps = [0.6, 0.5, 0.35]
    total_dur = 0.65
    n = int(SAMPLE_RATE * total_dur)
    for i in range(n):
        t = i / SAMPLE_RATE
        val = 0
        for bt, ba in zip(burst_times, burst_amps):
            dt = t - bt
            if 0 < dt < 0.12:
                # Each burst: quick attack, exponential decay
                env = min(1.0, dt / 0.008) * math.exp(-dt * 18)
                # Voiced "ha" — formants for open vowel
                f1 = 0.3 * env * math.sin(2 * math.pi * 700 * t)  # F1
                f2 = 0.2 * env * math.sin(2 * math.pi * 1200 * t)  # F2
                # Slight pitch drop within burst
                pitch = 280 - 40 * dt
                glottal = 0.35 * env * math.sin(2 * math.pi * pitch * t)
                # Soft FM shimmer
                shimmer = 0.08 * env * math.sin(2 * math.pi * pitch * 2.01 * t)
                val += ba * (f1 + f2 + glottal + shimmer)
        samples.append(val)
    return reverb(samples, decay=0.25, delays_ms=(30, 55, 89))

def sigh_content():
    """Content sigh — warm descending breath with vocal resonance and reverb."""
    n = int(SAMPLE_RATE * 0.9)
    samples = []
    for i in range(n):
        t = i / SAMPLE_RATE
        # Slow attack, sustained, long decay
        if t < 0.04:
            env = t / 0.04
        elif t < 0.25:
            env = 1.0
        else:
            env = max(0, 1.0 - ((t - 0.25) / 0.65)) ** 0.7  # Rounded decay
        # Descending fundamental with vibrato
        freq = 320 - 80 * (t / 0.9) + 3 * math.sin(2 * math.pi * 5.5 * t)
        glottal = 0.35 * env * math.sin(2 * math.pi * freq * t)
        # Warm formants (open "ah" vowel)
        f1 = 0.2 * env * math.sin(2 * math.pi * 700 * t)
        f2 = 0.12 * env * math.sin(2 * math.pi * 1150 * t)
        # Breathy noise layer
        breath = 0.12 * env * (random.random() * 2 - 1) * math.exp(-t * 1.5)
        samples.append(glottal + f1 + f2 + breath)
    return reverb(samples, decay=0.35, delays_ms=(40, 67, 97, 130))

def hmm_thoughtful():
    """Thoughtful hmm — nasal hum with formants, vibrato, and reverb."""
    n = int(SAMPLE_RATE * 0.55)
    samples = []
    for i in range(n):
        t = i / SAMPLE_RATE
        # Smooth envelope: slow attack, sustain, gentle release
        if t < 0.03:
            env = t / 0.03
        elif t < 0.42:
            env = 1.0
        else:
            env = max(0, (0.55 - t) / 0.13) ** 0.5
        # Fundamental with gentle vibrato
        freq = 140 + 4 * math.sin(2 * math.pi * 5 * t)
        fund = 0.4 * env * math.sin(2 * math.pi * freq * t)
        # Nasal formants ("mm" quality)
        nasal1 = 0.2 * env * math.sin(2 * math.pi * 280 * t)  # 2nd harmonic
        nasal2 = 0.1 * env * math.sin(2 * math.pi * 420 * t)  # 3rd harmonic
        nasal3 = 0.05 * env * math.sin(2 * math.pi * 700 * t)  # 5th harmonic
        # Slight frequency modulation for warmth
        warmth = 0.03 * env * math.sin(2 * math.pi * freq * 2.003 * t)
        samples.append(fund + nasal1 + nasal2 + nasal3 + warmth)
    return reverb(samples, decay=0.3, delays_ms=(33, 61, 97))

def oh_realization():
    """Sudden realization — rising pitch with harmonic sparkle and reverb."""
    n = int(SAMPLE_RATE * 0.35)
    samples = []
    for i in range(n):
        t = i / SAMPLE_RATE
        # Sharp attack, sustained, quick decay
        if t < 0.01:
            env = t / 0.01
        elif t < 0.08:
            env = 1.0
        elif t < 0.2:
            env = max(0, 1.0 - (t - 0.08) / 0.12) ** 0.6
        else:
            env = 0.1 * math.exp(-(t - 0.2) * 20)
        # Rising pitch: "oh!" vowel
        freq = 350 + 400 * (t / 0.35)
        glottal = 0.45 * env * math.sin(2 * math.pi * freq * t)
        # "oh" formants
        f1 = 0.2 * env * math.sin(2 * math.pi * 500 * t)   # F1 ~500
        f2 = 0.15 * env * math.sin(2 * math.pi * 900 * t)   # F2 ~900
        # Surprise sparkle — high harmonic
        sparkle = 0.08 * env * math.sin(2 * math.pi * 2400 * t) * math.exp(-t * 8)
        # Quick breath attack
        breath = 0.15 * (random.random() * 2 - 1) * max(0, 1 - t * 50) if t < 0.02 else 0
        samples.append(glottal + f1 + f2 + sparkle + breath)
    return reverb(samples, decay=0.3, delays_ms=(27, 47, 73))

def throat_clear():
    """Brief throat clear — noise burst with resonant cavity tone and reverb."""
    n = int(SAMPLE_RATE * 0.2)
    samples = []
    for i in range(n):
        t = i / SAMPLE_RATE
        # Very sharp double-envelope (two tiny bursts)
        if t < 0.03:
            env = t / 0.03
        elif t < 0.06:
            env = 1.0 - 0.5 * (t - 0.03) / 0.03
        elif t < 0.07:
            env = 0.5 + 0.5 * (t - 0.06) / 0.01  # Re-attack
        elif t < 0.1:
            env = 1.0
        else:
            env = max(0, (0.2 - t) / 0.1) ** 0.5
        # Resonant cavity tone
        tone = 0.3 * env * math.sin(2 * math.pi * 180 * t)
        harm2 = 0.15 * env * math.sin(2 * math.pi * 360 * t)
        # Shaped noise
        noise_val = 0.4 * env * (random.random() * 2 - 1)
        samples.append(tone + harm2 + noise_val)
    # Extend with silence to 0.4s for reverb tail
    while len(samples) < int(SAMPLE_RATE * 0.4):
        samples.append(0)
    return reverb(samples[:int(SAMPLE_RATE * 0.4)], decay=0.2, delays_ms=(15, 31, 53))

def chuckle_warm():
    """Warm chuckle — three voiced bursts with FM warmth and room reverb."""
    samples = []
    total_dur = 0.55
    n = int(SAMPLE_RATE * total_dur)
    burst_times = [0.0, 0.15, 0.3]
    burst_amps = [0.55, 0.45, 0.3]
    for i in range(n):
        t = i / SAMPLE_RATE
        val = 0
        for bt, ba in zip(burst_times, burst_amps):
            dt = t - bt
            if 0 < dt < 0.1:
                env = min(1.0, dt / 0.008) * math.exp(-dt * 15)
                # Voiced "huh" — warm formants
                pitch = 220 + 30 * dt
                glottal = 0.3 * env * math.sin(2 * math.pi * pitch * t)
                f1 = 0.18 * env * math.sin(2 * math.pi * 650 * t)
                f2 = 0.1 * env * math.sin(2 * math.pi * 1050 * t)
                # FM warmth
                warmth = 0.06 * env * math.sin(2 * math.pi * pitch * 2.005 * t)
                val += ba * (glottal + f1 + f2 + warmth)
        samples.append(val)
    return reverb(samples, decay=0.25, delays_ms=(35, 63, 97))

def mhm_affirming():
    """Affirming mhm — double-pitched nasal hum with formants and reverb."""
    n = int(SAMPLE_RATE * 0.45)
    samples = []
    for i in range(n):
        t = i / SAMPLE_RATE
        # Two-hump envelope: "m" pause "m"
        if t < 0.03:
            env = t / 0.03
        elif t < 0.15:
            env = 1.0
        elif t < 0.22:
            env = 0.25 + 0.0 * (t - 0.15)  # Sustain dip
        elif t < 0.25:
            env = 0.25 + 0.75 * (t - 0.22) / 0.03  # Re-attack
        elif t < 0.38:
            env = 1.0
        else:
            env = max(0, (0.45 - t) / 0.07) ** 0.5
        # Nasal "m" formants
        fund = 0.35 * env * math.sin(2 * math.pi * 120 * t)  # Low fundamental
        nasal1 = 0.2 * env * math.sin(2 * math.pi * 280 * t)   # 2nd harmonic
        nasal2 = 0.12 * env * math.sin(2 * math.pi * 400 * t)  # 3rd harmonic
        nasal3 = 0.06 * env * math.sin(2 * math.pi * 600 * t)  # 5th harmonic
        # Subtle vibrato for warmth
        vibrato = 0.02 * env * math.sin(2 * math.pi * 4 * t)
        samples.append(fund + nasal1 + nasal2 + nasal3 + vibrato)
    return reverb(samples, decay=0.3, delays_ms=(37, 67, 103))

def windchime_subtle():
    """Ethereal windchime — layered sine tones with decay and spatial reverb."""
    n = int(SAMPLE_RATE * 1.5)  # 1.5 seconds for spacious feel
    samples = []
    # Chime notes: pentatonic scale with random timing
    chime_freqs = [523.25, 659.25, 783.99, 1046.50, 1318.51]  # C5, E5, G5, C6, E6
    chime_times = [0.0, 0.08, 0.22, 0.35, 0.12]  # Staggered strikes
    chime_amps = [0.3, 0.25, 0.2, 0.15, 0.22]

    for i in range(n):
        t = i / SAMPLE_RATE
        val = 0
        for cf, ct, ca in zip(chime_freqs, chime_times, chime_amps):
            dt = t - ct
            if dt > 0:
                # Long exponential decay with slow modulation
                env = ca * math.exp(-dt * 3.5) * (1 + 0.08 * math.sin(2 * math.pi * 2.5 * dt))
                # Fundamental + shimmer harmonics
                fundamental = env * math.sin(2 * math.pi * cf * dt)
                harmonic2 = 0.3 * env * math.sin(2 * math.pi * cf * 2.0 * dt)
                harmonic3 = 0.1 * env * math.sin(2 * math.pi * cf * 3.01 * dt)  # Slight detune for shimmer
                # Slight vibrato from wind
                vibrato = 0.05 * env * math.sin(2 * math.pi * (cf + 3 * math.sin(2 * math.pi * 1.5 * dt)) * dt)
                val += fundamental + harmonic2 + harmonic3 + vibrato
        # Very gentle wind noise throughout
        if t < 1.2:
            wind_env = 0.02 * (1 + 0.5 * math.sin(2 * math.pi * 0.3 * t))
            wind = wind_env * (random.random() * 2 - 1) * math.exp(-t * 0.8)
            val += wind
        samples.append(val)
    return reverb(samples, decay=0.45, delays_ms=(47, 79, 127, 173, 223))

if __name__ == '__main__':
    print(f'Generating rich soundboard WAVs in {OUTPUT_DIR}...')
    generate_wav('gasp_subtle.wav', gasp_subtle())
    print('  ✓ gasp_subtle.wav — shaped breath + formant resonance + reverb')
    generate_wav('laugh_soft.wav', laugh_soft())
    print('  ✓ laugh_soft.wav — warm vocal bursts + FM shimmer + reverb')
    generate_wav('sigh_content.wav', sigh_content())
    print('  ✓ sigh_content.wav — descending breath + vocal formants + reverb')
    generate_wav('hmm_thoughtful.wav', hmm_thoughtful())
    print('  ✓ hmm_thoughtful.wav — nasal hum + harmonics + vibrato + reverb')
    generate_wav('oh_realization.wav', oh_realization())
    print('  ✓ oh_realization.wav — rising pitch + sparkle harmonics + reverb')
    generate_wav('throat_clear.wav', throat_clear())
    print('  ✓ throat_clear.wav — resonant cavity + shaped noise + reverb')
    generate_wav('chuckle_warm.wav', chuckle_warm())
    print('  ✓ chuckle_warm.wav — warm FM bursts + formants + reverb')
    generate_wav('mhm_affirming.wav', mhm_affirming())
    print('  ✓ mhm_affirming.wav — nasal double-hump + harmonics + reverb')
    generate_wav('windchime_subtle.wav', windchime_subtle())
    print('  ✓ windchime_subtle.wav — pentatonic chimes + shimmer + wind noise + reverb')
    print('All 9 rich soundboard WAVs generated!')