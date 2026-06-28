# PiezoMic

A DIY piezoelectric microphone built from scratch — from analog circuit design to digital signal processing.

![Microphone Build](docs/microphone_build.jpeg)

## What is this?

A contact microphone built from a salvaged piezo disc, a plastic cup, and a nitrile glove membrane — connected to an ESP32 through a custom two-stage BJT amplifier circuit. The system captures speech at 16kHz and streams it to a PC over USB serial, where a Python-based DSP pipeline cleans up the audio through a multi-stage filter chain (mains-hum removal, background-noise reduction, and band-limiting to the speech range).

## System Architecture

```
Piezo Disc → BJT Amplifier (2-stage) → ESP32 ADC (I2S DMA) → USB Serial → Python Recorder → DSP Filter Chain → WAV
```

**Analog stage:** Emitter follower (high-impedance buffer) → AC-coupled common-emitter amplifier, both using 2N2222 transistors. Powered from 3.3V with voltage divider biasing. The circuit was designed and simulated in LTSpice before breadboard assembly.

**Digital stage:** The ESP32 samples at 64kHz using I2S-driven ADC with DMA, applies 4x decimation (averaging) to produce a 16kHz output stream, and sends data blocks over serial at 921600 baud with a sync protocol (0xAA 0x55 header + block size).

**DSP pipeline (Python):**
1. High-pass filter (100Hz, 4th order Butterworth) — removes mechanical vibration
2. Notch filters (50Hz + harmonics) — removes Israeli power line interference
3. Spectral subtraction — estimates and removes stationary background noise
4. Presence boost (2kHz, gentle peak) — improves speech intelligibility
5. Low-pass filter (4kHz) — removes out-of-band noise

## Results

The recorded speech is clearly intelligible. The DSP chain noticeably reduces background hiss and mains hum — the effect is audible in the before/after samples below, and visible in the spectrum and spectrogram, where high-frequency noise and the 50Hz line components are attenuated while the speech band (roughly 100Hz–4kHz) is preserved.

![Audio Enhancement - Full Chain](docs/full_chain.png)

### Audio Samples

- [`samples/raw_recording.wav`](samples/raw_recording.wav) — raw capture from ESP32, no processing
- [`samples/filtered_recording.wav`](samples/filtered_recording.wav) — after full DSP chain

## Hardware

### Circuit Schematic

![Schematic](docs/schematic.jpeg)

Two-stage BJT amplifier using 2N2222 transistors:
- **Stage 1 — Emitter Follower:** High input impedance (~1MΩ) to avoid loading the piezo crystal. Unity voltage gain, low output impedance.
- **Stage 2 — Common Emitter:** Voltage amplification with biasing via voltage divider (R5=28.85K, R7=1.524K). AC-coupled from buffer stage through 10µF capacitor.
- **Output:** RC low-pass filter (R9=1K, C5=10nF) before ADC input, with DC bias at ~1.65V for mid-range ADC operation.

> Note: this is a breadboard prototype using 2N2222 transistors. On breadboard the front-end picks up significant environmental noise and the achievable gain is limited; the digital filter chain compensates for much of this. A cleaner op-amp-based front-end on a PCB is a natural next step.

### Simulation Results

| | |
|---|---|
| ![Frequency Response](docs/frequency_response.jpeg) | ![Time Domain](docs/time_domain_simulation.jpeg) |
| Bode plot — gain and phase response | Transient simulation — signal at each node |

### Bill of Materials

| Component | Value | Role |
|-----------|-------|------|
| Piezo disc | Salvaged | Transducer |
| 2N2222 (×2) | NPN BJT | Buffer + Amplifier |
| R1 | 220Ω | Power supply decoupling |
| R2 | 10KΩ | Emitter follower load |
| R3 | 1MΩ | Buffer base bias |
| R4 | 1MΩ | Buffer base bias |
| R5 | 28.85KΩ | Amplifier bias divider (top) |
| R6 | 10KΩ | Amplifier bias divider (bottom) |
| R7 | 1.524KΩ | Collector resistor |
| R8 | 100Ω | Emitter degeneration |
| R9 | 1KΩ | Output filter |
| C1 | 10µF | Power supply filter |
| C2 | 10nF | Power supply HF bypass |
| C3 | 10nF | Input AC coupling |
| C4 | 10µF | Inter-stage AC coupling |
| C5 | 10nF | Output low-pass filter |

### Physical Build

The microphone housing is a plastic cup with a nitrile glove stretched over the opening as a membrane (held tight with rubber bands). The piezo disc sits underneath the membrane, and the leads are shielded with aluminum foil to reduce electromagnetic interference.

## Project Structure

```
PiezoMic/
├── README.md
├── firmware/
│   ├── piezo_mic_esp32_V1.ino   # ESP32 firmware (I2S ADC + serial streaming)
│   └── esp32_recorder.py        # Python receiver with live waveform + FFT display
├── scripts/
│   └── audio_filters.py         # DSP filter chain (HP → Notch → Spectral Sub → Boost → LP)
├── samples/
│   ├── raw_recording.wav        # Raw capture from ESP32
│   └── filtered_recording.wav   # After full DSP pipeline
├── hardware/
│   └── amplifier_circuit.asc    # LTSpice schematic (open with LTSpice)
└── docs/
    ├── microphone_build.jpeg    # Photo of the physical microphone
    ├── schematic.jpeg           # Circuit schematic
    ├── frequency_response.jpeg  # Bode plot from simulation
    ├── time_domain_simulation.jpeg
    ├── noise_analysis.png       # Noise spectrum analysis
    ├── audio_analysis.png       # Waveform, spectrogram, PSD
    └── full_chain.png           # Before/after PSD, waveform and spectrogram
```

## Requirements

### Hardware
- ESP32 development board
- Piezo disc (any salvaged buzzer element works)
- 2× 2N2222 NPN transistors
- Resistors and capacitors (see BOM above)
- Breadboard + jumper wires
- USB cable

### Software
- [Arduino IDE](https://www.arduino.cc/en/software) or PlatformIO (for ESP32 firmware)
- Python 3.8+
- [LTSpice](https://www.analog.com/en/resources/design-tools-and-calculators/ltspice-simulator.html) (optional, for circuit simulation)

```bash
pip install pyserial numpy matplotlib scipy
```

## Usage

1. Flash `firmware/piezo_mic_esp32_V1.ino` to your ESP32
2. Run the recorder:
   ```bash
   python firmware/esp32_recorder.py
   ```
3. Speak into the microphone — you'll see live waveform and FFT
4. Close the plot window to stop and save the WAV file
5. Apply the filter chain:
   ```bash
   python scripts/audio_filters.py samples/raw_recording.wav samples/filtered_recording.wav
   ```

## Analysis

### Noise Characterization

![Noise Analysis](docs/noise_analysis.png)

### Raw Audio Analysis

![Audio Analysis](docs/audio_analysis.png)

## License

MIT

## Author

Nir Sabbah
