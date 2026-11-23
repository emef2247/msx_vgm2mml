"""Cartridge VGM variants from a source-native musical performance.

Only the source ingestion stage reads VGM/State/Segments. This module can
render an authored or deserialized NativePerformance without any source file.
"""
from collections import Counter
import csv
import json
from pathlib import Path
import struct

from musical_wave_target import project_waves, project_psg_opll

# Keeping a real chip in the mix exists only in the layered form
# (owner, 2026-11-22): the per-base scc_* / psg_* compositions are
# retired in favour of scc_layered / psg_layered.
SCC_PROFILES = {'scc_layered':'layered'}
PSG_PROFILES = {'psg_layered':'layered'}
# The RX21 rhythm variants (sfg01_rx21 / makoto_rx21) are retired
# (owner, 2026-11-22): a rhythm-timbre swap inside a base profile
# made the variant list hard to read.  Compositions are grouped by
# what the added cartridge provides (PCM playback, a rhythm unit)
# or by the native chip kept.
PROFILES = ('sfg01','sfg01_opllrhythm','sfg01_opl3','makoto','makoto_msxaudio','makoto_msxaudio_msxaudio','misato','misato_msxaudio','sfg01_makoto','sfg01_msxaudio','sfg01_misato','msxaudio','msxaudio_msxaudio','opl3','opl3_makoto','opl3_msxaudio','layered', *SCC_PROFILES, *PSG_PROFILES)
# The opl3 composition has no PCM unit; these profiles pair it with
# a PCM cartridge instead.  Misato gets no such pairing with Makoto:
# both are OPNA cartridges and their I/O ports collide, so Misato's
# only PCM complement is misato_msxaudio on the main route below
# (owner, 2026-11-22).
OPL3_PCM_AUXILIARY = {'opl3_makoto':'opna','opl3_msxaudio':'y8950'}
# Composition profiles live under their base profile's folder
# (owner, 2026-11-22): vgm-variants/<base>/ holds the base, and a
# subfolder named by the added element alone -- the second
# cartridge (makoto, msxaudio, opl3, misato), the kept native chip
# (scc, psg) or the rhythm source (opllrhythm) -- holds each
# composition, e.g. vgm-variants/sfg01/makoto/.  A variant whose
# output is byte-identical to the base's own output is not
# published at all: the subfolder only carries what the
# composition actually changes.
PROFILE_PARENTS = {'sfg01_opllrhythm':'sfg01',
                   'sfg01_opl3':'sfg01','sfg01_makoto':'sfg01',
                   'sfg01_msxaudio':'sfg01','sfg01_misato':'sfg01',
                   'makoto_msxaudio':'makoto','misato_msxaudio':'misato',
                   'makoto_msxaudio_msxaudio':'makoto_msxaudio',
                   'msxaudio_msxaudio':'msxaudio',
                   'opl3_makoto':'opl3','opl3_msxaudio':'opl3',
                   **SCC_PROFILES, **PSG_PROFILES}
PROFILE_ELEMENTS = {'sfg01_opllrhythm':'opllrhythm',
                    'sfg01_opl3':'opl3','sfg01_makoto':'makoto',
                    'sfg01_msxaudio':'msxaudio','sfg01_misato':'misato',
                    'makoto_msxaudio':'msxaudio','misato_msxaudio':'msxaudio',
                    'makoto_msxaudio_msxaudio':'msxaudio',
                    'msxaudio_msxaudio':'msxaudio',
                    'opl3_makoto':'makoto','opl3_msxaudio':'msxaudio',
                    **{name:'scc' for name in SCC_PROFILES},
                    **{name:'psg' for name in PSG_PROFILES}}


def variant_folder(profile):
    parent = PROFILE_PARENTS.get(profile)
    return variant_folder(parent) / PROFILE_ELEMENTS[profile] if parent else Path(profile)
CLOCKS = {0x54:(0x30,3579545),0x56:(0x48,8000000),0x57:(0x48,8000000),
          0x51:(0x10,3579545),0xa0:(0x74,1789773),0x5c:(0x58,3579545),
          0xac:(0x58,3579545),
          0x5e:(0x5c,14318180),0x5f:(0x5c,14318180)}
# Variant volume offsets in TL steps (0.75 dB each, positive =
# quieter), set by the hidden --v-offset-* export options.  The
# rhythm defaults carry the owner's cartridge level correction of
# 2026-11-21 (30 steps, about -22.5 dB); the fitted preset JSONs
# are never edited for level adjustments.
DEFAULT_VOLUME_OFFSETS = {'opm_melody': 0, 'opm_rhythm': 30,
                          'opna_melody': 0, 'opna_rhythm': 30}


def _volume_offsets(volume_offsets):
    return {**DEFAULT_VOLUME_OFFSETS, **(volume_offsets or {})}


def _write(performance, rows, prefix, path):
    from native_imports.vgm_timing import command_times
    rows=sorted(rows,key=lambda row:(row['sample'],row.get('order',0)))
    header=bytearray(256);header[:4]=b'Vgm '
    body=bytearray(prefix);cursor=0;loop_address=None
    loop=performance.song_loop_sample
    if loop is not None and not 0<=loop<performance.end_sample:raise ValueError('Invalid musical song loop')
    def wait(count):
        while count:
            size=min(65535,count);body.extend(b'\x61'+struct.pack('<H',size));count-=size
    def advance(sample):
        nonlocal cursor,loop_address
        if sample<cursor or sample>performance.end_sample:raise ValueError('Target operation outside musical timeline')
        if loop is not None and loop_address is None and cursor<=loop<=sample:
            wait(loop-cursor);cursor=loop;loop_address=256+len(body)
            # A repeat starts with the ending chip state, not the intro's
            # cached state. Keep each register's first assignment in the loop.
            cache.clear()
        wait(sample-cursor);cursor=sample
    cache={}
    for index,row in enumerate(rows):
        advance(row['sample'])
        row['write_id']=index;row['target_address']=256+len(body)
        command=row['command']
        if command[0]==0x67:
            # A data block (for example a later PCM stream image) carries no
            # register clock or dedup state: emit it where it sits so the
            # player loads it when playback reaches it.
            row['emitted']=True;body.extend(command);continue
        if command[0]==0xd2:
            offset,clock=0x9c,row['scc_clock_raw']
        elif command[0] in CLOCKS:offset,clock=CLOCKS[command[0]]
        else:raise ValueError('Unmapped source chip escaped into cartridge output')
        struct.pack_into('<I',header,offset,clock)
        reg=command[1]
        state_only=(command[0]==0x54 and 0x20<=reg<=0xff or command[0] in (0x56,0x57) and (0x30<=reg<0x90 or 0xb0<=reg<=0xb6)
            or command[0] in (0x5c,0xac) and 0x20<=reg<=0xc8
            or command[0] in (0x5e,0x5f) and 0x20<=reg<=0xf5)
        key=(command[0],reg)
        row['emitted']=not (state_only and cache.get(key)==command[2])
        if row['emitted']:
            body.extend(command);cache[key]=command[2]
    if any(row['command'][0]==0xac for row in rows):
        # A second Y8950 is in the mix (owner, 2026-11-23): its
        # writes use 0xac and the header clock carries the VGM
        # dual-chip flag.
        struct.pack_into('<I',header,0x58,3579545|0x40000000)
    advance(performance.end_sample);body.append(0x66)
    for offset,value in ((8,0x171),(0x18,performance.end_sample),(0x34,256-0x34)):
        struct.pack_into('<I',header,offset,value)
    if any(row['command'][0]==0xa0 for row in rows):header[0x78]=0x10
    if loop_address is not None:
        struct.pack_into('<I',header,0x1c,loop_address-0x1c)
        struct.pack_into('<I',header,0x20,performance.end_sample-loop)
    raw=header+body
    gd3=bytes.fromhex(dict(performance.metadata).get('gd3_hex',''))
    if gd3:
        if gd3[:4]!=b'Gd3 ' or len(gd3)<12 or int.from_bytes(gd3[8:12],'little')+12!=len(gd3):raise ValueError('Invalid retained GD3')
        struct.pack_into('<I',raw,0x14,len(raw)-0x14);raw.extend(gd3)
    struct.pack_into('<I',raw,4,len(raw)-4)
    framing=tuple(command_times(raw))
    if not framing or framing[-1].command!=0x66 or framing[-1].vgmticks!=performance.end_sample:
        raise ValueError('Cartridge VGM timing differs from musical performance')
    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    return rows


def _split_pcm_assets(performance, lane_count):
    """Split decoded PCM assets across lane_count cartridge PCM units.

    Returns one sub-performance per unit (None for a unit that
    receives nothing).  Assets keep their identity and are assigned
    in start order to the first unit free at their start, so
    content that sounds together lands on different units; each
    unit is then projected on its own with its own 256 KiB budget.
    Content beyond the unit count falls back to the first unit,
    whose projection mixes it and records that loss.  A
    single-stream source (one MSM6258 stream or one OPN2 DAC
    timeline) is one voice and stays on the first unit whole.
    """
    from dataclasses import replace
    assets=sorted(getattr(performance,'pcm_assets',()),
                  key=lambda a:(a.start_sample,a.asset_id))
    lanes=[[] for _ in range(lane_count)]
    if assets:
        devices={d.device_id:d.chip for d in performance.devices}
        single_stream=(all(devices[a.device_id]=='msm6258' for a in assets)
            or all(devices[a.device_id]=='opn2'
                   and 'dac_timeline' in dict(a.parameters) for a in assets))
        if single_stream:
            lanes[0]=list(assets)
        else:
            free_at=[0]*lane_count
            for asset in assets:
                for lane in range(lane_count):
                    if asset.start_sample>=free_at[lane]:
                        lanes[lane].append(asset)
                        free_at[lane]=max(free_at[lane],asset.end_sample)
                        break
                else:
                    lanes[0].append(asset)
    return [replace(performance,pcm_assets=tuple(lane)) if lane else None
            for lane in lanes]


def _project_fm_layer(performance, chip, clock, *, force, include_psg=False,
                      soundcore_levels=False, melody_tl_offset=0):
    from musical_fm_target import project_fm
    fm, losses, allocation = project_fm(performance, chip, clock, force=force)
    from opll_fm_target import project_opll_fm
    opll_rows, opll_losses, opll_allocation = project_opll_fm(
        performance, chip, clock, reserved=set(allocation.values()), force=force,
        soundcore_levels=soundcore_levels, melody_tl_offset=melody_tl_offset)
    wave, wave_losses, wave_allocation = project_waves(performance, chip, clock,
        set(allocation.values()) | set(opll_allocation.values()), force=True,
        include_psg=include_psg)
    if wave_losses.get('wave_channel_capacity_units_omitted') and not force:
        raise ValueError('Waveform voices exceed cartridge FM capacity (use --force for explicit omission)')
    losses = Counter(losses)
    losses.update(opll_losses)
    losses.update(wave_losses)
    return fm + opll_rows + wave, losses, dict(clock_hz=clock,
        fm_allocation={str(k): v for k, v in allocation.items()},
        opll_allocation={str(k): v for k, v in opll_allocation.items()},
        waveform_allocation={str(k): v for k, v in wave_allocation.items()},
        losses=dict(losses))


def _project_msxaudio(performance, *, force=False, dcsg_gain=.25,
                      dual_pcm=False):
    """MSX-AUDIO profile: the Y8950 FM section is the primary target.

    OPLL voices project to Y8950 FM through the commercially
    observed conversion table and OPLL percussion to the native
    rhythm unit; Y8950 sources re-emit natively; PCM rides the
    Y8950 Delta-T unit.  NES APU / FDS and HuC6280 waveform voices
    project through the established four-harmonic wave projection
    (the y8950 arm of musical_wave_target), as on the OPM / OPNA
    bases; lanes beyond the nine-channel budget are an explicit
    omission under --force only.  Source families whose Y8950
    projection is not established yet (4-op FM) make the profile
    unavailable.
    """
    from musical_opl_target import project_opl_fm
    from musical_pcm_target import project_pcm
    allowed={'y8950','opll','psg','dcsg','msm6258','nesapu','huc6280','segapcm'}
    # The gate counts sounding devices only, as in the opl3 route:
    # a device that never sounds (an msxplay.com export lists every
    # device) must not fail the profile; a sounding unsupported
    # chip still does.
    by_id={d.device_id:d.chip for d in performance.devices}
    present={by_id[u.device_id] for u in performance.units}
    present|={by_id[e.device_id] for e in performance.percussion}
    present|={p.chip for p in performance.pcm_packets}
    bad=sorted(present-allowed)
    if bad:raise ValueError('msxaudio profile has no projection for '+', '.join(bad))
    msm_issues=[d for d in performance.decisions if d and d[0] in
        ('msm6258_pcm_source_issue','msm6258_pcm_unresolved_playback')]
    if msm_issues and not force:
        raise ValueError('MSM6258 PCM source evidence is unresolved; inspect native decisions')
    rows=[];prefix=b'';losses=Counter();pcm_stats={};plan_extra={}
    fm_rows,fm_losses,allocation=project_opl_fm(performance,force=force)
    rows.extend(fm_rows);losses.update(fm_losses)
    wave_chips={'nesapu','huc6280'}&present
    if wave_chips:
        # Waveform sources (NES APU / FDS, HuC6280) project through
        # the four-harmonic wave projection, as on the OPM / OPNA
        # bases.  Nine FM channels take two four-carrier voices.
        # A waveform lane has no native fallback here, so exceeding
        # the budget is an explicit omission under --force only.
        from musical_wave_target import project_waves
        wave_rows,wave_losses,wave_allocation=project_waves(performance,'y8950',3579545,
            reserved=set(allocation.values()),force=True,
            chips=tuple(sorted(wave_chips)))
        if wave_losses.get('wave_channel_capacity_units_omitted') and not force:
            raise ValueError('Waveform voices exceed Y8950 FM capacity (use --force for explicit omission)')
        rows.extend(wave_rows);losses.update(wave_losses)
        plan_extra['waveform_allocation']={str(k):v for k,v in wave_allocation.items()}
    opll_device=next((d.device_id for d in performance.devices if d.chip=='opll'),None)
    aux,aux_losses=project_psg_opll(performance,dcsg_gain=dcsg_gain,
        opna=False,force=True,opll_fm_device=opll_device)
    rows.extend(aux);losses.update(aux_losses)
    assets=getattr(performance,'pcm_assets',())
    if assets and dual_pcm:
        # Two MSX-AUDIO cartridges (owner, 2026-11-23): the second
        # unit's Delta-T is a second PCM voice beside the first
        # unit's, each with its own 256 KiB.  Its FM section is not
        # used.  The second unit is written as the VGM dual-chip
        # Y8950 (command 0xac, flagged RAM block).
        lane_stats=[];lane_prefixes=[]
        for instance,lane_perf in enumerate(_split_pcm_assets(performance,2)):
            if lane_perf is None:lane_stats.append(None);continue
            pcm,lane_prefix,pcm_losses,stats=project_pcm(lane_perf,'y8950',force=force,instance=instance)
            if any(count for code,count in pcm_losses.items() if 'budget' in code and ('omitted' in code or 'dropped' in code)) and not force:
                raise ValueError('PCM content exceeds cartridge DRAM (use --force for explicit omission)')
            rows.extend(pcm);losses.update(pcm_losses)
            lane_prefixes.append(lane_prefix);lane_stats.append(stats)
            if instance:losses['pcm_assets_on_second_unit']+=len(lane_perf.pcm_assets)
        prefix=b''.join(lane_prefixes);pcm_stats={'lanes':lane_stats}
    elif assets:
        pcm,prefix,pcm_losses,pcm_stats=project_pcm(performance,'y8950',force=force)
        if any(count for code,count in pcm_losses.items() if 'budget' in code and ('omitted' in code or 'dropped' in code)) and not force:
            raise ValueError('PCM content exceeds cartridge DRAM (use --force for explicit omission)')
        rows.extend(pcm);losses.update(pcm_losses)
    if not rows and not prefix:raise ValueError('No mapped musical operations in source')
    plan=dict(fm_allocation={str(k):v for k,v in allocation.items()},pcm=pcm_stats)
    plan.update(plan_extra)
    return rows,prefix,dict(losses),plan


def _project_opl3(performance, *, force=False, dcsg_gain=.25,
                  pcm_auxiliary=None):
    """OPL3 profile: the YMF262 is the primary target.

    OPLL voices project through the commercially observed
    conversion table, Y8950 sources re-emit on the OPL3's OPL
    banks and YMF262 sources re-emit natively (4-op pairs
    included).  The chip has no PCM unit, and the 4-op FM
    projection is not established yet; sources needing it make
    the profile unavailable.  NES APU / FDS and HuC6280 waveform
    voices project through the established four-harmonic wave
    projection (the opl3 arm of musical_wave_target), as on the
    OPM / OPNA bases; lanes beyond the channel budget are an
    explicit omission under --force only.
    """
    from musical_opl3_target import project_opl3_fm
    allowed={'opll','y8950','ymf262','psg','dcsg','nesapu','huc6280','segapcm'}
    # The gate counts sounding devices only: a device that never
    # sounds (an msxplay.com export lists every device) must not
    # fail the profile; a sounding unsupported chip still does.
    by_id={d.device_id:d.chip for d in performance.devices}
    present={by_id[u.device_id] for u in performance.units}
    present|={by_id[e.device_id] for e in performance.percussion}
    present|={p.chip for p in performance.pcm_packets}
    bad=sorted(present-allowed)
    if bad:raise ValueError('opl3 profile has no projection for '+', '.join(bad))
    rows=[];losses=Counter();plan={}
    fm_rows,fm_losses,allocation=project_opl3_fm(performance,force=force)
    rows.extend(fm_rows);losses.update(fm_losses)
    wave_chips={'nesapu','huc6280'}&present
    if wave_chips:
        # Waveform sources (NES APU / FDS, HuC6280) project through
        # the four-harmonic wave projection, as on the OPM / OPNA
        # bases.  A waveform lane has no native fallback here, so
        # exceeding the budget is an explicit omission under
        # --force only.
        from musical_wave_target import project_waves
        wave_rows,wave_losses,wave_allocation=project_waves(performance,'opl3',14318180,
            reserved=set(allocation.values()),force=True,
            chips=tuple(sorted(wave_chips)))
        if wave_losses.get('wave_channel_capacity_units_omitted') and not force:
            raise ValueError('Waveform voices exceed OPL3 FM capacity (use --force for explicit omission)')
        rows.extend(wave_rows);losses.update(wave_losses)
        plan['waveform_allocation']={str(k):v for k,v in wave_allocation.items()}
    opll_device=next((d.device_id for d in performance.devices if d.chip=='opll'),None)
    aux,aux_losses=project_psg_opll(performance,dcsg_gain=dcsg_gain,
        opna=False,force=True,opll_fm_device=opll_device)
    rows.extend(aux);losses.update(aux_losses)
    prefix=b'';pcm_stats={}
    assets=getattr(performance,'pcm_assets',())
    if assets:
        if pcm_auxiliary:
            # opl3_makoto / opl3_msxaudio: the paired cartridge gives
            # the PCM content its destination (owner, 2026-11-22).
            from musical_pcm_target import project_pcm
            pcm,prefix,pcm_losses,pcm_stats=project_pcm(performance,pcm_auxiliary,force=force)
            if any(count for code,count in pcm_losses.items() if 'budget' in code and ('omitted' in code or 'dropped' in code)) and not force:
                raise ValueError('PCM content exceeds cartridge DRAM (use --force for explicit omission)')
            rows.extend(pcm);losses.update(pcm_losses)
        else:
            if not force:raise ValueError('OPL3 has no PCM destination (use --force to omit the PCM content)')
            losses['pcm_content_omitted_no_opl3_destination']+=len(assets)
    if not rows:raise ValueError('No mapped musical operations in source')
    plan['fm_allocation']={str(k):v for k,v in allocation.items()}
    if pcm_stats:plan['pcm']=pcm_stats
    return rows,prefix,dict(losses),plan


def project_variant(performance, profile, *, force=False, dcsg_gain=.25, opna_law=False,
                    soundcore_levels=False, volume_offsets=None):
    offsets = _volume_offsets(volume_offsets)
    from musical_pcm_target import project_pcm
    if profile not in PROFILES:raise ValueError('Unknown cartridge profile')
    real_scc=profile in SCC_PROFILES
    profile=SCC_PROFILES.get(profile,profile)
    real_psg=profile in PSG_PROFILES
    profile=PSG_PROFILES.get(profile,profile)
    opl3_pcm_auxiliary=OPL3_PCM_AUXILIARY.get(profile)
    if opl3_pcm_auxiliary:profile='opl3'
    # sfg01_opllrhythm keeps the sfg01 OPM melody projection but leaves
    # OPLL percussion on the native chip (owner, 2026-11-16): no FM
    # rhythm table is selected for it below, so project_rhythm emits
    # the percussion natively instead of skipping it.
    native_opll_rhythm=profile=='sfg01_opllrhythm'
    # sfg01_opl3 keeps the sfg01 OPM melody projection and plays
    # OPLL percussion on the OPL3 cartridge's rhythm unit instead
    # of the FM one-shot table (owner, 2026-11-22).
    opl3_rhythm_unit=profile=='sfg01_opl3'
    if not 0<dcsg_gain<=1:raise ValueError('DCSG gain must be >0 and <=1')
    if profile in ('msxaudio','msxaudio_msxaudio'):
        return _project_msxaudio(performance,force=force,dcsg_gain=dcsg_gain,
            dual_pcm=profile=='msxaudio_msxaudio')
    if profile=='opl3':
        return _project_opl3(performance,force=force,dcsg_gain=dcsg_gain,
            pcm_auxiliary=opl3_pcm_auxiliary)
    chip='opna' if profile in ('makoto','makoto_msxaudio','makoto_msxaudio_msxaudio','misato','misato_msxaudio') else 'opm'
    clock=8000000 if chip=='opna' else 3579545
    # Misato is the Makoto composition on the OPN3 cartridge, which
    # has no ADPCM unit (owner, 2026-11-16): PCM content has no
    # destination there and percussion plays on the native YM2608
    # rhythm unit instead of ADPCM-B samples.
    auxiliary='opna' if profile in ('makoto','makoto_msxaudio','makoto_msxaudio_msxaudio','sfg01_makoto','layered') else 'misato' if profile in ('misato','sfg01_misato','misato_msxaudio') else 'y8950' if profile=='sfg01_msxaudio' else None
    # misato_msxaudio keeps the Misato rhythm/SSG side (auxiliary
    # above) and gives PCM content the MSX-AUDIO Delta-T as its
    # destination; a Makoto pairing is impossible (I/O collision).
    pcm_auxiliary='y8950' if profile=='misato_msxaudio' else auxiliary
    # makoto_msxaudio adds the MSX-AUDIO Delta-T as a second PCM
    # unit beside Makoto's ADPCM-B (owner, 2026-11-23): decoded PCM
    # assets split across the units, each with its own 256 KiB.
    # makoto_msxaudio_msxaudio stacks a second MSX-AUDIO as a third
    # unit (256 KiB x 3); its Y8950 is the VGM dual chip.
    pcm_lanes=(('opna',0),('y8950',0)) if profile=='makoto_msxaudio' else \
        (('opna',0),('y8950',0),('y8950',1)) if profile=='makoto_msxaudio_msxaudio' else None
    # FM-only SFG01 compositions play OPLL rhythm as fitted FM
    # one-shots.  sfg01_opllrhythm selects no table: its rhythm
    # stays native.
    fm_rhythm_table='opll' if profile=='sfg01' else None
    pcm_library='ika'
    losses=Counter();rows=[];prefix=b''
    supported={'opm','opna','opn2','opn','psg','opll','scc','dcsg','huc6280','nesapu','msm6258','segapcm'}
    for device in performance.devices:
        if device.chip not in supported:losses['unsupported_source_device_'+device.chip]+=1
    if any(k.startswith('unsupported_source_device_') for k in losses):
        raise ValueError('No cartridge projection for '+', '.join(sorted(losses)))
    msm_issues=[d for d in performance.decisions if d and d[0] in
        ('msm6258_pcm_source_issue','msm6258_pcm_unresolved_playback')]
    if msm_issues:
        if not force:raise ValueError('MSM6258 PCM source evidence is unresolved; inspect native decisions')
        losses['msm6258_pcm_unavailable_source_assets_omitted']+=len(msm_issues)
    if real_psg:
        # The PSG layered profiles stack FM doublings on the native AY
        # lanes; they are defined for PSG-only sources (owner, 2026-11-14).
        devices={d.device_id:d for d in performance.devices}
        sounding={devices[u.device_id].chip for u in performance.units}
        sounding|={devices[e.device_id].chip for e in performance.percussion}
        sounding|={p.chip for p in performance.pcm_packets}
        if not any(devices[u.device_id].chip=='psg' and u.section!='noise'
                and u.role!='unpitched' for u in performance.units):
            raise ValueError('No sounding PSG units for the PSG layered profile')
        if sounding!={'psg'}:
            raise ValueError('PSG layered profiles require a PSG-only source')
    # Inherent cross-chip waveform/LFO approximations are reported, not fatal.
    # Resource omissions still follow the caller's documented --force policy.
    targets=[(chip,clock)]
    if profile=='layered':targets.append(('opna',8000000))
    fm_layers={}
    fm_performance=performance
    scc_plan=None
    if real_scc:
        from musical_scc_target import project_scc
        scc_rows,scc_losses,scc_plan=project_scc(performance)
        rows.extend(scc_rows);losses.update(scc_losses)
    for target_chip,target_clock in targets:
        fm,fm_losses,layer_plan=_project_fm_layer(fm_performance,target_chip,target_clock,force=force,
            include_psg=real_psg,soundcore_levels=soundcore_levels,
            melody_tl_offset=offsets[target_chip+'_melody'])
        rows.extend(fm);losses.update(fm_losses)
        fm_layers[target_chip]=layer_plan
    opll_fm_device=next((d.device_id for d in performance.devices if d.chip=='opll' and
        any(u.device_id==d.device_id and u.section=='fm' for u in performance.units)),None)
    # Layered stacks every FM source (owner, 2026-11-14): when the
    # source has an OPLL device, its native lane joins the OPM and
    # OPNA FM projections instead of being consumed by them, and
    # its rhythm plays natively rather than via the PCM substitute.
    opll_ids={d.device_id for d in performance.devices if d.chip=='opll'}
    layered_opll=profile=='layered' and bool(opll_ids)
    opll_percussion=any(e.device_id in opll_ids for e in performance.percussion)
    aux,aux_losses=project_psg_opll(performance,dcsg_gain=dcsg_gain,
        opna=auxiliary in ('opna','misato'),force=True,
        opll_fm_device=None if layered_opll else opll_fm_device)
    if any(aux_losses.get(k) for k in ('psg_channel_capacity_units_omitted','second_opll_device_omitted')) and not force:
        raise ValueError('Auxiliary voices exceed cartridge capacity (use --force for explicit omission)')
    rows.extend(aux);losses.update(aux_losses)
    assets=getattr(performance,'pcm_assets',())
    pcm_stats={}
    rhythm_pcm=False
    pcm_performance=performance
    if not assets and auxiliary in ('opna','y8950') and not (layered_opll and opll_percussion):
        from opll_rhythm_pcm import build_rhythm_pcm_assets
        derived,rhythm_pcm_losses=build_rhythm_pcm_assets(performance,library=pcm_library,
            soundcore_levels=soundcore_levels,
            rhythm_tl_offset=offsets['opna_rhythm'])
        if derived:
            from dataclasses import replace
            pcm_performance=replace(performance,pcm_assets=derived)
            assets=derived;rhythm_pcm=True
            losses.update(rhythm_pcm_losses)
    missing_pcm=[decision for decision in performance.decisions if decision and decision[0] in ('nes_pcm_missing_sample_bytes','opn2_pcm_source_issue','opn2_pcm_direct_without_observed_enable')]
    if missing_pcm:losses['source_pcm_content_incomplete_diagnostics']+=len(missing_pcm)
    if assets and pcm_auxiliary=='misato':
        if not force:raise ValueError('Misato has no ADPCM unit (use --force to omit the PCM content)')
        losses['pcm_content_omitted_no_misato_destination']+=len(assets)
    elif assets:
        if pcm_auxiliary is None:raise ValueError('PCM source requires sfg01_makoto or sfg01_msxaudio')
        if pcm_lanes and not rhythm_pcm:
            lane_stats=[];lane_prefixes=[]
            for lane_index,((lane_target,lane_instance),lane_perf) in enumerate(zip(pcm_lanes,_split_pcm_assets(pcm_performance,len(pcm_lanes)))):
                if lane_perf is None:lane_stats.append(None);continue
                pcm,lane_prefix,pcm_losses,stats=project_pcm(lane_perf,lane_target,force=force,instance=lane_instance)
                if any(count for code,count in pcm_losses.items() if 'budget' in code and ('omitted' in code or 'dropped' in code)) and not force:
                    raise ValueError('PCM content exceeds cartridge DRAM (use --force for explicit omission)')
                rows.extend(pcm);losses.update(pcm_losses)
                lane_prefixes.append(lane_prefix);lane_stats.append(stats)
                if lane_index==1:losses['pcm_assets_on_second_unit']+=len(lane_perf.pcm_assets)
                elif lane_index==2:losses['pcm_assets_on_third_unit']+=len(lane_perf.pcm_assets)
            prefix=b''.join(lane_prefixes);pcm_stats={'lanes':lane_stats}
        else:
            pcm,prefix,pcm_losses,pcm_stats=project_pcm(pcm_performance,pcm_auxiliary,force=force)
            if any(count for code,count in pcm_losses.items() if 'budget' in code and ('omitted' in code or 'dropped' in code)) and not force:
                raise ValueError('PCM content exceeds cartridge DRAM (use --force for explicit omission)')
            rows.extend(pcm);losses.update(pcm_losses)
    native_pcm=[p for p in performance.pcm_packets if p.chip=='opna']
    if native_pcm:
        from opn2_target_vgm import ADPCM_B_DRAM_BUDGET
        blocks=[bytes.fromhex(p.command_hex) for p in native_pcm if bytes.fromhex(p.command_hex)[0]==0x67]
        exceeds=any(len(b)<15 or int.from_bytes(b[7:11],'little')>ADPCM_B_DRAM_BUDGET or int.from_bytes(b[11:15],'little')+len(b)-15>ADPCM_B_DRAM_BUDGET for b in blocks)
        if exceeds:
            if not force:raise ValueError('Native OPNA ADPCM exceeds the Makoto 256 KiB RAM budget; relocation required')
            losses['native_opna_adpcm_capacity_lane_omitted']+=1
            native_pcm=[]
    if native_pcm and auxiliary=='misato':
        if not force:raise ValueError('Misato has no ADPCM unit (use --force to omit native OPNA ADPCM content)')
        losses['native_opna_adpcm_omitted_no_misato_destination']+=1
        native_pcm=[]
    if native_pcm:
        if assets:raise ValueError('Native OPNA ADPCM and decoded PCM compete for one Delta-T unit')
        if auxiliary!='opna':raise ValueError('Native OPNA ADPCM requires Makoto auxiliary cartridge')
        for p in native_pcm:
            command=bytes.fromhex(p.command_hex)
            if command[0]==0x67:
                if p.sample!=0:raise ValueError('Mid-song native ADPCM memory uploads require an explicit relocation plan')
                prefix+=command
            elif command[0] in (0x56,0x57):
                rows.append(dict(sample=p.sample,order=p.order,command=command,
                    unit_id='',device_id='opna:0',source_indices=(p.source_event_id,),reason='native ADPCM preservation'))
            else:raise ValueError('Native ADPCM stream transport needs decoded content before relocation')
        losses['native_opna_adpcm_clock_not_repitched']+=1
        pcm_stats.update(ram_budget_bytes=ADPCM_B_DRAM_BUDGET,ram_used_bytes=max((int.from_bytes(b[11:15],'little')+len(b)-15 for b in blocks),default=0),encoder_path='native_opna_packet_preservation')
    rhythm_info={}
    if fm_rhythm_table:
        from opll_rhythm_fm import project_opll_rhythm_fm
        reserved=set()
        for layer_plan in fm_layers.values():
            for key in ('fm_allocation','opll_allocation','waveform_allocation'):
                reserved.update(int(v) for v in layer_plan[key].values())
        fm_rhythm,fm_rhythm_losses,rhythm_info=project_opll_rhythm_fm(
            performance,fm_rhythm_table,reserved,force=force,
            soundcore_levels=soundcore_levels,
            tl_offset=offsets['opm_rhythm'])
        rows.extend(fm_rhythm);losses.update(fm_rhythm_losses)
    if opl3_rhythm_unit:
        from musical_opl3_target import project_opl3_rhythm
        opl3_rows,opl3_losses=project_opl3_rhythm(performance)
        rows.extend(opl3_rows);losses.update(opl3_losses)
    from musical_rhythm_target import project_rhythm
    rhythm,rhythm_losses=project_rhythm(performance,makoto=auxiliary in ('opna','misato'),
        opll_pcm=rhythm_pcm,opll_fm=bool(fm_rhythm_table),
        opna_rhythm=auxiliary=='misato',opl3_rhythm=opl3_rhythm_unit,
        soundcore_levels=soundcore_levels,
        opna_rhythm_tl_offset=offsets['opna_rhythm'])
    rows.extend(rhythm);losses.update(rhythm_losses)
    # The measured OPNA TL/decay law is applied to projected carrier values,
    # after native curve/voice recombination, never to source evidence.
    if opna_law and any(target=='opna' for target,_ in targets):
        from opn2_target_vgm import _OPNA_LAW_TL, _OPNA_LAW_DECAY
        device_chips={d.device_id:d.chip for d in performance.devices}
        carriers=(8,8,8,8,12,14,14,15);algorithms={};ks={}
        for row in sorted(rows,key=lambda r:(r['sample'],r.get('order',0))):
            if device_chips.get(row['device_id'])!='opn2':continue
            cmd,reg,value=row['command'];port=cmd-0x56
            if cmd not in (0x56,0x57):continue
            ch=reg%4+3*port;bank=(reg%16)//4
            if 0xb0<=reg<=0xb2:algorithms[ch]=value&7
            elif 0x50<=reg<=0x5f:ks[ch,bank]=value>>6
            elif 0x40<=reg<=0x4f and carriers[algorithms.get(ch,0)]&(1<<bank):value=_OPNA_LAW_TL[value&127]
            elif 0x60<=reg<=0x7f and ks.get((ch,bank),0)==0:value=(value&0xe0)|_OPNA_LAW_DECAY[value&31]
            row['command']=bytes((cmd,reg,value))
    if any(row['command'][0] in (0x56,0x57) for row in rows):
        rows.insert(0,dict(sample=0,order=-2,command=bytes((0x56,0x29,0x80)),unit_id='',device_id='',source_indices=(),reason='enable six OPNA FM channels'))
    if not rows and not prefix:raise ValueError('No mapped musical operations in source')
    plan=dict(fm_allocation=fm_layers[chip]['fm_allocation'],
        waveform_allocation=fm_layers[chip]['waveform_allocation'],pcm=pcm_stats)
    if rhythm_info:plan['opll_rhythm_fm']=rhythm_info
    if rhythm_pcm:plan['opll_rhythm_pcm']=pcm_library
    if layered_opll:plan['native_opll_layer']=True
    if native_opll_rhythm:plan['native_opll_rhythm']=True
    if opl3_rhythm_unit:plan['opl3_rhythm_unit']=True
    if auxiliary=='misato':plan['misato_no_adpcm']=True
    if profile=='layered':plan['fm_layers']=fm_layers
    if real_scc:plan['real_scc']=scc_plan
    if real_psg:plan['psg_fm_doubling']=True
    return rows,prefix,dict(losses),plan


def export_variants(performance, outdir, stem, *, force=False, dcsg_gain=.25, opna_law=False,
                    soundcore_levels=False, volume_offsets=None):
    root=Path(outdir);root.mkdir(parents=True,exist_ok=True);results={}
    for profile in PROFILES:
        folder=root/variant_folder(profile);folder.mkdir(parents=True,exist_ok=True)
        path=folder/(stem+'.vgm');path.unlink(missing_ok=True)
        result=dict(profile=profile,stage='musical_layer_target_projection',
            input_representation='NativePerformance',source_file_consulted=False,
            sample_rate=44100,status='unavailable',source_decisions=performance.decisions)
        try:
            # The auxiliary SFG01 compositions are "OPM, or OPM + PCM
            # when the source carries PCM" (owner, 2026-11-15): they
            # are published whenever sfg01 is, even when no PCM lane
            # is needed and the result matches sfg01, so the profile
            # set a user finds does not depend on the song's content.
            rows,prefix,losses,plan=project_variant(performance,profile,force=force,
                dcsg_gain=dcsg_gain,opna_law=opna_law,
                soundcore_levels=soundcore_levels,
                volume_offsets=volume_offsets)
            rows=_write(performance,rows,prefix,path)
            with (folder/(stem+'.writes.csv')).open('w',newline='',encoding='utf-8') as stream:
                fields=['write_id','sample','order','device_id','unit_id','source_indices','reason','command_hex','target_address','emitted']
                writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
                for row in rows:
                    writer.writerow({k:(row['command'].hex() if k=='command_hex' else
                        json.dumps(row.get(k)) if k=='source_indices' else row.get(k,'')) for k in fields})
            result.update(status='success',path=str(path),writes=sum(r['emitted'] for r in rows),planned_writes=len(rows),losses=losses,plan=plan,
                song_loop_sample=performance.song_loop_sample)
            parent=PROFILE_PARENTS.get(profile)
            while parent:
                parent_path=root/variant_folder(parent)/(stem+'.vgm')
                if parent_path.is_file():
                    if parent_path.read_bytes()==path.read_bytes():
                        # The composition changed nothing for this song:
                        # the base folder already carries the same bytes.
                        path.unlink()
                        (folder/(stem+'.writes.csv')).unlink(missing_ok=True)
                        result.update(status='identical_to_parent',
                            reason=f'Identical to the {parent} output; omitted')
                    break
                # The parent itself was omitted as identical; compare
                # against the nearest published ancestor instead.
                parent=PROFILE_PARENTS.get(parent)
        except ValueError as error:
            result.update(reason=str(error))
        except Exception as error:
            result.update(status='failed',reason=f'{type(error).__name__}: {error}')
        (folder/(stem+'.projection.json')).write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        results[profile]=result
    return results
