# PSG/SCC register-period review

Date: 2026-09-29

User reported distorted drums in both vgmrips and MML-exported Gradius2 inputs,
out-of-tune gra2_008, and MGSC Invalid parameter on GRA2_02. These reports concern
sound reproduction and take precedence over text compression.

## Confirmed causes and corrections

1. Target hardware-envelope output incorrectly multiplied the PSG envelope
   period by 143.03493. MGSC/libkss probes show `m66` writes register period 66,
   while `m9440` writes 9440. The target now emits the observed period directly.
   Legacy debug renderers remain unchanged for historical regression comparison;
   the fix applies to the main target/merged output.
2. `m0` is rejected by MGSC 1.11. A probe confirmed `y11,0 y12,0` preserves zero
   in the PSG envelope period registers. Target output uses these direct writes
   for zero; it does not silently substitute period one.
3. PSG/SCC target output retained inferred note names but lost actual period
   differences, including custom tuning and detune. Emit an explicit common
   `#psg_tune` table and signed per-note detune: table[scale] >> (octave-1)
   minus observed period. MGSC/libkss confirms that positive detune subtracts
   from the final period. This is source-independent, not a game-specific table.

The input trace/Segments are not rewritten. `target_notes.csv` now includes
`target_detune`, `target_tone_period`, and `period_exact`. MGSC accepts detune
-127..127 in probes; outside this range the target clamps the correction,
records inexactness and emits a warning. Do not claim arbitrary periods are
fully representable with this fixed table. Target settings and loop candidates
still preserve source period identity.

## Independent validation

MGSC 1.11 + local libkss-js were used to compile synthetic MML, regenerate VGM,
and inspect PSG/SCC register traces. These probes are independent of the
converter's old hardware-envelope conversion formula.

- m66 -> period 66; m9440 -> period 9440; m0 -> compile error.
- Direct zero-period writes -> observed period zero.
- Explicit table, o4 c, detune 3 -> period 424; detune -1 raises period by one.
- GRA2_02 now compiles as a complete song (2035 total used bytes in this run).
- gra2_008 now compiles as a complete song (6325 total used bytes in this run).
- First 12 seconds of regenerated gra2_008 tracks 2,3,5,6 were inspected.
  Sustained source periods and channel detune distinctions are recovered;
  setup transients/initial silent writes and timing quantization remain distinct.
- Regenerated gra2_003 track 2 has hardware periods 66 and 768, matching input
  in the inspected opening interval. This is not a full-song audio equivalence
  assertion or a claim that every reported distortion has been independently heard.

Previously, the per-tick test compared inferred pitch names and repeated the same
incorrect hardware-period formula. Passing it did not establish correct playback
frequencies. The expected hardware period now comes directly from the Segment;
new target-period tests cover detune, zero-period output and unsupported ranges.

## Remaining validation

Ask the user to listen to regenerated gra2_008 and affected drum tracks. Other
issues such as retrigger interpretation, sub-tick writes and shared PSG register
interactions are not ruled out by these focused checks. Buffer capacity remains a
separate issue; accurate detune may increase target size.

Local artifacts: outputs/sound_review/ contains probes, original traces, regenerated
VGMs and corrected MML under fixed008/, fixed003/, fixed02/. Private material stays
outside version control. Tests use synthetic states; local fixture tests prefer
the user's new psg_scc/msxplay.com/gra2_msx directory and retain the old fallback.
