"""Source-native musical information, independent of a target's precision.

Native controls retain chip semantics and original time. Musical units group
complete sounding gates; they do not replace the constituent state evidence.
The existing MusicalPlan remains an accepted output projection.
"""
from dataclasses import asdict, dataclass
import csv
import json
from pathlib import Path


@dataclass(frozen=True)
class NativeDevice:
    device_id: str
    chip: str
    instance: int
    clock_hz: int
    clock_raw: int = 0
    parameters: tuple = ()


@dataclass(frozen=True)
class NativeControl:
    control_id: str
    device_id: str
    section: str
    channel: int | None
    sample: int
    order: int
    kind: str
    parameters: tuple
    source_event_id: int | None = None
    source_indices: tuple = ()
    unit_ids: tuple = ()


@dataclass(frozen=True)
class NativeVoice:
    voice_id: str
    device_id: str
    section: str
    parameters: tuple


@dataclass(frozen=True)
class NativeUnit:
    unit_id: str
    device_id: str
    section: str
    channel: int
    start_sample: int
    end_sample: int
    pitch_curve: tuple = ()  # (source sample, frequency Hz), never MGS note codes
    volume_curve: tuple = ()  # native/inferred levels; projection chooses scaling
    voice_curve: tuple = ()  # (source sample, NativeVoice identity)
    control_ids: tuple = ()
    source_indices: tuple = ()
    role: str = 'melody'
    parameters: tuple = ()

    def __post_init__(self):
        if not 0 <= self.start_sample <= self.end_sample:
            raise ValueError('Native musical unit must have an ordered nonnegative interval')


@dataclass(frozen=True)
class NativePercussion:
    event_id: str
    device_id: str
    instrument_id: str
    instrument_family: str
    start_sample: int
    stop_sample: int | None = None  # no invented natural-decay endpoint
    volume_curve: tuple = ()
    pitch_curve: tuple = ()
    control_ids: tuple = ()
    observed: bool = True
    parameters: tuple = ()


@dataclass(frozen=True)
class NativePacket:
    packet_id: str
    sample: int
    order: int
    command_hex: str
    chip: str
    kind: str
    dependencies: tuple = ()
    source_event_id: int | None = None


@dataclass(frozen=True)
class NativePerformance:
    devices: tuple
    units: tuple
    controls: tuple
    voices: tuple
    percussion: tuple
    pcm_packets: tuple
    end_sample: int
    source_sha256: str
    source_header_hex: str
    song_loop_sample: int | None = None
    song_loop_order: int | None = None
    metadata: tuple = ()
    decisions: tuple = ()
    patterns: tuple = ()

    def __post_init__(self):
        ids = {device.device_id for device in self.devices}
        if len(ids) != len(self.devices):
            raise ValueError('Duplicate native device identity')
        if self.end_sample < 0:
            raise ValueError('Negative native performance duration')
        for item in (*self.units, *self.controls, *self.voices, *self.percussion):
            if item.device_id not in ids:
                raise ValueError('Native record references an unknown device')
        for unit in self.units:
            if unit.end_sample > self.end_sample:
                raise ValueError('Native unit exceeds the source duration')
        if any(c.sample > self.end_sample or c.sample < 0 for c in self.controls):
            raise ValueError('Native control outside the source timeline')

    def dump(self, folder, stem):
        root = Path(folder)
        root.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        data.update(sample_rate=44100, time_domain='original_source_samples',
                    projection_applied=False, patterns_are_descriptive=True)
        (root / f'{stem}.native_music.json').write_text(json.dumps(data, indent=2)+'\n', encoding='utf-8')
        for name, records, cls in (
            ('devices', self.devices, NativeDevice), ('units', self.units, NativeUnit),
            ('controls', self.controls, NativeControl), ('voices', self.voices, NativeVoice),
            ('percussion', self.percussion, NativePercussion), ('pcm_packets', self.pcm_packets, NativePacket)):
            with (root / f'{stem}.native_music.{name}.csv').open('w', newline='', encoding='utf-8') as stream:
                writer = csv.DictWriter(stream, fieldnames=list(cls.__dataclass_fields__))
                writer.writeheader()
                for record in records:
                    writer.writerow({key: json.dumps(value) if isinstance(value, tuple) else value
                                     for key, value in asdict(record).items()})
