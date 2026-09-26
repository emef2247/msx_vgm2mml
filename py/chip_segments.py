"""Interpreted PSG/SCC intervals, retaining chip-specific state and evidence.

Zero-length state changes are retained. Timing uses the existing 60 Hz pass
interpretation; ``time`` retains the source CSV timestamp. No repeat compression
or target-length quantization is performed here.
"""
import csv
from dataclasses import asdict, dataclass, fields
import json


@dataclass(frozen=True)
class Segment:
    ev_type: str
    time: float
    ch: int
    ticks: int
    l: int
    tone_period: int
    volume: int
    octave: int
    scale: str
    volume_delta: int
    # Exact analyzed row, including legacy fields not yet given semantic names.
    # Renderers use named fields exclusively; this is diagnostic evidence.
    pass3_row: tuple[str, ...]

    @property
    def tick_start(self):
        return self.ticks

    @property
    def tick_end(self):
        return self.ticks + self.l


@dataclass(frozen=True)
class PsgSegment(Segment):
    mode: int
    noise_period: int
    envelope_enabled: int
    envelope_period: int
    envelope_shape: int
    mixer: int
    amplitude_register: int


@dataclass(frozen=True)
class SccSegment(Segment):
    previous_tone_period: int
    enabled: int
    volume_run_count: int
    waveform_id: int
    waveform_hex: str
    enable_register: int


@dataclass(frozen=True)
class SccAnalysis:
    segments: dict[int, list[SccSegment]]
    # All analyzed waveforms, including any not used by a sounding segment.
    waveforms: tuple[str, ...]


def dump_segments(path, segments, segment_type):
    """Write named fields and the lossless legacy row as a quoted JSON array."""
    columns = [field.name for field in fields(segment_type)]
    with open(path, 'w', encoding='utf-8', newline='') as fh:
        writer = csv.DictWriter(fh, fieldnames=columns + ['tick_start', 'tick_end'],
                                lineterminator='\n')
        writer.writeheader()
        for channel in segments.values():
            for segment in channel:
                row = asdict(segment)
                row['pass3_row'] = json.dumps(segment.pass3_row, ensure_ascii=False)
                row['tick_start'] = segment.tick_start
                row['tick_end'] = segment.tick_end
                writer.writerow(row)
