"""NES APU native sounding units; target routing stays in later stages."""
import json

from nesapu import NOISE_PERIODS, analyze
from native_music import NativeUnit

SECTIONS = ('pulse', 'pulse', 'triangle', 'noise', 'fds')


def _pitch_hz(trace, view):
    if view.kind == 'noise':
        cycles = NOISE_PERIODS[view.noise_period_index]
        return trace.clock_hz / cycles if trace.clock_hz else None
    if view.kind == 'fds':
        return (trace.clock_hz * view.period * view.mod_ratio / 2**22
                if trace.clock_hz else None)
    divisor = 16 if view.kind == 'pulse' else 32
    return trace.clock_hz / (divisor * (view.period + 1)) if trace.clock_hz else None


def add_units(builder, root, stem):
    trace = analyze(builder.raw)
    trace.dump(root, stem)
    device = builder.device('nesapu')
    retriggers = {}
    for channel, at, _ in trace.retriggers:
        retriggers.setdefault(channel, []).append(at)
    rows = {}
    for index, segment in enumerate(trace.segments):
        rows.setdefault(segment.channel, []).append((index, segment))
    for channel, segments in sorted(rows.items()):
        section = SECTIONS[channel]
        active = []
        number = 0

        def finish():
            nonlocal number
            if not active:
                return
            first, last = active[0][1], active[-1][1]
            pitch, volume, voices = [], [], []

            def append(curve, at, value):
                if not curve or curve[-1][1] != value:
                    curve.append((at, value))

            for _, segment in active:
                view = segment.state
                at = segment.start_vgmticks
                append(pitch, at, _pitch_hz(trace, view))
                append(volume, at, view.volume)
                parameters = (('duty', view.duty),) if view.kind == 'pulse' else \
                    (('lfsr_mode', view.lfsr_mode),) if view.kind == 'noise' else \
                    (('wave_id', view.wave_id),) if view.kind == 'fds' else \
                    (('waveform', 'triangle'),)
                append(voices, at, builder.voice(device, section, parameters))
            builder.units.append(NativeUnit(
                f'nesapu:0:{channel}:gate:{number}', device.device_id,
                section, channel, first.start_vgmticks, last.end_vgmticks,
                tuple(pitch), tuple(volume), tuple(voices),
                builder.control_ids(device, section, channel,
                                    first.start_vgmticks, last.end_vgmticks),
                tuple(i for i, _ in active),
                'unpitched' if section == 'noise' else 'melody',
                (('boundary_origin', 'source_audibility_or_counter_transition'),
                 ('volume_domain', 'native_apu_level_0_15' if section != 'triangle'
                  else 'triangle_fixed_level_no_volume_register'),
                 ('dpcm_events_retained_in_trace', bool(trace.dpcm_events)),
                 ('fds_waves_retained_in_trace', bool(trace.fds_waves)))))
            number += 1
            active.clear()

        for index, segment in segments:
            if not segment.active:
                finish()
                continue
            retrigger = bool(active and any(
                active[-1][1].start_vgmticks < at <= segment.start_vgmticks
                for at in retriggers.get(channel, ())))
            if active and (active[-1][1].end_vgmticks != segment.start_vgmticks
                           or retrigger):
                finish()
            active.append((index, segment))
        finish()
    runs = {}
    for slice_ in trace.dpcm_slices:
        runs.setdefault(slice_.event_index, []).append(slice_)
    for number, (event_index, run) in enumerate(sorted(runs.items())):
        volume = []

        def append_volume(at, value):
            if not volume or volume[-1][1] != value:
                volume.append((at, value))

        for slice_ in run:
            append_volume(slice_.start_vgmticks, slice_.volume)
        builder.units.append(NativeUnit(
            f'nesapu:0:4:gate:{number}', device.device_id,
            'dpcm', 4, run[0].start_vgmticks, run[-1].end_vgmticks,
            ((run[0].start_vgmticks, None),), tuple(volume),
            (builder.voice(device, 'dpcm', (('rendering', 'scc_slice'),)),),
            builder.control_ids(device, 'dpcm', 4,
                                run[0].start_vgmticks, run[-1].end_vgmticks),
            (), 'unpitched',
            (('boundary_origin', 'dpcm_trigger_playback_interval'),
             ('volume_domain', 'native_apu_level_0_15'),
             ('source_event_index', str(event_index)))))
    report = builder.bundle['report']
    report['active_chips'] = tuple(dict.fromkeys(
        (*report['active_chips'], 'nesapu')))
    report['analysis_available']['nesapu'] = True
    report['command_counts']['nesapu'] = len(trace.writes)
    report['interpretation_issues']['nesapu'] = list(trace.issues)
    builder.decisions.extend(('nesapu_source_issue', issue)
                             for issue in trace.issues)
    (root / f'{stem}.native.source.json').write_text(
        json.dumps(report, indent=2) + '\n', encoding='utf-8')
