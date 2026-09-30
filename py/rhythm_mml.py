"""Project exact rhythm groups to MGSDRV track f without retiming Segments."""
from rhythm_patterns import group_segments, find_patterns
from dataclasses import replace
import warnings

LETTERS = {'BD': 'b', 'SD': 's', 'TOM': 'm', 'CYM': 'c', 'HH': 'h'}


def _target_groups(groups):
    """Collapse only identical same-time retriggers with no intervening duration.

    Source groups/Segments remain lossless. Distinct sub-tick events still fail
    explicitly rather than being silently lost or shifted to another tick.
    """
    result = []
    for group in groups:
        hits, positions = [], {}
        for hit in group.hits:
            if hit.instrument in positions:
                index = positions[hit.instrument]
                previous = hits[index]
                if (previous.interval == 0 and previous.source_time == hit.source_time
                        and previous.state == hit.state):
                    warnings.warn(f'Collapsed zero-duration same-time {hit.instrument} retrigger '
                                  f'at tick {group.tick} for MGSDRV; source CSV retains both events',
                                  RuntimeWarning)
                    hits[index] = hit
                    continue
                raise ValueError(f'Cannot represent multiple {hit.instrument} triggers at tick {group.tick} in MGSDRV rhythm MML')
            positions[hit.instrument] = len(hits)
            hits.append(hit)
        result.append(replace(group, hits=tuple(hits)))
    return tuple(result)


def _timed(token, steps, raw):
    """Long inter-onset gaps continue as rests, never as repeated attacks."""
    result = []
    while steps > 0:
        length = min(steps, 255)
        suffix = str(192 // length) if not raw and 192 % length == 0 else f'%{length}'
        result.append(token + suffix)
        token = 'r'
        steps -= length
    return result


def render(segments, raw_ticks=False, end_tick=None):
    groups = _target_groups(group_segments(segments))
    if not groups:
        return ''
    factor = 1 if raw_ticks else 3
    end = max((s.tick_end for rows in segments.values() for s in rows), default=0)
    if end_tick is not None:
        end = max(end, end_tick)
    patterns, occurrences = find_patterns(groups)
    tokens = _timed('r', groups[0].tick * factor, raw_ticks)
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
            body.extend(_timed(''.join(notes), gap * factor, raw_ticks))
        # Every unit sets its required volumes independently of incoming state.
        remaining = occurrence.repeats
        while remaining:
            repeats = min(remaining, 255)
            tokens.append('[' + ' '.join(body) + f']{repeats}' if repeats > 1 else ' '.join(body))
            remaining -= repeats
    return '\nf ' + ' '.join(tokens) + '\n'
