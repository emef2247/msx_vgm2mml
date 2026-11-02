"""NDP score pages: the blueprint score re-spelled for naruto's PSG driver.

NDP (PSG Driver for MSX, by naruto2413) is a PSG-only driver with its own
MML: tone tracks 1-3 for PSG Ch.A-C and a rhythm track R whose voices
interrupt Ch.C. This projection consumes the same step-space score notes
the blueprint pages render, so the two pages can never disagree about the
score. PSG tone lanes take tracks 1-3; the most active remaining tone
lanes are folded into any free tracks as an arrangement scaffold, and
noise-role lanes become rhythm voices on track R.

Like the blueprint pages, dynamics and synthesis controls are omitted
(fixed V15, no envelope definitions); source timbres stay documentary
comments. Note lengths are frame-exact: NDP runs at 60 frames per second,
and lengths are spelled on the #TIMEBASE grid with %frame ties for the
remainder, so no timing is silently rounded into different music.
"""
from collections import defaultdict
from fractions import Fraction
import json
import textwrap

NOTES = ('c', 'c+', 'd', 'd+', 'e', 'f', 'f+', 'g', 'g+', 'a', 'a+', 'b')
# Rhythm voice letters: a-z minus the R-track commands this page emits
# itself (rests r, and l/v/t which stay available as commands).
RHYTHM_LETTERS = tuple(c for c in 'abcdefghijklmnopqrstuvwxyz' if c not in 'lrtv')
MAX_RHYTHM_VOICES = len(RHYTHM_LETTERS)
MAX_RHYTHM_FRAMES = 24


def _frames(step, tempo):
    """Score steps to NDP frames (60 fps), rounding half up, exactly."""
    value = Fraction(step * 75, tempo) + Fraction(1, 2)
    return value.numerator // value.denominator


def _length_tokens(frames, timebase):
    """Spell a frame count as NDP length tokens on the timebase grid."""
    values = [(value, token) for value, token in
              ((4 * timebase, '1'), (3 * timebase, '2.'), (2 * timebase, '2'),
               (timebase, '4'), (timebase // 2, '8'), (timebase // 4, '16'),
               (timebase // 8, '32'), (timebase // 16, '64')) if value > 0]
    tokens = []
    rest = frames
    for value, token in values:
        while rest >= value:
            tokens.append(token)
            rest -= value
    if rest:
        tokens.append(f'%{rest}')
    return tokens or ['%0']


def _spell(frames, timebase):
    """Length suffix chain: first token bare, the rest tied with ^."""
    tokens = _length_tokens(frames, timebase)
    return tokens[0] + ''.join('^' + token for token in tokens[1:])


def _lane_key(row):
    return (row['source_chip'], row['source_instance'], row['source_section'], row['source_channel'])


def _harvest(pages, performance):
    """Rebuild source lanes in score steps from the rendered blueprint pages."""
    units = {unit.unit_id: unit for unit in performance.units}
    devices = {device.device_id: device for device in performance.devices}
    lanes, unmapped_percussion = [], []
    grouped = defaultdict(list)
    targets = {}
    tempo, end_step = None, 0
    for _, report in pages:
        tempo = report['tempo']
        end_step = max(end_step, report['end_step'])
        for row in report['allocations']:
            targets[row['unit_id']] = row['target_chip']
        for row in report['score_notes']:
            if row['percussion']:
                unmapped_percussion.append(row)
            else:
                grouped[_lane_key(row)].append(row)
    for key, rows in grouped.items():
        rows.sort(key=lambda r: (r['step_start'], r['step_end'], r['unit_id']))
        sublanes, current = [], None
        for row in rows:
            if current is None or row['step_start'] < current[-1]['step_end']:
                current = []
                sublanes.append(current)
            current.append(row)
        for index, spans in enumerate(sublanes):
            roles = {units[row['unit_id']].role for row in spans if row['unit_id'] in units}
            lanes.append(dict(key=key, chunk=index, spans=spans, roles=roles,
                              primary={targets.get(row['unit_id']) for row in spans} == {'psg'},
                              sounding=sum(r['step_end'] - r['step_start'] for r in spans)))
    return lanes, unmapped_percussion, tempo, end_step


def _noise_period(unit, devices):
    """Recover the AY noise period (0-31) a noise unit sounds at, if known."""
    device = devices.get(unit.device_id)
    clock = device.clock_hz if device else 1789773
    for _, frequency in unit.pitch_curve:
        if frequency:
            return max(0, min(31, round(clock / (16 * frequency))))
    return None


def _render_tone_lane(lane, tempo, timebase, total_frames, loop_frame):
    """Render one lane's spans as an NDP track body in frames."""
    spans = []
    for row in lane['spans']:
        start, stop = _frames(row['step_start'], tempo), _frames(row['step_end'], tempo)
        if stop > start:
            spans.append((start, stop, row['midi_note'], row['unit_id'], row['attack']))
    if loop_frame is not None:
        split = []
        for start, stop, midi, unit_id, attack in spans:
            if start < loop_frame < stop:
                split.append((start, loop_frame, midi, unit_id, attack))
                split.append((loop_frame, stop, midi, unit_id, False))
            else:
                split.append((start, stop, midi, unit_id, attack))
        spans = split
    tokens, cursor, octave, loop_pending = [], 0, None, loop_frame is not None
    index = 0
    while index < len(spans):
        start, stop, midi, unit_id, attack = spans[index]
        if start > cursor:
            if loop_pending and cursor < loop_frame < start:
                tokens.append('r' + _spell(loop_frame - cursor, timebase))
                tokens.append('@L')
                loop_pending, cursor = False, loop_frame
            prefix = '@L ' if loop_pending and cursor == loop_frame else ''
            if prefix:
                loop_pending = False
            tokens.append(prefix + 'r' + _spell(start - cursor, timebase))
            cursor = start
        # Merge this unit's spans: equal pitches extend, new pitches slur.
        group = [(start, stop, midi)]
        index += 1
        while index < len(spans) and spans[index][3] == unit_id and spans[index][0] == group[-1][1]:
            group.append((spans[index][0], spans[index][1], spans[index][2]))
            index += 1
        for number, (gstart, gstop, gmidi) in enumerate(group):
            note_octave = gmidi // 12 - 1
            prefix = ''
            if loop_pending and gstart == loop_frame:
                prefix, loop_pending = '@L ', False
            if note_octave != octave:
                prefix += f'o{note_octave} '
                octave = note_octave
            slur = '&' if number else ''
            tokens.append(prefix + slur + NOTES[gmidi % 12] + _spell(gstop - gstart, timebase))
        cursor = group[-1][1]
    if loop_pending and cursor == loop_frame:
        tokens.append('@L')
        loop_pending = False
    if cursor < total_frames:
        if loop_pending and cursor < loop_frame < total_frames:
            tokens.append('r' + _spell(loop_frame - cursor, timebase))
            tokens.append('@L')
            loop_pending, cursor = False, loop_frame
        prefix = '@L ' if loop_pending and cursor == loop_frame else ''
        tokens.append(prefix + 'r' + _spell(total_frames - cursor, timebase))
        loop_pending = False
    return ' '.join(tokens), loop_pending


def render_ndp_page(pages, performance):
    """Return (NDP MML text, report) or None when no lane can be rendered."""
    if not pages:
        return None
    lanes, unmapped_percussion, tempo, end_step = _harvest(pages, performance)
    tone_lanes = [lane for lane in lanes if 'noise' not in lane['roles'] and lane['key'][2] != 'noise']
    noise_lanes = [lane for lane in lanes if lane not in tone_lanes]
    if not tone_lanes and not noise_lanes:
        return None
    devices = {device.device_id: device for device in performance.devices}
    units = {unit.unit_id: unit for unit in performance.units}
    total_frames = _frames(end_step, tempo)
    if total_frames <= 0:
        return None
    timebase = max(1, round(3600 / tempo))
    loop_frame = None
    if performance.song_loop_sample:
        candidate = round(performance.song_loop_sample / 735)
        if 0 < candidate < total_frames:
            loop_frame = candidate
    # Lanes already projected onto PSG take tracks first (source channel
    # order); the most active remaining tone lanes fold into free tracks.
    def source_rank(lane):
        _, instance, _, channel = lane['key']
        return (instance, channel, lane['chunk'])
    primary = sorted((lane for lane in tone_lanes if lane['primary']), key=source_rank)
    others = [lane for lane in tone_lanes if not lane['primary']]
    others.sort(key=lambda lane: (-lane['sounding'], lane['key'], lane['chunk']))
    assignment, omitted = [], []
    for lane in primary + others:
        if len(assignment) < 3:
            assignment.append(lane)
        else:
            omitted.append(lane)
    tracks = {}
    loop_unplaced = []
    for number, lane in enumerate(assignment, 1):
        body, pending = _render_tone_lane(lane, tempo, timebase, total_frames, loop_frame)
        tracks[number] = (lane, body)
        if pending:
            loop_unplaced.append(number)
    # Noise lanes merge by priority; overlaps keep the earlier lane's hit.
    noise_lanes.sort(key=lambda lane: (not lane['primary'], lane['key'], lane['chunk']))
    hits, noise_omitted = [], []
    for lane in noise_lanes:
        for row in lane['spans']:
            start, stop = _frames(row['step_start'], tempo), _frames(row['step_end'], tempo)
            if stop <= start:
                continue
            unit = units.get(row['unit_id'])
            period = _noise_period(unit, devices) if unit else None
            volume = 15
            if unit and unit.volume_curve:
                volume = max(0, min(15, round(unit.volume_curve[0][1])))
            hits.append((start, stop, period, volume, lane))
    hits.sort(key=lambda hit: (hit[0], hit[1]))
    merged, cursor = [], 0
    for hit in hits:
        start, stop = hit[0], hit[1]
        if start < cursor:
            start = cursor
        if stop > start:
            merged.append((start, stop, hit[2], hit[3], hit[4]))
            cursor = stop
        else:
            noise_omitted.append(hit)
    # Rhythm voices keyed by (period, volume, capped duration).
    voices, rhythm_tokens, approximations = {}, [], []
    unknown_period = [hit for hit in merged if hit[2] is None]
    known_periods = sorted({hit[2] for hit in merged if hit[2] is not None})
    fallback_period = known_periods[len(known_periods) // 2] if known_periods else 16
    for start, stop, period, volume, lane in merged:
        if period is None:
            period = fallback_period
            approximations.append(dict(kind='noise_period_unknown', step_frame=start,
                                       fallback_period=period))
        duration = min(stop - start, MAX_RHYTHM_FRAMES)
        key = (period, volume, duration)
        if key not in voices:
            if len(voices) >= MAX_RHYTHM_VOICES:
                nearest = min(voices, key=lambda k: (abs(k[0] - period), abs(k[1] - volume),
                                                     abs(k[2] - duration)))
                approximations.append(dict(kind='rhythm_voice_folded', wanted=key, used=nearest))
                key = nearest
            else:
                voices[key] = RHYTHM_LETTERS[len(voices)]
        rhythm_tokens.append((start, stop, voices[key]))
    rhythm_body = None
    if rhythm_tokens:
        tokens, cursor = [], 0
        for start, stop, letter in rhythm_tokens:
            if start > cursor:
                tokens.append('r' + _spell(start - cursor, timebase))
            tokens.append(letter + _spell(stop - start, timebase))
            cursor = stop
        if cursor < total_frames:
            tokens.append('r' + _spell(total_frames - cursor, timebase))
        rhythm_body = ' '.join(tokens)
    # Documentary header, mirroring the blueprint pages' conventions.
    lines = ['; Editable NDP blueprint: dynamics and synthesis controls are omitted.',
             '; NDP (PSG Driver for MSX) and its MML format are by naruto; see https://ndp.squares.net/',
             '; All source volume commands and instrument definitions are removed.',
             '; Audition defaults only: fixed v15 on every track; edit freely.',
             '; Note lengths are frame-exact for NDP (60 fps); steps match the blueprint score pages.',
             '; Source timbres are documentary only; no source instrument selections are restored.',
             f'; Source duration {performance.end_sample} samples; projected duration {total_frames} frames.']
    if 3600 % tempo:
        lines.append(f'; #TIMEBASE {timebase} frames per quarter note approximates tempo {tempo} '
                     f'(effective {3600 / timebase:.1f}); lengths stay frame-exact via % ties.')
    if loop_frame is not None:
        lines.append(f'; Song loop starts at frame {loop_frame}; @L marks it in each rendered track.')
    for number, (lane, _) in tracks.items():
        chip, instance, section, channel = lane['key']
        folded = ' (folded into a free track)' if not lane['primary'] else ''
        lines.append(f'; Track {number}: source {chip.upper()} #{instance + 1} / {section} ch {channel + 1}'
                     f'{folded}; score notes {len(lane["spans"])}.')
    for lane in omitted:
        chip, instance, section, channel = lane['key']
        lines.append(f'; Omitted lane (no free NDP track): {chip.upper()} #{instance + 1} / {section} ch {channel + 1}.')
    for lane in noise_lanes:
        chip, instance, section, channel = lane['key']
        lines.append(f'; Rhythm track R: source {chip.upper()} #{instance + 1} / {section} ch {channel + 1} noise.')
    if noise_omitted:
        lines.append(f'; Noise hits lost to an earlier overlapping lane: {len(noise_omitted)}.')
    for row in unmapped_percussion[:8]:
        lines.append('; Unmapped percussion: ' + json.dumps(
            dict(unit_id=row['unit_id'], source_chip=row['source_chip']), sort_keys=True))
    if len(unmapped_percussion) > 8:
        lines.append(f'; Unmapped percussion: {len(unmapped_percussion) - 8} more events.')
    documented = {}
    for _, report in pages:
        for voice in report.get('documented_voices', []):
            documented.setdefault(voice['voice_id'], voice)
    used_voices = {voice_id for _, report in pages for row in report['allocations']
                   for voice_id in row['voice_ids']}
    for identity in sorted(used_voices & set(documented)):
        voice = documented[identity]
        lines.append(f'; Timbre: source voice {identity}')
        description = 'Voice parameters: ' + json.dumps(voice.get('parameters', {}),
                                                        ensure_ascii=True, sort_keys=True)
        lines.extend('; ' + line for line in textwrap.wrap(description, width=106,
                                                           break_long_words=True, break_on_hyphens=False))
    lines.append(f'#TEMPO {tempo}')
    lines.append(f'#TIMEBASE {timebase}')
    for (period, volume, duration), letter in sorted(voices.items(), key=lambda item: item[1]):
        lines.append(f'@R:{letter}=*2 N{period} V{volume}' + ' /' * (duration - 1))
    for number, (_, body) in tracks.items():
        lines.append(f'{number} v15 ' + body)
    if rhythm_body is not None:
        lines.append('R ' + rhythm_body)
    report = dict(status='success', tempo=tempo, timebase_frames=timebase, total_frames=total_frames,
                  loop_frame=loop_frame, loop_unplaced_tracks=loop_unplaced,
                  tracks={str(number): dict(source_chip=lane['key'][0], source_instance=lane['key'][1],
                                            source_section=lane['key'][2], source_channel=lane['key'][3],
                                            chunk=lane['chunk'], folded=not lane['primary'])
                          for number, (lane, _) in tracks.items()},
                  omitted_lanes=[dict(source_chip=lane['key'][0], source_instance=lane['key'][1],
                                      source_section=lane['key'][2], source_channel=lane['key'][3],
                                      chunk=lane['chunk']) for lane in omitted],
                  rhythm_voices=[dict(letter=letter, period=key[0], volume=key[1], frames=key[2])
                                 for key, letter in sorted(voices.items(), key=lambda item: item[1])],
                  rhythm_hits=len(merged), noise_hits_omitted=len(noise_omitted),
                  unmapped_percussion=len(unmapped_percussion), approximations=approximations,
                  volume_policy='source_volume_commands_removed; fixed audition volume only',
                  timbre_policy='all source timbres documentary only; fixed audition defaults are target-only')
    return '\n'.join(lines) + '\n', report
