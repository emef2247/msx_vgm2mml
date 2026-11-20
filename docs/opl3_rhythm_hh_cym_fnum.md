> Archived 2026-11-21 from the OPL3 calibration workspace
> (opl3_preset_explore/hh_cym_fnum_check/). The analysis scripts
> (parse_vgm.py, analyze3.py) and the WAV renders stay in that
> workspace; the figures are archived alongside this document.

# FMPAC02 OPL3 rhythm HH/CYM — fnum investigation

Analysis only; no repository code was modified. All register values below were
extracted from the VGM files themselves (parser: `parse_vgm.py` in this
directory) and cross-checked against the raw write census of each file.
Audio figures come from `analyze3.py` plus a multi-hit averaged-spectrum pass;
figures: `HH_hit.png`, `CYM_hit.png`, `avg_spectra.png`.

Hit counts and hit times are identical in all three VGMs (HH 168 hits,
CYM 43, BD 128; e.g. first isolated HH hit at 6.420 s, CYM hit at 12.820 s in
every file), so the three renders are directly comparable hit-by-hit.

## 1. The fnum comparison (state in effect at the hits)

Formulas: OPLL f = fnum·(3579545/72)/2^(19−block);
OPL3 f = fnum·(14318180/288)/2^(20−block).

| channel | original YM2413 | current OPL3 | source-pitch OPL3 |
|---|---|---|---|
| ch6 (BD) | fnum 288, block 2 → **109.2 Hz** | fnum 608, block 1 → **57.7 Hz** (0.53×) | fnum 576, block 2 → **109.2 Hz** ✓ |
| ch7 at HH hits | fnum 336, block 2 → **127.4 Hz** | fnum 624, block 1 → **59.2 Hz** (0.46×) | fnum 672, block 2 → **127.4 Hz** ✓ |
| ch8 at CYM hits | fnum 448, block 0 → **42.5 Hz** | fnum 880, block 1 → **83.4 Hz** (1.96×) | fnum 896, block 0 → **42.5 Hz** ✓ |
| ch7 at CYM hits (partner) | fnum 336, block 2 → **127.4 Hz** | fnum 896, block 4 → **679.7 Hz** (5.34×) | fnum 672, block 2 → **127.4 Hz** ✓ |

In the original, the at-hit state is 100 % consistent (168/168 HH hits see
ch7 = (336,2); 43/43 CYM hits see ch8 = (448,0), ch7 = (336,2)). The only
other states in the file are brief initialisation transients before the song
settles (e.g. (288,3) for a few writes at the start).

## 2. Does the conversion machinery land where it intends?

Yes — the machinery is Hz-exact; the divergence is in the table values
themselves.

- The current files contain the fixed-table frequencies exactly: HH 59.2 Hz,
  CYM 83.4 Hz + partner 679.7 Hz, BD 57.7 Hz. (The (fnum, block) pair is
  sometimes re-encoded — e.g. BD's table entry (304,2) appears in the file as
  (608,1) — because `_pitch` picks the smallest block with fnum ≤ 1023 in the
  OPL3 frame; the resulting Hz is identical, 57.7 Hz either way. A (fnum,
  block) pair also yields the same Hz in the Y8950 "/144 frame" and on OPL3,
  since 14318180/288/2^(20−block) = 3579545/144/2^(19−block).)
- The source-pitch override **did** reach the files, re-encoded the same way
  (e.g. its (336,3) appears as (672,2)), and it reproduces the original
  performance's Hz **exactly** on all three channels (109.2 / 127.4 / 42.5 Hz).
- So the current table simply aims at different frequencies than the original
  performance plays: HH −1.1 octaves (59.2 vs 127.4), CYM +0.97 octaves
  (83.4 vs 42.5), CYM partner +2.4 octaves (679.7 vs 127.4), BD −0.92 octaves
  (57.7 vs 109.2). These table values came from the Y8950-era fits, not from
  this performance.

## 3. Multipliers (MUL)

Both conversions write the identical MUL set once at setup (register 0x20+off,
low nibble; OPL MUL encoding 0=×0.5, 14=×15):

| op | offset | MUL reg | factor |
|---|---|---|---|
| ch6 mod | 16 | 2 | ×2 |
| ch6 car | 19 | 0 | ×0.5 |
| ch7 mod | 17 | 14 | **×15** |
| ch7 car | 20 | 0 | ×0.5 |
| ch8 mod | 18 | 5 | ×5 |
| ch8 car | 21 | 6 | ×6 |

No waveform-select writes (0xE0+) appear, so all rhythm ops use waveform 0.
On the YM2413 the rhythm channels' multipliers are **not register-programmable**
— they are the chip's internal rhythm-patch behaviour; the file's user-patch
registers 0x00/0x01 (MULT=1) belong to the melody user patch, and in rhythm
mode the 0x36–0x38 high nibbles are percussion volumes, not instrument selects.
So there is no original MUL to copy from the file; the reference render is the
only evidence of the original's effective behaviour (see §4).

Effective phase rates of the HH/CYM noise-XOR sources on OPL3
(f_channel × MUL of the driving modulator op):

- HH (ch7 mod, ×15): current 59.2×15 = **888 Hz**; source-pitch 127.4×15 =
  **1911 Hz**.
- CYM partner contribution (ch7 mod, ×15): current 679.7×15 ≈ 10.2 kHz;
  source-pitch **1911 Hz**. CYM's own ch8 car (×6): current 500 Hz;
  source-pitch 255 Hz.

## 4. Waveform / spectrum observations

Single hits at the same musical position (HH 6.420 s, CYM 12.820 s) plus
spectra averaged over all hits. Spectral centroids are nearly identical in
all versions (HH 7.6–8.1 kHz; CYM 7.7–8.0 kHz) — overall "brightness" is not
what differs. What differs is **discrete line structure**:

**HH**
- Reference: averaged spectrum is noise with a *weak, dense* line series on a
  ~680 Hz grid (2039, 3398, 5438, 7477, 8836, 10876 Hz = 3,5,8,11,13,16 ×
  680 Hz; 680 Hz = 16 × ch8's 42.5 Hz). Lines stand only ~15–20 dB over the
  noise floor. Waveform is strongly asymmetric/unipolar (DC ≈ 47 % of peak
  over the first 100 ms, vs 4–5 % in the conversions) — a raw, "dirty" noise
  signal. Autocorrelation shows no strong period (strength 0.33).
- Current: averaged spectrum is dominated by **two very strong narrow lines
  at ≈3.55 kHz and ≈10.6 kHz** (series n × 3550 Hz, reaching ~30 dB over the
  noise floor), i.e. a definite pitched ring — the "iron bar". The 3550 Hz
  spacing is exactly 60 × f_ch7 = 4 × (59.2 Hz × MUL 15). Waveform is a clean
  bipolar noise burst decaying over ~40 ms. Autocorrelation strength 0.68 at
  the 888 Hz phase rate.
- Source-pitch: same kind of line series, spacing ≈3830 Hz = 30 × f_ch7 =
  2 × (127.4 × 15), lines ~25 dB over the floor at 3.8 / 7.7 / 11.5 / 15.3 kHz.
  Still clearly pitched, slightly less extreme than current — matching the
  user's "slightly less metallic, still metallic".

**CYM**
- Reference: attack with visible oscillation, decaying in ~20 ms to a low
  sustained noise tail. Its averaged spectrum carries the **same line series
  as the reference HH** (2039/3398/5438/7477/8836/10876 Hz) — the periodic
  content is a property of the shared noise-XOR mechanism, not of either
  channel alone. Tail (30–80 ms) autocorrelation period ≈170 Hz = 4 × 42.5 Hz.
- Current: channel rate is genuinely ~1 octave high (83.4 vs 42.5 Hz) with the
  partner at 679.7 Hz; waveform sustains a denser, louder tail (with a
  persistent negative offset) instead of the reference's decay-to-low-tail.
  Tail period ≈882 Hz.
- Source-pitch: channel rates are exactly the original's, yet it still
  measures top-heavy vs the reference (band energy 10–16 kHz: 36 % vs 24 %;
  1–3 kHz: 5 % vs 14 %) and its tail period is 255 Hz = 6 × 42.5 Hz — i.e.
  exactly ch8's rate × the ch8-carrier MUL (×6) — where the reference's tail
  sits at 4 × 42.5 Hz. Its spectrum also contains lines on the 3830 Hz grid
  stamped by the ch7-modulator ×15 phase (3767, 11526, 15271 Hz), which the
  reference does not have.

## 5. Conclusions

1. **The fnum-only hypothesis holds for CYM-current, and only there.** The
   current CYM really is played ~1 octave above the original (83.4 vs
   42.5 Hz, partner 5.3× high), which fits "CYM sounds too high". Fixing the
   fnums (as source-pitch does) removes that specific error.
2. **It does not explain HH.** The current HH channel rate is *lower* than the
   original (59.2 vs 127.4 Hz), yet it is the most metallic of the three. The
   metallic quality is a discrete line series whose spacing is locked to
   f_ch7 × MUL(ch7 mod) = f × 15 (888 Hz current, 1911 Hz source-pitch):
   changing the fnum only *moves* the ring (3550 → 3830 Hz spacing), it does
   not remove it — exactly what the source-pitch listening showed.
3. **It does not fully explain CYM-source-pitch either.** With fnums identical
   to the original it still sounds high/top-heavy: the remaining differences
   are the multipliers (ch7 mod ×15 stamping a 3830 Hz line grid onto CYM;
   ch8 car ×6 giving a 255 Hz tail period vs the reference's 170 Hz) and a
   longer, denser tail. On the YM2413 these multipliers are internal and
   evidently produce a much finer, weaker line structure (~680 Hz grid,
   shared by HH and CYM).
4. **What would make the conversions play the same fnums (in Hz) as the
   original** is already demonstrated by the source-pitch files: per hit,
   ch7 = (672, 2) for HH; ch8 = (896, 0) with ch7 = (672, 2) for CYM;
   ch6 = (576, 2) for BD. That change is necessary for CYM but, per points
   2–3, not sufficient for HH/CYM timbre: the shared rhythm template's MUL
   set — above all ch7-mod ×15 — has to be part of the same conversation,
   since it (not the fnum) sets the spacing and prominence of the metallic
   line series in both conversions.

Files in this directory: `REPORT.md`, `parse_vgm.py`, `analyze3.py`,
`HH_hit.png`, `CYM_hit.png`, `avg_spectra.png`, `hit_metrics.json`,
`cur_HH.wav`, `cur_CYM.wav` (renders of the current production VGMs;
the reference and source-pitch WAVs were used in place).
