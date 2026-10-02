"""Compare reference loop repetitions with integer source event times.

Correspondence uses note order and verifies pitch sequences, not an assumed
frame period. PSG candidate alignment is reference-specific and separately
verified with a shared clock estimate. No source timing is normalized, and
all raw repetition comparisons are exact; MML is not regenerated.
"""
import argparse
import csv
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'py'), str(ROOT / 'scripts')]
from audit_reference_loop_windows import Loop, parse_reference, windows
from mml_sync import _NOTE, _RHYTHM_NOTE, _duration
from opll_target import target_note


def reference_notes(nodes, macros, infinite_passes=8):
    notes = []
    state = dict(step=0, length=48, octave=4, volume=15, gate=8, tied=False)

    def visit(items, last=False):
        for node in items:
            if isinstance(node, Loop):
                for repeat in range(node.count or infinite_passes):
                    visit(node.body, last=node.count != 0 and repeat == node.count - 1)
                continue
            token, line = node
            token = token.lower()
            if token == '|':
                if last:
                    break
            elif token == '&':
                state['tied'] = True
                if notes:
                    notes[-1]['end'] = state['step']
            elif token.startswith('*'):
                raise ValueError('Reference note alignment does not support macros yet')
            elif re.fullmatch(r'l(%\d+|\d+)\.*', token):
                match = re.fullmatch(r'l(%\d+|\d+)(\.*)', token)
                state['length'] = _duration(*match.groups(), state['length'])
            elif re.fullmatch(r'o\d+', token):
                state['octave'] = int(token[1:])
            elif token in ('<', '>'):
                state['octave'] += 1 if token == '>' else -1
            elif re.fullmatch(r'q\d+', token):
                state['gate'] = int(token[1:])
            elif re.fullmatch(r'v[-+]?\d+', token):
                state['volume'] = (state['volume'] + int(token[1:])
                                   if token[1] in '+-' else int(token[1:]))
            elif token.startswith(('(', ')')):
                state['volume'] += (1 if token[0] == ')' else -1) * int(token[1:] or 1)
            else:
                match = _NOTE.fullmatch(token)
                tie = re.fullmatch(r'\^(%\d+|\d+)?(\.*)', token)
                if not match and not tie:
                    continue
                length = _duration(*(tie or match).groups(), state['length'])
                if tie:
                    if not notes:
                        raise ValueError('Tie extension without a note')
                    notes[-1]['end'] = state['step'] + length
                elif not token.startswith('r') and state['volume'] > 0:
                    pitch = token[:len(token) - len(match[1] or '') - len(match[2])]
                    part = (state['octave'], pitch)
                    end = state['step'] + length * (state['gate'] or 8) / 8
                    if state['tied']:
                        if not notes:
                            raise ValueError('Legato without a note')
                        if notes[-1]['parts'][-1] != part:
                            notes[-1]['parts'].append(part)
                        notes[-1]['end'] = end
                    else:
                        notes.append(dict(start=state['step'], end=end, parts=[part], line=line))
                state['tied'] = False
                state['step'] += length
    visit(nodes)
    return notes


def source_notes(rows):
    """Use physical 0->1 / 1->0 edges, retaining sub-frame state intervals."""
    notes, active = [], None
    for i, row in enumerate(rows):
        if row.get('vgmticks') in (None, ''):
            raise ValueError('Segments lack vgmticks; generate with --vgmticks --dump-passes')
        sample = int(row['vgmticks'])
        if int(row['key_on_edge']):
            if active is not None:
                raise ValueError('A source rising edge occurred without a preceding key-off')
            active = dict(start=sample, end=None, segment_index=i, members=[], trajectory=[])
            notes.append(active)
        if not int(row['keyon']):
            if active is not None:
                active['end'] = sample
            active = None
        if active is None:
            continue
        active['members'].append(i)
        end = int(row['vgmticks_end'])
        if end <= sample:
            continue
        value = tuple(int(row[k]) for k in ('fnum', 'block', 'inst', 'vol', 'sus'))
        runs = active['trajectory']
        if runs and runs[-1][2] == value and runs[-1][1] == sample:
            runs[-1] = (runs[-1][0], end, value)
        else:
            runs.append((sample, end, value))
    for i, note in enumerate(notes):
        note['ioi'] = notes[i + 1]['start'] - note['start'] if i + 1 < len(notes) else None
        note['gate'] = note['end'] - note['start'] if note['end'] is not None else None
        parts = []
        for start, end, value in note['trajectory']:
            # A high/low FNUM register pair can expose a one-sample intermediate
            # pitch. Keep it in raw evidence; exclude only from note alignment.
            if end - start <= 1:
                continue
            pitch = target_note(value[0], value[1])
            if not parts or pitch != parts[-1]:
                parts.append(pitch)
        note['parts'] = parts
    return notes


def psg_decay_notes(rows):
    """Reference-specific candidates for non-increasing software envelopes.

    A volume rise starts a candidate; it is not a PSG hardware KEYON event.
    Do not reuse this rule for arbitrary envelopes or composed voices.
    """
    notes, active, previous_volume = [], None, 0
    for i, row in enumerate(rows):
        if int(row['envelope_enabled']):
            raise ValueError('PSG decay alignment does not support hardware envelopes')
        sample = int(row['vgmticks'])
        volume = int(row['volume']) if int(row['mode']) else 0
        if volume > previous_volume:
            if active is not None and active['end'] is None:
                active['end'] = sample
            active = dict(start=sample, end=None, segment_index=i, members=[], trajectory=[], parts=[])
            notes.append(active)
        if not volume and active is not None:
            active['end'] = sample
            active = None
        if active is not None:
            active['members'].append(i)
            end = int(row['vgmticks_end'])
            if end > sample:
                value = tuple(int(row[k]) for k in ('tone_period', 'volume', 'mode', 'noise_period',
                              'envelope_period', 'envelope_shape'))
                runs = active['trajectory']
                if runs and runs[-1][2] == value and runs[-1][1] == sample:
                    runs[-1] = (runs[-1][0], end, value)
                else:
                    runs.append((sample, end, value))
                part = (int(row['octave']), row['scale'])
                if not active['parts'] or part != active['parts'][-1]:
                    active['parts'].append(part)
        previous_volume = volume
    for i, note in enumerate(notes):
        note['ioi'] = notes[i + 1]['start'] - note['start'] if i + 1 < len(notes) else None
        note['gate'] = note['end'] - note['start'] if note['end'] is not None else None
    return notes


def reference_hits(nodes):
    hits = []
    state = dict(step=0, length=48, volumes=dict.fromkeys('bsmch', 15))
    channels = dict(b=9, s=10, m=11, c=12, h=13)

    def visit(items, last=False):
        for node in items:
            if isinstance(node, Loop):
                for repeat in range(node.count or 8):
                    visit(node.body, last=node.count != 0 and repeat == node.count - 1)
                continue
            token = node[0].lower()
            if token == '|':
                if last:
                    break
            elif re.fullmatch(r'l(%\d+|\d+)\.*', token):
                m = re.fullmatch(r'l(%\d+|\d+)(\.*)', token)
                state['length'] = _duration(*m.groups(), state['length'])
            elif re.fullmatch(r'v[bsmch][-+]?\d+', token):
                name, value = token[1], token[2:]
                state['volumes'][name] = (state['volumes'][name] + int(value)
                                           if value[0] in '+-' else int(value))
            elif token.startswith('*'):
                raise ValueError('Reference hit alignment does not support macros yet')
            else:
                m = _RHYTHM_NOTE.fullmatch(token)
                if not m:
                    continue
                length = _duration('' if m[1] == ':' else m[1], m[2], state['length'])
                prefix = token[:len(token) - len(m[1] or '') - len(m[2])]
                if prefix != 'r':
                    hits.append(dict(start=state['step'], voices=tuple(sorted(
                        (channels[c], state['volumes'][c]) for c in prefix))))
                state['step'] += length
    visit(nodes)
    return hits


def rhythm_comparison(nodes, macros, rows):
    grouped = {}
    for row in rows:
        if row['ev_type'] != 'rhythm_expand' or not int(row['keyon']):
            continue
        value = tuple(int(row[k]) for k in ('ch', 'vol', 'fnum', 'block', 'sus',
                      'fnum_ch6', 'block_ch6', 'fnum_ch7', 'block_ch7', 'fnum_ch8', 'block_ch8'))
        grouped.setdefault(int(row['vgmticks']), []).append(value)
    actual = [dict(start=sample, state=tuple(sorted(values))) for sample, values in sorted(grouped.items())]
    expected = reference_hits(nodes)
    mismatches = [i for i, (a, e) in enumerate(zip(actual, expected))
                  if tuple((v[0], 15 - v[1]) for v in a['state']) != e['voices']]
    alignment = dict(track='f', source_hit_groups=len(actual), expanded_reference_groups=len(expected),
                     instrument_volume_mismatch_indices=mismatches,
                     alignment_verified=not mismatches and len(actual) <= len(expected))
    records, first = [], {}
    if mismatches or len(actual) > len(expected):
        return alignment, records
    loops, _ = windows(nodes, macros, rhythm=True)
    for loop in sorted(loops, key=lambda r: (r['loop_id'], r['step_start'])):
        if not loop['count']:
            continue
        indices = [i for i, e in enumerate(expected) if loop['step_start'] <= e['start'] < loop['step_end']]
        if not indices or indices[-1] >= len(actual):
            continue
        members = [actual[i] for i in indices]
        offsets = tuple(n['start'] - members[0]['start'] for n in members)
        iois = tuple(actual[i + 1]['start'] - actual[i]['start'] if i + 1 < len(actual) else None for i in indices)
        states = tuple(n['state'] for n in members)
        baseline = first.setdefault(loop['loop_id'], dict(loop=loop, offsets=offsets, iois=iois, states=states))
        comparable = (loop['commands'] == baseline['loop']['commands'] and len(offsets) == len(baseline['offsets']))
        records.append(dict(track='f', source_mml_line=loop['line'], loop_id=loop['loop_id'],
            iteration=loop['iteration'], hit_groups=len(members), comparable_to_first=comparable,
            vgmticks_first=members[0]['start'], vgmticks_last=members[-1]['start'],
            raw_onset_offsets_equal=offsets == baseline['offsets'], raw_iois_equal=iois == baseline['iois'],
            state_sequences_equal=states == baseline['states'],
            max_onset_offset_delta_samples=max((abs(a - b) for a, b in zip(offsets, baseline['offsets'])), default=0) if comparable else ''))
    return alignment, records


def note_loop_comparison(track, nodes, macros, rows, actual, expected):
    records, details = [], []
    loops, _ = windows(nodes, macros)
    first = {}
    for loop in sorted(loops, key=lambda r: (r['loop_id'], r['step_start'])):
        if not loop['count']:
            continue
        indices = [i for i, n in enumerate(expected)
                   if loop['step_start'] <= n['start'] < loop['step_end']]
        if not indices or indices[-1] >= len(actual):
            continue
        members = [actual[i] for i in indices]
        if any(n['end'] is None for n in members):
            continue
        anchor = members[0]['start']
        offsets = tuple(n['start'] - anchor for n in members)
        gates = tuple(n['gate'] for n in members)
        iois = tuple(n['ioi'] for n in members)
        states = tuple(tuple(run[2] for run in n['trajectory']) for n in members)
        durations = tuple(tuple(b - a for a, b, _ in n['trajectory']) for n in members)
        stable_states = tuple(tuple(run[2] for run in n['trajectory'] if run[1] - run[0] > 44) for n in members)
        rounded_offsets = tuple(int(rows[n['segment_index']]['tick_start'])
                               - int(rows[members[0]['segment_index']]['tick_start']) for n in members)
        baseline = first.setdefault(loop['loop_id'], dict(loop=loop, offsets=offsets,
                                   gates=gates, iois=iois, states=states, durations=durations,
                                   members=members, rounded_offsets=rounded_offsets, stable_states=stable_states))
        comparable = (loop['commands'] == baseline['loop']['commands']
                      and len(members) == len(baseline['members']))
        records.append(dict(track=track, source_mml_line=loop['line'], loop_id=loop['loop_id'],
            iteration=loop['iteration'], note_count=len(members), comparable_to_first=comparable,
            vgmticks_first=anchor, vgmticks_last_keyoff=members[-1]['end'],
            raw_onset_offsets_equal=offsets == baseline['offsets'],
            raw_gate_lengths_equal=gates == baseline['gates'],
            raw_iois_equal=iois == baseline['iois'],
            state_sequences_equal=states == baseline['states'],
            raw_state_durations_equal=durations == baseline['durations'],
            stable_state_sequences_equal=stable_states == baseline['stable_states'],
            rounded_tick_offsets_equal=rounded_offsets == baseline['rounded_offsets']))
        if comparable:
            for j, (note, old) in enumerate(zip(members, baseline['members'])):
                details.append(dict(track=track, source_mml_line=loop['line'], loop_id=loop['loop_id'],
                    iteration=loop['iteration'], note_in_loop=j, reference_note_index=indices[j],
                    source_segment_index=note['segment_index'], vgmticks=note['start'],
                    gate_samples=note['gate'], ioi_samples=note['ioi'],
                    onset_offset_delta_samples=offsets[j] - baseline['offsets'][j],
                    gate_delta_samples=note['gate'] - old['gate'],
                    ioi_delta_samples=note['ioi'] - old['ioi'] if note['ioi'] is not None and old['ioi'] is not None else '',
                    rounded_offset_delta_ticks=rounded_offsets[j] - baseline['rounded_offsets'][j],
                    state_sequence_equal=states[j] == baseline['states'][j],
                    raw_trajectory=json.dumps(note['trajectory'], separators=(',', ':'))))
    return records, details


def compare(reference_path, segments_path, outdir):
    tracks, macros, tempo = parse_reference(reference_path.read_text(encoding='utf-8-sig'))
    with segments_path.open(newline='', encoding='utf-8') as stream:
        source = list(csv.DictReader(stream))
    records, details, alignments, clock_pairs = [], [], [], []
    for track in '9abcde':
        if track not in tracks:
            continue
        rows = [r for r in source if int(r['ch']) == int(track, 16) - 9]
        if not rows:
            continue
        actual = source_notes(rows)
        expected = reference_notes(tracks[track], macros)
        mismatches = [i for i, (a, b) in enumerate(zip(actual, expected))
                      if a['parts'] and a['parts'] != b['parts']]
        alignments.append(dict(track=track, source_keyon_count=len(actual),
                               alignment_pitch_filter_max_samples=1,
                               expanded_reference_notes=len(expected),
                               pitch_mismatch_indices=mismatches,
                               alignment_verified=not mismatches and len(actual) <= len(expected),
                               terminal_unclosed_notes=sum(n['end'] is None for n in actual)))
        # Never make timing comparisons on an unverified ordinal alignment.
        if mismatches or len(actual) > len(expected):
            continue
        clock_pairs.extend((e['start'], a['start']) for a, e in zip(actual, expected) if a['end'] is not None)
        track_records, track_details = note_loop_comparison(track, tracks[track], macros, rows, actual, expected)
        records.extend(track_records)
        details.extend(track_details)
    outdir.mkdir(parents=True, exist_ok=True)
    rhythm_alignment, rhythm_records = (rhythm_comparison(tracks['f'], macros, source)
                                         if 'f' in tracks else ({}, []))
    psg_alignment, psg_records, psg_details = {}, [], []
    psg_path = segments_path.with_name(segments_path.name.replace('.opll.segments.csv', '.psg.segments.csv'))
    if '1' in tracks and psg_path != segments_path and psg_path.exists() and clock_pairs:
        with psg_path.open(newline='', encoding='utf-8') as stream:
            psg_rows = [r for r in csv.DictReader(stream) if int(r['ch']) == 0]
        actual = psg_decay_notes(psg_rows)
        expected = reference_notes(tracks['1'], macros)
        mismatches = [i for i, (a, e) in enumerate(zip(actual, expected)) if a['parts'] and a['parts'] != e['parts']]
        mx = sum(x for x, y in clock_pairs) / len(clock_pairs)
        my = sum(y for x, y in clock_pairs) / len(clock_pairs)
        scale = sum((x - mx) * (y - my) for x, y in clock_pairs) / sum((x - mx)**2 for x, y in clock_pairs)
        # A shared slope inferred from OPLL checks candidate order. It neither
        # changes PSG source timing nor supplies the raw loop comparison.
        errors = [abs(actual[i]['ioi'] - (expected[i + 1]['start'] - expected[i]['start']) * scale)
                  for i in range(min(len(actual) - 1, len(expected) - 1))]
        verified = not mismatches and len(actual) <= len(expected) and max(errors, default=0) <= 735
        psg_alignment = dict(track='1', method='volume-reset candidates for this decaying-envelope reference only',
            source_volume_resets=len(actual), expanded_reference_notes=len(expected),
            pitch_mismatch_indices=mismatches, alignment_verified=verified,
            inferred_shared_samples_per_reference_step=scale, alignment_ioi_tolerance_samples=735,
            maximum_alignment_ioi_error_samples=max(errors, default=0))
        if verified:
            psg_records, psg_details = note_loop_comparison('1', tracks['1'], macros, psg_rows, actual, expected)
    for name, data in (('reference_loop_vgmticks.csv', records), ('reference_note_vgmticks.csv', details)):
        if data:
            with (outdir / name).open('w', newline='', encoding='utf-8') as stream:
                writer = csv.DictWriter(stream, fieldnames=list(data[0]))
                writer.writeheader()
                writer.writerows(data)
    if rhythm_records:
        with (outdir / 'reference_rhythm_vgmticks.csv').open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rhythm_records[0]))
            writer.writeheader()
            writer.writerows(rhythm_records)
    for name, data in (('reference_psg_loop_vgmticks.csv', psg_records), ('reference_psg_note_vgmticks.csv', psg_details)):
        if data:
            with (outdir / name).open('w', newline='', encoding='utf-8') as stream:
                writer = csv.DictWriter(stream, fieldnames=list(data[0]))
                writer.writeheader()
                writer.writerows(data)
    later = [r for r in records if r['iteration'] and r['comparable_to_first']]
    differences = [r for r in details if r['iteration']]
    psg_later = [r for r in psg_records if r['iteration'] and r['comparable_to_first']]
    rhythm_later = [r for r in rhythm_records if r['iteration'] and r['comparable_to_first']]
    summary = dict(tempo=tempo, sample_rate=44100, alignment='source key-edge order verified by complete note pitch sequences',
        scope='OPLL melody/rhythm plus reference-specific PSG volume-reset candidates; no general PSG note inference',
        alignment_pitch_filter_max_samples=1, stable_state_filter_max_samples=44,
        alignments=alignments, compared_later_windows=len(later),
        rhythm_alignment=rhythm_alignment,
        rhythm_compared_later_windows=sum(r['iteration'] > 0 and r['comparable_to_first'] for r in rhythm_records),
        psg_alignment=psg_alignment,
        psg_compared_later_windows=sum(r['iteration'] > 0 and r['comparable_to_first'] for r in psg_records),
        psg_differences={field: sum(not r[field] for r in psg_later) for field in
            ('raw_onset_offsets_equal', 'raw_gate_lengths_equal', 'raw_iois_equal', 'state_sequences_equal')},
        rhythm_differences={field: sum(not r[field] for r in rhythm_later) for field in
            ('raw_onset_offsets_equal', 'raw_iois_equal', 'state_sequences_equal')},
        rhythm_maximum_onset_offset_delta_samples=max(
            (r['max_onset_offset_delta_samples'] for r in rhythm_later), default=0),
        differences={field: sum(not r[field] for r in later) for field in
            ('raw_onset_offsets_equal', 'raw_gate_lengths_equal', 'raw_iois_equal',
             'state_sequences_equal', 'raw_state_durations_equal', 'stable_state_sequences_equal', 'rounded_tick_offsets_equal')},
        maximum_absolute_deltas={field: max((abs(r[field]) for r in differences if r[field] != ''), default=0)
            for field in ('onset_offset_delta_samples', 'gate_delta_samples', 'ioi_delta_samples', 'rounded_offset_delta_ticks')})
    (outdir / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reference', type=Path)
    parser.add_argument('--segments', type=Path, required=True)
    parser.add_argument('--outdir', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(compare(args.reference, args.segments, args.outdir), indent=2))
