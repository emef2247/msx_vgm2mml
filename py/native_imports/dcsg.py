"""Native SN76489-family command evidence and exact-sample control Segments.

This module decodes registers, not oscillator phase or target MML. An interval
boundary is not a KeyOn: this chip has no key register. Register knowledge is
explicit, so a truncated capture never invents a silent/reset source state.
Header flag interpretation follows libvgm player/vgmplayer.cpp; the raw flags
remain available even where waveform-level behavior is outside this analysis.
"""
from dataclasses import asdict, dataclass
import csv
import json
from pathlib import Path

from .vgm_io import read_vgm_header, read_vgm_bytes
from .vgm_timing import command_times


@dataclass(frozen=True)
class Config:
    clock_raw: int
    clock_hz: int
    dual_chip: bool
    t6w28: bool
    feedback_raw: int
    shift_width_raw: int
    flags_raw: int
    feedback: int
    shift_width: int
    clock_divider: int
    sega_zero_period: bool
    negate: bool
    stereo: bool
    ncr: bool


def read_config(raw):
    header = read_vgm_header(raw)
    version, start = header['version'], header['data_start']
    def field(offset, size, since):
        return int.from_bytes(raw[offset:offset + size], 'little') if (
            version >= since and offset + size <= start) else 0
    clock = field(0x0c, 4, 0x100)
    feedback = field(0x28, 2, 0x110)
    width = field(0x2a, 1, 0x110)
    flags = field(0x2b, 1, 0x151)
    return Config(clock, clock & 0x3fffffff, bool(clock & 0x40000000),
                  bool(clock & 0x80000000), feedback, width, flags,
                  feedback or 9, width or 16, 1 if flags & 8 else 8,
                  not bool(flags & 1), bool(flags & 2), not bool(flags & 4),
                  bool(flags & 16))


@dataclass(frozen=True)
class State:
    chip_instance: int
    registers: tuple
    known_masks: tuple
    latched_register: int | None
    stereo_mask: int
    stereo_observed: bool
    noise_reset_count: int


@dataclass(frozen=True)
class Write:
    event_id: int
    source_event_id: int
    address: int
    vgmticks: int
    original_vgmticks: int
    loop_iteration: int
    chip_instance: int
    command: int
    data: int
    kind: str
    register: int | None
    previous_value: int | None
    value: int | None
    known_mask: int
    noise_reset: bool
    state_index: int


@dataclass(frozen=True)
class Segment:
    segment_id: int
    chip_instance: int
    ch: int
    start_sample: int
    end_sample: int
    source_event_id: int | None
    state_index: int
    period: int | None
    period_known_mask: int
    attenuation: int | None
    stereo_left: bool
    stereo_right: bool
    noise_control: int | None
    noise_tone2_coupled: bool
    tone2_period: int | None
    noise_reset_count: int
    frequency_hz: float | None
    noise_shift_hz: float | None
    audible: bool

    @property
    def length_samples(self):
        return self.end_sample - self.start_sample


@dataclass(frozen=True)
class Analysis:
    config: Config
    writes: tuple
    states: tuple
    segments: tuple
    end_sample: int
    issues: tuple


def _segment(config, state, ch, start, stop, source_id, state_index):
    reg, known = state.registers, state.known_masks
    period = reg[ch * 2] if ch < 3 else None
    period_known = known[ch * 2] if ch < 3 else 0
    attenuation = reg[ch * 2 + 1] if known[ch * 2 + 1] == 15 else None
    noise = reg[6] if known[6] & 7 == 7 else None
    tone2 = reg[4] if known[4] == 1023 else None
    coupled = ch == 3 and noise is not None and noise & 3 == 3
    def effective(value):
        if value:
            return value
        return None if config.sega_zero_period else 1024
    frequency = shift = None
    if ch < 3 and period_known == 1023:
        divisor = effective(period)
        if divisor:
            frequency = config.clock_hz / (4 * config.clock_divider * divisor)
    elif ch == 3 and noise is not None:
        if coupled and tone2 is not None:
            divisor = effective(tone2)
            if divisor:
                shift = config.clock_hz / (4 * config.clock_divider * divisor)
        elif not coupled:
            shift = config.clock_hz / (64 * config.clock_divider * (1 << (noise & 3)))
    mask = state.stereo_mask if config.stereo else 255
    left, right = bool(mask & (16 << ch)), bool(mask & (1 << ch))
    return Segment(-1, state.chip_instance, ch, start, stop, source_id,
                   state_index, period, period_known, attenuation, left, right,
                   noise if ch == 3 else None, coupled, tone2 if ch == 3 else None,
                   state.noise_reset_count if ch == 3 else 0, frequency, shift,
                   attenuation is not None and attenuation < 15 and (left or right))


def analyze(raw, *, loop_count=1):
    """Preserve all writes and snapshots, plus positive-duration native slices.

    Undeclared instances and unknown latch state are retained as issues, never
    silently routed to another chip. The first data-only write has unknown
    destination until an explicit latch; reset latch assumptions are not source
    evidence. T6W28 is inventoried but its cross-chip routing is not reconstructed.
    """
    config = read_config(raw)
    writes, states, segments, issues = [], [], [], []
    current, active = {}, {}
    def initialize(instance):
        state = State(instance, (0,) * 8, (0,) * 8, None, 255, False, 0)
        index = len(states)
        states.append(state)
        current[instance] = state
        active[instance] = [(_segment(config, state, ch, 0, 0, None, index), 0)
                            for ch in range(4)]
    for instance in range(2 if config.dual_chip else 1):
        initialize(instance)
    if config.t6w28:
        issues.append(dict(code='t6w28_cross_chip_routing_not_interpreted'))
    end = 0
    for event_id, event in enumerate(command_times(raw, loop_count=loop_count)):
        end = event.vgmticks + event.wait_samples
        if event.command not in (0x50, 0x30, 0x4f, 0x3f):
            continue
        instance = int(event.command in (0x30, 0x3f))
        if instance not in current:
            initialize(instance)
        if not config.clock_hz or (instance and not config.dual_chip):
            issues.append(dict(code='undeclared_dcsg_instance', event_id=event_id,
                               chip_instance=instance, vgmticks=event.vgmticks))
        old = current[instance]
        data = raw[event.address + 1]
        reg, known = list(old.registers), list(old.known_masks)
        latch, stereo = old.latched_register, old.stereo_mask
        stereo_observed, resets = old.stereo_observed, old.noise_reset_count
        register = previous = value = None
        reset = False
        kind = 'stereo' if event.command in (0x4f, 0x3f) else 'latch' if data & 128 else 'data'
        if kind == 'stereo':
            previous, value, stereo, stereo_observed = stereo, data, data, True
            if not config.stereo:
                issues.append(dict(code='stereo_write_on_mono_variant', event_id=event_id,
                                   chip_instance=instance, vgmticks=event.vgmticks))
        else:
            if data & 128:
                latch = (data >> 4) & 7
            register = latch
            if register is None:
                issues.append(dict(code='data_before_known_latch', event_id=event_id,
                                   chip_instance=instance, vgmticks=event.vgmticks))
            else:
                previous = reg[register]
                if register in (0, 2, 4):
                    if data & 128:
                        reg[register] = (reg[register] & 0x3f0) | (data & 15)
                        known[register] |= 15
                    else:
                        reg[register] = (reg[register] & 15) | ((data & 63) << 4)
                        known[register] |= 0x3f0
                else:
                    reg[register] = data & 15
                    known[register] = 15
                if register == 6:
                    reset = not config.ncr or bool((previous ^ reg[6]) & 4)
                    resets += int(reset)
                value = reg[register]
        state = State(instance, tuple(reg), tuple(known), latch, stereo,
                      stereo_observed, resets)
        state_index = len(states)
        states.append(state)
        writes.append(Write(event_id, event.source_event_id, event.address,
                            event.vgmticks, event.original_vgmticks,
                            event.loop_iteration, instance, event.command, data,
                            kind, register, previous, value,
                            known[register] if register is not None else 0,
                            reset, state_index))
        current[instance] = state
        for ch in range(4):
            previous_segment, start = active[instance][ch]
            candidate = _segment(config, state, ch, start, start, event_id, state_index)
            # Slice only when channel-observable controls change. Retain every
            # same-time and repeated request independently in writes/states.
            signature = lambda s: tuple(getattr(s, k) for k in (
                'period', 'period_known_mask', 'attenuation', 'stereo_left',
                'stereo_right', 'noise_control', 'noise_tone2_coupled',
                'tone2_period', 'noise_reset_count', 'frequency_hz', 'noise_shift_hz'))
            if signature(previous_segment) != signature(candidate):
                if event.vgmticks > start:
                    segments.append(Segment(**{**asdict(previous_segment),
                                               'end_sample': event.vgmticks}))
                candidate = Segment(**{**asdict(candidate),
                                       'start_sample': event.vgmticks,
                                       'end_sample': event.vgmticks})
                active[instance][ch] = (candidate, event.vgmticks)
    for instance in active:
        for previous, start in active[instance]:
            if end > start:
                segments.append(Segment(**{**asdict(previous), 'end_sample': end}))
    segments.sort(key=lambda s: (s.chip_instance, s.ch, s.start_sample))
    segments = tuple(Segment(**{**asdict(s), 'segment_id': i}) for i, s in enumerate(segments))
    return Analysis(config, tuple(writes), tuple(states), segments, end, tuple(issues))


def dump_analysis(analysis, outdir, stem):
    folder = Path(outdir)
    folder.mkdir(parents=True, exist_ok=True)
    paths = {}
    for kind, values, cls in (('writes', analysis.writes, Write),
                              ('states', analysis.states, State),
                              ('segments', analysis.segments, Segment)):
        path = folder / f'{stem}.dcsg.{kind}.csv'
        with path.open('w', encoding='utf-8', newline='') as stream:
            extra = ['state_index', 'event_id', 'vgmticks'] if kind == 'states' else []
            writer = csv.DictWriter(stream, fieldnames=extra + list(cls.__dataclass_fields__))
            writer.writeheader()
            state_events = {w.state_index: w for w in analysis.writes}
            for index, value in enumerate(values):
                row = asdict(value)
                if kind == 'states':
                    event = state_events.get(index)
                    row.update(state_index=index, event_id=event.event_id if event else None,
                               vgmticks=event.vgmticks if event else 0)
                for key in ('registers', 'known_masks'):
                    if key in row:
                        row[key] = json.dumps(row[key], separators=(',', ':'))
                writer.writerow(row)
        paths[kind] = str(path)
    path = folder / f'{stem}.dcsg.analysis.json'
    path.write_text(json.dumps(dict(config=asdict(analysis.config),
                                   end_sample=analysis.end_sample,
                                   writes=len(analysis.writes), states=len(analysis.states),
                                   segments=len(analysis.segments), issues=analysis.issues,
                                   reset_policy='unobserved register values remain unknown',
                                   source_phase_emulated=False, paths=paths), indent=2) + '\n',
                    encoding='utf-8')
    paths['manifest'] = str(path)
    return paths


def load_source(path, outdir=None, *, loop_count=1):
    analysis = analyze(read_vgm_bytes(path), loop_count=loop_count)
    if outdir is not None:
        dump_analysis(analysis, outdir, Path(path).stem)
    return analysis
