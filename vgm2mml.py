#!/usr/bin/env python3
"""
vgm2mml.py - Top-level CLI: VGM binary → MGSDRV MML

Usage:
    python vgm2mml.py <vgm_file> [--outdir <dir>] [--dump-passes] [--debug]
                      [--scc-input trace|log] [--psg-input trace|log]

Default output (no --debug):
    A single merged <stem>.mml file containing PSG, SCC, and OPLL parts.

With --debug:
    The merged <stem>.mml file plus all chip-specific MML variants and the
    raw log/trace CSV files.

Example:
    python vgm2mml.py inputs/02_StartingPoint/02_StartingPoint.vgm \\
        --outdir outputs_py --dump-passes
"""
import sys
import os
import argparse
import json

# Allow importing py/ siblings from the repository root
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_SCRIPT_DIR, 'py'))

from vgm_reader import parse_vgm
from scc_mml import process_scc_csv
from psg_mml import process_psg_csv
from opll_mml import process_opll_csv
from mml_sync import annotate_sync_points
from mml_macros import compress_macros
from gd3 import title_from_gd3
from mml_alloc import parse_alloc, override_alloc
from mml_envelopes import EnvelopeBank
from psg_scc_target import TUNING_HEADER
from mgs_conversion_config import MgsOptions


def _has_chip_data(csv_path: str) -> bool:
    """Return True if *csv_path* contains at least one non-header data row."""
    try:
        with open(csv_path, 'r', newline='') as fh:
            for line in fh:
                line = line.rstrip('\r\n')
                if line and not line.startswith('#') and line.strip():
                    return True
    except OSError:
        pass
    return False


def _extract_from_alloc(mml_path: str) -> str:
    """Read *mml_path* and return the content starting from the first ``#alloc`` line.

    Lines before the first ``#alloc`` (i.e., the chip-level header:
    ``;[name=...]``, ``#opll_mode``, ``#tempo``, ``#title``) are stripped.
    The returned string starts with the first ``#alloc`` line.
    """
    try:
        with open(mml_path, 'r', newline='') as fh:
            lines = fh.readlines()
    except OSError:
        return ''

    for i, line in enumerate(lines):
        if line.startswith('#alloc'):
            return ''.join(lines[i:])
    # No #alloc found – return full content as fallback
    return ''.join(lines)


def _build_merged_mml(stem: str, song_dir: str,
                      has_psg: bool, has_scc: bool, has_opll: bool,
                      raw_ticks: bool = False, sync_min_gap: int = 1000,
                      target: bool = True, name: str | None = None,
                      title: str | None = None, tempo: int | None = None, opll_mode: int = 1) -> str:
    """Build the merged MML text from per-chip compress outputs.

    The merged file has a single global header followed by PSG, SCC, and OPLL
    parts (in that order) when the corresponding chip is present.  Each part
    begins with a separator comment and includes the chip MML content starting
    from the ``#alloc`` line (chip-level header is stripped).
    """
    lines = []
    lines.append(f';[name={stem if name is None else name} lpf=1]')
    lines.append(f'#opll_mode {opll_mode}')
    if target and (has_psg or has_scc):
        lines.append(TUNING_HEADER)
    lines.append(f'#tempo {tempo}' if tempo is not None else '#tempo 75' if raw_ticks else '#tempo 225')
    lines.append(f'#title {{ "{stem if title is None else title}"}}')
    lines.append('')

    parts = [
        ('psg',  'psg',
         "\n;-----------------------  psg part -------------------------------"),
        ('scc',  'scc',
         "\n;-----------------------  scc part -------------------------------"),
        ('opll', 'opll',
         "\n;-----------------------  OPLL part -------------------------------"),
    ]
    flags = {'psg': has_psg, 'scc': has_scc, 'opll': has_opll}

    header_text = '\n'.join(lines) + '\n'
    body_parts = [header_text]

    suffix = 'pass3.compress.MGS_pct.mml' if raw_ticks else 'pass3.compress.MGS.mml'

    for chip_key, chip_ext, separator in parts:
        if not flags[chip_key]:
            continue
        mml_path = os.path.join(song_dir,
                                f'{stem}.{chip_ext}.{suffix}')
        target_path = os.path.join(song_dir, f'{stem}.{chip_ext}.target.mml')
        if target and chip_key in ('psg', 'scc', 'opll') and os.path.exists(target_path):
            mml_path = target_path
        body_parts.append(separator + '\n')
        body_parts.append(_extract_from_alloc(mml_path))

    result = ''.join(body_parts)
    if not result.endswith('\n'):
        result += '\n'
    formatted = annotate_sync_points(result, min_gap=sync_min_gap, drop_silent=target)
    return compress_macros(formatted) if target else formatted


def main():
    parser = argparse.ArgumentParser(
        description='Convert a VGM file to MGSDRV MML (SCC + PSG + OPLL)')
    parser.add_argument('vgm', help='Input VGM file')
    parser.add_argument('--target', choices=['mgs', 'opm', 'opm-additive'], default='mgs',
                        help='opm emits PSG/SCC MDX MML (FM PSG by default); opm-additive retains the old model')
    parser.add_argument('--psg-gain', type=float, default=None, help='OPM PSG gain: default fm=1, additive=0.125')
    parser.add_argument('--psg-model', choices=['fm', 'additive'], default=None,
                        help='PSG tone model for --target opm (default: fm)')
    parser.add_argument('--opm-pitch-policy', choices=['clamp', 'error'], default=None,
                        help='OPM range policy: default fm=clamp, additive=error')
    parser.add_argument('--scc-gain', type=float, default=.125, help='OPM additive SCC gain')
    parser.add_argument('--outdir', default=None,
                        help='Output directory (default: <vgm_stem>_log/ next to vgm)')
    parser.add_argument('--name', help='Override the player metadata name (default: input stem)')
    parser.add_argument('--enhance-macros', action='store_true', default=True,
                        help='Enable enhanced macros (now the default)')
    parser.add_argument('--enhance-rhythm', '--enhance-drums', dest='enhance_drums', action='store_true',
                        help='Add inferred PSG/SCC percussion on OPLL rhythm; preserve source parts')
    psg_parts = parser.add_mutually_exclusive_group()
    psg_parts.add_argument('--psg-melody-only', '--psg-melody_only', dest='psg_part',
                           action='store_const', const='melody', default='all',
                           help='Solo native PSG intervals not classified as rhythm')
    psg_parts.add_argument('--psg-rhythm-only', '--psg-rhythm_only', dest='psg_part',
                           action='store_const', const='rhythm',
                           help='Solo conservatively classified native PSG rhythm intervals')
    parser.add_argument('--legacy-macros', dest='enhance_macros', action='store_false',
                        help='Use the previous greedy macro compressor')
    parser.add_argument('--legacy-loops', action='store_true',
                        help='Use previous loop/envelope projection for PSG, SCC and OPLL')
    parser.add_argument('--title', dest='title',
                        help='Override #title (default: GD3 metadata, then input stem)')
    parser.add_argument('--gd3-language', choices=['ja', 'en'], default='ja',
                        help='Preferred GD3 language, with per-field fallback (default: ja)')
    parser.add_argument('--dump-passes', action='store_true',
                        help='Keep event log/trace CSVs and write pass0-3 and PSG/SCC Segment CSVs')
    parser.add_argument('--vgmticks', action='store_true',
                        help='Append absolute VGM sample positions to trace/Segment evidence; does not retime MML')
    parser.add_argument('--normalize-lengths', action='store_true',
                        help='Infer a shared musical clock and normalize target note lengths; retain source samples')
    parser.add_argument('--fm-state-ms', type=float, default=None,
                        help='OPLL internal pitch/volume state threshold in ms (effective default 1); enables optional normalization')
    parser.add_argument('--normalization-ms', type=float, default=None,
                        help='Maximum target timing correction in ms (effective default 8); enables optional normalization, not gate deletion')
    volume_curves = parser.add_mutually_exclusive_group()
    volume_curves.add_argument('--software-volume-curves', action='store_true', default=False,
                        help='Share exact fixed-pitch PSG/SCC attack volume curves (opt-in)')
    volume_curves.add_argument('--no-software-volume-curves', dest='software_volume_curves',
                               action='store_false', help='Disable PSG/SCC software volume curve projection')
    parser.add_argument('--force', action='store_true',
                        help='Omit explicitly listed unsupported chip writes for MGS; malformed streams and compiler limits still fail')
    parser.add_argument('--debug', action='store_true',
                        help='Write all chip-specific MML variants and raw CSV files '
                             'in addition to the merged <stem>.mml output')
    parser.add_argument('--scc-input', choices=['trace', 'log'], default='trace',
                        help='SCC intermediate format: trace (default, chronological)'
                             ' or log (per-channel grouped)')
    parser.add_argument('--psg-input', choices=['trace', 'log'], default='trace',
                        help='PSG intermediate format: trace (default, chronological)'
                             ' or log (per-channel grouped)')
    parser.add_argument('--raw-ticks', action='store_true',
                        help='Output note lengths as raw tick %% notation '
                             '(e.g. c%%N). '
                             'Default is note-value/divisor notation (e.g. c16, d8.).')
    parser.add_argument('--sync-min-gap', type=int, default=1000,
                        help='Minimum target-MML steps between sync comments '
                             '(default: 1000; 0: all shared boundaries; end always shown)')
    parser.add_argument('--alloc', type=parse_alloc,
                        help='Override selected track allocations, e.g. "9=1800, a=3780"')
    args = parser.parse_args()
    try:
        options = MgsOptions(args.normalize_lengths, args.normalization_ms, args.fm_state_ms,
                             args.force, args.dump_passes, args.enhance_drums, psg_part=args.psg_part,
                             software_volume_curves=args.software_volume_curves)
    except ValueError as error:
        parser.error(str(error))
    args.normalize_lengths = options.enabled
    if args.target != 'mgs' and args.software_volume_curves:
        parser.error('--software-volume-curves requires --target mgs')
    if args.target != 'mgs' and args.enhance_drums:
        parser.error('--enhance-rhythm requires --target mgs')
    if args.target != 'mgs' and args.psg_part != 'all':
        parser.error('PSG part selection requires --target mgs')
    if args.target != 'mgs' and args.force:
        parser.error('--force currently applies only to the MGS target')
    if args.sync_min_gap < 0:
        parser.error('--sync-min-gap must be nonnegative')
    if args.normalize_lengths and args.raw_ticks:
        parser.error('--normalize-lengths cannot be combined with --raw-ticks')

    for field, value in (('name', args.name), ('title', args.title)):
        if value is not None and (any(c in value for c in '\r\n') or
                                  (']' in value if field == 'name' else '"' in value)):
            parser.error(f'--{field} contains a character that would break the MML header')

    vgm_path = args.vgm
    if not os.path.isfile(vgm_path):
        print(f"Error: {vgm_path!r} not found", file=sys.stderr)
        sys.exit(1)

    # Determine base name: "02_StartingPoint"
    base_name = os.path.splitext(os.path.basename(vgm_path))[0]
    if args.title is None:
        args.title = title_from_gd3(vgm_path, base_name, args.gd3_language)

    if args.outdir:
        song_dir = args.outdir
    else:
        song_dir = os.path.join(
            os.path.dirname(os.path.abspath(vgm_path)),
        )
    
    os.makedirs(song_dir, exist_ok=True)

    if args.target == 'opm-additive' and args.psg_model not in (None, 'additive'):
        parser.error('--target opm-additive requires the additive PSG model')
    if args.target == 'mgs' and (args.psg_model or args.opm_pitch_policy):
        parser.error('OPM model/pitch switches require an OPM target')
    if args.target in ('opm', 'opm-additive'):
        if args.alloc or args.normalize_lengths or args.raw_ticks or not args.enhance_macros or args.legacy_loops:
            parser.error('MGSDRV allocation/normalization/compression options do not apply to OPM targets')
        from scripts.psg_scc_to_mdx import convert
        try:
            mml, plan = convert(vgm_path, song_dir, psg_gain=args.psg_gain,
                                scc_gain=args.scc_gain, title=args.title,
                                psg_model=args.psg_model or ('additive' if args.target == 'opm-additive' else 'fm'),
                                pitch_policy=args.opm_pitch_policy,
                                dump_passes=args.dump_passes or args.debug)
        except ValueError as error:
            parser.error(str(error))
        print(f'MDX MML: {mml}')
        return

    from pathlib import Path
    from mgs_force import inspect_projection
    root = Path(song_dir)
    report_path = root / f'{base_name}.conversion.json'
    # Remove only artifacts owned by this conversion, including old optional
    # decisions which could otherwise look like current successful output.
    for suffix in ('mml', 'normalization.json', 'fm.short_states.json', 'fm.short_states.csv',
                   'opll.normalized.notes.csv', 'opll.normalized.loops.csv',
                   'opll.normalized.expanded.mml', 'drums.json', 'drums.candidates.csv',
                   'drums.projection.csv', 'drums.before.target.mml', 'drums.after.target.mml',
                   'volume_curves.target.json'):
        (root / f'{base_name}.{suffix}').unlink(missing_ok=True)
    for chip in ('psg', 'scc', 'opll'):
        (root / f'{base_name}.{chip}.before.normalize.mml').unlink(missing_ok=True)
        (root / f'{base_name}.{chip}.before.envelope_ties.mml').unlink(missing_ok=True)
    for chip in ('psg', 'scc'):
        for suffix in ('json', 'notes.csv', 'gates.csv', 'controls.csv', 'boundaries.csv', 'segments.csv'):
            (root / f'{base_name}.{chip}.performance.{suffix}').unlink(missing_ok=True)
    for chip in ('psg', 'scc'):
        for suffix in ('json', 'candidates.csv', 'notes.csv', 'decisions.csv'):
            (root / f'{base_name}.{chip}.volume_curves.{suffix}').unlink(missing_ok=True)
    report = dict(status='converting', target='mgs', input=str(Path(vgm_path).resolve()),
                  options=options.as_dict(), source_segments_unchanged=True)
    def save_report():
        report_path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    save_report()
    try:
        force_summary = inspect_projection(vgm_path, song_dir, base_name, force=args.force)
        report['force'] = dict(enabled=bool(args.force), omission_count=force_summary['omission_count'],
                               csv_path=force_summary['csv_path'])
        if args.force:
            print(f"Forced MGS projection: {force_summary['omission_count']} omitted source writes")
            if force_summary['omission_count']:
                print(f"Omission details: {force_summary['csv_path']}")
        if not args.normalize_lengths:
            disabled = dict(enabled=False, applied=False, status='disabled',
                reason='optional normalization not requested', source_segments_unchanged=True,
                normalization_ms=float(options.effective_normalization_ms),
                fm_state_ms=float(options.effective_fm_state_ms), whole_gate_omission=False,
                fm_state_scope='OPLL melody within accepted normalization only',
                psg_scc_curves_filtered=False, omitted_states=0)
            (root / f'{base_name}.normalization.json').write_text(json.dumps(disabled, indent=2), encoding='utf-8')
            (root / f'{base_name}.fm.short_states.json').write_text(json.dumps(disabled, indent=2), encoding='utf-8')
        _convert_mgs(args, options, vgm_path, song_dir, base_name)
        report['normalization'] = json.loads((root / f'{base_name}.normalization.json').read_text(encoding='utf-8'))
        if args.software_volume_curves:
            report['volume_curve_target'] = json.loads((root / f'{base_name}.volume_curves.target.json').read_text(encoding='utf-8'))
        if args.enhance_drums:
            report['drums'] = json.loads((root / f'{base_name}.drums.json').read_text(encoding='utf-8'))
        if args.psg_part != 'all':
            report['psg_selection'] = json.loads((root / f'{base_name}.psg.selection.json').read_text(encoding='utf-8'))
        report.update(status='success', mml=str(root / f'{base_name}.mml'))
    except Exception as error:
        report.update(status='conversion_failed', error_type=type(error).__name__, detail=str(error))
        save_report()
        raise
    else:
        save_report()


def _convert_mgs(args, options, vgm_path, song_dir, base_name):
    # ── Step 1: Parse VGM → SCC + PSG + OPLL log/trace CSVs ──────
    opm_metadata = {}
    (psg_log_csv, scc_log_csv, psg_trace_csv, scc_trace_csv,
     opll_log_csv, opll_trace_csv, opll_voice_csv, opll_regs_csv) = parse_vgm(
         vgm_path, song_dir, dump_loop=args.debug or args.dump_passes,
         include_vgmticks=args.vgmticks or args.normalize_lengths or args.enhance_drums or args.software_volume_curves or args.psg_part != 'all',
         opm_metadata=opm_metadata, dump_opm_segments=args.debug or args.dump_passes)

    if args.debug:
        print(f"PSG log:       {psg_log_csv}")
        print(f"PSG trace:     {psg_trace_csv}")
        print(f"SCC log:       {scc_log_csv}")
        print(f"SCC trace:     {scc_trace_csv}")
        print(f"OPLL log:      {opll_log_csv}")
        print(f"OPLL trace:    {opll_trace_csv}")
        print(f"OPLL voice:    {opll_voice_csv}")
        print(f"OPLL regs:     {opll_regs_csv}")
        if opm_metadata['csv_path']:
            print(f"OPM regs:      {opm_metadata['csv_path']}")
            print(f"OPM state:     {opm_metadata['state_csv_path']}")
            print(f"OPM Segments:  {opm_metadata['segments_csv_path']}")

    # Detect chip presence from trace CSVs
    has_psg  = _has_chip_data(psg_trace_csv)
    has_scc  = _has_chip_data(scc_trace_csv)
    has_opll = _has_chip_data(opll_trace_csv)

    if args.psg_part != 'all' and not has_psg:
        raise ValueError('PSG part selection requires source PSG register data')

    # ── Step 2: SCC MML pipeline ─────────────────────────────────
    if args.legacy_loops:
        envelope_bank = EnvelopeBank(deferred=True)
    else:
        from pre_envelope_loops import LoopFirstEnvelopeBank
        envelope_bank = LoopFirstEnvelopeBank(deferred=True)
    scc_csv = scc_trace_csv if args.scc_input == 'trace' else scc_log_csv

    scc_mml_path = process_scc_csv(scc_csv, song_dir, stem=base_name,
                                   dump_passes=args.dump_passes,
                                   debug=args.debug,
                                   raw_ticks=args.raw_ticks,
                                   envelope_bank=envelope_bank)
    if args.debug:
        print(f"SCC MML: {scc_mml_path}")

    # ── Step 3: PSG MML pipeline ─────────────────────────────────
    psg_csv = psg_trace_csv if args.psg_input == 'trace' else psg_log_csv

    psg_mml_path = process_psg_csv(psg_csv, song_dir, stem=base_name,
                                   dump_passes=args.dump_passes,
                                   debug=args.debug,
                                   raw_ticks=args.raw_ticks,
                                   envelope_bank=envelope_bank)
    if args.debug:
        print(f"PSG MML: {psg_mml_path}")

    performances = [kwargs['performance'] for _, _, _, kwargs in envelope_bank.pending]
    selection_candidates = ()
    selected_psg = None
    if args.psg_part != 'all':
        from pathlib import Path
        from psg_part_selection import select, dump as dump_selection
        from psg_scc_performance import analyze, dump as dump_performance
        from chip_segments import PsgSegment, dump_segments
        native_psg = next(p for p in performances if p.chip == 'psg')
        selected_psg, selection_candidates, summary, catalog, membership = select(native_psg, args.psg_part)
        dump_selection(song_dir, base_name, summary, catalog, membership)
        projected_performance = analyze(selected_psg, 'psg')
        pending = []
        for segments, chip, path, kwargs in envelope_bank.pending:
            if chip != 'psg':
                continue
            kwargs = dict(kwargs, performance=projected_performance)
            if args.dump_passes:
                prefix = str(Path(song_dir) / (base_name + '.psg.selection'))
                kwargs['dump_path'] = prefix + '.target_notes.csv'
                dump_performance(projected_performance, prefix)
                dump_segments(prefix+'.segments.csv', selected_psg, PsgSegment)
            pending.append((selected_psg, chip, path, kwargs))
        envelope_bank.pending = pending
        Path(song_dir, base_name+'.scc.target.mml').write_text('', encoding='utf-8')
        print(f"PSG selection: {args.psg_part}; {summary['eligible_rhythm_candidates']} rhythm candidates; "
              f"{summary['hardware_phase_abstentions']} hardware-envelope abstentions")
    else:
        from pathlib import Path
        for suffix in ('json', 'candidates.csv', 'mask.csv'):
            Path(song_dir, base_name+'.psg.selection.'+suffix).unlink(missing_ok=True)
    if args.software_volume_curves:
        from psg_scc_volume_curves import project as project_curves, dump as dump_curves
        projected_pending = []
        for segments, chip, path, kwargs in envelope_bank.pending:
            projection = project_curves(kwargs['performance'])
            summary = projection.summary()
            dump_curves(projection, Path(song_dir) / f'{base_name}.{chip}.volume_curves',
                        details=args.dump_passes or args.debug)
            projected_pending.append((segments, chip, path,
                                      dict(kwargs, performance=projection.performance)))
            print(f"{chip.upper()} volume curves: {summary['original_units']} -> "
                  f"{summary['projected_units']} units; "
                  f"{summary['joined_boundaries']} joined boundaries (exact renderer ticks)")
        envelope_bank.pending = projected_pending
    envelope_bank.flush()

    from opll_mode import mode_from_trace
    opll_mode = mode_from_trace(opll_trace_csv)

    # ── Step 4: OPLL MML pipeline ────────────────────────────────
    opll_mml_path = process_opll_csv(opll_trace_csv, song_dir, stem=base_name,
                                     dump_passes=args.dump_passes,
                                     debug=args.debug,
                                     voice_csv_path=opll_voice_csv,
                                     raw_ticks=args.raw_ticks, source_loops=not args.legacy_loops,
                                     opll_mode=opll_mode)
    if args.debug:
        print(f"OPLL MML: {opll_mml_path}")

    # Optional target-only normalization; legacy passes and Segment dumps stay native.
    drum_control_sources = None
    if args.enhance_drums:
        from pathlib import Path
        drum_control_sources = {chip: Path(song_dir, f'{base_name}.{chip}.target.mml').read_text(encoding='utf-8')
                                for chip in ('psg', 'scc')}
    normalized_tempo = None
    if args.normalize_lengths:
        print(f'Normalization settings: {options.effective_normalization_ms:g} ms timing bound; '
              f'{options.effective_fm_state_ms:g} ms OPLL internal-state threshold')
        from note_normalization import normalize_outputs
        from psg import build_segments as build_psg
        from scc import build_segments as build_scc
        controls = {}
        if has_psg:
            controls['psg'] = (selected_psg if selected_psg is not None else
                               build_psg(psg_csv, song_dir, base_name, dump_passes=False))
        if has_scc and args.psg_part == 'all':
            controls['scc'] = build_scc(scc_csv, song_dir, dump_passes=False, stem=base_name).segments
        normalized_tempo = normalize_outputs(opll_trace_csv, opll_voice_csv, song_dir,
                                             base_name, args.dump_passes or args.debug, controls,
                                             opll_mode=opll_mode, source_loops=not args.legacy_loops,
                                             normalization_ms=options.effective_normalization_ms,
                                             fm_state_ms=options.effective_fm_state_ms)
        if normalized_tempo is not None:
            print(f'Note normalization: applied (tempo {normalized_tempo})')
        else:
            with open(os.path.join(song_dir, f'{base_name}.normalization.json'), encoding='utf-8') as stream:
                reason = json.load(stream)['reason']
            print(f'Note normalization: unchanged ({reason})')

    if args.software_volume_curves:
        from pathlib import Path
        from mgs_envelope_ties import compensate
        control_paths = {chip: Path(song_dir, f'{base_name}.{chip}.target.mml')
                         for chip in ('psg', 'scc') if Path(song_dir, f'{base_name}.{chip}.target.mml').exists()}
        control_texts = {chip: path.read_text(encoding='utf-8') for chip, path in control_paths.items()}
        if args.dump_passes or args.debug:
            for chip, text in control_texts.items():
                Path(song_dir, f'{base_name}.{chip}.before.envelope_ties.mml').write_text(text, encoding='utf-8')
        try:
            if normalized_tempo is not None:
                raise ValueError('normalized note splitting requires separately validated envelope timing')
            corrected, tie_report = compensate(control_texts, tempo=75 if args.raw_ticks else 225)
        except ValueError as error:
            # Retry the ordinary complete pipeline, including clock acceptance and
            # drum boundary mapping. A plan accepted for fewer projected boundaries
            # need not be safe for the original partitions.
            from copy import copy
            from dataclasses import replace
            fallback_args = copy(args)
            fallback_args.software_volume_curves = False
            fallback_args.vgmticks = True
            print(f'Software volume curves: retaining ordinary projection ({error})')
            _convert_mgs(fallback_args, replace(options, software_volume_curves=False),
                         vgm_path, song_dir, base_name)
            tie_report = dict(status='fallback', applied=False, reason=str(error),
                              source_segments_unchanged=True, fallback='ordinary complete MGS pipeline')
            for chip in ('psg', 'scc'):
                summary_path = Path(song_dir, f'{base_name}.{chip}.volume_curves.json')
                if summary_path.exists():
                    summary = json.loads(summary_path.read_text())
                    summary.update(applied=False, reason=str(error),
                        candidate_projected_units=summary['projected_units'],
                        candidate_joined_boundaries=summary['joined_boundaries'],
                        candidate_inactive_reset_joins=summary['inactive_reset_joins'],
                        candidate_unchanged_period_joins=summary['unchanged_period_joins'],
                        projected_units=summary['original_units'], joined_boundaries=0,
                        inactive_reset_joins=0, unchanged_period_joins=0)
                    summary_path.write_text(json.dumps(summary, indent=2)+'\n', encoding='utf-8')
            Path(song_dir, f'{base_name}.volume_curves.target.json').write_text(
                json.dumps(tie_report, indent=2)+'\n', encoding='utf-8')
            return
        for chip, text in corrected.items():
            control_paths[chip].write_text(text, encoding='utf-8', newline='\n')
            summary_path = Path(song_dir, f'{base_name}.{chip}.volume_curves.json')
            if summary_path.exists():
                summary = json.loads(summary_path.read_text())
                summary.update(applied=True, backend_tie_compensation=True)
                summary_path.write_text(json.dumps(summary, indent=2)+'\n', encoding='utf-8')
        tie_report.update(status='applied', applied=True, source_segments_unchanged=True)
        Path(song_dir, f'{base_name}.volume_curves.target.json').write_text(
            json.dumps(tie_report, indent=2)+'\n', encoding='utf-8')

    if args.enhance_drums:
        from drum_inference import infer
        from drum_enhancement import apply
        from opll import _build_segments
        native_opll, _ = _build_segments(opll_trace_csv)
        if args.psg_part != 'all':
            # Solo excludes native SCC/OPLL, but preserves their source evidence
            # and the native OPLL timing anchor used above.
            native_opll = {}
            Path(song_dir, base_name+'.opll.target.mml').write_text('', encoding='utf-8')
            overlay_candidates = selection_candidates if args.psg_part == 'rhythm' else ()
            overlay_performances = [projected_performance]
        else:
            overlay_candidates = infer(performances)
            overlay_performances = performances
        with open(os.path.join(song_dir, f'{base_name}.normalization.json'), encoding='utf-8') as stream:
            normalization = json.load(stream)
        opll_mode, drum_report = apply(overlay_candidates, native_opll, overlay_performances,
            song_dir, base_name, native_mode=opll_mode, normalization=normalization,
            raw_ticks=args.raw_ticks, dump_passes=args.dump_passes or args.debug,
            control_sources=drum_control_sources)
        has_opll = has_opll or bool(drum_report['added_hits'])
        print(f"Rhythm enhancement: {drum_report['added_hits']} added hits; {drum_report['reason']}")

    # ── Step 5: Build merged MML ──────────────────────────────────
    target_scc = has_scc and args.psg_part == 'all'
    target_opll = has_opll if args.psg_part == 'all' else bool(args.enhance_drums and drum_report['added_hits'])
    merged_text = _build_merged_mml(base_name, song_dir,
                                    has_psg, target_scc, target_opll,
                                    raw_ticks=args.raw_ticks,
                                    sync_min_gap=args.sync_min_gap,
                                    name=args.name, title=args.title, tempo=normalized_tempo, opll_mode=opll_mode)
    merged_text = override_alloc(merged_text, args.alloc)
    if args.enhance_macros:
        from structured_macros import enhance_macros
        merged_text = enhance_macros(merged_text,
            dump_prefix=os.path.join(song_dir, base_name) if args.dump_passes else None)
    from mml_format import format_mml
    merged_text = format_mml(merged_text)
    merged_path = os.path.join(song_dir, f'{base_name}.mml')
    with open(merged_path, 'w', encoding='cp932', errors='replace', newline='\n') as fh:
        fh.write(merged_text)
    print(f"Merged MML: {merged_path}")
    if not args.debug and not args.dump_passes:
        for chip in ('psg', 'scc', 'opll'):
            os.remove(os.path.join(song_dir, f'{base_name}.{chip}.target.mml'))

    # ── Step 6: Clean up intermediate files in non-debug mode ─────
    if not args.debug:
        # Remove log/trace CSVs written by parse_vgm (intermediate inputs)
        if not args.dump_passes:
            for csv_path in (psg_log_csv, psg_trace_csv,
                             scc_log_csv, scc_trace_csv,
                             opll_log_csv, opll_trace_csv,
                             opll_voice_csv, opll_regs_csv,
                             opm_metadata['csv_path']):
                if csv_path is None:
                    continue
                try:
                    os.remove(csv_path)
                except OSError:
                    pass
        # Every pipeline writes these variants, including absent chips.
        # Debug mode retains them; normal output must not leak empty-chip files.
        chips_to_clean = ('psg', 'scc', 'opll')

        for chip in chips_to_clean:
            for suffix in ('pass3.compress.MGS.mml', 'pass3.compress.MGS_pct.mml'):
                chip_path = os.path.join(song_dir, f'{base_name}.{chip}.{suffix}')
                try:
                    os.remove(chip_path)
                except OSError:
                    pass


if __name__ == '__main__':
    main()
