#!/usr/bin/env python3
"""
vgm2mml.py - Top-level CLI: VGM binary → MGSDRV MML

Usage:
    python vgm2mml.py <vgm_file> [--outdir <dir>] [--dump-passes] [--debug]
                      [--scc-input trace|log] [--psg-input trace|log]

Default output (no --debug):
    Merged <stem>.mml, tracks/<stem>.vgm, and a structured blueprint/<stem>.mml.

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


def _write_direct_vgm(plan, source, song_dir, stem):
    """Publish an owned direct VGM without overwriting an input or foreign file."""
    from pathlib import Path
    import hashlib
    import tempfile
    from musical_conversion import source_gd3
    from musical_vgm import write_vgm
    root = Path(song_dir).resolve()
    target = root / 'tracks' / f'{stem}.vgm'
    manifest = root / f'{stem}.direct_vgm.json'
    mapping = root / f'{stem}.vgm.writes.csv'
    if target.resolve() == Path(source).resolve() or not target.resolve().is_relative_to(root):
        raise ValueError('Direct VGM target would overwrite an input or escape the output directory')
    previous = json.loads(manifest.read_text()) if manifest.is_file() else {}
    if target.exists():
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        if previous.get('vgm_sha256') != digest or previous.get('source') != str(Path(source).resolve()):
            raise ValueError(f'Direct VGM target is unowned or modified: {target}')
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='direct_vgm_', dir=root) as temporary:
        temporary = Path(temporary)
        generated, trace = temporary / 'output.vgm', temporary / 'writes.csv'
        writes = write_vgm(plan, generated, gd3=source_gd3(source), mapping_path=trace)
        record = dict(status='success',source=str(Path(source).resolve()), vgm=str(target),
                      vgm_sha256=hashlib.sha256(generated.read_bytes()).hexdigest(),
                      controls=len(plan.source_performance.controls) if dict(plan.metadata).get('target_profile') == 'native' else len(plan.controls), writes=len(writes),
                      end_sample=plan.source_performance.end_sample if dict(plan.metadata).get('target_profile')=='native' else plan.end_sample,
                      compiler_invoked=False, mml_generated=False)
        prepared = temporary / 'manifest.json'
        prepared.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
        operations = ((generated, target), (trace, mapping), (prepared, manifest))
        backups = {}
        for index, (_, destination) in enumerate(operations):
            if destination.exists():
                backup = temporary / f'previous{index}'
                import shutil
                shutil.copyfile(destination, backup)
                backups[destination] = backup
        replaced = []
        try:
            for src, destination in operations:
                os.replace(src, destination)
                replaced.append(destination)
        except OSError:
            for destination in reversed(replaced):
                if destination in backups:
                    os.replace(backups[destination], destination)
                else:
                    destination.unlink(missing_ok=True)
            raise
    print(f'Direct VGM: {target}')
    return record


def _curve_timeline(performance):
    """Compare audible state/volume holds independently of score packaging."""
    from psg_scc_performance import settings
    result = []
    for channel, notes in performance.channels:
        holds = []
        for note in notes:
            cursor = note.start
            runs = ((0, note.length),) if note.rest else note.runs
            state = ('rest',) if note.rest else settings(note.segment, performance.chip)
            for volume, length in runs:
                if length <= 0:
                    continue
                value = (state, volume)
                if holds and holds[-1][1] == cursor and holds[-1][2] == value:
                    holds[-1] = (holds[-1][0], cursor + length, value)
                else:
                    holds.append((cursor, cursor + length, value))
                cursor += length
        result.append((channel, tuple(holds)))
    return tuple(result)


def main():
    parser = argparse.ArgumentParser(
        description='Convert a VGM file to MGSDRV MML (SCC + PSG + OPLL)',
        epilog='Also emits a volume-free blueprint/<stem>.mml with source-timbre comments; direct VGM is enabled by default.')
    parser.add_argument('vgm', help='Input VGM file')
    parser.add_argument('--output-format', choices=['mml', 'vgm', 'both'], default='both',
                        help='Emit MML, reconstructed musical VGM, or both (default: both)')
    parser.add_argument('--song-loop', choices=['none', 'source'], default='none',
                        help='Direct VGM song loop: finite playback or declared source loop (default: none)')
    parser.add_argument('--target', choices=['mgs'], default='mgs',
                        help='Output target (MGSDRV MML)')
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
    from score_normalization import add_arguments as add_score_arguments
    add_score_arguments(parser)
    parser.add_argument('--fm-state-ms', type=float, default=None,
                        help='OPLL internal pitch/volume state threshold in ms (effective default 1); enables optional normalization')
    parser.add_argument('--normalization-ms', type=float, default=None,
                        help='Maximum target timing correction in ms (effective default 8); enables optional normalization, not gate deletion')
    volume_curves = parser.add_mutually_exclusive_group()
    volume_curves.add_argument('--software-volume-curves', action='store_true', default=False,
                        help='Share exact fixed-pitch PSG/SCC attack volume curves (opt-in)')
    volume_curves.add_argument('--no-software-volume-curves', dest='software_volume_curves',
                               action='store_false', help='Disable PSG/SCC software volume curve projection')
    parser.add_argument('--score-guided-loops',action='store_true',
                        help='Propose melodic repeats from score; preserve exact output commands and target-specific envelope handling')
    parser.add_argument('--psg-state-ms',type=float,default=None,
                        help='Opt-in maximum contiguous changed PSG volume interval in ms (default: disabled)')
    parser.add_argument('--scc-state-ms',type=float,default=None,
                        help='Opt-in maximum contiguous changed SCC volume interval in ms (default: disabled)')
    parser.add_argument('--curve-volume-error',type=float,default=None,
                        help='Explicit maximum register-level volume error, 0..15, for curve approximation')
    parser.add_argument('--curve-mean-error',type=float,default=None,
                        help='Explicit maximum duration-weighted mean register-level error for curve approximation')
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
                             software_volume_curves=args.software_volume_curves,
                             score_guided_loops=args.score_guided_loops,
                             psg_state_ms=args.psg_state_ms,scc_state_ms=args.scc_state_ms,
                             curve_volume_error=args.curve_volume_error,curve_mean_error=args.curve_mean_error,
                             score_normalize=args.score_normalize,score_tempo=args.score_tempo,
                             blueprint_score_normalize=args.blueprint_score_normalize)
    except ValueError as error:
        parser.error(str(error))
    args.normalize_lengths = options.enabled
    if args.score_guided_loops and args.legacy_loops:
        parser.error('--score-guided-loops cannot be combined with --legacy-loops')
    if args.sync_min_gap < 0:
        parser.error('--sync-min-gap must be nonnegative')
    if args.song_loop != 'none' and args.output_format == 'mml':
        parser.error('--song-loop applies to VGM output; select --output-format vgm or both')
    if args.normalize_lengths and args.raw_ticks:
        parser.error('--normalize-lengths cannot be combined with --raw-ticks')
    if args.score_normalize and args.raw_ticks:
        parser.error('--score-normalize cannot be combined with --raw-ticks')

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

    from pathlib import Path
    from mgs_force import inspect_projection
    root = Path(song_dir)
    report_path = root / f'{base_name}.conversion.json'
    if args.output_format != 'vgm':
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
                  options=options.as_dict(), output_format=args.output_format, source_segments_unchanged=True)
    def save_report():
        report_path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    save_report()
    try:
        from musical_conversion import build_plan
        decisions = {}
        shared_plan, execution = build_plan(vgm_path, song_dir, base_name,
            normalization_ms=options.effective_normalization_ms,
            fm_state_ms=options.effective_fm_state_ms, normalize_lengths=args.normalize_lengths,
            software_volume_curves=args.software_volume_curves, force=args.force,
            psg_part=args.psg_part, enhance_drums=args.enhance_drums,
            song_loop=args.song_loop, dump_passes=args.dump_passes or args.debug,
            psg_input=args.psg_input, scc_input=args.scc_input,
            score_guided_loops=args.score_guided_loops,curve_approx_options=options.curve_approx_options,
            score_normalize=options.score_normalize,score_tempo=options.score_tempo,
            decision_sink=decisions)
        from musical_blueprint import write_blueprint
        report['curve_approximation']=execution.get('curve_approximation',{})
        for chip,summary in report['curve_approximation'].items():
            if summary.get('status')=='abstained':
                print(f"{chip.upper()} curve approximation: abstained ({summary['reason']})")
            else:
                print(f"{chip.upper()} curve approximation: {summary['replaced_notes']} notes replaced; "
                      f"maximum register-level error {summary['maximum_volume_error']}")
        blueprint_plan = shared_plan
        if options.blueprint_score_normalize:
            from musical_blueprint import score_timing_view
            blueprint_plan = score_timing_view(shared_plan, tempo=options.score_tempo,
                                              output_root=root, stem=base_name)
        report['blueprint'] = write_blueprint(blueprint_plan, root, base_name)
        save_report()
        conversion_input = decisions.get('conversion_input', vgm_path)
        source_projection = decisions.get('source_projection')
        if source_projection is not None:
            report['source_projection'] = source_projection
        report['shared_musical_plan'] = str(root / f'{base_name}.musical_plan.json')
        report['shared_normalization'] = decisions['mapper'].report
        if options.score_normalize:
            report['score_normalization']=execution.get('score_normalization')
            timing=report['score_normalization']
            print(f"Score normalization: tempo {timing['reference_tempo']}; 1/64={timing['quantum_ms']:.4f} ms; "
                  f"{len(timing['sync_points'])} per-device quiet anchors")
            for device in timing['devices']:
                print(f"  {device['device_id']}: {device['status']}; "
                      f"collapsed gates {device['collapsed_units']}; {device['reason']}")
        if args.output_format != 'vgm':
            legacy_execution = decisions.get('legacy_execution_plan', shared_plan)
            sustained = [c for c in legacy_execution.controls if c.chip == 'opll'
                         and c.kind == 'pitch' and c.value[2]]
            report['backend_losses'] = ([dict(kind='opll_sustain_not_encoded_by_mgs_lowering',
                inherited=True, state_controls=len(sustained),
                retained_in_shared_plan=execution.get('target_profile') != 'native',
                retained_in_direct_vgm=execution.get('target_profile') != 'native',
                retained_in_projected_execution=True,
                reference_basis='original_source' if execution.get('target_profile') == 'native' else 'accepted_msx_execution',
                unit_ids=sorted({c.unit_id for c in sustained if c.unit_id}))] if sustained else [])
        force_summary = execution['force']
        if args.output_format in ('vgm', 'both'):
            try:
                report['direct_vgm'] = _write_direct_vgm(shared_plan, vgm_path, song_dir, base_name)
                report.setdefault('outputs', {})['vgm'] = dict(status='success', path=report['direct_vgm']['vgm'])
            except Exception as error:
                report['direct_vgm']=dict(status='failed',error_type=type(error).__name__,detail=str(error))
                report.setdefault('outputs',{})['vgm']=dict(status='failed',detail=str(error))
                if args.output_format=='vgm':
                    save_report()
                    raise
            save_report()
        if args.output_format == 'vgm':
            report.update(status='success', vgm=report['direct_vgm']['vgm'],
                          normalization=decisions['mapper'].report, compiler_invoked=False,
                          mml_generated=False)
            save_report()
            return
        if execution.get('mgs_projection_error'):
            raise ValueError('MGS execution lowering failed: '+execution['mgs_projection_error']['detail'])
        if execution.get('target_profile') == 'native':
            from mgs_force import inspect_projection
            # Native source acceptance and native VGM are not MGS projection.
            # Apply the existing explicit omission/blocking policy only here.
            force_summary = inspect_projection(conversion_input, root, base_name, force=args.force)
        report['force'] = dict(enabled=bool(args.force), omission_count=force_summary['omission_count'],
                               csv_path=force_summary['csv_path'])
        if args.force:
            print(f"Forced MGS projection: {force_summary['omission_count']} omitted source writes")
            if force_summary['omission_count']:
                print(f"Omission details: {force_summary['csv_path']}")
            partial = report.get('source_projection') or {}
            if partial.get('force_partial'):
                print(f"HuC6280 partial projection: retained source channels {partial['retained_source_channels']}; "
                      f"omitted source channels {partial['omitted_source_channels']} (zero-based)")
                print(f"Projection details: {root / (base_name + '.huc6280.projection.json')}")
        if not args.normalize_lengths:
            disabled = dict(enabled=False, applied=False, status='disabled',
                reason='optional normalization not requested', source_segments_unchanged=True,
                normalization_ms=float(options.effective_normalization_ms),
                fm_state_ms=float(options.effective_fm_state_ms), whole_gate_omission=False,
                fm_state_scope='OPLL melody within accepted normalization only',
                psg_scc_curves_filtered=False, omitted_states=0)
            (root / f'{base_name}.normalization.json').write_text(json.dumps(disabled, indent=2), encoding='utf-8')
            (root / f'{base_name}.fm.short_states.json').write_text(json.dumps(disabled, indent=2), encoding='utf-8')
        mgs_root=decisions.get('score_output_root',song_dir)
        _convert_mgs(args, options, str(conversion_input), mgs_root, base_name, decision_context=decisions)
        if mgs_root!=song_dir:
            import shutil
            shutil.copyfile(Path(mgs_root)/f'{base_name}.mml',root/f'{base_name}.mml')
            for suffix in ('mgs.force.json','mgs.force.csv','normalization.json','volume_curves.target.json',
                           'drums.json','psg.selection.json'):
                artifact=Path(mgs_root)/f'{base_name}.{suffix}'
                if artifact.is_file():shutil.copyfile(artifact,root/artifact.name)
        from mml_layout import format_mml_loops
        main_mml=root/f'{base_name}.mml'
        main_mml.write_text(format_mml_loops(main_mml.read_text(encoding='cp932')),
                            encoding='cp932', newline='\n')
        report['normalization'] = json.loads((root / f'{base_name}.normalization.json').read_text(encoding='utf-8'))
        if args.software_volume_curves:
            report['volume_curve_target'] = json.loads((root / f'{base_name}.volume_curves.target.json').read_text(encoding='utf-8'))
        if args.enhance_drums:
            report['drums'] = json.loads((root / f'{base_name}.drums.json').read_text(encoding='utf-8'))
        if args.psg_part != 'all':
            report['psg_selection'] = json.loads((root / f'{base_name}.psg.selection.json').read_text(encoding='utf-8'))
        report.update(status='success', mml=str(root / f'{base_name}.mml'), mml_generated=True)
        report.setdefault('outputs', {})['mml'] = dict(status='success', path=report['mml'],
            song_loop='finite score; loop selection applies to direct VGM')
        if report.get('direct_vgm', {}).get('status') == 'failed':
            report.update(status='partial_failure', detail='MML generated; requested reference VGM failed')
    except Exception as error:
        report.update(status='conversion_failed', error_type=type(error).__name__, detail=str(error))
        if args.output_format != 'vgm':
            report.setdefault('outputs', {})['mml'] = dict(status='conversion_failed', detail=str(error))
        save_report()
        raise
    else:
        save_report()
        return 1 if report['status'] == 'partial_failure' else 0


def _convert_mgs(args, options, vgm_path, song_dir, base_name, *, decision_context=None):
    from pathlib import Path
    # ── Step 1: Parse VGM → SCC + PSG + OPLL log/trace CSVs ──────
    opm_metadata = {}
    (psg_log_csv, scc_log_csv, psg_trace_csv, scc_trace_csv,
     opll_log_csv, opll_trace_csv, opll_voice_csv, opll_regs_csv) = parse_vgm(
         vgm_path, song_dir, dump_loop=args.debug or args.dump_passes,
         include_vgmticks=args.vgmticks or args.normalize_lengths or args.score_normalize or args.enhance_drums or args.software_volume_curves or args.psg_part != 'all',
         opm_metadata=opm_metadata, dump_opm_segments=args.debug or args.dump_passes)
    if options.score_normalize:
        from score_normalization import sample_csv,timing_for_chip
        sample_csv(opll_trace_csv)
        sample_csv(opll_voice_csv)

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
        from pre_envelope_loops import LoopFirstEnvelopeBank,ScoreGuidedEnvelopeBank
        envelope_bank = (ScoreGuidedEnvelopeBank if args.score_guided_loops else LoopFirstEnvelopeBank)(deferred=True)
        if args.score_guided_loops:
            envelope_bank.score_guide=getattr((decision_context or {}).get('musical_plan'),'score_guide',None)
            envelope_bank.guide_bindings=((decision_context or {}).get('source_projection') or {}).get('allocation',())
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
    if decision_context is not None:
        accepted = {performance.chip: performance for performance in decision_context['performances']}
        pending = []
        for segments, chip, path, kwargs in envelope_bank.pending:
            if chip not in accepted:
                Path(path).write_text('', encoding='utf-8')
                continue
            performance = accepted[chip]
            pending.append((performance.reconstruct_segments(), chip, path,
                            dict(kwargs, performance=performance,
                                 **({'score_timing':timing_for_chip(decision_context['score_normalization'],chip)}
                                    if options.score_normalize else {}))))
        envelope_bank.pending = pending
        selection_candidates = decision_context.get('selection_candidates') or ()
        if args.psg_part != 'all':
            projected_performance = accepted['psg']
            selected_psg = projected_performance.reconstruct_segments()
            summary = decision_context.get('selection_summary') or {}
            print(f"PSG selection: {args.psg_part}; shared accepted musical decisions")
    else:
        if args.psg_part != 'all':
            from pathlib import Path
            from psg_part_selection import select, dump as dump_selection
            from psg_scc_performance import analyze, dump as dump_performance
            from chip_segments import PsgSegment, dump_segments
            native_psg = next(p for p in performances if p.chip == 'psg')
            selected_psg, selection_candidates, summary, catalog, membership = select(native_psg, args.psg_part)
            dump_selection(song_dir, base_name, summary, catalog, membership)
            projected_performance = analyze(selected_psg, 'psg',tick_clock_hz=native_psg.tick_clock_hz)
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
    if decision_context is not None and opll_mode:
        shared = decision_context.get('legacy_execution_plan',decision_context['musical_plan'])
        if any(unit.chip == 'opll' and unit.channel >= 6 and not unit.rest
               and unit.articulation != 'inferred_percussion' for unit in shared.units):
            raise ValueError('MGSDRV rhythm layout cannot also represent accepted melodic channels 7-9; direct VGM remains available')

    # ── Step 4: OPLL MML pipeline ────────────────────────────────
    opll_mml_path = process_opll_csv(opll_trace_csv, song_dir, stem=base_name,
                                     dump_passes=args.dump_passes,
                                     debug=args.debug,
                                     voice_csv_path=opll_voice_csv,
                                     raw_ticks=args.raw_ticks, source_loops=not args.legacy_loops,
                                     opll_mode=opll_mode,score_guided=args.score_guided_loops,
                                     score_timing=timing_for_chip(decision_context['score_normalization'],'opll') if options.score_normalize else None,
                                     decision_segments=(decision_context or {}).get('opll_source_segments') if options.score_normalize else None)
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
                                             fm_state_ms=options.effective_fm_state_ms,
                                             decision_mapper=decision_context.get('mapper') if decision_context else None,
                                             score_guided=args.score_guided_loops)
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
            if options.score_normalize and options.score_tempo!=225:
                corrected=control_texts
                tie_report=dict(status='inline_curves',applied=False,
                    reason='score tempo differs from validated tied-envelope driver profile')
            else:
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
            fallback_context = decision_context
            packaging = None
            if decision_context is not None:
                base = decision_context.get('base_performances')
                if base is None:
                    raise ValueError('MML backend needs retained pre-curve partitions for safe fallback') from error
                accepted = {p.chip: p for p in decision_context['performances']}
                decomposition = []
                mapping = []
                for performance in base:
                    if performance.chip not in accepted:
                        continue
                    source = accepted[performance.chip]
                    if _curve_timeline(performance) != _curve_timeline(source) and options.curve_approx_options:
                        from curve_projection_validation import repartition
                        performance=repartition(performance,source)
                    if _curve_timeline(performance) != _curve_timeline(source):
                        raise ValueError('MML partition fallback would change the accepted volume timeline') from error
                    decomposition.append(performance)
                    mapping.extend(dict(chip=performance.chip, channel=ch, backend_note=index,
                        source_segment_indices=note.segment_indices, start_tick=note.start,
                        end_tick=note.start + note.length)
                        for ch, notes in performance.channels for index, note in enumerate(notes))
                fallback_context = dict(decision_context, performances=tuple(decomposition),
                                        backend_partition_fallback=True)
                packaging = dict(backend_partition_fallback=True,
                    semantic_volume_timeline_unchanged=True,
                    shared_clock_preserved=True, source_unit_mapping=mapping)
            print(f'Software volume curves: retaining ordinary projection ({error})')
            _convert_mgs(fallback_args, replace(options, software_volume_curves=False),
                         vgm_path, song_dir, base_name, decision_context=fallback_context)
            tie_report = dict(status='fallback', applied=False, reason=str(error),
                              source_segments_unchanged=True, fallback='ordinary complete MGS pipeline')
            if packaging:
                tie_report.update(packaging)
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
            overlay_candidates = (() if decision_context is not None else infer(performances))
            overlay_performances = performances
        with open(os.path.join(song_dir, f'{base_name}.normalization.json'), encoding='utf-8') as stream:
            normalization = json.load(stream)
        opll_mode, drum_report = apply(overlay_candidates, native_opll, overlay_performances,
            song_dir, base_name, native_mode=opll_mode, normalization=normalization,
            raw_ticks=args.raw_ticks, dump_passes=args.dump_passes or args.debug,
            control_sources=drum_control_sources,
            decision_projection=decision_context.get('drum_projection') if decision_context else None)
        has_opll = has_opll or bool(drum_report['added_hits'])
        print(f"Rhythm enhancement: {drum_report['added_hits']} added hits; {drum_report['reason']}")

    # ── Step 5: Build merged MML ──────────────────────────────────
    if options.score_normalize:normalized_tempo=options.score_tempo
    target_scc = has_scc and args.psg_part == 'all'
    target_opll = has_opll if args.psg_part == 'all' else bool(args.enhance_drums and drum_report['added_hits'])
    merged_text = _build_merged_mml(base_name, song_dir,
                                    has_psg, target_scc, target_opll,
                                    raw_ticks=args.raw_ticks,
                                    sync_min_gap=args.sync_min_gap,
                                    name=args.name, title=args.title, tempo=normalized_tempo, opll_mode=opll_mode)
    merged_text = override_alloc(merged_text, args.alloc)
    if options.score_normalize:
        from mml_note_values import decompose
        merged_text=decompose(merged_text,dump_prefix=os.path.join(song_dir,base_name))
        from score_normalization import comment_header
        merged_text=comment_header(merged_text,(decision_context or {}).get('score_normalization'))
    if args.enhance_macros:
        from structured_macros import enhance_macros
        merged_text = enhance_macros(merged_text,
            dump_prefix=os.path.join(song_dir, base_name) if args.dump_passes else None)
    from mml_format import format_mml
    merged_text = format_mml(merged_text)
    from mml_notation import compact as compact_notation
    merged_text=compact_notation(merged_text)
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
    sys.exit(main())
