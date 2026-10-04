"""Inspectable hybrid MDX notes and reversible per-track loop structure.

Native Segments are never rewritten. Only isolated fixed-mask attacks with
complete, losslessly encodable tones become ordinary MDX notes; all other
controls keep explicit register spelling. Source times remain absolute.
"""
import csv
from collections import Counter
from dataclasses import asdict, dataclass, replace
import json
from pathlib import Path

from opm import NOTE_NAMES, key_counts
from opm_mdx import mdx_tick, projected_samples
from opm_loops import build_source_loops, OpmLoopProjection
from mdx_compaction import compact

KC_CODES = (0, 1, 2, 4, 5, 6, 8, 9, 10, 12, 13, 14)
VOICE_FIELDS = ('ar', 'd1r', 'd2r', 'rr', 'd1l', 'tl', 'ks',
                'mul', 'dt1', 'dt2', 'am_enabled')


@dataclass(frozen=True)
class MdxUnit:
    track: str
    start_tick: int
    end_tick: int
    command: str
    source_event_ids: tuple
    source_segment_ids: tuple
    kind: str = 'controls'
    voice_id: int | None = None
    target_note: str = ''


def voice_key(state):
    """A tone bank cannot encode unknown fields or discarded register bits."""
    if state.algorithm is None or state.feedback is None:
        return None
    rows = tuple(tuple(getattr(op, field) for field in VOICE_FIELDS)
                 for op in state.operators)
    if any(value is None for row in rows for value in row):
        return None
    regs = dict(state.channel_registers)
    # Retain unsupported/reserved bits by leaving those attacks as y commands.
    for reg, value in regs.items():
        masks = {0x40: 0x7f, 0x60: 0x7f, 0x80: 0xdf,
                 0xa0: 0x9f, 0xc0: 0xdf, 0xe0: 0xff}
        base = reg & 0xe0
        if base in masks and value & ~masks[base]:
            return None
    return rows, state.algorithm, state.feedback, state.key_mask


def note_spelling(state):
    """Invert MDX's KC table and explicit five-unit fine-pitch bias.

    This is target notation, distinct from the native canonical KC label.
    The resulting MDX note plus D must reproduce the original KC/KF bytes.
    """
    kc, kf = state.kc_raw, state.kf_raw
    if kc is None or kf is None or kc & 0x80 or kf & 3 or (kc & 15) not in KC_CODES:
        return None
    index = (kc >> 4) * 12 + KC_CODES.index(kc & 15)
    absolute = index + 3
    octave, semitone = divmod(absolute, 12)
    return octave, NOTE_NAMES[semitone], (kf >> 2) - 5


def note_command(octave, name, detune, duration, voice, pan):
    # A compiled MDX note is at most 256 ticks. Explicit ties avoid accidental
    # retriggers from a compiler splitting a long % duration into plain notes.
    chunks = []
    while duration:
        count = min(duration, 256)
        chunks.append(f'{name}%{count}')
        duration -= count
    return f'@{voice} @v127 p{pan} q8 D{detune} o{octave} ' + ' & '.join(chunks)


def advance(duration):
    chunks = []
    while duration:
        count = min(duration, 65535)
        chunks.append(f'r%{count}')
        duration -= count
    return ' '.join(chunks)


@dataclass
class MdxStructure:
    units: dict
    voices: tuple
    plans: dict
    reports: dict
    text: str
    plain_text: str
    uncompacted_text: str
    compaction: tuple

    def summary(self):
        depth = maximum = 0
        for line in self.text.splitlines():
            if len(line) < 2 or line[0] not in 'ABCDEFGH' or line[1] != ' ':
                continue
            for character in line:
                if character == '[':
                    depth += 1; maximum = max(maximum, depth)
                elif character == ']':
                    depth -= 1
        return dict(notation='structured', voices=len(self.voices),
                    note_units=sum(u.kind == 'note' for units in self.units.values() for u in units),
                    raw_units=sum(u.kind == 'controls' for units in self.units.values() for u in units),
                    loop_markers=sum(len(rows) for rows in self.reports.values()),
                    applied_loops=sum(r['status'] == 'applied' for rows in self.reports.values() for r in rows),
                    emitted_loop_commands=sum(line.count('[') for line in self.text.splitlines()
                                              if len(line) > 1 and line[0] in 'ABCDEFGH' and line[1] == ' '),
                    max_loop_depth=maximum,
                    source_loop_tracks=sum(bool(any(a['opm_source_loop_path'] for a in plan.source.annotations().values()))
                                           for plan in self.plans.values()),
                    loop_projection_status={track: plan.status for track, plan in self.plans.items()},
                    source_loop_commands=sum(line.count('[') for line in self.uncompacted_text.splitlines()
                                             if len(line) > 1 and line[0] in 'ABCDEFGH' and line[1] == ' '),
                    omitted_setters=sum(r['action'] == 'omit_setter' for r in self.compaction),
                    duration_compactions=sum(r['action'] != 'omit_setter' for r in self.compaction),
                    compaction_bytes_saved_estimate=sum(r['bytes_saved'] for r in self.compaction),
                    uncompacted_mml_chars=len(self.uncompacted_text),
                    plain_mml_chars=len(self.plain_text), structured_mml_chars=len(self.text))

    def dump(self, prefix, *, segments_csv=None):
        prefix = Path(prefix)
        prefix.parent.mkdir(parents=True, exist_ok=True)
        Path(str(prefix)+'.plain.mml').write_text(self.plain_text, encoding='utf-8')
        Path(str(prefix)+'.uncompacted.mml').write_text(self.uncompacted_text, encoding='utf-8')
        with Path(str(prefix)+'.compaction.csv').open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=('track', 'token_index', 'action', 'before',
                                                       'after', 'reason', 'bytes_saved'))
            writer.writeheader(); writer.writerows(self.compaction)
        rows, annotations, source_annotations = [], {}, {}
        for track, units in self.units.items():
            plan = self.plans[track]
            source_annotations.update(plan.source.annotations())
            for index, unit in enumerate(units):
                paths = [dict(path, ch=ord(track)-65, projection_status=plan.status)
                         for sid in unit.source_segment_ids
                         for path in source_annotations.get(sid, {}).get('opm_source_loop_path', [])]
                row = asdict(unit)
                row.update(unit_id=f'{track}:{index}', loop_path=paths)
                for key in ('source_event_ids', 'source_segment_ids', 'loop_path'):
                    row[key] = json.dumps(row[key], separators=(',', ':'))
                rows.append(row)
                for sid in unit.source_segment_ids:
                    annotations.setdefault(sid, []).append((f'{track}:{index}', paths, unit.voice_id))
        fields = ('unit_id', 'track', 'start_tick', 'end_tick', 'kind', 'voice_id',
                  'target_note', 'command', 'source_event_ids', 'source_segment_ids', 'loop_path')
        with Path(str(prefix)+'.units.csv').open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader(); writer.writerows(rows)
        with Path(str(prefix)+'.voices.csv').open('w', newline='', encoding='utf-8') as stream:
            writer = csv.writer(stream)
            writer.writerow(('voice_id', 'algorithm', 'feedback', 'key_mask', 'operator_rows'))
            for vid, (ops, alg, fb, mask) in enumerate(self.voices):
                writer.writerow((vid, alg, fb, mask, json.dumps(ops)))
        if segments_csv is not None:
            path = Path(segments_csv)
            with path.open(newline='', encoding='utf-8') as stream:
                reader = csv.DictReader(stream)
                fields, source_rows = list(reader.fieldnames), list(reader)
            for field in ('mdx_unit_ids', 'mdx_voice_ids', 'mdx_loop_path',
                          'opm_phrase_unit_id', 'opm_source_loop_path', 'mdx_loop_projection'):
                if field not in fields:
                    fields.append(field)
            for row in source_rows:
                sid = int(row['segment_id'])
                entries = annotations.get(sid, [])
                native = source_annotations.get(sid, {})
                row['opm_phrase_unit_id'] = native.get('opm_phrase_unit_id', '')
                row['opm_source_loop_path'] = json.dumps(native.get('opm_source_loop_path', []))
                row['mdx_loop_projection'] = self.plans[chr(65+int(row['ch']))].status if chr(65+int(row['ch'])) in self.plans else 'no_target_track'
                row['mdx_unit_ids'] = json.dumps([entry[0] for entry in entries])
                row['mdx_voice_ids'] = json.dumps(sorted({entry[2] for entry in entries if entry[2] is not None}))
                row['mdx_loop_path'] = json.dumps([p for _, paths, _ in entries for p in paths])
            with path.open('w', newline='', encoding='utf-8') as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader(); writer.writerows(source_rows)


def build_structure(projection, source_segments, *, title='OPM Segment replay', loops=True):
    """Build target units, then reversible loops; no inferred source edits."""
    source_plans = build_source_loops(source_segments)
    by_event = {}
    for segment in source_segments:
        if segment.source_event_id is not None:
            by_event.setdefault(segment.source_event_id, {})[segment.ch] = segment
    tracks = {'A': []}
    for write in projection.writes:
        tracks.setdefault(write.mdx_track, []).append(write)
    voices, units_by_track = {}, {}
    for track, writes in sorted(tracks.items()):
        ch = ord(track)-65
        units, cursor, index = [], 0, 0
        while index < len(writes):
            write = writes[index]
            if write.mdx_tick > cursor:
                units.append(MdxUnit(track, cursor, write.mdx_tick,
                                     advance(write.mdx_tick-cursor), (), (), 'time'))
                cursor = write.mdx_tick
            # Consecutive pitch setup at the same projected attack time can be
            # subsumed by the note. No unrelated control is moved across it.
            onset = index
            while (onset < len(writes) and writes[onset].mdx_tick == cursor
                   and writes[onset].register in (0x28+ord(track)-65, 0x30+ord(track)-65)):
                onset += 1
            attack = writes[onset] if onset < len(writes) and writes[onset].mdx_tick == cursor else write
            segment = by_event[attack.source_event_id].get(ch)
            off = writes[onset+1] if onset+1 < len(writes) else None
            key = voice_key(segment.state) if segment is not None else None
            spelling = note_spelling(segment.state) if segment is not None else None
            safe = (segment is not None and attack.register == 8 and segment.state.key_mask > 0
                    and segment.rising_mask == segment.state.key_mask and segment.falling_mask == 0
                    and attack.data & 0x80 == 0
                    and onset-index <= 2
                    and len({w.register for w in writes[index:onset]}) == onset-index
                    and off is not None and off.register == 8 and off.data == ch
                    and off.mdx_tick > cursor and key is not None and spelling is not None
                    and segment.state.noise_enabled != 1 and (key in voices or len(voices) < 256))
            if safe:
                vid = voices.setdefault(key, len(voices))
                octv, name, detune = spelling
                control = dict(segment.state.channel_registers).get(0x20+ch)
                if control is None:
                    safe = False
            if safe:
                members = writes[index:onset+2]
                command = note_command(octv, name, detune, off.mdx_tick-cursor, vid, control >> 6)
                units.append(MdxUnit(track, cursor, off.mdx_tick, command,
                    tuple(w.source_event_id for w in members),
                    tuple(sid for w in members for sid in w.source_segment_ids),
                    'note', vid, f'o{octv}{name} D{detune}'))
                cursor, index = off.mdx_tick, onset+2
                continue
            # Raw units group same-tick controls and the following time advance.
            stop = index + 1
            while stop < len(writes) and writes[stop].mdx_tick == cursor:
                stop += 1
            # Stop before a eligible same-tick attack so setup does not hide it.
            for candidate in range(index+1, stop):
                if writes[candidate].register == 8 and writes[candidate].data >> 3 > 0:
                    stop = candidate
                    break
            end = writes[stop].mdx_tick if stop < len(writes) else projection.end_mdx_tick
            members = writes[index:stop]
            commands = [f'y{w.register},{w.data}' for w in members]
            if end > cursor:
                commands.append(advance(end-cursor))
            units.append(MdxUnit(track, cursor, end, ' '.join(commands),
                                tuple(w.source_event_id for w in members),
                                tuple(sid for w in members for sid in w.source_segment_ids)))
            cursor, index = end, stop
        if cursor < projection.end_mdx_tick:
            units.append(MdxUnit(track, cursor, projection.end_mdx_tick,
                         advance(projection.end_mdx_tick-cursor), (), (), 'time'))
        # An exported final wait may merge the last phrase's delay and the
        # song tail. Split one previously repeated exact prefix, without
        # changing total time or inventing an attack/rest boundary in source.
        if units and units[-1].kind == 'time':
            tail = units[-1]
            counts = Counter(u.end_tick-u.start_tick for u in units[:-1] if u.kind == 'time')
            prefixes = [duration for duration, count in counts.items()
                        if count >= 2 and 0 < duration < tail.end_tick-tail.start_tick]
            if prefixes:
                split = tail.start_tick+max(prefixes)
                units[-1:] = [replace(tail, end_tick=split, command=advance(split-tail.start_tick)),
                              replace(tail, start_tick=split, command=advance(tail.end_tick-split))]
        # Time-only slices still point to the native state interval they cover.
        # One native Segment can consequently belong to several target units.
        for i, unit in enumerate(units):
            if unit.kind == 'time':
                ids = tuple(s.segment_id for s in source_segments if s.ch == ch
                            and mdx_tick(s.vgmticks) < unit.end_tick
                            and unit.start_tick < mdx_tick(s.vgmticks_end))
                units[i] = replace(unit, source_segment_ids=ids)
        units_by_track[track] = tuple(units)
    title = str(title).replace('"', "'").replace('\r', ' ').replace('\n', ' ')
    header = [f'#title "{title}"', '; OPM hybrid notes/register controls; ch0..7 -> A..H.',
              '; @t255=256 us; source Segments remain unchanged.']
    for key, vid in voices.items():
        ops, alg, fb, mask = key
        header += [f'@{vid} = {{', *['  '+','.join(map(str, ops[i]))+',' for i in (0, 2, 1, 3)],
                   f'  {alg},{fb},{mask}', '}']
    header.append('A @t255')
    plans, reports, plain, structured = {}, {}, header[:], header[:]
    uncompacted, compaction = header[:], []
    for track, units in units_by_track.items():
        commands = [u.command for u in units]
        plan = OpmLoopProjection.build(source_plans[0, ord(track)-65], units, mdx_tick)
        text, report = plan.render(commands) if loops else (' '.join(commands), [])
        plans[track], reports[track] = plan, report
        # Identical wrapping makes the loop/no-loop size comparison meaningful.
        # Track prefixes resume the same stream across physical lines.
        def wrapped(body):
            lines, line = [], track
            for word in body.split():
                if len(line)+len(word)+1 > 110:
                    lines.append(line); line = track
                line += ' '+word
            if line != track:
                lines.append(line)
            return lines
        plain += wrapped(' '.join(commands))
        uncompacted += wrapped(text)
        compacted, decisions = compact(text, track, durations=loops)
        compaction.extend(decisions)
        structured += wrapped(compacted)
    return MdxStructure(units_by_track, tuple(voices), plans, reports,
                        '\n'.join(structured)+'\n', '\n'.join(plain)+'\n',
                        '\n'.join(uncompacted)+'\n', tuple(compaction))


def compare_hybrid(projection, source, actual, *, initialization):
    """Compare Key edges and effective state on the union of target boundaries.

    Ordinary note/@voice expansion changes the register sequence. This separate
    semantic comparison does not replace the strict register replay comparator.
    It checks all source-known raw/decoded values, including released tails.
    """
    from opm_roundtrip import controls, _known_differences
    raw = controls(actual)
    prefix_ok = raw[:len(initialization)] == list(initialization)
    def edges(analysis, projected):
        return {ch: [(mdx_tick(e.vgmticks) if projected else e.vgmticks,
                      e.rising_mask, e.falling_mask) for e in analysis.events
                     if e.ch == ch and (e.rising_mask or e.falling_mask)] for ch in range(8)}
    expected_edges = edges(source, True)
    returned_edges = edges(actual, False)
    expected_edges = {ch: [(projected_samples(t), a, b) for t, a, b in rows]
                      for ch, rows in expected_edges.items()}
    edge_matches = expected_edges == returned_edges
    mismatches = []
    for ch in range(8):
        expected = [(projected_samples(mdx_tick(e.vgmticks)), e.state)
                    for e in source.events if e.ch == ch]
        returned = [(e.vgmticks, e.state) for e in actual.events if e.ch == ch]
        boundaries = sorted({t for t, _ in expected} | {t for t, _ in returned})
        i = j = 0; ref = act = None
        for tick in boundaries:
            while i < len(expected) and expected[i][0] <= tick:
                ref = expected[i][1]; i += 1
            while j < len(returned) and returned[j][0] <= tick:
                act = returned[j][1]; j += 1
            if ref is None:
                continue
            if act is None:
                mismatches.append(f'ch{ch}, sample {tick}, absent state'); continue
            a, b = asdict(ref), asdict(act)
            # Shared register 0x19 has two latches; its most recent selector is
            # still retained and compared along with decoded AMD and PMD.
            for field in ('channel_registers', 'shared_registers'):
                known, observed = dict(a.pop(field)), dict(b.pop(field))
                for reg, value in known.items():
                    if observed.get(reg) != value:
                        mismatches.append(f'ch{ch}, sample {tick}, register {reg}')
            mismatches.extend(f'ch{ch}, sample {tick}, {path}' for path in _known_differences(a, b))
    counts_a, counts_b = key_counts(source), key_counts(actual)
    report = dict(comparison='hybrid_effective_state', initialization_prefix_matches=prefix_ok,
                  source_controls=len(projection.writes), returned_controls=max(0, len(raw)-len(initialization)),
                  key_edge_sequence_matches=edge_matches, known_state_mismatches=len(mismatches),
                  first_state_mismatches=mismatches[:10],
                  source_end_vgmticks=projection.source_end_vgmticks,
                  returned_end_vgmticks=actual.source_end_vgmticks,
                  max_abs_projected_timing_error_samples=abs(actual.source_end_vgmticks-projection.end_projected_vgmticks),
                  max_abs_source_timing_error_samples=projection.timing_report()['max_abs_timing_error_samples'])
    for label, key in [('channel_attacks', 'channel_attack_events'),
                       ('operator_keyons', 'operator_keyons'), ('operator_keyoffs', 'operator_keyoffs')]:
        report[f'source_{label}'], report[f'returned_{label}'] = counts_a[key], counts_b[key]
        field = 'rising_mask' if label != 'operator_keyoffs' else 'falling_mask'
        per_ch = lambda analysis: [sum(bool(getattr(e, field)) if label == 'channel_attacks'
                                      else getattr(e, field).bit_count() for e in analysis.events if e.ch == ch)
                                  for ch in range(8)]
        left, right = per_ch(source), per_ch(actual)
        report[f'missing_{label}'] = sum(max(0, a-b) for a, b in zip(left, right))
        report[f'extra_{label}'] = sum(max(0, b-a) for a, b in zip(left, right))
    report['passed'] = (prefix_ok and edge_matches and not mismatches
                        and report['max_abs_projected_timing_error_samples'] == 0
                        and report['max_abs_source_timing_error_samples'] <= 6)
    return report
