"""Collect seven native source domains on one original 44100-Hz timeline.

Analysis limitations are separate from retained native commands. In particular,
an unsupported PCM variant must not erase data needed by a passthrough backend.
"""
from dataclasses import asdict
import csv
import hashlib
import json
from pathlib import Path
import struct

from .vgm_io import read_vgm_bytes, read_vgm_header
from .vgm_timing import command_times
from .vgm_loop import read_loop_metadata


WRITE_CHIPS = {0x54: 'opm', 0xa4: 'opm', 0x56: 'opna', 0x57: 'opna',
               0xa6: 'opna', 0xa7: 'opna', 0x50: 'dcsg', 0x30: 'dcsg',
               0x4f: 'dcsg', 0x3f: 'dcsg', 0xb7: 'msm6258', 0xb8: 'msm6295',
               0xc0: 'segapcm', 0xd4: 'c140'}
BLOCK_CHIPS = {4: 'msm6258', 0x44: 'msm6258', 0x80: 'segapcm',
               0x81: 'opna', 0x8b: 'msm6295', 0x8d: 'c140'}
STREAM_CHIPS = {0: 'dcsg', 3: 'opm', 4: 'segapcm', 7: 'opna',
                0x17: 'msm6258', 0x18: 'msm6295', 0x1c: 'c140'}
CHIPS = ('opm', 'opna', 'dcsg', 'msm6258', 'msm6295', 'segapcm', 'c140')


def _header(raw):
    header = dict(read_vgm_header(raw))
    def field(offset, size, since):
        return int.from_bytes(raw[offset:offset+size], 'little') if (
            header['version'] >= since and offset+size <= header['data_start']) else 0
    header.update(opm_clock_raw=field(0x30, 4, 0x110),
                  dcsg_clock_raw=field(0x0c, 4, 0x100),
                  dcsg_feedback_raw=field(0x28, 2, 0x110),
                  dcsg_shift_width_raw=field(0x2a, 1, 0x110),
                  dcsg_flags_raw=field(0x2b, 1, 0x151))
    return header


def inspect_source(source):
    """Return command evidence/inventory without running chip interpretation.

    ``source`` may be bytes or a file path. Header declarations alone never add
    an active domain. Stream setup and ROM/data blocks are retained usage facts,
    not a claim that a corresponding voice is audible.
    """
    raw = bytes(source) if isinstance(source, (bytes, bytearray, memoryview)) else read_vgm_bytes(source)
    header = _header(raw)
    events = tuple(command_times(raw))
    active, counts, streams = set(), {}, {}
    for event in events:
        command, pos = event.command, event.address
        chip = WRITE_CHIPS.get(command)
        if command == 0x67:
            chip = BLOCK_CHIPS.get(raw[pos+2])
        elif command == 0x90:
            chip = STREAM_CHIPS.get(raw[pos+2] & 0x7f)
            streams[raw[pos+1]] = chip
        elif 0x91 <= command <= 0x95:
            chip = streams.get(raw[pos+1])
        if chip:
            active.add(chip)
            counts[chip] = counts.get(chip, 0) + 1
    source_end = max((e.vgmticks+e.wait_samples for e in events), default=0)
    return dict(raw=raw, header=header, events=events, source_end_sample=source_end,
                active_chips=tuple(chip for chip in CHIPS if chip in active),
                command_counts=counts, source_sha256=hashlib.sha256(raw).hexdigest(),
                loop=read_loop_metadata(raw))


def _csv(path, rows, fields):
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _fm_trace(bundle, chip, root, stem):
    from . import opm, opna
    raw, header = bundle['raw'], bundle['header']
    module = opm if chip == 'opm' else opna
    clock_raw = header[chip+'_clock_raw']
    clock = clock_raw & 0x3fffffff
    chip_type = ('YM2164' if clock_raw & 0x80000000 else 'YM2151') if chip == 'opm' else 'YM2608'
    rows = []
    for event_id, event in enumerate(bundle['events']):
        command = event.command
        if WRITE_CHIPS.get(command) != chip:
            continue
        pos = event.address
        register, value = raw[pos+1:pos+3]
        instance = int(command in (0xa4, 0xa6, 0xa7))
        port = int(command in (0x57, 0xa7))
        channel = (module.register_channel(register, value) if chip == 'opm' else
                   module.register_channel(register, value, port))
        row = dict(event_id=event_id, source_event_id=event.source_event_id,
            original_event_id=event.source_event_id, address=pos,
            command=command, chip_instance=instance, chip_type=chip_type,
            clock_hz=clock, clock_raw=clock_raw, ch='' if channel is None else channel,
            register=register, data=value, vgmticks=event.vgmticks,
            loop_iteration=event.loop_iteration, original_vgmticks=event.original_vgmticks)
        if chip == 'opna':
            row['port'] = port
        rows.append(row)
    path = root/f'{stem}.native.{chip}.registers.csv'
    fields = ('event_id', 'source_event_id', 'original_event_id', 'address', 'command',
              'chip_instance', 'chip_type', 'clock_hz', 'clock_raw', 'ch', 'register',
              'data', 'vgmticks', 'loop_iteration', 'original_vgmticks')
    if chip == 'opna':
        fields += ('port',)
    _csv(path, rows, fields)
    analysis = module.build_segments(path, end_vgmticks=bundle['source_end_sample'])
    module.dump_analysis(analysis, state_csv=root/f'{stem}.native.{chip}.states.csv',
                         segments_csv=root/f'{stem}.native.{chip}.segments.csv')
    if chip == 'opna':
        module.dump_unmodeled_writes(analysis, csv_path=root/f'{stem}.native.opna.unmodeled.csv')
    return analysis, str(path)


def _sega(bundle, root, stem):
    from .segapcm import SegaPcmTrace
    raw = bundle['raw']
    analysis = SegaPcmTrace(bundle['header'])
    for event_id, event in enumerate(bundle['events']):
        pos = event.address
        if event.command == 0xc0:
            analysis.write(event_id, event, int.from_bytes(raw[pos+1:pos+3], 'little'), raw[pos+3])
        elif event.command == 0x67 and raw[pos+2] == 0x80:
            length = struct.unpack_from('<I', raw, pos+3)[0]
            analysis.rom_block(event_id, event, length, raw[pos+7:pos+7+(length & 0x7fffffff)])
    analysis.dump(root, stem+'.native', bundle['source_end_sample'])
    return analysis


def analyze_source(source, outdir, stem=None):
    """Native State/Segment analyses plus intact command evidence for all chips.

    Returned mapping includes ``analyses`` and per-chip aliases; unavailable or
    failed analyses are None. ``errors`` contains interpretation failures, never
    a request to omit the native commands. Malformed VGM framing still raises.
    No source audio is synthesized and no target sample banks are created.
    """
    root = Path(outdir)
    root.mkdir(parents=True, exist_ok=True)
    if stem is None:
        stem = 'source' if isinstance(source, (bytes, bytearray, memoryview)) else Path(source).stem
    bundle = inspect_source(source)
    analyses = {chip: None for chip in CHIPS}
    errors, trace_paths = {}, {}
    evidence = [dict(event_id=index, **asdict(e)) for index, e in enumerate(bundle['events'])]
    _csv(root/f'{stem}.native.commands.csv', evidence, ('event_id', *bundle['events'][0].__dataclass_fields__))
    for chip in bundle['active_chips']:
        try:
            if chip in ('opm', 'opna'):
                analysis, trace_paths[chip] = _fm_trace(bundle, chip, root, stem)
            elif chip == 'segapcm':
                analysis = _sega(bundle, root, stem)
            elif chip == 'dcsg':
                from . import dcsg
                analysis = dcsg.analyze(bundle['raw'])
                dcsg.dump_analysis(analysis, root, stem+'.native')
            else:
                from importlib import import_module
                module = import_module('.'+chip, __package__)
                analysis = module.analyze(bundle['raw'])
                analysis.dump(root, stem+'.native')
            analyses[chip] = analysis
        except (ValueError, IndexError, KeyError, OSError) as error:
            errors[chip] = dict(error_type=type(error).__name__, detail=str(error),
                                native_commands_retained=True)
    provenance_path = Path(__file__).resolve().parents[2]/'docs/native_import_provenance.json'
    provenance = json.loads(provenance_path.read_text()) if provenance_path.is_file() else None
    interpretation_issues = {}
    for chip, analysis in analyses.items():
        issues = getattr(analysis, 'issues', ())
        if issues:
            interpretation_issues[chip] = [asdict(issue) if hasattr(issue, '__dataclass_fields__') else issue
                                          for issue in issues]
    report = dict(source_sha256=bundle['source_sha256'], source_end_sample=bundle['source_end_sample'],
        active_chips=bundle['active_chips'], command_counts=bundle['command_counts'],
        header=bundle['header'], loop=bundle['loop'], errors=errors,
        interpretation_issues=interpretation_issues,
        source_only=True, target_projection=False,
        analysis_available={chip: analyses[chip] is not None for chip in CHIPS})
    (root/f'{stem}.native.source.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    return dict(bundle, analyses=analyses, errors=errors, trace_paths=trace_paths,
                provenance=provenance, report=report, **analyses)
