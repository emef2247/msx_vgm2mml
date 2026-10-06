"""Ordinary MDX notation for an already-inspectable additive target plan.

This is target-to-target spelling, not reconstruction of native OPM Segments.
"""
from collections import defaultdict
from opm_mdx import projected_samples
from opm_mdx_structure import KC_CODES

NAMES = ('c', 'c+', 'd', 'd+', 'e', 'f', 'f+', 'g', 'g+', 'a', 'a+', 'b')


def snapshots(writes, end_tick):
    grouped = defaultdict(lambda: defaultdict(list))
    for w in writes:
        grouped[w.target_ch][w.mdx_tick].append(w)
    result = {}
    for ch, ticks in sorted(grouped.items()):
        state, intervals = {}, []
        times = sorted(set(ticks) | {end_tick})
        for i, tick in enumerate(times[:-1]):
            for w in ticks[tick]:
                state[w.register] = w.data
            if times[i+1] > tick:
                intervals.append((tick, times[i+1], dict(state)))
        result[ch] = intervals
    return result


def render(writes, end_tick, title):
    voices, tracks, mapping = {}, [], []
    for ch, intervals in snapshots(writes, end_tick).items():
        tokens = ['q8']
        for start, end, state in intervals:
            if state.get(0x20+ch, 0) & 63 != 7:
                raise ValueError('Note renderer requires additive AL7/FB0')
            tls = tuple(state[0x60+ch+8*b] for b in range(4))
            attenuation = min(tls)
            ops = tuple((31, 0, 0, 15, 0, tl-attenuation, 0,
                         state[0x40+ch+8*b], 0, 0, 0) for b, tl in enumerate(tls))
            if ops not in voices:
                if len(voices) == 256:
                    raise ValueError('MDX tone bank needs more than 256 voices')
                voices[ops] = len(voices)
            voice = voices[ops]
            kc, kf = state[0x28+ch], state[0x30+ch]
            absolute = (kc >> 4)*12 + KC_CODES.index(kc & 15) + 3
            octave, note = divmod(absolute, 12)
            pan = state[0x20+ch] >> 6
            volume = 127-attenuation if pan else 0
            tokens += [f'@{voice}', f'@v{volume}', f'p{pan}', f'D{(kf>>2)-5}', f'o{octave}']
            duration = end-start
            while duration:
                count = min(duration, 256)
                tokens.append(f'{NAMES[note]}%{count}')
                duration -= count
                if duration or end < end_tick:
                    tokens.append('&')
            mapping.append(dict(track=chr(65+ch), start_tick=start, end_tick=end,
                                voice=voice, volume=volume, pan=pan, kc=kc, kf=kf))
        line = chr(65+ch)
        for token in tokens:
            if len(line)+len(token)+1 > 110:
                tracks.append(line); line = chr(65+ch)
            line += ' '+token
        tracks.append(line)
    title = title.replace('"', "'").replace('\n', ' ').replace('\r', ' ')
    lines = [f'#title "{title}"', '; Additive target rendered as MDX notes, tied across state updates.']
    for ops, vid in voices.items():
        lines += [f'@{vid} = {{', *[' '+','.join(map(str, ops[i]))+',' for i in (0, 2, 1, 3)], ' 7,0,15', '}']
    lines += ['A @t255'] + tracks
    return '\n'.join(lines)+'\n', mapping


def verify(writes, end_tick, actual_controls):
    """Compare positive-duration audible target register states and key edges.

Redundant writes and inaudible setup pitches are not sequence equality.
"""
    expected = [(projected_samples(w.mdx_tick), w.register, w.data) for w in writes]
    def timeline(events):
        times = defaultdict(list)
        for time, reg, data in events:
            times[time].append((reg, data))
        return times
    e, a = timeline(expected), timeline(actual_controls)
    es, ac, errors = {}, {}, []
    keys_e, keys_a = defaultdict(int), defaultdict(int)
    edges_e, edges_a = [], []
    end = projected_samples(end_tick)
    channels = sorted({w.target_ch for w in writes})
    times = sorted(set(e) | set(a) | {end})
    for time in times:
        for events, state, keys, edges in ((e, es, keys_e, edges_e), (a, ac, keys_a, edges_a)):
            for reg, data in events.get(time, []):
                state[reg] = data
                if reg == 8 and data & 7 in channels:
                    ch, mask = data & 7, (data >> 3) & 15
                    if mask != keys[ch]:
                        edges.append((time, ch, keys[ch], mask))
                    keys[ch] = mask
        if time >= end:
            continue
        for ch in channels:
            pan_e, pan_a = es.get(0x20+ch, 0) >> 6, ac.get(0x20+ch, 0) >> 6
            if pan_e != pan_a:
                errors.append((time, ch, 'pan', pan_e, pan_a))
            if pan_e:
                registers = [0x20+ch, 0x28+ch, 0x30+ch, 0x38+ch]
                registers += [base+ch+8*b for base in (0x40,0x60,0x80,0xa0,0xc0,0xe0) for b in range(4)]
                for reg in registers:
                    if es.get(reg, 0) != ac.get(reg, 0):
                        errors.append((time, ch, hex(reg), es.get(reg, 0), ac.get(reg, 0)))
    return dict(passed=not errors and sorted(edges_e)==sorted(edges_a),
                state_mismatches=len(errors), first_mismatches=errors[:20],
                expected_key_edges=sorted(edges_e), actual_key_edges=sorted(edges_a),
                scope='Audible positive-duration register states and all key edges; not waveform equivalence')
