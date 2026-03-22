"""
Piezo Microphone Filter Chain
==============================
מבוסס על הניתוח של ההקלטה הגולמית מה-ESP32.
מיישם את ה-chain שהשיג SNR של ~31dB.

שימוש:
    python piezo_filter.py input.wav output.wav

דרישות:
    pip install numpy scipy
"""

import sys
import numpy as np
from scipy.io import wavfile
from scipy import signal
from scipy.ndimage import uniform_filter1d
import warnings
warnings.filterwarnings('ignore')


def load_audio(path):
    sr, data = wavfile.read(path)
    if data.ndim > 1:
        data = data[:, 0]
    if np.issubdtype(data.dtype, np.integer):
        max_val = np.iinfo(data.dtype).max
    else:
        max_val = 1.0
    return sr, data.astype(np.float64) / max_val


def save_audio(path, sr, data):
    # Normalize to -3dBFS
    peak = np.max(np.abs(data))
    if peak > 0:
        data = data * (10 ** (-3 / 20)) / peak
    out = np.clip(data * 32767, -32768, 32767).astype(np.int16)
    wavfile.write(path, sr, out)


def highpass(audio, sr, cutoff=100, order=4):
    """High-pass filter - מחסל רטט מכני ורעש חשמל"""
    sos = signal.butter(order, cutoff, btype='high', fs=sr, output='sos')
    return signal.sosfilt(sos, audio)


def notch_powerline(audio, sr, fundamental=50, harmonics=3, Q=30):
    """Notch filters על 50Hz והרמוניות - רעש חשמל ישראלי"""
    x = audio.copy()
    for n in range(1, harmonics + 1):
        freq = fundamental * n
        if freq < sr / 2:
            b, a = signal.iirnotch(freq, Q=Q, fs=sr)
            x = signal.lfilter(b, a, x)
    return x


def spectral_subtraction(audio, sr, noise_duration=0.3, alpha=1.5):
    """
    Spectral subtraction - מסיר רעש רקע סטטי.
    מניח שה-noise_duration הראשון הוא שקט (רעש בלבד).
    """
    n_noise = int(noise_duration * sr)
    noise_sample = audio[:n_noise]

    nperseg = 512
    freqs, _, Zxx = signal.stft(audio, sr, nperseg=nperseg)
    _, _, Zxx_noise = signal.stft(noise_sample, sr, nperseg=nperseg)

    noise_mag = np.mean(np.abs(Zxx_noise), axis=1, keepdims=True)
    mag = np.abs(Zxx)
    phase = np.angle(Zxx)

    # Spectral floor: לא נרד מתחת ל-10% של המגנטיד המקורי
    mag_sub = np.maximum(mag - alpha * noise_mag, 0.1 * mag)
    Zxx_clean = mag_sub * np.exp(1j * phase)

    _, audio_clean = signal.istft(Zxx_clean, sr, nperseg=nperseg)
    return audio_clean[:len(audio)]


def presence_boost(audio, sr, center=2000, Q=1.5, gain=0.3):
    """Boost עדין בטווח ה-intelligibility של הדיבור (1k-3kHz)"""
    sos = signal.iirpeak(center, Q=Q, fs=sr)
    boosted = signal.sosfilt(signal.tf2sos(*sos), audio)
    return audio + gain * boosted


def lowpass(audio, sr, cutoff=4000, order=4):
    """Low-pass - שומר רק טווח הדיבור"""
    sos = signal.butter(order, cutoff, btype='low', fs=sr, output='sos')
    return signal.sosfilt(sos, audio)


def compute_snr(audio, sr):
    frame_size = int(sr * 0.02)
    n_frames = len(audio) // frame_size
    frame_rms = np.array([
        np.sqrt(np.mean(audio[i * frame_size:(i + 1) * frame_size] ** 2))
        for i in range(n_frames)
    ])
    noise_floor = np.percentile(frame_rms, 10)
    signal_level = np.percentile(frame_rms, 90)
    return 20 * np.log10((signal_level + 1e-10) / (noise_floor + 1e-10))


def process(audio, sr, verbose=True):
    """
    Full filter chain — אותו chain שהשיג ~31dB SNR.
    """
    if verbose:
        snr_before = compute_snr(audio, sr)
        print(f"SNR לפני עיבוד:  {snr_before:.1f} dB")

    # 1. High-pass 100Hz
    x = highpass(audio, sr, cutoff=100, order=4)
    if verbose: print("✓ High-pass 100Hz")

    # 2. Notch 50Hz + הרמוניות
    x = notch_powerline(x, sr, fundamental=50, harmonics=3, Q=30)
    if verbose: print("✓ Notch 50/100/150Hz")

    # 3. Spectral subtraction
    x = spectral_subtraction(x, sr, noise_duration=0.3, alpha=1.5)
    if verbose: print("✓ Spectral subtraction")

    # 4. Presence boost
    x = presence_boost(x, sr, center=2000, Q=1.5, gain=0.3)
    if verbose: print("✓ Presence boost 2kHz")

    # 5. Low-pass 4kHz
    x = lowpass(x, sr, cutoff=4000, order=4)
    if verbose: print("✓ Low-pass 4kHz")

    if verbose:
        snr_after = compute_snr(x, sr)
        print(f"SNR אחרי עיבוד: {snr_after:.1f} dB")
        print(f"שיפור:          +{snr_after - snr_before:.1f} dB")

    return x


def main():
    if len(sys.argv) < 3:
        print("שימוש: python piezo_filter.py input.wav output.wav")
        print("דוגמה: python piezo_filter.py ESP_RAW.wav ESP_filtered.wav")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2]

    print(f"\nטוען: {input_path}")
    sr, audio = load_audio(input_path)
    print(f"Sample rate: {sr}Hz | אורך: {len(audio)/sr:.1f}s\n")

    filtered = process(audio, sr)

    save_audio(output_path, sr, filtered)
    print(f"\nנשמר: {output_path}")


if __name__ == "__main__":
    main()
