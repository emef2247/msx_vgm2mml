"""Project exact rhythm groups to MGSDRV track f without retiming Segments."""
from rhythm_patterns import group_segments, find_patterns
from dataclasses import replace
import warnings
import csv
import json

LETTERS = {'BD': 'b', 'SD': 's', 'TOM': 'm', 'CYM': 'c', 'HH': 'h'}


def _target_groups(groups, collision_path=None):
    """Keep the last same-instrument attack in a quantized target tick.

    Source groups retain every edge. MGSDRV cannot encode a positive interval
    between these attacks; do not invent one or change later onset times.
    """
    result, collisions = [], []
    for group in groups:
        hits, positions = [], {}
        for hit in group.hits:
            if hit.instrument in positions:
                index = positions[hit.instrument]
                previous = hits[index]
                if previous.interval != 0 or hit.source_time < previous.source_time:
                    raise ValueError(f'Cannot represent multiple {hit.instrument} triggers at tick {group.tick} in MGSDRV rhythm MML')
                same_time = previous.source_time == hit.source_time
                adjacent_sample = hit.source_time - previous.source_time <= 1 / 44100 + 1e-12
                reason = ('same-time' if same_time else 'one-sample' if adjacent_sample
                          else 'quantized-tick')
                collisions.append((group.tick, hit.instrument, reason,
                                   previous.segment_index, hit.segment_index,
                                   previous.source_time, hit.source_time,
                                   json.dumps(previous.state), json.dumps(hit.state)))
                hits[index] = hit
                continue
            positions[hit.instrument] = len(hits)
            hits.append(hit)
        result.append(replace(group, hits=tuple(hits)))
    if collision_path is not None:
        with open(collision_path, 'w', encoding='utf-8', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(('tick', 'instrument', 'reason', 'dropped_segment_index',
                             'kept_segment_index', 'dropped_source_time',
                             'kept_source_time', 'dropped_state', 'kept_state'))
            writer.writerows(collisions)
    if collisions:
        reasons = ', '.join(sorted({row[2] for row in collisions}))
        warnings.warn(f'Collapsed {len(collisions)} zero-duration {reasons} rhythm retrigger(s) '
                      'for MGSDRV; last attack per instrument/tick wins; '
                      'source CSV retains all events', RuntimeWarning)
    return tuple(result)


def _timed(token, steps, raw, minimum_steps=1):
    """Long inter-onset gaps continue as rests, never as repeated attacks."""
    result = []
    while steps > 0:
        length = min(steps, 255)
        if length < minimum_steps:
            raise ValueError('Rhythm interval is below the target minimum length')
        if 0 < steps - length < minimum_steps:
            length -= minimum_steps - (steps - length)
        suffix = (str(192 // length) if not raw and 192 % length == 0
                  and 192 // length in (1, 2, 4, 8, 16, 32, 64) else f'%{length}')
        result.append(token + suffix)
        token = 'r'
        steps -= length
    return result


def render(segments, raw_ticks=False, end_tick=None, collision_path=None, minimum_steps=1):
    groups = _target_groups(group_segments(segments), collision_path)
    if not groups:
        return ''
    factor = 1 if raw_ticks else 3
    end = max((s.tick_end for rows in segments.values() for s in rows), default=0)
    if end_tick is not None:
        end = max(end, end_tick)
    patterns, occurrences = find_patterns(groups)
    tokens = _timed('r', groups[0].tick * factor, raw_ticks, minimum_steps)
    for occurrence in occurrences:
        count = len(patterns[occurrence.pattern_id])
        unit = groups[occurrence.group_start:occurrence.group_start + count]
        body, volumes = [], {}
        for group in unit:
            seen, notes = set(), []
            for hit in group.hits:
                letter = LETTERS[hit.instrument]
                if letter in seen:
                    raise ValueError(f'Cannot represent multiple {hit.instrument} triggers at tick {group.tick} in MGSDRV rhythm MML')
                seen.add(letter)
                volume = 15 - hit.state[0]
                if volumes.get(letter) != volume:
                    body.append(f'v{letter}{volume}')
                    volumes[letter] = volume
                notes.append(letter)
            # The final attack needs a positive encoded length. Use the known
            # analysis end, with one source tick minimum; this is not decay.
            gap = group.gap if group.gap is not None else max(1, end - group.tick)
            body.extend(_timed(''.join(notes), gap * factor, raw_ticks, minimum_steps))
        # Every unit sets its required volumes independently of incoming state.
        remaining = occurrence.repeats
        while remaining:
            repeats = min(remaining, 255)
            tokens.append('[' + ' '.join(body) + f']{repeats}' if repeats > 1 else ' '.join(body))
            remaining -= repeats
    return '\nf ' + ' '.join(tokens) + '\n'
