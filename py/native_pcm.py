"""Source PCM extraction only: no cartridge allocation, encoding or target clocks."""
from collections import defaultdict
import math

from native_music import NativePCM


def _held_samples(start, stop, changes, initial):
    """Materialize observed DAC holds on the original 44100 Hz time grid."""
    result = []
    cursor, value = start, initial
    for at, level in changes:
        at = max(start, min(stop, at))
        result.extend([value] * (at - cursor))
        cursor, value = at, level
    result.extend([value] * (stop - cursor))
    return tuple(result)


def add_opn2_pcm(builder):
    # This existing helper decodes source commands only. No project_dac,
    # resampler, cartridge encoder or target budget participates here.
    from opn2_target_vgm import _decode_dac_stream
    raw, events = builder.raw, builder.bundle['events']
    end = builder.bundle['source_end_sample']
    supplies, issues, _ = _decode_dac_stream(raw, events)
    for issue, count in sorted(issues.items()):
        builder.decisions.append(('opn2_pcm_source_issue', issue, count))
    changes = defaultdict(list)
    second_stream_starts = set()
    stream_instances = {}
    valid_streams = set()
    manual_instances = {}
    quick_instance = None
    for index, event in enumerate(events):
        cmd, pos = event.command, event.address
        if cmd == 0x90:
            stream_instances[raw[pos + 1]] = raw[pos + 2] >> 7
            if raw[pos+2]&127 == 2 and raw[pos+4] == 0x2a:
                valid_streams.add(raw[pos+1])
            else:
                valid_streams.discard(raw[pos+1])
        elif cmd in (0x93, 0x95) and stream_instances.get(raw[pos + 1]):
            second_stream_starts.add(index)
        if cmd == 0x95:
            quick_instance = stream_instances.get(raw[pos+1],0)
        if cmd == 0xe0 or 0x80 <= cmd <= 0x8f:
            if quick_instance is None:
                quick_instance = stream_instances[next(iter(valid_streams))] if len(valid_streams)==1 else 0
            manual_instances[index] = quick_instance
        if cmd not in (0x52, 0xa2):
            continue
        reg, value = raw[pos + 1:pos + 3]
        if reg in (0x2a, 0x2b):
            instance = int(cmd == 0xa2)
            changes[instance].append((event.vgmticks, index, reg, value,
                                      event.source_event_id, False, None, None))
    for at, value, source_index, offset, step in supplies:
        if at >= end:
            continue
        instance = manual_instances.get(source_index,int(source_index in second_stream_starts))
        event = events[source_index]
        changes[instance].append((at, source_index, 0x2a, value, event.source_event_id, True, offset, step))
    for instance, rows in sorted(changes.items()):
        device = builder.device('opn2', instance)
        enabled, held, onset, initial = None, None, None, None
        inferred_enable = False
        unknown_direct = 0
        levels, sources, timeline = [], [], []
        number = 0
        def finish(stop):
            nonlocal onset, number, levels, sources, timeline
            if onset is not None and stop > onset:
                builder.pcm_assets.append(NativePCM(
                    f'{device.device_id}:dac:{number}', device.device_id,
                    onset, stop, 44100, _held_samples(onset, stop, levels, initial),
                    tuple(dict.fromkeys(sources)),
                    (('source_encoding', 'unsigned8_dac'),
                     ('reconstruction', 'original_sample_grid_zero_order_hold'),
                     ('dac_enable_gated', not inferred_enable),
                     ('enable_basis', 'stream_playback_intent' if inferred_enable
                         else 'observed_dac_enable'),
                     ('dac_timeline',tuple(point for point in timeline if onset<=point[0]<stop)))))
                number += 1
            onset = None
            levels, sources, timeline = [], [], []
        for at, order, reg, value, identity, is_stream, offset, step in sorted(rows, key=lambda r: r[:2]):
            if at > end:
                continue
            if reg == 0x2b:
                new_enabled = bool(value & 128)
                if enabled and not new_enabled:
                    sources.append(identity)
                    finish(at)
                    inferred_enable = False
                elif new_enabled and not enabled and held is not None:
                    onset, initial = at, (held - 128) * 256
                    sources.append(identity)
                    timeline.append((at,identity,None,None))
                if new_enabled and not enabled and held is None:
                    sources.append(identity)
                enabled = new_enabled
            else:
                held = value
                if enabled is None and is_stream:
                    enabled, inferred_enable = True, True
                    builder.decisions.append(('opn2_pcm_stream_intent_without_observed_enable',
                                              device.device_id))
                elif enabled is None:
                    unknown_direct += 1
                if enabled:
                    if onset is None:
                        onset, initial = at, (value - 128) * 256
                    levels.append((at, (value - 128) * 256))
                    timeline.append((at,identity,offset,step))
                    sources.append(identity)
        finish(end)
        if unknown_direct:
            builder.decisions.append(('opn2_pcm_direct_enable_unknown',device.device_id,unknown_direct))


def add_nes_pcm(builder, trace, device):
    from nesapu import DMC_RATE_PERIODS, _sample_memory
    if not trace.dpcm_events or not trace.clock_hz:
        return
    memory, covered = _sample_memory(builder.raw)
    disables = [w for w in trace.writes if w.register == 21 and not w.value & 16]
    for index, event in enumerate(trace.dpcm_events):
        rate = trace.clock_hz / DMC_RATE_PERIODS[event.rate_index]
        count = event.length_bytes * 8
        start = event.vgmticks
        end = builder.bundle['source_end_sample']
        if index + 1 < len(trace.dpcm_events):
            end = min(end, trace.dpcm_events[index + 1].vgmticks)
        end = min([end] + [w.vgmticks for w in disables if w.vgmticks > start])
        if not event.loop:
            end = min(end, start + round(count * 44100 / rate))
        addresses = [0x8000 + ((event.address + i - 0x8000) & 0x7fff)
                     for i in range(event.length_bytes)]
        if any(at not in covered for at in addresses):
            builder.decisions.append(('nes_pcm_missing_sample_bytes', index,
                sum(at not in covered for at in addresses)))
            continue
        if end <= start:
            continue
        data = bytes(memory[at] for at in addresses)
        bits = min(count, math.ceil((end-start)*rate/44100)) if not event.loop else math.ceil((end-start)*rate/44100)
        level, samples = event.level, []
        for bit in range(bits):
            value = data[(bit // 8) % len(data)] >> (bit & 7) & 1
            if value and level <= 125:
                level += 2
            elif not value and level >= 2:
                level -= 2
            samples.append((level - 64) * 512)
        source_ids = tuple(w.source_event_id for w in trace.writes
            if start <= w.vgmticks <= end and w.register in (16,17,18,19,21))
        builder.pcm_assets.append(NativePCM(
            f'{device.device_id}:dpcm:{index}', device.device_id, start, end,
            rate, tuple(samples), source_ids,
            (('source_encoding','nes_dpcm_lsb_first'),('initial_level',event.level),
             ('loop',event.loop),('address',event.address),
             ('length_bytes',event.length_bytes),('analog_filter_applied',False))))
        if any(start < w.vgmticks < end and w.register in (16,17) for w in trace.writes):
            builder.decisions.append(('nes_pcm_midplay_rate_or_level_unmodeled', index))
    # Existing trace memory assembly uses the complete source memory image.
    # Make that assumption explicit instead of presenting it as timed DMA.
    builder.decisions.append(('nes_pcm_memory_basis','source_data_block_memory_image'))


def add_huc_pcm(builder, trace, device, channel, active, number):
    from huc6280 import attenuation_levels, VOLUME_TABLE
    first, last = active[0][1], active[-1][1]
    start, end = first.start_vgmticks, last.end_vgmticks
    changes, evidence = [], []
    for _, segment in active:
        state = segment.state
        left, right = attenuation_levels(state.control, state.balance, segment.global_balance)
        gain = (VOLUME_TABLE[left] + VOLUME_TABLE[right]) / (2 * VOLUME_TABLE[0])
        changes.append((segment.start_vgmticks, round((state.dda - 16) * 2048 * gain)))
        evidence.append((segment.start_vgmticks, state.dda, left, right))
    if end <= start:
        return
    ids = tuple(event.write.source_event_id for event in trace.states
        if start <= event.write.vgmticks <= end and
        event.selected_channel == channel)
    builder.pcm_assets.append(NativePCM(
        f'{device.device_id}:dda:{channel}:{number}', device.device_id, start, end,
        44100, _held_samples(start,end,changes,changes[0][1]),ids,
        (('source_encoding','unsigned5_dda'),('channel',channel),
         ('source_level_and_stereo_attenuation_curve',tuple(evidence)),
         ('stereo_fold_down','mean_left_right_amplitude'),
         ('reconstruction','original_sample_grid_zero_order_hold'))))
