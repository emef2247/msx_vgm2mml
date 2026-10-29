# Score-guided target projection and bounded volume curves

## Order and target boundary

Source NativePerformance is built first. An inspectable ScoreGuide then retains
source-time pitch spans, rests and attack/hold identities, independently of
volume and synthesis settings. Blueprint consumes its pitch spans and applies
its own documented display clock; its generated MML is never parsed back into
production. Native source registers, controls and curves remain unchanged.

The score guide is suitable for any melodic source/target adapter, not only
PSG/SCC software envelopes. Current MGSDRV adapters accept optional score-based
repeat candidates for PSG, SCC and ordinary/normalized OPLL. Additional native
sources have source guides and blueprint allocation; this does not implement
new MGS chip mappings.

Production maps source events onto whole accepted target notes, retaining
many-to-many membership. Gaps, overlaps, unknown times and multi-unit coverage
abstain to existing exact keys. Guide cuts never create new notes or restart a
held envelope. Candidate pitch equality can ignore sub-semitone details, but
actual target pitch/detune is preserved. Both the score candidate and prior exact
plan render the same complete commands; their expanded commands must match.
The shorter equivalent text is selected, with both choices inspectable. This is
not a compiled-byte cost estimator.

For PSG/SCC, retain every exact settings/curve variant per structural leaf slot
before selecting the existing shared envelope bank. Do not count only the first
occurrence, or globally deduplicate a curve used at different stored positions.
The existing 32-entry bank, prefix checks and exact inline fallback are unchanged.
OPLL repeat guidance does not involve this software-envelope bank.

## Hardware envelopes are not loop barriers

An autonomous hardware envelope does not need its evolving waveform expanded
into score notes. Pitch, duration and articulation provide repeat candidates;
initial volume and actual control commands remain subject to target verification.
Keep source reset/reconfiguration operations in their original iteration. Never
add a reset just to synchronize the internal phase at a loop boundary.

Hardware/noise paths are outside the *volume approximation* prototype below;
they remain eligible for structural guidance. The physical target driver can
restart hardware envelopes when dispatching a new note even if the MML shape
selection occurs only once. That target articulation behavior must be checked
separately from repeat discovery. Current guidance preserves existing complete
commands rather than claiming to repair all hardware-envelope articulation.

## Export settings and low-level experimental options

`export_mgs.py` exposes `--fm-state-ms MS` (default 24 ms), which affects OPLL
internal-state handling when clock normalization is accepted. PSG/SCC state
thresholds and their error budgets are left unspecified, so bounded volume
approximation is disabled in this frontend. Exact software-volume grouping
and envelope reuse remain enabled by default and are separate from lossy
approximation. The temporary common `--state-ms` switch has been withdrawn
to reduce configuration differences while comparing loop/macro behavior.

The following lower-level switches remain on `vgm2mml.py`,
`batch_vgm_to_mgs.py` and `export_vgm.py`; the chip-specific approximation
thresholds are initially disabled there. They are no longer exposed by
`export_mgs.py`, which also omits rhythm enhancement, PSG solo selection and
the redundant `--normalize-lengths` flag. `--score-guided-loops` remains an
opt-in switch on all these entry points.

- `--score-guided-loops`: use score-based melodic repeat proposals; retain exact
  command equality and the existing plan as fallback.
- `--psg-state-ms MS`, `--scc-state-ms MS`: maximum connected interval changed by
  volume approximation. Omitted or zero disables approximation for that chip.
- `--curve-volume-error LEVEL`: required maximum absolute volume-register error.
- `--curve-mean-error LEVEL`: required duration-weighted mean absolute error.

Both error limits must be explicit when a positive chip threshold is requested.
Their domain is native register levels 0..15, not linear acoustic amplitude,
percentage or dB. These lower-level switches do not automatically enable score
timing normalization or exact software-volume grouping.

Example comparison (the error budgets are experiment settings, not defaults):

```sh
python vgm2mml.py input.vgm --outdir outputs/exact --score-guided-loops
python vgm2mml.py input.vgm --outdir outputs/approx --score-guided-loops \
  --psg-state-ms 24 --scc-state-ms 24 --curve-volume-error 1 --curve-mean-error 0.25
```

## Conservative observed-curve reuse

The prototype only changes derived ScoreNote volume runs. It uses simpler
observed curves with identical source/renderer duration, compatible exact pitch
and settings, fixed waveform where relevant, and identical initial/terminal
levels. It never changes note boundaries, pitch, waveform, native evidence or
zero/nonzero audibility. Noise, hardware-envelope operation, unknown timestamps,
ordered side-effect barriers and waveform changes abstain.

Candidates are deterministic, compared directly with the original curve, not
transitively clustered. The search is bounded to 64 observed candidates per
compatible group and reports truncation. A threshold is not permission to drop
every shorter state: pointwise error, absolute integrated/mean error and longest
connected changed duration are all checked, separately in source samples and
renderer frames. Source and renderer timing are not substituted for each other.

An actively normalized target clock can clip or extend volume holds after these
checks. Until a composed post-normalization error check exists, approximation
explicitly abstains when clock normalization applies. The original curves are
retained and candidate decisions/reason remain inspectable. A mere normalization
request without an accepted clock does not block approximation.

Backend partition fallback slices the accepted projected curve across the old
partitions and verifies the same accepted timeline; it must not restore original
values after approximation has been accepted.

## Inspection and validation limits

Diagnostics include:

- `<stem>.score_guide.json` and `.score_guide.events.csv`: original sample-time
  score events, source unit/Segment IDs and descriptive repeat candidates.
- `<stem>.<chip>.score_guide.mapping.json`: many-to-many target membership;
  no executable guide cuts are applied.
- `<stem>.<chip>.curve_approx.json` / `.decisions.csv`: original/projected runs,
  observed representative identity, accepted/rejected candidates and both clocks'
  deviation measures.
- Pre-envelope counts distinguish expanded occurrences, first score slots and
  exact curve variants. Target loop dumps retain candidates and exact fallback.

Authored tests cover dynamics/timbre variants, nested repeats, hardware-envelope
commands, ordinary/normalized OPLL, gaps/overlaps, original source preservation,
explicit budgets and target fallback. Actual MGSC/libkss probes cover two onset
phases and a full envelope bank. Settled output-frame levels match the expected
one-level/one-frame change in those cases. Raw register dispatch can shift by
one sample and create a larger instantaneous difference at a steep transition;
this is recorded separately, not silently treated as satisfying a samplewise
or acoustic bound. Existing source-to-driver quantization is a separate issue.

Neither fewer MML characters nor more loop markers proves a smaller MGS, correct
audio, or buffer fit. Measure per-track usage/compile outcomes and let listening
judge the explicitly permitted approximation. Pitch/LFO simplification, envelope
base-volume families and automatic reattachment of arbitrary curves to a score
skeleton are not implemented by this prototype.
