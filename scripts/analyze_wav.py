"""Compare PCM WAVs with explicit metrics, not a perceptual quality score.

Requires numpy; --plot additionally requires matplotlib. Render compared VGMs
with the same external emulator, sample rate, loop count and fade settings.
"""
import argparse
import csv
import json
import math
from pathlib import Path
import wave

import numpy as np


def read_pcm(path):
    with wave.open(str(path), 'rb') as f:
        rate, channels, width = f.getframerate(), f.getnchannels(), f.getsampwidth()
        raw = f.readframes(f.getnframes())
    if width == 1:
        samples = (np.frombuffer(raw, dtype=np.uint8).astype(float) - 128) / 128
    elif width in (2, 4):
        samples = np.frombuffer(raw, dtype='<i' + str(width)).astype(float) / (2 ** (8 * width - 1))
    elif width == 3:
        b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        v = b[:, 0] | b[:, 1] << 8 | b[:, 2] << 16
        v = (v ^ 0x800000) - 0x800000
        samples = v.astype(float) / 8388608
    else:
        raise ValueError('Only integer PCM WAV (8/16/24/32 bit) is supported')
    return rate, samples.reshape(-1, channels), width


def db(value):
    return 20 * math.log10(value) if value > 0 else None


def analyze(samples, rate, width, fft_size=4096):
    if len(samples) < fft_size:
        raise ValueError('Selected interval is shorter than one FFT frame')
    if fft_size < 16 or fft_size & (fft_size - 1):
        raise ValueError('FFT size must be a power of two, at least 16')
    window = np.hanning(fft_size)
    hop = fft_size // 4
    spectra, levels = [], []
    for start in range(0, len(samples) - fft_size + 1, hop):
        frame = samples[start:start + fft_size]
        levels.append(float(np.sqrt(np.mean(frame ** 2))))
        # Average channel POWER, avoiding cancellation from stereo phase differences.
        centered = frame - frame.mean(axis=0)
        spectrum = np.abs(np.fft.rfft(centered * window[:, None], axis=0)) ** 2
        power = spectrum.mean(axis=1) / (rate * np.sum(window ** 2))
        power[1:-1] *= 2
        spectra.append(power)
    psd = np.mean(spectra, axis=0)
    frequency = np.fft.rfftfreq(fft_size, 1 / rate)
    energy = psd.sum()
    centroid = float(np.sum(frequency * psd) / energy) if energy > 0 else None
    rolloff = float(frequency[np.searchsorted(np.cumsum(psd), .95 * energy)]) if energy > 0 else None
    rms = float(np.sqrt(np.mean(samples ** 2)))
    ac = samples - samples.mean(axis=0)
    stats = dict(sample_rate=rate, channels=samples.shape[1], frames=len(samples),
                 duration_seconds=len(samples) / rate, fft_size=fft_size, hop=hop,
                 bin_hz=rate / fft_size, spectrum_frames=len(spectra),
                 rms_dbfs=db(rms), ac_rms_dbfs=db(float(np.sqrt(np.mean(ac ** 2)))),
                 peak_dbfs=db(float(np.max(np.abs(samples)))),
                 full_scale_samples=int(np.sum(np.abs(samples) >= 1 - 1 / (2 ** (width * 8 - 1)))),
                 spectral_centroid_hz=centroid, spectral_rolloff95_hz=rolloff,
                 energy_above_4khz_fraction=float(psd[frequency >= 4000].sum() / energy) if energy > 0 else None,
                 dc_per_channel=[float(x) for x in samples.mean(axis=0)])
    return stats, frequency, psd, np.array(levels)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('wav', nargs='+', type=Path)
    parser.add_argument('--outdir', required=True, type=Path)
    parser.add_argument('--start', type=float, default=0)
    parser.add_argument('--end', type=float)
    parser.add_argument('--fft-size', type=int, default=4096)
    parser.add_argument('--plot', action='store_true')
    args = parser.parse_args()
    signals = [read_pcm(p) for p in args.wav]
    if len({r for r, _, _ in signals}) != 1:
        parser.error('Sample rates must match; no implicit resampling is performed')
    end = args.end if args.end is not None else min(len(x) / r for r, x, _ in signals)
    if not 0 <= args.start < end or any(end > len(x) / r for r, x, _ in signals):
        parser.error('Choose one valid shared interval in all WAVs')
    args.outdir.mkdir(parents=True, exist_ok=True)
    rows, curves = [], []
    for index, (path, (rate, samples, width)) in enumerate(zip(args.wav, signals)):
        a, b = round(args.start * rate), round(end * rate)
        stats, frequency, psd, levels = analyze(samples[a:b], rate, width, args.fft_size)
        label = str(index + 1) + '_' + path.stem
        rows.append(dict(file=str(path.resolve()), label=label, start_seconds=a/rate,
                         end_seconds=b/rate, **stats))
        curves.append((label, frequency, psd, levels, rate))
    report = dict(method='Welch mean power, Hann window, 75% overlap, per-frame DC removal, mean channel power',
                  scope='Descriptive metrics only; no alignment, quality ranking or loudness matching', files=rows)
    (args.outdir / 'metrics.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    with (args.outdir / 'metrics.csv').open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    with (args.outdir / 'spectra.csv').open('w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['frequency_hz'] + [x[0] + '_power_per_hz' for x in curves])
        writer.writerows(zip(curves[0][1], *(x[2] for x in curves)))
    if args.plot:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(2, 1, figsize=(10, 7))
        for label, frequency, psd, levels, rate in curves:
            normalized = psd / max(float(psd.sum()), np.finfo(float).tiny)
            axes[0].semilogx(frequency[1:], 10*np.log10(np.maximum(normalized[1:], 1e-15)), label=label)
            times = args.start + (np.arange(len(levels)) * (args.fft_size//4) + args.fft_size/2) / rate
            axes[1].plot(times, 20*np.log10(np.maximum(levels, 1e-15)), label=label)
        axes[0].set(xlabel='Frequency (Hz)', ylabel='dB of total spectral power per bin', xlim=(20, rate/2), ylim=(-100, 0))
        axes[1].set(xlabel='Time (s)', ylabel='Frame RMS (dBFS; display floor -100)', ylim=(-100, 0))
        for ax in axes:
            ax.legend(); ax.grid(True, alpha=.3)
        fig.suptitle('Spectrum shape and original level (no perceptual score)')
        fig.tight_layout(); fig.savefig(args.outdir / 'comparison.png', dpi=150); plt.close(fig)
    print(json.dumps(rows, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
