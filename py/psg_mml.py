"""MGSDRV rendering of PSG Segments; CSV analysis lives in psg.py."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from mml_utils import (estimate_mml_used, estimate_alloc, ticks_to_mml_length,
                       get_mgs_note_token, get_mgs_note_token_pct)
from psg import build_segments


def _envelope_mml_period(segment):
    # Preserve the existing MGSDRV projection, separate from source period.
    return int(143.03493 * segment.envelope_period)


def _build_psg_mml_buffer(work_buffer1, raw_ticks=False):
    """Build per-channel MML buffers from work_buffer1.

    When *raw_ticks* is True, emit ``{scale}%{N}`` notation and omit
    the ``l64`` default-length directive (pass3.simple.mml style).
    When False (default), emit standard divisor notation with ``l64``
    (pass3.simple.MGS.mml style, #tempo 225).
    """
    ch_list = list(work_buffer1)
    mml_buffer = {}
    for ch in ch_list:
        mml_buffer[ch] = []

    ch_offset = 1  # PSG channels displayed as 1-based

    for ch in ch_list:
        note_cnt = 0
        mml = ""
        l_cnt = 0
        o_stamp = 0
        v_stamp = 0
        mode_stamp = -1   # tracks previous mode so we can flush on mode change
        is_first_group = True

        ch_start = f"\n\n;ch{ch + ch_offset} start"
        mml_buffer[ch].append(ch_start)

        for segment in work_buffer1[ch]:
            type_ = segment.ev_type
            l = segment.l
            v = segment.volume
            f = segment.tone_period
            o = segment.octave
            scale = segment.scale
            mode = segment.mode

            noise_freq = segment.noise_period
            hw_env_on = segment.envelope_enabled
            hw_env_period = _envelope_mml_period(segment)
            hw_env_shape = segment.envelope_shape

            if l > 0:
                length = l

                # Flush current MML group when mode changes mid-group so
                # that the new header reflects the updated mode/noise/env.
                if note_cnt > 0 and mode != mode_stamp:
                    mml_buffer[ch].append(mml)
                    mml = ""
                    mml_buffer[ch].append(f"\n;tick count: {l_cnt}\n")
                    note_cnt = 0

                if note_cnt == 0:
                    if raw_ticks:
                        # No l64; o emitted inline as needed
                        if mode == 0:
                            v = 0
                            if is_first_group:
                                mml = f"\n{ch + ch_offset} /0 v{v}"
                                is_first_group = False
                            else:
                                mml = f"\n{ch + ch_offset} /0 v{v}"
                        elif mode == 1:
                            if is_first_group:
                                mml = f"\n{ch + ch_offset} /1 s{hw_env_shape} m{hw_env_period} v{v}"
                                is_first_group = False
                            else:
                                mml = f"\n{ch + ch_offset} /1 s{hw_env_shape} m{hw_env_period} v{v}"
                        elif mode == 2:
                            if is_first_group:
                                mml = f"\n{ch + ch_offset} /2 s{hw_env_shape} m{hw_env_period} n{noise_freq} v{v}"
                                is_first_group = False
                            else:
                                mml = f"\n{ch + ch_offset} /2 s{hw_env_shape} m{hw_env_period} n{noise_freq} v{v}"
                        elif mode == 3:
                            if is_first_group:
                                mml = f"\n{ch + ch_offset} /3 s{hw_env_shape} m{hw_env_period} n{noise_freq} v{v}"
                                is_first_group = False
                            else:
                                mml = f"\n{ch + ch_offset} /3 s{hw_env_shape} m{hw_env_period} n{noise_freq} v{v}"
                    else:
                        if mode == 0:
                            v = 0
                            if is_first_group:
                                mml = f"\n{ch + ch_offset} /0 v{v} o{o} l64"
                                o_stamp = o
                                is_first_group = False
                            else:
                                mml = f"\n{ch + ch_offset} /0 v{v}"
                        elif mode == 1:
                            if is_first_group:
                                mml = f"\n{ch + ch_offset} /1 s{hw_env_shape} m{hw_env_period} v{v} o{o} l64"
                                o_stamp = o
                                is_first_group = False
                            else:
                                mml = f"\n{ch + ch_offset} /1 s{hw_env_shape} m{hw_env_period} v{v}"
                        elif mode == 2:
                            if is_first_group:
                                mml = f"\n{ch + ch_offset} /2 s{hw_env_shape} m{hw_env_period} n{noise_freq} v{v} o{o} l64"
                                o_stamp = o
                                is_first_group = False
                            else:
                                mml = f"\n{ch + ch_offset} /2 s{hw_env_shape} m{hw_env_period} n{noise_freq} v{v}"
                        elif mode == 3:
                            if is_first_group:
                                mml = f"\n{ch + ch_offset} /3 s{hw_env_shape} m{hw_env_period} n{noise_freq} v{v} o{o} l64"
                                o_stamp = o
                                is_first_group = False
                            else:
                                mml = f"\n{ch + ch_offset} /3 s{hw_env_shape} m{hw_env_period} n{noise_freq} v{v}"

                while length > 0:
                    ltmp = min(length, 255)

                    if type_ in ('mode', 'fCA', 'fCB', 'aVC', 'wNC', 'ePL', 'evM', 'evS'):
                        if mode == 0:
                            v = 0
                            scale = 'r'
                        if v != v_stamp and note_cnt != 0:
                            mml += f" v{v}"
                        if o != o_stamp:
                            mml += f" o{o}"
                        if raw_ticks:
                            mml += f" {scale}%{ltmp}"
                        else:
                            mml += f" {ticks_to_mml_length(ltmp, scale)}"
                        l_cnt += ltmp

                    length -= ltmp

                    if length >= 0:
                        mml_buffer[ch].append(mml)
                        mml = ""

                note_cnt += 1
                if note_cnt == 8 or mode == 0:
                    mml_buffer[ch].append(mml)
                    mml = ""
                    info = f"\n;tick count: {l_cnt}\n"
                    mml_buffer[ch].append(info)
                    note_cnt = 0

                o_stamp = o
                v_stamp = v
                mode_stamp = mode

        if mml:
            mml_buffer[ch].append(mml)

        info = f"\n;ch{ch + ch_offset} end: tick count: {l_cnt}\n"
        mml_buffer[ch].append(info)

    return mml_buffer

def _write_psg_mml(mml_buffer, path, title, raw_ticks=False):
    """Serialise a PSG mml_buffer to *path* with the appropriate header."""
    ch_list = list(mml_buffer)
    tempo = 75 if raw_ticks else 225
    ch_offset = 1
    with open(path, 'w', newline='\n') as fh:
        fh.write(';[name=psg lpf=1]\n')
        fh.write('#opll_mode 1\n')
        fh.write(f'#tempo {tempo}\n')
        fh.write(f'#title {{ "{title}"}}\n')
        for ch in ch_list:
            track = ch + ch_offset
            used = estimate_mml_used(mml_buffer[ch])
            alloc = estimate_alloc(used)
            fh.write(f'#alloc {track}={alloc}\n')
        fh.write('\n')
        for ch in ch_list:
            for item in mml_buffer[ch]:
                fh.write(item)

def _update_and_optimize_cnt_psg(src_buffer):
    """Re-compute cnt for truly repeating notes in the PSG work buffer.

    Port of the Tcl ``update_and_optimize_cnt`` procedure.  For each
    channel, consecutive rows of type ``fCA``, ``fCB``, or ``aVC`` where
    ``f``, ``l``, ``o``, ``vDiff``, mode, noise period, hw-envelope shape
    and hw-envelope period all match the previous segment's values, the ``cnt``
    repeat count of the previous output item is incremented.

    Returns per-channel (Segment, repeat_count) pairs. Input Segments stay intact.
    """
    ch_list = list(src_buffer)
    dst_buffer = {ch: [] for ch in ch_list}

    for ch in ch_list:
        f_stamp = None
        l_stamp = None
        o_stamp = None
        vdiff_stamp = None
        mode_stamp = None
        noise_stamp = None
        env_shape_stamp = None
        env_period_stamp = None
        cnt_stamp = 0

        for segment in src_buffer[ch]:
            type_ = segment.ev_type
            l = segment.l
            f = segment.tone_period
            o = segment.octave
            v_diff = segment.volume_delta
            mode = segment.mode
            noise_period = segment.noise_period
            hw_env_shape = segment.envelope_shape
            hw_env_period = _envelope_mml_period(segment)

            # Reset stamps on silent fCA/fCB events
            if type_ in ('fCA', 'fCB') and mode == 0:
                f_stamp = None
                l_stamp = None
                o_stamp = None
                vdiff_stamp = None
                mode_stamp = None
                noise_stamp = None
                env_shape_stamp = None
                env_period_stamp = None
                cnt_stamp = 0

            if l != 0:
                if type_ in ('fCA', 'fCB', 'aVC'):
                    if (f == f_stamp and l == l_stamp and o == o_stamp
                            and v_diff == vdiff_stamp
                            and mode == mode_stamp
                            and noise_period == noise_stamp
                            and hw_env_shape == env_shape_stamp
                            and hw_env_period == env_period_stamp):
                        # Merge into previous segment: increment its cnt
                        cnt_stamp += 1
                        dst_buffer[ch][-1] = (dst_buffer[ch][-1][0], cnt_stamp)
                        # Skip appending current segment (it is absorbed)
                    else:
                        dst_buffer[ch].append((segment, 1))
                        cnt_stamp = 1  # First occurrence is always 1
                else:
                    dst_buffer[ch].append((segment, 1))
                    cnt_stamp = 1  # First occurrence is always 1

                f_stamp = f
                l_stamp = l
                o_stamp = o
                vdiff_stamp = v_diff
                mode_stamp = mode
                noise_stamp = noise_period
                env_shape_stamp = hw_env_shape
                env_period_stamp = hw_env_period
            else:
                dst_buffer[ch].append((segment, 1))

    return dst_buffer

def _build_psg_mml_mgs_buffer(work_buf, use_cnt=False, use_pct=False):
    """Build PSG MML buffers using MGS delta-token octave/volume style.

    Implements the Tcl ``generate_mml_MGS`` behaviour:
    * Group headers include ``v{v}`` (absolute volume) and, on the very
      first group only, ``o{o} l64`` to initialise the octave register
      (``l64`` is omitted when *use_pct* is True).
    * Within each group the octave and volume are expressed using delta
      tokens (``<`` / ``>`` for octave, ``(`` / ``)`` for volume) when
      the absolute difference is ≤ 3; otherwise an absolute ``oN`` / ``vN``
      token is used.
    * When ``use_cnt`` is True and ``cnt > 1`` (after
      :func:`_update_and_optimize_cnt_psg`), the note body is wrapped in
      ``[...]cnt`` with the octave prefix placed outside the bracket
      (Tcl behaviour for compress.MGS.mml).
    * When ``use_cnt`` is False (default, for simple.MGS.mml) each segment is
      treated as a single note (cnt forced to 1, no bracket wrapping).
    * When ``use_pct`` is True, note lengths are encoded as
      ``{scale}%{N}`` raw tick tokens instead of the divisor notation
      produced by :func:`mgs_length_to_str` (MGS_pct variant).

    The ``o_stamp`` is *not* reset at the start of each new group so that
    inter-group octave transitions are correctly encoded as delta tokens.
    The ``v_stamp`` is reset to the group header's volume at the start of
    each new group (since the header declares the volume explicitly).

    Args:
        work_buf: per-channel list of (Segment, repeat_count) pairs.
        use_cnt:  when True, use the target repeat count for ``[...]cnt``
                  bracket wrapping (compress.MGS variant).  When False
                  (default) each segment is emitted as a single note.
        use_pct:  when True, emit ``{scale}%{N}`` tick lengths and omit
                  ``l64`` from group headers (MGS_pct variant).

    Returns:
        dict mapping channel → list of MML fragment strings.
    """
    ch_list = list(work_buf)
    note_token_fn = get_mgs_note_token_pct if use_pct else get_mgs_note_token
    mml_buffer = {ch: [] for ch in ch_list}
    ch_offset = 1

    for ch in ch_list:
        note_cnt = 0
        mml = ""
        l_cnt = 0
        o_stamp = 0
        v_stamp = 0
        mode_stamp = -1
        is_first_group = True

        mml_buffer[ch].append(f"\n\n;ch{ch + ch_offset} start")

        for segment, repeat_count in work_buf[ch]:
            type_ = segment.ev_type
            l = segment.l
            v = segment.volume
            o = segment.octave
            scale = segment.scale
            mode = segment.mode
            v_diff = segment.volume_delta
            if use_cnt:
                cnt = repeat_count
                if cnt < 1:
                    cnt = 1
            else:
                cnt = 1

            noise_freq = segment.noise_period
            hw_env_period = _envelope_mml_period(segment)
            hw_env_shape = segment.envelope_shape

            if l > 0:
                length = l

                # Flush current group on mode change
                if note_cnt > 0 and mode != mode_stamp:
                    mml_buffer[ch].append(mml)
                    mml = ""
                    mml_buffer[ch].append(f"\n;tick count: {l_cnt}\n")
                    note_cnt = 0

                if note_cnt == 0:
                    if mode == 0:
                        v = 0
                        if is_first_group:
                            if use_pct:
                                mml = f"\n{ch + ch_offset} /0 v{v} o{o}"
                            else:
                                mml = f"\n{ch + ch_offset} /0 v{v} o{o} l64"
                            o_stamp = o
                            is_first_group = False
                        else:
                            mml = f"\n{ch + ch_offset} /0 v{v}"
                        v_stamp = v
                    elif mode == 1:
                        if is_first_group:
                            if use_pct:
                                mml = (f"\n{ch + ch_offset} /1"
                                       f" s{hw_env_shape} m{hw_env_period}"
                                       f" v{v} o{o}")
                            else:
                                mml = (f"\n{ch + ch_offset} /1"
                                       f" s{hw_env_shape} m{hw_env_period}"
                                       f" v{v} o{o} l64")
                            o_stamp = o
                            is_first_group = False
                        else:
                            mml = (f"\n{ch + ch_offset} /1"
                                   f" s{hw_env_shape} m{hw_env_period}"
                                   f" v{v}")
                        v_stamp = v
                    elif mode == 2:
                        if is_first_group:
                            if use_pct:
                                mml = (f"\n{ch + ch_offset} /2"
                                       f" s{hw_env_shape} m{hw_env_period}"
                                       f" n{noise_freq} v{v} o{o}")
                            else:
                                mml = (f"\n{ch + ch_offset} /2"
                                       f" s{hw_env_shape} m{hw_env_period}"
                                       f" n{noise_freq} v{v} o{o} l64")
                            o_stamp = o
                            is_first_group = False
                        else:
                            mml = (f"\n{ch + ch_offset} /2"
                                   f" s{hw_env_shape} m{hw_env_period}"
                                   f" n{noise_freq} v{v}")
                        v_stamp = v
                    elif mode == 3:
                        if is_first_group:
                            if use_pct:
                                mml = (f"\n{ch + ch_offset} /3"
                                       f" s{hw_env_shape} m{hw_env_period}"
                                       f" n{noise_freq} v{v} o{o}")
                            else:
                                mml = (f"\n{ch + ch_offset} /3"
                                       f" s{hw_env_shape} m{hw_env_period}"
                                       f" n{noise_freq} v{v} o{o} l64")
                            o_stamp = o
                            is_first_group = False
                        else:
                            mml = (f"\n{ch + ch_offset} /3"
                                   f" s{hw_env_shape} m{hw_env_period}"
                                   f" n{noise_freq} v{v}")
                        v_stamp = v

                while length > 0:
                    ltmp = min(length, 255)

                    if type_ in ('mode', 'fCA', 'fCB', 'aVC', 'wNC',
                                 'ePL', 'evM', 'evS'):
                        if mode == 0:
                            v = 0
                            scale = 'r'
                        note = note_token_fn(
                            ltmp, v, v_diff, scale, cnt, o,
                            o_stamp, v_stamp)
                        mml += " " + note
                        l_cnt += ltmp

                    length -= ltmp

                    if length >= 0:
                        mml_buffer[ch].append(mml)
                        mml = ""

                note_cnt += 1
                if note_cnt == 8 or mode == 0:
                    mml_buffer[ch].append(mml)
                    mml = ""
                    mml_buffer[ch].append(f"\n;tick count: {l_cnt}\n")
                    note_cnt = 0

                o_stamp = o
                v_stamp = v
                mode_stamp = mode

        if mml:
            mml_buffer[ch].append(mml)

        mml_buffer[ch].append(f"\n;ch{ch + ch_offset} end: tick count: {l_cnt}\n")

    return mml_buffer

def write_psg_mml(segments, output_dir, stem, debug=True, raw_ticks=False):
    """Render already interpreted Segments without reading event CSVs."""
    os.makedirs(output_dir, exist_ok=True)
    output_name_body = stem
    # ---- cnt-optimised work buffer (needed for compress variants) ----
    work_buffer2 = _update_and_optimize_cnt_psg(segments)

    # ---- pass3.compress.MGS_pct.mml (cnt-optimised repeat + MGS delta-token + % lengths) ----
    # Always produced so merged output can select raw-tick mode.
    compress_mgs_pct_buf = _build_psg_mml_mgs_buffer(work_buffer2, use_cnt=True, use_pct=True)
    compress_mgs_pct_path = os.path.join(output_dir, f"{output_name_body}.psg.pass3.compress.MGS_pct.mml")
    _write_psg_mml(compress_mgs_pct_buf, compress_mgs_pct_path, output_name_body, raw_ticks=True)

    # ---- pass3.compress.MGS.mml (cnt-optimised repeat + MGS delta-token) ----
    # Always produced so merged output can select divisor mode in non-debug.
    compress_mgs_buf = _build_psg_mml_mgs_buffer(work_buffer2, use_cnt=True)
    compress_path = os.path.join(output_dir, f"{output_name_body}.psg.pass3.compress.MGS.mml")
    _write_psg_mml(compress_mgs_buf, compress_path, output_name_body, raw_ticks=False)

    if not debug:
        return compress_mgs_pct_path if raw_ticks else compress_path

    simple_segments = {ch: [(seg, 1) for seg in rows] for ch, rows in segments.items()}

    # ---- debug-only variants ----

    # Primary .psg.mml (divisor notation, #tempo 225)
    mml_buffer1 = _build_psg_mml_buffer(segments, raw_ticks=False)
    pass3_mml_path = os.path.join(output_dir, f"{output_name_body}.psg.mml")
    _write_psg_mml(mml_buffer1, pass3_mml_path, output_name_body, raw_ticks=False)

    # pass3.simple.mml (raw tick notation, #tempo 75)
    raw_buf = _build_psg_mml_buffer(segments, raw_ticks=True)
    simple_raw_path = os.path.join(output_dir, f"{output_name_body}.psg.pass3.simple.mml")
    _write_psg_mml(raw_buf, simple_raw_path, output_name_body, raw_ticks=True)

    # pass3.simple.MGS.mml (MGS delta-token notation, #tempo 225)
    simple_mgs_buf = _build_psg_mml_mgs_buffer(simple_segments, use_cnt=False)
    simple_mgs_path = os.path.join(output_dir, f"{output_name_body}.psg.pass3.simple.MGS.mml")
    _write_psg_mml(simple_mgs_buf, simple_mgs_path, output_name_body, raw_ticks=False)

    # pass3.simple.MGS_pct.mml (MGS delta-token, raw tick % lengths, #tempo 75)
    simple_mgs_pct_buf = _build_psg_mml_mgs_buffer(simple_segments, use_cnt=False, use_pct=True)
    simple_mgs_pct_path = os.path.join(output_dir, f"{output_name_body}.psg.pass3.simple.MGS_pct.mml")
    _write_psg_mml(simple_mgs_pct_buf, simple_mgs_pct_path, output_name_body, raw_ticks=True)

    return pass3_mml_path


def process_psg_csv(input_path, output_dir, stem=None, dump_passes=True,
                    debug=True, raw_ticks=False):
    """Compatibility entry point: CSV -> Segments -> MGSDRV MML."""
    segments = build_segments(input_path, output_dir, stem, dump_passes)
    name = stem if stem is not None else os.path.splitext(os.path.basename(input_path))[0]
    return write_psg_mml(segments, output_dir, name, debug, raw_ticks)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(f"Usage: python {sys.argv[0]} <log_psg_csv>")
        sys.exit(1)

    input_csv = sys.argv[1]
    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    file_body = os.path.splitext(os.path.basename(input_csv))[0]
    out_dir = os.path.join(script_dir, 'outputs', file_body)

    result = process_psg_csv(input_csv, out_dir)
    print(f"Wrote {result}")
