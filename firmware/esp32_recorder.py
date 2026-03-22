"""
============================================================
Piezo Microphone - Python Receiver V2
============================================================
מקבל אודיו מה-ESP32 דרך Serial ושומר כקובץ WAV
כולל גרף חי של צורת הגל ו-FFT

שימוש:
    python piezo_recorder_v2.py

דרישות:
    pip install pyserial numpy matplotlib
"""

import serial
import serial.tools.list_ports
import numpy as np
import wave
import struct
import time
import sys
import os
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from collections import deque
import threading

# --- הגדרות ---
BAUD_RATE = 921600
SAMPLE_RATE = 16000
SYNC_BYTE_1 = 0xAA
SYNC_BYTE_2 = 0x55

# --- הגדרות גרף ---
DISPLAY_SECONDS = 0.1         # כמה שניות להציג בגרף הגל
DISPLAY_SAMPLES = int(SAMPLE_RATE * DISPLAY_SECONDS)
FFT_SIZE = 2048               # גודל FFT

# --- משתנים גלובליים ---
samples_list = []
total_samples = 0
is_recording = True
display_buffer = deque(maxlen=DISPLAY_SAMPLES)
fft_buffer = deque(maxlen=FFT_SIZE)

# אתחול הבאפר באפסים
for _ in range(DISPLAY_SAMPLES):
    display_buffer.append(0)
for _ in range(FFT_SIZE):
    fft_buffer.append(0)


def find_esp32_port():
    """מחפש אוטומטית את הפורט של ה-ESP32"""
    ports = serial.tools.list_ports.comports()
    esp_keywords = ['CP210', 'CH340', 'CH910', 'SLAB', 'USB Serial', 'ESP32']
    
    for port in ports:
        desc = f"{port.description} {port.manufacturer or ''}"
        for keyword in esp_keywords:
            if keyword.lower() in desc.lower():
                return port.device
    
    if ports:
        print("Available ports:")
        for i, port in enumerate(ports):
            print(f"  [{i}] {port.device} - {port.description}")
        choice = int(input("Select port number: "))
        return ports[choice].device
    
    print("ERROR: No serial ports found!")
    sys.exit(1)


def read_block(ser):
    """קורא בלוק אחד של נתונים מה-ESP32"""
    while True:
        b = ser.read(1)
        if len(b) == 0:
            return None
        if b[0] == SYNC_BYTE_1:
            b2 = ser.read(1)
            if len(b2) > 0 and b2[0] == SYNC_BYTE_2:
                break
    
    size_bytes = ser.read(2)
    if len(size_bytes) < 2:
        return None
    block_size = struct.unpack('<H', size_bytes)[0]
    
    data_bytes = ser.read(block_size * 2)
    if len(data_bytes) < block_size * 2:
        return None
    
    samples = np.frombuffer(data_bytes, dtype=np.uint16)
    
    # --- תיקון ערוץ כפול ---
    # ה-I2S מחזיר כל דגימה פעמיים (LEFT + RIGHT)
    # לוקחים רק כל דגימה שנייה
    samples = samples[::2]
    
    return samples


def serial_reader(ser):
    """Thread שקורא מ-Serial ברקע"""
    global total_samples, is_recording
    
    blocks_received = 0
    start_time = time.time()
    
    while is_recording:
        try:
            block = read_block(ser)
            if block is not None and len(block) > 0:
                samples_list.append(block)
                total_samples += len(block)
                blocks_received += 1
                
                # עדכון באפרים לגרף
                for s in block:
                    display_buffer.append(s)
                    fft_buffer.append(s)
                
                if blocks_received % 100 == 0:
                    elapsed = time.time() - start_time
                    rate = total_samples / elapsed if elapsed > 0 else 0
                    print(f"\r  Recording: {elapsed:.1f}s | "
                          f"Samples: {total_samples} | "
                          f"Rate: {rate:.0f} Hz | "
                          f"Blocks: {blocks_received}", end="")
        except Exception as e:
            if is_recording:
                print(f"\nSerial error: {e}")
            break


def samples_to_wav(samples_list, filename):
    """שומר את הדגימות כקובץ WAV"""
    all_samples = np.concatenate(samples_list).astype(np.float32)
    
    if len(all_samples) == 0:
        print("No samples recorded!")
        return
    
    # הסרת DC offset
    dc_offset = np.mean(all_samples)
    centered = all_samples - dc_offset
    
    # נרמול ל-16-bit
    max_val = np.max(np.abs(centered))
    if max_val > 0:
        normalized = centered / max_val * 32000
    else:
        normalized = centered
    
    wav_samples = normalized.astype(np.int16)
    
    with wave.open(filename, 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(wav_samples.tobytes())
    
    duration = len(wav_samples) / SAMPLE_RATE
    print(f"\nSaved: {filename}")
    print(f"Duration: {duration:.1f} seconds")
    print(f"Samples: {len(wav_samples)}")
    print(f"File size: {os.path.getsize(filename)} bytes")


def main():
    global is_recording
    
    # --- חיבור ---
    port = find_esp32_port()
    print(f"Connecting to {port}...")
    ser = serial.Serial(port, BAUD_RATE, timeout=2)
    time.sleep(2)
    ser.reset_input_buffer()
    print(f"Connected! Recording at {SAMPLE_RATE}Hz...")
    print("Close the plot window or press Ctrl+C to stop and save.\n")
    
    # --- התחלת קריאה ברקע ---
    reader_thread = threading.Thread(target=serial_reader, args=(ser,), daemon=True)
    reader_thread.start()
    
    # --- הגדרת גרפים ---
    fig, (ax_wave, ax_fft) = plt.subplots(2, 1, figsize=(12, 7))
    fig.suptitle('Piezo Microphone - Live', fontsize=14, fontweight='bold')
    
    # גרף גל
    time_axis = np.linspace(0, DISPLAY_SECONDS * 1000, DISPLAY_SAMPLES)  # ms
    line_wave, = ax_wave.plot(time_axis, np.zeros(DISPLAY_SAMPLES), color='#00cc66', linewidth=0.8)
    ax_wave.set_xlim(0, DISPLAY_SECONDS * 1000)
    ax_wave.set_ylim(0, 4095)
    ax_wave.set_xlabel('Time (ms)')
    ax_wave.set_ylabel('ADC Value (12-bit)')
    ax_wave.set_title('Waveform')
    ax_wave.grid(True, alpha=0.3)
    ax_wave.set_facecolor('#1a1a2e')
    
    # גרף FFT
    freq_axis = np.linspace(0, SAMPLE_RATE / 2, FFT_SIZE // 2)
    line_fft, = ax_fft.plot(freq_axis, np.zeros(FFT_SIZE // 2), color='#ff6600', linewidth=0.8)
    ax_fft.set_xlim(0, SAMPLE_RATE / 2)
    ax_fft.set_ylim(0, 60)
    ax_fft.set_xlabel('Frequency (Hz)')
    ax_fft.set_ylabel('Magnitude (dB)')
    ax_fft.set_title('FFT Spectrum')
    ax_fft.grid(True, alpha=0.3)
    ax_fft.set_facecolor('#1a1a2e')
    
    fig.set_facecolor('#0f0f23')
    for ax in [ax_wave, ax_fft]:
        ax.tick_params(colors='white')
        ax.xaxis.label.set_color('white')
        ax.yaxis.label.set_color('white')
        ax.title.set_color('white')
        for spine in ax.spines.values():
            spine.set_color('#333333')
    fig.suptitle('Piezo Microphone - Live', fontsize=14, fontweight='bold', color='white')
    
    plt.tight_layout()
    
    def update(frame):
        """עדכון הגרפים"""
        # עדכון גרף גל
        wave_data = np.array(display_buffer)
        line_wave.set_ydata(wave_data)
        
        # עדכון auto-scale לגרף הגל
        if len(wave_data) > 0:
            wave_min = max(0, np.min(wave_data) - 100)
            wave_max = min(4095, np.max(wave_data) + 100)
            if wave_max - wave_min < 50:
                center = (wave_max + wave_min) / 2
                wave_min = center - 100
                wave_max = center + 100
            ax_wave.set_ylim(wave_min, wave_max)
        
        # עדכון FFT
        fft_data = np.array(fft_buffer, dtype=np.float32)
        # הסרת DC
        fft_data = fft_data - np.mean(fft_data)
        # חלון Hanning למניעת spectral leakage
        window = np.hanning(len(fft_data))
        fft_result = np.fft.rfft(fft_data * window)
        # המרה ל-dB
        magnitude = np.abs(fft_result[:FFT_SIZE // 2])
        magnitude_db = 20 * np.log10(magnitude + 1e-10)  # +epsilon למניעת log(0)
        line_fft.set_ydata(magnitude_db)
        
        # auto-scale FFT
        if np.max(magnitude_db) > 0:
            ax_fft.set_ylim(max(-20, np.min(magnitude_db)), np.max(magnitude_db) + 5)
        
        return line_wave, line_fft
    
    # --- הרצת אנימציה ---
    ani = FuncAnimation(fig, update, interval=50, blit=False, cache_frame_data=False)
    
    try:
        plt.show()
    except KeyboardInterrupt:
        pass
    
    # --- סיום ---
    print("\n\nStopping...")
    is_recording = False
    reader_thread.join(timeout=2)
    ser.close()
    
    if samples_list:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"piezo_recording_{timestamp}.wav"
        samples_to_wav(samples_list, filename)
    else:
        print("No data received.")


if __name__ == "__main__":
    main()
