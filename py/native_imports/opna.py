"""Native YM2608 (OPNA) source FM state and inspectable intervals.

Unwritten values remain unknown; cleared key gates are a reset assumption.
Intervals describe control state, not envelope output or acoustic duration.
"""
import csv
from dataclasses import asdict, dataclass, field
import json

OPERATOR_NAMES = ('op1', 'op3', 'op2', 'op4')  # Register-bank order.
KEY_BITS = {'op1': 1, 'op2': 2, 'op3': 4, 'op4': 8}


def _bits(value, shift, mask):
    return None if value is None else (value >> shift) & mask


def register_channel(register, data, port=0):
    if port == 0 and register == 0x28:
        local = data & 3
        return None if local == 3 else local + (3 if data & 4 else 0)
    if 0x30 <= register <= 0x9f and register & 3 != 3:
        return (register & 3) + port * 3
    if (0xa0 <= register <= 0xa2 or 0xa4 <= register <= 0xa6
            or 0xb0 <= register <= 0xb2 or 0xb4 <= register <= 0xb6):
        return (register & 3) + port * 3
    if port == 0 and (0xa8 <= register <= 0xaa or 0xac <= register <= 0xae):
        return 2
    return None


def register_role(register, port=0):
    if port == 0 and register <= 0x0f:
        return 'ssg'
    if port == 0 and 0x10 <= register <= 0x1f:
        return 'rhythm'
    if port == 1 and register < 0x10:
        return 'adpcm_b'
    if port == 1 and register == 0x10:
        return 'irq_flag_control'
    if port == 0 and register == 0x28:
        return 'key'
    if port == 0 and register in (0x24, 0x25, 0x26, 0x27):
        return 'common_timer'
    if port == 0 and register in (0x2d, 0x2e, 0x2f):
        return 'prescaler'
    if port == 0 and register == 0x22:
        return 'common_lfo'
    if port == 0 and register == 0x29:
        return 'channel_enable'
    if 0x30 <= register <= 0x9f and register & 3 != 3:
        return 'operator_level' if register & 0xf0 == 0x40 else 'operator_voice'
    if (0xa0 <= register <= 0xa2 or 0xa4 <= register <= 0xa6
            or port == 0 and (0xa8 <= register <= 0xaa or 0xac <= register <= 0xae)):
        return 'pitch'
    if 0xb0 <= register <= 0xb2:
        return 'voice'
    if 0xb4 <= register <= 0xb6:
        return 'pan_modulation'
    return 'uninterpreted'


@dataclass(frozen=True)
class OpnaOperator:
    dt: int | None
    mul: int | None
    tl: int | None
    ks: int | None
    ar: int | None
    am_enabled: int | None
    d1r: int | None
    d2r: int | None
    sl: int | None
    rr: int | None
    ssg_eg_raw: int | None
    ssg_eg_enabled: int | None
    ssg_eg_shape: int | None


@dataclass(frozen=True)
class OpnaState:
    key_mask: int
    key_register_raw: int | None
    fnum_low_raw: int | None
    fnum_high_raw: int | None
    fnum: int | None
    block: int | None
    frequency_high_latch_raw: int | None
    algorithm: int | None
    feedback: int | None
    left_enabled: int | None
    right_enabled: int | None
    ams: int | None
    pms: int | None
    operators: tuple[OpnaOperator, ...]
    special_frequencies: tuple[tuple[str, int | None, int | None], ...]
    special_frequency_high_latch_raw: int | None
    special_frequencies_raw: tuple[tuple[int | None, int | None], ...]
    timer_a_high_raw: int | None
    timer_a_low_raw: int | None
    timer_b_raw: int | None
    mode_raw: int | None
    channel3_special_enabled: int | None
    csm_enabled: int | None
    six_channel_enabled: int | None
    channel_enable_raw: int | None
    lfo_raw: int | None
    lfo_enabled: int | None
    lfo_rate: int | None
    prescaler_address: int | None
    fm_prescale_divisor: int
    channel_registers: tuple[tuple[int, int, int], ...]
    shared_registers: tuple[tuple[int, int, int], ...]


@dataclass(frozen=True)
class OpnaStateEvent:
    source_event_id: int | None
    address: int | None
    command: int | None
    register: int | None
    data: int | None
    port: int
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
    state: OpnaState
    original_event_id: int | None = field(default=None, kw_only=True)
    loop_iteration: int = field(default=0, kw_only=True)
    original_vgmticks: int | None = field(default=None, kw_only=True)

    @property
    def time(self):
        return self.vgmticks / 44100.0


@dataclass(frozen=True)
class OpnaSegment(OpnaStateEvent):
    segment_id: int
    vgmticks_end: int

    @property
    def duration_samples(self):
        return self.vgmticks_end - self.vgmticks


@dataclass(frozen=True)
class OpnaUnmodeledWrite:
    source_event_id: int
    address: int
    command: int
    register: int
    data: int
    port: int
    chip_instance: int
    chip_type: str
    clock_hz: int
    clock_raw: int
    vgmticks: int
    domain: str
    original_event_id: int
    loop_iteration: int
    original_vgmticks: int


@dataclass(frozen=True)
class OpnaAnalysis:
    events: tuple[OpnaStateEvent, ...]
    segments: tuple[OpnaSegment, ...]
    source_end_vgmticks: int
    csm_observed: bool
    unmodeled_writes: tuple[OpnaUnmodeledWrite, ...]
    issues: tuple[str, ...]


class OpnaRegisterState:
    def __init__(self):
        self.num_channels = 6
        self.regs = {}
        self.keys = [0] * self.num_channels
        self.key_raw = [None] * self.num_channels
        self.continuity = [0] * self.num_channels
        self.frequency = [None] * self.num_channels
        self.high_latch = None
        self.special_high_latch = None
        self.special = [None] * 3
        self.prescaler = None
        self.prescale_divisor = 6

    def snapshot(self, ch):
        port, local = divmod(ch, 3)
        def reg(address):
            return self.regs.get((port, address + local))
        def shared(address):
            return self.regs.get((0, address))
        operators = []
        for bank in range(4):
            dt_mul, tl, ks_ar, am_d1r, d2r, sl_rr, ssg = (
                reg(base + bank * 4) for base in (0x30, 0x40, 0x50, 0x60, 0x70, 0x80, 0x90))
            operators.append(OpnaOperator(
                _bits(dt_mul, 4, 7), _bits(dt_mul, 0, 15), _bits(tl, 0, 127),
                _bits(ks_ar, 6, 3), _bits(ks_ar, 0, 31),
                _bits(am_d1r, 7, 1), _bits(am_d1r, 0, 31),
                _bits(d2r, 0, 31), _bits(sl_rr, 4, 15), _bits(sl_rr, 0, 15),
                ssg, _bits(ssg, 3, 1), _bits(ssg, 0, 7)))
        frequency = self.frequency[ch]
        low, high = frequency if frequency is not None else (None, None)
        voice, pan, mode, lfo, enable = reg(0xb0), reg(0xb4), shared(0x27), shared(0x22), shared(0x29)
        special = []
        for name, index in (('op1', 1), ('op2', 2), ('op3', 0)):
            value = self.special[index] if ch == 2 else None
            lo, hi = value if value is not None else (None, None)
            special.append((name, None if lo is None or hi is None else lo | ((hi & 7) << 8),
                            _bits(hi, 3, 7)))
        special.append(('op4', None if low is None or high is None else low | ((high & 7) << 8),
                        _bits(high, 3, 7)))
        channel_regs, shared_regs = [], []
        for (p, address), data in sorted(self.regs.items()):
            target = register_channel(address, data, p)
            (channel_regs if target == ch else shared_regs if target is None else []).append((p, address, data))
        return OpnaState(self.keys[ch], self.key_raw[ch], low, high,
                        None if low is None or high is None else low | ((high & 7) << 8),
                        _bits(high, 3, 7), self.high_latch,
                        _bits(voice, 0, 7), _bits(voice, 3, 7),
                        _bits(pan, 7, 1),
                        _bits(pan, 6, 1),
                        _bits(pan, 4, 3),
                        _bits(pan, 0, 7), tuple(operators), tuple(special),
                        self.special_high_latch if ch == 2 else None,
                        tuple(value if value is not None else (None, None) for value in self.special) if ch == 2 else (),
                        shared(0x24), shared(0x25), shared(0x26), mode,
                        None if mode is None else int(bool(mode & 0xc0)), _bits(mode, 7, 1),
                        _bits(enable, 7, 1), enable,
                        lfo, _bits(lfo, 3, 1),
                        _bits(lfo, 0, 7), self.prescaler,
                        self.prescale_divisor, tuple(channel_regs), tuple(shared_regs))

    def write(self, register, data, port=0):
        role = register_role(register, port)
        ch = register_channel(register, data, port)
        rising = falling = 0
        if role == 'key':
            if ch is None or ch >= self.num_channels:
                return (), 'invalid_key_channel', 0, 0
            mask = (data >> 4) & 15
            rising, falling = mask & ~self.keys[ch], self.keys[ch] & ~mask
            self.keys[ch], self.key_raw[ch] = mask, data
            if rising:
                self.continuity[ch] += 1
            return (ch,), 'key_change' if rising and falling else 'key_on' if rising else 'key_off' if falling else 'key_nochange', rising, falling
        self.regs[port, register] = data
        if role == 'prescaler':
            self.prescaler = register
            if register == 0x2d:
                self.prescale_divisor = 6
            elif register == 0x2e and self.prescale_divisor == 6:
                self.prescale_divisor = 3
            elif register == 0x2f:
                self.prescale_divisor = 2
        if 0xa4 <= register <= 0xa6:
            self.high_latch = data
            return tuple(range(self.num_channels)), 'frequency_latch', 0, 0
        if 0xa0 <= register <= 0xa2 and ch is not None and ch < self.num_channels:
            self.frequency[ch] = (data, self.high_latch)
        if port == 0 and 0xac <= register <= 0xae:
            self.special_high_latch = data
        if port == 0 and 0xa8 <= register <= 0xaa:
            self.special[register - 0xa8] = (data, self.special_high_latch)
        channels = tuple(range(self.num_channels)) if ch is None else (ch,) if ch < self.num_channels else ()
        return channels, role, rising, falling


def build_segments(trace_csv, *, end_vgmticks):
    if type(end_vgmticks) is not int or end_vgmticks < 0:
        raise ValueError('OPNA source end must be a nonnegative integer sample')
    with open(trace_csv, encoding='utf-8', newline='') as stream:
        rows = list(csv.DictReader(stream))
    chips, identities, current = {}, {}, {}
    events, segments, unmodeled, issues = [], [], [], set()
    previous_id = previous_address = -1
    previous_tick = previous_iteration = 0
    csm_observed = False
    chip_type = 'YM2608'

    def close(event, end):
        segments.append(OpnaSegment(**event.__dict__, segment_id=len(segments), vgmticks_end=end))

    for row in rows:
        instance, tick, event_id, address, register, data, command, clock, clock_raw, port = (
            int(row[k]) for k in ('chip_instance', 'vgmticks', 'event_id', 'address', 'register',
                                  'data', 'command', 'clock_hz', 'clock_raw', 'port'))
        expected_command = (0x56 + port) + (0x50 if instance else 0)
        if (instance not in (0, 1) or port not in (0, 1)
                or command != expected_command or row['chip_type'] != chip_type
                or not 0 <= register <= 255 or not 0 <= data <= 255 or clock <= 0
                or not 0 <= clock_raw <= 0xffffffff or clock_raw & 0x80000000
                or clock != clock_raw & 0x3fffffff
                or instance == 1 and not clock_raw & 0x40000000):
            raise ValueError('Invalid OPNA register evidence')
        expected_ch = register_channel(register, data, port)
        if 'ch' in row and row['ch'] != ('' if expected_ch is None else str(expected_ch)):
            raise ValueError('OPNA trace channel disagrees with register control')
        iteration = int(row.get('loop_iteration') or 0)
        original_id = int(row['original_event_id']) if row.get('original_event_id') else event_id
        original_tick = int(row['original_vgmticks']) if row.get('original_vgmticks') else tick
        if (event_id < 0 or address < 0 or iteration < 0 or original_id < 0
                or not 0 <= original_tick <= tick
                or event_id <= previous_id or iteration < previous_iteration
                or iteration == previous_iteration and address <= previous_address
                or not previous_tick <= tick <= end_vgmticks):
            raise ValueError('OPNA evidence must be in source order and within source end')
        previous_id, previous_address, previous_tick, previous_iteration = event_id, address, tick, iteration
        identity = (chip_type, clock, clock_raw)
        if instance not in chips:
            chips[instance] = OpnaRegisterState()
            identities[instance] = identity
            for ch in range(chips[instance].num_channels):
                current[instance, ch] = OpnaStateEvent(None, None, None, None, None, ch // 3,
                    instance, *identity, ch, 0, 'initial', False, 0, 0, 0, chips[instance].snapshot(ch))
        elif identities[instance] != identity:
            raise ValueError('OPNA clock/variant changed within one source stream')
        role = register_role(register, port)
        supported = role in ('key', 'common_timer', 'prescaler', 'operator_level', 'operator_voice', 'pitch', 'voice')
        supported |= role in ('common_lfo', 'channel_enable', 'pan_modulation')
        if not supported:
            unmodeled.append(OpnaUnmodeledWrite(event_id, address, command, register, data, port,
                instance, *identity, tick, role, original_id, iteration, original_tick))
            issues.add(f'{chip_type}: {role} writes retained without source-domain Segment interpretation')
            continue
        chip = chips[instance]
        channels, kind, rising, falling = chip.write(register, data, port)
        if not channels:
            unmodeled.append(OpnaUnmodeledWrite(event_id, address, command, register, data, port,
                instance, *identity, tick, kind, original_id, iteration, original_tick))
            issues.add(f'{chip_type}: {kind} writes retained without FM channel effect')
        for ch in channels:
            prior = current[instance, ch]
            state = chip.snapshot(ch)
            event = OpnaStateEvent(event_id, address, command, register, data, port, instance,
                *identity, ch, tick, kind, state != prior.state, rising, falling,
                chip.continuity[ch], state, original_event_id=original_id,
                loop_iteration=iteration, original_vgmticks=original_tick)
            events.append(event)
            csm_observed |= state.csm_enabled == 1
            if event.changed or role in ('common_timer', 'prescaler'):
                close(prior, tick)
                current[instance, ch] = event
    for key in sorted(current):
        close(current[key], end_vgmticks)
    if csm_observed:
        issues.add(f'{chip_type}: CSM timer-generated key edges are not modeled')
    return OpnaAnalysis(tuple(events), tuple(segments), end_vgmticks, csm_observed,
                       tuple(unmodeled), tuple(sorted(issues)))


def _flatten(event):
    row = asdict(event)
    state = row.pop('state')
    for name, operator in zip(OPERATOR_NAMES, state.pop('operators')):
        row.update((f'{name}_{key}', value) for key, value in operator.items())
    for key in ('channel_registers', 'shared_registers', 'special_frequencies', 'special_frequencies_raw'):
        state[key] = json.dumps(state[key], separators=(',', ':'))
    row.update(state)
    row.update(time=event.time, key_observed=event.state.key_register_raw is not None,
               gate_state='held' if event.state.key_mask else 'released', key_reset_assumed=True,
               csm_edges_modeled=False, prescale_reset_assumed=True)
    for name, bit in KEY_BITS.items():
        row[f'{name}_key_on'] = int(bool(event.state.key_mask & bit))
        row[f'{name}_key_on_edge'] = int(bool(event.rising_mask & bit))
        row[f'{name}_key_off_edge'] = int(bool(event.falling_mask & bit))
    if isinstance(event, OpnaSegment):
        row['duration_samples'] = event.duration_samples
    return row


def dump_analysis(analysis, *, state_csv, segments_csv):
    chip = OpnaRegisterState()
    initial = OpnaStateEvent(None, None, None, None, None, 0, 0, 'YM2608',
                            0, 0, 0, 0, 'initial', False, 0, 0, 0, chip.snapshot(0))
    segment = OpnaSegment(**initial.__dict__, segment_id=0, vgmticks_end=0)
    for path, records, empty in ((state_csv, analysis.events, initial), (segments_csv, analysis.segments, segment)):
        with open(path, 'w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(_flatten(empty)), lineterminator='\n')
            writer.writeheader()
            writer.writerows(_flatten(record) for record in records)


def key_counts(analysis):
    keys = [event for event in analysis.events if event.ev_type.startswith('key_')]
    return {'key_writes': len(keys), 'channel_attack_events': sum(bool(e.rising_mask) for e in keys),
            'operator_keyons': sum(e.rising_mask.bit_count() for e in keys),
            'operator_keyoffs': sum(e.falling_mask.bit_count() for e in keys)}


def dump_unmodeled_writes(analysis, *, csv_path):
    fields = list(OpnaUnmodeledWrite.__dataclass_fields__)
    with open(csv_path, 'w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows(asdict(event) for event in analysis.unmodeled_writes)
