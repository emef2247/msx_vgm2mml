"""
vgm_reader.py - Port of vgm_read.tcl + psg.tcl + scc.tcl
Parse a VGM binary file and produce PSG and SCC log/trace CSVs.
Usage: python vgm_reader.py <vgm_file> [output_dir]

Log CSV  (*_log.scc.csv)  : events grouped by channel (Tcl scc.tcl output)
Trace CSV (*_trace.scc.csv): events in chronological VGM-stream order (Tcl trace)

Note: 0x77 and 0x7a wait commands are intentionally treated as 0-sample waits
to match the reference Tcl vgm_read.tcl behaviour (these handlers omit the
update_global_time call in the Tcl source).
"""
import struct
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from mml_utils import get_ticks


# ─────────────────────────────────────────────────────────────────
# PSG state machine  (mirrors psg.tcl)
# ─────────────────────────────────────────────────────────────────

class _PsgState:
    NUM_CH = 3

    def __init__(self):
        self._global_time = 0.0
        self._start_time  = 0.0
        self._common_time = 0.0

        # registers (broadcast regs are stored per-channel for easy CSV output)
        self.fCtrlA      = [85, 0, 0]    # ch0 initialises to 85
        self.fCtrlB      = [0,  0, 0]
        self.wNCtrl      = [0,  0, 0]
        self.vVCtrl      = [187, 187, 187]
        self.aVCtrl      = [0,  0, 0]
        self.envPCtrlL   = [11, 11, 11]
        self.envPCtrlM   = [0,  0, 0]
        self.envShape    = [0,  0, 0]
        self.ioParallel1 = [0,  0, 0]
        self.ioParallel2 = [0,  0, 0]
        self.psgMode     = [self._calc_mode(ch, 187) for ch in range(self.NUM_CH)]

        self.log_buf = {ch: [] for ch in range(self.NUM_CH)}
        self.trace_buf: list[str] = []   # chronological (all channels)

    # ── time ────────────────────────────────────────────────────
    def _update_time(self, time_s: float):
        self._global_time = time_s
        if self._start_time == 0:
            self._start_time = time_s
        self._common_time = time_s - self._start_time

    # ── PSG mode from vVCtrl ────────────────────────────────────
    @staticmethod
    def _calc_mode(ch: int, reg: int) -> int:
        mask = 1 << ch            # 1, 2, 4 for ch 0, 1, 2
        noise_mute = bool((reg >> 3) & mask)
        tone_mute  = bool(reg & mask)
        # noiseMute*2 + toneMute → 0→3, 1→2, 2→1, 3→0
        return [3, 2, 1, 0][int(noise_mute) * 2 + int(tone_mute)]

    # ── CSV row builder ─────────────────────────────────────────
    def _row(self, ch: int, type_: str) -> str:
        t     = self._common_time
        ticks = get_ticks(t)
        mode  = self.psgMode[ch]
        cols = [
            type_, repr(t), str(ch), str(ticks),
            '', '', '', '', '', '', '', '',           # 4-11 empty
            str(mode),
            '', '', '', '', '', '', '', '', '', '', '',  # 13-23 empty
            str(self.fCtrlA[ch]),
            str(self.fCtrlB[ch]),
            str(self.wNCtrl[ch]),
            str(self.vVCtrl[ch]),
            str(self.aVCtrl[ch]),
            str(self.envPCtrlL[ch]),
            str(self.envPCtrlM[ch]),
            str(self.envShape[ch]),
            str(self.ioParallel1[ch]),
            str(self.ioParallel2[ch]),
        ]
        return ','.join(cols)   # 34 fields

    # ── main write entry point ───────────────────────────────────
    def write(self, time_s: float, address: int, value: int):
        self._update_time(time_s)
        a = address
        v = value

        if   a == 0:  self._set_fCtrlA(0, v)
        elif a == 1:  self._set_fCtrlB(0, v)
        elif a == 2:  self._set_fCtrlA(1, v)
        elif a == 3:  self._set_fCtrlB(1, v)
        elif a == 4:  self._set_fCtrlA(2, v)
        elif a == 5:  self._set_fCtrlB(2, v)
        elif a == 6:
            for ch in range(self.NUM_CH):
                self._set_wNCtrl(ch, v)
        elif a == 7:
            for ch in range(self.NUM_CH):
                self._set_vVCtrl(ch, v)
        elif a == 8:  self._set_aVCtrl(0, v)
        elif a == 9:  self._set_aVCtrl(1, v)
        elif a == 10: self._set_aVCtrl(2, v)
        elif a == 11:
            for ch in range(self.NUM_CH):
                self._set_envPCtrlL(ch, v)
        elif a == 12:
            for ch in range(self.NUM_CH):
                self._set_envPCtrlM(ch, v)
        elif a == 13:
            for ch in range(self.NUM_CH):
                self._set_envShape(ch, v)
        elif a == 14:
            for ch in range(self.NUM_CH):
                self._set_ioParallel1(ch, v)
        elif a == 15:
            for ch in range(self.NUM_CH):
                self._set_ioParallel2(ch, v)

    def _set_fCtrlA(self, ch, v):
        self.fCtrlA[ch] = v
        row = self._row(ch, 'fCA')
        self.log_buf[ch].append(row)
        self.trace_buf.append(row)

    def _set_fCtrlB(self, ch, v):
        self.fCtrlB[ch] = v
        row = self._row(ch, 'fCB')
        self.log_buf[ch].append(row)
        self.trace_buf.append(row)

    def _set_wNCtrl(self, ch, v):
        self.wNCtrl[ch] = v
        row = self._row(ch, 'wNC')
        self.log_buf[ch].append(row)
        self.trace_buf.append(row)

    def _set_vVCtrl(self, ch, v):
        self.vVCtrl[ch] = v
        new_mode = self._calc_mode(ch, v)
        if new_mode != self.psgMode[ch]:
            self.psgMode[ch] = new_mode
            row = self._row(ch, 'mode')
            self.log_buf[ch].append(row)
            self.trace_buf.append(row)

    def _set_aVCtrl(self, ch, v):
        self.aVCtrl[ch] = v
        row = self._row(ch, 'aVC')
        self.log_buf[ch].append(row)
        self.trace_buf.append(row)

    def _set_envPCtrlL(self, ch, v):
        self.envPCtrlL[ch] = v
        row = self._row(ch, 'ePL')
        self.log_buf[ch].append(row)
        self.trace_buf.append(row)

    def _set_envPCtrlM(self, ch, v):
        self.envPCtrlM[ch] = v
        row = self._row(ch, 'evM')
        self.log_buf[ch].append(row)
        self.trace_buf.append(row)

    def _set_envShape(self, ch, v):
        self.envShape[ch] = v
        row = self._row(ch, 'evS')
        self.log_buf[ch].append(row)
        self.trace_buf.append(row)

    def _set_ioParallel1(self, ch, v):
        self.ioParallel1[ch] = v
        row = self._row(ch, 'ioP1')
        self.log_buf[ch].append(row)
        self.trace_buf.append(row)

    def _set_ioParallel2(self, ch, v):
        self.ioParallel2[ch] = v
        row = self._row(ch, 'ioP2')
        self.log_buf[ch].append(row)
        self.trace_buf.append(row)

    # ── CSV output ───────────────────────────────────────────────
    def output_csv(self, out_path: str):
        hdr = ('#type,time,ch,ticks,l,fL,v,fV,f,fF,o,scale,en,fEn,vDiff,vCnt,'
               'oDiff,envlp,envlpIndex,nE,nF,offset,data,wtbIndex,'
               'fCtrlA,fCtrlB,wNCtrl,vVCtrl,aVCtrl,envPCtrlL,envPCtrlM,'
               'envShape,ioParallel1,ioParallel2')
        with open(out_path, 'w', newline='\n') as fh:
            fh.write(hdr + '\n')
            for ch in range(self.NUM_CH):
                for row in self.log_buf[ch]:
                    fh.write(row + '\n')
                fh.write('\n')

    def output_trace_csv(self, out_path: str):
        """Write chronological trace CSV (all channels interleaved by time)."""
        hdr = ('#type,time,ch,ticks,l,fL,v,fV,f,fF,o,scale,en,fEn,vDiff,vCnt,'
               'oDiff,envlp,envlpIndex,nE,nF,offset,data,wtbIndex,'
               'fCtrlA,fCtrlB,wNCtrl,vVCtrl,aVCtrl,envPCtrlL,envPCtrlM,'
               'envShape,ioParallel1,ioParallel2')
        with open(out_path, 'w', newline='\n') as fh:
            fh.write(hdr + '\n')
            for row in self.trace_buf:
                fh.write(row + '\n')


# ─────────────────────────────────────────────────────────────────
# SCC state machine  (mirrors scc.tcl)
# ─────────────────────────────────────────────────────────────────

class _SccState:
    NUM_CH = 4

    def __init__(self):
        self._global_time = 0.0
        self._start_time  = 0.0
        self._common_time = 0.0

        self.f1Ctrl  = [0] * self.NUM_CH
        self.f2Ctrl  = [0] * self.NUM_CH
        self.vCtrl   = [0] * self.NUM_CH
        self.enCtrl  = [0] * self.NUM_CH
        self.enBit   = [0] * self.NUM_CH

        self.wtb_offset = [0] * self.NUM_CH
        self.wtb_last   = [0] * self.NUM_CH
        self.wtbl_index = [0] * self.NUM_CH   # index into global table

        # global registry of completed 32-byte waveforms (hex strings)
        self._wtbl_bytes_list: list[str] = []
        # current accumulating waveform (list of 2-char hex strings)
        self._cur_wtbl: list[str] = []

        self.log_buf = {ch: [] for ch in range(self.NUM_CH)}
        self.trace_buf: list[str] = []   # chronological (all channels)

    # ── time ────────────────────────────────────────────────────
    def _update_time(self, time_s: float):
        self._global_time = time_s
        if self._start_time == 0:
            self._start_time = time_s
        self._common_time = time_s - self._start_time

    # ── SCC enable bit ───────────────────────────────────────────
    @staticmethod
    def _enable_bit(ch: int, reg: int) -> int:
        ch_val = ch + 1        # 1, 2, 3, 4 for ch 0, 1, 2, 3
        return 1 if (reg & ch_val) == ch_val else 0

    # ── wavetable helpers ────────────────────────────────────────
    def _get_wtbl_index(self, key: str) -> int:
        try:
            return self._wtbl_bytes_list.index(key)
        except ValueError:
            return len(self._wtbl_bytes_list)

    def _new_wavetable(self, ch: int, data: int):
        self._cur_wtbl = [format(data & 0xFF, '02x')]
        self.wtb_offset[ch] = 0

    def _append_wavetable(self, ch: int, data: int):
        self._cur_wtbl.append(format(data & 0xFF, '02x'))
        self.wtb_offset[ch] = len(self._cur_wtbl) - 1
        if len(self._cur_wtbl) == 32:
            key = ''.join(self._cur_wtbl)
            if key not in self._wtbl_bytes_list:
                self._wtbl_bytes_list.append(key)
            self.wtbl_index[ch] = self._get_wtbl_index(key)

    # ── CSV row builder ─────────────────────────────────────────
    def _row(self, ch: int, type_: str) -> str:
        t     = self._common_time
        ticks = get_ticks(t)
        cols = [
            type_, repr(t), str(ch), str(ticks),
            '', '', '', '', '', '', '', '',          # 4-11 empty
            str(self.enBit[ch]),
            '', '', '', '', '', '', '', '',          # 13-20 empty
            str(self.wtb_offset[ch]),
            str(self.wtb_last[ch]),
            str(self.wtbl_index[ch]),
            str(self.f1Ctrl[ch]),
            str(self.f2Ctrl[ch]),
            str(self.vCtrl[ch]),
            str(self.enCtrl[ch]),
        ]
        return ','.join(cols)   # 28 fields

    def _log(self, ch: int, type_: str):
        """Append a row to both the per-channel log buffer and the trace buffer."""
        row = self._row(ch, type_)
        self.log_buf[ch].append(row)
        self.trace_buf.append(row)

    # ── main write entry point ───────────────────────────────────
    def write_scc(self, time_s: float, address: int, value: int):
        self._update_time(time_s)
        a = address

        # Wavetable ch0
        if a == 0x9800:
            ch = 0
            self._new_wavetable(ch, value)
            self.wtb_last[ch] = value
            self._log(ch, 'wtbNew')
            return
        if 0x9800 < a < 0x9820:
            ch = 0
            self._append_wavetable(ch, value)
            self.wtb_last[ch] = value
            self._log(ch, 'wtbLast')
            return
        # Wavetable ch1
        if a == 0x9820:
            ch = 1
            self._new_wavetable(ch, value)
            self.wtb_last[ch] = value
            self._log(ch, 'wtbNew')
            return
        if 0x9820 < a < 0x9840:
            ch = 1
            self._append_wavetable(ch, value)
            self.wtb_last[ch] = value
            self._log(ch, 'wtbLast')
            return
        # Wavetable ch2
        if a == 0x9840:
            ch = 2
            self._new_wavetable(ch, value)
            self.wtb_last[ch] = value
            self._log(ch, 'wtbNew')
            return
        if 0x9840 < a < 0x9860:
            ch = 2
            self._append_wavetable(ch, value)
            self.wtb_last[ch] = value
            self._log(ch, 'wtbLast')
            return
        # Wavetable ch3
        if a == 0x9860:
            ch = 3
            self._new_wavetable(ch, value)
            self.wtb_last[ch] = value
            self._log(ch, 'wtbNew')
            return
        if 0x9860 < a < 0x9880:
            ch = 3
            self._append_wavetable(ch, value)
            self.wtb_last[ch] = value
            self._log(ch, 'wtbLast')
            return

        # Frequency registers
        if   a == 0x9880: ch = 0; self.f1Ctrl[ch] = value; self._log(ch, 'f1Ctrl'); return
        if   a == 0x9881: ch = 0; self.f2Ctrl[ch] = value; self._log(ch, 'f2Ctrl'); return
        if   a == 0x9882: ch = 1; self.f1Ctrl[ch] = value; self._log(ch, 'f1Ctrl'); return
        if   a == 0x9883: ch = 1; self.f2Ctrl[ch] = value; self._log(ch, 'f2Ctrl'); return
        if   a == 0x9884: ch = 2; self.f1Ctrl[ch] = value; self._log(ch, 'f1Ctrl'); return
        if   a == 0x9885: ch = 2; self.f2Ctrl[ch] = value; self._log(ch, 'f2Ctrl'); return
        if   a == 0x9886: ch = 3; self.f1Ctrl[ch] = value; self._log(ch, 'f1Ctrl'); return
        if   a == 0x9887: ch = 3; self.f2Ctrl[ch] = value; self._log(ch, 'f2Ctrl'); return

        # Volume registers
        if   a == 0x988A: ch = 0; self.vCtrl[ch] = value; self._log(ch, 'vCtrl'); return
        if   a == 0x988B: ch = 1; self.vCtrl[ch] = value; self._log(ch, 'vCtrl'); return
        if   a == 0x988C: ch = 2; self.vCtrl[ch] = value; self._log(ch, 'vCtrl'); return
        if   a == 0x988D: ch = 3; self.vCtrl[ch] = value; self._log(ch, 'vCtrl'); return

        # Enable register (broadcast)
        if a == 0x988F:
            for ch in range(self.NUM_CH):
                self.enCtrl[ch] = value
                new_bit = self._enable_bit(ch, value)
                if new_bit != self.enBit[ch]:
                    self.enBit[ch] = new_bit
                    self._log(ch, 'enBit')

    # ── CSV output ───────────────────────────────────────────────
    def output_csv(self, out_path: str):
        """Write per-channel grouped log CSV (Tcl *_log.scc.csv format)."""
        hdr = ('#type,time,ch,ticks,l,fL,v,fV,f,fF,o,scale,en,fEn,vDiff,vCnt,'
               'oDiff,envlp,envlpIndex,nE,nF,offset,data,wtblIndex,'
               'f1Ctrl,f2Ctrl,vCtrl,enCtrl')
        with open(out_path, 'w', newline='\n') as fh:
            fh.write(hdr + '\n')
            for ch in range(self.NUM_CH):
                for row in self.log_buf[ch]:
                    fh.write(row + '\n')
                fh.write('\n')

    def output_trace_csv(self, out_path: str):
        """Write chronological trace CSV (Tcl *_trace.scc.csv format)."""
        hdr = ('#type,time,ch,ticks,l,fL,v,fV,f,fF,o,scale,en,fEn,vDiff,vCnt,'
               'oDiff,envlp,envlpIndex,nE,nF,offset,data,wtblIndex,'
               'f1Ctrl,f2Ctrl,vCtrl,enCtrl')
        with open(out_path, 'w', newline='\n') as fh:
            fh.write(hdr + '\n')
            for row in self.trace_buf:
                fh.write(row + '\n')


# ─────────────────────────────────────────────────────────────────
# VGM parser
# ─────────────────────────────────────────────────────────────────

def parse_vgm(vgm_path: str, output_dir: str | None = None) -> tuple[str, str, str, str]:
    """
    Parse a VGM file and write PSG and SCC log/trace CSVs.

    Returns:
        (psg_log_csv, scc_log_csv, psg_trace_csv, scc_trace_csv)

    Note: 0x77 and 0x7a wait commands are treated as 0-sample waits to match
    the reference Tcl vgm_read.tcl behaviour (see module docstring).
    """
    with open(vgm_path, 'rb') as fh:
        raw = fh.read()

    # ── Header ──────────────────────────────────────────────────
    # VGM_data_offset field is at absolute byte 0x34 (4-byte LE).
    # Data starts at absolute offset:  0x34 + VGM_data_offset.
    vgm_data_offset = struct.unpack_from('<I', raw, 0x34)[0]
    data_start = 0x34 + vgm_data_offset

    # ── Process data stream ──────────────────────────────────────
    psg = _PsgState()
    scc = _SccState()
    global_time = 0.0
    pos = data_start

    while pos < len(raw):
        cmd = raw[pos]; pos += 1

        if cmd == 0x66:
            break
        elif cmd == 0x61:
            nn = struct.unpack_from('<H', raw, pos)[0]; pos += 2
            global_time += nn / 44100.0
        elif cmd == 0x62:
            global_time += 735 / 44100.0
        elif cmd == 0x63:
            global_time += 882 / 44100.0
        elif 0x70 <= cmd <= 0x7F:
            # 0x77 and 0x7a: the Tcl vgm_read.tcl handlers compute a local
            # time variable but never call update_global_time, so they
            # effectively add 0 samples.  Replicate that behaviour here so
            # the Python-generated trace CSV is byte-for-byte identical to
            # the Tcl reference.
            if cmd not in (0x77, 0x7a):
                global_time += ((cmd & 0xF) + 1) / 44100.0
        elif cmd == 0xA0:
            aa = raw[pos]; pos += 1
            dd = raw[pos]; pos += 1
            psg.write(global_time, aa, dd)
        elif cmd == 0xD2:
            pp = raw[pos]; pos += 1
            aa = raw[pos]; pos += 1
            dd = raw[pos]; pos += 1
            base = {0: 0x9800, 1: 0x9880, 2: 0x988A, 3: 0x988F}.get(pp, 0x9800)
            scc.write_scc(global_time, base + aa, dd)
        # Other commands: single byte already consumed, skip

    # ── Write CSVs ───────────────────────────────────────────────
    base_name = os.path.splitext(os.path.basename(vgm_path))[0]
    if output_dir is None:
        output_dir = os.path.dirname(os.path.abspath(vgm_path))
    os.makedirs(output_dir, exist_ok=True)

    psg_log_csv   = os.path.join(output_dir, f"{base_name}_log.psg.csv")
    scc_log_csv   = os.path.join(output_dir, f"{base_name}_log.scc.csv")
    psg_trace_csv = os.path.join(output_dir, f"{base_name}_trace.psg.csv")
    scc_trace_csv = os.path.join(output_dir, f"{base_name}_trace.scc.csv")

    psg.output_csv(psg_log_csv)
    psg.output_trace_csv(psg_trace_csv)
    scc.output_csv(scc_log_csv)
    scc.output_trace_csv(scc_trace_csv)
    return psg_log_csv, scc_log_csv, psg_trace_csv, scc_trace_csv


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(f"Usage: python {sys.argv[0]} <vgm_file> [output_dir]")
        sys.exit(1)
    p_log, s_log, p_trace, s_trace = parse_vgm(
        sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
    print(f"PSG log CSV:   {p_log}")
    print(f"SCC log CSV:   {s_log}")
    print(f"SCC trace CSV: {s_trace}")
