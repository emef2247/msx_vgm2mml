"""Serialize accepted musical controls into one ordered PSG/SCC/OPLL VGM.

No MML parser, compiler, emulator or source-command replay is used here.
The plan has already chosen notes, curves, global operations and timing.
"""
from pathlib import Path
import csv
import json
import struct


def scheduled_writes(plan):
    """Lower typed musical events while maintaining shared hardware registers."""
    writes = []
    ay = [0] * 16
    ay[7] = 63
    scc_enable = 0
    opll = [0] * 64
    native_rhythm, overlay_rhythm = 0, 0
    overlay_mode = False
    native_rhythm_volumes = {0x36: 0, 0x37: 0, 0x38: 0}
    overlay_levels = {}
    scc_volumes = [0] * 5
    scc_gates = [False] * 5
    psg_volumes = [0] * 3
    psg_envelopes = [False] * 3
    psg_modes = [0] * 3
    psg_gates = [False] * 3
    active_chips = {c.chip for c in plan.controls}

    def emit(chip, register, data, control=None, *, port=0, sample=0, reason='initial_state'):
        if control is not None:
            sample = control.sample
            reason = control.kind
        if chip == 'psg':
            command = bytes((0xa0, register, data))
            ay[register] = data
        elif chip == 'scc':
            command = bytes((0xd2, port, register, data))
        else:
            command = bytes((0x51, register, data))
            opll[register] = data
        writes.append(dict(write_id=len(writes), sample=sample, chip=chip,
            register=register, port=port, data=data, command_hex=command.hex(),
            unit_id=control.unit_id if control else None,
            source_sample=control.source_sample if control else None,
            source_event_id=control.source_event_id if control else None,
            source_indices=control.source_indices if control else (), reason=reason,
            origin=control.origin if control else 'reset_assumption'))

    if 'psg' in active_chips:
        emit('psg', 7, 63)
        for ch in range(3):
            emit('psg', 8 + ch, 0)
    if 'scc' in active_chips:
        emit('scc', 0, 0, port=3)
        for ch in range(5):
            emit('scc', ch, 0, port=2)
    if 'opll' in active_chips:
        for register in (*range(8), 0x0e, *range(0x10, 0x19), *range(0x20, 0x29), *range(0x30, 0x39)):
            emit('opll', register, 0)

    def psg_mix(control):
        mixer = ay[7] & 0xc0 | 63
        for ch in range(3):
            mode = psg_modes[ch] if psg_gates[ch] else 0
            if mode & 1:
                mixer &= ~(1 << ch)
            if mode & 2:
                mixer &= ~(1 << (ch + 3))
        emit('psg', 7, mixer, control)

    for control in plan.ordered_controls():
        chip, ch, kind, value = control.chip, control.channel, control.kind, control.value
        if chip == 'psg':
            if kind == 'pitch':
                emit(chip, 2 * ch, value[0] & 255, control)
                emit(chip, 2 * ch + 1, value[0] >> 8, control)
            elif kind == 'volume':
                psg_volumes[ch] = value[0]
                emit(chip, 8 + ch, 16 if psg_envelopes[ch] else value[0], control)
            elif kind == 'gate':
                psg_gates[ch] = bool(value[0])
                psg_mix(control)
            elif kind == 'psg_mode':
                psg_modes[ch] = value[0]
                psg_mix(control)
            elif kind == 'psg_noise':
                emit(chip, 6, value[0], control)
            elif kind == 'psg_envelope_enable':
                psg_envelopes[ch] = bool(value[0])
                emit(chip, 8 + ch, 16 if value[0] else psg_volumes[ch], control)
            elif kind == 'psg_envelope_period':
                emit(chip, 11, value[0] & 255, control)
                emit(chip, 12, value[0] >> 8, control)
            elif kind == 'psg_envelope_shape':
                # A repeated equal value still retriggers hardware.
                emit(chip, 13, value[0], control)
        elif chip == 'scc':
            if kind == 'pitch':
                emit(chip, 2 * ch, value[0] & 255, control, port=1)
                emit(chip, 2 * ch + 1, value[0] >> 8, control, port=1)
            elif kind == 'volume':
                scc_volumes[ch] = value[0]
                emit(chip, ch, value[0], control, port=2)
            elif kind == 'gate':
                scc_gates[ch] = bool(value[0])
                scc_enable = sum(1 << index for index, enabled in enumerate(scc_gates) if enabled)
                emit(chip, 0, scc_enable, control, port=3)
            elif kind == 'waveform':
                for index, byte in enumerate(value):
                    emit(chip, min(ch, 3) * 32 + index, byte, control, port=0)
            elif kind == 'wave_write':
                slot, index, byte = value
                emit(chip, slot * 32 + index, byte, control, port=0)
        else:
            if kind == 'pitch':
                fnum, block, sustain = value
                emit(chip, 0x10 + ch, fnum & 255, control)
                high = (opll[0x20 + ch] & 16) | (fnum >> 8) | (block << 1) | (sustain << 5)
                emit(chip, 0x20 + ch, high, control)
            elif kind == 'volume':
                emit(chip, 0x30 + ch, (opll[0x30 + ch] & 0xf0) | (15 - value[0]), control)
            elif kind == 'instrument':
                emit(chip, 0x30 + ch, value[0] << 4 | (opll[0x30 + ch] & 15), control)
            elif kind == 'gate':
                emit(chip, 0x20 + ch, (opll[0x20 + ch] & ~16) | (16 if value[0] else 0), control)
            elif kind == 'patch_write':
                emit(chip, value[0], value[1], control)
            elif kind == 'rhythm_register':
                register, data = value
                if register == 0x0e:
                    native_rhythm = data & 31
                    overlay_rhythm &= ~native_rhythm
                    data = data | overlay_rhythm | (32 if overlay_mode else 0)
                elif register in native_rhythm_volumes:
                    native_rhythm_volumes[register] = data
                    for instrument, (bit, address, shift) in enumerate(((16,0x36,0),(8,0x37,0),
                            (4,0x38,4),(2,0x38,0),(1,0x37,4))):
                        if register == address and overlay_rhythm & bit:
                            data = (data & ~(15 << shift)) | ((15 - overlay_levels[instrument]) << shift)
                emit(chip, register, data, control)
            elif kind == 'percussion':
                instrument, volume, enabled = value
                bit = (16, 8, 4, 2, 1)[instrument]
                overlay_mode = True
                if enabled:
                    # Preserve other native/overlay bits and volume nibbles.
                    overlay_rhythm &= ~bit
                    emit(chip, 0x0e, 32 | native_rhythm | overlay_rhythm, control)
                    reg, shift = ((0x36, 0), (0x37, 0), (0x38, 4), (0x38, 0), (0x37, 4))[instrument]
                    data = (opll[reg] & ~(15 << shift)) | ((15 - volume) << shift)
                    emit(chip, reg, data, control)
                    overlay_rhythm |= bit
                    overlay_levels[instrument] = volume
                else:
                    overlay_rhythm &= ~bit
                    reg, shift = ((0x36, 0), (0x37, 0), (0x38, 4), (0x38, 0), (0x37, 4))[instrument]
                    data = (opll[reg] & ~(15 << shift)) | (native_rhythm_volumes[reg] & (15 << shift))
                    emit(chip, reg, data, control)
                emit(chip, 0x0e, 32 | native_rhythm | overlay_rhythm, control)
    # Termination belongs to finite playback. Loop plans must supply their
    # explicit re-entry controls instead of an invented all-channel reset.
    if plan.song_loop_sample is None:
        for chip in sorted(active_chips):
            if chip == 'psg':
                emit(chip, 7, 63, sample=plan.end_sample, reason='finite_end')
                for ch in range(3):
                    emit(chip, 8 + ch, 0, sample=plan.end_sample, reason='finite_end')
            elif chip == 'scc':
                emit(chip, 0, 0, port=3, sample=plan.end_sample, reason='finite_end')
            else:
                for ch in range(9):
                    emit(chip, 0x20 + ch, opll[0x20 + ch] & ~16,
                         sample=plan.end_sample, reason='finite_end')
                emit(chip, 0x0e, opll[0x0e] & 32, sample=plan.end_sample, reason='finite_end')
    return tuple(writes)


def write_vgm(plan, path, *, gd3=None, mapping_path=None):
    """Encode one VGM with global sample time; return inspectable write rows."""
    if dict(plan.metadata).get('target_profile') == 'native':
        from native_vgm import write_native_vgm
        if plan.source_performance is None:
            raise ValueError('Native VGM profile requires source-native musical information')
        return write_native_vgm(plan.source_performance, path, gd3=gd3,
            mapping_path=mapping_path, source_loop=plan.song_loop_sample is not None)
    writes = scheduled_writes(plan)
    body = bytearray()
    cursor, loop_address = 0, None

    def advance(sample):
        nonlocal cursor, loop_address
        if sample < cursor:
            raise ValueError('Scheduled musical writes move backwards')
        boundary = plan.song_loop_sample
        if boundary is not None and loop_address is None and cursor <= boundary <= sample:
            wait(boundary - cursor)
            cursor = boundary
            loop_address = 256 + len(body)
        wait(sample - cursor)
        cursor = sample

    def wait(samples):
        while samples:
            count = min(65535, samples)
            body.extend(b'\x61' + struct.pack('<H', count))
            samples -= count

    mapped = []
    for row in writes:
        advance(row['sample'])
        mapped.append(dict(row, target_command_address=256 + len(body)))
        body.extend(bytes.fromhex(row['command_hex']))
    advance(plan.end_sample)
    body.append(0x66)
    raw = bytearray(256)
    raw[:4] = b'Vgm '
    for offset, value in ((8, 0x171), (0x34, 256 - 0x34), (0x18, plan.end_sample)):
        struct.pack_into('<I', raw, offset, value)
    chips = {c.chip for c in plan.controls}
    clocks = dict(plan.chip_clocks)
    for chip, offset, default in (('psg', 0x74, 1789773), ('scc', 0x9c, 1789773), ('opll', 0x10, 3579545)):
        if chip in chips:
            struct.pack_into('<I', raw, offset, clocks.get(chip, default))
    if 'psg' in chips:
        raw[0x78] = 0x10
    if loop_address is not None:
        struct.pack_into('<I', raw, 0x1c, loop_address - 0x1c)
        struct.pack_into('<I', raw, 0x20, plan.end_sample - plan.song_loop_sample)
    raw.extend(body)
    if gd3:
        if gd3[:4] != b'Gd3 ' or len(gd3) < 12:
            raise ValueError('Expected a complete encoded GD3 block')
        if int.from_bytes(gd3[8:12], 'little') + 12 != len(gd3):
            raise ValueError('GD3 declared length differs from the supplied block')
        struct.pack_into('<I', raw, 0x14, len(raw) - 0x14)
        raw.extend(gd3)
    struct.pack_into('<I', raw, 4, len(raw) - 4)
    if loop_address is not None:
        validate_loop_registers(raw)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    if mapping_path is not None:
        with Path(mapping_path).open('w', newline='', encoding='utf-8') as stream:
            fields = list(mapped[0]) if mapped else ['write_id', 'sample', 'chip', 'target_command_address']
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for row in mapped:
                writer.writerow({k: json.dumps(v) if isinstance(v, tuple) else v for k, v in row.items()})
    return tuple(mapped)


def validate_loop_registers(raw):
    """Check audible register dependencies, not oscillator/envelope phase.

    No synthetic loop-entry reset is inserted. Every held voice and shared
    patch/RAM dependency must be restored by the planned loop operations.
    """
    from vgm_timing import command_times
    from vgm_loop import read_loop_metadata
    loop = read_loop_metadata(raw)
    if loop['status'] != 'valid':
        raise ValueError('Generated song loop is not a valid command boundary')
    commands = list(command_times(raw))
    ay, opll, scc = [0] * 16, [0] * 64, {}

    def snapshot():
        psg = tuple((ay[ch * 2] + 256 * ay[ch * 2 + 1], ay[ch + 8],
                     (ay[7] >> ch) & 9, ay[6] if not ay[7] & (1 << (ch + 3)) else None,
                     tuple(ay[11:14]) if ay[ch + 8] & 16 else ())
                    if ay[ch + 8] and (ay[7] & (9 << ch)) != (9 << ch) else None for ch in range(3))
        voices = tuple((scc.get((1, ch * 2), 0) + 256 * scc.get((1, ch * 2 + 1), 0),
                        scc.get((2, ch), 0),
                        tuple(scc.get((0, min(ch, 3) * 32 + n), 0) for n in range(32)))
                       if scc.get((3, 0), 0) & (1 << ch) and scc.get((2, ch), 0) else None for ch in range(5))
        fm = tuple((opll[0x10 + ch], opll[0x20 + ch], opll[0x30 + ch],
                    tuple(opll[:8]) if not opll[0x30 + ch] >> 4 else ())
                   if opll[0x20 + ch] & 16 and (ch < 6 or not opll[14] & 32) else None for ch in range(9))
        rhythm = tuple(opll[reg] for reg in (14, 0x16, 0x17, 0x18, 0x26, 0x27, 0x28, 0x36, 0x37, 0x38)) if opll[14] & 31 else ()
        return psg, voices, fm, rhythm

    def traverse(items):
        result = []
        for command in items:
            pos = command.address
            if command.command == 0xa0:
                ay[raw[pos + 1]] = raw[pos + 2]
            elif command.command == 0x51:
                opll[raw[pos + 1]] = raw[pos + 2]
            elif command.command == 0xd2:
                scc[(raw[pos + 1], raw[pos + 2])] = raw[pos + 3]
            if command.wait_samples and command.address >= loop['loop_address']:
                result.append((command.wait_samples, snapshot()))
        return result
    first = traverse(commands)
    second = traverse([c for c in commands if c.address >= loop['loop_address']])
    if first != second:
        raise ValueError('Song-loop register dependencies differ on re-entry; explicit musical restoration is required')
