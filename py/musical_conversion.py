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


def _build_accepted_plan(source, outdir, stem=None, *, normalization_ms=8, fm_state_ms=24,
               normalize_lengths=True, software_volume_curves=True, force=False,
               psg_part='all', enhance_drums=False, song_loop='none', dump_passes=True,
               decision_sink=None, psg_input='trace', scc_input='trace',
               source_performance=None, prepared_input=None, prepared_projection=None,
               source_score_guide=None, score_guided_loops=False, curve_approx_options=None,score_target_clock=False):
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
    conversion_input, projection = ((prepared_input, prepared_projection) if prepared_input is not None
                                    else prepare(source, root, stem, force=force))
    raw = read_vgm_bytes(conversion_input)
    from native_imports import inspect_source
    source_inventory = inspect_source(raw)
    native_profile = bool(source_inventory['active_chips']) or bool(
        projection and source_performance is not None and
        any(device.chip == 'huc6280' for device in source_performance.devices))
    if native_profile and (psg_part != 'all' or enhance_drums):
        raise ValueError('Native VGM profiles currently preserve all source parts; MSX part selection/enhancement is separate')
    inventory = (dict(enabled=False, omission_count=0, omissions=[], csv_path='',
                      scope='source acceptance; MGS projection policy is separate') if native_profile else
                 inspect_projection(conversion_input, root, stem, force=force))
    metadata = {}
    paths = parse_vgm(str(conversion_input), str(root), include_vgmticks=True,
                      dump_loop=True, loop_metadata=metadata)
    if score_target_clock:
        from score_normalization import sample_csv
        sample_csv(paths[5])
        sample_csv(paths[6])
    psg_segments = build_psg(paths[2] if psg_input == 'trace' else paths[0], root, stem, dump_passes=dump_passes)
    scc_segments = build_scc(paths[3] if scc_input == 'trace' else paths[1], root, dump_passes=dump_passes, stem=stem).segments
    opll_segments, _ = build_opll_segments(paths[5])
    from opll_segments import dump_segments as dump_opll_segments
    dump_opll_segments(opll_segments, root / f'{stem}.opll.native.segments.csv')
    if score_target_clock:
        from score_normalization import sample_segments
        psg_segments=sample_segments(psg_segments,root/f'{stem}.psg.sample_clock.csv')
        scc_segments=sample_segments(scc_segments,root/f'{stem}.scc.sample_clock.csv')
        opll_segments=sample_segments(opll_segments,root/f'{stem}.opll.sample_clock.csv')
    native = [analyze(psg_segments, 'psg',tick_clock_hz=44100 if score_target_clock else 60),
              analyze(scc_segments, 'scc',tick_clock_hz=44100 if score_target_clock else 60)]
    for performance in native:
        dump(performance, root / f'{stem}.{performance.chip}.native')
    selection_candidates = None
    selection_summary = None
    if psg_part != 'all':
        from psg_part_selection import select, dump as dump_selection
        selected, selection_candidates, summary, catalog, membership = select(native[0], psg_part)
        selection_summary = summary
        dump_selection(root, stem, summary, catalog, membership)
        performances = [analyze(selected, 'psg',tick_clock_hz=native[0].tick_clock_hz)]
    else:
        performances = native
    mapper = choose_timing(opll_segments, paths[6], enabled=normalize_lengths,
                           normalization_ms=normalization_ms, fm_state_ms=fm_state_ms,
                           num_channels=9)
    if score_target_clock:
        from score_normalization import SampleTimingMapper
        mapper=SampleTimingMapper()
    accepted = []
    curve_reports={}
    for performance in performances:
        if software_volume_curves:
            curves = project_curves(performance)
            dump_curves(curves, root / f'{stem}.{performance.chip}.volume_curves', details=dump_passes)
            performance = curves.performance
        if curve_approx_options and curve_approx_options.get(performance.chip,{}).get('state_ms'):
            from psg_scc_curve_approx import project as approximate, dump as dump_approximation
            approximation=approximate(performance,**curve_approx_options[performance.chip])
            if mapper.applied:
                from psg_scc_curve_approx import abstain
                approximation=abstain(approximation,'normalized_clock_requires_post_lowering_error_validation')
            dump_approximation(approximation,root/f'{stem}.{performance.chip}.curve_approx',details=True)
            curve_reports[performance.chip]=approximation.summary()
            performance=approximation.performance
        if source_score_guide is not None:
            from score_structure import map_partitions
            rows=map_partitions(source_score_guide,performance,(projection or {}).get('allocation',()))
            (root/f'{stem}.{performance.chip}.score_guide.mapping.json').write_text(
                json.dumps(dict(source_guide=f'{stem}.score_guide.json',
                    executable_cuts_applied=False,mappings=rows),indent=2)+'\n',encoding='utf-8')
        dump(performance, root / f'{stem}.{performance.chip}.accepted')
        accepted.append(performance)
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
    if song_loop == 'source' and not native_profile:
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
    # The source layer is primary. The former MusicalPlan is an output-specific
    # accepted execution, retained separately when native chips are present.
    if source_performance is None:
        from native_source_music import build_native_performance
        try:
            source_performance = build_native_performance(conversion_input, root, stem,
                legacy_performances=tuple(native), legacy_opll_segments=opll_segments)
        except ValueError:
            if native_profile:
                raise
            source_performance = None
    if source_performance is not None:
        source_performance.dump(root, stem)
        plan = replace(plan, source_performance=source_performance,score_guide=source_score_guide,
            metadata=plan.metadata + (('source_performance_ref', f'{stem}.native_music.json'),)+
                ((('score_guide_ref',f'{stem}.score_guide.json'),) if source_score_guide is not None else ()))
    legacy_execution_plan = plan
    if native_profile:
        plan.dump(root, stem+'.mgs_projection')
        loop_sample = source_performance.song_loop_sample if song_loop == 'source' else None
        if song_loop == 'source' and loop_sample is None:
            raise ValueError('Native source has no valid declared loop')
        plan = replace(plan, units=(), controls=(), patterns=(),
            end_sample=source_performance.end_sample, source_end_sample=source_performance.end_sample,
            song_loop_sample=loop_sample, chip_clocks=tuple((d.device_id, d.clock_hz)
                for d in source_performance.devices), metadata=tuple(
                    (k, v) for k, v in plan.metadata if k != 'target_profile') +
                (('target_profile', 'native'), ('native_time_domain', 'original_source_samples')))
    plan.dump(root, stem)
    if decision_sink is not None:
        decision_sink.update(performances=tuple(accepted), mapper=mapper,
            base_performances=tuple(performances),
            opll_source_segments=opll_segments,
            native_performances=tuple(native), selection_candidates=selection_candidates,
            selection_summary=selection_summary, drum_projection=drum_projection,
            conversion_input=str(conversion_input), source_projection=projection, musical_plan=plan)
        decision_sink['legacy_execution_plan'] = legacy_execution_plan
    report = dict(status='planned', output='direct_vgm', source=str(source.resolve()),
        target_profile='native' if native_profile else 'msx_standard', source_projection=projection,
        source_end_sample=source_end, end_sample=plan.end_sample,
        units=len(source_performance.units) if native_profile else len(plan.units),
        controls=len(source_performance.controls) if native_profile else len(plan.controls),
        patterns=len(source_performance.patterns) if native_profile else len(plan.patterns),
        chips=sorted({d.chip for d in source_performance.devices}) if native_profile else sorted({c.chip for c in plan.controls}),
        normalization=mapper.report, force=inventory, psg_part=psg_part,
        software_volume_curves=software_volume_curves, enhance_drums=enhance_drums,
        curve_approximation=curve_reports,score_guided_loops=score_guided_loops,
        loop_policy=song_loop, source_loop=metadata,
        mml_generated=False, compiler_invoked=False)
    if native_profile:
        from native_vgm import capability_report
        report['native_source'] = capability_report(source_performance)
    (root / f'{stem}.execution.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return plan, report


def _build_native_plan(source, outdir, stem=None, **options):
    """Retain source music before independently lowering the MGS execution.

    A supported native performance remains usable by the score/reference
    backends even when accepted MGS timing or source policy cannot be lowered.
    The failure and the different execution basis are explicit, never silent.
    """
    from huc6280_projection import prepare
    from native_source_music import build_native_performance
    from musical_plan import MusicalPlan
    from musical_timing import AcceptedTimingMapper
    from native_vgm import capability_report
    source=Path(source);root=Path(outdir)
    root.mkdir(parents=True,exist_ok=True)
    stem=source.stem if stem is None else stem
    conversion_input,projection=source,None
    source_error=None
    try:
        performance=build_native_performance(source,root,stem)
    except ValueError as error:
        performance=None
        source_error=dict(status='failed',error_type=type(error).__name__,detail=str(error))
    sink=options.get('decision_sink')
    guide=None
    if performance is not None:
        from score_structure import build as build_score_guide
        guide=build_score_guide(performance,repeats=options.get('score_guided_loops',False))
        guide.dump(root,stem)
    try:
        conversion_input,projection=prepare(source,root,stem,force=options.get('force',False))
        plan,report=_build_accepted_plan(source,root,stem,**options,
            source_performance=performance,prepared_input=conversion_input,prepared_projection=projection,
            source_score_guide=guide)
    except Exception as error:
        if performance is None:
            raise
        failure=dict(error_type=type(error).__name__,detail=str(error))
        loop=performance.song_loop_sample if options.get('song_loop','none')=='source' else None
        if options.get('song_loop','none')=='source' and loop is None:
            raise ValueError('Native source has no valid declared loop') from error
        plan=MusicalPlan((),(),performance.end_sample,performance.end_sample,
            tuple((d.device_id,d.clock_hz) for d in performance.devices),loop,
            metadata=(('target_profile','native'),('native_time_domain','original_source_samples'),
                ('source_sha256',performance.source_sha256),('source_performance_ref',f'{stem}.native_music.json'),
                ('source_projection',projection),('mgs_projection_error',failure)),
            source_performance=performance,score_guide=guide)
        plan.dump(root,stem)
        unavailable=dict(status='unavailable',applied=False,reason='MGS execution lowering failed; native source retained')
        report=dict(status='planned',target_profile='native',source=str(source.resolve()),
            source_projection=projection,source_end_sample=performance.end_sample,end_sample=performance.end_sample,
            force=dict(enabled=False,omission_count=0,omissions=[],csv_path=''),normalization=unavailable,
            native_source=capability_report(performance),mgs_projection_error=failure,
            compiler_invoked=False,mml_generated=False)
        (root/f'{stem}.execution.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        if sink is not None:
            sink.update(conversion_input=str(conversion_input),source_projection=projection,
                musical_plan=plan,mapper=AcceptedTimingMapper(report=unavailable),
                legacy_execution_plan=plan,mgs_projection_error=failure)
        return plan,report
    if source_error is not None:
        report['native_source_error']=source_error
        if sink is not None:sink['native_source_error']=source_error
        (root/f'{stem}.execution.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return plan,report


def build_plan(source,outdir,stem=None,*,score_normalize=False,score_tempo=225,**options):
    """Optional per-device score view, then the established target lowerer."""
    root=Path(outdir);stem=stem or Path(source).stem
    for suffix in ('json','anchors.csv','intervals.csv','controls.csv'):
        (root/f'{stem}.score_normalization.{suffix}').unlink(missing_ok=True)
    if not score_normalize:return _build_native_plan(source,outdir,stem,**options)
    from native_source_music import build_native_performance
    from native_vgm import write_native_vgm
    from score_normalization import normalize
    source=Path(source)
    root.mkdir(parents=True,exist_ok=True)
    original=build_native_performance(source,root,stem)
    normalized=normalize(original,tempo=score_tempo,source_loop=options.get('song_loop')=='source')
    normalized.dump(root,stem)
    # Never run the old fitted clock after this independent musical decision.
    options=dict(options,normalize_lengths=False,score_target_clock=True)
    work=root/'_score_normalized';work.mkdir(exist_ok=True)
    projected=work/f'{stem}.vgm'
    if projected.resolve()==source.resolve():raise ValueError('Score projection must not overwrite its source VGM')
    write_native_vgm(normalized.performance,projected,gd3=source_gd3(source),
                     mapping_path=work/f'{stem}.projected.writes.csv',source_loop=options.get('song_loop')=='source')
    # Interpret original durations. Reference-VGM boundary warping is a separate
    # projection and cannot supply the durations that the score pass truncates.
    plan,report=_build_native_plan(source,work,stem,**options)
    reference=build_native_performance(projected,work/'reference',stem)
    if plan.source_performance is None:raise ValueError('Score normalization requires a reparsed native performance')
    metadata=tuple((key,value) for key,value in plan.metadata if key not in
        ('target_profile','source_performance_ref','score_guide_ref'))
    metadata+=(('target_profile','native'),('native_time_domain','score_normalized_source_samples'),
        ('source_performance_ref',str(work/'reference'/f'{stem}.native_music.json')),
        ('score_guide_ref',str(work/f'{stem}.score_guide.json')),
        ('original_source_performance_ref',str(root/f'{stem}.native_music.json')),
        ('score_normalization',normalized.report))
    plan=replace(plan,metadata=metadata,source_end_sample=original.end_sample,
                 source_performance=reference,score_performance=original)
    sink=options.get('decision_sink')
    if sink is not None:
        sink.update(musical_plan=plan,score_output_root=str(work),score_normalization=normalized.report)
    report.update(source=str(source.resolve()),score_normalization=normalized.report,
        target_profile='native',execution_source=str(source),reference_source=str(projected),
        original_segments_retained=True,score_duration_input='original interpreted sample spans')
    plan.dump(root,stem)
    (root/f'{stem}.execution.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return plan,report


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
