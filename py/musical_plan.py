"""Backend-neutral accepted musical performance, retaining native provenance.

Times are integer 44100-Hz samples. Units are half-open intervals; controls
are ordered, piecewise-constant steps. Pattern metadata describes the already
expanded unit timeline and must never cause a writer to expand it again.
"""
from dataclasses import asdict, dataclass
from pathlib import Path
import csv
import json

KINDS = {
    'pitch': {'psg', 'scc', 'opll'}, 'volume': {'psg', 'scc', 'opll'},
    'gate': {'psg', 'scc', 'opll'}, 'psg_mode': {'psg'},
    'psg_noise': {'psg'}, 'psg_envelope_period': {'psg'},
    'psg_envelope_shape': {'psg'}, 'psg_envelope_enable': {'psg'},
    'waveform': {'scc'}, 'wave_write': {'scc'},
    'instrument': {'opll'}, 'patch_write': {'opll'},
    'rhythm_register': {'opll'}, 'percussion': {'opll'},
}


@dataclass(frozen=True)
class MusicalControl:
    sample: int
    chip: str
    channel: int | None
    kind: str
    value: tuple
    order: int = 0
    unit_id: str | None = None
    source_sample: int | None = None
    source_event_id: int | None = None
    source_indices: tuple = ()
    origin: str = 'interpreted'

    def __post_init__(self):
        if not isinstance(self.sample, int) or self.sample < 0:
            raise ValueError('Musical control sample must be a nonnegative integer')
        if self.kind not in KINDS or self.chip not in KINDS[self.kind]:
            raise ValueError(f'Unsupported musical control: {self.chip}/{self.kind}')
        if not isinstance(self.value, tuple) or any(not isinstance(v, int) for v in self.value):
            raise ValueError('Control values must be an immutable integer tuple')
        limit = {'psg': 3, 'scc': 5, 'opll': 9}[self.chip]
        if self.channel is not None and not 0 <= self.channel < limit:
            raise ValueError('Musical control channel outside chip range')
        global_kinds = {'psg_noise', 'psg_envelope_period', 'psg_envelope_shape',
                        'wave_write', 'patch_write', 'rhythm_register', 'percussion'}
        if (self.channel is None) != (self.kind in global_kinds):
            raise ValueError('Musical control channel/global scope differs from its kind')
        expected = (3 if self.kind == 'percussion' or self.kind == 'pitch' and self.chip == 'opll' else
                    32 if self.kind == 'waveform' else 3 if self.kind == 'wave_write' else
                    2 if self.kind in ('patch_write', 'rhythm_register') else 1)
        if len(self.value) != expected:
            raise ValueError(f'Invalid payload length for {self.kind}')
        if self.kind in ('gate', 'psg_envelope_enable') and self.value[0] not in (0, 1):
            raise ValueError('Gate/envelope enable must be zero or one')
        if self.kind in ('volume', 'instrument', 'psg_envelope_shape') and not 0 <= self.value[0] <= 15:
            raise ValueError('Four-bit musical control outside range')
        if self.kind == 'psg_mode' and not 0 <= self.value[0] <= 3:
            raise ValueError('PSG mode outside range')
        if self.kind == 'psg_noise' and not 0 <= self.value[0] <= 31:
            raise ValueError('PSG noise period outside range')
        if self.kind == 'psg_envelope_period' and not 0 <= self.value[0] <= 65535:
            raise ValueError('PSG hardware envelope period outside range')
        if self.kind == 'pitch':
            if self.chip == 'opll':
                fnum, block, sustain = self.value
                if not (0 <= fnum <= 511 and 0 <= block <= 7 and sustain in (0, 1)):
                    raise ValueError('OPLL pitch outside native range')
            elif not 0 <= self.value[0] <= 4095:
                raise ValueError('PSG/SCC period outside native range')
        if self.kind == 'waveform' and any(not 0 <= v <= 255 for v in self.value):
            raise ValueError('SCC wave values must be bytes')
        if self.kind == 'wave_write':
            slot, index, value = self.value
            if not (0 <= slot < 4 and 0 <= index < 32 and 0 <= value <= 255):
                raise ValueError('SCC wave-RAM write outside range')
        if self.kind == 'patch_write' and not (0 <= self.value[0] <= 7 and 0 <= self.value[1] <= 255):
            raise ValueError('OPLL patch write outside range')
        if self.kind == 'rhythm_register':
            reg, value = self.value
            if reg not in (0x0e, 0x16, 0x17, 0x18, 0x26, 0x27, 0x28, 0x36, 0x37, 0x38) or not 0 <= value <= 255:
                raise ValueError('OPLL rhythm/shared register outside reviewed scope')
        if self.kind == 'percussion':
            instrument, volume, enabled = self.value
            if not (0 <= instrument < 5 and 0 <= volume <= 15 and enabled in (0, 1)):
                raise ValueError('Percussion control outside instrument/volume/gate range')


@dataclass(frozen=True)
class MusicalUnit:
    unit_id: str
    chip: str
    channel: int
    start_sample: int
    end_sample: int
    rest: bool
    articulation: str = 'score_partition'
    source_indices: tuple = ()
    source_start: int | None = None
    source_end: int | None = None
    gate_ids: tuple = ()
    parameters: tuple = ()

    def __post_init__(self):
        if not 0 <= self.start_sample <= self.end_sample:
            raise ValueError('Musical units must be nonnegative half-open intervals')


@dataclass(frozen=True)
class MusicalPlan:
    units: tuple
    controls: tuple
    end_sample: int
    source_end_sample: int
    chip_clocks: tuple = ()
    song_loop_sample: int | None = None
    patterns: tuple = ()
    decisions: tuple = ()
    metadata: tuple = ()

    def __post_init__(self):
        if self.end_sample < 0 or self.source_end_sample < 0:
            raise ValueError('Musical plan duration must be nonnegative')
        if any(c.sample > self.end_sample for c in self.controls):
            raise ValueError('Musical control exceeds plan duration')
        if any(u.end_sample > self.end_sample for u in self.units):
            raise ValueError('Musical unit exceeds plan duration')
        if self.song_loop_sample is not None and not 0 <= self.song_loop_sample < self.end_sample:
            raise ValueError('Song loop must have a positive duration')

    def ordered_controls(self):
        return tuple(c for _, c in sorted(enumerate(self.controls),
                     key=lambda item: (item[1].sample, item[1].order, item[0])))

    def dump(self, folder, stem):
        root = Path(folder)
        root.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        data.update(sample_rate=44100, interval_convention='half_open',
                    curve_interpolation='piecewise_constant', patterns_executable=False)
        (root / f'{stem}.musical_plan.json').write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
        for name, records, cls in (('units', self.units, MusicalUnit),
                                    ('controls', self.ordered_controls(), MusicalControl)):
            with (root / f'{stem}.musical_plan.{name}.csv').open('w', newline='', encoding='utf-8') as stream:
                writer = csv.DictWriter(stream, fieldnames=list(cls.__dataclass_fields__))
                writer.writeheader()
                for record in records:
                    writer.writerow({key: json.dumps(value) if isinstance(value, tuple) else value
                                     for key, value in asdict(record).items()})


def combine(plans, *, metadata=()):
    plans = tuple(plans)
    if not plans:
        return MusicalPlan((), (), 0, 0, metadata=metadata)
    loops = {p.song_loop_sample for p in plans if p.song_loop_sample is not None}
    if len(loops) > 1:
        raise ValueError('Conflicting musical song-loop boundaries')
    clocks = {}
    for plan in plans:
        for chip, clock in plan.chip_clocks:
            if chip in clocks and clocks[chip] != clock:
                raise ValueError('Conflicting target chip clocks')
            clocks[chip] = clock
    return MusicalPlan(tuple(u for p in plans for u in p.units), tuple(c for p in plans for c in p.controls),
        max(p.end_sample for p in plans), max(p.source_end_sample for p in plans),
        tuple(sorted(clocks.items())), next(iter(loops), None), tuple(x for p in plans for x in p.patterns),
        tuple(x for p in plans for x in p.decisions),
        tuple((f'component_{index}', p.metadata) for index, p in enumerate(plans) if p.metadata) + tuple(metadata))
