"""Native SN76489 (DCSG) sources -> MSX cartridge variant VGMs.

The MSX composition follows the shape the user set for PSG-class
content and the precedent of the OPN2 route's DCSG lanes
(opn2_target_vgm.project_dcsg): the DCSG lanes stay on PSG-class
devices — the first chip on the internal MSX PSG (AY commands),
the second on the OPNA Sound Cartridge's SSG section. That PSG
composition is the whole ``sfg01/dac_makoto`` variant: there is
no FM lane in it. The ``layered`` variant adds the x68k DCSG>OPM
projection (dcsg_opm.py, ported) on the pseudo-OPM cartridge at
its 3.579545 MHz clock, the layering principle applied to this
route's two grounded projections.

Variant applicability, recorded by the export instead of
emitting degenerate files:

- ``makoto``: no composition. An OPNA-side DCSG route is the
  mucom88-side stage (S3); nothing grounded exists here yet.
- ``sfg01/dac_y8950``: a DCSG source has no DAC-class lane for
  the Y8950 to carry.
- ``opm4mhz``: the sfg01 composition has no OPM lane whose clock
  the variant would switch; the layered file is the only OPM
  composition and it runs at the cartridge clock.
"""
import csv
import json
from pathlib import Path

from dcsg_opm import dump_projection, project as project_dcsg_opm
from native_imports.source import analyze_source
from opn2_target_vgm import TARGET_CLOCK, project_dcsg, write_vgm


def convert(source, outdir, *, force=False, layered=False, target='sfg01',
            dac='opna'):
    """Analyze one DCSG VGM and emit its cartridge variant VGM.

    Same contract as opn2_target_vgm.convert. ``target`` accepts
    only 'sfg01' (the PSG composition); 'makoto' and 'opm4mhz'
    raise with the applicability reason so callers record the
    variant unavailable rather than emitting a duplicate file.
    """
    if target == 'makoto':
        raise ValueError('DCSG sources have no makoto composition in this '
                         'stage: the OPNA-side DCSG route belongs to the '
                         'mucom88-side stage (S3)')
    if target == 'opm4mhz':
        raise ValueError('the DCSG sfg01 composition has no OPM lane; the '
                         '4 MHz OPM clock variant does not apply (the '
                         'layered composition runs at the cartridge clock)')
    if target != 'sfg01':
        raise ValueError(f'Unknown DCSG target cartridge: {target!r}')
    if dac != 'opna':
        raise ValueError('DCSG sources have no DAC-class lane for the '
                         'Y8950 to carry')
    source, outdir = Path(source), Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    stem = source.stem
    bundle = analyze_source(source, outdir, stem)
    if 'dcsg' not in bundle['active_chips']:
        raise ValueError('Input has no DCSG (SN76489) writes')
    extra = [chip for chip in bundle['active_chips'] if chip != 'dcsg']
    if extra:
        raise ValueError('DCSG variant route covers DCSG-only sources in this '
                         f'stage; this source also uses {extra}')
    analysis = bundle['analyses']['dcsg']
    if analysis is None:
        raise ValueError(f"DCSG analysis failed: {bundle['errors'].get('dcsg')}")
    loop = bundle['loop']
    loop_start = loop_event_id = None
    if loop.get('status') == 'valid':
        loop_start = loop['loop_start_samples']
        loop_event_id = next((e.source_event_id for e in bundle['events']
                              if e.address == loop.get('loop_address')), None)
    rows, losses, stats = project_dcsg(
        analysis, loop_start=loop_start, loop_event_id=loop_event_id)
    # project_dcsg emits per-channel groups; the serializer
    # needs the merged stream in source sample order (the OPN2
    # convert's merge does the same sort).
    rows = sorted(rows, key=lambda r: (r['source_vgmticks'],
                                       r.get('sort_rank', 1)))
    target_file = outdir / f'{stem}.target.vgm'
    write_vgm(rows, target_file, end=bundle['source_end_sample'],
              loop_start=loop_start, loop_event_id=loop_event_id,
              opm_clock=TARGET_CLOCK)
    if rows:
        dcsg_csv = outdir / f'{stem}.dcsg.writes.csv'
        with dcsg_csv.open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    layer_target, layer_target_writes, layer_stats = None, 0, {}
    if layered:
        plan = project_dcsg_opm(analysis, force=force,
                                terminate=loop.get('status') != 'valid',
                                opm_clock=TARGET_CLOCK)
        dump_projection(plan, outdir, stem)
        # scheduled_writes() is the ordering x68k's own target
        # VGM writer uses, so the layered OPM lane matches the
        # --emit-vgm stream event for event at the 4 MHz law
        # clock; each write keeps its exact source tick.
        opm_rows = [dict(source_vgmticks=w.vgmticks, source_event_id=None,
                         target_register=w.register, target_data=w.data,
                         sort_rank=1)
                    for w in plan.scheduled_writes()]
        layer_merged = sorted(rows + opm_rows,
                              key=lambda r: (r['source_vgmticks'],
                                             r.get('sort_rank', 1)))
        layer_target = outdir / f'{stem}.layer.target.vgm'
        write_vgm(layer_merged, layer_target, end=bundle['source_end_sample'],
                  loop_start=loop_start, loop_event_id=loop_event_id,
                  opm_clock=TARGET_CLOCK)
        layer_target_writes = len(layer_merged)
        layer_stats = dict(opm_writes=len(opm_rows),
                           forced_omissions=len(plan.settings['forced_omissions']),
                           approximations=len(plan.settings['approximations']))
    summary = dict(source=str(source), source_sha256=bundle['source_sha256'],
                   active_chips=list(bundle['active_chips']),
                   target_cartridge=target,
                   target_clock_hz=TARGET_CLOCK,
                   target_vgm=target_file.name,
                   target_writes=len(rows),
                   dcsg=stats,
                   layered=layered,
                   layer_target_vgm=(layer_target.name if layer_target else None),
                   layer_target_writes=layer_target_writes,
                   layer=layer_stats,
                   losses=losses,
                   loop=dict(status=loop.get('status'), start_sample=loop_start))
    (outdir / f'{stem}.dcsg_target.json').write_text(
        json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    return summary
