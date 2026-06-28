#!/usr/bin/env python3
"""
make_full_chain.py
Regenerates docs/full_chain.png from the raw and filtered recordings.
Shows three honest, data-derived panels — no SNR claims:
  1. PSD (raw vs filtered)  — shows noise attenuation
  2. Waveform (filtered)    — shows the captured speech
  3. Spectrogram (filtered) — shows the speech structure

Usage:
    python make_full_chain.py raw_recording.wav filtered_recording.wav full_chain.png
"""

import sys
import numpy as np
from scipy.io import wavfile
from scipy import signal
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec


def load(path):
    sr, d = wavfile.read(path)
    if d.ndim > 1:
        d = d[:, 0]
    d = d.astype(np.float64)
    d /= (np.max(np.abs(d)) + 1e-12)   # normalize to ±1 for fair comparison
    return sr, d


def main():
    raw_path  = sys.argv[1] if len(sys.argv) > 1 else "raw.wav"
    filt_path = sys.argv[2] if len(sys.argv) > 2 else "filtered.wav"
    out_path  = sys.argv[3] if len(sys.argv) > 3 else "full_chain.png"

    sr, raw  = load(raw_path)
    _,  filt = load(filt_path)

    # --- dark theme to match the existing repo figures ---
    plt.rcParams.update({
        "figure.facecolor":  "#0f0f23",
        "axes.facecolor":    "#0f0f23",
        "savefig.facecolor": "#0f0f23",
        "text.color":        "white",
        "axes.labelcolor":   "white",
        "axes.edgecolor":    "#333333",
        "xtick.color":       "white",
        "ytick.color":       "white",
        "font.size":         10,
    })

    fig = plt.figure(figsize=(13, 8))
    gs  = GridSpec(2, 2, figure=fig, hspace=0.35, wspace=0.25)
    fig.suptitle("Audio Enhancement — Full Chain", fontsize=15, fontweight="bold", color="white")

    # ---------- 1. PSD: raw vs filtered ----------
    ax1 = fig.add_subplot(gs[0, 0])
    f_raw,  p_raw  = signal.welch(raw,  fs=sr, nperseg=2048)
    f_filt, p_filt = signal.welch(filt, fs=sr, nperseg=2048)
    ax1.semilogy  # keep linear-dB instead
    ax1.plot(f_raw,  10*np.log10(p_raw  + 1e-12), color="#ff5b5b", lw=1.0, label="Raw")
    ax1.plot(f_filt, 10*np.log10(p_filt + 1e-12), color="#00e676", lw=1.0, label="Filtered (full chain)")
    ax1.axvspan(100, 4000, color="#00e676", alpha=0.06)  # speech band marker
    ax1.set_title("PSD — Raw vs Filtered", color="white")
    ax1.set_xlabel("Frequency (Hz)")
    ax1.set_ylabel("Power (dB)")
    ax1.set_xlim(0, sr/2)
    ax1.grid(True, alpha=0.2)
    leg = ax1.legend(facecolor="#1a1a2e", edgecolor="#333333", labelcolor="white", fontsize=8)

    # ---------- 2. Waveform (filtered) ----------
    ax2 = fig.add_subplot(gs[0, 1])
    t = np.arange(len(filt)) / sr
    ax2.plot(t, filt, color="#00e676", lw=0.5)
    ax2.set_title("Waveform — Filtered", color="white")
    ax2.set_xlabel("Time (s)")
    ax2.set_ylabel("Amplitude")
    ax2.set_xlim(0, t[-1])
    ax2.grid(True, alpha=0.2)

    # ---------- 3. Spectrogram (filtered) ----------
    ax3 = fig.add_subplot(gs[1, :])
    f_s, t_s, Sxx = signal.spectrogram(filt, fs=sr, nperseg=512, noverlap=384)
    Sxx_db = 10*np.log10(Sxx + 1e-12)
    pcm = ax3.pcolormesh(t_s, f_s, Sxx_db, shading="gouraud", cmap="magma",
                         vmin=np.percentile(Sxx_db, 5), vmax=np.percentile(Sxx_db, 99))
    ax3.set_title("Spectrogram — Filtered", color="white")
    ax3.set_xlabel("Time (s)")
    ax3.set_ylabel("Frequency (Hz)")
    ax3.set_ylim(0, sr/2)
    cb = fig.colorbar(pcm, ax=ax3, pad=0.01)
    cb.set_label("Power (dB)", color="white")
    cb.ax.yaxis.set_tick_params(color="white")
    plt.setp(plt.getp(cb.ax.axes, "yticklabels"), color="white")

    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()
