"""Native NES APU evidence: register writes replayed through the frame
sequencer so hardware envelopes, sweeps and counters become intervals.

The frame sequencer, length counters, linear counter, envelope generators
and sweep units are re-executed on the source clock; the emitted segments
retain the derived pitch/volume state, not target notes. DPCM sample
playback and FDS registers are recorded as evidence, not analyzed.
"""
from dataclasses import dataclass, asdict, replace
from pathlib import Path
import csv
import json
import math
import struct

from vgm_io import read_vgm_header
from vgm_timing import command_times

LENGTH_TABLE = (10, 254, 20, 2, 40, 4, 80, 6, 160, 8, 60, 10, 14, 12, 26, 14,
                12, 16, 24, 18, 48, 20, 96, 22, 192, 24, 72, 26, 16, 28, 32, 30)
NOISE_PERIODS = (4, 8, 16, 32, 64, 96, 128, 160, 202, 254, 380, 508, 762,
                 1016, 2034, 4068)
DMC_RATE_PERIODS = (428, 380, 340, 320, 286, 254, 226, 214, 190, 160, 142,
                    128, 106, 84, 72, 54)
SLICE_SAMPLES = 735  # one 1/60 s tick at 44100 Hz
# (offset cycles from frame start, clocks quarter frame, clocks half frame)
FRAME_STEPS = {
    0: ((7457, True, False), (14913, True, True), (22371, True, False),
        (29828, True, True)),
    1: ((7457, True, False), (14913, True, True), (22371, True, False),
        (29828, False, False), (37281, True, True)),
}
FRAME_LENGTH = {0: 29828, 1: 37281}
PULSE_REGS = {0: (0, 1, 2, 3), 1: (4, 5, 6, 7)}
LENGTH_LOAD_REGS = (3, 7, 11, 15)


@dataclass(frozen=True)
class Write:
    event_id: int
    source_event_id: int
    address: int
    vgmticks: int
    register: int
    value: int


MOD_TABLE_STEPS = {0: 0, 1: 1, 2: 2, 3: 4, 4: None, 5: -4, 6: -2, 7: -1}
FDS_MASTER_VOLUMES = (1.0, 2 / 3, 2 / 4, 2 / 5)


def fds_pitch_ratio(counter, gain):
    """Modulated pitch multiplier from the NESdev FDS formula."""
    temp = counter * gain
    if (temp & 0x0f) and not (temp & 0x800):
        temp += 0x20
    temp += 0x400
    temp = (temp >> 4) & 0xff
    return temp / 64


@dataclass(frozen=True)
class ChannelView:
    """One channel's state over a segment: derived audibility plus the raw
    control registers, so a segment row is self-contained evidence."""
    channel: int
    kind: str
    audible: bool
    period: int
    duty: int
    volume: int
    lfsr_mode: int
    noise_period_index: int
    control: int = 0
    sweep: int = 0
    wave_id: int = -1
    mod_ratio: float = 1.0


@dataclass(frozen=True)
class Segment:
    channel: int
    start_vgmticks: int
    end_vgmticks: int
    start_event_id: int | None
    end_event_id: int | None
    state: ChannelView

    @property
    def active(self):
        return self.state.audible


@dataclass(frozen=True)
class DpcmEvent:
    vgmticks: int
    address: int
    length_bytes: int
    rate_index: int
    loop: bool
    level: int = 0


@dataclass(frozen=True)
class DpcmSlice:
    """One 1/60 s slice of DPCM playback: the decoded waveform averaged
    into 32 cells plus the slice peak as a 0..15 volume, so a wavetable
    channel running at a 60 Hz cycle reproduces the slice."""
    start_vgmticks: int
    end_vgmticks: int
    cells: tuple
    volume: int
    event_index: int


def lfsr_tick_cells(clock_hz, period_index, mode, ticks):
    """Yield successive per-tick 32-cell waveforms of the APU noise LFSR.

    The sequence is generated from the canonical seed at the segment
    start (hardware phase continuity across segments is not preserved;
    inaudible for noise). Cell values are bipolar around 0.
    """
    bits_per_tick = clock_hz / NOISE_PERIODS[period_index] / 60
    state = 1
    bits = []
    for _ in range(int(bits_per_tick * ticks) + 2):
        bits.append(state & 1)
        feedback = (state & 1) ^ ((state >> (6 if mode else 1)) & 1)
        state = (state >> 1) | (feedback << 14)
    for tick in range(ticks):
        base = tick * bits_per_tick
        cells = []
        for cell in range(32):
            a = base + bits_per_tick * cell / 32
            b = base + bits_per_tick * (cell + 1) / 32
            lo = int(a)
            hi = min(len(bits), max(lo + 1, math.ceil(b)))
            window = bits[lo:hi] or [bits[-1]]
            cells.append(round((sum(window) / len(window) * 2 - 1) * 110))
        yield tuple(cells)


class _Envelope:
    __slots__ = ('divider', 'decay', 'start')

    def __init__(self):
        self.divider = 0
        self.decay = 0
        self.start = False

    def clock(self, param, loop):
        if self.start:
            self.start = False
            self.decay = 15
            self.divider = param
        elif self.divider > 0:
            self.divider -= 1
        else:
            self.divider = param
            if self.decay > 0:
                self.decay -= 1
            elif loop:
                self.decay = 15


class _Pulse:
    __slots__ = ('control', 'sweep', 'period', 'length', 'envelope',
                 'sweep_divider', 'sweep_reload')

    def __init__(self):
        self.control = 0
        self.sweep = 0
        self.period = 0
        self.length = 0
        self.envelope = _Envelope()
        self.sweep_divider = 0
        self.sweep_reload = False

    @property
    def sweep_target(self):
        shift = self.sweep & 7
        if not shift:
            return self.period
        change = self.period >> shift
        if self.sweep & 8:
            return self.period - change
        return self.period + change

    @property
    def sweep_muted(self):
        return self.period < 8 or self.sweep_target > 0x7ff

    def clock_sweep(self, negate_ones_complement):
        if self.sweep_reload:
            self.sweep_divider = (self.sweep >> 4) & 7
            self.sweep_reload = False
        elif self.sweep_divider > 0:
            self.sweep_divider -= 1
        else:
            self.sweep_divider = (self.sweep >> 4) & 7
            if self.sweep & 128 and self.sweep & 7 and not self.sweep_muted:
                target = self.sweep_target
                if self.sweep & 8 and negate_ones_complement:
                    target -= 1
                self.period = target

    def volume(self):
        if self.control & 16:
            return self.control & 15
        return self.envelope.decay


class _Fds:
    """FDS (2C33) audio state: envelopes and modulator re-executed."""

    __slots__ = ('vol_control', 'mod_control', 'vol_gain', 'mod_gain',
                 'vol_next', 'mod_next', 'freq', 'freq_high', 'mod_freq',
                 'mod_high', 'mod_counter', 'mod_acc', 'mod_base',
                 'carry_next', 'mod_table', 'wave', 'master_volume',
                 'wave_write_enable', 'env_master', 'seen')

    def __init__(self):
        self.vol_control = 0x80  # BIOS reset state: fixed gain 0
        self.mod_control = 0x80
        self.vol_gain = 0
        self.mod_gain = 0
        self.vol_next = math.inf
        self.mod_next = math.inf
        self.freq = 0
        self.freq_high = 0
        self.mod_freq = 0
        self.mod_high = 0
        self.mod_counter = 0
        self.mod_acc = 0
        self.mod_base = 0.0
        self.carry_next = math.inf
        self.mod_table = [0] * 32
        self.wave = [0] * 64
        self.master_volume = 0
        self.wave_write_enable = False
        self.env_master = 0
        self.seen = False


class Runtime:
    """Mutable NES APU model; derived views are immutable snapshots."""

    def __init__(self, clock_hz):
        self.clock_hz = clock_hz
        self.pulses = [_Pulse(), _Pulse()]
        self.tri_period = 0
        self.tri_control = 0
        self.tri_length = 0
        self.tri_linear = 0
        self.tri_reload_value = 0
        self.tri_reload = False
        self.noise_control = 0
        self.noise_mode_period = 0
        self.noise_length = 0
        self.noise_envelope = _Envelope()
        self.status = 0
        self.dmc = dict(control=0, level=0, address=0, length=0)
        self.dmc_bytes_remaining = 0
        self.frame_mode = 0
        self.frame_start = 0.0
        self.frame_step = 0
        self.dpcm_events = []
        self.fds = _Fds()
        self.fds_waves = []
        self._fds_wave_ids = {}

    # -- frame sequencer -------------------------------------------------
    def _next_step_cycle(self):
        steps = FRAME_STEPS[self.frame_mode]
        return self.frame_start + steps[self.frame_step][0]

    def advance_to(self, cycle, on_step=None):
        """Run frame steps scheduled at or before ``cycle`` (CPU cycles).

        ``on_step`` is called with the sample time of each step immediately
        after that step's clocks, while the derived state matches the step.
        """
        fired = []
        while self.clock_hz:
            frame_at = self._next_step_cycle()
            fds_at = self._fds_next_at()
            if min(frame_at, fds_at) > cycle:
                break
            if fds_at <= frame_at:
                self._fds_process(fds_at)
                sample = round(fds_at * 44100 / self.clock_hz)
                fired.append(sample)
                if on_step is not None:
                    on_step(sample)
                continue
            at = frame_at
            _, quarter, half = FRAME_STEPS[self.frame_mode][self.frame_step]
            if quarter:
                self._clock_quarter()
            if half:
                self._clock_half()
            sample = round(at * 44100 / self.clock_hz)
            fired.append(sample)
            if on_step is not None:
                on_step(sample)
            self.frame_step += 1
            if self.frame_step == len(FRAME_STEPS[self.frame_mode]):
                self.frame_step = 0
                self.frame_start += FRAME_LENGTH[self.frame_mode]
        return fired

    def _clock_quarter(self):
        for pulse in self.pulses:
            pulse.envelope.clock(pulse.control & 15, bool(pulse.control & 32))
        self.noise_envelope.clock(self.noise_control & 15,
                                  bool(self.noise_control & 32))
        if self.tri_reload:
            self.tri_linear = self.tri_reload_value
        elif self.tri_linear > 0:
            self.tri_linear -= 1
        if not self.tri_control & 128:
            self.tri_reload = False

    def _clock_half(self):
        for index, pulse in enumerate(self.pulses):
            if not pulse.control & 32 and pulse.length > 0:
                pulse.length -= 1
            pulse.clock_sweep(index == 0)
        if not self.tri_control & 128 and self.tri_length > 0:
            self.tri_length -= 1
        if not self.noise_control & 32 and self.noise_length > 0:
            self.noise_length -= 1

    # -- register writes ---------------------------------------------------
    def write(self, register, value, vgmticks):
        if register in PULSE_REGS[0] or register in PULSE_REGS[1]:
            index = 0 if register < 4 else 1
            pulse = self.pulses[index]
            slot = register & 3
            if slot == 0:
                pulse.control = value
            elif slot == 1:
                pulse.sweep = value
                pulse.sweep_reload = True
            elif slot == 2:
                pulse.period = (pulse.period & 0x700) | value
            else:
                pulse.period = (pulse.period & 0xff) | ((value & 7) << 8)
                if self.status & (1 << index):
                    pulse.length = LENGTH_TABLE[value >> 3]
                pulse.envelope.start = True
        elif register == 8:
            self.tri_control = value
            self.tri_reload_value = value & 127
        elif register == 10:
            self.tri_period = (self.tri_period & 0x700) | value
        elif register == 11:
            self.tri_period = (self.tri_period & 0xff) | ((value & 7) << 8)
            if self.status & 4:
                self.tri_length = LENGTH_TABLE[value >> 3]
            self.tri_reload = True
        elif register == 12:
            self.noise_control = value
        elif register == 14:
            self.noise_mode_period = value
        elif register == 15:
            if self.status & 8:
                self.noise_length = LENGTH_TABLE[value >> 3]
            self.noise_envelope.start = True
        elif register == 16:
            self.dmc['control'] = value
        elif register == 17:
            self.dmc['level'] = value & 127
        elif register == 18:
            self.dmc['address'] = value
        elif register == 19:
            self.dmc['length'] = value
        elif register == 21:
            self.status = value & 31
            if not value & 1:
                self.pulses[0].length = 0
            if not value & 2:
                self.pulses[1].length = 0
            if not value & 4:
                self.tri_length = 0
            if not value & 8:
                self.noise_length = 0
            if value & 16:
                if self.dmc_bytes_remaining == 0:
                    self.dmc_bytes_remaining = self.dmc['length'] * 16 + 1
                    self.dpcm_events.append(DpcmEvent(vgmticks,
                        0xc000 + self.dmc['address'] * 64,
                        self.dmc_bytes_remaining,
                        self.dmc['control'] & 15,
                        bool(self.dmc['control'] & 64),
                        self.dmc['level']))
            else:
                self.dmc_bytes_remaining = 0
        elif register == 23:
            self.frame_mode = 1 if value & 128 else 0
            self.frame_start = self._cycle(vgmticks)
            self.frame_step = 0
            if value & 128:
                self._clock_quarter()
                self._clock_half()

    def _cycle(self, vgmticks):
        return vgmticks * self.clock_hz / 44100 if self.clock_hz else 0.0

    # -- FDS (2C33) ---------------------------------------------------------
    def _fds_env_period(self, control):
        fds = self.fds
        if control & 0x80 or fds.env_master == 0 or fds.freq_high & 0x40:
            return None
        period = 8 * ((control & 0x3f) + 1) * (fds.env_master + 1)
        if fds.freq_high & 0x80:
            period = max(1, period // 4)
        return period

    def _fds_schedule_env(self, which, from_cycle):
        fds = self.fds
        control = fds.vol_control if which == 'vol' else fds.mod_control
        period = self._fds_env_period(control)
        setattr(fds, f'{which}_next',
                math.inf if period is None else from_cycle + period)

    def _fds_schedule_carry(self, from_cycle):
        fds = self.fds
        if (not fds.mod_freq or fds.mod_high & 0x80 or fds.freq_high & 0x80):
            fds.carry_next = math.inf
            return
        if fds.mod_high & 0x40:
            ticks = 1
        else:
            ticks = -(-(4096 - fds.mod_acc % 4096) // fds.mod_freq)
        fds.mod_base = from_cycle
        fds.carry_next = from_cycle + ticks * 16

    def _fds_tick_env(self, which):
        fds = self.fds
        control = fds.vol_control if which == 'vol' else fds.mod_control
        gain = fds.vol_gain if which == 'vol' else fds.mod_gain
        if control & 0x40:
            gain = gain + 1 if gain < 32 else gain
        else:
            gain = gain - 1 if gain > 0 else gain
        if which == 'vol':
            fds.vol_gain = gain
        else:
            fds.mod_gain = gain
        period = self._fds_env_period(control)
        setattr(fds, f'{which}_next',
                math.inf if period is None
                else getattr(fds, f'{which}_next') + period)

    def _fds_carry(self):
        fds = self.fds
        ticks = round((fds.carry_next - fds.mod_base) / 16)
        fds.mod_acc = (fds.mod_acc + fds.mod_freq * ticks) & 0x3ffff
        entry = fds.mod_table[(fds.mod_acc >> 13) & 31]
        step = MOD_TABLE_STEPS[entry]
        if step is None:
            fds.mod_counter = 0
        else:
            fds.mod_counter = ((fds.mod_counter + step + 64) % 128) - 64
        self._fds_schedule_carry(fds.carry_next)

    def _fds_next_at(self):
        fds = self.fds
        if not fds.seen:
            return math.inf
        return min(fds.vol_next, fds.mod_next, fds.carry_next)

    def _fds_process(self, at_cycle):
        fds = self.fds
        if fds.vol_next <= at_cycle:
            self._fds_tick_env('vol')
        if fds.mod_next <= at_cycle:
            self._fds_tick_env('mod')
        if fds.carry_next <= at_cycle:
            self._fds_carry()

    def write_fds(self, register, value, vgmticks):
        fds = self.fds
        fds.seen = True
        cycle = self._cycle(vgmticks)
        if 0x40 <= register <= 0x7f:
            if fds.wave_write_enable:
                fds.wave[register - 0x40] = value & 63
            return
        if register == 0x20:
            fds.vol_control = value
            if value & 0x80:
                fds.vol_gain = value & 0x3f
            self._fds_schedule_env('vol', cycle)
        elif register == 0x22:
            fds.freq = (fds.freq & 0xf00) | value
        elif register == 0x23:
            fds.freq = (fds.freq & 0xff) | ((value & 0x0f) << 8)
            fds.freq_high = value
            self._fds_schedule_env('vol', cycle)
            self._fds_schedule_env('mod', cycle)
            self._fds_schedule_carry(cycle)
        elif register == 0x24:
            fds.mod_control = value
            if value & 0x80:
                fds.mod_gain = value & 0x3f
            self._fds_schedule_env('mod', cycle)
        elif register == 0x25:
            counter = value & 0x7f
            fds.mod_counter = counter - 128 if counter >= 64 else counter
        elif register == 0x26:
            fds.mod_freq = (fds.mod_freq & 0xf00) | value
            self._fds_schedule_carry(cycle)
        elif register == 0x27:
            fds.mod_freq = (fds.mod_freq & 0xff) | ((value & 0x0f) << 8)
            fds.mod_high = value
            if value & 0x80:
                fds.mod_acc &= 0x3e000
            self._fds_schedule_carry(cycle)
        elif register == 0x28:
            if fds.mod_high & 0x80:
                fds.mod_table[(fds.mod_acc >> 13) & 31] = value & 7
                fds.mod_acc = (fds.mod_acc + 8192) & 0x3ffff
        elif register == 0x29:
            fds.wave_write_enable = bool(value & 0x80)
            fds.master_volume = value & 3
        elif register == 0x2a:
            fds.env_master = value
            self._fds_schedule_env('vol', cycle)
            self._fds_schedule_env('mod', cycle)

    def _fds_wave_id(self):
        key = tuple(self.fds.wave)
        if key not in self._fds_wave_ids:
            self._fds_wave_ids[key] = len(self.fds_waves)
            self.fds_waves.append(key)
        return self._fds_wave_ids[key]

    def _fds_view(self):
        fds = self.fds
        gain = min(fds.vol_gain, 32)
        volume = round(15 * (gain / 32) * FDS_MASTER_VOLUMES[fds.master_volume])
        halted = bool(fds.freq_high & 0x80) or fds.wave_write_enable
        return ChannelView(4, 'fds',
            volume > 0 and fds.freq > 0 and not halted,
            fds.freq, 0, volume, 0, 0, fds.vol_control, fds.mod_control,
            self._fds_wave_id(),
            fds_pitch_ratio(fds.mod_counter, fds.mod_gain))

    # -- derived views -----------------------------------------------------
    def views(self):
        result = []
        for index, pulse in enumerate(self.pulses):
            volume = pulse.volume()
            result.append(ChannelView(index, 'pulse',
                pulse.length > 0 and not pulse.sweep_muted and volume > 0,
                pulse.period, pulse.control >> 6, volume, 0, 0,
                pulse.control, pulse.sweep))
        result.append(ChannelView(2, 'triangle',
            self.tri_length > 0 and self.tri_linear > 0,
            self.tri_period, 0, 15, 0, 0, self.tri_control, 0))
        volume = (self.noise_control & 15 if self.noise_control & 16
                  else self.noise_envelope.decay)
        result.append(ChannelView(3, 'noise',
            self.noise_length > 0 and volume > 0, 0, 0, volume,
            1 if self.noise_mode_period & 128 else 0,
            self.noise_mode_period & 15, self.noise_control,
            self.noise_mode_period))
        if self.fds.seen:
            result.append(self._fds_view())
        return tuple(result)


@dataclass(frozen=True)
class Trace:
    source_end_vgmticks: int
    clock_raw: int
    clock_hz: int
    writes: tuple[Write, ...]
    segments: tuple[Segment, ...]
    retriggers: tuple[tuple[int, int, int], ...]
    dpcm_events: tuple[DpcmEvent, ...]
    issues: tuple[str, ...]
    dpcm_slices: tuple[DpcmSlice, ...] = ()
    fds_waves: tuple = ()

    def dump(self, outdir, stem):
        root = Path(outdir)
        root.mkdir(parents=True, exist_ok=True)
        _dump_csv(root / f'{stem}.nesapu.writes.csv',
                  [asdict(w) for w in self.writes])
        _dump_csv(root / f'{stem}.nesapu.segments.csv',
                  [dict(start_vgmticks=s.start_vgmticks,
                        end_vgmticks=s.end_vgmticks,
                        start_event_id=s.start_event_id,
                        end_event_id=s.end_event_id, **asdict(s.state))
                   for s in self.segments], 'channel')
        _dump_csv(root / f'{stem}.nesapu.dpcm.csv',
                  [asdict(e) for e in self.dpcm_events], 'vgmticks')
        _dump_csv(root / f'{stem}.nesapu.dpcm_slices.csv',
                  [dict(start_vgmticks=s.start_vgmticks,
                        end_vgmticks=s.end_vgmticks, volume=s.volume,
                        event_index=s.event_index,
                        cells=' '.join(str(c) for c in s.cells))
                   for s in self.dpcm_slices], 'start_vgmticks')
        _dump_csv(root / f'{stem}.nesapu.fds_waves.csv',
                  [dict(wave_id=index,
                        values=' '.join(str(v) for v in wave))
                   for index, wave in enumerate(self.fds_waves)],
                  'wave_id')
        report = dict(clock_raw=self.clock_raw, clock_hz=self.clock_hz,
            tick_clock_hz=44100, source_end_vgmticks=self.source_end_vgmticks,
            write_count=len(self.writes), segment_count=len(self.segments),
            dpcm_event_count=len(self.dpcm_events),
            dpcm_slice_count=len(self.dpcm_slices),
            fds_wave_count=len(self.fds_waves),
            semantics='ordered native writes replayed through the frame '
                      'sequencer; intervals of derived channel state, not '
                      'target notes',
            limitations=['frame sequencer write delay after $4017 is ignored',
                'dpcm playback is sliced into 1/60 s waveform cells; dma '
                'cycle stealing is not modeled',
                'fds volume gain changes are applied at segment '
                'resolution, not latched to wave position 0; the fds '
                'output lowpass (~2 khz) is not modeled',
                'initial sequencer phase assumes a reset at the first sample'],
            issues=self.issues)
        (root / f'{stem}.nesapu.source.json').write_text(
            json.dumps(report, indent=2) + '\n', encoding='utf-8')


def _dump_csv(path, rows, empty_column='event_id'):
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream,
                                fieldnames=list(rows[0]) if rows else [empty_column])
        writer.writeheader()
        writer.writerows(rows)


def _sample_memory(raw):
    """DPCM sample memory image from NES RAM data blocks."""
    memory, covered = {}, set()
    for command in command_times(raw):
        if command.command != 0x67:
            continue
        address = command.address
        block_type = raw[address + 2]
        if block_type not in (0xc0, 0xc1, 0xc2):
            continue
        size = struct.unpack_from('<I', raw, address + 3)[0]
        if size < 2:
            continue
        start = struct.unpack_from('<H', raw, address + 7)[0]
        for offset, byte in enumerate(raw[address + 9:address + 7 + size]):
            at = start + offset
            memory[at if at <= 0xffff else 0x8000 + at - 0x10000] = byte
            covered.add(at if at <= 0xffff else 0x8000 + at - 0x10000)
    return memory, covered


def _decode_dpcm(data, level):
    levels = []
    for byte in data:
        for bit in range(8):
            level = min(127, level + 2) if (byte >> bit) & 1 \
                else max(0, level - 2)
            levels.append(level)
    return levels


def _dpcm_slices(raw, events, writes, clock_hz, song_end, issues):
    """Slice each DPCM playback into 1/60 s waveform cells.

    A playback runs from its trigger until the sample ends, the next
    trigger, a $4015 write clearing bit 4, or the song end; looped
    samples wrap until cut. Triggers whose sample range no data block
    covered produce no slices and are reported as an issue.
    """
    if not events or not clock_hz:
        return ()
    memory, covered = _sample_memory(raw)
    disables = sorted(w.vgmticks for w in writes
                      if w.register == 21 and not w.value & 16)
    decoded = {}
    slices = []
    missing = False
    for index, event in enumerate(events):
        start = event.vgmticks
        rate_hz = clock_hz / DMC_RATE_PERIODS[event.rate_index]
        total_bits = event.length_bytes * 8
        natural_end = start + round(total_bits * 44100 / rate_hz)
        cut = song_end
        if index + 1 < len(events):
            cut = min(cut, events[index + 1].vgmticks)
        for at in disables:
            if start < at < cut:
                cut = at
                break
        end = cut if event.loop else min(natural_end, cut)
        if end <= start:
            continue
        addresses = [event.address + i if event.address + i <= 0xffff
                     else 0x8000 + event.address + i - 0x10000
                     for i in range(event.length_bytes)]
        if not any(at in covered for at in addresses):
            missing = True
            continue
        key = (event.address, event.length_bytes, event.level)
        if key not in decoded:
            data = bytes(memory.get(at, 0) for at in addresses)
            decoded[key] = _decode_dpcm(data, event.level)
        levels = decoded[key]
        at = start
        while at < end:
            slice_end = min(at + SLICE_SAMPLES, end)
            bit_a = (at - start) * rate_hz / 44100
            bit_b = (slice_end - start) * rate_hz / 44100
            if event.loop:
                bit_a %= total_bits
                bit_b = bit_a + (slice_end - at) * rate_hz / 44100
            cells = []
            for cell in range(32):
                a = bit_a + (bit_b - bit_a) * cell / 32
                b = bit_a + (bit_b - bit_a) * (cell + 1) / 32
                lo = int(a) % total_bits if event.loop else int(a)
                hi = max(lo + 1, math.ceil(b)) if not event.loop else lo + 1
                if event.loop:
                    window = [levels[(lo + j) % total_bits]
                              for j in range(max(1, int(b - a)))]
                else:
                    window = levels[lo:min(hi, total_bits)] or [levels[-1]]
                average = sum(window) / len(window)
                cells.append(max(-127, min(127, round((average - 63.5) * 1.9))))
            lo = int(bit_a)
            hi = min(total_bits, max(lo + 1, math.ceil(bit_b)))
            peak = max(levels[lo % total_bits if event.loop else lo:
                              hi if not event.loop else total_bits],
                       default=0) if not event.loop else max(
                levels[(lo + j) % total_bits]
                for j in range(max(1, int(bit_b - bit_a))))
            slices.append(DpcmSlice(at, slice_end, tuple(cells),
                                    round(peak * 15 / 127), index))
            at = slice_end
    if missing:
        issues.append('dpcm_trigger_without_sample_data')
    return tuple(slices)


def analyze(raw):
    header = read_vgm_header(raw)
    clock_raw = header.get('nes_apu_clock_raw', 0)
    clock_hz = clock_raw & 0x3fffffff
    runtime = Runtime(clock_hz)
    writes, segments, retriggers, issues = [], [], [], []
    # Some rips never write $4015 at all (the Metroid FDS pack is one):
    # the enable write happened before logging started, and players
    # start with the APU channels enabled. Length loads in such a
    # stream only make sense with the channels on, so mirror the
    # players: assume the four tone channels enabled from the start
    # and record the assumption instead of rendering the song silent.
    if not any(command.command == 0xb4 and raw[command.address + 1] == 21
               for command in command_times(raw)):
        runtime.status = 0x0f
        issues.append('no_4015_writes_channels_assumed_enabled')
    end = 0
    pending = {}

    def checkpoint(sample, event_id):
        for view in runtime.views():
            current = pending.get(view.channel)
            if current is None:
                pending[view.channel] = (sample, event_id, view)
            elif current[2] != view:
                start, start_id, previous = current
                if sample > start:
                    segments.append(Segment(view.channel, start, sample,
                                            start_id, event_id, previous))
                pending[view.channel] = (sample, event_id, view)

    checkpoint(0, None)
    for event_id, command in enumerate(command_times(raw)):
        end = command.vgmticks + command.wait_samples
        runtime.advance_to(
            command.vgmticks * clock_hz / 44100 if clock_hz else 0,
            on_step=lambda sample: checkpoint(sample, None))
        if command.command != 0xb4:
            continue
        register, value = raw[command.address + 1], raw[command.address + 2]
        writes.append(Write(event_id, event_id,
                            command.address, command.vgmticks, register, value))
        if register >= 0x80 and 'nes_apu_high_register_bit_observed' not in issues:
            issues.append('nes_apu_high_register_bit_observed')
        if 0x20 <= register <= 0x2a or 0x40 <= register <= 0x7f:
            if 'fds_registers_present' not in issues:
                issues.append('fds_registers_present')
            runtime.write_fds(register, value, command.vgmticks)
            checkpoint(command.vgmticks, event_id)
            continue
        if 0x2b <= register <= 0x2f:
            if 'fds_unknown_register_observed' not in issues:
                issues.append('fds_unknown_register_observed')
            continue
        if register in LENGTH_LOAD_REGS:
            retriggers.append((register // 4, command.vgmticks, event_id))
        runtime.write(register, value, command.vgmticks)
        if register in LENGTH_LOAD_REGS:
            channel = register // 4
            current = pending.get(channel)
            if current is not None:
                start, start_id, view = current
                if command.vgmticks > start:
                    segments.append(Segment(channel, start, command.vgmticks,
                                            start_id, event_id, view))
                view = next(v for v in runtime.views() if v.channel == channel)
                pending[channel] = (command.vgmticks, event_id, view)
        checkpoint(command.vgmticks, event_id)
    runtime.advance_to(end * clock_hz / 44100 if clock_hz else 0,
                       on_step=lambda sample: checkpoint(sample, None))
    for channel, (start, start_id, view) in pending.items():
        if end > start:
            segments.append(Segment(channel, start, end, start_id, None, view))
    segments.sort(key=lambda s: (s.channel, s.start_vgmticks))
    if runtime.dpcm_events:
        issues.append('dpcm_sample_playback_observed')
    slices = _dpcm_slices(raw, runtime.dpcm_events, writes, clock_hz, end,
                          issues)
    # Compact FDS wave ids to the waves segments actually reference
    # (wave-RAM loading passes through many transient waveforms).
    remap = {}
    waves = []
    rebuilt = []
    for segment in segments:
        if segment.channel == 4 and segment.state.wave_id >= 0:
            old = segment.state.wave_id
            if old not in remap:
                remap[old] = len(waves)
                waves.append(runtime.fds_waves[old])
            if remap[old] != old:
                segment = replace(segment,
                                  state=replace(segment.state,
                                                wave_id=remap[old]))
        rebuilt.append(segment)
    segments = rebuilt
    return Trace(end, clock_raw, clock_hz, tuple(writes), tuple(segments),
                 tuple(retriggers), tuple(runtime.dpcm_events), tuple(issues),
                 slices, tuple(waves))
