"""Native HuC6280 evidence and a pinned, explicitly labeled waveform profile.

Source controls and waveform RAM remain separate from MGSDRV representation.
The basic waveform cursor follows libvgm's c6280_mame profile; active LFO and
noise phase are deliberately not guessed by this analysis adapter.
"""
from dataclasses import dataclass, asdict
from pathlib import Path
import csv
import hashlib
import json
import math

from vgm_io import read_vgm_header
from vgm_timing import command_times

REFERENCE_REVISION = 'bad50c571db45b872304bdcd0603dd2214f0663e'
REFERENCE_CORE_SHA256 = 'f342dd818a7b4bf0afe15f12320e62d85ff38f5ebf78ba2cc4d49b8e6f02eb4b'
BALANCE_SCALE = (0, 3, 5, 7, 9, 11, 13, 15, 16, 19, 21, 23, 25, 27, 29, 31)


def _volume_table():
    level, result = 65536.0 / 6.0 / 32.0, []
    for _ in range(31):
        result.append(int(level))
        level /= math.pow(10.0, 1.5 / 20.0)
    return tuple(result) + (0,)


VOLUME_TABLE = _volume_table()


def attenuation_levels(control, balance, global_balance):
    volume = control & 31
    return tuple(min(31, 93 - BALANCE_SCALE[(global_balance >> shift) & 15]
                     - BALANCE_SCALE[(balance >> shift) & 15] - volume)
                 for shift in (4, 0))


@dataclass(frozen=True)
class Write:
    event_id: int
    source_event_id: int
    address: int
    vgmticks: int
    register: int
    value: int
    chip_instance: int = 0


@dataclass(frozen=True)
class ChannelState:
    channel: int
    frequency: int
    control: int
    balance: int
    noise_control: int
    dda: int
    waveform: tuple[int | None, ...]
    waveform_known: tuple[bool, ...]
    waveform_id: int | None
    index: int | None
    counter: int | None
    index_origin: str

    @property
    def period(self):
        return self.frequency

    @property
    def enabled(self):
        return bool(self.control & 128)

    @property
    def dda_mode(self):
        return bool(self.control & 64)

    @property
    def volume(self):
        return self.control & 31

    @property
    def waveform_complete(self):
        return all(self.waveform_known)

    @property
    def mode(self):
        return ('disabled' if not self.enabled else
                'noise' if self.channel >= 4 and self.noise_control & 128 else
                'dda' if self.dda_mode else 'wave')


@dataclass(frozen=True)
class StateSnapshot:
    selected_channel: int
    global_balance: int
    lfo_frequency: int
    lfo_control: int
    channels: tuple[ChannelState, ...]
    native_frame: int


@dataclass(frozen=True)
class StateEvent:
    write: Write
    state: StateSnapshot
    key_on_edge: bool
    dda_reset_edge: bool

    @property
    def channels(self):
        return self.state.channels

    @property
    def selected_channel(self):
        return self.state.selected_channel

    @property
    def global_balance(self):
        return self.state.global_balance

    @property
    def lfo_frequency(self):
        return self.state.lfo_frequency

    @property
    def lfo_control(self):
        return self.state.lfo_control

    @property
    def native_frame(self):
        return self.state.native_frame


@dataclass(frozen=True)
class Segment:
    channel: int
    start_vgmticks: int
    end_vgmticks: int
    start_event_id: int | None
    end_event_id: int | None
    state: ChannelState
    global_balance: int
    lfo_frequency: int
    lfo_control: int
    start_native_frame: int
    end_native_frame: int
    end_index: int | None
    end_counter: int | None

    @property
    def frequency(self):
        return self.state.frequency

    @property
    def control(self):
        return self.state.control

    @property
    def waveform(self):
        return self.state.waveform

    @property
    def waveform_id(self):
        return self.state.waveform_id

    @property
    def volume(self):
        return self.state.volume

    @property
    def balance(self):
        return self.state.balance

    @property
    def attenuation(self):
        return attenuation_levels(self.state.control, self.state.balance, self.global_balance)

    @property
    def active(self):
        return self.state.enabled and min(self.attenuation) < 31


class Runtime:
    """Mutable reference-profile machine; every emitted snapshot is immutable."""
    def __init__(self, clock_hz):
        self.clock_hz = clock_hz
        self.rate_hz = clock_hz // 16
        self.selected_channel = self.global_balance = 0
        self.lfo_frequency = self.lfo_control = self.native_frame = 0
        self.waveforms, self._waveform_ids = [], {}
        self.channels = [dict(frequency=0, control=0, balance=0, noise_control=0,
            dda=0, waveform=(0,) * 32, waveform_known=(False,) * 32,
            waveform_id=None, index=0, counter=0, index_origin='reference_reset_assumption')
            for _ in range(8)]

    def snapshot(self):
        return StateSnapshot(self.selected_channel, self.global_balance,
            self.lfo_frequency, self.lfo_control,
            tuple(ChannelState(channel, **values) for channel, values in enumerate(self.channels)),
            self.native_frame)

    def advance(self, frames):
        if frames < 0:
            raise ValueError('HuC6280 frame clock must not move backward')
        if frames and self.rate_hz <= 0:
            raise ValueError('HuC6280 clock cannot produce a reference sample rate')
        for channel, state in enumerate(self.channels[:6]):
            if not frames or not state['control'] & 128:
                continue
            if channel >= 4 and state['noise_control'] & 128:
                continue
            if state['control'] & 64:
                continue
            if channel < 2 and self.lfo_control & 3:
                state.update(index=None, counter=None, index_origin='unmodeled_lfo_phase')
                continue
            if state['counter'] is None:
                state.update(index=None, index_origin='unresolved_previous_phase')
                continue
            period = state['frequency'] or 4096
            step = int(((self.clock_hz / self.rate_hz) * 4096) / period)
            state['counter'] = (state['counter'] + step * frames) & 0x1ffff
            state['index'] = (state['counter'] >> 12) & 31
            state['index_origin'] = 'reference_waveform_counter'
        self.native_frame += frames

    def write(self, register, value):
        register, value = register & 15, value & 255
        state = self.channels[self.selected_channel]
        if register == 0:
            self.selected_channel = value & 7
        elif register == 1:
            self.global_balance = value
        elif register == 2:
            state['frequency'] = (state['frequency'] & 0xf00) | value
        elif register == 3:
            state['frequency'] = (state['frequency'] & 255) | ((value & 15) << 8)
        elif register == 4:
            if state['control'] & 64 and not value & 64:
                state.update(index=0, index_origin='observed_dda_falling_edge')
            if not state['control'] & 128 and value & 128:
                state['counter'] = 0
            state['control'] = value
        elif register == 5:
            state['balance'] = value
        elif register == 6:
            if state['control'] & 64:
                state['dda'] = value & 31
            elif state['index'] is None:
                state.update(waveform=(None,) * 32, waveform_known=(False,) * 32,
                             waveform_id=None)
            else:
                index = state['index'] & 31
                wave, known = list(state['waveform']), list(state['waveform_known'])
                wave[index], known[index] = value & 31, True
                state['waveform'], state['waveform_known'] = tuple(wave), tuple(known)
                if all(known):
                    identity = state['waveform']
                    if identity not in self._waveform_ids:
                        self._waveform_ids[identity] = len(self.waveforms)
                        self.waveforms.append(identity)
                    state['waveform_id'] = self._waveform_ids[identity]
                else:
                    state['waveform_id'] = None
                if not state['control'] & 128:
                    state['index'] = (index + 1) & 31
                    state['index_origin'] = 'observed_disabled_wave_write'
        elif register == 7:
            state['noise_control'] = value
        elif register == 8:
            self.lfo_frequency = value
        elif register == 9:
            self.lfo_control = value


def _channel_row(channel):
    result = asdict(channel)
    result['waveform'] = json.dumps(channel.waveform, separators=(',', ':'))
    result['waveform_known'] = ''.join('1' if known else '0' for known in channel.waveform_known)
    return result


def _dump_csv(path, rows, empty_column='event_id'):
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]) if rows else [empty_column])
        writer.writeheader()
        writer.writerows(rows)


@dataclass(frozen=True)
class Trace:
    source_end_vgmticks: int
    clock_raw: int
    clock_hz: int
    writes: tuple[Write, ...]
    states: tuple[StateEvent, ...]
    segments: tuple[Segment, ...]
    waveforms: tuple[tuple[int, ...], ...]
    final_state: StateSnapshot
    issues: tuple[str, ...]

    @property
    def state_events(self):
        return self.states

    @property
    def rate_hz(self):
        return self.clock_hz // 16

    def dump(self, outdir, stem):
        root = Path(outdir)
        root.mkdir(parents=True, exist_ok=True)
        _dump_csv(root / f'{stem}.huc6280.writes.csv', [asdict(w) for w in self.writes])
        states = []
        for event in self.states:
            for channel in event.channels:
                states.append(dict(event_id=event.write.event_id,
                    source_event_id=event.write.source_event_id, vgmticks=event.write.vgmticks,
                    register=event.write.register, value=event.write.value,
                    selected_channel=event.selected_channel, global_balance=event.global_balance,
                    lfo_frequency=event.lfo_frequency, lfo_control=event.lfo_control,
                    native_frame=event.native_frame, key_on_edge=event.key_on_edge,
                    dda_reset_edge=event.dda_reset_edge, **_channel_row(channel)))
        _dump_csv(root / f'{stem}.huc6280.states.csv', states)
        segments = []
        for segment in self.segments:
            row = asdict(segment)
            row.pop('state')
            row.update(_channel_row(segment.state))
            row.update(attenuation_left=segment.attenuation[0], attenuation_right=segment.attenuation[1],
                       active=segment.active)
            segments.append(row)
        _dump_csv(root / f'{stem}.huc6280.segments.csv', segments, 'channel')
        _dump_csv(root / f'{stem}.huc6280.waveforms.csv', [dict(waveform_id=index,
            waveform_u5=json.dumps(wave, separators=(',', ':')),
            sha256=hashlib.sha256(bytes(wave)).hexdigest()) for index, wave in enumerate(self.waveforms)],
            'waveform_id')
        report = dict(clock_raw=self.clock_raw, clock_hz=self.clock_hz,
            reference_native_rate_hz=self.rate_hz, tick_clock_hz=44100,
            source_end_vgmticks=self.source_end_vgmticks, write_count=len(self.writes),
            segment_count=len(self.segments), waveform_count=len(self.waveforms),
            reference_revision=REFERENCE_REVISION, reference_core_sha256=REFERENCE_CORE_SHA256,
            initialization=dict(origin='reference_reset_assumption', observed=False,
                registers='all zero', waveform_ram='zero-valued assumption; waveform_known is false until written',
                waveform_index=0, counter=0),
            semantics='ordered native writes and control intervals, not target notes',
            limitations=['active LFO oscillator phase is unmodeled',
                'reference waveform/noise/LFO behavior is not a hardware-equivalence claim'],
            issues=self.issues)
        (root / f'{stem}.huc6280.source.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')


def analyze(raw):
    header = read_vgm_header(raw)
    clock_raw = header.get('huc6280_clock_raw', 0)
    clock_hz = clock_raw & 0x3fffffff
    runtime = Runtime(clock_hz)
    writes, states, segments, issues = [], [], [], []
    if clock_raw & 0x40000000:
        issues.append('dual_huc6280_header_unsupported')
    if clock_raw & 0x80000000:
        issues.append('unknown_huc6280_clock_flag')
    initial = runtime.snapshot()
    pending = {ch: (0, None, initial) for ch in range(6)}
    end = 0

    def close(channel, tick, event_id):
        start, start_id, snapshot = pending[channel]
        current = runtime.snapshot()
        if tick > start:
            segments.append(Segment(channel, start, tick, start_id, event_id,
                snapshot.channels[channel], snapshot.global_balance, snapshot.lfo_frequency,
                snapshot.lfo_control, snapshot.native_frame, current.native_frame,
                current.channels[channel].index, current.channels[channel].counter))

    for event_id, command in enumerate(command_times(raw)):
        end = command.vgmticks + command.wait_samples
        if command.command != 0xb9:
            continue
        if runtime.rate_hz > 0:
            target = -(-command.vgmticks * runtime.rate_hz // 44100)
            runtime.advance(target - runtime.native_frame)
        offset = command.address
        address, value = raw[offset + 1:offset + 3]
        register, instance = address & 127, address >> 7
        write = Write(event_id, event_id, offset, command.vgmticks, register, value, instance)
        writes.append(write)
        if instance:
            issues.append('second_huc6280_write_unsupported')
            continue
        if register > 9:
            issues.append(f'unsupported_register_{register:02x}')
        selected = runtime.selected_channel
        affected = (tuple(range(6)) if register == 1 else (0, 1) if register in (8, 9)
                    else (selected,) if 2 <= register <= 7 and selected < 6 else ())
        for channel in affected:
            close(channel, command.vgmticks, event_id)
        previous = runtime.channels[selected]['control']
        runtime.write(register, value)
        snapshot = runtime.snapshot()
        states.append(StateEvent(write, snapshot,
            register == 4 and not previous & 128 and bool(value & 128),
            register == 4 and bool(previous & 64) and not value & 64))
        for channel in affected:
            pending[channel] = (command.vgmticks, event_id, snapshot)
    if runtime.rate_hz > 0:
        target = -(-end * runtime.rate_hz // 44100)
        runtime.advance(target - runtime.native_frame)
    for channel in range(6):
        close(channel, end, None)
    if writes and not clock_hz:
        issues.append('missing_huc6280_clock')
    return Trace(end, clock_raw, clock_hz, tuple(writes), tuple(states),
        tuple(sorted(segments, key=lambda s: (s.start_vgmticks, s.channel))),
        tuple(runtime.waveforms), runtime.snapshot(), tuple(dict.fromkeys(issues)))
