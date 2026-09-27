"""MGSDRV rendering of SCC Segments; CSV analysis lives in scc.py."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from mml_utils import (estimate_mml_used, estimate_alloc, ticks_to_mml_length,
                       get_mgs_note_token, get_mgs_note_token_pct)
from scc import build_segments

CH_OFFSET = 4

def _generate_simple_raw_mml(temp_buf3, ch_list, file_name_body, waveforms):
    """Generate simple raw-tick MML text (pass3.simple.mml variant).

    Uses ``{scale}%{N}`` tick notation and ``#tempo 75``.  No ``l64``
    default-length directive is emitted; the octave is declared as an
    inline ``o{N}`` token whenever it changes.
    """
    mml_buffer = {}

    for ch in ch_list:
        mml_buffer[ch] = []
        note_cnt  = 0
        l_cnt     = 0
        o_stamp   = 0
        v_stamp   = 0
        at_stamp  = -1
        is_first_group = True
        mml       = ''

        ch_num = ch + CH_OFFSET
        mml_buffer[ch].append(f'\n\n;ch{ch_num} start')

        for segment in temp_buf3[ch]:
            type_      = segment.ev_type
            l          = segment.l
            v          = segment.volume
            o          = segment.octave
            scale      = segment.scale
            en         = segment.enabled
            wtb_index  = segment.waveform_id

            if l > 0:
                length = l
                while length > 0:
                    ltmp = min(length, 255)

                    if note_cnt == 0:
                        if is_first_group:
                            mml = f'\n{ch_num} @{wtb_index} v{v}'
                            at_stamp = wtb_index
                            v_stamp  = v
                            is_first_group = False
                        else:
                            mml = f'\n{ch_num}'
                            if wtb_index != at_stamp:
                                mml += f' @{wtb_index}'
                                at_stamp = wtb_index
                            if v != v_stamp:
                                mml += f' v{v}'
                                v_stamp = v

                    if v != v_stamp and note_cnt != 0:
                        mml += f' v{v}'

                    if wtb_index != at_stamp:
                        mml += f' @{wtb_index}'
                        at_stamp = wtb_index
                    if o != o_stamp:
                        mml += f' o{o}'

                    mml += f' {scale}%{ltmp} '
                    l_cnt += ltmp

                    length -= ltmp

                note_cnt += 1
                if note_cnt == 8 or (type_ == 'enBit' and en == 0) or v == 0:
                    mml_buffer[ch].append(mml)
                    mml = ''
                    mml_buffer[ch].append(f'\n;tick count: {l_cnt}\n')
                    note_cnt = 0

                o_stamp = o
                v_stamp = v

        if mml:
            mml_buffer[ch].append(mml)

        mml_buffer[ch].append(f'\n;ch{ch_num} end: tick count: {l_cnt}\n')

    # --- Build final MML text ---
    lines = []
    lines.append(';[name=scc lpf=1]')
    lines.append('#opll_mode 1')
    lines.append('#tempo 75')
    lines.append(f'#title {{ "{file_name_body}"}}')
    for ch in ch_list:
        ch_num = ch + CH_OFFSET
        used = estimate_mml_used(mml_buffer[ch])
        alloc = estimate_alloc(used)
        lines.append(f'#alloc {ch_num}={alloc}')
    lines.append('')

    for i, wbytes in enumerate(waveforms):
        lines.append(f'@s{i:02d} = {{{wbytes}}}')
    lines.append('')
    lines.append('')

    header_text = '\n'.join(lines)

    body_parts = [header_text]
    for ch in ch_list:
        for item in mml_buffer[ch]:
            body_parts.append(item)

    result = ''.join(body_parts)
    if not result.endswith('\n'):
        result += '\n'
    return result


def _generate_mml(temp_buf3, ch_list, file_name_body, waveforms):
    """Generate MML text from pass-3 data."""
    mml_buffer = {}

    for ch in ch_list:
        mml_buffer[ch] = []
        note_cnt  = 0
        l_cnt     = 0
        o_stamp   = 0
        v_stamp   = 0
        at_stamp  = -1
        is_first_group = True
        mml       = ''

        ch_num = ch + CH_OFFSET
        mml_buffer[ch].append(f'\n\n;ch{ch_num} start')

        for segment in temp_buf3[ch]:
            type_      = segment.ev_type
            l          = segment.l
            v          = segment.volume
            o          = segment.octave
            scale      = segment.scale
            en         = segment.enabled
            wtb_index  = segment.waveform_id

            if l > 0:
                length = l
                while length > 0:
                    ltmp = min(length, 255)

                    if note_cnt == 0:
                        if is_first_group:
                            mml = f'\n{ch_num} @{wtb_index} v{v} o{o} l64'
                            at_stamp = wtb_index
                            v_stamp  = v
                            o_stamp  = o
                            is_first_group = False
                        else:
                            mml = f'\n{ch_num}'
                            if wtb_index != at_stamp:
                                mml += f' @{wtb_index}'
                                at_stamp = wtb_index
                            if v != v_stamp:
                                mml += f' v{v}'
                                v_stamp = v

                    if v != v_stamp and note_cnt != 0:
                        mml += f' v{v}'

                    if wtb_index != at_stamp:
                        mml += f' @{wtb_index}'
                        at_stamp = wtb_index
                    if o != o_stamp:
                        mml += f' o{o}'

                    mml += f' {ticks_to_mml_length(ltmp, scale)} '
                    l_cnt += ltmp

                    length -= ltmp

                note_cnt += 1
                if note_cnt == 8 or (type_ == 'enBit' and en == 0) or v == 0:
                    mml_buffer[ch].append(mml)
                    mml = ''
                    mml_buffer[ch].append(f'\n;tick count: {l_cnt}\n')
                    note_cnt = 0

                o_stamp = o
                v_stamp = v

        if mml:
            mml_buffer[ch].append(mml)

        mml_buffer[ch].append(f'\n;ch{ch_num} end: tick count: {l_cnt}\n')

    # --- Build final MML text ---
    lines = []
    lines.append(f';[name=scc lpf=1]')
    lines.append('#opll_mode 1')
    lines.append('#tempo 225')
    lines.append(f'#title {{ "{file_name_body}"}}')
    for ch in ch_list:
        ch_num = ch + CH_OFFSET
        used = estimate_mml_used(mml_buffer[ch])
        alloc = estimate_alloc(used)
        lines.append(f'#alloc {ch_num}={alloc}')
    lines.append('')

    for i, wbytes in enumerate(waveforms):
        lines.append(f'@s{i:02d} = {{{wbytes}}}')
    lines.append('')
    lines.append('')

    header_text = '\n'.join(lines)

    body_parts = [header_text]
    for ch in ch_list:
        for item in mml_buffer[ch]:
            body_parts.append(item)

    result = ''.join(body_parts)
    if not result.endswith('\n'):
        result += '\n'
    return result


def _update_and_optimize_cnt_scc(src_buf, ch_list):
    """Compress only adjacent, identical audible states; never cross a write."""
    result = {ch: [] for ch in ch_list}
    for ch in ch_list:
        previous_key = None
        for segment in src_buf[ch]:
            key = (segment.l, segment.tone_period, segment.octave, segment.scale,
                   segment.volume, segment.enabled, segment.waveform_id)
            if segment.l > 0 and key == previous_key:
                previous, count = result[ch][-1]
                result[ch][-1] = (previous, count + 1)
            else:
                result[ch].append((segment, 1))
            previous_key = key if segment.l > 0 else None
    return result


def _generate_mml_mgs(buf3, ch_list, file_name_body, waveforms, use_cnt=False, use_pct=False):
    """Generate MGS delta-token MML text from pass-3 SCC data.

    Implements the Tcl ``generate_mml_MGS`` behaviour for SCC:
    * Group headers: ``ch_num @wtb v{v}`` on the first group (with ``o{o} l64``
      unless *use_pct* is True, in which case ``l64`` is omitted),
      subsequent groups: ``ch_num [@wtb] v{v}`` (absolute volume, no octave).
    * Within groups: ``<`` / ``>`` for small octave deltas, ``(`` / ``)`` for
      small volume deltas; ``oN`` / ``vN`` for larger deltas (abs > 3).
    * When ``use_cnt`` is True and ``cnt > 1`` (after
      :func:`_update_and_optimize_cnt_scc`), the note body is wrapped in
      ``[...]cnt`` with the octave prefix outside.  When ``use_cnt`` is False
      (default, for simple.MGS.mml) cnt is forced to 1 (no wrapping).
    * When ``use_pct`` is True, note lengths are encoded as ``{scale}%{N}``
      raw tick tokens and ``#tempo 75`` is used (MGS_pct variant).
    """
    note_token_fn = get_mgs_note_token_pct if use_pct else get_mgs_note_token
    tempo = 75 if use_pct else 225
    mml_buffer = {ch: [] for ch in ch_list}

    for ch in ch_list:
        note_cnt = 0
        l_cnt = 0
        o_stamp = 0
        v_stamp = 0
        at_stamp = -1
        is_first_group = True
        mml = ''

        ch_num = ch + CH_OFFSET
        mml_buffer[ch].append(f'\n\n;ch{ch_num} start')

        for segment, repeat_count in buf3[ch]:
            type_ = segment.ev_type
            l = segment.l
            v = segment.volume
            o = segment.octave
            scale = segment.scale
            en = segment.enabled
            wtb_index = segment.waveform_id
            v_diff = segment.volume_delta
            if use_cnt:
                cnt = repeat_count
                if cnt < 1:
                    cnt = 1
            else:
                cnt = 1

            if l > 0:
                length = l
                while length > 0:
                    ltmp = min(length, 255)

                    if note_cnt == 0:
                        if is_first_group:
                            if use_pct:
                                mml = f'\n{ch_num} @{wtb_index} v{v} o{o}'
                            else:
                                mml = f'\n{ch_num} @{wtb_index} v{v} o{o} l64'
                            at_stamp = wtb_index
                            v_stamp = v
                            o_stamp = o
                            is_first_group = False
                        else:
                            mml = f'\n{ch_num}'
                            if wtb_index != at_stamp:
                                mml += f' @{wtb_index}'
                                at_stamp = wtb_index
                            mml += f' v{v}'
                            v_stamp = v

                    if wtb_index != at_stamp:
                        mml += f' @{wtb_index}'
                        at_stamp = wtb_index
                    if o != o_stamp:
                        mml += f' o{o}'
                        o_stamp = o
                    if v != v_stamp:
                        mml += f' v{v}'
                        v_stamp = v
                    note = note_token_fn(
                        ltmp, v, 0, scale, cnt, o, o, v)
                    mml += ' ' + note
                    l_cnt += ltmp * cnt

                    length -= ltmp

                note_cnt += 1
                if note_cnt == 8 or (type_ == 'enBit' and en == 0) or v == 0:
                    mml_buffer[ch].append(mml)
                    mml = ''
                    mml_buffer[ch].append(f'\n;tick count: {l_cnt}\n')
                    note_cnt = 0

                o_stamp = o
                v_stamp = v

        if mml:
            mml_buffer[ch].append(mml)

        mml_buffer[ch].append(f'\n;ch{ch_num} end: tick count: {l_cnt}\n')

    # --- Build final MML text ---
    lines = []
    lines.append(';[name=scc lpf=1]')
    lines.append('#opll_mode 1')
    lines.append(f'#tempo {tempo}')
    lines.append(f'#title {{ "{file_name_body}"}}')
    for ch in ch_list:
        ch_num = ch + CH_OFFSET
        used = estimate_mml_used(mml_buffer[ch])
        alloc = estimate_alloc(used)
        lines.append(f'#alloc {ch_num}={alloc}')
    lines.append('')

    for i, wbytes in enumerate(waveforms):
        lines.append(f'@s{i:02d} = {{{wbytes}}}')
    lines.append('')
    lines.append('')

    header_text = '\n'.join(lines)

    body_parts = [header_text]
    for ch in ch_list:
        for item in mml_buffer[ch]:
            body_parts.append(item)

    result = ''.join(body_parts)
    if not result.endswith('\n'):
        result += '\n'
    return result


def write_scc_mml(analysis, output_dir, stem, debug=True, raw_ticks=False):
    """Render Segments and their waveform bank without reading event CSVs."""
    os.makedirs(output_dir, exist_ok=True)
    segments, waveforms = analysis.segments, analysis.waveforms
    ch_list = list(segments)
    file_name_body = stem
    # ---- cnt-optimised buffer (needed for compress variants) ----
    compress_buf3 = _update_and_optimize_cnt_scc(segments, ch_list)

    # ---- pass3.compress.MGS_pct.mml – always produced for raw-tick mode ----
    compress_mgs_pct_text = _generate_mml_mgs(
        compress_buf3, ch_list, file_name_body, waveforms, use_cnt=True, use_pct=True)
    compress_mgs_pct_path = os.path.join(output_dir, f'{file_name_body}.scc.pass3.compress.MGS_pct.mml')
    with open(compress_mgs_pct_path, 'w', newline='\n') as fh:
        fh.write(compress_mgs_pct_text)

    # ---- pass3.compress.MGS.mml – always produced for default divisor mode ----
    compress_mgs_text = _generate_mml_mgs(
        compress_buf3, ch_list, file_name_body, waveforms, use_cnt=True)
    compress_path = os.path.join(output_dir, f'{file_name_body}.scc.pass3.compress.MGS.mml')
    with open(compress_path, 'w', newline='\n') as fh:
        fh.write(compress_mgs_text)

    if not debug:
        return compress_mgs_pct_path if raw_ticks else compress_path

    simple_segments = {ch: [(seg, seg.volume_run_count) for seg in rows] for ch, rows in segments.items()}

    # ---- debug-only MML variants ----

    # Primary .scc.mml
    mml_text = _generate_mml(segments, ch_list, file_name_body, waveforms)
    mml_path = os.path.join(output_dir, f'{file_name_body}.scc.mml')
    with open(mml_path, 'w', newline='\n') as fh:
        fh.write(mml_text)

    # pass3.simple.mml – raw tick (%N) notation, #tempo 75
    simple_raw_text = _generate_simple_raw_mml(
        segments, ch_list, file_name_body, waveforms)
    simple_raw_path = os.path.join(output_dir, f'{file_name_body}.scc.pass3.simple.mml')
    with open(simple_raw_path, 'w', newline='\n') as fh:
        fh.write(simple_raw_text)

    # pass3.simple.MGS.mml – MGS delta-token notation, #tempo 225
    simple_mgs_text = _generate_mml_mgs(
        simple_segments,
        ch_list, file_name_body, waveforms, use_cnt=False)
    simple_mgs_path = os.path.join(output_dir, f'{file_name_body}.scc.pass3.simple.MGS.mml')
    with open(simple_mgs_path, 'w', newline='\n') as fh:
        fh.write(simple_mgs_text)

    # pass3.simple.MGS_pct.mml – MGS delta-token, raw tick (%) lengths, #tempo 75
    simple_mgs_pct_text = _generate_mml_mgs(
        simple_segments,
        ch_list, file_name_body, waveforms, use_cnt=False, use_pct=True)
    simple_mgs_pct_path = os.path.join(output_dir, f'{file_name_body}.scc.pass3.simple.MGS_pct.mml')
    with open(simple_mgs_pct_path, 'w', newline='\n') as fh:
        fh.write(simple_mgs_pct_text)

    return mml_path


def process_scc_csv(input_path, output_dir, dump_passes=True, stem=None,
                    debug=True, raw_ticks=False, envelope_bank=None):
    """Compatibility entry point: CSV -> Segments -> MGSDRV MML."""
    analysis = build_segments(input_path, output_dir, dump_passes, stem)
    name = stem if stem is not None else os.path.splitext(os.path.splitext(os.path.basename(input_path))[0])[0]
    result = write_scc_mml(analysis, output_dir, name, debug, raw_ticks)
    if envelope_bank is not None:
        from mml_envelopes import render
        target = render(analysis.segments, 'scc', envelope_bank, raw_ticks, analysis.waveforms,
                        dump_path=os.path.join(output_dir, f'{name}.scc.target_notes.csv') if dump_passes else None)
        with open(os.path.join(output_dir, f'{name}.scc.target.mml'), 'w', newline='\n') as fh:
            fh.write(target)
    return result


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(f"Usage: python {sys.argv[0]} <log_scc_csv> [output_dir]")
        sys.exit(1)

    input_csv = sys.argv[1]
    if len(sys.argv) > 2:
        out_dir = sys.argv[2]
    else:
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        stem = os.path.splitext(os.path.splitext(os.path.basename(input_csv))[0])[0]
        out_dir = os.path.join(script_dir, 'outputs', stem)

    result = process_scc_csv(input_csv, out_dir)
    print(f"Wrote {result}")
