"""SCC event analysis, waveforms and inspectable Segment construction."""
import os

from mml_utils import get_ticks, get_octave, get_scale
from chip_segments import SccSegment, SccAnalysis, dump_segments

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


def _parse_input_line(line, include_vgmticks=False):
    """Split a CSV line into a padded list of NUM_COLS normalised strings."""
    parts = line.split(',')
    while len(parts) < NUM_COLS:
        parts.append(EMPTY)
    parts = parts[:NUM_COLS + int(include_vgmticks)]
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

def _pass0(log_buffer, ch_list, include_vgmticks=False):
    """Recalculate ticks, update wtbIndex for completed waveforms.

    Returns:
        temp_buf0   : dict ch -> list of rows (list-of-strings, 28 cols each)
        wtb_tracker : _WavetableTracker with all finalised waveforms
    """
    wtb = _WavetableTracker()
    temp_buf0 = {}

    for ch in ch_list:
        temp_buf0[ch] = []
        wave_id = 0
        for raw_line in log_buffer[ch]:
            row = _parse_input_line(raw_line, include_vgmticks)

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
                    wave_id = wtb.get_index(key)

            row[COL_WTBINDEX] = str(wave_id)
            temp_buf0[ch].append(row)

    return temp_buf0, wtb


# ---------------------------------------------------------------------------
# Pass 1
# ---------------------------------------------------------------------------

def _pass1(temp_buf0, ch_list):
    """Interpret each post-write state over [this tick, next event tick)."""
    result = {}
    for ch in ch_list:
        rows = temp_buf0[ch]
        result[ch] = []
        previous_f = 0
        previous_v = 0
        for index, source in enumerate(rows):
            row = list(source)
            if len(row) > NUM_COLS:
                row.append(rows[index + 1][NUM_COLS] if index + 1 < len(rows) else row[NUM_COLS])
            tick = _int(row[COL_TICKS])
            end = _int(rows[index + 1][COL_TICKS]) if index + 1 < len(rows) else tick
            f = _get_frequency(row) & 0xfff
            v = _get_volume(row)
            row[COL_L] = str(end - tick)
            row[COL_FL] = str(end - tick)
            row[COL_F] = str(f)
            row[COL_FF] = str(previous_f)
            row[COL_V] = str(v)
            row[COL_FV] = str(previous_v)
            row[COL_O] = str(get_octave(f))
            row[COL_SCALE] = get_scale(f) if v and _int(row[COL_EN]) else 'r'
            row[COL_VDIFF] = str(v - previous_v)
            row[COL_VCNT] = '1'
            row[COL_ODIFF] = str(get_octave(f) - get_octave(previous_f))
            row[COL_FEN] = row[COL_EN]
            result[ch].append(row)
            previous_f, previous_v = f, v
    return result


def _pass2(temp_buf1, ch_list):
    """Drop zero-time waveform bookkeeping, never move time to another state.

    A waveform write followed by a wait is a real interval and must remain.
    Other zero-duration writes are preserved as event evidence.
    """
    return {ch: [list(row) for row in temp_buf1[ch]
                 if row[COL_TYPE] not in ('wtbNew', 'wtbLast') or _int(row[COL_L]) > 0]
            for ch in ch_list}


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


def _write_csv(path, header, ch_list, buf):
    with open(path, 'w', newline='\n') as fh:
        fh.write(header + '\n')
        for ch in ch_list:
            for row in buf[ch]:
                fh.write(_row_to_csv(row) + '\n')


def build_segments(input_path, output_dir, dump_passes=True, stem=None):
    """Interpret SCC log/trace CSV through the existing passes into segments."""
    # ---- Derive output name body from input filename or stem ----
    if stem is not None:
        file_name_body = stem
    else:
        # Input: /some/path/02_StartingPoint_log.scc.csv
        # Body : 02_StartingPoint_log
        base = os.path.basename(input_path)           # 02_StartingPoint_log.scc.csv
        root = os.path.splitext(base)[0]              # 02_StartingPoint_log.scc
        file_name_body = os.path.splitext(root)[0]    # 02_StartingPoint_log

    os.makedirs(output_dir, exist_ok=True)

    # ---- Read input CSV ----
    log_buffer = {}
    ch_list = []
    has_vgmticks = False

    with open(input_path, 'r', newline='') as fh:
        for line in fh:
            line = line.rstrip('\r\n')
            if line.startswith('#'):
                has_vgmticks = 'vgmticks' in line.split(',')
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
    temp_buf0, wtb_tracker = _pass0(log_buffer, ch_list, has_vgmticks)
    if dump_passes:
        _write_csv(
            os.path.join(output_dir, f'{file_name_body}.scc.pass0.csv'),
            SCC_HEADER_PASS0 + (',vgmticks' if has_vgmticks else ''), ch_list, temp_buf0)

    # ---- Pass 1 ----
    temp_buf1 = _pass1(temp_buf0, ch_list)
    if dump_passes:
        _write_csv(
            os.path.join(output_dir, f'{file_name_body}.scc.pass1.csv'),
            SCC_HEADER_PASS1 + (',vgmticks,vgmticks_end' if has_vgmticks else ''), ch_list, temp_buf1)

    # ---- Pass 2 ----
    temp_buf2 = _pass2(temp_buf1, ch_list)
    if dump_passes:
        _write_csv(
            os.path.join(output_dir, f'{file_name_body}.scc.pass2.csv'),
            SCC_HEADER_PASS23 + (',vgmticks,vgmticks_end' if has_vgmticks else ''), ch_list, temp_buf2)

    # ---- Pass 3 ----
    temp_buf3, _envlp = _pass3(temp_buf2, ch_list)
    if dump_passes:
        _write_csv(
            os.path.join(output_dir, f'{file_name_body}.scc.pass3.csv'),
            SCC_HEADER_PASS23 + (',vgmticks,vgmticks_end' if has_vgmticks else ''), ch_list, temp_buf3)

    waveforms = tuple(wtb_tracker.bytes_list)
    segments = {ch: [_to_segment(row, waveforms) for row in temp_buf3[ch]] for ch in ch_list}
    if dump_passes:
        dump_segments(os.path.join(output_dir, f'{file_name_body}.scc.segments.csv'),
                      segments, SccSegment)
        with open(os.path.join(output_dir, f'{file_name_body}.scc.waveforms.csv'),
                  'w', newline='\n') as fh:
            fh.write('waveform_id,waveform_hex\n')
            for index, waveform in enumerate(waveforms):
                fh.write(f'{index},{waveform}\n')
    return SccAnalysis(segments, waveforms)


def _to_segment(row, waveforms):
    wave_id = _int(row[COL_WTBINDEX])
    return SccSegment(
        vgmticks=int(row[28]) if len(row) > 28 and row[28] not in ('', EMPTY) else None,
        vgmticks_end=int(row[29]) if len(row) > 29 and row[29] not in ('', EMPTY) else None,
        ev_type=row[COL_TYPE], time=float(row[COL_TIME]) if row[COL_TIME] not in ('', EMPTY) else 0,
        ch=_int(row[COL_CH]), ticks=_int(row[COL_TICKS]), l=_int(row[COL_L]),
        tone_period=_int(row[COL_F]), previous_tone_period=_int(row[COL_FF]),
        volume=_get_volume(row), octave=_int(row[COL_O]),
        scale=row[COL_SCALE] if row[COL_SCALE] not in ('', EMPTY) else 'r',
        volume_delta=_int(row[COL_VDIFF]), enabled=_int(row[COL_EN]),
        volume_run_count=_int(row[COL_VCNT]), waveform_id=wave_id,
        waveform_hex=waveforms[wave_id] if 0 <= wave_id < len(waveforms) else '',
        enable_register=_int(row[COL_ENCTRL]), pass3_row=tuple(row))
