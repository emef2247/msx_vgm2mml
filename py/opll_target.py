"""MGSDRV melodic projection with distinct ROM/user voices and tied lengths."""
import csv
import math
from bisect import bisect_right
from mml_envelopes import length_tokens
from mml_utils import track_id_to_mgsdrv, compact_state_token


def decode_patch(patch):
    """Decode YM2413 registers 00..07 into TL/FB and MGSDRV operator fields."""
    if len(patch) != 8:
        raise ValueError('An OPLL user patch must contain eight bytes')
    operators = []
    for carrier in (0, 1):
        control = patch[carrier]
        rate = patch[4 + carrier]
        release = patch[6 + carrier]
        operators.extend((rate >> 4, rate & 15, release >> 4, release & 15,
                          patch[2 + carrier] >> 6, control & 15,
                          control >> 7, (control >> 6) & 1,
                          (control >> 5) & 1, (control >> 4) & 1,
                          (patch[3] >> (3 + carrier)) & 1))
    return (patch[2] & 63, patch[3] & 7, *operators)


def target_note(fnum, block):
    """MGSDRV o4 uses OPLL block 3 (one above scientific octave naming)."""
    if not fnum:
        return 1, 'r'
    frequency = 49716.0 * fnum * (1 << block) / (1 << 19)
    midi = round(69 + 12 * math.log2(frequency / 440.0))
    return max(1, min(8, midi // 12)), ('c', 'c+', 'd', 'd+', 'e', 'f',
                                                   'f+', 'g', 'g+', 'a', 'a+', 'b')[midi % 12]




# Authored MGSC/libkss chromatic probe; stable writes after the key/high byte.
MGSDRV_FNUM = (172, 182, 194, 205, 217, 230, 244, 258, 273, 290, 307, 325)
NOTE_NAMES = ('c', 'c+', 'd', 'd+', 'e', 'f', 'f+', 'g', 'g+', 'a', 'a+', 'b')


def note_pitch(octave, note):
    """Encode the accepted MML semitone in MGSDRV's measured OPLL profile."""
    if note == 'r':
        return 0, 0
    return MGSDRV_FNUM[NOTE_NAMES.index(note)], max(0, min(7, int(octave) - 1))

def read_patch_updates(voice_csv_path):
    """Read ordered native global patch snapshots without allocating target voices."""
    updates = []
    if voice_csv_path:
        with open(voice_csv_path, newline='') as stream:
            updates = [(int(row['ticks']), bytes.fromhex(row['patch_hex']))
                       for row in csv.DictReader(stream) if row['#type'] == 'patch']
    return updates


def segment_decisions(rows, updates=()):
    """Shared pure melodic pitch, patch, attack and continuation decisions."""
    from types import SimpleNamespace
    times = [tick for tick, _ in updates]
    previous_key = False
    result = []
    for index, seg in enumerate(rows):
        edge = bool(getattr(seg, 'key_on_edge', seg.keyon and not previous_key))
        previous_key = bool(seg.keyon)
        octave, note = target_note(seg.fnum, seg.block)
        position = bisect_right(times, seg.tick_start) - 1
        patch = (updates[position][1] if position >= 0 else bytes(8)) if not seg.inst else None
        end, later_key, continuation = seg.tick_end, bool(seg.keyon), False
        for later in rows[index + 1:]:
            later_edge = bool(getattr(later, 'key_on_edge', later.keyon and not later_key))
            if not later.keyon or later_edge or later.tick_start != end:
                break
            later_key = bool(later.keyon)
            if later.tick_end > later.tick_start:
                continuation = bool(later.fnum)
                break
        result.append(SimpleNamespace(edge=edge, octave=octave, note=note,
            patch=patch, continuation=continuation, instrument=int(seg.inst), volume=15-int(seg.vol)))
    return tuple(result)

def render(segments, voice_csv_path=None, raw_ticks=False, dump_path=None, *, source_loops=False,
           source_strategy='retained', num_channels=6,score_guided=False,score_timing=None):

    from melody_patterns import analyze
    from melody_loops import project, dump_projection
    from performed_patterns import Unit, compress, dump_units
    from opll_note_units import group_notes
    performed = {}
    before_lines, loop_report = [], []
    updates = read_patch_updates(voice_csv_path)
    analysis = analyze(segments, "opll", voice_csv_path)
    source_plans = {}
    if source_loops and source_loops != 'after':
        from opll_inner_loops import OpllLoopPlan
        for ch in range(num_channels):
            if ch in analysis:
                members, source_units = group_notes(segments[ch], analysis[ch][0])
                plan = OpllLoopPlan.build(members, source_units, analysis[ch][0], source_strategy,score_guided)
                source_plans[ch] = (plan, members, source_units)
    times = [tick for tick, _ in updates]
    patches, lines, evidence = {}, [], []
    for ch in range(num_channels):
        body, current, cursor = [], {}, 0
        boundaries = {}
        sounding = False
        active, pending_edge, previous_key = False, False, False
        score_cursor=0
        rows = segments.get(ch, ())
        decisions = segment_decisions(rows, updates)
        schedule={}
        if score_timing and rows:
            # Truncate a complete keyed unit once. Internal register slices
            # neither define independent short notes nor each lose a residue.
            members,_=group_notes(rows,analysis[ch][0])
            for member in members:
                begin,end=score_timing.span(member.start,member.start+member.length,
                    rest=not rows[member.segment_indices[0]].keyon)
                positive=[]
                for index in member.segment_indices:
                    segment=rows[index]
                    start=max(begin,min(end,score_timing.position(segment.tick_start)))
                    stop=max(start,min(end,score_timing.position(segment.tick_end)))
                    schedule[index]=(start,stop)
                    if stop>start:positive.append(index)
                for index in positive:decisions[index].continuation=index!=positive[-1]
        for index, seg in enumerate(rows):
            boundaries[index] = len(body)
            decision = decisions[index]
            edge = decision.edge
            pending_edge |= edge
            previous_key = bool(seg.keyon)
            if not seg.keyon:
                active = False
            length = seg.tick_end - seg.tick_start
            if length <= 0:
                continue
            if score_timing:
                start,stop=schedule[index]
                if stop<=start:continue
                if start<score_cursor:raise ValueError('Score OPLL intervals overlap after projection')
                if start>score_cursor:
                    body.append(length_tokens('r',start-score_cursor,True));active=False
                length=stop-start;score_cursor=stop
            elif seg.tick_start > cursor:
                body.append(length_tokens('r', seg.tick_start - cursor, raw_ticks))
                active = False
            cursor = seg.tick_end
            octave, note = decision.octave, decision.note
            if not seg.keyon or not seg.fnum or note == 'r':
                body.append(length_tokens('r', length,True if score_timing else raw_ticks))
                active, pending_edge = False, False
                continue
            sounding = True
            if active and not pending_edge:
                body.append("&")
            active, pending_edge = True, False
            patch_hex = ''
            if seg.inst:
                voice = seg.inst - 1  # MGSDRV ROM instruments are @0..@14.
            else:
                patch = decision.patch
                if patch not in patches:
                    voice = 16 + len(patches)
                    if voice > 255:
                        raise ValueError('Too many OPLL user voices for MGSDRV')
                    patches[patch] = voice
                voice = patches[patch]
                patch_hex = patch.hex()
            for key, value, prefix in (('voice', voice, '@'), ('volume', 15-seg.vol, 'v'),
                                        ('octave', octave, 'o')):
                if current.get(key) != value:
                    body.append(compact_state_token(prefix, value, current.get(key)))
                    current[key] = value
            # q0 preserves key-on across a pitch/state change; & alone only
            # prevented reattack for equal pitches in the MGSC/libkss probe.
            gate = 0 if decision.continuation else 8
            if current.get('gate', 8) != gate:
                body.append(f'q{gate}')
                current['gate'] = gate
            body.append(length_tokens(note, length,True if score_timing else raw_ticks))
            evidence.append((ch, index, seg.tick_start, seg.tick_end, seg.inst,
                             voice, patch_hex, note, octave, 15-seg.vol,
                             seg.keyon, int(edge), getattr(seg, 'onset', 0)))
        boundaries[len(segments.get(ch, ()))] = len(body)
        if sounding:
            before_lines.append(track_id_to_mgsdrv(ch + 9) + ' ' + ' '.join(body))
            if source_loops:
                if source_loops == 'after':
                    from opll_inner_loops import OpllLoopPlan
                    members, source_units = group_notes(segments[ch], analysis[ch][0])
                    plan = OpllLoopPlan.build(members, source_units, analysis[ch][0], source_strategy,score_guided)
                    source_plans[ch] = (plan, members, source_units)
                plan, members, source_units = source_plans[ch]
                text, hierarchy = plan.render(body, boundaries)
                performed[ch] = (members, source_units,
                                 [{k: v for k, v in row.items() if k != 'emitted_repeats'} for row in hierarchy])
                lines.append(track_id_to_mgsdrv(ch + 9) + ' ' + text)
                if dump_path:
                    plan.dump(str(dump_path).replace('.target_notes.csv', f'.ch{ch}.source_loops.csv'),
                              [n.segment_indices for n in members], hierarchy)
                continue
            items = analysis[ch][0]
            units = [Unit(i, i + 1, 'note' if segments[ch][i].keyon else 'rest',
                          item.signature()) for i, item in enumerate(items)]
            commands = [' '.join(body[boundaries[i]:boundaries[i + 1]]) for i in range(len(items))]
            legacy_performed_text, _ = compress(units, commands)
            note_members, note_units = group_notes(segments[ch], items)
            note_commands = [' '.join(body[boundaries[n.segment_indices[0]]:
                                           boundaries[n.segment_indices[-1] + 1]])
                             for n in note_members]
            performed_text, hierarchy = compress(note_units, note_commands)
            performed[ch] = (note_members, note_units, hierarchy)
            if len(legacy_performed_text) < len(performed_text):
                performed_text = legacy_performed_text
                for entry in hierarchy:
                    entry['status'] = 'legacy_projection_selected'
            body, report = project(body, boundaries, analysis[ch], ch)
            selected = len(performed_text) <= len(' '.join(body))
            if selected:
                body = [performed_text]
                report = [(*r[:-1], 'performed_projection_selected') for r in report]
            else:
                for entry in hierarchy:
                    entry['status'] = 'legacy_projection_selected'
            loop_report.extend(report)
            lines.append(track_id_to_mgsdrv(ch + 9) + ' ' + ' '.join(body))
    header = [f'#tempo {score_timing.tempo}' if score_timing else '#tempo 75' if raw_ticks else '#tempo 225', '#alloc 9=0']
    for patch, voice in patches.items():
        values = decode_patch(patch)
        header.extend((f'@{voice} = {{', '; TL FB', f'{values[0]}, {values[1]},',
                       '; AR DR SL RR KL MT AM VB EG KR WF',
                       ', '.join(map(str, values[2:13])) + ',',
                       ', '.join(map(str, values[13:])) + ' }'))
    if dump_path:
        with open(dump_path, 'w', newline='', encoding='utf-8') as stream:
            writer = csv.writer(stream)
            writer.writerow(('ch', 'segment_index', 'tick_start', 'tick_end', 'source_inst',
                             'target_voice', 'patch_hex', 'note', 'octave', 'volume',
                             'source_keyon', 'key_on_edge', 'onset'))
            writer.writerows(evidence)
    dump_units(dump_path, performed)
    if dump_path and source_loops:
        from opll_inner_loops import annotate_segments
        annotate_segments(str(dump_path).replace('.target_notes.csv', '.segments.csv'),
                          {ch: value[0] for ch, value in source_plans.items()})
    result = '\n'.join(header + lines) + '\n'
    dump_projection(dump_path, '\n'.join(header + before_lines) + '\n', result, loop_report)
    return result
