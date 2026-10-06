# GRA2_17 additive OPM prototype — 2026-10-05

User selected NEMESIS2/GRA2_17 (The War is Over / Game Over). M_G2_17S is a
manual arrangement reference, not the sound target. Its patches were not copied.

Input: tests/fixtures/local_only/psg_scc/vgmrips.net/NEMESIS2/GRA2_17.vgm.
Output: outputs/opm/psg_scc_prototype/GRA2_17/.

- 665 native source Segment rows mapped; PSG3 + SCC4 active parts retained.
- Four target voices: ideal PSG square and three SCC spectra. No channel merging.
- Source end: 194039 samples; target end: 194034 samples after MDX quantization.
- 2438 target writes exactly matched returned MDX playback controls/timing.
- Seven held target KeyOns matched seven returned KeyOns. These are synthesis
  strategy keys, not a claim that the source contains seven musical notes.
- MML 30952 bytes, MDX 8697 bytes, VGM 59144 bytes. Compression is not attempted.
- Three source PSG period-zero shutdown transients, each two VGM samples long,
  project to zero target duration. They are marked omitted in target CSV; source
  rows are intact. Positive target-duration out-of-range pitch remains an error.
- Five unit tests pass: DFT/amplitude, clock/pitch, held-key continuity and source
  immutability, explicit unsupported-control rejection, transient diagnostics.

The roundtrip passes, but listening approval and source/target gain calibration
remain open. DC/phase and unselected harmonics differ; PSG attenuation is approximate.
No claim of audio equality. No copyrighted wave/patch data is copied into this note.

Next: listen to GRA2_17, then investigate noise for GRA2_05 and hardware EG for
GRA2_03. Composite-timbre and rhythm-pattern detection remain future analyses.
