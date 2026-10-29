"""Build the numeric ROM-preset fit catalog from the pinned optional oracle.

Developer utility only; conversion does not import numpy or load an emulator.
No source music, ROM bytes or private waveform is stored in the catalog.
"""
import argparse
import json
from pathlib import Path

from musical_vgm_reference import Core, COMMIT

CLOCK = 3579545


def build():
    import numpy as np
    rows = []
    for preset in range(1, 16):
        profiles = []
        for block in (3, 4, 5):
            core = Core('opll', CLOCK)
            try:
                core.write(0, 0x30, preset << 4)
                core.write(0, 0x10, 290 & 255)
                core.write(0, 0x20, 0x30 | (block << 1) | (290 >> 8))
                audio = np.asarray(core.render(88200)[0], dtype=float)
            finally:
                core.close()
            hz = CLOCK * 290 * 2 ** block / (72 * 2 ** 19)
            spectrum = []
            for start in (22050, 66150):
                section = audio[start:start + 16384]
                window = np.hanning(len(section))
                fft = abs(np.fft.rfft((section - section.mean()) * window))
                # Local-bin maxima tolerate the independent core's pitch grid.
                spectrum.append([float(max(fft[max(1, round(hz * h * len(section) / 44100) - 2):
                    round(hz * h * len(section) / 44100) + 3], default=0)) for h in range(1, 17)])
            harmonics = np.mean(spectrum, axis=0)
            harmonics /= max(float(np.linalg.norm(harmonics)), 1e-20)
            early = float(np.sqrt(np.mean(audio[22050:44100] ** 2)))
            late = float(np.sqrt(np.mean(audio[66150:88200] ** 2)))
            profiles.append(dict(block=block, frequency_hz=hz,
                harmonics=[round(float(v), 8) for v in harmonics],
                early_rms=round(early, 5), late_rms=round(late, 5),
                sustain_ratio=round(late / max(early, 1e-20), 6)))
        rows.append(dict(preset=preset, profiles=profiles))
    core = Core('scc', CLOCK // 2)
    try:
        for i in range(32):core.write(0, i, (128 if i < 16 else 120))
        core.write(1, 0, 253);core.write(1, 1, 0)
        core.write(2, 0, 15);core.write(3, 0, 1)
        audio = np.asarray(core.render(core.rate)[0], dtype=float)
        scc_scale = float(np.std(audio)) / 124
    finally:
        core.close()
    return dict(schema=1, reference_commit=COMMIT, clock_hz=CLOCK,
        scc_rms_per_wave_unit=round(scc_scale, 8),
        method='ROM1..15; key+sustain; fnum290; blocks3/4/5; two settled harmonic windows',
        limitations=['Amplitude-spectrum fit only; phase and transient shape differ',
                    'Reference mixer RMS is not a hardware gain calibration'], presets=rows)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(build(), indent=2) + '\n', encoding='utf-8')
