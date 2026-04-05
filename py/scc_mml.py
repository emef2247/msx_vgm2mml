"""
scc_mml.py - Port of scc.mml.tcl
Converts SCC log CSV to pass0-3 CSVs and pass3.mml.
Usage: python scc_mml.py <log_scc_csv> [output_dir]
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from mml_utils import get_ticks, get_octave, get_scale

# ---------------------------------------------------------------------------
# Column indices (28 columns, 0-27)
# ---------------------------------------------------------------------------
COL_TYPE     = 0
COL_TIME     = 1
COL_CH       = 2
COL_TICKS    = 3
COL_L        = 4
COL_FL       = 5
COL_V        = 6
COL_FV       = 7
COL_F        = 8
COL_FF       = 9
COL_O        = 10
COL_SCALE    = 11
COL_EN       = 12
COL_FEN      = 13
COL_VDIFF    = 14
COL_VCNT     = 15
COL_ODIFF    = 16
COL_ENVLP    = 17
COL_ENVLP_IX = 18
COL_NE       = 19
COL_NF       = 20
COL_OFFSET   = 21
COL_DATA     = 22
COL_WTBINDEX = 23
COL_F1CTRL   = 24
COL_F2CTRL   = 25
COL_VCTRL    = 26
COL_ENCTRL   = 27

NUM_COLS = 28

# CSV headers (matching Tcl scc.mml.tcl output exactly)
_HEADER_COMMON = ("type,time,ch,ticks,l,fL,v,fV,f,fF,o,scale,en,fEn,vDiff,vCnt,"
                  "oDiff,envlp,envlpIndex,nE,nF,offset,data,wtbIndex,"
                  "f1Ctrl,f2Ctrl,vCtrl,enCtrl")
SCC_HEADER_PASS0  = "#" + _HEADER_COMMON
SCC_HEADER_PASS1  =       _HEADER_COMMON   # Tcl omits '#' for pass1
SCC_HEADER_PASS23 = "#" + _HEADER_COMMON

# SCC channels start at MGSDRV channel 4
CH_OFFSET = 4

# Tcl-compatible empty placeholder
EMPTY = '{}'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _int(val):
    """Safely convert to int; empty / '{}' → 0."""
    if val is None or val == '' or val == '{}':
        return 0
    try:
        return int(val)
    except (ValueError, TypeError):
        return 0


def _norm(val):
    """Normalise an empty CSV field to '{}'."""
    return EMPTY if (val is None or val == '') else val


def _get_volume(row):
    return _int(row[COL_VCTRL]) & 0xF


def _get_frequency(row):
    return _int(row[COL_F1CTRL]) + 256 * _int(row[COL_F2CTRL])


def _row_to_csv(row):
    return ','.join(str(v) for v in row)


def _parse_input_line(line):
    """Split a CSV line into a padded list of NUM_COLS normalised strings."""
    parts = line.split(',')
    while len(parts) < NUM_COLS:
        parts.append(EMPTY)
    parts = parts[:NUM_COLS]
    return [_norm(p) for p in parts]


# ---------------------------------------------------------------------------
# Wavetable tracker (mirrors scc_mml.tcl new_wavetable / append_wavetable)
# ---------------------------------------------------------------------------

class _WavetableTracker:
    def __init__(self):
        # Current 32-byte waveform being assembled (list of 2-char hex strings)
        self._cur = ['00'] * 32
        # Ordered list of completed 64-char hex strings (unique)
        self.bytes_list = []

    def new_wavetable(self, data):
        """Start a new waveform: byte[0] = data, rest = 0x00."""
        self._cur = [format(data & 0xFF, '02x')] + ['00'] * 31

    def append_wavetable(self, offset, data):
        """Update byte at offset.  If offset==31, finalise and return 64-char key."""
        self._cur[offset] = format(data & 0xFF, '02x')
        if offset == 31:
            key = ''.join(self._cur)
            if key not in self.bytes_list:
                self.bytes_list.append(key)
            return key
        return ''

    def get_index(self, key):
        try:
            return self.bytes_list.index(key)
        except ValueError:
            return 0


# ---------------------------------------------------------------------------
# Envelope list (mirrors scc_mml.tcl envlpList)
# ---------------------------------------------------------------------------

class _EnvlpTracker:
    def __init__(self):
        self._list = []

    def init(self):
        """Pre-populate with 'F' as the default envelope."""
        self._list = []
        self.add('F')

    def add(self, target):
        if target in self._list:
            return self._list.index(target)
        self._list.append(target)
        return len(self._list) - 1

    def get_index(self, target):
        try:
            return self._list.index(target)
        except ValueError:
            return -1


# ---------------------------------------------------------------------------
# Pass 0
# ---------------------------------------------------------------------------

def _pass0(log_buffer, ch_list):
    """Recalculate ticks, update wtbIndex for completed waveforms.

    Returns:
        temp_buf0   : dict ch -> list of rows (list-of-strings, 28 cols each)
        wtb_tracker : _WavetableTracker with all finalised waveforms
    """
    wtb = _WavetableTracker()
    temp_buf0 = {}

    for ch in ch_list:
        temp_buf0[ch] = []
        for raw_line in log_buffer[ch]:
            row = _parse_input_line(raw_line)

            # Recalculate ticks from time
            time_s = float(row[COL_TIME]) if row[COL_TIME] not in ('', EMPTY) else 0.0
            row[COL_TICKS] = str(get_ticks(time_s))

            type_ = row[COL_TYPE]

            if type_ == 'wtbNew':
                data = _int(row[COL_DATA])
                wtb.new_wavetable(data)

            elif type_ == 'wtbLast':
                offset = _int(row[COL_OFFSET])
                data   = _int(row[COL_DATA])
                key = wtb.append_wavetable(offset, data)
                if offset == 31:
                    row[COL_WTBINDEX] = str(wtb.get_index(key))

            temp_buf0[ch].append(row)

    return temp_buf0, wtb


# ---------------------------------------------------------------------------
# Pass 1
# ---------------------------------------------------------------------------

def _pass1(temp_buf0, ch_list):
    """Compute l, fL, v, fV, f, fF, o, scale, en, fEn, vDiff, vCnt, oDiff."""
    temp_buf1 = {}

    for ch in ch_list:
        buf       = temp_buf0[ch]
        n         = len(buf)
        temp_buf1[ch] = []

        f_tick_stamp = 0
        f_stamp      = 0
        fv_stamp     = 0
        en_stamp     = 0
        v_cnt        = 0

        line_stamp = None
        index = 0

        while index < n:
            line = buf[index]
            next_row = buf[index + 1] if index + 1 < n else None

            if line_stamp is not None:
                # --- skip-ahead when two consecutive f1/f2Ctrl share the same tick ---
                if next_row is not None:
                    cur_type  = line[COL_TYPE]
                    nxt_type  = next_row[COL_TYPE]
                    next_l    = _int(next_row[COL_TICKS]) - _int(line[COL_TICKS])
                    if (cur_type in ('f1Ctrl', 'f2Ctrl') and
                            nxt_type in ('f1Ctrl', 'f2Ctrl') and
                            next_l == 0):
                        index += 1
                        line = buf[index]
                        next_row = buf[index + 1] if index + 1 < n else None

                # --- process line_stamp ---
                lt = list(line_stamp)   # working copy
                type_ = line_stamp[COL_TYPE]

                # l = ticks(line) - ticks(line_stamp)
                l = _int(line[COL_TICKS]) - _int(line_stamp[COL_TICKS])
                lt[COL_L] = str(l)

                # fL (only for f1Ctrl / f2Ctrl / enBit)
                if type_ in ('f1Ctrl', 'f2Ctrl', 'enBit'):
                    f_ticks = _int(line_stamp[COL_TICKS])
                    fl = f_ticks - f_tick_stamp
                    lt[COL_FL] = str(fl)
                    f_tick_stamp = f_ticks

                # v = vCtrl & 0xF
                v = _get_volume(line_stamp)
                lt[COL_V] = str(v)

                # fV (only for f1Ctrl / f2Ctrl / enBit)
                if type_ in ('f1Ctrl', 'f2Ctrl', 'enBit'):
                    lt[COL_FV] = str(fv_stamp)
                    fv_stamp = v

                # f = f1Ctrl + 256*f2Ctrl
                f = _get_frequency(line_stamp)
                lt[COL_F] = str(f)

                # fF = previous f_stamp
                lt[COL_FF] = str(f_stamp)
                if type_ in ('f1Ctrl', 'f2Ctrl'):
                    f_stamp = f

                # o, scale (derived from fF)
                lt[COL_O]     = str(get_octave(f_stamp if type_ not in ('f1Ctrl', 'f2Ctrl') else _int(lt[COL_FF])))
                lt[COL_SCALE] = get_scale(_int(lt[COL_FF]))

                # en
                en = _int(line_stamp[COL_EN])
                lt[COL_EN] = str(en)

                # fEn (only updated by f1Ctrl / f2Ctrl, not enBit)
                lt[COL_FEN] = str(en_stamp)
                if type_ in ('f1Ctrl', 'f2Ctrl'):
                    en_stamp = en

                # vDiff = volume(next line) - volume(line_stamp)
                v_diff = _get_volume(line) - v
                lt[COL_VDIFF] = str(v_diff)

                # vCnt (incremented only for vCtrl)
                if type_ == 'vCtrl':
                    v_cnt += 1
                lt[COL_VCNT] = str(v_cnt)

                # oDiff = octave(next_f) - octave(fF)
                next_f = _get_frequency(line)
                next_o = get_octave(next_f)
                o_diff = next_o - _int(lt[COL_O])
                lt[COL_ODIFF] = str(o_diff)

                # wtbIndex stays from line_stamp
                lt[COL_WTBINDEX] = line_stamp[COL_WTBINDEX]

                temp_buf1[ch].append(lt)

                # Update vCnt after line_stamp is an f1Ctrl/f2Ctrl
                if type_ in ('f1Ctrl', 'f2Ctrl'):
                    f_stamp = f   # redundant but mirrors Tcl outside-block update
                    v_cnt = 1

            line_stamp = line
            index += 1

        # --- last line ---
        if line_stamp is not None:
            lt = list(line_stamp)
            type_ = line_stamp[COL_TYPE]

            l = 0   # ticks(last) - ticks(last) = 0
            lt[COL_L] = str(l)

            if type_ in ('f1Ctrl', 'f2Ctrl', 'enBit'):
                f_ticks = _int(line_stamp[COL_TICKS])
                fl = f_ticks - f_tick_stamp
                lt[COL_FL] = str(fl)
                f_tick_stamp = f_ticks

            v = _get_volume(line_stamp)
            lt[COL_V] = str(v)

            if type_ in ('f1Ctrl', 'f2Ctrl', 'enBit'):
                lt[COL_FV] = str(fv_stamp)
                fv_stamp = v

            f = _get_frequency(line_stamp)
            lt[COL_F] = str(f)
            lt[COL_FF] = str(f_stamp)
            if type_ in ('f1Ctrl', 'f2Ctrl'):
                f_stamp = f

            lt[COL_O]     = str(get_octave(_int(lt[COL_FF])))
            lt[COL_SCALE] = get_scale(_int(lt[COL_FF]))

            en = _int(line_stamp[COL_EN])
            lt[COL_EN] = str(en)
            lt[COL_FEN] = str(en_stamp)
            if type_ in ('f1Ctrl', 'f2Ctrl'):
                en_stamp = en

            # vDiff using last row as both line and line_stamp → 0
            v_diff = 0
            lt[COL_VDIFF] = str(v_diff)

            if type_ == 'vCtrl':
                v_cnt += 1
            lt[COL_VCNT] = str(v_cnt)

            lt[COL_ODIFF] = str(0)
            lt[COL_WTBINDEX] = line_stamp[COL_WTBINDEX]

            temp_buf1[ch].append(lt)

    return temp_buf1


# ---------------------------------------------------------------------------
# Pass 2
# ---------------------------------------------------------------------------

def _pass2(temp_buf1, ch_list):
    """Remove wtbNew/wtbLast rows; merge f1/f2Ctrl + vCtrl/enBit at same tick.

    When wtbNew/wtbLast rows are dropped, their l values are accumulated and
    propagated to the nearest adjacent non-wtb row so that the total tick count
    per channel is preserved.  Specifically:
    - If a non-wtb row already exists in the output buffer, the accumulated l is
      added to the last such row's l (covers the case of a wavetable update in
      the middle of playback).
    - If no non-wtb row has been emitted yet (wavetable setup at the very start
      of the channel), the accumulated l is added to the first non-wtb row's l
      (covers the case of ch7 starting with waveform initialisation at tick 0).
    """
    temp_buf2 = {}

    for ch in ch_list:
        buf = temp_buf1[ch]
        n   = len(buf)
        temp_buf2[ch] = []

        line_stamp = None
        index = 0
        _acc_l = 0   # l accumulated from dropped wtb rows

        while index < n:
            line     = buf[index]
            next_row = buf[index + 1] if index + 1 < n else None

            if line_stamp is not None:
                lt_type = line_stamp[COL_TYPE]

                # Add line_stamp to buffer (unless it is a wavetable row)
                if lt_type not in ('wtbNew', 'wtbLast'):
                    if _acc_l > 0:
                        row_to_add = list(line_stamp)
                        if temp_buf2[ch]:
                            # There is a previous non-wtb row: extend its l
                            temp_buf2[ch][-1][COL_L] = str(
                                _int(temp_buf2[ch][-1][COL_L]) + _acc_l)
                        else:
                            # No previous row yet: add to the current row's l
                            row_to_add[COL_L] = str(
                                _int(row_to_add[COL_L]) + _acc_l)
                        _acc_l = 0
                    else:
                        row_to_add = list(line_stamp)
                    temp_buf2[ch].append(row_to_add)
                else:
                    # Accumulate the l from the dropped wavetable row
                    _acc_l += _int(line_stamp[COL_L])

                # Check merge: line is f1/f2Ctrl AND next is vCtrl/enBit at same tick
                if next_row is not None:
                    cur_type = line[COL_TYPE]
                    nxt_type = next_row[COL_TYPE]
                    next_l   = _int(next_row[COL_TICKS]) - _int(line[COL_TICKS])

                    if (cur_type in ('f1Ctrl', 'f2Ctrl') and
                            nxt_type in ('vCtrl', 'enBit') and
                            next_l == 0):
                        # Build the merged row: start from next_row, copy fields from line
                        merged = list(next_row)
                        merged[COL_TYPE]    = cur_type
                        merged[COL_FL]      = line[COL_FL]
                        merged[COL_FV]      = line[COL_FV]
                        merged[COL_F]       = line[COL_F]
                        merged[COL_FF]      = line[COL_FF]
                        merged[COL_O]       = line[COL_O]
                        merged[COL_SCALE]   = line[COL_SCALE]
                        merged[COL_FEN]     = line[COL_FEN]
                        merged[COL_VCNT]    = line[COL_VCNT]
                        merged[COL_WTBINDEX] = line[COL_WTBINDEX]
                        temp_buf2[ch].append(merged)
                        # Skip both line and next_row
                        index += 2
                        line = buf[index] if index < n else None

            line_stamp = line
            index += 1

        # Last line_stamp
        if line_stamp is not None:
            lt_type = line_stamp[COL_TYPE]
            if lt_type not in ('wtbNew', 'wtbLast'):
                if _acc_l > 0:
                    row_to_add = list(line_stamp)
                    if temp_buf2[ch]:
                        temp_buf2[ch][-1][COL_L] = str(
                            _int(temp_buf2[ch][-1][COL_L]) + _acc_l)
                    else:
                        row_to_add[COL_L] = str(
                            _int(row_to_add[COL_L]) + _acc_l)
                    _acc_l = 0
                    temp_buf2[ch].append(row_to_add)
                else:
                    temp_buf2[ch].append(list(line_stamp))

    return temp_buf2


# ---------------------------------------------------------------------------
# Pass 3  (computes envlp / envlpIndex)
# ---------------------------------------------------------------------------

def _is_direction_change(v_diff, v_diff_stamp):
    """True when volume direction reverses (neg→pos or pos→neg)."""
    return ((v_diff > 0 and v_diff_stamp < 0) or
            (v_diff < 0 and v_diff_stamp > 0))


def _pass3(temp_buf2, ch_list):
    """Compute envlp (col17) and envlpIndex (col18)."""
    envlp_tracker = _EnvlpTracker()
    envlp_tracker.init()          # pre-populate 'F'
    temp_buf3 = {}

    for ch in ch_list:
        temp_buf3[ch] = []

        v_cnt        = 0
        v_length     = 0
        v_envlp      = ''
        v_envlp_temp = ''
        envlp        = 'F'
        v_diff_stamp = 0

        for row in temp_buf2[ch]:
            row = list(row)   # working copy
            type_ = row[COL_TYPE]
            l     = _int(row[COL_L])
            fL    = _int(row[COL_FL]) if row[COL_FL] != EMPTY else 0
            v     = _get_volume(row)
            v_diff = _int(row[COL_VDIFF])

            if fL > 0 and type_ in ('f1Ctrl', 'f2Ctrl'):
                # --- frequency event: finalise envelope for this segment ---
                if v_cnt > 1:
                    envlp = envlp + '.' + v_envlp
                else:
                    envlp = 'F'

                envlp_index = envlp_tracker.add(envlp)
                row[COL_ENVLP]    = envlp
                row[COL_ENVLP_IX] = str(envlp_index)

                # Reset envelope accumulator for next segment
                v_cnt        = 1
                v_length     = l
                v_envlp      = ''
                v_envlp_temp = ''
                envlp        = format(v, 'X')   # e.g. 'A' for 10

            elif type_ in ('vCtrl', 'enBit'):
                if l > 0:
                    v_cnt  += 1
                v_length += l

                if v_cnt > 1 or l != 0:
                    hex_v = format(v, 'X')
                    if v_envlp_temp:
                        if v_length > 1:
                            v_envlp = v_envlp_temp + '.' + hex_v + '=' + str(v_length)
                        else:
                            v_envlp = v_envlp_temp + '.' + hex_v
                    else:
                        if v_length > 1:
                            v_envlp = hex_v + '=' + str(v_length)
                        else:
                            v_envlp = hex_v

                # Check for direction reversal
                if _is_direction_change(v_diff, v_diff_stamp):
                    v_envlp_temp = v_envlp
                    v_length     = l

                row[COL_ENVLP] = v_envlp if v_envlp else EMPTY

            temp_buf3[ch].append(row)
            v_diff_stamp = v_diff

    return temp_buf3, envlp_tracker


# ---------------------------------------------------------------------------
# MML generation  (mirrors scc_mml.tcl generate_mml)
# ---------------------------------------------------------------------------

def _generate_mml(temp_buf3, ch_list, file_name_body, wtb_tracker):
    """Generate MML text from pass-3 data."""
    mml_buffer = {}

    for ch in ch_list:
        mml_buffer[ch] = []
        note_cnt  = 0
        l_cnt     = 0
        o_stamp   = 0
        v_stamp   = 0
        mml       = ''

        ch_num = ch + CH_OFFSET
        mml_buffer[ch].append(f'\n\n;ch{ch_num} start')

        for row in temp_buf3[ch]:
            type_      = row[COL_TYPE]
            l          = _int(row[COL_L])
            v          = _get_volume(row)
            o          = _int(row[COL_O])
            scale      = row[COL_SCALE] if row[COL_SCALE] not in ('', EMPTY) else 'r'
            en         = _int(row[COL_EN])
            wtb_index  = _int(row[COL_WTBINDEX])

            if l > 0:
                length = l
                while length > 0:
                    ltmp = min(length, 255)

                    if note_cnt == 0:
                        mml = f'\n{ch_num} @{wtb_index} v{v}'

                    if v != v_stamp and note_cnt != 0:
                        mml += f' v{v}'

                    if o != o_stamp:
                        mml += f' o{o}'

                    mml += f' {scale}%{ltmp} '
                    l_cnt += ltmp

                    length -= ltmp
                    if length > 0:
                        mml_buffer[ch].append(mml)
                        mml = ''

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
    lines.append('#tempo 75')
    lines.append(f'#title {{ "{file_name_body}"}}')
    lines.append('#alloc 1=3100')
    lines.append('#alloc 2=3100')
    lines.append('#alloc 3=2400')
    lines.append('#alloc 4=2100')
    lines.append('#alloc 5=1100')
    lines.append('#alloc 6=1000')
    lines.append('#alloc 7=1000')
    lines.append('')

    for i, wbytes in enumerate(wtb_tracker.bytes_list):
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


# ---------------------------------------------------------------------------
# Write helpers
# ---------------------------------------------------------------------------

def _write_csv(path, header, ch_list, buf):
    with open(path, 'w', newline='\n') as fh:
        fh.write(header + '\n')
        for ch in ch_list:
            for row in buf[ch]:
                fh.write(_row_to_csv(row) + '\n')


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def process_scc_csv(input_path, output_dir, dump_passes=True):
    """Run the full SCC MML pipeline.

    Args:
        input_path  : path to ``*_log.scc.csv``
        output_dir  : directory for output files
        dump_passes : when True (default) write pass0-3 CSV files

    Returns:
        path to the generated ``*.scc.pass3.mml``
    """
    # ---- Derive output name body from input filename ----
    # Input: /some/path/02_StartingPoint_log.scc.csv
    # Body : 02_StartingPoint_log
    base = os.path.basename(input_path)           # 02_StartingPoint_log.scc.csv
    root = os.path.splitext(base)[0]              # 02_StartingPoint_log.scc
    file_name_body = os.path.splitext(root)[0]    # 02_StartingPoint_log

    os.makedirs(output_dir, exist_ok=True)

    # ---- Read input CSV ----
    log_buffer = {}
    ch_list = []

    with open(input_path, 'r', newline='') as fh:
        for line in fh:
            line = line.rstrip('\r\n')
            if not line or line.lstrip().startswith('#'):
                continue
            if not line.replace(',', '').strip():
                continue
            cols = line.split(',')
            ch = int(cols[COL_CH]) if cols[COL_CH].strip() else 0
            if ch not in log_buffer:
                log_buffer[ch] = []
                ch_list.append(ch)
            log_buffer[ch].append(line)

    # ---- Pass 0 ----
    temp_buf0, wtb_tracker = _pass0(log_buffer, ch_list)
    if dump_passes:
        _write_csv(
            os.path.join(output_dir, f'{file_name_body}.scc.pass0.csv'),
            SCC_HEADER_PASS0, ch_list, temp_buf0)

    # ---- Pass 1 ----
    temp_buf1 = _pass1(temp_buf0, ch_list)
    if dump_passes:
        _write_csv(
            os.path.join(output_dir, f'{file_name_body}.scc.pass1.csv'),
            SCC_HEADER_PASS1, ch_list, temp_buf1)

    # ---- Pass 2 ----
    temp_buf2 = _pass2(temp_buf1, ch_list)
    if dump_passes:
        _write_csv(
            os.path.join(output_dir, f'{file_name_body}.scc.pass2.csv'),
            SCC_HEADER_PASS23, ch_list, temp_buf2)

    # ---- Pass 3 ----
    temp_buf3, _envlp = _pass3(temp_buf2, ch_list)
    if dump_passes:
        _write_csv(
            os.path.join(output_dir, f'{file_name_body}.scc.pass3.csv'),
            SCC_HEADER_PASS23, ch_list, temp_buf3)

    # ---- MML ----
    mml_text = _generate_mml(temp_buf3, ch_list, file_name_body, wtb_tracker)
    mml_path = os.path.join(output_dir, f'{file_name_body}.scc.pass3.mml')
    with open(mml_path, 'w', newline='\n') as fh:
        fh.write(mml_text)

    return mml_path


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
