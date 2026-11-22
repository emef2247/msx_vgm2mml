"""SegaPCM playback reconstruction into decoded PCM assets.

The native trace (native_imports.segapcm) retains write-observed
configuration intervals only; audible gates are deliberately not
part of that evidence.  This module re-executes the channel
runtime under the VGMPlay-compatible model the project family
documents: channel RAM resets to FF (every channel disabled),
samples are unsigned bytes centred at 0x80, each output frame
(clock / 128) advances a 16.8 fixed-point address by the
programmed delta, reaching the end page stops the channel or
wraps it to the loop address, and the control register's bank
bits select the ROM window.  Uncovered ROM bytes read as 0x80.

Each gate becomes NativePCM assets at the gate's own byte rate
(clock * delta / 32768); a mid-gate delta change starts a new
asset, and other register writes are baked into the samples at
frame boundaries.  Stereo volumes fold to mono by their mean,
as in the other source PCM reconstructions.  Only the first chip
instance is decoded; the second instance's clock lives in the
extra header and is not interpreted.
"""
from fractions import Fraction

from native_music import NativePCM

_FRAME_STEP = 44100 * 128  # frame index = vgmticks * clock / this


def _ceil(value):
    return -(-value.numerator // value.denominator)


class _Rom:
    def __init__(self):
        self.image = bytearray()
        self.written = bytearray()
        self.size = 0
        self.mask = 0

    def apply(self, block):
        if block.malformed_header or block.declared_rom_size is None \
                or block.start_address is None:
            return False
        size, start = block.declared_rom_size, block.start_address
        if size <= 0 or start < 0 or start + len(block.payload) > size:
            return False
        if size != self.size:
            self.image = bytearray([0x80]) * size
            self.written = bytearray(size)
            self.size = size
            self.mask = (1 << (size - 1).bit_length()) - 1
        self.image[start:start + len(block.payload)] = block.payload
        self.written[start:start + len(block.payload)] = b'\x01' * len(block.payload)
        return True

    def read(self, address):
        if not self.size:
            return 0x80, False
        address &= self.mask
        return self.image[address], bool(self.written[address])


class _Channel:
    __slots__ = ('active', 'position', 'fraction', 'gate', 'asset', 'number',
                 'zero_delta_hold')

    def __init__(self):
        self.active = False
        self.position = Fraction(0)
        self.fraction = Fraction(0)
        self.gate = None   # (start_vgmticks, source_event_id) of the open gate
        self.asset = None  # [samples, rate, start, source_ids, volumes]
        self.number = 0
        self.zero_delta_hold = False


def add_segapcm_pcm(builder):
    trace = builder.bundle['analyses'].get('segapcm')
    if trace is None:
        builder.decisions.append(('segapcm_pcm_source_issue', 'analysis_unavailable'))
        return
    if not trace.clock_hz:
        builder.decisions.append(('segapcm_pcm_source_issue', 'clock_unknown'))
        return
    for issue in trace.issues:
        builder.decisions.append(('segapcm_pcm_source_issue', issue))
    clock = trace.clock_hz
    if trace.clock_raw & 0x80000000:
        builder.decisions.append(('segapcm_pcm_source_issue', 'clock_flag_unmodeled'))
        return
    shift = trace.interface_raw & 0xff
    if shift >= 32:
        builder.decisions.append(('segapcm_pcm_source_issue', 'bank_shift_unsupported'))
        return
    mask_declared = (trace.interface_raw >> 16) & 0xff
    end = builder.bundle['source_end_sample']
    device = builder.device('segapcm', 0)
    rom = _Rom()
    ram = bytearray([0xff]) * 0x800
    channels = [_Channel() for _ in range(16)]
    holes = [0]
    frame_now = [0]

    def frame_of(vgmticks):
        return -(-vgmticks * clock // _FRAME_STEP)

    def frame_time(frame):
        return int(Fraction(frame * _FRAME_STEP, clock) + Fraction(1, 2))

    def flush(channel, at):
        state = channels[channel]
        if state.asset is not None and state.asset[0]:
            samples, rate, start, ids, vol = state.asset
            builder.pcm_assets.append(NativePCM(
                f'{device.device_id}:ch{channel}:{state.number}', device.device_id,
                start, max(at, start + 1), float(rate), tuple(samples),
                tuple(dict.fromkeys(ids)),
                (('source_encoding', 'unsigned8'), ('channel', channel),
                 ('volume_left', vol[0]), ('volume_right', vol[1]),
                 ('reconstruction', 'frame_model_byte_rate'),
                 ('stereo_fold_down', 'mean_left_right_amplitude'))))
            state.number += 1
        state.asset = None

    def advance(channel, target_frame):
        state = channels[channel]
        frames = target_frame - frame_now[0]
        if not state.active or frames <= 0:
            return
        base = channel * 8
        delta = ram[base + 7]
        if delta == 0:
            if not state.zero_delta_hold:
                state.zero_delta_hold = True
                builder.decisions.append(
                    ('segapcm_pcm_zero_delta_hold', device.device_id, channel))
            return
        rate = Fraction(clock * delta, 32768)
        if state.asset is not None and state.asset[1] != rate:
            flush(channel, frame_time(frame_now[0]))
        if state.asset is None:
            # The asset starts when bytes actually start flowing:
            # a gate keyed on with delta still zero (a common setup
            # order) sounds nothing until delta is programmed, so
            # the key-on time must not stretch the byte sequence.
            ids = []
            if state.gate is not None:
                ids = [state.gate[1]]
                state.gate = None
            state.asset = [[], rate, frame_time(frame_now[0]), ids,
                           (ram[base + 2] & 0x7f, ram[base + 3] & 0x7f)]
        samples = state.asset[0]
        vol = (ram[base + 2] & 0x7f) + (ram[base + 3] & 0x7f)
        end_page = (ram[base + 6] + 1) & 0xff
        control = ram[base + 0x86]
        loop_enabled = not control & 2
        loop_position = (ram[base + 5] << 8) | ram[base + 4]
        bank_mask = (mask_declared or 0x70) & (rom.mask >> shift) if rom.size else 0
        bank = (control & bank_mask) << shift
        step = Fraction(delta, 256)
        position = state.position
        remaining = frames
        while remaining > 0:
            if (int(position) >> 8) & 0xff == end_page:
                if loop_enabled and loop_position != int(position):
                    position = Fraction(loop_position)
                    continue
                stop_frame = frame_now[0] + (frames - remaining)
                state.active = False
                state.gate = None
                state.fraction = Fraction(0)
                flush(channel, frame_time(stop_frame))
                return
            byte_index = int(position)
            value, covered = rom.read(byte_index + bank)
            if not covered:
                holes[0] += 1
            samples.append((value - 128) * vol // 2)
            take = min(_ceil((byte_index + 1 - position) / step), remaining)
            position += step * take
            remaining -= take
        state.position = position
        state.fraction = position - int(position)

    def advance_all(target_frame):
        if target_frame <= frame_now[0]:
            return
        for channel in range(16):
            advance(channel, target_frame)
        frame_now[0] = target_frame

    ordered = sorted([*trace.writes, *trace.rom_blocks],
                     key=lambda e: e.source.event_id)
    second_instance = False
    for event in ordered:
        source = event.source
        if source.chip_instance != 0:
            second_instance = True
            continue
        advance_all(frame_of(source.vgmticks))
        if hasattr(event, 'payload'):
            if not rom.apply(event):
                builder.decisions.append(
                    ('segapcm_pcm_source_issue', 'rom_block_unusable', source.event_id))
                for channel in range(16):
                    flush(channel, source.vgmticks)
                    channels[channel].active = False
                    channels[channel].gate = None
            continue
        offset = event.ram_offset
        old = ram[offset]
        ram[offset] = event.value
        channel = event.channel
        if channel is None:
            continue
        state = channels[channel]
        base = channel * 8
        if event.role in ('programmed_address_low', 'programmed_address_high'):
            integer = (ram[base + 0x85] << 8) | ram[base + 0x84]
            state.position = Fraction(integer) + state.fraction
        elif event.role == 'control':
            if event.value & 1:
                if state.active:
                    state.active = False
                    state.gate = None
                    flush(channel, source.vgmticks)
            elif old & 1:
                integer = (ram[base + 0x85] << 8) | ram[base + 0x84]
                state.position = Fraction(integer) + state.fraction
                state.active = True
                state.zero_delta_hold = False
                state.gate = (source.vgmticks, source.source_event_id)
        if state.active and state.asset is not None:
            state.asset[3].append(source.source_event_id)
    advance_all(frame_of(end))
    for channel in range(16):
        flush(channel, end)
    if second_instance:
        builder.decisions.append(
            ('segapcm_pcm_second_instance_not_decoded', device.device_id))
    if holes[0]:
        builder.decisions.append(
            ('segapcm_pcm_rom_holes_read_as_neutral', device.device_id, holes[0]))
