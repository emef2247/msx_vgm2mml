"""
psg_mml.py - Port of psg.mml.tcl
Converts PSG log CSV to pass0-3 CSVs and pass3.mml.
Usage: python psg_mml.py <log_psg_csv_file>
"""
import sys
import os
import math

sys.path.insert(0, os.path.dirname(__file__))
from mml_utils import (get_ticks, get_octave, get_scale, get_tone_frequency,
                       estimate_mml_used, estimate_alloc, ticks_to_mml_length,
                       compress_mml_text, get_mgs_note_token,
                       get_mgs_note_token_pct)

# PSG column indices
COL_TYPE = 0
COL_TIME = 1
COL_CH = 2
COL_TICKS = 3
COL_L = 4
COL_FL = 5
COL_V = 6
COL_FV = 7
COL_F = 8
COL_FF = 9
COL_O = 10
COL_SCALE = 11
COL_EN = 12   # PSG mode: 0=mute, 1=tone, 2=noise, 3=both
COL_FEN = 13
COL_VDIFF = 14
COL_VCNT = 15
COL_ODIFF = 16
# cols 17-23 empty
COL_FCTRLA = 24
COL_FCTRLB = 25
COL_WNCTRL = 26
COL_VVCTRL = 27
COL_AVCTRL = 28
COL_ENVPCTRL_L = 29
COL_ENVPCTRL_M = 30
COL_ENVSHAPE = 31
COL_IOPARALLEL1 = 32
COL_IOPARALLEL2 = 33

# Pass-3 extra columns (appended by the pass-3 loop)
_PSG_COL_LDIFF = 34
_PSG_COL_ODIFF3 = 35
_PSG_COL_CNT = 36


def _int(val):
    """Safely convert to int, returning 0 for empty/None."""
    if val is None or val == '' or val == '{}':
        return 0
    try:
        return int(val)
    except (ValueError, TypeError):
        return 0


def get_volume(row):
    return _int(row[COL_AVCTRL]) & 0xF


def get_frequency(row):
    return _int(row[COL_FCTRLA]) + 256 * _int(row[COL_FCTRLB])


def get_psg_mode(ch, vvctrl):
    """Get PSG mode (0=mute, 1=tone, 2=noise, 3=both) for channel ch."""
    tone_mask = 1 << ch
    noise_mask = 1 << (ch + 3)
    tone_enabled = (vvctrl & tone_mask) == 0
    noise_enabled = (vvctrl & noise_mask) == 0
    if tone_enabled and not noise_enabled:
        return 1
    elif not tone_enabled and noise_enabled:
        return 2
    elif tone_enabled and noise_enabled:
        return 3
    else:
        return 0


def get_noise_period(row):
    return _int(row[COL_WNCTRL]) & 0x1F


def get_hw_envelope_on(row):
    return _int(row[COL_AVCTRL]) // 16


def get_hw_envelope_frequency(row):
    envl = _int(row[COL_ENVPCTRL_L])
    envm = _int(row[COL_ENVPCTRL_M])
    period = envm * 256 + envl
    return int(143.03493 * period)


def get_hw_envelope_shape(row):
    return _int(row[COL_ENVSHAPE]) & 0xF


def _row_to_csv(row):
    return ','.join(str(v) for v in row)


def process_psg_csv(input_path, output_dir, stem=None, dump_passes=True,
                    debug=True):
    """Main processing pipeline for PSG log CSV.

    Args:
        input_path  : path to ``*_log.psg.csv``
        output_dir  : directory for output files
        stem        : base name for output files (e.g. ``"02_StartingPoint_psg_log"``).
                      When *None* (default) the stem is derived from *input_path*.
        dump_passes : when True (default) write pass0-3 intermediate CSV files
        debug       : when True (default) write all MML variant files; when False
                      write only the ``pass3.compress.MGS_pct.mml`` file.

    Returns:
        path to the generated MML file (``*.psg.mml`` in debug mode, or
        ``*.psg.pass3.compress.MGS_pct.mml`` in non-debug mode).
    """
    # Read raw CSV lines into logBuffer per channel
    log_buffer = {}   # ch -> list of raw CSV line strings
    ch_list = []

    with open(input_path, 'r', newline='') as f:
        for line in f:
            line = line.rstrip('\n').rstrip('\r')
            if not line.strip() or line.strip().startswith('#') or line.strip().replace(',', '') == '':
                continue
            cols = line.split(',')
            ch = int(cols[COL_CH]) if cols[COL_CH].strip() else 0
            if ch not in log_buffer:
                log_buffer[ch] = []
                ch_list.append(ch)
            log_buffer[ch].append(line)

    if stem is not None:
        output_name_body = stem
    else:
        # Derive stem from input filename: strip extensions like .psg.csv -> base
        file_name_body = os.path.splitext(os.path.basename(input_path))[0]
        output_name_body = file_name_body

    os.makedirs(output_dir, exist_ok=True)

    PSG_HEADER = "#type,time,ch,ticks,l,fL,v,fV,f,fF,o,scale,en,fEn,vDiff,vCnt,oDiff,envlp,envlpIndex,nE,nF,offset,data,wtbIndex,fCtrlA,fCtrlB,wNCtrl,vVCtrl,aVCtrl,envPCtrlL,envPCtrlM,envShape,ioParallel1,ioParallel2"

    # -------------------------------------------------------
    # Pass 0: compute ticks from time, store as list-of-lists
    # -------------------------------------------------------
    temp_buffer0 = {}
    for ch in ch_list:
        temp_buffer0[ch] = []
        for raw_line in log_buffer[ch]:
            cols = raw_line.split(',')
            # Pad to 34 columns
            while len(cols) < 34:
                cols.append('')
            time_s = float(cols[COL_TIME]) if cols[COL_TIME] else 0.0
            ticks = get_ticks(time_s)
            cols[COL_TICKS] = str(ticks)
            temp_buffer0[ch].append(cols)

    # Write pass0.csv
    if dump_passes:
        pass0_path = os.path.join(output_dir, f"{output_name_body}.psg.pass0.csv")
        with open(pass0_path, 'w', newline='\n') as f:
            f.write(PSG_HEADER + '\n')
            for ch in ch_list:
                for row in temp_buffer0[ch]:
                    f.write(_row_to_csv(row) + '\n')

    # -------------------------------------------------------
    # Pass 1: compute l, v, f, o, scale, mode, vDiff, etc.
    #
    # Key principles (matching SCC snapshot approach):
    #   - Same-tick fCA+fCB: skip fCA so fCB gives the complete 12-bit frequency
    #   - scale/octave are computed from the CURRENT frequency f (not stale fF=0)
    #   - audibility = (mode != 0) AND (volume > 0 OR hw_envelope_on)
    #   - scale = 'r' when not audible
    # -------------------------------------------------------
    temp_buffer1 = {}
    for ch in ch_list:
        temp_buffer1[ch] = []
        buf = temp_buffer0[ch]
        n = len(buf)
        line_stamp = None
        en_stamp = 0
        v_cnt = 0

        index = 0
        while index < n:
            line = buf[index]
            nxt = buf[index + 1] if index + 1 < n else None

            if line_stamp is not None:
                # --- skip-ahead: if line is fCA and next is fCB at the same tick,
                # advance line to fCB so the complete 12-bit frequency is used.
                if nxt is not None:
                    cur_type = line[COL_TYPE]
                    nxt_type = nxt[COL_TYPE]
                    next_l = _int(nxt[COL_TICKS]) - _int(line[COL_TICKS])
                    if cur_type == 'fCA' and nxt_type == 'fCB' and next_l == 0:
                        index += 1
                        line = buf[index]
                        nxt = buf[index + 1] if index + 1 < n else None

                # --- process line_stamp ---
                line_temp = list(line_stamp)
                type_ = line_stamp[COL_TYPE]

                # l = ticks(current) - ticks(lineStamp)
                l = _int(line[COL_TICKS]) - _int(line_stamp[COL_TICKS])
                line_temp[COL_L] = str(l)

                # v = aVCtrl & 0xF
                v = get_volume(line_stamp)
                line_temp[COL_V] = str(v)

                # f = fCtrlA + 256*fCtrlB (current complete frequency from this row)
                f = get_frequency(line_stamp)
                line_temp[COL_F] = str(f)

                # fF = same as f for PSG (no separate "previous" concept needed here)
                line_temp[COL_FF] = str(f)

                # mode from col 12 (set by vVCtrl events in the log)
                mode = _int(line_stamp[COL_EN])
                line_temp[COL_EN] = str(mode)

                # fEn = enStamp
                line_temp[COL_FEN] = str(en_stamp)
                if type_ == 'mode':
                    en_stamp = mode

                # Audibility: mode must be non-zero AND (volume > 0 OR hw_envelope on)
                hw_env_on = get_hw_envelope_on(line_stamp)
                audible = (mode != 0) and (v > 0 or hw_env_on)

                # o and scale from current frequency when audible, else rest
                o = get_octave(f) if audible else 1
                scale = get_scale(f) if audible else 'r'
                line_temp[COL_O] = str(o)
                line_temp[COL_SCALE] = scale

                # vDiff = volume(next line) - volume(line_stamp)
                next_v = get_volume(line)
                v_diff = next_v - v
                line_temp[COL_VDIFF] = str(v_diff)

                # vCnt
                if type_ == 'aVC':
                    v_cnt += 1
                line_temp[COL_VCNT] = str(v_cnt)

                # oDiff = octave(next_f) - octave(f)
                next_f = get_frequency(line)
                next_o = get_octave(next_f)
                o_diff = next_o - o
                line_temp[COL_ODIFF] = str(o_diff)

                temp_buffer1[ch].append(line_temp)

            line_stamp = line
            index += 1

        # Last line (lineStamp = last element, l = 0)
        if line_stamp is not None and n > 0:
            line_temp = list(line_stamp)
            type_ = line_stamp[COL_TYPE]

            l = 0
            line_temp[COL_L] = str(l)

            v = get_volume(line_stamp)
            line_temp[COL_V] = str(v)
            f = get_frequency(line_stamp)
            line_temp[COL_F] = str(f)
            line_temp[COL_FF] = str(f)
            mode = _int(line_stamp[COL_EN])
            line_temp[COL_EN] = str(mode)
            line_temp[COL_FEN] = str(en_stamp)

            hw_env_on = get_hw_envelope_on(line_stamp)
            audible = (mode != 0) and (v > 0 or hw_env_on)
            o = get_octave(f) if audible else 1
            scale = get_scale(f) if audible else 'r'
            line_temp[COL_O] = str(o)
            line_temp[COL_SCALE] = scale

            v_diff = 0
            line_temp[COL_VDIFF] = str(v_diff)
            line_temp[COL_VCNT] = str(v_cnt)
            line_temp[COL_ODIFF] = '0'
            temp_buffer1[ch].append(line_temp)

    # Write pass1.csv
    if dump_passes:
        pass1_path = os.path.join(output_dir, f"{output_name_body}.psg.pass1.csv")
        with open(pass1_path, 'w', newline='\n') as f:
            f.write(PSG_HEADER + '\n')
            for ch in ch_list:
                for row in temp_buffer1[ch]:
                    f.write(_row_to_csv(row) + '\n')

    # -------------------------------------------------------
    # Pass 2: filter rows
    # Keep rows where l != 0, OR type in important state-change types
    # (keeps state-change events even when they occur at the same tick as
    #  the following event, so that volume/mode/envelope changes are tracked)
    # -------------------------------------------------------
    _KEEP_L0_TYPES = frozenset(
        ('mode', 'fCA', 'fCB', 'aVC', 'evS', 'evM', 'ePL', 'wNC'))
    temp_buffer2 = {}
    for ch in ch_list:
        temp_buffer2[ch] = []
        for row in temp_buffer1[ch]:
            type_ = row[COL_TYPE]
            l = _int(row[COL_L])
            if l != 0:
                temp_buffer2[ch].append(row)
            elif type_ in _KEEP_L0_TYPES:
                temp_buffer2[ch].append(row)

    # Write pass2.csv
    if dump_passes:
        pass2_path = os.path.join(output_dir, f"{output_name_body}.psg.pass2.csv")
        with open(pass2_path, 'w', newline='\n') as f:
            f.write(PSG_HEADER + '\n')
            for ch in ch_list:
                for row in temp_buffer2[ch]:
                    f.write(_row_to_csv(row) + '\n')

    # -------------------------------------------------------
    # Pass 3: add lDiff, vDiff, oDiff, cnt columns
    # -------------------------------------------------------
    PSG_HEADER3 = PSG_HEADER + ",vDiff,oDiff,cnt"
    temp_buffer3 = {}
    for ch in ch_list:
        temp_buffer3[ch] = []
        l_stamp = 0
        v_diff_stamp = 0
        cnt = 0
        for row in temp_buffer2[ch]:
            l = _int(row[COL_L])
            v = _int(row[COL_V])
            o = _int(row[COL_O])
            l_diff = l - l_stamp
            v_diff = _int(row[COL_VDIFF])
            o_diff = _int(row[COL_ODIFF])
            if l_diff == 0 and v_diff == v_diff_stamp:
                cnt += 1
            else:
                cnt = 1
            new_row = list(row) + [str(l_diff), str(o_diff), str(cnt)]
            temp_buffer3[ch].append(new_row)
            l_stamp = l
            v_diff_stamp = v_diff

    # Write pass3.csv
    if dump_passes:
        pass3_csv_path = os.path.join(output_dir, f"{output_name_body}.psg.pass3.csv")
        with open(pass3_csv_path, 'w', newline='\n') as f:
            f.write(PSG_HEADER3 + '\n')
            for ch in ch_list:
                for row in temp_buffer3[ch]:
                    f.write(_row_to_csv(row) + '\n')

    # -------------------------------------------------------
    # Copy tempBuffer3 to workBuffer1 and generate MML
    # -------------------------------------------------------
    work_buffer1 = {}
    for ch in ch_list:
        work_buffer1[ch] = list(temp_buffer3[ch])

    def _build_psg_mml_buffer(raw_ticks=False):
        """Build per-channel MML buffers from work_buffer1.

        When *raw_ticks* is True, emit ``{scale}%{N}`` notation and omit
        the ``l64`` default-length directive (pass3.simple.mml style).
        When False (default), emit standard divisor notation with ``l64``
        (pass3.simple.MGS.mml style, #tempo 225).
        """
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

            for row in work_buffer1[ch]:
                type_ = row[COL_TYPE]
                l = _int(row[COL_L])
                v = _int(row[COL_V])
                f = _int(row[COL_F])
                o = _int(row[COL_O])
                scale = row[COL_SCALE] if row[COL_SCALE] else 'r'
                mode = _int(row[COL_EN])

                noise_freq = get_noise_period(row)
                hw_env_on = get_hw_envelope_on(row)
                hw_env_period = get_hw_envelope_frequency(row)
                hw_env_shape = get_hw_envelope_shape(row)

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
        and hw-envelope period all match the previous row's values, the ``cnt``
        column (index :data:`_PSG_COL_CNT`) of the *previous* row in the output
        buffer is incremented and the current row is discarded.

        Returns a new buffer dict with the same structure as *src_buffer*.
        """
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

            for row in src_buffer[ch]:
                type_ = row[COL_TYPE]
                l = _int(row[COL_L])
                f = _int(row[COL_F])
                o = _int(row[COL_O])
                v_diff = _int(row[COL_VDIFF])
                mode = _int(row[COL_EN])
                noise_period = get_noise_period(row)
                hw_env_shape = get_hw_envelope_shape(row)
                hw_env_period = get_hw_envelope_frequency(row)
                cnt = _int(row[_PSG_COL_CNT]) if len(row) > _PSG_COL_CNT else 1

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
                            # Merge into previous row: increment its cnt
                            cnt_stamp += 1
                            prev = list(dst_buffer[ch][-1])
                            while len(prev) <= _PSG_COL_CNT:
                                prev.append('0')
                            prev[_PSG_COL_CNT] = str(cnt_stamp)
                            dst_buffer[ch][-1] = prev
                            # Skip appending current row (it is absorbed)
                        else:
                            new_row = list(row)
                            while len(new_row) <= _PSG_COL_CNT:
                                new_row.append('0')
                            new_row[_PSG_COL_CNT] = '1'  # reset to 1
                            dst_buffer[ch].append(new_row)
                            cnt_stamp = 1  # First occurrence is always 1
                    else:
                        new_row = list(row)
                        while len(new_row) <= _PSG_COL_CNT:
                            new_row.append('0')
                        new_row[_PSG_COL_CNT] = '1'  # reset to 1
                        dst_buffer[ch].append(new_row)
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
                    dst_buffer[ch].append(list(row))

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
        * When ``use_cnt`` is False (default, for simple.MGS.mml) each row is
          treated as a single note (cnt forced to 1, no bracket wrapping).
        * When ``use_pct`` is True, note lengths are encoded as
          ``{scale}%{N}`` raw tick tokens instead of the divisor notation
          produced by :func:`mgs_length_to_str` (MGS_pct variant).

        The ``o_stamp`` is *not* reset at the start of each new group so that
        inter-group octave transitions are correctly encoded as delta tokens.
        The ``v_stamp`` is reset to the group header's volume at the start of
        each new group (since the header declares the volume explicitly).

        Args:
            work_buf: per-channel list of pass-3 rows (same structure as
                      ``work_buffer1``).
            use_cnt:  when True, use the ``cnt`` column for ``[...]cnt``
                      bracket wrapping (compress.MGS variant).  When False
                      (default) each row is emitted as a single note.
            use_pct:  when True, emit ``{scale}%{N}`` tick lengths and omit
                      ``l64`` from group headers (MGS_pct variant).

        Returns:
            dict mapping channel → list of MML fragment strings.
        """
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

            for row in work_buf[ch]:
                type_ = row[COL_TYPE]
                l = _int(row[COL_L])
                v = _int(row[COL_V])
                o = _int(row[COL_O])
                scale = row[COL_SCALE] if row[COL_SCALE] else 'r'
                mode = _int(row[COL_EN])
                v_diff = _int(row[COL_VDIFF])
                if use_cnt:
                    cnt = _int(row[_PSG_COL_CNT]) if len(row) > _PSG_COL_CNT else 1
                    if cnt < 1:
                        cnt = 1
                else:
                    cnt = 1

                noise_freq = get_noise_period(row)
                hw_env_period = get_hw_envelope_frequency(row)
                hw_env_shape = get_hw_envelope_shape(row)

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

    # ---- cnt-optimised work buffer (needed for compress variants) ----
    work_buffer2 = _update_and_optimize_cnt_psg(work_buffer1)

    # ---- pass3.compress.MGS_pct.mml (cnt-optimised repeat + MGS delta-token + % lengths) ----
    # Always produced – used as the merge source and as the primary non-debug output.
    compress_mgs_pct_buf = _build_psg_mml_mgs_buffer(work_buffer2, use_cnt=True, use_pct=True)
    compress_mgs_pct_path = os.path.join(output_dir, f"{output_name_body}.psg.pass3.compress.MGS_pct.mml")
    _write_psg_mml(compress_mgs_pct_buf, compress_mgs_pct_path, output_name_body, raw_ticks=True)

    if not debug:
        return compress_mgs_pct_path

    # ---- debug-only variants ----

    # Primary .psg.mml (divisor notation, #tempo 225)
    mml_buffer1 = _build_psg_mml_buffer(raw_ticks=False)
    pass3_mml_path = os.path.join(output_dir, f"{output_name_body}.psg.mml")
    _write_psg_mml(mml_buffer1, pass3_mml_path, output_name_body, raw_ticks=False)

    # pass3.simple.mml (raw tick notation, #tempo 75)
    raw_buf = _build_psg_mml_buffer(raw_ticks=True)
    simple_raw_path = os.path.join(output_dir, f"{output_name_body}.psg.pass3.simple.mml")
    _write_psg_mml(raw_buf, simple_raw_path, output_name_body, raw_ticks=True)

    # pass3.simple.MGS.mml (MGS delta-token notation, #tempo 225)
    simple_mgs_buf = _build_psg_mml_mgs_buffer(work_buffer1, use_cnt=False)
    simple_mgs_path = os.path.join(output_dir, f"{output_name_body}.psg.pass3.simple.MGS.mml")
    _write_psg_mml(simple_mgs_buf, simple_mgs_path, output_name_body, raw_ticks=False)

    # pass3.compress.MGS.mml (cnt-optimised repeat + MGS delta-token)
    compress_mgs_buf = _build_psg_mml_mgs_buffer(work_buffer2, use_cnt=True)
    compress_path = os.path.join(output_dir, f"{output_name_body}.psg.pass3.compress.MGS.mml")
    _write_psg_mml(compress_mgs_buf, compress_path, output_name_body, raw_ticks=False)

    # pass3.simple.MGS_pct.mml (MGS delta-token, raw tick % lengths, #tempo 75)
    simple_mgs_pct_buf = _build_psg_mml_mgs_buffer(work_buffer1, use_cnt=False, use_pct=True)
    simple_mgs_pct_path = os.path.join(output_dir, f"{output_name_body}.psg.pass3.simple.MGS_pct.mml")
    _write_psg_mml(simple_mgs_pct_buf, simple_mgs_pct_path, output_name_body, raw_ticks=True)

    return pass3_mml_path


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
