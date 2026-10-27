"""Serialize a source-native musical performance, without MGS projection.

FM/PSG controls are re-encoded from typed native parameters. PCM packets are an
explicit preservation lane retaining their dependent data/stream operations.
"""
from dataclasses import asdict
import csv
import hashlib
import json
from pathlib import Path
import struct


def scheduled_native_writes(performance):
    from native_registers import encode_control
    devices = {d.device_id: d for d in performance.devices}
    rows = []
    for control in performance.controls:
        device = devices[control.device_id]
        command = encode_control(control, device)
        if not isinstance(command, bytes) or not command:
            raise ValueError(f'Native codec produced no command: {control.control_id}')
        rows.append(dict(sample=control.sample, order=control.order, command=command,
            chip=device.chip, instance=device.instance, section=control.section,
            source_event_id=control.source_event_id, control_id=control.control_id,
            unit_ids=control.unit_ids, kind=control.kind, preserved_pcm=False))
    for packet in performance.pcm_packets:
        command = bytes.fromhex(packet.command_hex)
        if not command:
            raise ValueError(f'Empty native PCM packet: {packet.packet_id}')
        rows.append(dict(sample=packet.sample, order=packet.order, command=command,
            chip=packet.chip, instance=None, section='pcm', source_event_id=packet.source_event_id,
            control_id=packet.packet_id, unit_ids=(), kind=packet.kind, preserved_pcm=True))
    rows.sort(key=lambda r: (r['sample'], r['order']))
    positions = [(r['sample'], r['order']) for r in rows]
    if len(set(positions)) != len(positions):
        raise ValueError('Two native operations claim the same source event position')
    if any(not 0 <= row['sample'] <= performance.end_sample for row in rows):
        raise ValueError('Native operation outside the source timeline')
    return tuple(rows)


def _header(performance):
    source = bytes.fromhex(performance.source_header_hex)
    if len(source) < 0x40 or source[:4] != b'Vgm ':
        raise ValueError('Native performance has no valid source header')
    version = int.from_bytes(source[8:12], 'little')
    extra = int.from_bytes(source[0xbc:0xc0], 'little') if version >= 0x170 and len(source) >= 0xc0 else 0
    if extra and not 0xc0 <= 0xbc + extra < len(source):
        raise ValueError('Native VGM extra header outside the retained header is unsupported')
    header = bytearray(source)
    header.extend(bytes(max(0, 256-len(header))))
    # Old reserved bytes must not acquire a meaning when upgrading the version.
    if version < 0x151:
        header[0x38:] = bytes(len(header)-0x38)
    if version < 0x110:
        header[0x28:0x34] = bytes(12)
    offsets = {'dcsg':0x0c, 'opll':0x10, 'opm':0x30, 'segapcm':0x38,
               'opna':0x48, 'psg':0x74, 'msm6258':0x90, 'msm6295':0x98,
               'scc':0x9c, 'c140':0xa8,'huc6280':0xa4}
    by_chip = {}
    for device in performance.devices:
        by_chip.setdefault(device.chip, []).append(device)
    for chip, devices in by_chip.items():
        if chip not in offsets:
            raise ValueError(f'No native VGM header codec for {chip}')
        if len({d.clock_hz for d in devices}) != 1:
            raise ValueError('Distinct per-instance clocks require a structured extra-header projection')
        primary = next((d for d in devices if d.instance == 0), devices[0])
        clock = primary.clock_hz | (primary.clock_raw & 0xc0000000)
        if any(d.instance for d in devices):
            clock |= 0x40000000
        struct.pack_into('<I', header, offsets[chip], clock)
        parameters = dict(primary.parameters)
        if chip == 'dcsg':
            struct.pack_into('<H', header, 0x28, parameters.get('feedback', int.from_bytes(header[0x28:0x2a], 'little')))
            header[0x2a] = parameters.get('shift_width', header[0x2a])
            header[0x2b] = parameters.get('flags', header[0x2b])
        elif chip == 'segapcm':
            struct.pack_into('<I', header, 0x3c, parameters.get('interface', int.from_bytes(header[0x3c:0x40], 'little')))
        elif chip == 'msm6258':
            header[0x94] = parameters.get('flags', header[0x94])
        elif chip == 'c140':
            header[0x96] = parameters.get('chip_type', header[0x96])
    struct.pack_into('<I', header, 8, max(version, 0x171))
    struct.pack_into('<I', header, 0x34, len(header)-0x34)
    for offset in (4, 0x14, 0x18, 0x1c, 0x20):
        struct.pack_into('<I', header, offset, 0)
    return header


def write_native_vgm(performance, path, *, gd3=None, mapping_path=None, source_loop=False):
    """Write only the performance: the original input file is not consulted."""
    writes = scheduled_native_writes(performance)
    header, body, mapped = _header(performance), bytearray(), []
    loop_sample = performance.song_loop_sample if source_loop else None
    loop_order = performance.song_loop_order
    if source_loop and (loop_sample is None or not 0 <= loop_sample < performance.end_sample):
        raise ValueError('Source song loop requested without a valid native boundary')
    if source_loop and dict(performance.metadata).get('wait_override_in_loop'):
        raise ValueError('State-dependent wait overrides require explicit native loop validation')
    cursor, loop_address = 0, None

    def wait(samples):
        if samples < 0:
            raise ValueError('Native writes are not ordered in time')
        while samples:
            size = min(65535, samples)
            body.extend(b'\x61' + struct.pack('<H', size))
            samples -= size

    def advance(sample, order):
        nonlocal cursor, loop_address
        if loop_sample is not None and loop_address is None:
            if cursor <= loop_sample < sample:
                wait(loop_sample-cursor)
                cursor = loop_sample
                loop_address = len(header)+len(body)
            elif loop_sample == sample and (loop_order is None or order >= loop_order):
                wait(sample-cursor)
                cursor = sample
                loop_address = len(header)+len(body)
        wait(sample-cursor)
        cursor = sample

    for row in writes:
        advance(row['sample'], row['order'])
        command = row['command']
        record = {k: v for k, v in row.items() if k != 'command'}
        record.update(target_command_address=len(header)+len(body), opcode=f'{command[0]:02x}',
            bytes=len(command), payload_sha256=hashlib.sha256(command).hexdigest())
        mapped.append(record)
        body.extend(command)
    advance(performance.end_sample, float('inf'))
    body.append(0x66)
    struct.pack_into('<I', header, 0x18, performance.end_sample)
    if loop_address is not None:
        struct.pack_into('<I', header, 0x1c, loop_address-0x1c)
        struct.pack_into('<I', header, 0x20, performance.end_sample-loop_sample)
    raw = header+body
    if gd3 is None:
        encoded = dict(performance.metadata).get('gd3_hex')
        gd3 = bytes.fromhex(encoded) if encoded else None
    if gd3:
        if gd3[:4] != b'Gd3 ' or len(gd3) < 12 or int.from_bytes(gd3[8:12], 'little')+12 != len(gd3):
            raise ValueError('Invalid native GD3 metadata')
        struct.pack_into('<I', raw, 0x14, len(raw)-0x14)
        raw.extend(gd3)
    struct.pack_into('<I', raw, 4, len(raw)-4)
    # Validate the complete command framing before touching the output file.
    from native_imports.vgm_timing import command_times
    events = tuple(command_times(raw))
    if not events or events[-1].vgmticks != performance.end_sample:
        raise ValueError('Native VGM duration does not match its musical performance')
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name+'.tmp')
    temporary.write_bytes(raw)
    temporary.replace(path)
    if mapping_path is not None:
        with Path(mapping_path).open('w', encoding='utf-8', newline='') as stream:
            fields = list(mapped[0]) if mapped else ['sample', 'order', 'chip', 'target_command_address']
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for row in mapped:
                writer.writerow({key: json.dumps(value) if isinstance(value, tuple) else value
                                 for key, value in row.items()})
    return tuple(mapped)


def capability_report(performance):
    chips = sorted({device.chip for device in performance.devices})
    return dict(profile='native', time_domain='original_source_samples', chips=chips,
        devices=[asdict(device) for device in performance.devices],
        musical_units=len(performance.units), musical_controls=len(performance.controls),
        native_percussion_events=len(performance.percussion),
        pcm_preserved_packets=len(performance.pcm_packets), pcm_blueprint=False,
        target_mml_constraints_applied=False,
        decisions=performance.decisions, source_information_retained=True)
