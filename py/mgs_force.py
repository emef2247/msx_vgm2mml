"""Inventory source activity before the MGSDRV projection accepts any loss.

Force is intentionally limited to the register-write commands listed below.
It cannot repair malformed inputs, decode another chip instance, or interpret
PCM data/stream commands. Native reader inputs are never rewritten.
"""
import csv
import json
import zlib
from collections import Counter
from pathlib import Path

from vgm_io import read_vgm_bytes, read_vgm_header
from vgm_timing import command_times


class MgsProjectionError(ValueError):
    """A source cannot be projected within the explicitly supported scope."""


# Only these commands have a reviewed, independent register-write layout.
# Omitting one cannot change the meaning of a subsequent supported command.
_OMIT_WRITES = {
    0x54: ('OPM', 0, 0), 0xa4: ('OPM', 1, 0),
    0x56: ('OPNA', 0, 0), 0x57: ('OPNA', 0, 1),
    0xa6: ('OPNA', 1, 0), 0xa7: ('OPNA', 1, 1),
    0x50: ('DCSG', 0, 0), 0x30: ('DCSG', 1, 0),
    0x4f: ('DCSG', 0, 'stereo'), 0x3f: ('DCSG', 1, 'stereo'),
    0xb7: ('MSM6258', None, 0), 0xc0: ('SegaPCM', None, 0),
    0xa1: ('OPLL', 1, 0),
}
_FIELDS = ('command', 'address', 'vgmticks', 'chip', 'instance', 'port',
           'register', 'data', 'reason', 'action')


def _write_evidence(raw, event):
    cmd, pos = event.command, event.address
    chip, instance, port = _OMIT_WRITES[cmd]
    if cmd in (0x50, 0x30, 0x4f, 0x3f):
        register, data = '', raw[pos + 1]
    elif cmd == 0xc0:
        address = int.from_bytes(raw[pos + 1:pos + 3], 'little')
        instance, register, data = address >> 15, address & 0x7fff, raw[pos + 3]
    else:
        register, data = raw[pos + 1:pos + 3]
        if cmd == 0xb7:
            instance, register = register >> 7, register & 0x7f
    return dict(command=f'0x{cmd:02X}', address=pos, vgmticks=event.vgmticks,
                chip=chip, instance=instance, port=port, register=register,
                data=data, reason='source_to_mgs_projection_not_implemented',
                action='omit_write_from_target')


def _supported_write_error(raw, event, header):
    cmd, pos = event.command, event.address
    if cmd == 0xa0:
        reg = raw[pos + 1]
        if reg & 0x80:
            return 'Second AY instance is not supported by the native decoder'
        if reg > 15:
            return 'AY register is outside the supported decoder range'
    elif cmd == 0x51:
        reg, data = raw[pos + 1:pos + 3]
        valid = (reg <= 7 or reg in (0x0e, 0x0f) or 0x10 <= reg <= 0x18
                 or 0x20 <= reg <= 0x28 or 0x30 <= reg <= 0x38)
        if not valid:
            return 'OPLL register is outside the supported decoder range'
        if reg == 0x0f and data:
            return 'Nonzero OPLL test control is not supported by the projection'
    elif cmd == 0xd2:
        port, reg = raw[pos + 1:pos + 3]
        clock = header['scc_clock_raw']
        if clock & 0x80000000:
            return 'SCC variant clock flag is outside the supported decoder scope'
        if port not in (0, 1, 2, 3):
            return 'SCC instance/variant/test port is not supported by the native decoder'
        if reg > {0: 127, 1: 9, 2: 4, 3: 0}[port]:
            return 'SCC address is outside the supported decoder range'
    return None


def inspect_projection(source_path, outdir, stem, force=False):
    """Validate the entire command stream and emit the target-loss inventory.

    Unused clock declarations do not indicate active unsupported sources.
    Legacy AY/OPLL writes without clock declarations retain reader compatibility;
    SCC needs its declaration for active decoding. For compatibility with legacy
    exports, undeclared SCC initialization with no nonzero volume write is
    inventoried separately and left to the reader's existing ignore behavior.
    Every call emits source JSON and force JSON/CSV, including blocked calls.
    """
    folder = Path(outdir)
    folder.mkdir(parents=True, exist_ok=True)
    csv_path = folder / f'{stem}.mgs.force.csv'
    summary = dict(enabled=bool(force), omission_count=0, omissions=[],
                   csv_path=str(csv_path), blocked=[])
    inventory = dict(source_path=str(source_path), header=None, command_counts={},
                     commands=[], supported_write_count=0,
                     undeclared_scc_initialization_count=0, validation_error=None)
    candidates = []
    try:
        raw = read_vgm_bytes(source_path)
        header = read_vgm_header(raw)
        inventory['header'] = header
        declared_end = int.from_bytes(raw[4:8], 'little')
        if declared_end and declared_end + 4 > len(raw):
            raise ValueError('VGM declared EOF exceeds the available bytes')
        # Materialize first: no target omissions can be accepted before the last
        # command (including its payload bounds and terminating 0x66) is checked.
        events = list(command_times(raw))
        scc_nonzero_volume = any(
            e.command == 0xd2 and raw[e.address + 1] == 2
            and raw[e.address + 2] <= 4 and raw[e.address + 3] & 15
            for e in events)
        loop_offset = int.from_bytes(raw[0x1c:0x20], 'little')
        if loop_offset and loop_offset + 0x1c not in {e.address for e in events}:
            raise ValueError('VGM loop offset is not a command boundary')
        inventory['command_counts'] = dict(Counter(f'0x{e.command:02X}' for e in events))
        for event in events:
            cmd = event.command
            row = dict(command=f'0x{cmd:02X}', address=event.address,
                       vgmticks=event.vgmticks, wait_samples=event.wait_samples)
            inventory['commands'].append(row)
            if cmd in (0xa0, 0x51, 0xd2):
                error = _supported_write_error(raw, event, header)
                undeclared_scc = cmd == 0xd2 and not header['scc_clock_raw'] & 0x3fffffff
                if not error and undeclared_scc and scc_nonzero_volume:
                    error = 'Active SCC writes require a declared SCC clock for native decoding'
                if error:
                    summary['blocked'].append(dict(code='unsupported_native_write',
                                                   detail=error, **row))
                    row['projection'] = 'blocked'
                elif undeclared_scc:
                    inventory['undeclared_scc_initialization_count'] += 1
                    row['projection'] = 'undeclared_scc_initialization'
                else:
                    inventory['supported_write_count'] += 1
                    row['projection'] = 'supported'
            elif cmd in _OMIT_WRITES:
                evidence = _write_evidence(raw, event)
                candidates.append(evidence)
                row.update(evidence)
                row['projection'] = 'force_eligible'
            elif cmd in (0x61, 0x62, 0x63, 0x64, 0x66) or 0x70 <= cmd <= 0x7f:
                row['projection'] = 'timing'
            else:
                # Includes data blocks, DAC-with-wait, streams, PCM transfers,
                # and commands whose register layout has not been inventoried.
                row['projection'] = 'blocked'
                summary['blocked'].append(dict(code='unsupported_command',
                    detail='Command is outside the finite force omission scope', **row))
        if not inventory['supported_write_count']:
            summary['blocked'].append(dict(code='no_supported_source_writes',
                detail='No supported AY, OPLL or SCC writes remain for MGSDRV'))
        if candidates and not force:
            summary['blocked'].append(dict(code='unsupported_source_writes',
                detail=f'{len(candidates)} unsupported source register writes; '
                       'use --force to omit the inventoried target operations'))
        if force and not summary['blocked']:
            summary['omissions'] = candidates
            summary['omission_count'] = len(candidates)
    except (OSError, ValueError, EOFError, zlib.error) as exc:
        inventory['validation_error'] = str(exc)
        summary['blocked'].append(dict(code='invalid_source', detail=str(exc)))
    finally:
        with csv_path.open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=_FIELDS)
            writer.writeheader()
            writer.writerows(summary['omissions'])
        for path, value in ((folder / f'{stem}.mgs.force.json', summary),
                            (folder / f'{stem}.mgs.source.json', inventory)):
            path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n',
                            encoding='utf-8')
    if summary['blocked']:
        counts = Counter(issue['detail'] for issue in summary['blocked'])
        items = list(counts.items())
        details = '; '.join(f'{detail} ({count} occurrences)' if count > 1 else detail
                            for detail, count in items[:4])
        if len(items) > 4:
            details += f'; {len(items) - 4} additional reasons in report'
        raise MgsProjectionError(f'MGSDRV source projection blocked: {details}; '
                                 f'report={folder / (stem + ".mgs.force.json")}')
    return summary
