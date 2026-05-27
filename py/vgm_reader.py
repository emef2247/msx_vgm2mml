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
# OPLL (YM2413) state machine  – melody channels 0..5 (+ ch6..8 in regs)
# ─────────────────────────────────────────────────────────────────
class _OpllState:
    """Track YM2413 (OPLL) register state and emit chronological trace CSVs.

    YM2413 register map coverage
    ─────────────────────────────
    0x00–0x07  user instrument (patch) parameters
    0x0E       rhythm control: bit5=rhythm-mode, bits0–4=rhythm instruments
    0x0F       test register (usually 0)
    0x10–0x18  F-Number low 8 bits  (ch0..8; ch0..5=melody, ch6..8=rhythm)
    0x20–0x28  Fnum MSB + Block + KeyOn + Sustain
    0x30–0x35  Instrument select + volume (melody ch0..5)
    0x36–0x38  Rhythm channel volumes (ch6=BD, ch7=HH/SD, ch8=TOM/CYM)

    Existing trace CSV (*_trace.opll.csv) – kept unchanged for opll_mml.py
    ──────────────────────────────────────────────────────────────────────
    Columns (9):  type, time, ch, ticks, keyon, fnum, block, inst, vol
    Only melody channels 0..5 are emitted here.

    Extended register trace CSV (*_trace.opll_regs.csv) – NEW
    ──────────────────────────────────────────────────────────
    Columns (6):  type, time, ticks, addr, val, ch
      type  – usrPat (0x00-0x07), rhythm (0x0E), test (0x0F),
               fNumL (0x10-0x18), keyBlk (0x20-0x28), instVol (0x30-0x38)
      addr  – register address in hex (e.g. 0x10)
      val   – written value (decimal)
      ch    – channel 0..8, or -1 for global registers (usrPat, rhythm, test)
    All YM2413 writes are captured here so that nothing is lost.

    Voice CSV (*_trace.opll_voice.csv) – unchanged
    ───────────────────────────────────────────────
    Columns (7):  type, time, ch, ticks, inst, vol, patch_hex
      type='patch'   – user-patch register update (ch=-1, global)
      type='instVol' – per-channel inst/vol change with current patch snapshot
    """

    NUM_CH = 9   # 0..8:melody+rhythm

    _HEADER = ('#type,time,ch,ticks,l,fl,kl,vl,beat_pos,beat,fb,kb,vb,keyon,is_legato,is_vibrato,is_portamento,is_envelope,fnum,block,inst,vol,sus,scale,ioi,onset,tempo,'
               'is_ryt,r_tempo,r_ioi,r_mode_ioi,r_hh_ioi,r_hh_mode_ioi,BdSdTomTcHH,'
               'bd,sd,tom,tc,hh,'
               'bd_vol,sd_vol,tom_vol,tc_vol,hh_vol,'
               'fnum_ch6,vol_ch6,sus_ch6,block_ch6,'
               'fnum_ch7,vol_ch7,sus_ch7,block_ch7,'
               'fnum_ch8,vol_ch8,sus_ch8,block_ch8,')
    _VOICE_HEADER = '#type,time,ch,ticks,inst,vol,patch_hex'
    _REGS_HEADER  = '#type,time,ticks,addr,val,ch'

    def __init__(self):
        self._global_time = 0.0
        self._start_time: float | None = None
        self._common_time = 0.0
        self.fnum_low = [0] * self.NUM_CH   # 0x10-0x18 LSB (all ch)
        self.fnum_msb = [0] * self.NUM_CH   # keyBlk[0]...keyBlk[8] LSB (all ch)
        self.sus      = [0] * self.NUM_CH   # sustain bit (keyBlk)
        self.block    = [0] * self.NUM_CH   # block bit (keyBlk)
        self.key_blk  = [0] * self.NUM_CH   # 0x20-0x28
        self.inst_vol = [0] * self.NUM_CH   # 0x30-0x38
        self.user_patch = [0] * 8
        self.rhythm_mode = 0
        self.rhythm_history = []
        self.log_buf = {ch: [] for ch in range(self.NUM_CH)}
        self.trace_buf: list[str] = []
        self.voice_trace_buf: list[str] = []
        self.regs_trace_buf: list[str] = []

    def _update_time(self, time_s: float):
        self._global_time = time_s
        if self._start_time is None:
            self._start_time = time_s
        self._common_time = time_s - self._start_time

    def fnum9(self, ch: int) -> int:
        """Assembled OPLL 9bit F-Number (all ch, will be 0 if not set)."""
        return (self.fnum_low[ch] & 0xFF) | ((self.fnum_msb[ch] & 0x01) << 8)

    def _block(self, ch: int) -> int:
        return (self.key_blk[ch] >> 1) & 0x07

    def _keyon(self, ch: int) -> int:
        return (self.key_blk[ch] >> 4) & 0x01
    
    def _sus(self, ch: int) -> int:
        return (self.key_blk[ch] >> 5) & 0x01

    def _inst(self, ch: int) -> int:
        return (self.inst_vol[ch] >> 4) & 0x0F

    def _vol(self, ch: int) -> int:
        if self.rhythm_mode & ch >= 6:
            return self.inst_vol[ch] & 0xFF
        else:
            return self.inst_vol[ch] & 0x0F

    def _bd_vol(self) -> int:
        return self.inst_vol[6] & 0x0F

    def _sd_vol(self) -> int:
        return self.inst_vol[7] & 0x0F

    def _hh_vol(self) -> int:
        return (self.inst_vol[7] >> 4) & 0x0F

    def _tc_vol(self) -> int:
        return self.inst_vol[8] & 0x0F

    def _tom_vol(self) -> int:
        return (self.inst_vol[8] >> 4) & 0x0F

    def _patch_hex(self) -> str:
        return ''.join(f'{b:02x}' for b in self.user_patch)

    @staticmethod
    def _decode_rhythm_bits(regval):
        is_ryt = (regval >> 5) & 1
        bits = regval & 0x1F
        bd  = (bits >> 4) & 1
        sd  = (bits >> 3) & 1
        tom = (bits >> 2) & 1
        tc  = (bits >> 1) & 1
        hh  = (bits >> 0) & 1
        return is_ryt, bd, sd, tom, tc, hh

    def _rhythm_fields_at_tick(self, ticks):
        last_val = 0
        for t, v in self.rhythm_history:
            if t > ticks:
                break
            last_val = v
        return self._decode_rhythm_bits(last_val)

    def _row(self, ch: int, type_: str) -> str:
        t     = self._common_time
        ticks = get_ticks(t)
        is_ryt, bd, sd, tom, tc, hh = self._rhythm_fields_at_tick(ticks)
        cols = [
            type_, repr(t), str(ch), str(ticks),'','','','','','','','','',
            str(self._keyon(ch)),
            '','','','',
            str(self.fnum9(ch)),
            str(self._block(ch)),
            str(self._inst(ch)),
            str(self._vol(ch)),
            str(self._sus(ch)),
            '','','','',
            str(is_ryt),'','','','','','',
            '', '', '', '', '',
            '', '', '', '', '',
            '', '', '', '',
            '', '', '', '',
            '', '', '', '',
        ]
        return ','.join(cols)

    def _row_rhythm_vol(self, ch: int, type_: str) -> str:
        t     = self._common_time
        ticks = get_ticks(t)
        is_ryt, bd, sd, tom, tc, hh = self._rhythm_fields_at_tick(ticks)
        cols = [
            type_, repr(t), str(ch), str(ticks),'','','', '', '', '', '', '', '','','','','','','','','','','','','','','',
            str(is_ryt),'','','','','','',
            '', '', '', '', '',
            str(self._bd_vol()), str(self._sd_vol()), str(self._tom_vol()), str(self._tc_vol()), str(self._hh_vol()),
            '', '', '', '',
            '', '', '', '',
            '', '', '', '',
        ]
        return ','.join(cols)

    def _log(self, ch: int, type_: str):
        row = self._row(ch, type_)
        self.log_buf[ch].append(row)
        self.trace_buf.append(row)

    def _log_rhythm_vol(self, ch: int, type_: str):
        row = self._row_rhythm_vol(ch, type_)
        self.trace_buf.append(row)

    def _log_rhythm_event(self, type_: str, regval: int):
        t     = self._common_time
        ticks = get_ticks(t)
        BdSdTomTcHH = f"0x{(regval & 0x1F):02X}"
        is_ryt, bd, sd, tom, tc, hh = self._decode_rhythm_bits(regval)
        cols = [
            type_, repr(t), '-1', str(ticks),'','','', '', '', '', '', '', '','','','','','','','','','','','','','','',
            str(is_ryt),'','','','','',BdSdTomTcHH,
            str(bd), str(sd), str(tom), str(tc), str(hh),
            str(self._bd_vol()), str(self._sd_vol()), str(self._tom_vol()), str(self._tc_vol()), str(self._hh_vol()),
            str(self.fnum9(6)), str(self._vol(6)), str(self._sus(6)), str(self._block(6)),
            str(self.fnum9(7)), str(self._vol(7)), str(self._sus(7)), str(self._block(7)),
            str(self.fnum9(8)), str(self._vol(8)), str(self._sus(8)), str(self._block(8)),
        ]
        self.trace_buf.append(','.join(cols))

    def _voice_row(self, type_: str, ch: int, inst: int, vol: int) -> str:
        t     = self._common_time
        ticks = get_ticks(t)
        cols = [
            type_, repr(t), str(ch), str(ticks),
            str(inst), str(vol), self._patch_hex(),
        ]
        return ','.join(cols)

    def _regs_row(self, type_: str, addr: int, val: int, ch: int) -> str:
        t = self._common_time
        ticks = get_ticks(t)
        cols = [type_, repr(t), str(ticks), f'0x{addr:02X}', str(val), str(ch)]
        return ','.join(cols)

    def write(self, time_s: float, address: int, value: int):
        self._update_time(time_s)
        a = address
        v = value

        _ch = -1
        _type = 'raw'

        if 0x00 <= a <= 0x07:
            _type, _ch = 'usrPat', -1
            self.user_patch[a] = v & 0xFF
            row = self._voice_row('patch', -1, 0, 0)
            self.voice_trace_buf.append(row)

        elif a == 0x0E:
            # rhythm control (bit5 = rhythm_mode)
            _type, _ch = 'rhythm', -1

        elif a == 0x0F:
            _type, _ch = 'test', -1

        elif 0x10 <= a <= 0x18:
            ch = a - 0x10
            _type, _ch = 'fNumL', ch
            self.fnum_low[ch] = v & 0xFF

            # ch6–8: rhythm_mode=1 のときは記録しない
            if not (self.rhythm_mode and ch >= 6):
                self._log(ch, 'fNumL')

        elif 0x20 <= a <= 0x28:
            ch = a - 0x20
            _type, _ch = 'keyBlk', ch
            self.key_blk[ch]  = v & 0x3F
            self.fnum_msb[ch] = v & 0x01
            self.sus[ch]      = (v >> 5) & 0x01
            self.block[ch]    = (v >> 1) & 0x07

            # ch6–8: rhythm_mode=1 の時は記録しない
            if not (self.rhythm_mode and ch >= 6):
                self._log(ch, 'keyBlk')

        elif 0x30 <= a <= 0x38:
            ch = a - 0x30
            if not self.rhythm_mode:
                _type, _ch = 'instVol', ch
                self.inst_vol[ch] = v & 0xFF
                self._log(ch, 'instVol')
                row = self._voice_row('instVol', ch, self._inst(ch), self._vol(ch))
                self.voice_trace_buf.append(row)
            elif ch < 6:
                _type, _ch = 'instVol', ch
                self.inst_vol[ch] = v & 0xFF
                self._log(ch, 'instVol')
                row = self._voice_row('instVol', ch, self._inst(ch), self._vol(ch))
                self.voice_trace_buf.append(row)
            else :
                _type, _ch = 'rhythmVol', ch
                self.inst_vol[ch] = v & 0xFF
                self._log_rhythm_vol(ch, 'rhythmVol')

        # 全レジスタの生トレース
        self.regs_trace_buf.append(self._regs_row(_type, a, v, _ch))

        # Rhythm レジスタ (0x0E) の実処理
        if a == 0x0E:
            self.rhythm_mode = (v >> 5) & 1
            t = self._common_time
            ticks = get_ticks(t)
            self.rhythm_history.append((ticks, v))
            self._log_rhythm_event('rhythm', v)


    def output_trace_csv(self, out_path: str):
        header = self._HEADER
        with open(out_path, 'w', newline='\n') as fh:
            fh.write(header + '\n')
            for row in self.trace_buf:
                fh.write(row + '\n')

    def output_log_csv(self, out_path: str):
        header = self._HEADER
        with open(out_path, 'w', newline='\n') as fh:
            fh.write(header + '\n')
            for ch in range(self.NUM_CH):
                for row in self.log_buf[ch]:
                    fh.write(row + '\n')
                fh.write('\n')

    def output_voice_csv(self, out_path: str):
        with open(out_path, 'w', newline='\n') as fh:
            fh.write(self._VOICE_HEADER + '\n')
            for row in self.voice_trace_buf:
                fh.write(row + '\n')

    def output_regs_csv(self, out_path: str):
        with open(out_path, 'w', newline='\n') as fh:
            fh.write(self._REGS_HEADER + '\n')
            for row in self.regs_trace_buf:
                fh.write(row + '\n')

# ─────────────────────────────────────────────────────────────────
# VGM parser
# ─────────────────────────────────────────────────────────────────

def parse_vgm(vgm_path: str, output_dir: str | None = None) -> tuple[str, str, str, str, str, str, str, str]:
    """
    Parse a VGM file and write PSG, SCC, and OPLL log/trace CSVs.

    Returns:
        (psg_log_csv, scc_log_csv, psg_trace_csv, scc_trace_csv,
         opll_log_csv, opll_trace_csv, opll_voice_csv, opll_regs_csv)

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

    # VGM spec: if a chip's clock is 0, the chip is not installed and its
    # data commands must be ignored.
    #
    # K051649 (SCC/SCC+) clock is at header offset 0xCC, added in VGM 1.61.
    # Only process 0xD2 (K051649) commands when the clock is non-zero.
    vgm_version = struct.unpack_from('<I', raw, 0x08)[0] if len(raw) >= 0x0C else 0
    has_k051649 = False
    if vgm_version >= 0x161 and len(raw) >= 0xD0:
        k051649_clock = struct.unpack_from('<I', raw, 0xCC)[0]
        has_k051649 = (k051649_clock != 0)

    # ── Process data stream ──────────────────────────────────────
    psg  = _PsgState()
    scc  = _SccState()
    opll = _OpllState()
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
        elif cmd == 0x51:
            aa = raw[pos]; pos += 1
            dd = raw[pos]; pos += 1
            opll.write(global_time, aa, dd)
        elif cmd == 0xD2:
            pp = raw[pos]; pos += 1
            aa = raw[pos]; pos += 1
            dd = raw[pos]; pos += 1
            # Only route to SCC state machine when the K051649 chip is
            # declared in the VGM header.  A clock of 0 means the chip is
            # absent; writing to it would produce spurious SCC output.
            if has_k051649:
                base = {0: 0x9800, 1: 0x9880, 2: 0x988A, 3: 0x988F}.get(pp, 0x9800)
                scc.write_scc(global_time, base + aa, dd)
        # Other commands: single byte already consumed, skip

    # ── Write CSVs ───────────────────────────────────────────────
    base_name = os.path.splitext(os.path.basename(vgm_path))[0]
    if output_dir is None:
        output_dir = os.path.dirname(os.path.abspath(vgm_path))
    os.makedirs(output_dir, exist_ok=True)

    psg_log_csv    = os.path.join(output_dir, f"{base_name}_log.psg.csv")
    scc_log_csv    = os.path.join(output_dir, f"{base_name}_log.scc.csv")
    psg_trace_csv  = os.path.join(output_dir, f"{base_name}_trace.psg.csv")
    scc_trace_csv  = os.path.join(output_dir, f"{base_name}_trace.scc.csv")
    opll_log_csv   = os.path.join(output_dir, f"{base_name}_log.opll.csv")
    opll_trace_csv = os.path.join(output_dir, f"{base_name}_trace.opll.csv")

    psg.output_csv(psg_log_csv)
    psg.output_trace_csv(psg_trace_csv)
    scc.output_csv(scc_log_csv)
    scc.output_trace_csv(scc_trace_csv)
    opll.output_log_csv(opll_log_csv)
    opll.output_trace_csv(opll_trace_csv)
    opll_voice_csv = os.path.join(output_dir, f"{base_name}_trace.opll_voice.csv")
    opll.output_voice_csv(opll_voice_csv)
    opll_regs_csv = os.path.join(output_dir, f"{base_name}_trace.opll_regs.csv")
    opll.output_regs_csv(opll_regs_csv)

    return (psg_log_csv, scc_log_csv, psg_trace_csv, scc_trace_csv,
            opll_log_csv, opll_trace_csv, opll_voice_csv, opll_regs_csv)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(f"Usage: python {sys.argv[0]} <vgm_file> [output_dir]")
        sys.exit(1)
    p_log, s_log, p_trace, s_trace, o_log, o_trace, o_voice, o_regs = parse_vgm(
        sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
    print(f"PSG log CSV:       {p_log}")
    print(f"SCC log CSV:       {s_log}")
    print(f"SCC trace CSV:     {s_trace}")
    print(f"OPLL log CSV:      {o_log}")
    print(f"OPLL trace CSV:    {o_trace}")
    print(f"OPLL voice CSV:    {o_voice}")
    print(f"OPLL regs CSV:     {o_regs}")
