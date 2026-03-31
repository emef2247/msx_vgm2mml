"""
psg_mml.py - Port of psg.mml.tcl
Converts PSG log CSV to pass0-3 CSVs and pass3.mml.
Usage: python psg_mml.py <log_psg_csv_file>
"""
import sys
import os
import math

sys.path.insert(0, os.path.dirname(__file__))
from mml_utils import get_ticks, get_octave, get_scale, get_tone_frequency

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


def process_psg_csv(input_path, output_dir):
    """Main processing pipeline for PSG log CSV."""
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

    file_name_body = os.path.splitext(os.path.basename(input_path))[0]
    # Remove _log.psg suffix if present
    for suffix in ['.psg', '.scc', '_log']:
        if file_name_body.endswith(suffix):
            pass  # keep full stem for pass0
    # output name body = file stem without last extension
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
    pass0_path = os.path.join(output_dir, f"{output_name_body}.psg.pass0.csv")
    with open(pass0_path, 'w', newline='\n') as f:
        f.write(PSG_HEADER + '\n')
        for ch in ch_list:
            for row in temp_buffer0[ch]:
                f.write(_row_to_csv(row) + '\n')

    # -------------------------------------------------------
    # Pass 1: compute l, v, f, fF, o, scale, mode, vDiff, etc.
    # (First loop only - mirrors Tcl first loop)
    # -------------------------------------------------------
    temp_buffer1 = {}
    num_of_ch = 3
    for ch in ch_list:
        temp_buffer1[ch] = []
        buf = temp_buffer0[ch]
        n = len(buf)
        line_stamp = None
        f_stamp = 0
        en_stamp = 0
        v_cnt = 0
        v_stamp = 0
        o_stamp = 1

        index = 0
        while index < n:
            line = buf[index]
            nxt = buf[index + 1] if index + 1 < n else None

            if line_stamp is not None:
                line_temp = list(line_stamp)  # copy
                type_ = line_stamp[COL_TYPE]

                # l = ticks(current) - ticks(lineStamp)
                l = _int(line[COL_TICKS]) - _int(line_stamp[COL_TICKS])
                line_temp[COL_L] = str(l)

                # fL - NOTE: Tcl checks "fCtrlA"/"fCtrlB"/"aVCtrl" which never match
                # PSG types ("fCA"/"fCB"/"aVC"), so fL is never set here.
                # We leave col 5 as original (empty string from CSV).

                # v = aVCtrl & 0xF
                v = get_volume(line_stamp)
                line_temp[COL_V] = str(v)

                # f = fCtrlA + 256*fCtrlB
                f = get_frequency(line_stamp)
                line_temp[COL_F] = str(f)

                # fF = fStamp (previous frequency) - never updated for PSG type names
                line_temp[COL_FF] = str(f_stamp)

                # o = get_octave(fF)
                o = get_octave(f_stamp)
                line_temp[COL_O] = str(o)

                # scale = get_scale(fF)
                scale = get_scale(f_stamp)
                line_temp[COL_SCALE] = scale

                # mode = PSG mode at col 12 (from original log CSV)
                mode = _int(line_stamp[COL_EN])
                line_temp[COL_EN] = str(mode)

                # fEn = enStamp
                line_temp[COL_FEN] = str(en_stamp)
                # fCtrlA/fCtrlB type check (never fires for PSG)

                # vDiff
                next_v = get_volume(line) if nxt is None else get_volume(line)
                v_diff = next_v - v
                line_temp[COL_VDIFF] = str(v_diff)

                # vCnt
                line_temp[COL_VCNT] = str(v_cnt)

                # oDiff
                next_f = get_frequency(line)
                next_o = get_octave(next_f)
                o_diff = next_o - o
                line_temp[COL_ODIFF] = str(o_diff)

                temp_buffer1[ch].append(line_temp)

                v_stamp = v
                o_stamp = o

            line_stamp = line
            index += 1

        # Last line (lineStamp = last element, line = last element)
        if line_stamp is not None and n > 0:
            line = buf[n - 1]
            line_temp = list(line_stamp)
            type_ = line_stamp[COL_TYPE]

            l = _int(line[COL_TICKS]) - _int(line_stamp[COL_TICKS])
            line_temp[COL_L] = str(l)

            v = get_volume(line_stamp)
            line_temp[COL_V] = str(v)
            f = get_frequency(line_stamp)
            line_temp[COL_F] = str(f)
            line_temp[COL_FF] = str(f_stamp)
            o = get_octave(f_stamp)
            line_temp[COL_O] = str(o)
            line_temp[COL_SCALE] = get_scale(f_stamp)
            mode = _int(line_stamp[COL_EN])
            line_temp[COL_EN] = str(mode)
            line_temp[COL_FEN] = str(en_stamp)
            next_v = get_volume(line)
            v_diff = next_v - v
            line_temp[COL_VDIFF] = str(v_diff)
            line_temp[COL_VCNT] = str(v_cnt)
            next_f = get_frequency(line)
            next_o = get_octave(next_f)
            o_diff = next_o - o
            line_temp[COL_ODIFF] = str(o_diff)
            temp_buffer1[ch].append(line_temp)

    # Write pass1.csv
    pass1_path = os.path.join(output_dir, f"{output_name_body}.psg.pass1.csv")
    with open(pass1_path, 'w', newline='\n') as f:
        f.write(PSG_HEADER + '\n')
        for ch in ch_list:
            for row in temp_buffer1[ch]:
                f.write(_row_to_csv(row) + '\n')

    # -------------------------------------------------------
    # Pass 2: filter rows
    # Keep rows where l != 0, OR type in {mode, fCA, fCB}
    # -------------------------------------------------------
    temp_buffer2 = {}
    for ch in ch_list:
        temp_buffer2[ch] = []
        for row in temp_buffer1[ch]:
            type_ = row[COL_TYPE]
            l = _int(row[COL_L])
            if l != 0:
                temp_buffer2[ch].append(row)
            elif type_ in ('mode', 'fCA', 'fCB'):
                temp_buffer2[ch].append(row)

    # Write pass2.csv
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

    mml_buffer1 = {}
    for ch in ch_list:
        mml_buffer1[ch] = []

    ch_offset = 1  # PSG channels displayed as 1-based

    for ch in ch_list:
        note_cnt = 0
        mml = ""
        l_cnt = 0
        o_stamp = 0
        v_stamp = 0

        ch_start = f"\n\n;ch{ch + ch_offset} start"
        mml_buffer1[ch].append(ch_start)

        for row in work_buffer1[ch]:
            type_ = row[COL_TYPE]
            l = _int(row[COL_L])
            v = _int(row[COL_V])
            f = _int(row[COL_F])
            ff = _int(row[COL_FF])
            o = _int(row[COL_O])
            scale = row[COL_SCALE] if row[COL_SCALE] else 'r'
            mode = _int(row[COL_EN])

            noise_freq = get_noise_period(row)
            hw_env_on = get_hw_envelope_on(row)
            hw_env_period = get_hw_envelope_frequency(row)
            hw_env_shape = get_hw_envelope_shape(row)

            if l > 0:
                length = l
                ltmp = l

                if note_cnt == 0:
                    if mode == 0:
                        v = 0
                        mml = f"\n{ch + ch_offset} /0 v{v}"
                    elif mode == 1:
                        mml = f"\n{ch + ch_offset} /1 s{hw_env_shape} m{hw_env_period} v{v}"
                    elif mode == 2:
                        mml = f"\n{ch + ch_offset} /2 s{hw_env_shape} m{hw_env_period} n{noise_freq} v{v}"
                    elif mode == 3:
                        mml = f"\n{ch + ch_offset} /3 s{hw_env_shape} m{hw_env_period} n{noise_freq} v{v}"

                while length > 0:
                    ltmp = min(length, 255)

                    if type_ in ('mode', 'fCA', 'fCB', 'aVC', 'wNC', 'vVC', 'ePL', 'evM ', 'evS'):
                        if mode == 0:
                            v = 0
                        if v != v_stamp and note_cnt != 0:
                            mml += f" v{v}"
                        if o != o_stamp:
                            mml += f" o{o}"
                        mml += f" {scale}%{ltmp}"
                        l_cnt += ltmp

                    length -= ltmp

                    if length >= 0:
                        mml_buffer1[ch].append(mml)
                        mml = ""

                note_cnt += 1
                if note_cnt == 8 or mode == 0:
                    mml_buffer1[ch].append(mml)
                    mml = ""
                    info = f"\n;tick count: {l_cnt}\n"
                    mml_buffer1[ch].append(info)
                    note_cnt = 0

                o_stamp = o
                v_stamp = v

        if mml:
            mml_buffer1[ch].append(mml)

        info = f"\n;ch{ch + ch_offset} end: tick count: {l_cnt}\n"
        mml_buffer1[ch].append(info)

    # Write pass3.mml
    pass3_mml_path = os.path.join(output_dir, f"{output_name_body}.psg.pass3.mml")
    with open(pass3_mml_path, 'w', newline='\n') as f:
        f.write(';[name=scc lpf=1]\n')
        f.write('#opll_mode 1\n')
        f.write('#tempo 75\n')
        f.write('#title { "psg example"}\n')
        f.write('#alloc 1=3100\n')
        f.write('#alloc 2=3100\n')
        f.write('#alloc 3=2400\n')
        f.write('#alloc 4=2100\n')
        f.write('#alloc 5=1100\n')
        f.write('#alloc 6=1000\n')
        f.write('#alloc 7=1000\n')
        f.write('\n')
        for ch in ch_list:
            for item in mml_buffer1[ch]:
                f.write(item)

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
