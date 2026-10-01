# Alest202 OPLL retrigger evaluation

Source: optional local ALESTE2/Alest202 fixture. No private musical content is
included here. Outputs are under outputs/alest202_retrigger_check.

MGSC 1.11/libkss rendering of each isolated track was used because all melodic
tracks plus rhythm require 20770 compiled bytes (2847, 5780, 1817, 3709, 6050,
567), exceeding the normal 15000 track budget. The short explicit title avoids
the previously observed GD3 object-size failure. This is not full-song compilation.

Key-on counts, source / isolated MGS playback:
- ch0: 164 / 164
- ch1: 163 / 163
- ch2: 398 / 397 (zero-duration terminal onset at tick 4183)
- ch3: 515 / 514 (zero-duration terminal onset at tick 4195)
- ch4: 515 / 515, but counts hide a mismatch: two nearby playback onsets at
  ticks 4034 and 4035 versus source key edge at 4029, followed by shifted
  sequence pairing. The final source onset at 4195 is zero-duration and omitted.

The corresponding ch4 Segment onset markers include recovery from attenuation
15 while key-on remains set. These inferred audible onsets are not necessarily
hardware key edges. Target rendering currently treats such markers as attacks;
this is a remaining suspect for the short additional retrigger. No correction
was applied during this evaluation. Counts alone must not be called equivalence.

ch0/ch1 sequential paired key-on ticks differ by +2..+6 across playback, consistent
with the known startup/driver-clock discrepancy; no automatic timing correction
or sample-exact claim is made. Rhythm was isolated/compiled/rendered but not
included in the melodic key-edge count comparison.

Artifacts: generated/Alest202.mml (full source, does not compile with the old
allocation), isolated/*.mml, *.mgs, *.vgm, *.compile.log and trace_* directories;
summary.json and onset_pairs.csv retain raw count/order comparisons. Pair rows
for unequal counts are positional diagnostics, not an alignment oracle.


## User-provided pre-fix export comparison

The user supplied a pre-fix MML/MGS and an msxplay-exported VGM. The attached
MML compiles successfully with MGSC 1.11: tracks use 1735, 3656, 1341, 2821,
4714, 567 bytes, totaling 14834 track bytes plus 20 definition bytes. The
attached padded MGS is 14976 bytes; do not confuse file size with used tracks.

Source / old export / fixed isolated melodic key-on counts:
- ch0: 164 / 887 / 164
- ch1: 163 / 2876 / 163
- ch2: 398 / 1169 / 397
- ch3: 515 / 1914 / 514
- ch4: 515 / 3425 / 515

Old versus fixed compiled track usage is 14834 versus 20770 bytes (+5936,
about 40%). Fewer hardware attacks do not imply fewer encoded commands:
continuous pitch/volume intervals still need durations, state changes and
key-preserving control, and changed sequences can reduce loop compression.
No reduction/optimization was implemented in this comparison. A useful next
candidate is coalescing adjacent intervals that project to exactly the same
note/state without crossing real key edges, evaluated with MGSC and key traces.
Comparison artifacts: outputs/alest202_retrigger_check/old_export, including
key_edges.csv, summary.json and attached.compile.log. User attachments untouched.

Target interval coalescing subsequently reduced track usage to 13174 bytes.
Full-song compile/render succeeded with allocations 530/1069/1827/3171/6060/577.
Melodic key-on counts remain 164/163/397/514/515, with the previously described
residual mismatch unchanged. Default allocation still needs adjustment.

## Withdrawal
The user reported loss of the opening guitar after coalescing. That optimization
was removed. Its compile/key-count results above do not establish reproduction.
Root cause remains unconfirmed; retain artifacts only as failed experiments.
