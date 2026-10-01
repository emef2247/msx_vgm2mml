# OPLL key state and autonomous envelope decay

Scope: read-only review of the user's local eseopl3patcher implementation and
existing emu2413 reference. No converter behavior changed in this review.

- src/opll/opll2opl3_conv.c preserves the current key bit while translating
  FNUM-low writes (around lines 1318-1326). Frequency updates do not force
  an off/on pair. The 0x20..0x28 handler translates the supplied key bit.
- OPL3 SL/RR mapping around lines 1073-1074 depends on operator EGT and key
  state. This is conversion code, not a universal chip-spec proof.
- Existing emu2413 reference processes changed key bits through _slotOn/_slotOff;
  SUSTAIN envelope rate is zero with EG=1 and patch RR with EG=0. Thus an
  EG=0 voice can decay while the register key bit remains high.

Do not confuse register key level, envelope attack, audible note activity and
Segment boundaries. A high key bit in successive states does not imply new
attacks. Silence after natural decay does not prove a missing register KeyOff.
Conversely, key-off is still meaningful and not universally optional.

The current converter's onset marker also includes recovery from attenuation
15 while key-on stays high. That is inferred audible onset, not necessarily a
hardware key edge; it must not automatically justify synthesizing off/on.
Key edge counts alone cannot establish envelope/audio equivalence. Existing
q0/slur changes still require timing/envelope validation; no new correction or
claim that this explains Alest202/YsSMS01's weak sound is made here.

## Follow-up: OPLL-to-OPL write sequencing

Reviewed the local copies of eseopl3patcher/src/opl3/opl3_convert.c
(`duplicate_write_opl3`) and vgm-conv/src/converter/ym2413-to-opl-converter.ts.
The GitHub pages did not expose readable code through the browser fetch, so
these observations describe the local checkout, not a verified remote revision.

- With `is_a0_b0_aligned` enabled, duplicate_write_opl3 stages A/FNUM-low
  writes while key is off. A rising key writes A then B/key; a falling key
  writes B/key then A. The option defaults to false in the reviewed main.c.
- Unchanged-key B writes preserve the supplied key bit. The default AB mode
  does not synthesize key-off. The BAB branch also writes the same B value
  twice: its `B(OFF)` enum comment is not evidence of a forced key-off.
- Optional `opl3_keyon_wait` inserts sample waits after B handling, including
  unchanged-key writes. This is target sequencing, not a source key transition.
- vgm-conv maps the source key bit to OPL B/key and refreshes voice settings
  on 0x20..0x28 writes. Its carrier RR mapping selects patch RR when EG or
  key is set, otherwise 6. Its output buffer suppresses unchanged register
  values; repeated identical key-high writes do not become forced off/on.

These implementations demonstrate that key-bit mapping alone does not fully
describe cross-chip envelope/timing reproduction. They do not establish that
an OPLL 1->1 key write restarts attack, or that missing source key-off writes
should be repaired by inventing edges. Preserve source write order/timing and
separate hardware edges from inferred audible onsets. The weak-sound cause
remains unproven. No conversion code changed during this follow-up review.

## User clarification: hardware experience

The user reports that the A/B ordering experiments addressed audible noise on
real OPL3 hardware: the two FNUM registers are written separately, and updates
crossing the low/high boundary can expose an unintended intermediate frequency
because writes are not simultaneous. Record this as the user's stated purpose
and hardware observation, not as an attempt to create additional key edges.

Separately, the user recalls OPLL playback requiring less strict off/on handling
than OPL3, with OPL3 becoming silent unless key-off was inserted appropriately.
The exact conditions are uncertain. The reviewed current code does not resolve
that historical observation; autonomous envelope decay alone is not sufficient
to explain it. Keep this as an open question, not a universal chip rule.

## Onset audit and correction

The user confirms that onset was a derived event rather than a register field.
Code audit found two target hazards: inferred attenuation-15 recovery was used
as a retrigger, and maximum-attenuation intervals were rendered as rests.
PASS3 silent merging also dropped key edges and internal register states.

Added independent key_on_edge to PASS2/PASS3 and Segment dumps, retaining the
legacy onset meaning. Bypassed silent merging in OPLL Segment construction.
Target notes now preserve keyed maximum-attenuation intervals as v0 and use
only key edges for retrigger decisions. This supersedes the earlier assumption
that all onset markers should authorize a target attack. No coalescing restored.

Before correction, Alest202 source/Segment edges for ch0/ch1/ch2 were
164/159, 163/158, 398/397. All source edges are now retained. Ch4 has 707
legacy onset markers but 515 source key edges; the 192 nonedge annotations
remain inspectable without becoming MML attacks. YsSMS01 had no nonedge
onsets, so the lighter-sound report remains unresolved.

MGSC 1.11/libkss synthetic roundtrip: key remains high across attenuation
15->3->15->4; two explicitly requested attacks produce two register key edges.
YsSMS01 compiles and roundtrips with 110/27/158/152/111 attacks. Its last ch1
source edge has zero tick duration at EOF and no timed target note.
Alest202 isolated melodic tracks compile and roundtrip with
164/163/397/514/514 attacks. Ch2/3/4 each have a terminal zero-duration source
attack absent from timed target output. Isolated melodic tracks use
2847/5782/1817/3709/6321 bytes (20476 total, excluding rhythm/definitions),
so full-song capacity remains unresolved; do not claim complete compilation.
Artifacts: outputs/opll_onset_review, including native Segments, target notes,
MGSC logs, exported VGM/trace and roundtrip_edges.json. Edge counts are not
proof of envelope or audible equivalence.

Validation: checked 65 related tests. Two synchronization test methods exposed
an existing helper/API mismatch (parsed macro lists supplied where _time expects
text); corrected the test helper and both methods, including four conversion
subcases, pass on rerun. Conversion code for synchronization was unchanged.
The user accepts the current retrigger correction; do not continue subjective
audio investigation without a new request.
