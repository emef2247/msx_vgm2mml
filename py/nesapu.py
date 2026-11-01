"""Native NES APU evidence: register writes replayed through the frame
sequencer so hardware envelopes, sweeps and counters become intervals.

The frame sequencer, length counters, linear counter, envelope generators
and sweep units are re-executed on the source clock; the emitted segments
retain the derived pitch/volume state, not target notes. DPCM sample
playback and FDS registers are recorded as evidence, not analyzed.
"""
from dataclasses import dataclass, asdict
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
        while self.clock_hz and self._next_step_cycle() <= cycle:
            at = self._next_step_cycle()
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
        report = dict(clock_raw=self.clock_raw, clock_hz=self.clock_hz,
            tick_clock_hz=44100, source_end_vgmticks=self.source_end_vgmticks,
            write_count=len(self.writes), segment_count=len(self.segments),
            dpcm_event_count=len(self.dpcm_events),
            dpcm_slice_count=len(self.dpcm_slices),
            semantics='ordered native writes replayed through the frame '
                      'sequencer; intervals of derived channel state, not '
                      'target notes',
            limitations=['frame sequencer write delay after $4017 is ignored',
                'dpcm playback is sliced into 1/60 s waveform cells; dma '
                'cycle stealing is not modeled',
                'fds registers are retained as controls but not analyzed',
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
        if 0x20 <= register <= 0x2f or 0x40 <= register <= 0x7f:
            if 'fds_registers_present_not_analyzed' not in issues:
                issues.append('fds_registers_present_not_analyzed')
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
    return Trace(end, clock_raw, clock_hz, tuple(writes), tuple(segments),
                 tuple(retriggers), tuple(runtime.dpcm_events), tuple(issues),
                 slices)
