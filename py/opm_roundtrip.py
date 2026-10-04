"""Explicit native OPM control/state comparison for the MDX target."""
from collections import Counter
from dataclasses import asdict


def controls(analysis):
    result = {}
    for event in analysis.events:
        result.setdefault(event.source_event_id, (event.vgmticks, event.register, event.data))
    return list(result.values())


def _known_differences(reference, actual, prefix=''):
    if reference is None:
        return []
    if isinstance(reference, dict):
        return [p for key, value in reference.items()
                for p in _known_differences(value, actual[key], prefix + key + '.')]
    if isinstance(reference, (tuple, list)):
        return [prefix] if reference != actual else []
    return [prefix.rstrip('.')] if reference != actual else []


def compare(projection, source_segments, actual, *, initialization):
    """Verify all target controls and known source states, not an audio score.

    Only an independently generated, exactly matching zero-time compiler
    initializer is removed. The source controls never have a prefix stripped.
    Unknown source registers/parameters do not become invented expectations.
    """
    source_segments = tuple(source_segments)
    raw_actual = controls(actual)
    prefix_ok = raw_actual[:len(initialization)] == list(initialization)
    replayed = raw_actual[len(initialization):] if prefix_ok else raw_actual
    expected = [(w.register, w.data) for w in projection.writes]
    observed = [(reg, data) for _, reg, data in replayed]
    sequence_ok = expected == observed
    projected_errors = [sample - w.projected_vgmticks
                        for w, (sample, _, _) in zip(projection.writes, replayed)]
    source_errors = [sample - w.source_vgmticks
                    for w, (sample, _, _) in zip(projection.writes, replayed)]
    source_errors.append(actual.source_end_vgmticks - projection.source_end_vgmticks)
    projected_errors.append(actual.source_end_vgmticks - projection.end_projected_vgmticks)

    def count(items, field, operators):
        result = Counter()
        for item in items:
            mask = getattr(item, field)
            result[item.ch] += mask.bit_count() if operators else bool(mask)
        return result

    result = dict(initialization_prefix_matches=prefix_ok, control_sequence_matches=sequence_ok,
                  source_controls=len(expected), returned_controls=len(observed),
                  source_end_vgmticks=projection.source_end_vgmticks,
                  returned_end_vgmticks=actual.source_end_vgmticks,
                  max_abs_source_timing_error_samples=max(map(abs, source_errors), default=0),
                  max_abs_projected_timing_error_samples=max(map(abs, projected_errors), default=0))
    for label, field, operators in [('channel_attacks', 'rising_mask', False),
                                    ('operator_keyons', 'rising_mask', True),
                                    ('operator_keyoffs', 'falling_mask', True)]:
        ref = count(source_segments, field, operators)
        act = count(actual.segments, field, operators)
        channels = ref.keys() | act.keys()
        result.update({f'source_{label}': sum(ref.values()), f'returned_{label}': sum(act.values()),
                       f'missing_{label}': sum(max(0, ref[ch] - act[ch]) for ch in channels),
                       f'extra_{label}': sum(max(0, act[ch] - ref[ch]) for ch in channels)})

    state_mismatches = []
    if prefix_ok and sequence_ok:
        actual_groups = {}
        for event in actual.events:
            actual_groups.setdefault(event.source_event_id, {})[event.ch] = event.state
        replay_ids = list(actual_groups)[len(initialization):]
        source_groups = {}
        for segment in source_segments:
            if segment.source_event_id is not None:
                source_groups.setdefault(segment.source_event_id, []).append(segment)
        for write, actual_id in zip(projection.writes, replay_ids):
            for segment in source_groups[write.source_event_id]:
                ref, act = asdict(segment.state), asdict(actual_groups[actual_id][segment.ch])
                # Additional initialized registers on the returned side are not
                # evidence about registers unwritten by the input VGM.
                for field in ('channel_registers', 'shared_registers'):
                    known = dict(ref[field]); observed_regs = dict(act[field])
                    for reg, value in known.items():
                        if observed_regs.get(reg) != value:
                            state_mismatches.append(f'event {write.source_event_id}, ch{segment.ch}, register {reg}')
                    ref.pop(field); act.pop(field)
                for path in _known_differences(ref, act):
                    state_mismatches.append(f'event {write.source_event_id}, ch{segment.ch}, {path}')
    result['known_state_mismatches'] = len(state_mismatches)
    result['first_state_mismatches'] = state_mismatches[:10]
    result['passed'] = (prefix_ok and sequence_ok and not state_mismatches
                        and result['max_abs_source_timing_error_samples'] <= 6
                        and result['max_abs_projected_timing_error_samples'] == 0
                        and all(result[f'{kind}_{label}'] == 0 for kind in ('missing', 'extra')
                                for label in ('channel_attacks', 'operator_keyons', 'operator_keyoffs')))
    return result
