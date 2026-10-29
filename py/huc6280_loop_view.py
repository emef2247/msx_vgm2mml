"""Explicit force-only first-traversal loop view; native input stays intact."""
import hashlib
import struct

from vgm_loop import read_loop_metadata
from vgm_timing import command_times


def project_loop_view(raw, trace):
    from huc6280_projection import project, ProjectionError
    loop = read_loop_metadata(raw)
    if trace.issues or loop['status'] != 'valid':
        raise ProjectionError('HuC6280 loop approximation requires valid native evidence')
    # Restoring register state cannot restore a RAM upload cursor, DDA stream,
    # or LFO phase. Keep those paths under the ordinary eligibility checks.
    if any(s.active and (s.state.mode != 'wave' or s.lfo_control & 3)
           for s in trace.segments):
        raise ProjectionError('HuC6280 loop approximation requires waveform-only playback')
    if any(e.write.address >= loop['loop_address'] and e.write.register == 6
           for e in trace.states):
        raise ProjectionError('HuC6280 loop approximation cannot restore waveform upload pointers')
    before = [e for e in trace.states if e.write.address < loop['loop_address']]
    if not before:
        raise ProjectionError('HuC6280 loop approximation requires an observed entry state')
    entry = before[-1].state
    commands = list(command_times(raw))
    start = commands[0].address
    header, body, mapping = bytearray(raw[:start]), bytearray(), {}
    loop_at = None

    def emit(command, original):
        mapping[len(mapping)] = original
        body.extend(command)

    def write(register, value):
        emit(bytes((0xb9, register, value)), None)

    for index, command in enumerate(commands):
        if command.address == loop['loop_address']:
            loop_at = start + len(body)
            write(1, entry.global_balance)
            write(8, entry.lfo_frequency)
            write(9, entry.lfo_control)
            for state in entry.channels:
                write(0, state.channel)
                write(4, 0)
                write(2, state.frequency & 255)
                write(3, state.frequency >> 8)
                write(5, state.balance)
                write(7, state.noise_control)
                write(4, state.control)
            write(0, entry.selected_channel)
        stop = commands[index + 1].address if index + 1 < len(commands) else command.address + 1
        emit(raw[command.address:stop], index)
    result = header + body
    struct.pack_into('<I', result, 0x1c, loop_at - 0x1c)
    relative = int.from_bytes(raw[0x14:0x18], 'little')
    struct.pack_into('<I', result, 0x14, 0)
    if relative:
        at = 0x14 + relative
        end = at + 12 + int.from_bytes(raw[at + 8:at + 12], 'little')
        if raw[at:at + 4] != b'Gd3 ' or end > len(raw):
            raise ProjectionError('Invalid source GD3 metadata')
        struct.pack_into('<I', result, 0x14, len(result) - 0x14)
        result.extend(raw[at:end])
    struct.pack_into('<I', result, 4, len(result) - 4)
    projected = project(bytes(result))  # Both native-view and target loop checks still run.
    for row in (*projected.controls, *projected.writes):
        value = row['source_event_id']
        row['source_event_id'] = mapping[value] if value is not None else None
    for row in projected.gates:
        for field in ('start_source_event_id', 'end_source_event_id'):
            value = row[field]
            row[field] = mapping[value] if value is not None else None
    projected.summary.update(
        source_sha256=hashlib.sha256(raw).hexdigest(),
        force_loop_approximation=True,
        loop_approximation='restore first-traversal register state at loop entry',
        loop_entry_vgmticks=loop['loop_start_samples'],
        loop_validation='two entry-restored view traversals and independent target replay',
        native_source_unchanged=True,
        source_event_ids='original_input_command_ordinals; null for entry restoration')
    return projected
