"""
REWIND.exe - procedural audio generator (numpy only).

Writes WAV files into Assets/Audio/:
  SFX/       short one-shots (terminal, doors, UI, tape)        mono 44.1 kHz
  Ambience/  seamless room loops (16 s)                          mono 32 kHz
  Music/     seamless dark-ambient / minimal-synth loops         stereo 44.1 kHz

Follows the GDD audio direction (section 8): old machines humming in an empty building,
mechanical clicks, tape noise, minimal non-distracting music.

Usage:  python Tools/AudioGen/generate_audio.py            (from the project root)
        python Tools/AudioGen/generate_audio.py --stats    (also prints peak/RMS/loop checks)
"""
import os
import sys
import wave

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(ROOT, "Assets", "Audio")
SR = 44100
STATS = []


# --------------------------------------------------------------------------
# DSP helpers
# --------------------------------------------------------------------------
def rng(seed):
    return np.random.default_rng(seed)


def ns(dur, sr=SR):
    """Sample count for a duration (single rounding rule everywhere, so layers always line up)."""
    return int(dur * sr)


def t_axis(dur, sr=SR):
    return np.arange(ns(dur, sr)) / sr


def osc(freq, dur=None, sr=SR, shape="sine", phase=0.0, n=None):
    """freq: number or per-sample array."""
    if n is None:
        n = len(freq) if np.ndim(freq) else ns(dur, sr)
    f = np.broadcast_to(np.asarray(freq, dtype=np.float64), (n,))
    ph = phase + np.cumsum(f) / sr
    frac = ph % 1.0
    if shape == "sine":
        return np.sin(2 * np.pi * ph)
    if shape == "saw":
        return 2 * frac - 1
    if shape == "square":
        return np.where(frac < 0.5, 1.0, -1.0)
    if shape == "tri":
        return 4 * np.abs(frac - 0.5) - 1
    raise ValueError(shape)


def noise(n, seed=0):
    return rng(seed).standard_normal(n)


def spectral(x, sr, fn):
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / sr)
    return np.fft.irfft(X * fn(f), len(x))


def lowpass(x, sr, fc, order=2):
    return spectral(x, sr, lambda f: 1 / np.sqrt(1 + (f / fc) ** (2 * order)))


def highpass(x, sr, fc, order=2):
    return spectral(x, sr, lambda f: 1 / np.sqrt(1 + (fc / np.maximum(f, 1e-6)) ** (2 * order)))


def bandpass(x, sr, lo, hi, order=2):
    return lowpass(highpass(x, sr, lo, order), sr, hi, order)


def pink(n, seed=0, sr=SR):
    return normalize(spectral(noise(n, seed), sr, lambda f: 1 / np.sqrt(np.maximum(f, 20))), 1)


def brown(n, seed=0, sr=SR):
    return normalize(spectral(noise(n, seed), sr, lambda f: 1 / np.maximum(f, 15)), 1)


def env_exp(n, tau, sr=SR, delay=0.0):
    t = np.arange(n) / sr - delay
    e = np.exp(-np.maximum(t, 0) / tau)
    e[t < 0] = 0
    return e


def env_ar(n, attack, release, sr=SR, hold=None):
    """Attack, optional hold, release (seconds). Hold default fills the rest."""
    t = np.arange(n) / sr
    dur = n / sr
    hold = dur - attack - release if hold is None else hold
    e = np.ones(n)
    e[t < attack] = t[t < attack] / max(attack, 1e-6)
    rel_start = attack + hold
    m = t >= rel_start
    e[m] = np.clip(1 - (t[m] - rel_start) / max(release, 1e-6), 0, 1)
    return e


def place(dst, src, at, sr=SR, gain=1.0):
    i = int(round(at * sr))
    if i >= len(dst):
        return dst
    j = min(len(dst), i + len(src))
    dst[i:j] += src[: j - i] * gain
    return dst


def normalize(x, peak=0.9):
    m = np.max(np.abs(x))
    return x * (peak / m) if m > 0 else x


def soft_clip(x, drive=1.0):
    return np.tanh(x * drive) / np.tanh(drive)


def fade_edges(x, sr, fin=0.002, fout=0.01):
    a, b = int(fin * sr), int(fout * sr)
    if a:
        x[:a] *= np.linspace(0, 1, a)
    if b:
        x[-b:] *= np.linspace(1, 0, b)
    return x


def fold_loop(x, loop_n):
    """x is longer than loop_n: the overhang (release tails, echoes) is wrapped onto the start,
    which makes the loop sample-accurately seamless."""
    out = x[..., :loop_n].copy()
    tail = x[..., loop_n:]
    k = 0
    while tail.shape[-1] > 0:
        seg = tail[..., :loop_n]
        out[..., : seg.shape[-1]] += seg
        tail = tail[..., loop_n:]
        k += 1
    return out


def midi(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def write(rel, x, sr=SR):
    path = os.path.join(OUT, rel.replace("/", os.sep))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    x = np.asarray(x, dtype=np.float64)
    stereo = x.ndim == 2
    data = np.clip(x.T if stereo else x, -1, 1)
    pcm = (data * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(2 if stereo else 1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    peak = float(np.max(np.abs(x)))
    rms = float(np.sqrt(np.mean(x ** 2)))
    # loop seam check: jump between last and first sample vs typical sample-to-sample step
    flat = x if not stereo else x[0]
    seam = float(abs(flat[-1] - flat[0]))
    typical = float(np.percentile(np.abs(np.diff(flat)), 99)) + 1e-9
    STATS.append((rel, len(flat) / sr, peak, rms, seam / typical))
    print(f"  {rel:42s} {len(flat) / sr:6.2f}s  {'stereo' if stereo else 'mono  '}  peak {peak:.2f}")


# --------------------------------------------------------------------------
# SFX (mono 44.1 kHz)
# --------------------------------------------------------------------------
def metal_ping(dur, freqs, tau, sr=SR):
    t = t_axis(dur, sr)
    return sum(np.sin(2 * np.pi * f * t) * np.exp(-t / (tau * (1 - i * 0.15))) for i, f in enumerate(freqs))


def thump(dur, f0, f1, tau, sr=SR):
    t = t_axis(dur, sr)
    f = f1 + (f0 - f1) * np.exp(-t / 0.05)
    return osc(f, sr=sr) * np.exp(-t / tau)


def click(dur=0.03, seed=1, lo=1500, hi=6000, tau=0.004, tone=900):
    n = int(dur * SR)
    x = bandpass(noise(n, seed), SR, lo, hi) * env_exp(n, tau)
    x = normalize(x, 1) + 0.5 * osc(tone, dur) * env_exp(n, tau * 1.5)
    return x


def sfx_hover():
    n = int(0.05 * SR)
    t = t_axis(0.05)
    x = (np.sin(2 * np.pi * 2600 * t) + 0.3 * np.sin(2 * np.pi * 5200 * t)) * env_exp(n, 0.009)
    return fade_edges(normalize(x, 0.22), SR, 0.001, 0.005)


def sfx_click():
    return fade_edges(normalize(click(0.05, 3), 0.55), SR, 0.0005, 0.005)


def sfx_type():
    x = click(0.03, 7, 2000, 9000, 0.0025, 1700)
    return fade_edges(normalize(x, 0.4), SR, 0.0003, 0.004)


def sfx_terminal_open():
    dur = 0.95
    n = int(dur * SR)
    t = t_axis(dur)
    x = np.zeros(n)
    x += 0.9 * np.pad(thump(0.4, 110, 38, 0.09), (0, n - int(0.4 * SR)))
    static = highpass(noise(n, 11), SR, 1800) * env_exp(n, 0.16, delay=0.02)
    x += 0.30 * normalize(static, 1) * (0.6 + 0.4 * (noise(n, 12) > 1.2))
    whine_f = 9000 + 6000 * np.clip(t / 0.4, 0, 1)
    x += 0.035 * osc(whine_f) * env_ar(n, 0.15, 0.4)
    hum = lowpass(osc(120, dur, shape="saw"), SR, 500)
    x += 0.25 * normalize(hum, 1) * env_ar(n, 0.08, 0.5)
    x = place(x, click(0.04, 13), 0.0, gain=0.5)
    return fade_edges(normalize(x, 0.8), SR, 0.001, 0.05)


def sfx_terminal_close():
    dur = 0.5
    n = int(dur * SR)
    t = t_axis(dur)
    f = 60 + 1400 * np.exp(-t / 0.07)
    x = 0.6 * osc(f) * env_exp(n, 0.12)
    x += 0.3 * normalize(lowpass(noise(n, 21), SR, 3000), 1) * env_exp(n, 0.05)
    x = place(x, click(0.04, 22, tone=500), 0.0, gain=0.5)
    return fade_edges(normalize(x, 0.7), SR, 0.001, 0.05)


def beep(freq, dur, sr=SR):
    n = int(dur * sr)
    x = osc(freq, dur) + 0.25 * osc(freq * 3, dur)
    return x * env_ar(n, 0.004, dur * 0.6)


def sfx_accept():
    x = np.zeros(int(0.32 * SR))
    place(x, beep(880, 0.09), 0.0)
    place(x, beep(1320, 0.16), 0.1)
    return fade_edges(normalize(lowpass(x, SR, 6000), 0.5), SR)


def sfx_error():
    x = np.zeros(int(0.34 * SR))
    for at in (0.0, 0.17):
        seg = lowpass(osc(150, 0.13, shape="square"), SR, 1800) * env_ar(int(0.13 * SR), 0.003, 0.03)
        place(x, seg, at)
    return fade_edges(normalize(x, 0.5), SR)


def sfx_door_open():
    dur = 1.0
    n = int(dur * SR)
    t = t_axis(dur)
    f = 170 + 140 * np.clip(t / 0.5, 0, 1) ** 2 + 5 * np.sin(2 * np.pi * 6 * t)
    servo = lowpass(osc(f, shape="saw"), SR, 1300) * env_ar(n, 0.05, 0.12, hold=0.45)
    hiss = bandpass(noise(n, 31), SR, 2500, 9000) * env_exp(n, 0.25, delay=0.01)
    x = 0.35 * normalize(servo, 1) + 0.25 * normalize(hiss, 1)
    clunk = 0.8 * thump(0.35, 80, 45, 0.07) + 0.15 * metal_ping(0.35, (620, 1480, 2330), 0.12)
    place(x, clunk, 0.62)
    place(x, click(0.04, 32, tone=300), 0.0, gain=0.4)
    return fade_edges(normalize(x, 0.8), SR, 0.001, 0.08)


def sfx_door_locked():
    dur = 0.55
    n = int(dur * SR)
    t = t_axis(dur)
    buzz = lowpass(osc(110, dur, shape="square"), SR, 1800) * (0.6 + 0.4 * np.sin(2 * np.pi * 18 * t))
    x = 0.6 * buzz * env_ar(n, 0.01, 0.12, hold=0.28)
    x += 0.25 * metal_ping(dur, (520, 1210), 0.06)
    x += 0.4 * np.pad(thump(0.2, 90, 50, 0.04), (0, n - int(0.2 * SR)))
    return fade_edges(normalize(x, 0.6), SR, 0.001, 0.05)


def sfx_door_unlock():
    x = np.zeros(int(0.6 * SR))
    for at, seed in ((0.0, 41), (0.07, 42)):
        place(x, thump(0.15, 300, 120, 0.03), at, gain=0.6)
        place(x, click(0.04, seed, tone=700), at, gain=0.4)
    place(x, 0.5 * beep(660, 0.1), 0.18)
    place(x, 0.5 * beep(990, 0.18), 0.29)
    return fade_edges(normalize(x, 0.6), SR)


def sfx_room_transition():
    """Tape-rewind whoosh: sweeping band of noise + warbling reel tone."""
    dur = 0.75
    n = int(dur * SR)
    t = t_axis(dur)
    x = np.zeros(n)
    bands = ((250, 700), (700, 1800), (1800, 4500), (4500, 11000))
    for i, (lo, hi) in enumerate(bands):
        center = 0.12 + i * 0.13
        e = np.exp(-((t - center) / 0.14) ** 2)
        x += normalize(bandpass(noise(n, 50 + i), SR, lo, hi), 1) * e
    f = 400 + 2200 * (t / dur) ** 1.5 + 60 * np.sin(2 * np.pi * 30 * t)
    x += 0.15 * osc(f) * env_ar(n, 0.05, 0.25)
    x *= env_ar(n, 0.06, 0.25)
    return fade_edges(normalize(x, 0.55), SR, 0.002, 0.05)


def motor(dur, f0, f1, seed):
    n = int(dur * SR)
    t = t_axis(dur)
    f = f0 + (f1 - f0) * (1 - np.exp(-t / (dur * 0.35)))
    m = lowpass(osc(f, shape="saw"), SR, 900) + 0.3 * bandpass(noise(n, seed), SR, 300, 2000)
    return normalize(m, 1)


def sfx_rec_start():
    dur = 0.7
    n = int(dur * SR)
    x = 0.35 * motor(dur, 30, 115, 61) * env_ar(n, 0.15, 0.25)
    place(x, click(0.05, 62, 800, 5000, 0.006, 600), 0.0, gain=0.8)
    return fade_edges(normalize(x, 0.7), SR, 0.0005, 0.05)


def sfx_rec_stop():
    dur = 0.6
    n = int(dur * SR)
    x = 0.35 * motor(dur, 115, 25, 63) * env_exp(n, 0.2)
    place(x, click(0.05, 64, 800, 5000, 0.006, 500), 0.0, gain=0.8)
    return fade_edges(normalize(x, 0.7), SR, 0.0005, 0.05)


def sfx_rewind():
    dur = 1.3
    n = int(dur * SR)
    t = t_axis(dur)
    flutter = 0.6 + 0.4 * np.sin(2 * np.pi * 22 * t)
    x = normalize(bandpass(noise(n, 71), SR, 1000, 6000), 1) * flutter * 0.5
    x += 0.2 * osc(1800 + 300 * np.sin(2 * np.pi * 9 * t) + 600 * t)
    x += 0.25 * motor(dur, 160, 220, 72)
    x *= env_ar(n, 0.12, 0.3)
    place(x, click(0.05, 73), 0.0, gain=0.6)
    return fade_edges(normalize(x, 0.6), SR, 0.001, 0.05)


def sfx_paper():
    x = np.zeros(int(0.4 * SR))
    r = rng(81)
    for i in range(7):
        n = int(r.uniform(0.02, 0.06) * SR)
        seg = bandpass(noise(n, 82 + i), SR, 1200, 7000) * env_ar(n, 0.005, n / SR * 0.7)
        place(x, seg, r.uniform(0, 0.3), gain=r.uniform(0.4, 1.0))
    return fade_edges(normalize(x, 0.45), SR)


# --------------------------------------------------------------------------
# Ambience loops (mono 32 kHz, 16 s, seamless)
# --------------------------------------------------------------------------
ASR = 32000
ALEN = 16.0


def amb_base(seed):
    n = int(ALEN * ASR)
    return n, t_axis(ALEN, ASR)


def tick(dur, sr, seed, lo=2000, hi=7000, tau=0.003):
    n = int(dur * sr)
    return normalize(bandpass(noise(n, seed), sr, lo, hi), 1) * env_exp(n, tau, sr)


def wrap_place(dst, src, at, sr, gain=1.0):
    """place() that wraps around the loop end (keeps loops seamless)."""
    i = int(round(at * sr)) % len(dst)
    j = i + len(src)
    if j <= len(dst):
        dst[i:j] += src * gain
    else:
        k = len(dst) - i
        dst[i:] += src[:k] * gain
        dst[: len(src) - k] += src[k:] * gain


def amb_control_room():
    n, t = amb_base(1)
    wob = 1 + 0.08 * np.sin(2 * np.pi * t / ALEN * 3)
    hum = (0.12 * np.sin(2 * np.pi * 50 * t) + 0.07 * np.sin(2 * np.pi * 100 * t)
           + 0.05 * np.sin(2 * np.pi * 150 * t) + 0.02 * np.sin(2 * np.pi * 250 * t)) * wob
    fan = 0.10 * normalize(bandpass(pink(n, 2, ASR), ASR, 180, 1100), 1)
    air = 0.14 * normalize(lowpass(brown(n, 3, ASR), ASR, 300), 1)
    x = hum + fan + air
    r = rng(4)
    for _ in range(7):
        wrap_place(x, tick(0.03, ASR, int(r.integers(1000)), 800, 4000, 0.004), r.uniform(0, ALEN), ASR, r.uniform(0.05, 0.12))
    beep_t = t_axis(0.12, ASR)
    wrap_place(x, np.sin(2 * np.pi * 1200 * beep_t) * env_ar(len(beep_t), 0.005, 0.08, ASR), 9.3, ASR, 0.025)
    return normalize(x, 0.5)


def amb_archive():
    n, t = amb_base(10)
    air = 0.2 * normalize(lowpass(brown(n, 11, ASR), ASR, 380), 1)
    hiss = 0.025 * normalize(highpass(pink(n, 12, ASR), ASR, 3500), 1)
    motor_hum = 0.03 * np.sin(2 * np.pi * 60 * t) + 0.015 * np.sin(2 * np.pi * 120 * t)
    x = air + hiss + motor_hum
    r = rng(13)
    at = 0.25
    while at < ALEN + 0.25 - 0.5:  # slow reel ticking
        wrap_place(x, tick(0.02, ASR, int(r.integers(1000)), 2500, 7000), at, ASR, r.uniform(0.04, 0.08))
        at += 0.5 + r.uniform(-0.04, 0.04)
    for c in (5.2, 12.6):  # shelf creaks
        d = 0.6
        cn = int(d * ASR)
        ct = t_axis(d, ASR)
        creak = osc(210 - 60 * ct / d, sr=ASR, shape="saw") * (0.5 + 0.5 * (noise(cn, int(c * 10)) > 0.8))
        wrap_place(x, lowpass(creak, ASR, 1500) * env_ar(cn, 0.1, 0.3, ASR), c, ASR, 0.05)
    return normalize(x, 0.45)


def amb_generator():
    n, t = amb_base(20)
    throb = 0.7 + 0.3 * np.sin(2 * np.pi * 0.5 * t)
    rumble = 0.5 * normalize(lowpass(brown(n, 21, ASR), ASR, 140), 1)
    tones = (0.22 * np.sin(2 * np.pi * 45 * t) + 0.12 * np.sin(2 * np.pi * 90 * t)
             + 0.05 * np.sin(2 * np.pi * 135 * t)) * throb
    hiss = 0.05 * normalize(bandpass(noise(n, 22), ASR, 1000, 4000), 1)
    x = rumble + tones + hiss
    for k in range(4):  # mechanical clank every 4 s
        clank = 0.7 * thump(0.4, 90, 40, 0.08, ASR)
        clank += 0.2 * metal_ping(0.4, (480, 1130), 0.1, ASR)
        wrap_place(x, clank, 1.0 + k * 4.0, ASR, 0.18)
    return normalize(x, 0.55)


def amb_core():
    n, t = amb_base(30)
    drone = (0.25 * normalize(lowpass(osc(55, ALEN, ASR, "saw"), ASR, 280), 1)
             + 0.15 * normalize(lowpass(osc(82.5, ALEN, ASR, "saw"), ASR, 300), 1))
    eerie = 0.02 * np.sin(2 * np.pi * 1760 * t) * (0.5 + 0.5 * np.sin(2 * np.pi * 0.25 * t))
    swell = 0.06 * normalize(bandpass(pink(n, 31, ASR), ASR, 500, 2000), 1) * (0.5 + 0.5 * np.sin(2 * np.pi * t / ALEN * 2))
    x = drone + eerie + swell
    for k in range(8):  # heartbeat pulse every 2 s
        hb = thump(0.3, 70, 45, 0.06, ASR)
        wrap_place(x, hb, k * 2.0, ASR, 0.3)
        wrap_place(x, hb, k * 2.0 + 0.28, ASR, 0.2)
    return normalize(x, 0.5)


# --------------------------------------------------------------------------
# Intro cutscene sounds
# --------------------------------------------------------------------------
def sfx_voice_operator():
    """Soft low 'talk' blip played while the operator's text types out."""
    dur = 0.06
    n = ns(dur)
    x = lowpass(osc(190, dur, shape="tri") + 0.3 * osc(380, dur), SR, 1600) * env_ar(n, 0.004, 0.04)
    return fade_edges(normalize(x, 0.35), SR)


def sfx_voice_system():
    """Short digital blip for SYSTEM lines."""
    dur = 0.045
    n = ns(dur)
    x = lowpass(osc(940, dur, shape="square"), SR, 5000) * env_ar(n, 0.002, 0.03)
    return fade_edges(normalize(x, 0.3), SR)


def sfx_blast_door():
    """Heavy bunker door: deep motor grind, pneumatic hiss, final slam."""
    dur = 2.6
    n = ns(dur)
    t = t_axis(dur)
    grind_f = 48 + 10 * np.sin(2 * np.pi * 3 * t) + 20 * np.clip(t / 1.5, 0, 1)
    grind = lowpass(osc(grind_f, shape="saw"), SR, 400) * (0.7 + 0.3 * (noise(n, 91) > 0.5))
    x = 0.55 * normalize(grind, 1) * env_ar(n, 0.15, 0.4, hold=1.6)
    x += 0.35 * normalize(lowpass(brown(n, 92), SR, 200), 1) * env_ar(n, 0.1, 0.6, hold=1.4)
    x += 0.30 * normalize(bandpass(noise(n, 93), SR, 2000, 9000), 1) * env_exp(n, 0.35, delay=0.05)
    place(x, 0.9 * thump(0.6, 70, 35, 0.15) + 0.2 * metal_ping(0.6, (310, 740, 1290), 0.2), 2.05)
    place(x, click(0.05, 94, 500, 3000, 0.01, 200), 0.0, gain=0.8)
    return fade_edges(normalize(x, 0.85), SR, 0.002, 0.1)


def sfx_power_up():
    """Old machine powering on: relay clack, rising hum, CRT whine, fan spin-up."""
    dur = 2.2
    n = ns(dur)
    t = t_axis(dur)
    f = 30 + 90 * (1 - np.exp(-t / 0.6))
    hum = lowpass(osc(f, shape="saw"), SR, 700)
    x = 0.45 * normalize(hum, 1) * env_ar(n, 0.3, 0.4)
    fan = bandpass(noise(n, 101), SR, 300, 1500) * np.clip(t / 1.2, 0, 1)
    x += 0.2 * normalize(fan, 1) * env_ar(n, 0.01, 0.5)
    x += 0.03 * osc(8000 + 7000 * np.clip(t / 1.0, 0, 1)) * env_ar(n, 0.4, 0.6)
    for at, seed in ((0.0, 102), (0.08, 103), (0.9, 104)):
        place(x, click(0.05, seed, 600, 4000, 0.008, 400), at, gain=0.7)
    return fade_edges(normalize(x, 0.8), SR, 0.002, 0.1)


def sfx_glitch():
    """Digital stutter: chopped noise and square bursts."""
    dur = 0.7
    n = ns(dur)
    x = np.zeros(n)
    r = rng(111)
    at = 0.0
    while at < dur - 0.05:
        seg_d = r.uniform(0.015, 0.06)
        sn = ns(seg_d)
        if r.random() < 0.5:
            seg = osc(r.uniform(200, 2400), seg_d, shape="square")
        else:
            seg = bandpass(noise(sn, int(r.integers(10000))), SR, 800, 9000)
        place(x, normalize(seg, 1) * env_ar(sn, 0.001, 0.005), at, gain=r.uniform(0.3, 1.0))
        at += seg_d + r.uniform(0.0, 0.04)
    return fade_edges(normalize(x, 0.5), SR, 0.001, 0.03)


def amb_wind():
    """Exterior: gusting wind over the wasteland, distant creaking wires."""
    n, t = amb_base(40)
    gust = 0.55 + 0.45 * np.sin(2 * np.pi * t / ALEN * 2) * np.sin(2 * np.pi * t / ALEN * 3 + 1)
    low = normalize(lowpass(brown(n, 41, ASR), ASR, 400), 1)
    whistle = normalize(bandpass(pink(n, 42, ASR), ASR, 700, 1800), 1)
    x = 0.45 * low * gust + 0.18 * whistle * gust ** 2
    for c in (3.0, 10.5):
        d = 1.2
        cn = ns(d, ASR)
        ct = t_axis(d, ASR)
        creak = osc(320 + 40 * np.sin(2 * np.pi * 1.5 * ct), sr=ASR, shape="saw")
        wrap_place(x, lowpass(creak, ASR, 1200) * env_ar(cn, 0.3, 0.6, ASR), c, ASR, 0.03)
    return normalize(x, 0.5)


# --------------------------------------------------------------------------
# Ending cutscene sounds
# --------------------------------------------------------------------------
def sfx_power_down():
    """Machines dying: hum sliding down, relays dropping out."""
    dur = 2.4
    n = ns(dur)
    t = t_axis(dur)
    f = 25 + 95 * np.exp(-t / 0.7)
    x = 0.5 * normalize(lowpass(osc(f, shape="saw"), SR, 700), 1) * env_ar(n, 0.01, 0.6)
    x += 0.04 * osc(15000 - 9000 * np.clip(t / 0.8, 0, 1)) * env_exp(n, 0.4)
    for at, seed in ((0.0, 121), (0.35, 122), (0.9, 123), (1.6, 124)):
        place(x, click(0.05, seed, 400, 3000, 0.01, 250), at, gain=0.6)
    return fade_edges(normalize(x, 0.8), SR, 0.002, 0.15)


def sfx_countdown_beep():
    dur = 0.22
    n = ns(dur)
    x = (osc(1320, dur, shape="square") * 0.4 + osc(1320, dur)) * env_ar(n, 0.003, 0.08)
    return fade_edges(normalize(lowpass(x, SR, 6000), 0.6), SR)


def sfx_nuke():
    """Nuclear blast: crack, sub-bass drop, long rumble, roaring wind and debris."""
    dur = 7.5
    n = ns(dur)
    t = t_axis(dur)
    x = np.zeros(n)
    crack = highpass(noise(ns(0.08), 131), SR, 1500) * env_exp(ns(0.08), 0.02)
    place(x, normalize(crack, 1), 0.0, gain=0.9)
    sub_f = 22 + 38 * np.exp(-t / 0.5)
    x += 1.0 * osc(sub_f) * env_exp(n, 1.6) * env_ar(n, 0.01, 1.0)
    x += 0.8 * normalize(lowpass(noise(n, 132), SR, 300), 1) * env_exp(n, 1.1)
    rumble = normalize(lowpass(brown(n, 133), SR, 120), 1) * (0.7 + 0.3 * np.sin(2 * np.pi * 0.7 * t))
    x += 0.7 * rumble * env_ar(n, 0.05, 3.0)
    roar = normalize(bandpass(noise(n, 134), SR, 200, 2200), 1)
    x += 0.35 * roar * np.clip(t / 0.6, 0, 1) * np.exp(-np.maximum(t - 1.0, 0) / 2.2)
    r = rng(135)
    for _ in range(40):
        at = r.uniform(0.8, 6.5)
        place(x, tick(0.03, SR, int(r.integers(9999)), 600, 5000, 0.006), at, gain=r.uniform(0.05, 0.2))
    return fade_edges(soft_clip(normalize(x, 1.0), 1.6) * 0.95, SR, 0.0005, 0.5)


def amb_alarm():
    """Klaxon + warning tone over a low hum (loops every 16 s, 1 s klaxon cycle)."""
    n, t = amb_base(50)
    phase = (t % 1.0)
    f = np.where(phase < 0.5, 620.0, 470.0)
    klax = lowpass(osc(f, sr=ASR, shape="square"), ASR, 2200) * (0.6 + 0.4 * np.sin(2 * np.pi * 4 * t))
    hum = 0.2 * np.sin(2 * np.pi * 50 * t) + 0.1 * np.sin(2 * np.pi * 100 * t)
    air = 0.15 * normalize(lowpass(brown(n, 51, ASR), ASR, 300), 1)
    return normalize(0.45 * normalize(klax, 1) + hum + air, 0.55)


def music_lifecycle():
    """Good ending: hopeful major-key version of the theme."""
    C = [48, 55, 60, 64, 67]
    G = [43, 50, 55, 59, 62, 67]
    Am = [45, 52, 57, 60, 64]
    F = [41, 48, 53, 57, 60, 65]
    Em = [40, 47, 52, 55, 59]
    return render_track([C, G, Am, F, C, Em, F, G], bpm=72, bars_per_chord=2, seed=300, hats_from_bar=4, pad_cutoff=1800)


# --------------------------------------------------------------------------
# Music (stereo 44.1 kHz, seamless)
# --------------------------------------------------------------------------
def reverb(stereo, sr, length=3.0, decay=1.1, wet=0.28, seed=90):
    n = stereo.shape[1]
    m = int(length * sr)
    out = np.zeros((2, n + m))
    for ch in range(2):
        ir = noise(m, seed + ch) * np.exp(-np.arange(m) / sr / decay)
        ir = lowpass(ir, sr, 5000)
        ir /= np.sqrt(np.sum(ir ** 2))
        size = 1 << int(np.ceil(np.log2(n + m)))
        wet_sig = np.fft.irfft(np.fft.rfft(stereo[ch], size) * np.fft.rfft(ir, size), size)[: n + m]
        out[ch, :n] += stereo[ch] * (1 - wet)
        out[ch] += wet_sig * wet
    return out


def pingpong(mono, sr, delay, fb=0.45, taps=6):
    n = len(mono)
    d = int(delay * sr)
    out = np.zeros((2, n + d * taps))
    out[0, :n] += mono
    out[1, :n] += mono
    for k in range(1, taps + 1):
        ch = k % 2
        out[ch, k * d:k * d + n] += mono * fb ** k
    return out


def pad_chord(notes, dur, sr, seed, attack=1.4, release=2.0, detune_cents=8):
    n = int((dur + release) * sr)
    out = np.zeros((2, n))
    r = rng(seed)
    for m in notes:
        for v, cents in enumerate((-detune_cents, 0, detune_cents)):
            f = midi(m) * 2 ** (cents / 1200)
            wave_ = osc(f, n=n, sr=sr, shape="saw", phase=r.uniform())
            pan = 0.5 + (v - 1) * 0.35
            out[0] += wave_ * (1 - pan)
            out[1] += wave_ * pan
    e = env_ar(n, attack, release, sr, hold=dur - attack)
    return out * e / (len(notes) * 3)


def bell(freq, dur, sr):
    t = t_axis(dur, sr)
    mod = np.sin(2 * np.pi * freq * 3.5 * t) * 2.0 * np.exp(-t / 0.15)
    return np.sin(2 * np.pi * freq * t + mod) * np.exp(-t / 0.5)


def render_track(chords, bpm, bars_per_chord, seed, sub=True, bells=True, hats_from_bar=None,
                 pad_cutoff=1300, extra=None, sr=SR):
    beat = 60.0 / bpm
    bar = beat * 4
    chord_len = bar * bars_per_chord
    loop_len = chord_len * len(chords)
    loop_n = int(round(loop_len * sr))
    tail = 6.0
    total = loop_n + int(tail * sr)
    mix = np.zeros((2, total))
    r = rng(seed)

    pad = np.zeros((2, total))
    for i, notes in enumerate(chords):
        seg = pad_chord(notes, chord_len + 0.6, sr, seed + i)
        start = int(round(i * chord_len * sr))
        end = min(total, start + seg.shape[1])
        pad[:, start:end] += seg[:, : end - start]
    for ch in range(2):
        pad[ch] = lowpass(pad[ch], sr, pad_cutoff, order=2)
    mix += 0.9 * pad

    if sub:
        bass = np.zeros(total)
        for i, notes in enumerate(chords):
            root = min(notes)
            while root > 40:
                root -= 12
            seg_n = int((chord_len + 1.0) * sr)
            seg = osc(midi(root), n=seg_n, sr=sr) * env_ar(seg_n, 0.4, 1.0, sr, hold=chord_len - 0.4)
            place(bass, seg, i * chord_len, sr)
        mix += 0.22 * np.stack([bass, bass])

    if bells:
        mono = np.zeros(total)
        eighth = beat / 2
        steps = int(loop_len / eighth)
        for s in range(steps):
            if r.random() < 0.22:
                ci = int((s * eighth) // chord_len)
                notes = sorted(chords[ci])
                m = notes[int(r.integers(1, len(notes)))] + 12
                while m < 72:
                    m += 12
                place(mono, bell(midi(m), 1.6, sr), s * eighth, sr, gain=r.uniform(0.5, 1.0))
        bell_st = pingpong(mono, sr, beat * 0.75, 0.42)
        mix[:, : min(total, bell_st.shape[1])] += 0.09 * bell_st[:, :total]

    if hats_from_bar is not None:
        mono = np.zeros(total)
        eighth = beat / 2
        for s in range(int(hats_from_bar * 8), int(loop_len / eighth)):
            if s % 2 == 1:
                place(mono, tick(0.04, sr, 1000 + s, 6000, 14000, 0.008), s * eighth, sr, gain=r.uniform(0.6, 1.0))
        mix += 0.035 * np.stack([mono * 0.8, mono])

    if extra is not None:
        mix += extra(total, loop_len, beat, sr, r)

    hiss = 0.006 * normalize(highpass(pink(total, seed + 7, sr), sr, 4000), 1)
    mix += np.stack([hiss, np.roll(hiss, 997)])

    wet = reverb(mix, sr)
    looped = fold_loop(wet, loop_n)
    looped = soft_clip(normalize(looped, 0.9), 1.2)
    return normalize(looped, 0.8)


def music_complex():
    """Main exploration theme: slow A-minor pad, sub bass, sparse delayed bells."""
    Am = [45, 52, 57, 60, 64]
    F = [41, 48, 53, 57, 60, 64]
    Dm = [38, 45, 50, 53, 57, 60]
    E = [40, 47, 52, 56, 59, 62]
    G = [43, 50, 55, 59, 62]
    return render_track([Am, F, Dm, E, Am, F, G, E], bpm=66, bars_per_chord=2, seed=100, hats_from_bar=8)


def music_core():
    """Final room: darker, slower, dissonant, with a heartbeat pulse."""
    Dm = [38, 45, 50, 53, 57]
    Bb = [34, 46, 50, 53, 58]
    Gm = [43, 50, 55, 58, 62]
    Aflat9 = [45, 52, 55, 58, 61]  # A7(b9) tension

    def heartbeat(total, loop_len, beat, sr, r):
        mono = np.zeros(total)
        for b in range(int(loop_len / beat)):
            if b % 2 == 0:
                place(mono, thump(0.35, 75, 42, 0.07, sr), b * beat, sr)
                place(mono, thump(0.35, 75, 42, 0.07, sr), b * beat + 0.26, sr, gain=0.6)
        blips = np.zeros(total)
        for _ in range(14):
            at = r.uniform(0, loop_len)
            seg = osc(r.choice([midi(86), midi(89), midi(93)]), 0.06, sr, "square") * env_exp(int(0.06 * sr), 0.015, sr)
            place(blips, lowpass(seg, sr, 4000), at, sr, gain=r.uniform(0.3, 0.7))
        bl = pingpong(blips, sr, beat * 0.5, 0.5)[:, :total]
        return 0.35 * np.stack([mono, mono]) + 0.05 * bl

    return render_track([Dm, Bb, Gm, Aflat9], bpm=54, bars_per_chord=2, seed=200, bells=False,
                        pad_cutoff=900, extra=heartbeat)


# --------------------------------------------------------------------------
def main():
    print("Generating REWIND.exe audio...")
    sfx = {
        "ui_hover": sfx_hover, "ui_click": sfx_click, "terminal_type": sfx_type,
        "terminal_open": sfx_terminal_open, "terminal_close": sfx_terminal_close,
        "terminal_accept": sfx_accept, "terminal_error": sfx_error,
        "door_open": sfx_door_open, "door_locked": sfx_door_locked, "door_unlock": sfx_door_unlock,
        "room_transition": sfx_room_transition, "paper": sfx_paper,
        "tape_rec_start": sfx_rec_start, "tape_rec_stop": sfx_rec_stop, "tape_rewind": sfx_rewind,
        "voice_operator": sfx_voice_operator, "voice_system": sfx_voice_system,
        "blast_door": sfx_blast_door, "power_up": sfx_power_up, "glitch": sfx_glitch,
        "power_down": sfx_power_down, "countdown_beep": sfx_countdown_beep, "nuke": sfx_nuke,
    }
    for name, fn in sfx.items():
        write(f"SFX/{name}.wav", fn())
    for name, fn in (("amb_control_room", amb_control_room), ("amb_archive", amb_archive),
                     ("amb_generator", amb_generator), ("amb_core", amb_core), ("amb_wind", amb_wind), ("amb_alarm", amb_alarm)):
        write(f"Ambience/{name}.wav", fn(), ASR)
    write("Music/music_complex.wav", music_complex())
    write("Music/music_core.wav", music_core())
    write("Music/music_lifecycle.wav", music_lifecycle())
    if "--stats" in sys.argv:
        print("\nfile                                        dur    peak   rms   seam/p99 (loops: <1 = seamless)")
        for rel, d, pk, rms, seam in STATS:
            print(f"{rel:42s} {d:6.2f} {pk:6.2f} {rms:6.3f} {seam:8.2f}")


if __name__ == "__main__":
    main()
