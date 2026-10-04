"""Native OPM state intervals from ordered reader evidence, without a target.

Unwritten parameters stay unknown. Key gates start cleared (explicit reset
assumption); release is not silence. All write evidence, including nonchanges,
is retained separately from state intervals. No timing quantization is applied.
"""
import csv
from dataclasses import asdict, dataclass
import json


OPERATOR_NAMES = ('m1', 'm2', 'c1', 'c2')  # Register-bank order.
KEY_BITS = {'m1': 1, 'c1': 2, 'm2': 4, 'c2': 8}
KC_NOTES = {0: 1, 1: 2, 2: 3, 4: 4, 5: 5, 6: 6,
            8: 7, 9: 8, 10: 9, 12: 10, 13: 11, 14: 12}
NOTE_NAMES = ('c', 'c+', 'd', 'd+', 'e', 'f', 'f+', 'g', 'g+', 'a', 'a+', 'b')


@dataclass(frozen=True)
class OpmOperator:
    dt1: int | None
    mul: int | None
    tl: int | None
    ks: int | None
    ar: int | None
    am_enabled: int | None
    d1r: int | None
    dt2: int | None
    d2r: int | None
    d1l: int | None
    rr: int | None


@dataclass(frozen=True)
class OpmState:
    key_mask: int
    key_register_raw: int | None
    kc_raw: int | None
    kf_raw: int | None
    octave: int | None
    note: str | None
    kf: int | None
    algorithm: int | None
    feedback: int | None
    left_enabled: int | None
    right_enabled: int | None
    pms: int | None
    ams: int | None
    operators: tuple[OpmOperator, ...]
    test_raw: int | None
    lfo_reset: int | None
    noise_raw: int | None
    noise_enabled: int | None
    noise_rate: int | None
    timer_a_high_raw: int | None
    timer_a_low_raw: int | None
    timer_b_raw: int | None
    timer_control_raw: int | None
    csm_enabled: int | None
    lfo_rate_raw: int | None
    amd: int | None
    pmd: int | None
    lfo_control_raw: int | None
    lfo_waveform: int | None
    ct: int | None
    channel_registers: tuple[tuple[int, int], ...]
    shared_registers: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class OpmStateEvent:
    source_event_id: int | None
    address: int | None
    command: int | None
    register: int | None
    data: int | None
    chip_instance: int
    chip_type: str
    clock_hz: int
    clock_raw: int
    ch: int
    vgmticks: int
    ev_type: str
    changed: bool
    rising_mask: int
    falling_mask: int
    continuity_id: int
    state: OpmState

    @property
    def time(self):
        return self.vgmticks / 44100.0


@dataclass(frozen=True)
class OpmSegment(OpmStateEvent):
    segment_id: int
    vgmticks_end: int

    @property
    def duration_samples(self):
        return self.vgmticks_end - self.vgmticks


@dataclass(frozen=True)
class OpmAnalysis:
    events: tuple[OpmStateEvent, ...]
    segments: tuple[OpmSegment, ...]
    source_end_vgmticks: int
    csm_observed: bool


def _bits(value, shift, mask):
    return None if value is None else (value >> shift) & mask


class _ChipState:
    def __init__(self):
        self.regs = {}
        self.keys = [0] * 8
        self.key_raw = [None] * 8
        self.continuity = [0] * 8
        self.amd = self.pmd = None

    def snapshot(self, ch):
        def reg(base):
            return self.regs.get(base + ch)

        operators = []
        for bank in range(4):
            values = [reg(base + bank * 8) for base in (0x40, 0x60, 0x80, 0xa0, 0xc0, 0xe0)]
            dt_mul, tl, ks_ar, am_d1r, dt_d2r, dl_rr = values
            operators.append(OpmOperator(
                _bits(dt_mul, 4, 7), _bits(dt_mul, 0, 15), _bits(tl, 0, 127),
                _bits(ks_ar, 6, 3), _bits(ks_ar, 0, 31),
                _bits(am_d1r, 7, 1), _bits(am_d1r, 0, 31),
                _bits(dt_d2r, 6, 3), _bits(dt_d2r, 0, 31),
                _bits(dl_rr, 4, 15), _bits(dl_rr, 0, 15)))
        kc, kf = reg(0x28), reg(0x30)
        semitone = None if kc is None else KC_NOTES.get(kc & 15)
        octave = None if semitone is None else ((kc >> 4) & 7) + semitone // 12
        note = None if semitone is None else NOTE_NAMES[semitone % 12]
        control, sensitivity = reg(0x20), reg(0x38)
        test, noise, timer, lfo = [self.regs.get(i) for i in (1, 0x0f, 0x14, 0x1b)]
        return OpmState(
            self.keys[ch], self.key_raw[ch], kc, kf, octave, note, _bits(kf, 2, 63),
            _bits(control, 0, 7), _bits(control, 3, 7), _bits(control, 6, 1),
            _bits(control, 7, 1), _bits(sensitivity, 4, 7), _bits(sensitivity, 0, 3),
            tuple(operators), test, _bits(test, 1, 1), noise, _bits(noise, 7, 1),
            _bits(noise, 0, 31), self.regs.get(0x10), self.regs.get(0x11),
            self.regs.get(0x12), timer, _bits(timer, 7, 1), self.regs.get(0x18),
            self.amd, self.pmd, lfo, _bits(lfo, 0, 3), _bits(lfo, 6, 3),
            tuple(sorted((r, v) for r, v in self.regs.items() if r >= 0x20 and r & 7 == ch)),
            tuple(sorted((r, v) for r, v in self.regs.items() if r < 0x20)))

    def write(self, register, data):
        rising = falling = 0
        if register == 8:
            ch, mask = data & 7, (data >> 3) & 15
            previous = self.keys[ch]
            rising, falling = mask & ~previous, previous & ~mask
            self.keys[ch], self.key_raw[ch] = mask, data
            if rising:
                self.continuity[ch] += 1
            kind = ('key_change' if rising and falling else 'key_on' if rising
                    else 'key_off' if falling else 'key_nochange')
            return (ch,), kind, rising, falling
        self.regs[register] = data
        if register == 0x19:
            if data & 0x80:
                self.pmd = data & 127
            else:
                self.amd = data & 127
        if register < 0x20:
            # Even unmodeled global writes retain their evidence and raw state.
            kind = ('shared_control' if register in (1, 0x0f, 0x10, 0x11, 0x12,
                                                     0x14, 0x18, 0x19, 0x1b)
                    else 'uninterpreted')
            return tuple(range(8)), kind, 0, 0
        kind = ('pitch' if 0x28 <= register <= 0x37 else 'channel'
                if register < 0x40 else 'operator')
        return (register & 7,), kind, 0, 0


def build_segments(trace_csv, *, end_vgmticks):
    """Reconstruct native state with explicit source end (never last-write end).

    Rows must be in source order; identical-time writes are not merged. Every
    write yields state evidence. Nonchanges stay in evidence but need not split
    intervals, except control writes whose side effects are not just values.
    """
    if not isinstance(end_vgmticks, int) or end_vgmticks < 0:
        raise ValueError('OPM source end must be a nonnegative integer sample')
    with open(trace_csv, encoding='utf-8', newline='') as stream:
        rows = list(csv.DictReader(stream))
    chips, facts, current = {}, {}, {}
    events, segments = [], []
    previous_id = previous_address = -1
    previous_time = 0
    csm_observed = False

    def close(event, end):
        segments.append(OpmSegment(**event.__dict__, segment_id=len(segments), vgmticks_end=end))

    for row in rows:
        instance, tick, event_id, address, register, data, command, clock, clock_raw = (
            int(row[k]) for k in ('chip_instance', 'vgmticks', 'event_id', 'address',
                                  'register', 'data', 'command', 'clock_hz', 'clock_raw'))
        if (instance not in (0, 1) or command != (0x54 if instance == 0 else 0xa4)
                or not 0 <= register <= 255 or not 0 <= data <= 255 or clock <= 0):
            raise ValueError('Invalid OPM register evidence')
        if event_id <= previous_id or address <= previous_address or not previous_time <= tick <= end_vgmticks:
            raise ValueError('OPM evidence must be in source order and within source end')
        previous_id, previous_address, previous_time = event_id, address, tick
        identity = (row['chip_type'], clock, clock_raw)
        if instance not in chips:
            chips[instance] = _ChipState()
            facts[instance] = identity
            for ch in range(8):
                current[instance, ch] = OpmStateEvent(
                    None, None, None, None, None, instance, *identity, ch, 0,
                    'initial', False, 0, 0, 0, chips[instance].snapshot(ch))
        elif facts[instance] != identity:
            raise ValueError('OPM clock/variant changed within one source stream')
        chip = chips[instance]
        channels, kind, rising, falling = chip.write(register, data)
        for ch in channels:
            prior = current[instance, ch]
            state = chip.snapshot(ch)
            changed = state != prior.state
            event = OpmStateEvent(event_id, address, command, register, data, instance,
                                  *identity, ch, tick, kind, changed, rising, falling,
                                  chip.continuity[ch], state)
            events.append(event)
            csm_observed |= state.csm_enabled == 1
            if changed or register in (1, 0x14):
                close(prior, tick)
                current[instance, ch] = event
    for key in sorted(current):
        close(current[key], end_vgmticks)
    return OpmAnalysis(tuple(events), tuple(segments), end_vgmticks, csm_observed)


def _flatten(event):
    row = asdict(event)
    state = row.pop('state')
    for name, operator in zip(OPERATOR_NAMES, state.pop('operators')):
        row.update((f'{name}_{field}', value) for field, value in operator.items())
    for key in ('channel_registers', 'shared_registers'):
        state[key] = json.dumps(state[key], separators=(',', ':'))
    row.update(state)
    row['time'] = event.time
    row['key_observed'] = event.state.key_register_raw is not None
    row['gate_state'] = 'held' if event.state.key_mask else 'released'
    row['key_reset_assumed'] = True
    row['csm_edges_modeled'] = False
    for name, bit in KEY_BITS.items():
        row[f'{name}_key_on'] = int(bool(event.state.key_mask & bit))
        row[f'{name}_key_on_edge'] = int(bool(event.rising_mask & bit))
        row[f'{name}_key_off_edge'] = int(bool(event.falling_mask & bit))
    if isinstance(event, OpmSegment):
        row['duration_samples'] = event.duration_samples
    return row


def dump_analysis(analysis, *, state_csv, segments_csv):
    """Self-contained CSVs, including four named operators and shared state."""
    initial = OpmStateEvent(None, None, None, None, None, 0, 'YM2151', 0, 0, 0,
                            0, 'initial', False, 0, 0, 0, _ChipState().snapshot(0))
    empty_segment = OpmSegment(**initial.__dict__, segment_id=0, vgmticks_end=0)
    for path, records, empty in ((state_csv, analysis.events, initial),
                                 (segments_csv, analysis.segments, empty_segment)):
        with open(path, 'w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(_flatten(records[0] if records else empty)),
                                    lineterminator='\n')
            writer.writeheader()
            ordered = sorted(records, key=lambda e: (e.chip_instance, e.ch, e.vgmticks, e.segment_id)) \
                if isinstance(empty, OpmSegment) else records
            writer.writerows(_flatten(record) for record in ordered)


def key_counts(analysis):
    keys = [event for event in analysis.events if event.register == 8]
    return {'key_writes': len(keys), 'channel_attack_events': sum(bool(e.rising_mask) for e in keys),
            'operator_keyons': sum(e.rising_mask.bit_count() for e in keys),
            'operator_keyoffs': sum(e.falling_mask.bit_count() for e in keys)}
