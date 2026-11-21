"""OPLL percussion events rendered as target PCM assets.

On PCM-capable cartridge compositions (Makoto ADPCM-B, MSX-Audio
Delta-T, and the layered / SFG01+Makoto combinations) OPLL rhythm
is played as PCM, per the owner's direction (2026-11-14).  The
hit library in data/presets/rhythm_pcm/ holds single hits rendered
by IKAOPLL at reference oscillator pitches and maximum level;
each percussion event becomes one NativePCM asset whose rate
tracks the song's rhythm-oscillator pitch for the family's
channel and whose amplitude tracks the event level (OPLL level
steps of 3.01 dB).  Assets are built at the projection boundary
only; the source performance is never modified.  The generic
PCM projector mixes overlaps into the cartridge's single
Delta-T voice and deduplicates repeated hits by content.
"""
from array import array
from collections import Counter
import json
import math
from pathlib import Path
import wave

from musical_wave_target import curve_value
from native_music import NativePCM

_PRESETS = Path(__file__).resolve().parent.parent / 'data' / 'presets'
_LIBS = {'ika': _PRESETS / 'rhythm_pcm',
        'rx21': _PRESETS / 'rhythm_pcm_rx21'}
_cache = {}
_PITCH_CHANNEL = {'BD': 7, 'SD': 6, 'TOM': 8, 'HH': 6, 'CYM': 8}
_FAMILY_MAP = {'BD': 'BD', 'SD': 'SD', 'HH': 'CLOSEHH', 'CYM': 'CYM'}


def _library(name='ika'):
    if name not in _cache:
        lib = _LIBS[name]
        manifest = json.loads((lib / 'manifest.json').read_text())
        hits = {}
        for family, entry in manifest['families'].items():
            with wave.open(str(lib / entry['file'])) as w:
                samples = array('h')
                samples.frombytes(w.readframes(w.getnframes()))
            hits[family] = tuple(samples)
        # Uniform staging: the IKAOPLL renders peak near -32 dBFS,
        # which left the cartridge PCM voice ~29 dB under the FM
        # lanes on real hardware (owner's FMPAC02 recordings,
        # 2026-11-14).  One gain per library preserves the
        # inter-family balance; the loudest hit sits at -1 dBFS
        # (render-checked against the native balance, 2026-11-14).
        peak = max(abs(v) for samples in hits.values() for v in samples)
        gain = (10 ** (-1.0 / 20) * 32767) / peak if peak else 1.0
        if abs(gain - 1.0) > 0.01:
            hits = {family: tuple(
                max(-32768, min(32767, round(v * gain))) for v in samples)
                for family, samples in hits.items()}
        _cache[name] = (manifest, hits)
    return _cache[name]


def _pitch_at(performance, device):
    """(sample -> {channel: Hz}) snapshots from pitch controls."""
    from native_registers import encode_control
    registers = {}
    snapshots = []
    controls = sorted(
        (c for c in performance.controls
         if c.device_id == device.device_id
         and c.kind in ('opll_pitch_low', 'opll_pitch_high')),
        key=lambda c: (c.sample, c.order))
    for c in controls:
        register = dict(c.parameters)['register']
        registers[register] = encode_control(c, device)[2]
        hz = {}
        for ch in (6, 7, 8):
            lo, hi = registers.get(0x10 + ch), registers.get(0x20 + ch)
            if lo is None or hi is None:
                continue
            fnum = lo | ((hi & 1) << 8)
            block = (hi >> 1) & 7
            hz[ch] = device.clock_hz / 72 * fnum * 2 ** block / 2 ** 19
        snapshots.append((c.sample, hz))
    return snapshots


def build_rhythm_pcm_assets(performance, library='ika', *,
                            soundcore_levels=False):
    """Derived NativePCM assets for the first OPLL device's rhythm.

    Returns (assets, losses); empty when the performance has no
    OPLL percussion.  library='ika' plays the IKAOPLL hit library;
    library='rx21' plays the owner's RX21 recordings instead
    (HH -> CLOSEHH; TOM -> the sample whose dominant pitch is
    nearest the event's, with a residual rate ratio).
    """
    devices = [d for d in performance.devices if d.chip == 'opll']
    if not devices:
        return (), Counter()
    device = devices[0]
    events = [e for e in performance.percussion
              if e.device_id == device.device_id]
    if not events:
        return (), Counter()
    manifest, hits = _library(library)
    rate = manifest['rate_hz']
    snapshots = _pitch_at(performance, device)
    losses = Counter()
    assets = []
    raw = []
    for index, event in enumerate(events):
        family = event.instrument_family
        hit_key = family if library == 'ika' else _FAMILY_MAP.get(family)
        if family == 'TOM' and library == 'rx21':
            hit_key = 'TOM'  # resolved per event below
        if hit_key is None or (hit_key not in hits and hit_key != 'TOM'):
            losses['opll_rhythm_pcm_unsupported_family'] += 1
            continue
        # Measured on IKAOPLL (2026-11-14): of the five rhythm
        # instruments only the TOM tracks its oscillator pitch
        # (dominant peak 211 -> 1274 Hz across the ch8 sweep);
        # BD stays waveform-identical and the noise instruments
        # keep their spectrum across pitch and instrument-select
        # changes, so their hits are fixed timbres played at
        # timing and level only, as the owner predicted.
        ratio = 1.0
        if family == 'TOM':
            hz = None
            for sample, state in snapshots:
                if sample > event.start_sample:
                    break
                hz = state.get(_PITCH_CHANNEL[family], hz)
            if library == 'ika':
                ref = manifest['families'][family]['ref_hz']
                if hz is None or hz <= 0:
                    losses['opll_rhythm_pcm_pitch_unknown'] += 1
                else:
                    ratio = hz / ref
                    if not 0.25 <= ratio <= 4.0:
                        ratio = max(0.25, min(4.0, ratio))
                        losses['opll_rhythm_pcm_pitch_ratio_clamped'] += 1
            else:
                osc_ref = manifest['opll_tom_osc_hz']
                if hz is None or hz <= 0:
                    losses['opll_rhythm_pcm_pitch_unknown'] += 1
                    hit_key = 'TOM2'
                else:
                    dominant = manifest['opll_tom_nominal_hz'] * hz / osc_ref
                    doms = manifest['tom_dominant_hz']
                    hit_key = min(doms, key=lambda n: abs(
                        math.log2(dominant / doms[n])))
                    ratio = dominant / doms[hit_key]
                    if not 0.5 <= ratio <= 2.0:
                        ratio = max(0.5, min(2.0, ratio))
                        losses['opll_rhythm_pcm_pitch_ratio_clamped'] += 1
        level = curve_value(event.volume_curve, event.start_sample)
        if level is None:
            level = 0
            losses['opll_rhythm_pcm_level_unknown'] += 1
        gain = 10 ** (-3.01 * max(0, min(15, int(level))) / 20)
        if soundcore_levels:
            # SoundCore level mode (owner's decisions, 2026-11-21):
            # the PCM rhythm drops to the same working level as
            # the other SoundCore-anchored lanes (about -22.5 dB).
            gain *= 10 ** (-22.5 / 20)
        samples = tuple(max(-32768, min(32767, round(v * gain)))
                        for v in hits[hit_key])
        raw.append((event.start_sample, rate * ratio, samples,
                    family if library == 'ika' else hit_key))
    # One Delta-T voice: simultaneous hits are mixed into one asset;
    # a later hit cuts the tail of the one still playing (the OPLL
    # retrigger restarts its own envelope the same way).  Keeping
    # hits as separate assets lets the PCM projector deduplicate
    # repeated hits instead of encoding the silences between them.
    by_start = {}
    for start, asset_rate, samples, family in raw:
        by_start.setdefault(start, []).append((asset_rate, samples, family))
    hits_out = []
    for start in sorted(by_start):
        group = by_start[start]
        if len(group) == 1:
            asset_rate, samples, family = group[0]
            hits_out.append((start, asset_rate, samples,
                             f'{family}'))
            continue
        losses['opll_rhythm_pcm_simultaneous_mixed'] += len(group) - 1
        asset_rate = max(g[0] for g in group)
        count = max(math.ceil(len(g[1]) * asset_rate / g[0]) for g in group)
        mixed = [0] * count
        for other_rate, samples, family in group:
            for i in range(count):
                pos = i * other_rate / asset_rate
                left = min(len(samples) - 1, int(pos))
                right = min(left + 1, len(samples) - 1)
                mixed[i] += round(samples[left] * (1 - (pos - int(pos)))
                                  + samples[right] * (pos - int(pos)))
        peak = max((abs(v) for v in mixed), default=0)
        if peak > 32767:
            # Scale the whole mix to fit instead of hard-clamping
            # individual samples (the RX21 mixes clipped audibly).
            scale = 32767 / peak
            mixed = [round(v * scale) for v in mixed]
            losses['opll_rhythm_pcm_mix_normalized'] += 1
        hits_out.append((start, asset_rate, tuple(mixed),
                         '+'.join(sorted(g[2] for g in group))))
    for i, (start, asset_rate, samples, label) in enumerate(hits_out):
        end = start + math.ceil(len(samples) * 44100 / asset_rate)
        if i + 1 < len(hits_out) and hits_out[i + 1][0] < end:
            keep = math.floor((hits_out[i + 1][0] - start)
                              * asset_rate / 44100)
            if keep < 16:
                losses['opll_rhythm_pcm_hit_cut'] += 1
                continue
            samples = samples[:keep]
            end = hits_out[i + 1][0]
            losses['opll_rhythm_pcm_tail_cut'] += 1
        end = min(performance.end_sample, end)
        assets.append(NativePCM(
            f'opll-rhythm:{device.instance}:{label}:{i}',
            device.device_id, start, end, asset_rate, samples))
    return tuple(assets), losses
