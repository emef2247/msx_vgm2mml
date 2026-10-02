# Integer VGM timing and reference repetitions

Scope: public PSG/OPLL msxplay sample only. No musical normalization or broad
catalog regression was introduced. User explicitly requested a global chip-shared
origin and counting all VGM waits; per-chip rebasing and skipped short waits
were bugs, not desired Tcl compatibility behavior.

Reader time now derives from absolute integer source samples. `--vgmticks`
adds the same values and interval ends to trace/pass/Segment evidence. Sample
decoded EOF is 1,413,769 samples. The sample contains no 0x77/0x7A waits, so
synthetic tests separately exercise those waits, DAC waits and wait overrides.

Sample regenerated with and without `--vgmticks` produces byte-identical MML.
MGSC compilation succeeds; reported track usage is 2,956 bytes including track 0.
This isolates metadata enrichment from the always-applied clock bug fixes.

Reference comparison validates ordered pitch correspondence on five melodic
OPLL tracks (225, 225, 53, 53, 53 source KEYONs). Each has one terminal unclosed
note, excluded from full gate comparisons. Expanded reference loops are compared
only over the available source prefix; unmatched final exits are not full repeats.

Across 32 comparable later OPLL repetitions, raw offsets, gates and IOIs differ
by at most 139 samples (about 3.15 ms). Four windows differ in relative rounded
60 Hz ticks, by at most one tick. Exact raw state sequences also differ because
of brief intermediate writes; stable sequences agree in all 32 windows after
excluding states lasting at most 44 samples. Raw evidence is retained unchanged.
Pitch-order alignment alone ignores intermediate states of at most one sample.
Neither diagnostic filter changes a Segment or production output.

Rhythm instrument/volume order matches 213 source hit groups; eight comparable
later repetitions have identical native state sequences and slightly different
sample timing. PSG has 77 volume-reset candidates with matching pitch order and
eight comparable repetitions. These candidates are specific to this reference's
decreasing software envelopes; they are not PSG hardware key events. Their order
is checked against one shared OPLL-derived slope, without rebasing chip origins.

Conclusion: source samples distinguish actual sub-tick variation from rounding,
but do not make reference repetitions sample-identical. Musical normalization
or tolerant loop matching still needs a separate, explicit policy. Generated
audit CSVs retain source Segment indices, raw trajectories and individual deltas;
no aggregate quality score is introduced.
