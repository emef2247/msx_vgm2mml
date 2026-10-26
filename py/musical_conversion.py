"""Build accepted musical information without an MML/driver capacity boundary."""
from dataclasses import replace
from pathlib import Path
import hashlib
import json

from musical_plan import combine
from vgm_io import read_vgm_bytes, read_vgm_header
from vgm_timing import command_times


def _source_patterns(performance):
    from pre_envelope_loops import prepare
    plans, _ = prepare(dict(performance.channels), performance.chip)
    rows = []
    for channel, plan in plans.items():
        def visit(nodes, depth=0):
            for node in nodes:
                if node.children:
                    rows.append((performance.chip, channel, node.start, node.end, node.repeats, depth))
                    visit(node.children, depth + 1)
        visit(plan.tree)
    return tuple(rows)


def build_plan(source, outdir, stem=None, *, normalization_ms=8, fm_state_ms=24,
               normalize_lengths=True, software_volume_curves=True, force=False,
               psg_part='all', enhance_drums=False, song_loop='none', dump_passes=True,
               decision_sink=None, psg_input='trace', scc_input='trace'):
    """Native evidence -> reconstructed units/curves -> executable shared plan.

    MGSDRV envelope banks and textual loops are deliberately absent. They can
    package these musical decisions later without limiting the direct output.
    """
    from huc6280_projection import prepare
    from mgs_force import inspect_projection
    from vgm_reader import parse_vgm
    from psg import build_segments as build_psg
    from scc import build_segments as build_scc
    from opll import _build_segments as build_opll_segments
    from psg_scc_performance import analyze, dump
    from psg_scc_volume_curves import project as project_curves, dump as dump_curves
    from psg_scc_execution import build_psg_scc
    from opll_execution import build_opll
    from musical_timing import choose_timing, AcceptedTimingMapper
    from mgs_conversion_config import sample_threshold
    from vgm_loop import read_loop_metadata

    source = Path(source)
    stem = source.stem if stem is None else stem
    root = Path(outdir)
    root.mkdir(parents=True, exist_ok=True)
    sample_threshold(normalization_ms, '--normalization-ms')
    sample_threshold(fm_state_ms, '--fm-state-ms')
    if psg_part not in ('all', 'melody', 'rhythm') or song_loop not in ('none', 'source'):
        raise ValueError('Invalid musical part or song-loop selection')
    if psg_input not in ('trace', 'log') or scc_input not in ('trace', 'log'):
        raise ValueError('Invalid source CSV selection')
    original = read_vgm_bytes(source)
    conversion_input, projection = prepare(source, root, stem)
    raw = read_vgm_bytes(conversion_input)
    inventory = inspect_projection(conversion_input, root, stem, force=force)
    metadata = {}
    paths = parse_vgm(str(conversion_input), str(root), include_vgmticks=True,
                      dump_loop=True, loop_metadata=metadata)
    psg_segments = build_psg(paths[2] if psg_input == 'trace' else paths[0], root, stem, dump_passes=dump_passes)
    scc_segments = build_scc(paths[3] if scc_input == 'trace' else paths[1], root, dump_passes=dump_passes, stem=stem).segments
    opll_segments, _ = build_opll_segments(paths[5])
    from opll_segments import dump_segments as dump_opll_segments
    dump_opll_segments(opll_segments, root / f'{stem}.opll.native.segments.csv')
    native = [analyze(psg_segments, 'psg'), analyze(scc_segments, 'scc')]
    for performance in native:
        dump(performance, root / f'{stem}.{performance.chip}.native')
    selection_candidates = None
    selection_summary = None
    if psg_part != 'all':
        from psg_part_selection import select, dump as dump_selection
        selected, selection_candidates, summary, catalog, membership = select(native[0], psg_part)
        selection_summary = summary
        dump_selection(root, stem, summary, catalog, membership)
        performances = [analyze(selected, 'psg')]
    else:
        performances = native
    accepted = []
    for performance in performances:
        if software_volume_curves:
            curves = project_curves(performance)
            dump_curves(curves, root / f'{stem}.{performance.chip}.volume_curves', details=dump_passes)
            performance = curves.performance
        dump(performance, root / f'{stem}.{performance.chip}.accepted')
        accepted.append(performance)
    mapper = choose_timing(opll_segments, paths[6], enabled=normalize_lengths,
                           normalization_ms=normalization_ms, fm_state_ms=fm_state_ms,
                           num_channels=9)
    # Every accepted boundary is checked before either output is published.
    # Curve holds remain semantic frame durations, independent of bank packing.
    try:
        for performance in accepted:
            for _, notes in performance.channels:
                mapper.boundaries([n.start + n.length for n in notes])
        plans = [build_psg_scc(p, source_raw=raw, timing=mapper) for p in accepted]
        if psg_part == 'all':
            plans.append(build_opll(opll_segments, paths[6], source_raw=raw, timing=mapper))
    except ValueError as error:
        if not mapper.applied:
            raise
        report = dict(mapper.report or {}, status='abstained', applied=False,
                      reason='global_control_or_boundary_timing: ' + str(error))
        mapper = AcceptedTimingMapper(report=report)
        plans = [build_psg_scc(p, source_raw=raw, timing=mapper) for p in accepted]
        if psg_part == 'all':
            plans.append(build_opll(opll_segments, paths[6], source_raw=raw, timing=mapper))
    patterns = tuple(row for performance in accepted for row in _source_patterns(performance))
    plan = combine(plans)
    source_end = list(command_times(raw))[-1].vgmticks
    end = max(plan.end_sample, mapper.source_sample(source_end))
    loop_sample = None
    if song_loop == 'source':
        loop = read_loop_metadata(raw)
        if loop['status'] != 'valid':
            raise ValueError('Source song-loop requested but no valid declared loop exists')
        loop_sample = mapper.source_sample(loop['loop_start_samples'])
        # The writer validates actual register dependencies before publication.
    plan = replace(plan, end_sample=end, source_end_sample=source_end,
        song_loop_sample=loop_sample, patterns=plan.patterns + patterns,
        metadata=plan.metadata + (('source_sha256', hashlib.sha256(original).hexdigest()),
            ('source_header', dict(read_vgm_header(original),
                opll_clock_raw=int.from_bytes(original[0x10:0x14], 'little'))),
            ('target_profile', 'msx_standard'), ('initial_state', 'explicit chip reset assumptions'),
            ('loop_policy', song_loop), ('source_loop', metadata),
            ('normalization', mapper.report), ('source_projection', projection),
            ('backend_note', 'MGS packaging/tick compensation is a later lowering operation')))
    drum_projection = None
    if enhance_drums:
        from drum_inference import infer
        from drum_enhancement import project_groups
        from drum_execution import add_overlay
        candidates = (selection_candidates if psg_part == 'rhythm' else () if psg_part != 'all'
                      else infer(native))
        groups, drum_end, summary, decisions = project_groups(candidates,
            opll_segments if psg_part == 'all' else {}, accepted, timing=mapper.plan)
        plan = add_overlay(plan, groups, drum_end, summary, decisions, timing=mapper)
        from rhythm_patterns import Group
        accepted_hits = {(row['target_tick'], row['instrument']) for row in decisions if row['status'] == 'added'}
        groups = tuple(Group(g.tick, g.gap, tuple(h for h in g.hits
            if h.channel != -1 or (g.tick, h.instrument) in accepted_hits)) for g in groups)
        drum_projection = (groups, drum_end, summary, decisions)
        (root / f'{stem}.drums.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    plan.dump(root, stem)
    if decision_sink is not None:
        decision_sink.update(performances=tuple(accepted), mapper=mapper,
            base_performances=tuple(performances),
            opll_source_segments=opll_segments,
            native_performances=tuple(native), selection_candidates=selection_candidates,
            selection_summary=selection_summary, drum_projection=drum_projection,
            conversion_input=str(conversion_input), source_projection=projection, musical_plan=plan)
    report = dict(status='planned', output='direct_vgm', source=str(source.resolve()),
        target_profile='msx_standard', source_projection=projection,
        source_end_sample=source_end, end_sample=plan.end_sample,
        units=len(plan.units), controls=len(plan.controls), patterns=len(plan.patterns),
        chips=sorted({c.chip for c in plan.controls}),
        normalization=mapper.report, force=inventory, psg_part=psg_part,
        software_volume_curves=software_volume_curves, enhance_drums=enhance_drums,
        loop_policy=song_loop, source_loop=metadata,
        mml_generated=False, compiler_invoked=False)
    (root / f'{stem}.execution.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return plan, report


def source_gd3(path):
    raw = read_vgm_bytes(path)
    offset = int.from_bytes(raw[0x14:0x18], 'little')
    if not offset:
        return None
    start = 0x14 + offset
    if start + 12 > len(raw) or raw[start:start + 4] != b'Gd3 ':
        raise ValueError('Invalid source GD3 block')
    stop = start + 12 + int.from_bytes(raw[start + 8:start + 12], 'little')
    if stop > len(raw):
        raise ValueError('Truncated source GD3 block')
    return raw[start:stop]
