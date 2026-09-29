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


def render(segments, voice_csv_path=None, raw_ticks=False, dump_path=None):

    from melody_patterns import analyze
    from melody_loops import project, dump_projection
    from performed_patterns import Unit, compress, dump_units
    from types import SimpleNamespace
    performed = {}
    analysis = analyze(segments, "opll", voice_csv_path)
    before_lines, loop_report = [], []
    updates = []
    if voice_csv_path:
        with open(voice_csv_path, newline='') as stream:
            for row in csv.DictReader(stream):
                if row['#type'] == 'patch':
                    updates.append((int(row['ticks']), bytes.fromhex(row['patch_hex'])))
    times = [tick for tick, _ in updates]
    patches, lines, evidence = {}, [], []
    for ch in range(6):
        body, current, cursor = [], {}, 0
        boundaries = {}
        sounding = False
        for index, seg in enumerate(segments.get(ch, ())):
            boundaries[index] = len(body)
            length = seg.tick_end - seg.tick_start
            if length <= 0:
                continue
            if seg.tick_start > cursor:
                body.append(length_tokens('r', seg.tick_start - cursor, raw_ticks))
            cursor = seg.tick_end
            octave, note = target_note(seg.fnum, seg.block)
            if not seg.keyon or not seg.fnum or seg.vol == 15 or note == 'r':
                body.append(length_tokens('r', length, raw_ticks))
                continue
            sounding = True
            patch_hex = ''
            if seg.inst:
                voice = seg.inst - 1  # MGSDRV ROM instruments are @0..@14.
            else:
                position = bisect_right(times, seg.tick_start) - 1
                patch = updates[position][1] if position >= 0 else bytes(8)
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
            body.append(length_tokens(note, length, raw_ticks))
            evidence.append((ch, index, seg.tick_start, seg.tick_end, seg.inst,
                             voice, patch_hex, note, octave, 15-seg.vol))
        boundaries[len(segments.get(ch, ()))] = len(body)
        if sounding:
            before_lines.append(track_id_to_mgsdrv(ch + 9) + ' ' + ' '.join(body))
            items = analysis[ch][0]
            units = [Unit(i, i + 1, 'note' if segments[ch][i].keyon else 'rest',
                          item.signature()) for i, item in enumerate(items)]
            commands = [' '.join(body[boundaries[i]:boundaries[i + 1]]) for i in range(len(items))]
            performed_text, hierarchy = compress(units, commands)
            notes = [SimpleNamespace(start=item.tick, length=item.duration,
                                     segment_indices=[i]) for i, item in enumerate(items)]
            performed[ch] = (notes, units, hierarchy)
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
    header = ['#tempo 75' if raw_ticks else '#tempo 225', '#alloc 9=0']
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
                             'target_voice', 'patch_hex', 'note', 'octave', 'volume'))
            writer.writerows(evidence)
    dump_units(dump_path, performed)
    result = '\n'.join(header + lines) + '\n'
    dump_projection(dump_path, '\n'.join(header + before_lines) + '\n', result, loop_report)
    return result
