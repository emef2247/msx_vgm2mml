# HuC6280 continuation after score checkpoint (2026-10-27)

User requested saving the completed score/blueprint work on a separate branch
before continuing HuC. Branch `codex/score-guidance-huc6280` contains checkpoint
`2a2f3b4`; private notes checkpoint `46fa6f1` is separate. No push performed.
User is auditioning the score/curve work; do not change its defaults or README.

HuC native source controls/units and the score guide now precede target prepare.
Successful and failed MGS lowering both retain original B9 commands/time in
reference VGM. DDA data writes are typed once, not duplicated PCM packets;
PCM units stay outside blueprint. The accepted target execution stays separate.
Source-to-target guide bindings carry original channel/mode provenance.

Extended MGS routing supports stopped waveform changes, PSG noise and OPLL ROM
overflow; the initial static SCC/PSG route remains. Shared SCC RAM and AY noise
are validated on positive overlaps and restored after zero-time transitions.
OPLL fits use a reproducible numeric reference catalog, with spectral/gain losses
reported. Key-off retains release pitch. DDA/LFO, enabled RAM writes and mixed
chip MGS lowering remain explicit limitations; native products survive them.
Extensionless `Vgm ` files are discovered without renaming inputs.

285 relevant tests pass, including authored real MGSC/libkss SCC+OPLL/noise
playback. Scoped private BIKKR06, DSPILT01 and KATOKEN11 compile and export real
MGS playback VGM with nonzero assigned-chip audio. DSAVER13 deliberately fails
MGS lowering for DDA while native VGM/blueprint succeed. All4 source hashes,
ordered B9 commands and native durations match. Evidence:
`outputs/diagnostics/huc6280_remaining_20261027/{summary.json,analysis_ja.md,unit_tests.log,exports/}`.
Generated/private data are untracked. Broad regression/listening are user-run.

Next allowed: user HuC listening/regression feedback or narrowly scoped fixes.
Do not claim exact OPLL/noise sound, hardware verification or DDA MGS support.
Do not modify user README, run_test.sh, run_sweep.sh or logs, or push private notes.

---

# SALAMD01 long PSG/SCC parity supplement completed (2026-10-26)

User requested a longer PSG+SCC case beyond the short sync blocks. Added only
psg_scc/vgmrips.net/SALAMD/SALAMD01.vgm (90 seconds), comparing the same fixed
mainab58c3e and implementation9da7011 with the preceding audit settings.
Ordinary MML is12373 bytes in both and byte-identical; both MGS compiles succeed,
and MGS bytes match. Force omissions0; input hashes unchanged. Total now29/29
ordinary MML pairs and29/29 compiled MGS pairs identical. No implementation or
README changes. Previous28 results reused; only the one new pair converted.

Evidence outputs/diagnostics/main_vs_musical_hal_9da7011/ now includes the long
case in summary.json/results.csv/analysis_ja.md and runs/psg_scc_long/SALAMD01/.
salamd01_source.json retains duration evidence. This completes the specifically
authorized supplement; no additional broad private run or listening performed.

---

# FMPAC rhythm parity supplement completed (2026-10-26)

User added opll/vgmrips.net/FMPAC because the previous MSLND selection does not
exercise OPLL rhythm. All5 FMPAC inputs compared using the same fixed mainab58c3e
and implementation9da7011 snapshots and settings as the preceding23-input audit.
FMPAC01/02/04/05 have native OPLL rhythm key-ons;03 has no rhythm. Both generated
MML versions have mode1 and active rhythm track f for those4, and mode0 for03.
All5 ordinary MML pairs and all5 compiled MGS pairs are byte-identical. Both
versions compile5/5; force omissions0; input hashes unchanged. Total audit now
28/28 MML and28/28 MGS byte-identical. This adds rhythm coverage; it is not a
hardware/source-score accuracy claim. No implementation or README changes.

Evidence remains outputs/diagnostics/main_vs_musical_hal_9da7011/; summary.json,
results.csv and analysis_ja.md include the supplement. fmpac_source_rhythm.json
records source mode/attack evidence and generated rhythm-mode/track presence.
Only these5 new pairs converted; previous23 results reused with verified output
hashes. This completes the specifically requested local supplement.

---

# Committed musical HAL: local ordinary-MML parity verified (2026-10-26)

Implementation committed as9da7011 on codex/musical_HAL. Related HuC/HAL/
blueprint private notes committed separately as3264937. No code was edited
for this comparison. Fixed local mainab58c3e and9da7011 runtime snapshots used
identical export-like settings: normalize-lengths, software-volume-curves,
fm-state-ms24, normalization-ms8, force, dump-passes; default loops/macros.

User-authorized local_only folders, all VGM directly within each folder:
- PSG psg/vgmrips.net/TWINBEE:7/7 normal MML and7/7 MGS byte-identical.
- PSG+SCC gra2_msx/gra2_001/with_sync_mark:6/6 MML and6/6 MGS byte-identical.
- OPLL opll/www.smspower.org/MSLND:10/10 MML and10/10 MGS byte-identical.

Both versions convert/compile all23 successfully. Input hashes unchanged.
MSLND09 has10 time-zero DCSG writes omitted by both versions under force;
all other22 inputs have0 omissions. This is ordinary <stem>.mml parity, not
blueprint comparison. MML bytes (including CP932 Japanese titles) and compiled
MGS bytes match. This demonstrates selected output compatibility, not new
hardware-listening or independent source-score correctness.

Evidence outputs/diagnostics/main_vs_musical_hal_9da7011/
{analysis_ja.md,summary.json,results.csv,refs.json,compare.py,runs/} contains
commands, logs, hashes, ordinary MML/MGS and pass dumps. Inputs/reference MML
and README untouched. No push. Next allowed: user review/listening or specifically
requested follow-up; no further broad local_only run within this completed audit.

---

# Editable blueprint addition (2026-10-26)

User clarified: remove timbre and SW-envelope definitions, KEEP volume changes.
New py/musical_blueprint.py consumes accepted MusicalPlan units/controls. Native
PSG/SCC/OPLL lanes remain; HuC provenance in adapter allocation metadata routes
those whole sounding units to free OPLL then PSG lanes. Inline v holds and tied
pitch/volume continuations, whole-unit finite loops then existing macros; @0
placeholders, no copied SCC wave/OPLL patch/SW-envelope definitions. Users add
their own SCC wave. Native source evidence/ordinary rendering are unchanged.

Canonical, export_mgs/batch and export_vgm automatically add blueprint/<stem>.mml
to each output package. Diagnostic <stem>.blueprint.json / .units.csv record
source lane, plan lane, output lane, samples/steps, controls, loops and rounding.
Primary MML/MGS/VGM ownership/failure rollback remains; the template can publish
even when ordinary MML or compilation fails. Edited/unowned templates are skipped
with blueprint_status=blocked; primary conversion continues. Stale templates
must not be relabelled as latest success. Canonical protects edits with a digest
and preserves ownership across blocked attempts.

Template rhythm is attack-grid/preset-decay notation; native off edges are in
rhythm_source_controls, not independent MML gates. Positive held percussion
volume changes block the template; same-sample release/setup transients do not.
Never invent attacks to represent such a curve. No silent lane-capacity omission.

95 focused tests pass, no errors/failures/skips, including actual MGS PSG volume
15->9->3 and full gate duration, templates/native lanes/spill/loops, hand edits,
failed-attempt publication, canonical/batch/VGM and HuC projection checks.
Fresh public PSG+SCC VGM and OPLL MGS exports succeed with template publication.
Fresh authorized BIKKR06 VGM succeeds;352 sounding units from6 source voices
are mapped to6 OPLL lanes in its blueprint. No broad private regression/listening.
Final public-template generation/compile audit: see
outputs/diagnostics/blueprint_20261026/public_final/summary.json.
Of60 saved public accepted plans,58 produce blueprint MML;2 report held native
percussion-volume limits (rhythm_only_test03 and sample).50 compile with MGSC;
8 hit track-buffer capacity. These are blueprint results, not primary conversion
failures. Tempo-specific minimum encoded lengths are explicitly checked; long
tied notes reserve a legal final piece. Raw%1/%2 are valid at low tempos, while
divisors96/192 are invalid. Do not confuse a compiler duration limit with missing
score-unit reconstruction, and do not silently add independent60Hz rounding.
Long explicit curves can exceed MGSDRV buffers; the template is not automatically
compiled. Successful MML generation does not imply identical timbre/playback.

Branch remains codex/musical_HAL, all HuC/HAL/blueprint work uncommitted.
README unchanged. No staging/commit/push. English specification in
docs/musical_blueprint.md; external private note records implementation/review.
Next allowed: user listening/regression or focused reported blueprint issues.
Do not flatten volume curves, copy source timbres back into blueprint, replace
source units by raw tied Segments, or run a broad local_only regression.

---

# musical_HAL initial foundation ready (2026-10-26; historical checkpoint)

Current public branch: codex/musical_HAL, created from main per user request.
All uncommitted HuC6280 + common-foundation work is preserved on the working tree.
No stage, commit or push performed. The older IN PROGRESS checkpoints below are
historical; the blockers listed there have been fixed and validated.

Shared MusicalPlan/Unit/Control plus native PerformanceIR and timing decisions
are wired into MML lowering and compiler-free mixed PSG/SCC/OPLL VGM output.
Preferred batch: python scripts/export_vgm.py <input> --outdir <output>.
Canonical: --output-format mml|vgm|both (defaultmml); VGM-only skips ordinary text
lowering; the later blueprint addition is a separate optional-success attempt.
Export defaults24msFM/8msnormalization/softwarecurveson/timeout1200. Finite output
by default; --song-loop source explicitly requests validated re-entry.
Flat tracks/<stem>.vgm + sourcecopies + diagnostic plan/CSV/writes + manifest,
results; ownership/failure rollback retained. Existing MGS products coexist.
README untouched. docs/musical_hal.md documents real usage/scope/differences.

Verified:153 focused authored/public/actual-MGS/reference checks pass with no
failures/errors/skips; existing MML public baseline passes;60 supported public
native/mixed inputs generate VGM (13PSG,13SCC,19OPLL,2PSG+SCC,1PSG+OPLL,
12PSG+SCC+OPLL). Final OPLL19 rerun after zero-pulse fix allsuccess. Independent
pinned C AY/OPLL/SCC actual audio + authored frequency checked; representative
public prefixes nonzero on intended chips. BIKKR06 direct route succeeds.
No broad private regression or hardware listening. User HuC regression ongoing.
Evidence outputs/diagnostics/shared_vgm_20261026/{summary.json,acceptance_tests.log,
mml_public_regression.log,final_public,independent_audio.json,BIKKR06}.

Important fixes: native rhythm shared bank protected from melodic6-8quantization;
modeentry native snapshots + modeexit accepted latent melody restoration. Complete
normalized zero-width transition groups include settling keyoff (no phantom held
note). Inferred drum volume nibbles restore native values; native hits win;
new drums use measured MGS initial pitch. No raw-note replay/MML parse prerequisite.
MML shares accepted PerformanceIR/normalized objects; packaging fallback verifies
same volume timeline, maps units and preserves accepted clock. MGS layout limits
fail explicitly; successful direct VGM remains. Inherited OPLL sustain omission
is recorded as MML backend loss; direct VGM/common plan retain sustain.
Architect focused review confirmed identified blockers fixed; no private runs.

Not implemented: MIDI/TX802/FB-01 or broader chips, HuC noise/DDA/LFO/dynamicwave.
Next allowed: user regression/listening on new VGM outputs; use retained native
parameters/source clocks for later profiles, not reverse MGSencoding. Do not
change README or run broad local_only without user scope. Avoid unfiltered
unittest discover: legacy local tests exist; use selected public/authored modules.
English implementation note saved separately in private external repository:
msx_vgm2mml/field_notes/2026-10-26_musical_hal_direct_vgm.md (uncommitted).

---

# musical_HAL branch checkpoint (2026-10-26)

User requested a separate architecture branch and explicitly allowed all current
uncommitted changes, including HuC6280. Created codex/musical_HAL from main;
all tracked/untracked work preserved. No commit or push was requested/performed.
Continue the common musical-layer/direct-VGM implementation on this branch.

Implementation is IN PROGRESS, not final acceptance. New typed MusicalPlan,
PSG/SCC/OPLL execution adapters, common timing decisions, direct mixed-chip VGM
writer, export_vgm.py package layout/ownership and canonical output-format branch
are saved. README remains unchanged. Existing MML lowering consumes shared
accepted decisions; packaging-only fallback integration still needs final review.

Important unfinished correctness item: OPLL channels6-8 melodic controls must not
overwrite native rhythm shared registers while source rhythm mode is active.
The OPLL worker identified the fix but hit usage limit before completion. Filter
melodic controls by ordered source mode; retain native rhythm banks at modeON;
restore accepted melodic state after modeOFF. Add authored positive-wait tests.
Do not call all mixed-rhythm output musically verified merely because generation
of19public OPLL files succeeded. Verify worker file state before continuing.

Pending: finish independent audio validation and public-group export summary,
shared MML fallback review, direct writer loop/GD3/resource tests, final focused
architect review, public regression checks and external note. Public tests may
still be running from root sessions; inspect results before repeating. Do not
run broad private regression. User HuC regression remains ongoing.

---

# Direct reconstructed VGM foundation requested (2026-10-26)

User BIKKR regression is still unfinished. New priority: output PSG/SCC/OPLL
mixed VGM directly from the same reconstructed musical information as MML,
without requiring MML/MGS to fit compiler/driver buffers. Current task is route
selection/audit only; no new direct writer implemented. See
 docs/reconstructed_vgm_routes.md for scope, existing seams and validation.

Start native PSG -> PSG, SCC -> SCC, PSG+SCC, then OPLL melody/native rhythm and
all mixed combinations. Reuse common final musical decisions and then integrate
existing inferred-rhythm overlay / HuC adapter. Existing HuC target VGM precedes
musical correction; MGS->VGM still requires successful compilation, so neither
alone satisfies this requirement. Extract text-coupled normalization, boundaries
and overlay decisions into a shared plan. Keep MGSDRV packaging/buffer limits in
MML lowering, source evidence intact, chip-global state and loop intent explicit.
README unchanged. No conversions/tests needed for this read-only route audit.

---

# HuC6280 BIKKR implementation ready for user regression (2026-10-26)

Single HuC6280 periodic/static-wave source is automatically analyzed from actual
B9 commands and projected into ordinary SCC + square-wave AY overflow. Stable
5-SCC allocation requires an equal shared pair; otherwise4 independent SCC RAMs.
Native immutable State/Segments/RAM/gain assumptions remain separate from the
retained target VGM and target-derived PSG/SCC Segments. Existing musical-unit,
loop/macro/SW-envelope renderers consume the adapter. README unchanged.

BIKKR06 and BIKKR01 scoped conversions both success, actual MGS->VGM export and
nonzero audio confirmed.6voices ->5SCC+1PSG. MGS sizes2432/14592bytes respectively;
MML5121/24827bytes. Private fixtures unchanged; no full catalog/listening claim.
Artifacts: outputs/diagnostics/huc6280_impl_20261026/{BIKKR06,BIKKR01,native06,
gain_probe,analysis_ja.md,verification.log}. Native/target/allocation/control/
gate/write CSVs retained. All6 authored active target periods checked in actual
MGS replay. Source C oracle pinned to libvgm bad50c571db45b872304bdcd0603dd2214f0663e.

Selected authored/public modules:77checks pass,0failures/errors/skips; subsequent
focused HuC checks33pass after adding phase-dependent third-loop guard tests.
Final small path containment guard is covered by the final focused rerun.
Earlier unfiltered discovery unexpectedly entered legacy local-only tests and
was interrupted; avoid unfiltered discovery if private scope must be limited.

Loop-cache review fixed redundant entry pitch/gain restoration and activation
after muted source pitch changes. Native and target second traversals validated;
phase-dependent loop RAM writes blocked unless disabled upload has explicit
in-loop reset. Finite replay equality alone is not a proof of phase independence.
Architect focused review confirmed all identified blockers addressed.

Batch still exports real MGS playback; HuC uses projected_source verification
status, never a false OPLL0/0 equality. Generated target VGM excluded from input
rediscovery; unowned intermediate targets protected; original source/package
publication ownership retained. Target octave verified through actual audio.
Gain/stereo/phase are explicit approximations, not hardware equivalence.

Not implemented: OPLL spill, noise, active DDA/LFO, dynamic audible wave changes,
mixed chips. These remain explicit failures even under force. Next allowed:
user BIKKR regression/listening, then decide next HuC feature from evidence.
Do not silently broaden support or change the user-maintained README.

English implementation note saved separately in external private repository:
msx_vgm2mml/field_notes/2026-10-26_huc6280_bikkr_initial_implementation.md.
Public and private changes remain unstaged/uncommitted; no push requested.

---

# HuC6280 hybrid target design (2026-10-25)

Investigation only, user authorizedreading local_only/huc6280; no production
converter/README/test changes or fixture mutation.106VGM inputs across6sets
inspected (KATOKEN14extensionless); sourceclock3579545, B9+wait/end only.
Allsets reach6enabled/gainpositivevoices. DDA16inputs(allDSAVER); no activeLFO,
DACstream, live enabled normalwavewrites observed. Counts are diagnostic,not
independent audio validation. See docs/huc6280_projection_design.md, ignored
outputs/diagnostics/huc6280_design_20261025/analysis_ja.md and external note
2026-10-25_huc6280_projection_design.md.

Baseline ordinarySCC:5voices/4independentwaveRAMs(ch4/5shared). Plan SCC primary,
PSG square/noise complement, OPLL other periodic spill; globalOPLLuserpatch and
sharedPSGnoise constraints explicit. Do not assume SCC+independentmode works in
MGSDRV. DDA is separate timed sampledata,not a periodic note; unsupportedparts
must remain visible. Preserve native6voice State/Segment and fullsounding-unit
+internalcurves before existingloops/macros/sharedSW-envelope adapters.

Nextallowed: scopedimplementation after user direction. Suggested short inputs:
BIKKR06,SCC+PSG;DSPILT01,OPLL;KATOKEN/11Miss,noise/extensionless;DSAVER13,laterDDA.
No source-to-MML conversion or broad regression run. No staging/commit/push.
Do not revive removed MDX external tools; keep user-maintained README unchanged.

---

# MDX toolchain removal (2026-10-25)

Removed inherited MDX export, compilation/replay, fixture-generator and external
inspector scripts plus their tool-specific tests. Public CLI no longer accepts
MDX/OPM output aliases. Native output and MGS compatibility remain; shared pure
source/structural modules and reference evidence were not purged. Removed the
corresponding MDX external-tool sections from THIRD_PARTY_NOTICES.md, retaining
required mapping attribution. README files outside the deleted Rust helper
are unchanged. Existing local tool installations and generated assets were not
deleted. Validation results follow in the task's private note. No commit/push.

---

# Export default and user successes (2026-10-25)

MSX export_mgs.py now enables --software-volume-curves by default; explicit
--no-software-volume-curves disables it. Canonical and legacy batch defaults
remain unchanged. README was not edited. User logs record NEMESIS2 9 successes
and gra2_msx 47 successes; successful input paths are recorded in external
field_notes/2026-10-25_export_default_and_user_successes.md. This checkpoint
records supplied success statuses only; no new fixture conversion was run.

# Verified reference-score release continuation (2026-10-25)

Current GRA2_001 split MMLs are valid direct oracles: all6 reference MML->MGS->VGM
are byte-identical to inputs. Same-period release continuation + inactive shared
latch handling is saved under --software-volume-curves. Native source/control/
boundary evidence is preserved; SCC remains excluded from period-write joins.
All6 final MGS compiles succeed; all6 PSG1/3 compiler-used-byte pairs shrink.
55 focused checks pass, plus case06 real-oracle PSG1/3 prefix200-frame volume/
enable equality. Full six-song/all-chip actual equivalence is not claimed.

IMPORTANT tradeoff: case05 SCC1(track4)1261->1790bytes; combinedtracks10100->10446.
Do not call this a universal buffer fix. Existing long-first shared32bank and
macro policies remain unchanged. Relative base-volume envelope families and
source note-off/release parameter recovery are still missing.

Read outputs/diagnostics/reference_gap_20261025/analysis_ja.md and external
field_notes/2026-10-25_reference_score_release_continuations.md for causes,
intermediate adverse results and final validation. Next focus is exact relative
curve sharing then controlled bank selection, not more arbitrary thresholds.
README is user-maintained and unchanged. Additional7dirs only if needed.
No stage/commit/push.

---

# Reference-score continuation work in progress (2026-10-25)

Fresh current GRA2_001 split MML files are confirmed paired oracles: all6 compile
and re-export VGM BYTE-IDENTICAL to inputs. Historical98-fine-cut mismatch is
superseded. New narrow opt-in unchanged-period continuation is saved in
psg_scc_volume_curves.py, with source controls/boundaries preserved and explicit
unchanged_period_joins reports. It addresses reference06 PSG1's16+4release tail.

Important: first candidate regressed05/06 buffer usage due PARTIAL joins blocked
by irrelevant shared wNC/ePL/evM writes. Those adverse outputs are preserved.
The saved correction permits those known latches only throughout fixed-tone /
HW-off spans; transient enable/mixer/unknown/pitch/volume-rise controls protect.
Final six-case compiles/usage comparison is IN PROGRESS under outputs/diagnostics/
reference_gap_20261025/production_effective_controls. Verify those results before
claiming completion; do not hide the first adverse portfolio.

New unit guards and authored unchanged-period real-driver test are saved. Source
same-period-write phase probe passed8emu2149 cases, not a hardware guarantee.
English external note:2026-10-25_reference_score_release_continuations.md.
README unchanged. Existing envelope/macro selection policy retained. Do not
expand to whole songs or the other7dirs without a missing-structure reason.
No commit/push.

---

# Current verified restart status (2026-10-25)

Missing external-note/handoff record is now complete. The production inactive
PSG-reset correction and explicit enable/disable switches are saved. New
reset-specific real-driver test passes all four authored subcases (tempos75/225,
constant/decay,200 frames, rest/restart and subsequent active HW reset). This
turn's38 focused checks pass. All six authorized split cases compile and their
source/projected holds match. Full private six-case actual replay is not claimed.
README was user-edited and has not been changed by this task. Keep it unchanged
unless explicitly asked. Long-curve allocator remains the existing long-first
policy; x68k history only supports separate target-duration tie splitting.
Detailed evidence and NEMESIS2 failing song names are in external field_notes/
2026-10-25_curve_integration_history_and_regression.md. No commit/push.

---

# Production curve integration and restart checkpoint (2026-10-25)

This section supersedes the earlier diagnostic-only implementation status below.
The user requested saving the unfinished field_notes/handoff first, then a
focused review of x68k long-SCC-note history and further production improvement.
README.md is user-maintained usage guidance: preserve its current contents;
do not add detailed options or technical background without an explicit request.
Detailed switches belong in CLI Usage and focused developer documents.

Saved production code: --software-volume-curves now coalesces derived fixed-tone
PSG boundaries caused solely by inactive hardware-envelope reset BEFORE the
existing single-rise/decay curve stage, reversible structure and shared bank.
The original PerformanceIR, source Segments, controls and boundary evidence are
preserved. Whole ordered source intervals, including zero-duration controls,
are checked for fixed-tone settings, hardware-enable, pitch/mixer operations,
audibility continuity, source gaps and unknown timestamps. Reports distinguish
inactive_reset_joins from curve recognition and preserve original note IDs.

All three CLIs provide mutually exclusive --software-volume-curves and
--no-software-volume-curves. Default remains False; config explicitly forwards
either polarity so future default-on does not lose a caller's legacy choice.
Existing long-curve envelope priority and macro-selection policy are unchanged.
Fallback reports zero actual inactive joins and separate planned joins.

Prior checks completed:52 CLI/config/export/batch checks and17 curve/protection/
playback checks passed. Architect code review found no blocking issue. Split
production conversion/compilation progress is recorded under outputs/diagnostics/
psg_scc_curves_impl_20261025/production_reset_join/summary.json. Full six-case
actual replay equivalence was NOT completed and is not claimed.

The prior final documentation write was rejected because automatic approval
review could not run at the usage limit; code had already been saved. Do not
repeat a diagnostic-only status as current behavior. This checkpoint completes
that missing record. Native reset evidence must never be removed to save bytes.

Next: inspect x68k long-note history before choosing a new curve-selection policy.
The user reports better MML with NEMESIS2 but remaining MGS capacity failures;
record failing song names only, with no new detailed statistics or broad rerun.
Use the six authorized GRA2_001 split VGM/master-MML materials for reference-based
checks. No full-song or unrelated regression expansion. No stage/commit/push.


## Completed source/projected check and historical scope clarification

Retained production results confirm all six authorized split conversions and
actual MGSC compiles succeeded. Source/projected volume-hold CSVs were checked
independently over every renderer frame for both chips in all six cases; they
match exactly. This checks the derived representation, not actual playback.
The local evidence is production_reset_join/projection_hold_audit.json.

This turn re-ran17 curve/protection/playback,13 tie-compensation and7 loop-first
checks:37 tests passed. A new authored inactive-reset actual-driver check is
being added separately; final status must identify its result before claiming
reset-specific playback validation.

The x68k historical rule is target-duration splitting with ties, not invented
source attacks. Existing MGS255-step duration splitting is retained; no arbitrary
long-note/source-envelope chopping or new allocator is introduced. That avoids
silently replacing the user's long-observed-curve selection preference. Future
candidate subdivision needs a separately validated continuation/rebinding policy.

README is unchanged. The user-owned current README's SHA256 was rechecked.
NEMESIS2 source-only user results were read only: GRA2_01/03/04/08/09/10/13/16
fail Track buffer full. No NEMESIS conversion or detailed statistics were run.

---

# Candidate-selection history audit (2026-10-25)

Re-read the September29/30 and October03 macro, shared-envelope and loop-first
records. Existing adopted baseline is complete sounding units -> reversible
loops -> stored representative counts -> shared long-observed-curve priority ->
state-safe target rendering/macros. Earlier byte-benefit allocation proposals
are not an implemented global optimizer. Tested macros reduce source characters
without necessarily reducing MGSC used bytes. Keep those policies fixed during
the first inactive-reset correction comparison.

The English equivalent of analysis_ja.md, including six-case buffer/loop tables,
reference provenance, historical policy audit and exact production flag scope,
is saved in external private field_notes/
2026-10-25_split_curve_analysis_and_inactive_hw_resets.md.
--software-volume-curves currently enables volume-only curve joins and final tie
compensation, NOT the diagnostic inactive-PSG-HW-reset join. Do not tell the user
the large diagnostic reductions are available under that flag yet. This audit
changed documentation only; no new conversions or behavior changes.

---

# Focused split-fixture analysis completed (2026-10-25)

User clarified the split VGM/MML cases are deliberately small reproductions of
whole-song buffer overflow, to recover loops and envelopes before scaling up.
Do not broaden this work to unrelated regression logs or whole-song conversions.
Use only the six VGM files and reference MML materials in the authorized
with_sync_mark directory. User explicitly approved the master MML as reference
for matching source intervals.

IMPORTANT PROVENANCE CORRECTION: the current same-name01..06 MML are DIFFERENT
fine cuts from the existing six VGM/MGS. Prior direct same-name MML footprint/
envelope comparisons are withdrawn. Corrected provenance is in the20261025
reference_provenance.json; matching existing MGS reproduce VGM byte-for-byte,
and their definitions match the compiled master. Master sync windows checked
against222 annotations. Do not reuse stale20261024 reference-MML comparison
numbers or present filename equality as source provenance.

Focused results and measured per-channel footprints are saved in:
outputs/diagnostics/psg_scc_curves_impl_20261025/analysis_ja.md,
channel_buffers.json, master_window_audit.json/.csv and
inactive_reset_counterfactual/report.json. No private score/waveform contents
were copied into project docs. The master-window/pitch check supports interval
mapping; arbitrary all-register source identity is not claimed.

MAIN FINDING: native PSG evS/global HW-envelope reset is unconditionally treated
as a renderer partition boundary even in channels not using the HW envelope.
Derived-note-only diagnostic joins reduce PSG1/3 compiled usage substantially.
This is a concrete structural improvement target, not a reason to erase native
reset evidence. Production coalescing is NOT implemented yet. Next allowed
implementation: target/performance-stage join of irrelevant resets with complete
source/settings/time/gate checks, then six-case loop/buffer/replay validation.
Preserve actual active HW resets and future HW-state evidence.

SCC finding: longer complete candidates can displace other definitions from the
32-slot shared bank and increase inline commands/buffer. Do not equate definition
count, MML character size, padded MGS filesize or loop count with score recovery.
A compiled-benefit selection change is a separate policy decision.

Opt-in curve + final uniform75/225 tie compensation code is saved; 104 focused
tests pass, including shared short-prefix/restart actual-driver probes. Raw75
max255-note release/onset quirks are unchanged from the ordinary same score and
explicitly recorded in tests. Corrected six-case MML compile+VGM exports succeed.
No staging/commit/push. Treat the reset coalescing experiments as diagnostics,
not published converter behavior. Earlier broader analysis below is historical.

---

# PSG/SCC tie compensation and buffer audit checkpoint (2026-10-25)

Implemented py/mgs_envelope_ties.py: joint final-target definitions/use validation,
uniform255-step schedule at tempos75/225, hold padding for boundaries in
[start,end), unchanged note/loop/macro bodies, no additional envelope IDs.
Integration runs after normalization and before final allocation/macros.
Unsupported schedules/accepted normalization/definition overflow rebuild the
ordinary complete pipeline (all clocks and drum mapping revalidated). Candidate
curve summaries then show applied=false, actual joins0 and separate planned counts.
Final target evidence: <stem>.volume_curves.target.json, with optional
<stem>.<chip>.before.envelope_ties.mml. Default behavior remains unchanged.

User supplied NEMESIS2_sw-voume.log:9/17 success,8 Track buffer full failures,
all force omissions0. No new NEMESIS2 fixture conversion was run. User clarified
PSG size investigation should prioritize loop reconstruction; keep loop and SW
envelope contributions separate. Original score also uses @e in PSG1/3, so do
not assume software envelopes are exclusive to SCC.

Per-channel actual MGSC measurements now saved in prior diagnostics:
channel_buffers.json/.csv. Full-song generated tracks measured independently
with unchanged original command bodies; source reference isolated bytes match
normal full-source -T output, validating that measurement method. Tracks1..8
reference used:810,4218,875,1109,1297,958,846,832. Baseline generated:
7260,6954,7506,5726,5727,4729,4660,4939. New projection before tie correction:
7254,6922,7522,5918,6123,5166,4652,4931. Track0 definitions are separate.

Full-source diagnostic grammar counts (numeric h setup ignored ONLY for counting)
are in loop_envelope_comparison.json. PSG1 stored NOTE tokens:source184 vsnew1577;
PSG3:201 vs1651. Finite-loop counts are higher in generated output, so count
alone is not the compression criterion. Generated attacks are also more split,
and far fewer use varying shared SW envelopes. Full source has27 definitions;
new shared bank uses32 IDs, which does not imply comparable coverage.

Current verification snapshots are separate under outputs/diagnostics/
psg_scc_curves_impl_20261025/. Corrected frontend case01 compiles and replays;
target-only reconstruction produces exactly the same final MML as the frontend.
The previous up-to7-frame SCC envelope advance is removed in raw transition
comparison. Remaining baseline differences can include correction of legacy
long envelopes, release behavior and intra-frame write scheduling: no blanket
source-audio equality claim.

Next: finish corrected six-case compilation/replay +focused suite, update audit
report, then inspect PSG complete-unit/phrase equality and why repetitions are
expanded. Do not introduce lossy duration/state filtering, change the16k pool,
or claim full-song buffer failures solved by the envelope stage. No commits,
staging or pushes requested. Older unfinished tie-warning below is superseded.

---

# Experimental PSG/SCC complete-volume-curve checkpoint (2026-10-24)

Saved opt-in `--software-volume-curves` across canonical/batch/export MGS
entry points. Fixed-pitch volume-only continuation candidates retain native
Segments/control evidence, protect ordered operations (including zero-time
rows), and feed one derived PerformanceIR to loops/shared envelopes/rendering.
JSON summaries and optional candidate/note/decision CSVs are emitted. Defaults
are unchanged. See docs/software_volume_curves.md for scope and limits.

Validation: 11 new focused tests pass (including public CLI and authored real
MGSDRV probes); worker CLI/config/batch checks: 48 pass. User authorized six
local gra2_001 with_sync_mark VGM inputs and then the parent gra2_001.vgm and
matching authored MML/MGS for independent comparison. Never inject score data
into conversion. Do not run unrelated local_only inputs.

IMPORTANT UNFINISHED BACKEND ISSUE: shared envelope phase advances once more
on a tied note continuation. New long curves can therefore run ahead of the
legacy output even when simulated renderer timelines are identical. Independent
PSG/SCC probes at tempos75/225 confirm one extra envelope update per tie; padding
holds for the actual tie schedule works in probes but is NOT integrated. A
universal duration extension is unsafe: sharing/prefix keys and final normalized
note splits must use the actual compensated schedule. Do not claim raw replay
or complete playback equality; keep this feature opt-in/experimental.

Fixture-specific measurements, per-channel allocation/used-byte and source
MML-envelope comparisons are being saved under outputs/diagnostics/
psg_scc_curves_impl_20261024. Preserve baseline and projected snapshots: later
fixes must not overwrite evidence used in the current comparison. User cares
primarily about per-channel MGSC allocated/used/free bytes (mgsc -T), not padded
MGS file size. Full-song bank sharing must be measured independently of summed
excerpts. Current task changes are in the worktree, not staged/committed/pushed.

Next: finish full-song/per-channel/original-envelope audit; implement and replay
verify tie-aware envelope encoding/sharing at the final clock boundary before
calling milestone1 exact on the real backend. Lossy curve smoothing and pitch
LFO/bend inference are not implemented.

---

# Proposed PSG/SCC curve projection audit (2026-10-24)

User requested history/book review before implementation. Reviewed prior MSX
loop/envelope notes, current PerformanceIR and relevant Konami driver scan
pages. Saved docs/psg_scc_curve_projection_plan.md and an external private audit.
No converter/option changes or local_only conversions in this turn.
Recommended next: derived complete sounding-unit/volume-curve candidates with
explicit boundary evidence and exact reuse; optional bounded volume-only
approximation follows. Do not flatten all short states, treat every volume
rise as attack, or import book/reference score parameters into conversion.
Await user direction on the proposed implementation scope.

# Completed checkpoint: shared export packages (2026-10-24)

Both MGS entry points now publish package/tracks/<stem>.mml/.mgs, with no
per-song listening directory. Packages preserve original INDIR-relative parents;
PSG mode namespace comes before that relative parent. Each package contains
_diagnostics/<stem>/, byte-identical _source_inputs, listening_manifest.json
(schema 1 filename-keyed entries), and results.csv/json with package-relative
paths. Root _diagnostics/results.* retains aggregate current-run progress.

Source staging and final publication use hash ownership checks. Case-insensitive
same-package target collisions fail before mutation; identical stems in separate
packages work. Edited/unowned final or staged files are preserved. Failed reruns
retain prior listening products, with latest_attempt_status and latest result rows
recording the failure. Partial reruns preserve other songs' package result rows.
Adjacent reruns prune generated inputs/tracks/diagnostics/mode directories.

Conversion/normalization/rhythm classification semantics are unchanged. Existing
uncommitted tests/script relocation and optional-outdir work remain intact.
Validation:31 batch +8 export +5 actual playback +10 rhythm tests pass (54 total),
including ownership,
partial reruns, staging/hash provenance, source-root conflicts and fault-injected
bundle replacement rollback. Actual retained public outputs live under
outputs/package_layout_public/{opll,psg}; both compile and roundtrip successfully.
OPLL retrigger has19/19 melodic Key-Ons; PSG scale has0/0 native OPLL Key-Ons.
Source/staged hashes match and tracks contain only MML/MGS. git diff --check passes.
No local_only regression, staging, commits or pushes; user handles private checks.

Next allowed work: review this common layout against X68000/MUCOM exporters and
run user regression. Do not resume PSG classification refinement in this task.

---

# Completed checkpoint: optional MGS output root (2026-10-24)

Both batch_vgm_to_mgs.py and export_mgs.py now accept omitted --outdir.
Explicit output keeps INDIR-relative parents: vgmrips.net/SALAMD/SONG01.vgm
maps to OUTDIR/vgmrips.net/SALAMD/SONG01.mml/.mgs, likewise NEMESIS2.
Omission selects adjacent output: final products beside source VGM/VGZ;
diagnostics/results under the input root _diagnostics (source parent for a file).
PSG mode branches remain relative to that output root. Native VGM bytes remain
unchanged, and explicit overlapping output roots remain rejected.

Adjacent directory discovery prunes _diagnostics/psg_melody/psg_rhythm before
walking them, preventing generated roundtrip VGM from feeding subsequent runs.
Existing ownership/hash checks, names, collision checks, and source/target
transformations are unchanged. Reports record output_root and adjacent_output.

Checks: batch25 + export8 =33pass. New tests cover the user's two-game relative
layout, adjacent file/directory reruns, generated VGM pruning, source-byte
preservation, and protected foreign output. Both actual CLI entrypoints compile
copied public OPLL input beside the source and retain matching melodic Key-Ons.
No private regression, staging/commit/push. Earlier tests/script relocation and
output audit remain saved. PSG classification refinement remains paused.

---

# Completed checkpoint: test scripts and output layout audit (2026-10-24)

User changed theme: PSG melody/rhythm split works mechanically but differs from
musical expectations. Classification refinement is paused pending a clearer user
definition. Do not resume it as part of file/output organization.

Moved68 top-level tests/*.py, including vgm_test_support.py, to tests/script/ as
explicitly requested. Repository-root lookups and sibling imports use new paths;
fixtures and tests/conversion_baseline.json stay in place. New package bootstrap
also preserves old root unittest discovery.514 tests collected before/after;
0 import errors, identical canonical IDs.125 selected public/synthetic checks:
124pass,1 known pre-existing GD3 prefix-space expectation failure. Original HEAD
version of test_vgm_io reproduces the same failure (4 tests,1 failure); no behavior
or expectation was altered. No local_only regression.

Both MGS entry points already share flat final publication: out/<relative-parent>/
<stem>.mml/.mgs; diagnostics under out/_diagnostics/tracks/<relative-input-name>/.
Solo products use psg_melody/ or psg_rhythm/; diagnostic/result branches match.
No extra per-song listening tracks/ directory. Actual public export of both
entries returns0 with19/19 melodic attacks. Conversion defaults remain different:
batch normalization opt-in (FM1ms when enabled), export FM24/timing8ms requested.

Documented exact layout, collisions, migration, and current cross-project mismatch
in docs/output_layout.md; corrected stale docs/batch_mgs.md and README descriptions.
Updated AGENTS/docs/test commands to unittest discover -s tests/script. Current
x68k export_mdx still uses final tracks/<relative-source-filename>/; MUCOM uses
tracks/<stem>/. Those exporters were only inspected, not modified.

Saved verification: outputs/diagnostics/test_layout_20261024/verification.md/json,
test_relocation.json and logs, plus concrete batch/export MML/MGS/roundtrip trees.
All changes saved in MSX working tree; no staging/commit/push. Next allowed work:
user review of output contract or an explicit follow-up to align the other
exporters. Preserve names/8.3-compatible stems, collision safeguards and separate
source/intermediate evidence. Do not claim all514 tests were executed.

---

# Completed checkpoint: silent compiled MGS repair (2026-10-24)

User-reported ordinary export silence is reproduced and repaired in the working
source; no staging/commit/push. Nonempty #alloc0 definition bodies omitted their
0xff terminator. py/mml_sync.py now reserves one byte once, within unchanged16000
shared pool. Controlled84->85 allocation changes only MGS byte152 (2c->ff), restores
0->6 actual Key-Ons; isolated tune/envelope/user-voice probes reproduce it. The old
body-only estimator is b5027feb (2026-10-06), independently of drum enhancement.
Existing generated MML must be regenerated. Prior compile-only descriptions of
playable drum examples did not establish playback; those older artifacts are not
certified by the present public-only checks.

Public defaults, no enhancement/bypasses:60 inputs,56 compiled,56 nonzero5s PCM,
55 exports complete with matching melodic OPLL channel counts;4 compile capacity
failures (cpebach/enchanted/turpinh/bridge). OPLL19/19 complete, paired nearest-note
labels and rhythm-instrument rising-edge counts also match. Compilation success,
melodic count match and actual sound are separate facts. PSG/SCC-only0/0 OPLL
counts are not an oracle; native Segment tone/activity comparisons were saved.
All26 standalone PSG/SCC have no tone-pitch/coverage differences with explicit
startup offset2ticks/tolerance1; some activity/boundary differences remain.

Remaining: bluemtns actual export hits104.67s and extended240s guards although
269/269 melodic attacks match and text ends82.06s. Zero-volume SCC control writes
continue; termination unresolved. Do not bypass guard or call this complete.
custom_voice raw onset drift reaches283.605ms; mixed giselle and other mixed
PSG/SCC differences remain. Full musical/audio equivalence is not established.
No browser GUI or human listening check was performed.

35 focused checks pass: test_mgs_playback5, test_mml_sync13, test_batch_mgs13,
test_export_mgs4. Real replay tests reproduce old successful-compile/zero-Key-On
case, test every definition class/combination and ordinary public export. New
scripts/probe_mgs_audio.mjs measures compiled PCM. Batch now marks unequal melodic
counts mismatch and export exits1 while compilation status stays separate.

Report and regenerated public MML/MGS/replay/selected Segment artifacts:
outputs/diagnostics/mgs_silence_20261024/verification.md/json and summary.csv.
Complete dumps/probes: Windows TEMP/msx_silence_20261024. New focused documentation:
docs/mgs_definition_storage.md. External note:2026-10-24_mgs_definition_terminator_silence.md.

Next allowed action: user regenerate/listen using the fixed ordinary exporter.
Investigate residual termination/timing/capacity from saved intermediate evidence
as separate work. Do not raise pool, suppress errors, change source Segments or
claim full fidelity merely because compilation, count equality or PCM succeeds.
Earlier staged frontend/performance changes and unrelated files are retained.

---

# Completed checkpoint: optional OPLL percussion overlay (2026-10-24)

Saved in the MSX working tree; no staging/commit/push. Earlier frontend/export/
performance-IR work is retained. Current feature: --enhance-drums on canonical
MGS converter, export_mgs and batch entry points; default remains disabled.

Drum inference consumes existing immutable PSG/SCC PerformanceIR. Audibility
spans and strong volume/noise/EG transitions nominate gestures; short noise,
decay plus downward pitch sweeps, or SCC broadband+decay nominate preset rhythm
instruments. Full accepted/rejected catalog and source lineage remain. Thresholds
are experimental, never source Key-On facts. Fixed-volume register decline does
not establish amplitude decay for hardware-envelope PSG.

The native source tracks/Segments remain intact. New target groups reuse ordinary
rhythm repeat rendering on f. Native rhythm wins same-instrument/time collisions;
duplicate inferred hits keep stronger level deterministically. Any native high-
OPLL channel6..8 Key-On with frequency blocks the entire overlay. Native mode and
target MML are unchanged when no hit is added; --force does not bypass the guard.

Projection runs after native rendering/normalization. Applied-clock onsets follow
actual projected PSG/SCC boundaries with source-error/minimum-step checks. Needed
pre-normalization text is retained in memory, independent of --dump-passes. This
was fixed after review found the first implementation depended on diagnostic
before.normalize files. The same-output dump-on -> dump-off applied-clock test
now preserves MML and all6 added test hits without those files.

Verification: related78 checks pass; post-review10 integration checks pass. Public
28 inputs compile and preserve original effective part timelines.25 public inputs
with no additions retain byte-identical MML. Two representatives from the user-
authorized local set compile and preserve source hashes/PSG-SCC timelines:
DSLY4_01 addsBD5; gra2_001_with_sync_mark01 addsSD7/HH3. No full local regression or
audio/listening accuracy claim. Existing rhythm suite has3 allocation assertions
expecting15000 versus committed16000; four ordinary/raw render cases match HEAD.

Reports and small playable examples:
outputs/diagnostics/drum_enhancement_20261024/verification.md/json and examples/.
Large public dumps/test logs remain under Windows TEMP/msx_drum_enhancement_20261024.
See docs/drum_enhancement.md for syntax, exact hypotheses and abstention rules.

Next allowed action: user listening/regression with --enhance-drums and separate
outdir. Refine classification from retained evidence; do not label inference as
hardware attacks, remove source parts, silently steal OPLL melody, or apply FM
state pruning to PSG/SCC curves. No further regression/commit/push is queued.

---

# Completed checkpoint: PSG/SCC performance IR (2026-10-24)

Implementation is saved in the working tree; no staging, commit or push.
The 2026-10-23 frontend/export catch-up changes remain saved as well.
Unrelated README copies, fixture directories and external notes are untouched.

## Completed scope

- PSG/SCC source-audibility spans, ordered pitch/volume/timbre/mode/hardware-
  envelope controls, and conservative inferred note partitions are separate in
  immutable PerformanceIR. Source Segment lineage and sample timing/unknowns,
  zero-time states and boundary reasons remain inspectable.
- One IR feeds existing loop preparation, shared envelope selection and rendering.
  Relative structural keys preserve prior equality; mutable target envelope IDs
  remain outside note identity. Existing partition policy and MML stay compatible.
- --dump-passes emits performance notes/gates/controls/boundaries/segments CSVs
  and JSON summaries. Known stale performance artifacts are removed on rerun.
- New vibrato/portamento/score-attack recognition is NOT implemented. A source-
  audibility gate is not an observed Key-On. Controls are per-Segment state
  snapshots, not independently observed raw register writes. Validation covers
  retained Segment state/order/lineage, not musical or raw-VGM replay fidelity.
- OPLL was explicitly excluded from this stage. Existing export_mgs.py defaults
  remain FM-state24ms / normalization8ms; its underlying batch file is unchanged
  from the preceding catch-up checkpoint.

## Verification

The user explicitly authorized all 59 selected PSG/PSG+SCC local inputs; the one
folder without sync-mark VGM uses its parent VGM as approved. Original SHA-256
values match for all 59 inputs. New MML generation succeeds for all 59; all MML
and 5,048 existing CSV/MML artifacts match the pre-IR renderer byte for byte.
All new performance summaries validate retained Segment state/order/lineage.
These native comparisons use --vgmticks --dump-passes without normalization to
isolate the IR refactor; export defaults are covered independently by tests.

Native MGSC:55/59 compile. DSLY4_02/11/14 and gra2_016_with_sync_mark03 reproduce
Track buffer full with the identical baseline MML. Public PSG/SCC/PSG+SCC:28/28
MML-identical and compiled. Focused suite:65/66 pass; its only failure is the
pre-existing allocation15000/16000 expectation mismatch. Additional CLI/stale-
artifact checks:3/3 pass. No audio-equivalence claim.

SCC has3,755 conservative note partitions spanning multiple sub-tick audibility
spans. This inherited ambiguity is now visible; it has not been resolved by
inventing new attacks or flattening curves. PSG has no such flagged partitions
in this set. Source sample coordinates are known for all retained local rows.

Evidence: outputs/diagnostics/psg_scc_curves_20261023/verification.md/json,
results.csv and performance/public output trees. I: became full during checking;
this task's artifacts were temporarily relocated and incomplete work rerun.
New output trees and aggregate reports are restored under outputs. Baseline
artifacts remain at C:/Users/ef110/AppData/Local/Temp/
msx_psg_scc_curves_20261023/baseline. See relocated_to.txt for actual locations.

Next allowed work: review/listen to the preserved output, then separately design
score-attack/continuous-pitch inference using authored expectations and the new
boundary/control evidence. Do not claim that gate_ambiguity is solved, apply FM
state pruning to PSG/SCC envelopes, or change existing source evidence implicitly.
No further local regression, staging, commit or push is queued.

---

## Export entry follow-up (2026-10-23)

scripts/export_mgs.py delegates to the existing batch runner, with explicit
FM-state24ms / normalization8ms defaults and CLI overrides. No batch source or
shared MgsOptions defaults were changed in this follow-up. Numeric defaults
request optional normalization; unchanged/reason remains visible when rejected.
Other batch behavior, including optional key-on checking, is inherited.
Four focused export checks pass, including a public PSG conversion. Evidence:
outputs/diagnostics/export_mgs_20261023/. Stage3 remains awaiting user patterns.

# Active checkpoint: MGSDRV frontend catch-up (2026-10-23)

Implementation is saved in the working tree. No staging, commit or push.
Existing unrelated README copies/public fixture directories are untouched.
The earlier shared helper/note-normalization edits are retained and extended.

## Current behavior

- Shared immutable MgsOptions feeds the converter and batch. With no normalization
  switches, conventional MSX output remains unchanged. Explicit --fm-state-ms or
  --normalization-ms enables optional normalization; rejected clock/projection
  keeps the ordinary output and records unchanged/reason.
- MSX effective defaults: FM1ms/44samples, correction8ms/352samples. X68000's24ms
  default is not assumed to be OPLL fidelity evidence. FM filtering is confined
  to OPLL melody inside accepted normalization. No independent PSG/SCC clock
  estimator, no whole-gate deletion and no PSG/SCC envelope filtering added.
- Release-final states and both sides of voice/custom-patch/sustain changes are
  protected. Rhythm boundaries obey the correction budget; newly merged distinct
  attacks reject normalization atomically. Original traces/Segments stay native.
- Force uses a validated finite command inventory: known OPM/OPNA/DCSG/MSM6258/
  SegaPCM/second-OPLL writes may be omitted, with exact source offsets/times/data.
  Unsupported-only input, malformed VGM, unsafe decoder variants and PCM stream/
  transfer commands still fail. Mere header clocks and existing undeclared muted
  SCC initialization are separate from forced omissions.
- Batch default timeout1200s. Primary success/conversion_failed/compilation_failed
  with stage/error_code/detail and legacy_status; incremental CSV/JSON plus raw
  logs and per-input report JSON/TXT. Nonempty current-run MML and MGS required.
  Key-on comparison remains independent, with its previous enabled default.
- New conversion, source inventory, force and normalization/FM decision reports
  survive failure. Known stale generated files are removed on rerun; unrelated
  user files/directories are not removed.

## Verification and limits

Public60 inputs:56 compile,4 existing MGSC track-buffer failures (cpebach,
enchanted,turpinh,bridge). Their MML is byte-identical to HEAD frontend output
using unchanged renderers with normalization disabled; HEAD compile also fails.
Authored STATE_PROBE:1ms retains all state runs,24ms omits24 internal pitch states;
both normalize and compile, retain24 attacks and identical native Segment hashes.
Public sample retains the historical applied oracle at explicit16.6667ms budget;
new8ms default may safely abstain. Segment evidence stays identical.

Related suite:117 checks,116 passed and1 pre-existing failure. Results are in
outputs/diagnostics/msx_catchup_20261023/focused_tests.json/log. The allocation assertion expecting15000 versus committed
16000 is pre-existing and is not edited; HEAD/current behavior is identical.

Existing libkss roundtrip check is NOT validated as passing:18/19 public OPLL
exports hit its duration guard, one compares19 source Key-Ons versus0 output.
That one has byte-identical HEAD/current MML and MGS and the same HEAD mismatch.
No blanket playback-equivalence claim. The export/runtime cause is not resolved
by this frontend catch-up. --skip-keyon-counts is available for compile-only runs.

All evidence: outputs/diagnostics/msx_catchup_20261023/.
Docs: docs/note_normalization.md, docs/mgs_force.md, docs/batch_mgs.md.
External private note: field_notes/2026-10-23_msx_frontend_catchup.md.

## Next allowed action

User runs local_only threshold sweeps/listening and may commit this checkpoint.
Stage3 (separate one sounding note from typed pitch/volume/timbre curves) has NOT
started. The user will provide its test patterns; wait for those before starting.
Do not blanket-prune PSG/SCC SW-envelope curves, relax compiler limits silently,
claim that a requested threshold was applied without inspecting its status, or
change unrelated allocation expectations to make this suite green.

---

## 2026-10-11: third-party license and copyright notices

- File edits only; do not stage, commit, push or switch branches without user request.
- README now credits external compilation/playback/development tools and displays
  Copyright (c) 2026 emef2247 with the project MIT link in both language sections.
- THIRD_PARTY_NOTICES.md retains vgm-conv ISC mapping attribution, MGSC/libkss
  notices and embedded-driver exceptions, and exact mmlx/soundlog MIT texts.
  Code headers link these notices; conversion algorithms are unchanged.
- Checked mgsc-js2.0.0 registry/source and installed libkss-js3.1.0. Native mgsc
  installed revision is unknown. MGSC.COM and MGSDRV have separate historical
  distribution terms; ISC wrapper metadata does not license every driver.
- A complete npm/WASM or Rust binary redistribution bundle still requires all
  bundled/transitive component notices. No dependency reinstall or private-data run.
- Pre-existing OPM/MDX work is preserved. Next allowed action: user review of
  this license-only diff; no conversion behavior or clock work is part of this task.

## 2026-10-07: native musical MDX renderer rebuild

- Work location: emef2247/test/msx_vgm2mml. Native OPM traces/Segments and
  integrated CSV are unchanged. Reference 32 MML/MDX pairs match originals on H:.
  Twelve missing VGMs generated from original MDX/PDX and saved beside reference/.
- New structured default groups Key-to-KeyOff notes with complete internal
  trajectories; infers a safe score clock; reuses MGSDRV source loop planning
  before target compaction. Partial/unknown/zero-time/unsafe same-tick cases keep
  explicit controls with reasons. Old behavior is --notation legacy/registers.
- Native converter and verifier installed. --reference-mml-only selects original
  score cases. --mdxdump optionally adds external reference/generated metadata
  audit; reference contents are never used as production conversion choices.
- 83 OPM/MDX checks plus 8 common-loop checks pass; public 38/38 external
  roundtrips. Local reference 30/32 pass projected Keys/known states/time;
  FF4WM1 and KMSM009 still exceed MDX offset capacity. MML/evidence retained.
- Record: field_notes/2026-10-07_mdx_musical_output.md; usage docs/opm_mdx.md.
  Listening/results: C:/Users/ef110/Documents/Codex/2026-09-25/co/tmp/mdx-rebuild/
  outputs/reference-benchmark-musical and outputs/public-musical.
- Next: user listening/MMDSP checks; two capacity cases; software LFO/tempo
  recovery and then integration with PSG/SCC target. No macros added yet.
  Do not fabricate Keys for meters, borrow reference score parameters, alter
  source CSV/schema, or add OPM to README. User .gitignore change preserved.
- No staging, commits or pushes performed.

## 2026-10-06: selectable FM PSG tone is the OPM default

- Main: --target opm defaults to --psg-model fm; additive remains selectable.
  --target opm-additive explicitly preserves the old model. MGSDRV stays default.
- FM AL4/FB7 profile independently implemented in py/psg_opm_fm.py; external
  converter code was not copied or added as a runtime dependency. SCC remains
  waveform-additive. Noise/hardware EG still fail explicitly.
- --opm-pitch-policy clamp|error; FM default clamp is an exposed approximation,
  additive default retains prior error/zero-target-duration omission policy.
  Requested/actual frequencies, cents and reasons stay in the target CSV.
- Reused the user's committed common read_vgm_header helper in py/vgm_io.py;
  this supersedes the earlier missing-header blocker for this converter.
- 19 focused checks pass. Public PSG: 11/13 external roundtrips per model;
  two noise cases unsupported. Local FM GRA1_03/GRA1_05/DSLY4_04/GRA2_17 all
  verify. Source Segment CSVs identical across 34 comparisons.
- WAVs/MDX/VGM/listening artifacts: outputs/opm/fm_default_2026-10-06/.
  New FM spectra/levels are close to external vgm-conv for two measured songs.
- test_vgm_io has an existing stale title-space expectation (one failure);
  no GD3 change was made. See field_notes/2026-10-06_psg_fm_default.md.
- MDX note-renderer redesign remains paused; it supports AL7 only. Do not apply
  its preview script to the new FM plans or invent KeyOns for graphical meters.
- Usage: docs/psg_scc_opm.md. No README edits, staging or commits performed.

## 2026-10-06: MDX display audit; sound-conversion priority

- User paused further MDX MML rendering changes. No renderer, native Segment,
  test or fixture changes in this audit. User note-MDX run: PSG 42/45 verified;
  PSG/SCC 15/23 verified; 11 external MDX offset failures in total.
- MMDSP MADRV level/spectrum graphics depend on new KeyOn notifications.
  Continuous ties explain initial meter/then peak-only behavior; not every
  static-display case was reproduced or diagnosed. Volume data is present.
- Recorded field_notes/2026-10-06_mdx_display_regression.md and
  field_notes/2026-10-06_psg_opm_conversion_audit.md. Existing source/result CSVs
  audited; local WAVs/plots/metrics under outputs/opm/diagnostics_2026-10-06.
- First failures: PSG noise/EG20, pitch17, MDX offset2; PSG/SCC noise/EG141,
  pitch26, offset7, dual/variant guard65. Counts include split inputs.
- GRA1_03 period-zero intermediate states last 2 samples; one falls across an
  MDX tick boundary and throws, another rounds to zero and is omitted. Address
  this in an inspectable target projection, never by deleting native evidence.
- GRA1_05/DSLY4_04 same-renderer WAV comparisons confirm less high-frequency
  energy and lower current gain in additive output than vgm-conv. No quality
  score or blanket sound-equivalence claim. vgm-conv does not reconstruct full EG.
- Next: bounded PSG transient/noise experiments, then mixed mixer and shared EG
  with explicit source-to-target plans. Eight-part PSG+SCC allocation needs a
  noise/operator-sharing decision. MDX display changes stay paused.
- Fresh additive regression needs the user's codex/mdx_vgm_header_parsing branch
  integrated: read_vgm_header is currently absent in this checkout. No branch
  switches, merges or code restorations were performed.

## 2026-10-05: local PSG/SCC additive listening entry

The experimental opm-additive path is present in this checkout. Shared header
reading accepts AY VGM 1.51. DSLY4_04 was compiled to MDX/VGM and verified against
7,568 projected controls; nine focused PSG/SCC projection tests passed.
See docs/psg_scc_opm.md for local directory conversion. Noise/hardware EG remain
unsupported. No switch to vgm-conv timbres has been made. The user's
legato_patch_mix listening report has an unconfirmed file identity and must not
be transferred to redundant_fnum_writes as an established observation.

# Current handoff

## General tonal PSG/SCC -> OPM output (2026-10-05)
- vgm2mml.py --target opm-additive emits only MDX MML by default; --dump-passes
  retains integrated native source CSVs and explicit target projections. Default
  MGSDRV output unchanged. No source fixtures or source Segment semantics changed.
- scripts/psg_scc_to_mdx.py supports directory runs, external compilation and
  results.csv/json; --comparison-dir retains matching existing OPM VGM copies.
- Public PSG: 11/13 verified; SCC: 12/13 verified. All 23 target write streams
  match external playback. Eight tests pass. Audio equivalence not claimed.
- Unsupported: PSG legato_patch_mix/patch_change_midnote (noise), SCC short_pulses
  (active OPLL). PSG block_boundary actually plays SCC. Initialization-only OPLL
  and zero-volume zero-clock SCC writes are accepted and counted explicitly.
- Listen: outputs/opm/psg_scc_public/LISTEN.md; compact files under listen/.
  Next: user listening, then noise/EG support if requested. Future OPN/OPNA/OPS
  targets should reuse spectral analysis rather than native OPM register state.
- Usage and limits: docs/psg_scc_opm.md. README remains unchanged.

## GRA2_17 PSG/SCC additive OPM prototype (2026-10-05)
- Separate scripts/psg_scc_to_mdx.py and py/psg_scc_opm.py; native Segments and
  default converter unchanged. Seven active source parts mapped independently.
- Listening files: outputs/opm/psg_scc_prototype/GRA2_17/GRA2_17.mdx and .vgm;
  MML: GRA2_17.mdx.mml. All 2438 target writes match external MDX playback.
- Five focused tests pass. Approximate harmonic timbres/gain, no acoustic equality
  claim; unsupported noise/EG rejected. Three zero-target-duration shutdown
  pitch states explicitly marked omitted, source rows retained.
- See docs/psg_scc_opm.md and field_notes/2026-10-05_gra2_17_opm_prototype.md.

## PSG/SCC -> OPM target investigation (2026-10-05)
- Audited all 17 NEMESIS2 GRA2_*.vgm through existing PSG/SCC Segment builders;
  inspected 18 MSXGRA2S MDX tone banks and MS.X chapter7. No converter changes.
- Source clocks both 1789772 Hz; state-active positive-duration SCC rows expose
  22 distinct waveforms. Noise in15 songs, mixed tone/noise in14, hardware EG in12.
  Four selected harmonic bins capture 86.90% duration-weighted discrete AC energy;
  this is not a target synthesis quality score. Even harmonics must be considered.
- Propose explicit cross-chip target plan, additive baseline with source amplitude
  trajectories and held keys, H allocation for the observed noise channel.
  Do not fake native OpmSegments, split source CSVs or copy manual reference patches.
- Start GRA2_17; then GRA2_05 (noise), GRA2_03 (hardware EG). Manual MDX numbering
  differs; match titles/phrases. Returned OPM compares to target plan, while
  cross-chip likeness additionally needs spectrum/envelope/listening evidence.
- Record: field_notes/2026-10-05_psg_scc_to_opm_plan.md. Private analysis artifacts:
  C:/Users/ef110/Documents/Codex/2026-09-25/co/tmp/psg_opm_study/.
  This investigation preceded the GRA2_17 prototype above.

## Rtype03 MGSC allocation diagnosis (2026-10-05)
- Current RTYPESMS/Rtype03 fails `Can't allocate` at #alloc totaling 16000;
  saved hierarchical_loop result already failed `Track buffer full` on ch9.
  Saved current GF2SMS02 compilation succeeds after the user's pool increase.
- MGSC 1.11 diagnostic isolated full-channel used bytes: 9=1861, a=1412,
  b=12991, c=398, d=6210, e=85; music total=22957. Unchanged full music cannot
  fit a 16000 pool by redistribution alone. This is not a successful combined
  MGS or an audio comparison.
- One-note setup probes reproduce allocation failure with the custom voice;
  without that setup, 16000 allocates successfully. Successful setup probes
  show an additional 903-byte track0 definition allocation (10 bytes used).
  Pool increases are not universally safe; no universal limit was inferred.
- Existing mgsc-js/MGSC1.11 used for diagnostics; native log confirms original
  failure. Source, Segments, production code and user's total=16000 edit intact.
- Record: field_notes/2026-10-05_rtype03_mgs_allocation.md. Private diagnostic
  copies/logs: C:/Users/ef110/Documents/Codex/2026-09-25/co/tmp/rtype_alloc/.
  Next: target-only compression/size estimation investigation for b/d if requested;
  do not drop attacks/channels or reshape Segments to satisfy capacity.

## MDX pre-macro target compaction (2026-10-05)
- Added py/mdx_compaction.py after native source-loop projection: conservative
  setter reuse plus exact rest/tied-note duration factoring. MDX macros remain
  unimplemented. OPLL continuation/inner loops and PSG/SCC loop-before-envelope
  behavior were reviewed; source interpretation and integrated CSVs stay intact.
- Raw tone writes invalidate cached voice/volume/pan; each source-loop entry
  retains its first setters. Untied notes remain distinct attacks. Tied chunks
  keep & inside their loop body; rests keep identical 128-tick chunk sequencing.
- Dump adds .uncompacted.mml and .compaction.csv; timing separates source loops
  from total duration loops and records setter omissions/estimated byte savings.
- 12 compaction tests and 58 OPM tests pass; public fresh roundtrips 38/38 pass.
  Local 52 saved targets: 35 old successes retained, M_G2_08S newly succeeds,
  16 capacity failures remain. All 36 successful comparisons have zero Key
  missing/extra and known-state mismatches (17,506 channel attacks both sides).
- Same old successful 35: MML 1,453,826 -> 1,165,412 chars; MDX 639,547 ->
  443,491 bytes. M_G2_18S text grows 14 chars but binary shrinks 102 bytes.
- Fresh M_G2_08S: 166,872 -> 145,270 chars, 56,208-byte MDX; original Segment,
  trace and target-unit CSVs unchanged and uncompacted MML matches previous.
  Fresh WARNOP still exceeds MDX capacity. No clock retuning or noise/held-control
  lowering added; source keys, timing and comparison rules remain unchanged.
- Record: field_notes/2026-10-05_mdx_pre_macro_compaction.md.
  Evidence/listening MML/MDX/VGM: outputs/opm/pre_macro_compaction/.
- Next: evaluate compact held/noise target expression from native evidence;
  do not insert retriggers, reshape Segments or weaken comparison for capacity.
  README remains unchanged; no staging/commit was performed.

## Structured local OPM/MDX regression review (2026-10-05)
- Reviewed the user's completed outputs/opm/regression/structured_local_only run:
  186 inputs = 35 success, 17 conversion_failed, 134 unsupported_target (3,579,580 Hz).
- Successful cohort: channel attacks 15,749/15,749, operator KeyOns 57,468/57,468,
  operator KeyOffs 57,200/57,200; missing/extra Keys and known-state mismatches=0.
  Projected timing/end match; maximum source projection error is 6 samples.
  Four source end times differ from returned/projected ends by 1–5 samples.
- Flat/structured text totals for successes: 1,580,660 -> 1,453,826 chars (-8.02%);
  660 emitted loops, 26 cases with loops, largest depth 3. No prior-run baseline.
- All 17 failures generated MML but external MDX compilation failed on cumulative
  track offsets >0xfffe; no returned MDX or fidelity verdict. Track 8 is the
  compiler's PCM dummy track, not a ninth OPM channel. This is not a timeout.
- Physical-command byte estimates checked against all eight FM track spans in
  all 35 successful MDX files. Failure breakdown points to H/noise/held controls,
  repeated setters and duration splitting; no source information was discarded.
- Record: field_notes/2026-10-05_opm_structured_local_regression.md.
  Derived summary/capacity CSV/JSON: outputs/opm/regression/structured_local_only_analysis/.
- No conversion code/tests/fixtures changed and no new full regression or audio
  comparison run. Original regression artifacts retained. Next: evaluate target-only
  setter reuse, duration factoring and conservative held/noise note lowering with
  inspectable native/target evidence. Do not reshape Segments to pass capacity,
  weaken Key/state comparisons, fake a 4-MHz source clock, or announce OPM in README.

## OPM source-derived channel loops (2026-10-05)
- User confirmed the native chords_mix.opm.segments.csv and clarified scope:
  preserve VGM->Segment and integrated all-channel CSV; work on source phrase
  structure and its MDX MML projection. Do not split CSVs or source streams.
- Removed the unnecessary analysis.streams partition and streams.csv output.
  Ownership labels remain on existing rows; complete native state is retained.
- py/opm_loops.py builds ch-local source phrase and inner Segment plans before
  target spelling/tone assignment. Equality uses exact source samples, complete
  state/Key edges and reset/timer effects. Zero-time inactive setup remains
  members/inner evidence; zero-time attacks and positive released tails remain.
- MDX projection maps source members to target commands, explicitly rejects
  boundary ambiguity and checks exact expanded tokens. No normalization, source
  time edits, macro extraction or native tail splitting. Source loop paths and
  phrase IDs append to the single native Segment CSV; no per-ch source CSVs.
- 58 OPM tests passed. Public38/38 and short local2/2 roundtrips passed with
  zero missing/extra Keys or known-state mismatches. Rules have native evidence
  tests; final roundtrip agreement is a separate validation step.
- Evidence/listening: outputs/opm/source_loops_20261005/.
  Record: field_notes/2026-10-05_opm_source_loops.md. README/source fixtures
  unchanged. No staging/commit. MDX target still uses the separate
  scripts/opm_to_mdx_mml.py; regular main converter remains MGSDRV output.

## OPM MDX channel separation (2026-10-04)
- User required channel separation before loop work. Native Segments already
  have ch0..7; raw OPM CSV now adds ch/register_scope and checks ownership.
- MDX default is channels A..H, independent time cursors from common origin.
  Shared controls occur once on A; noise is ch7/H. Native noise state/intervals
  no longer fan out to unrelated channels. All other shared snapshots remain.
- --notation registers --track-layout conductor keeps the prior source-ordered replay.
  Controls CSV distinguishes physical ch from mdx_track; no silent fallback.
- 42 OPM unit tests pass; independent channel-separated roundtrips pass all
  38 public inputs and two short local M_G2_17S/M_G2_18S inputs. Missing/extra
  channel/operator Key edges=0, known-state mismatches=0, projected-time delta=0;
  source timing delta<=6 samples. Equal-tick cross-channel order can change and
  is explicitly predicted/reported; comparisons have not been weakened.
- Evidence and listening MML/MDX/VGM: outputs/opm/channel_tracks_20261004/.
  Record: field_notes/2026-10-04_opm_mdx_channel_tracks.md.
- This was the earlier register-only stage; ordinary note/@voice and loops
  are now implemented above. Macros remain future work. Fixtures and README unchanged.

## README publication scope (2026-10-04)
- User requested that OPM support remain unannounced in README.md for now.
- Removed OPM/MDX introduction, feature bullet, command example and documentation
  links from README; existing implementation and technical records are retained.
- Keep the public README focused on PSG/OPLL/SCC to MGSDRV MML until the user
  explicitly approves announcing OPM support. Documentation-only change;
  verified the README diff and absence of OPM/MDX references.

## MSXGRA2S Segment replay listening outputs (2026-10-04)
- All 18 private OPM inputs have verified Segment -> MML -> MDX -> VGM outputs:
  outputs/opm/mdx_roundtrip/msxgra2s_20261004/listen/ (54 files).
  listening_results.csv/json and listening_summary.json retain final evidence.
- 20,141 source/returned channel attacks; missing/extra channel/operator keys=0;
  known state/order mismatches=0; source/projected timing delta=0 for these inputs.
  This is control preservation, not an audio/hardware equivalence assertion.
- Four oversized conductor-A tracks use listening-only conductor-W spelling and
  extended MDX layout. No clipping, dropped controls or added PCM. Exact command
  relabeling and returned Segment comparisons pass. Core defaults unchanged.
  Details: handoffs/local_only/msxgra2s_segment_replay_listening.md.
- User supplied an X screenshot proposing additive AL7 1/3/5/7 carriers and DFT
  level fitting. Recorded candidate and limits in
  field_notes/2026-10-04_opm_additive_harmonic_mapping.md.
  SCC waveform -> OPM target mapping is still unimplemented; do not imply this
  OPM roundtrip performs cross-chip translation. No files staged or committed.

## MSXGRA2S direct MDX fixtures and timbre investigation (2026-10-04)
- All18 original private MDX files played directly into same-directory VGM;
  native OPM traces/Segments retained under outputs/opm/msxgra2s_import_20261004/.
  Original MDX hashes unchanged; no PCM/PDX and no new pitch retuning.
- Read private DOC. Human port uses approximate MSX part roles, not a strict
  channel/song-number oracle. Match song titles; MDX13 corresponds to gra2_005.
- Investigated SCC reference wave -> OPM patch candidates. Recurring algorithm/
  harmonic-ratio families exist, but multiple waves can share a patch and one
  wave can use different FM envelopes. Do not introduce a dataset-specific or
  wave-only conversion invariant. Complete private evidence and limitations:
  handoffs/local_only/msxgra2s_scc_opm_timbres.md.
- Helper adds --from-mdx (preserves compiled input) and --inspect-mdx (typed
  tone-bank CSV). README updated.35 OPM tests pass;9 public MDX direct replays
  byte-identical; inspector smoke verified. No staging/commit performed.
- Possible next work: generic clock-aware Target pitch conversion, or a separately
  inspectable waveform/envelope -> FM profile experiment, only as requested.

## Public/local OPM roundtrip and listening run (2026-10-04)
- User requested local_only as well as public validation, retaining MML/MDX/VGM.
  All206 inputs classified: public38/38 success; local23 success,11 external
  MDX16-bit offset failures,134 unsupported3,579,580Hz clocks. No retuning,
  dropped controls or clipped end times; those limits remain unresolved.
- Results: outputs/opm/mdx_roundtrip/listening_20261004/{public,local_only}/.
  listen/ contains61 successful stem-named MML/MDX/VGM sets; copied183 files
  are byte-identical. listening_index.csv lists all206; summary.json totals.
- Successful cases have0 missing/extra channel/operator Key edges and0 known
  state differences; exact retained control order/projected time. Original
  source timing delta<=6 VGM samples. These are not waveform/hardware tests.
- New field note: field_notes/2026-10-04_opm_catalog_roundtrip.md. Private
  failed/listening case paths: handoffs/local_only/opm_catalog_roundtrip_20261004.md.
- Batch excludes reference/expected replay VGMs; accepts VGM/VGZ/gzip inputs;
  classifies unsupported headers early, saves progress CSV+JSON and failure
  logs. Helper saves compiled MDX before playback. All35 OPM tests pass.
- No source/Segment interpretation changed, no PSG/SCC direct mapping added.
  Next: user listens; clock-aware target and MDX capacity handling are separate
  work. Do not claim unsupported/compilation-failed cases passed. Do not stage
  generated/private assets or alter the separate test repository.


## Refreshed PSG-derived OPM fixtures: review (2026-10-04)
- Reviewed the user-supplied private square/pulse references and the moved
  I:/wsl/repositories/test/vgm-conv generator. Detailed local-only notes:
  handoffs/local_only/psg_scc_to_opm_review.md. Do not publish source assets.
- All13 refreshed from_psg VGMs match generator outputs and declare4MHz OPM.
  Their reference MML is original PSG intent, not a native OPM/MDX oracle.
- Fresh MDX MML/MDX/VGM/Segment replay passed13/13:2331 retained controls,
 52 channel attacks,169 operator KeyOns,0 KeyOffs; missing/extra edges and
  known-state mismatches0. Source timing difference<=6 samples, target timing
  exact. Results: outputs/opm/mdx_roundtrip/from_psg_20261004/results.csv/json.
- Keys occur only at initialization; subsequent audibility/pitch uses TL/KC/KF.
  A musical renderer must preserve these sustained gates, not add attacks at
  volume changes or inferred notes. Two cases activate noise; none selects a
  source PSG hardware envelope. No hardware-envelope or SCC waveform claim.
- Investigation only: no source-to-OPM mapping or renderer behavior changed.
  Next: agree square/pulse target policies and independent SCC level/waveform
  treatment. Keep direct PSG/SCC projection separate from native OPM decoding.
  OPLL profiles and reverse OPM->MSX composite voices remain deferred.


## OPM output packaging (2026-10-04)
- Regular scripts/opm_to_mdx_mml.py output is <stem>.mdx.mml only by default.
  --dump-passes keeps native/target CSVs and timing JSON. Native Segments are
  still constructed; internal traces are temporary unless dumps are requested.
- The roundtrip verifier always retains intermediate evidence. Existing dumps
  are not purged. README presents OPM input -> MDX MML output as the feature.
- All31 OPM tests pass, including CLI output inventory, byte-identical MML
  across default/dump modes and retained Key evidence. Earlier roundtrip
  measurements remain valid; rendering and source interpretation are unchanged.


## OPM MDX control target and public roundtrip (2026-10-04)
- Added py/opm_mdx.py, py/opm_roundtrip.py and two separate CLI tools:
  scripts/opm_to_mdx_mml.py / scripts/verify_opm_mdx_roundtrip.py.
  Target consumes native Segment objects, not a raw VGM passthrough.
- First target emits ordered y register controls on conductor A; ordinary
  MDX note/voice notation, musical compression and PCM are not implemented.
  One 4 MHz YM2151 only; other native inputs remain analyzable but rejected
  by this target. Absolute timing projection @t255 preserves the source data.
- All38 current public OPM inputs passed external MML/MDX/VGM/Segment replay:
  no missing/extra KeyOn/KeyOff or known-state/control-sequence mismatches.
  Maximum source timing difference6 samples;363 positive intervals collapse
  while preserving write order/edges. No acoustic equivalence claim.
- Existing PSG/SCC/OPLL public conversion baseline also passed (one aggregate test).
- 30 OPM tests pass, including nine committed original synthetic replay VGMs
  and negative checks. mmlx0.2.0/soundlog0.15.0 remain external test tools.
  Verifier derives playback max-ticks from source end, retaining long cases.
- Removed three unconverted from_fm/rhythm_only_test0* cases as requested.
  All13 from_psg cases retained. Current inputs:16 from_fm +9 from_mdx +13 from_psg.
- Results: outputs/opm/mdx_roundtrip/public_all/results.csv and results.json.
  Usage: docs/opm_mdx.md; record: field_notes/2026-10-04_opm_mdx_roundtrip.md.
- Earlier sections describe historical stages. Their no-target claims are
  superseded by this section. Private game VGM regression has not been run.
- Next: review register output/CSV, then design readable MDX notes/voices
  without losing partial keys, held controls, shared state or source evidence.
  Do not assume OPLL note/fnum semantics, discard zero-time controls, add an
  external compiler dependency to the engine or change existing MGS rendering.


## Original public OPM MDX fixtures (2026-10-04)
- Authored nine synthetic MDX MML cases under tests/fixtures/public/opm/from_mdx.
  Source patches/phrases were newly written; no private/game music or PCM used.
  MML, generated MDX and VGM follow the repository MIT license.
- Covers all8 channels/pan, partial keys, held pitch/patch/TL changes, hardware
  LFO/depth latches, channel7 noise, same-time pulses/redundant keys, release
  retriggers, distinct operator banks and finite nested phrases.
- External generator: scripts/mdx_fixture_generator (mmlx0.2.0/soundlog0.15.0);
  Python regeneration wrapper: scripts/generate_opm_public_fixtures.py.
  These are generation-only dependencies, not conversion-engine dependencies.
- Manifest keeps provenance, hashes and authored intent counts. Nine new fixture
  checks plus prior OPM checks pass (22 tests); inspectable CSVs/results are
  retained in outputs/opm/from_mdx. Regeneration reproduced all hashes.
- No Segment-to-MDX renderer or OPM audio roundtrip added. All earlier migrated
  inputs remain; native MDX fixture coverage supplements their limitations.


## MDX/MML OPM fixtures (2026-10-04)
- Matched and copied 32 private MML+MDX pairs; five MMLs have no paired MDX.
  Inputs are in tests/fixtures/local_only/opm, preserving title directories.
- mmlx 0.2.0 + soundlog 0.15.0 generated 20 VGMs. Twelve MML dialects are
  unsupported; source references and detailed failure logs are retained.
  No musical commands were dropped and no MDX fallback input was substituted.
- All 20 native analyses preserve raw KeyOn/KeyOff counts and source end.
  Reference MDX conversion agrees on KeyOn counts/end for all20, exact OPM
  write sequences for17; three have one final KC write difference at end.
- Results/logs/CSVs: outputs/opm/mdx_preparation. Provenance manifest:
  tests/fixtures/local_only/opm/preparation_results.json. Record:
  field_notes/2026-10-04_mdx_opm_fixture_preparation.md.
- Rust/toolchain and fixture generator remain external to the engine and
  system PATH. No user Rust installation was needed. Existing13 OPM tests pass.
- User's eventual MDX-only validation path needs Segment -> MDX MML output;
  that output stage has not been implemented. Private material stays ignored.


## OPM native state and Segments (2026-10-04)
- User supplied 19 public migrated OPM VGMs. Added py/opm.py after the existing
  vgm_reader command loop: raw writes -> effective state -> OpmSegment.
  Reader CLI and vgm2mml dump/debug write *_trace.opm_regs.csv,
  *_trace.opm.csv and *.opm.segments.csv. Eight legacy return paths remain
  compatible; no OPM target MML renderer has been added.
- All 19 source traces/state/intervals checked:5940 writes,6491 Segments,
  249 source/Segment channel attack events and996 operator KeyOns.
  No missing/added operator KeyOns. Source end and interval continuity checked.
  Local generated results are in outputs/opm/from_fm; record is
  field_notes/2026-10-04_opm_native_segments.md. Usage: docs/opm_segments.md.
- 13 OPM tests passed, including all19 fixtures. Known existing input GD3
  space expectation failure remains unrelated and was already reproduced with
  HEAD. No OPM playback or Segment-to-VGM roundtrip is claimed.
- Existing public conversion baseline regression passed, along with the
  VGM timing/loop checks. Existing PSG/SCC/OPLL conversion is preserved.
- Reuse existing integer VGM timing. Preserve KC/KF, four named operators,
  partial key edges, shared LFO/noise and source-event order. Key-bit and
  operator-register orders differ; AMD/PMD must remain independent states.
- Unwritten parameters are unknown; initial cleared Key gates are explicitly
  assumed. Gate release does not imply silence. Frequency Hz, acoustic
  envelope/LFO/timer simulation and CSM attacks are not yet modeled.
- Supplied Key writes use channel0/masks0/15 only; three rhythm-only inputs
  have no OPM Key writes. Synthetic tests cover additional channels, partial
  keys, dual instances and shared controls. Reference MML is pre-OPM context.
- Next: review native fields/CSV with user before adding frequency derivation,
  higher note interpretation or source replay. Do not map OPM into OPLL's
  fnum/volume model, discard zero-time evidence or imply full CSM coverage.
- The independent Segment engine remains the goal. mml2vgm is a possible
  external validation-data tool only; do not incorporate its code or add a
  compiler dependency to the converter.

Date: 2026-09-28
Status: ready to resume

## Last completed
- Added target-stage PSG/SCC rest cleanup and software-envelope extraction in
  py/mml_envelopes.py. Source Segments are unchanged; target_notes CSV and target
  MML are retained with --dump-passes. Shared envelope bank is limited to 32.
- Removed silent tracks from final body, allocation and sync-point calculation.
- Checked both supplied envelope fixtures in standard/raw modes and gra2_003:
  rendered pitch/volume/mode/wave state matches Segment intervals tick by tick.
- Full suite of 29 tests passed, then all six envelope tests passed after adding
  hardware-envelope/retrigger and definition-limit fallback coverage.
- Corrected SCC to five channels, one enable bit per channel, and shared
  waveform updates for channels 4/5 (MML 7/8).
- SCC PASS1 now describes post-write state until the next event; PASS2 does
  not move waveform-setup time into later notes. Repeat compression preserves
  duration and only groups identical adjacent states; waveform/volume/octave
  changes are applied immediately by the MGS renderer.
- Merged #alloc now distributes 15000 proportionally to emitted track-text
  size (excluding whitespace, track IDs and comments). Silent tracks get no
  allocation; their MML is retained pending a later cleanup step.
- gra2_002 raw SCC tracks 4..8 each total 356 ticks, matching trace intervals.
- Public conversion checks now use trace-state timing/pitch/volume assertions
  for SCC rather than old hashes that encoded the corrected bugs.
- Added --sync-min-gap (default 1000 target-MML steps, 0 for all shared points).
  Select the first shared boundary at least that far from the previous marker;
  start and final end are always retained. No note splitting or retiming.
- Fixed blank-line accumulation when sync annotation extracts track bodies:
  final header now keeps at most one blank separator. Regenerated outputs/check/giselle.mml;
  all nonblank lines (including music and sync comments) match the previous output.
- Added shared step comments to final merged MML via py/mml_sync.py. Common
  boundaries are calculated across all still-playing channels in target MML time.
- Preserved expanded note/command timelines; loops crossing a marker are expanded
  only as needed. Event/PASS/Segment generation remains unchanged.
- Verified all 20 existing/current unittest methods (including 134 conversion
  scenarios), then all 10 sync tests after adding a two-mode mixed-VGM CLI test.
- Verified all 12 mixed public VGMs in standard and raw modes (24 conversions).
- Documented sync semantics and time units in docs/mml_sync.md.
- Refactored PSG/SCC into event CSV -> analysis -> immutable chip-specific Segment -> MML.
- Added py/psg.py, py/scc.py and py/chip_segments.py; renderers consume named fields.
- Retained PASS0-3 and added Segment/waveform CSVs. --dump-passes now keeps input event CSVs.
- Initial 134-case comparison preserved an existing SCC-header bug. Corrected
  the clock offset from 0xCC (ES5503) to 0x9C (K051649), added header-boundary
  checking and clock-flag masking. Regression expectations now come from the
  old non-Segment converter plus only that header fix.
- Verified SCC note output from an unmodified public VGM; header tests added.
- Header correction validation: all 11 unittest methods passed, including 134
  conversion scenarios against the header-corrected pre-refactor reference.
- Inspected PSG zero-length/envelope fields and SCC waveform/Segment CSVs.
- Documented the architecture and preserved legacy heuristics in docs/psg_scc_segments.md.

## Unfinished
- No required implementation remains for automatic shared sync comments.
- Completed rest-only track removal, deferred rest-time controls, and explicit
  volume-hold envelope definitions. Fitting compact linear ramps (= syntax) is
  not implemented; supplied references therefore differ in envelope spelling.
- Supplied envelope reference lengths differ from VGM-derived timing by 3 ticks
  for 001 and 2 ticks for 002; do not claim exact reference-file equality.
- gra2_002 is not yet an exact match to the hand-authored reference: initial
  timing, PSG behavior and envelope representation remain distinct. Allocation
  weights are textual estimates, not measurements from an MML compiler.
- Hardware playback and WSL execution have not been checked.
- Changes are local and uncommitted; existing user-generated/untracked data was left intact.

## Next allowed action
- Review the local diff and run `python -m unittest discover -s tests -v`.
- Treat any changes to timing, waveform reconstruction or note-boundary heuristics as separate work.

## Do not do next
- Do not discard event/PASS evidence or replace chip-specific fields with OPLL defaults.
- Do not mistake 0xCC for SCC or infer valid conversion from old-output equality alone.
- Do not overwrite private fixtures or regenerate regression hashes to hide a mismatch.

## OPLL rhythm inspection update (2026-09-28)

Added native `.opll.segments.csv` output before target voice assignment,
including rhythm channels. Preserved legacy dumps and MML behavior. Added
optional reference parity tests for traces, PASS1-4 and rhythm Segment fields,
and synthetic edge-expansion tests. Private reference data remains untracked.
Next: assess remaining edge cases through the complete pipeline, then agree
on a common rhythm schema before implementing rhythm MML output. Do not
interpret source rhythm flags as independent triggers; use keyon and channel.

Validation: all 37 unittest methods passed (including 134 conversion cases
and all three optional rhythm references). CLI sample Segment CSV contains
282 rhythm rows; merged sample MML is byte-identical to the pre-change output.

## Rhythm grouping update

Added rhythm_patterns.py and group/definition/occurrence CSVs under --dump-passes.
Preserves native Segment data and MML output. Exact adjacent repeats only;
no timing tolerance or common OPNA schema yet. Tests reconstruct timing and
hit states from exported patterns and check every source reference, duplicates,
volume/pitch distinctions, initial silence and the unknown final gap.
Next: review sample patterns before implementing MGSDRV rhythm rendering.

Validation: all 42 unittest methods passed, including the existing 134-case
conversion regression. Sample: 282 input hits, 213 groups, 18 definitions and
71 occurrences; expanded pattern data matches groups and source references.
The sample merged MML remains byte-identical to the previous output.

## Timing field note

Recorded the external oplldrv/libkss timing evidence and sample recalculation
in field_notes/2026-09-28_mgsdrv_libkss_timing.md, linked from project knowledge.
This is documentation only: do not globally replace the existing 60 Hz clock.
Future timing profiles must separate VGM samples, playback frames and MML steps.

## Rhythm MML output update

Implemented rhythm_mml.py, OPLL target projection selection, rhythm-aware sync
and allocation, and five semantic tests. Exact loops and absolute per-drum
levels preserve group onsets/volumes. Legacy melodic variants remain unchanged.
All 47 tests passed. Six fixtures in both modes match grouped rhythm events.
All eight isolated rhythm outputs compile with MGSC 1.11 / mgsc-js 2.0.0;
full sample normal/raw and sx01v raw compile. Other full outputs hit source
length or melodic track buffer limits. No listening test performed.
Next: user playback review; overall melodic size/allocation tuning remains
separate. Do not apply a global 59.94 Hz correction or collapse duplicate hits.

Rhythm tail correction: target end includes the latest OPLL trace tick as
well as Segment ends. Attack-only rhythm Segments omit the final key-off;
using their ends alone truncated the last cymbal in rhythm_only_test02.
The fixture now ends at tick 77 rather than 41, retaining its tick-40 attack.
This does not reconstruct unlogged trailing VGM waits or acoustic decay.
Seven rhythm renderer tests pass, including normal/raw tail checks.

## OPLL custom voice and notation correction

Added opll_target.py and tests/test_opll_target.py. Final merged OPLL output
uses correct YM2413 patch decoding, ROM @0..@14 and user @16+ definitions,
and exact note lengths with ties on splits. Legacy variants remain unchanged
for regression comparisons. Target note CSV records source index and patch.
Custom-voice reference: all 15 definitions and alternating selections match
in normal/raw modes; MGSC 1.11 compiles normal output. No listening check.
Next: user audition; remaining mid-note patch scheduling and source Segment
boundary interpretation are separate from this target-format correction.

## Latest: rhythm notation optimization

Added py/rhythm_notation.py and tests/test_rhythm_notation.py. Final rhythm
output deduplicates absolute volumes safely across loop boundaries and uses
one default length if shorter. Pattern discovery remains Segment-based; no
new loops or macros are inferred from text. Added before/after target dumps
and optimization metrics under --dump-passes. Fixed physical line wrapping
inside long preserved loops after MGSC rejected an overlong line.

Six fixtures in normal/raw modes preserve attacks, volumes and duration.
All 24 isolated before/after rhythm files compile with MGSC 1.11. Sample
normal rhythm text: 1175 -> 633 characters; compiled bytes: 736 -> 449.
Next: extend Segment-based pattern analysis and notation reduction to melody;
macro extraction remains optional. No files staged or committed by the agent.

Full unittest discovery passed all 59 tests after the line-wrapping fix.

## Latest: OPLL octave correction after voice review

Fixed final target notes being one octave too low: MGSDRV octave = MIDI // 12.
Verified block 3 from o4 a versus block 2 from o3 a through MGSC/libkss.
Voice number mapping and custom patch decoding were correct and are unchanged.
Equivalent @16 and @v20 definitions/selectors produce identical user registers.
Generated grider compiles and its opening melody block now matches the source.
Added all-eight-block pitch tests and all-fifteen-ROM-instrument mapping tests.
No files staged or committed. Full audio equivalence remains unproven.

## Relative melody notation and export-tail observation

Final PSG/SCC/OPLL melodic renderers now use >/< for one-octave changes and
)/( for one-volume changes when the previously emitted state is known.
Initial values and larger changes remain absolute. Rest-time source changes
are deferred; relative commands use emitted state, not skipped source state.
Rhythm instrument volumes and Segment/pattern data remain unchanged.

Validation: 63 unittest methods pass. MGSC/libkss checks of absolute versus
relative PSG/OPLL phrases have identical ordered register states. Full grider
has 1934 matching distinct register snapshots after grouping interrupt writes.
PCM and raw VGM bytes are not bit-identical: command processing can change
within-frame write timing. Do not claim sample-exact audio equivalence.

The reference grider MML ends in an infinite repeat without an explicit fade.
Its input VGM has no loop and ends at 121.948390 s, only 19 samples after the
last chip write. A visible WAV fade/release tail may come from export/playback
handling; the screenshot alone cannot establish its origin. No automatic fade
or inferred tail padding was added. Preserve captured data versus target
encoding/export choices as separate concerns.

## Latest: exact melody pattern analysis

Added melody_patterns.py and per-chip pattern/occurrence/marking CSVs under
--dump-passes for PSG, SCC and OPLL. Reuses exact adjacent-repeat search; source
Segments and MML remain unchanged. Added six tests covering state/timing keys,
patch changes, zero-length rows, CSV reconstruction and nonmutation.

Local checks: grider OPLL has 50 repeated occurrences (39 multi-Segment),
PSG/SCC test001 has 202 PSG and 32 SCC repeated occurrences. All compared
state fields and intervals reconstruct from the emitted CSVs. grider final
MML is byte-identical to the pre-analysis output. No private fixture content
was added to tracked files. No staging or commit by the agent.

Next: inspect candidate grouping before implementing state-safe target loops.
Do not apply naive textual loops to relative commands or assume matching
Segment states prove envelope/shared-state equivalence. Macros are optional.

Validation completed: all 69 unittest methods passed.

## Pattern metadata in Segment CSVs

The main --dump-passes pipeline appends segment_index, pattern_id,
occurrence_id, repeat_index, pattern_step, pattern_segments and pattern_repeats
to each chip's existing segments.csv. Original cells and row order are preserved;
in-memory Segments remain unchanged. IDs are local to each chip/channel and
all indices are zero-based. pattern_segments is the unit size; pattern_repeats
is the number of consecutive repetitions in the occurrence. Filter
pattern_repeats > 1 to inspect adjacent repeats alongside pitch/volume/state.
Unmatched singleton candidates still have IDs with pattern_repeats = 1.
OPLL rhythm rows (channels 9..13) have blank melody-pattern columns.
The separate analysis CSVs remain available for definition-level inspection.

Validation: seven melody-pattern tests pass, including original-cell retention,
channel-local indices, zero-length rows, blank rhythm metadata and idempotence.

## Target volume-envelope IDs in Segment CSVs

PSG/SCC rendering appends envelope_id and envelope_kind to segments.csv when
--dump-passes is enabled. IDs are the actual shared MML @e IDs, not separately
allocated analysis IDs. Every positive-length source Segment contributing to
an extracted note receives that note's selection, including merged volume runs.

Kinds: software = extracted @e curve; constant = constant-volume @e0;
inline = tied explicit volume changes using @e0 (including bank-limit fallback);
hardware = PSG hardware envelope, no software ID; rest = no assignment;
zero_length = an event without its own rendered interval, no assignment.
Silent channels retain blank IDs. Pattern columns and all source cells are
preserved. Internal Segments, MML and the existing target_notes CSV are unchanged.
OPLL hardware instrument envelopes are not part of this PSG/SCC software bank.

Eight envelope tests passed, covering merged rows, bank overflow, hardware,
silent channels, zero-length rows, cell preservation and repeatable annotation.
The public PSG/SCC 001 fixture retains identical final MML and existing CSV
cells, including pattern metadata.

## MML loop projection

Final PSG/SCC/OPLL melody renderers now project Segment-derived candidates
through melody_loops.py. No MML string-pattern discovery is performed: candidate
positions and unit lengths come from melody_patterns.analyze. Every iteration
boundary must coincide with a complete rendered note boundary. Candidates that
cut an extracted envelope note are retained as ordinary MML.

Within a candidate, only consecutive units with exactly identical emitted
command sequences are replaced by finite loops, and only when text is shorter.
An initial iteration with different initialization is retained. This preserves
the expanded command stream exactly, including relative octave/volume commands,
envelope selections and tied continuations. Loop counts are split at 255.
No additional state resets, quantization, macros or new note boundaries are
introduced. This conservative first implementation leaves many candidates
uncompressed. Sync annotation can expand loops crossing a synchronization mark.

With --dump-passes, inspect `.melody.before.target.mml`,
`.melody.after.target.mml` and `.melody.loops.csv`. The report references ch,
pattern_id and occurrence_id and gives candidate/looped repetition counts and
an applied/skip status. Existing Segment annotations keep their candidate IDs.
The dump files are per-chip intermediates, before final merge/sync formatting.

Validation includes exact expanded-command equivalence, distinct first entry,
relative changes, envelope/tie boundary rejection, large repeat counts and
unmatched material. In normal mode, grider final MML changes from 32660 to
32438 characters; public PSG/SCC 001 changes from 8330 to 7834 characters.
Both grider versions compile with MGSC 1.11; regenerated VGM has the same
1934 ordered distinct interrupt-grouped register snapshots. This is not a
claim of sample-exact audio or optimal compression. Its padded MGS file size
remains 11264 bytes, so text reduction is not a binary-size guarantee.

Validation update: full discovery ran 77 tests; only the line-by-line sync test
helper failed on multiline loops. It now parses complete prefixes between marks
and checks final duration. All 11 sync tests pass on rerun; five new loop tests
pass. Twelve normal/raw chip projections have identical expanded timelines.

## gra2_005 compression investigation (2026-09-29)

No production conversion changes in this investigation. Baseline compiles;
track 3 is the largest byte consumer. SCC fills the shared 32-envelope bank
before PSG. Complete-note loop experiments preserve expanded commands but
only reduce total used bytes 7859 -> 7404; a few tracks grow in compiled size.
Next design: attack groups -> safe loop boundaries -> envelope extraction ->
global bank allocation -> final loops. Do not force every raw Segment repeat
boundary into an envelope break. See field_notes/2026-09-29_gra2_compression.md.

## User direction: musical structure and long envelopes (2026-09-29)

Use the supplied reference MML and ROM-analysis commentary as an evaluation
oracle for intended musical structure, not merely a source of arbitrary repeated
register patterns. Distinguish percussion gestures, repeated note/rest motifs,
nested phrases, reusable subroutines and outer song loops. Do not paste private
musical content into tracked documentation or hard-code a fixture's phrases.

The reference reuses envelope definitions across different note lengths and
base volumes. Matching entire observed volume-run tuples is too restrictive:
short notes can be observed prefixes of a longer shared envelope. Detect attack
boundaries and preserve envelope restart/continuation semantics before comparing
phrases. A mode-changing percussion gesture must not be absorbed into a volume
curve alone. Reference annotations inform validation; VGM observations remain
primary input. Do not invent an unobserved envelope tail.

The user prefers longer envelopes when the shared bank is limited, for MML size
reduction. Prioritize longer genuinely varying volume trajectories; inspect
saved explicit volume commands and definition/reference overhead as a benefit
check and tie-breaker. A long constant hold alone must not consume a new slot.
Evaluate the shared PSG/SCC candidate bank together, not SCC first. Do not
replace this preference with frequency-only ranking of expanded loop copies.

Next implementation target: recover representative long PSG envelope behavior,
reuse compatible observed prefixes/base-level variants with exact target
semantics, then match note/rest motifs and nested phrases using those envelope
identities. Keep Segment, note/envelope, pattern and occurrence mappings visible.

## SCC driver book review (2026-09-29)

Reviewed the user-provided book photographs; findings and page/photo index are
in [scc_driver_analysis.md](local_only/scc_driver_analysis.md). No converter changes.
Macro playback may truncate or pad with rests according to requested duration.
Gradius2 envelopes have phase-dependent release checks: shared prefixes alone
are insufficient to establish compatible envelopes across note lengths.
This qualifies the prefix-sharing proposal above. Next: validate complete
observed trajectories, release and restart semantics before implementing reuse.
Keep inferred musical structure separate from facts observed in VGM; do not
transcribe or commit the private source photos or musical listings.

## Generic shared envelope selection (2026-09-29)

The main pipeline now collects both PSG/SCC candidates before assigning the
shared 32 slots. Longer varying observed curves rank first, independently of
chip processing order or expanded occurrence frequency. Exact observed prefixes
can reuse a selected definition: every tick, including any release portion,
must agree. No Konami commands, fixture names or inferred envelope tails are
used. Existing Segment envelope IDs identify the actual shared definition.

Gra2_005: 19551 -> 14870 MML characters; MGSC 1.11 used bytes 7859 -> 5286.
All six rendered tracks match Segment pitch/volume/mode/wave state per tick.
Public mixed-envelope fixtures pass in standard and raw modes. This is not
sample-exact audio verification. Envelope extraction boundaries are unchanged.
Further work: gesture-aware percussion grouping and nested note-level phrases;
base-volume normalization and parametric envelope inference remain unimplemented.

## CLI metadata and default artifacts (2026-09-29)

Merged metadata name now defaults to the input stem. --name and --title override
name/title independently; --tile aliases --title. Output filenames remain unchanged.
Normal cleanup now covers all three chip pipelines, including absent chips, whose
empty legacy compress variants previously leaked into the output directory.
Debug and pass-dump modes remain available. No music conversion behavior changed.

## Performed units and nested loops (2026-09-29)

`performed_patterns.py` adds a source-derived performed-unit layer without
changing note boundaries or envelope extraction. PSG/SCC units start from complete
extracted notes/rests. A PSG sounding interval followed by a rest, containing noise,
is conservatively grouped with its trailing rest as a `percussion_candidate`.
Mode, noise period, tone period, volume trajectory and hardware-envelope settings
remain in its constituent signatures. This is an inferred coarse gesture, not a
recovered original drum macro. Uninterrupted or ambiguously separated hits are
not split by a new heuristic. Duration variants are not merged or truncated.

The hierarchy detects exact adjacent repeats of these units, then searches each
repeated phrase for inner repeats. OPLL melody uses its existing complete Segment
notes and patch-aware signatures. Source timing, envelope and patch differences
prevent candidate equality. The greedy search is not an optimal grammar recovery.
There are at most two emitted loop levels and 255 repetitions per loop command.
Only equal emitted command iterations are looped; different initialization stays
outside. Ties and complete envelope notes remain inside one unit. The result
expands to exactly the original commands, including relative state changes.
The smaller textual result of legacy and performed-unit projection is selected
per channel. Text savings do not guarantee smaller compiled bytes per channel.

With `--dump-passes`, `.performed.units.csv` retains constituent Segment indices,
relative signatures and hierarchy paths. `.performed.loops.csv` records channel,
pattern/occurrence/parent IDs, depth, unit range, repeat count and application status.
IDs are local to the channel and this analysis, distinct from raw Segment pattern
IDs. Segment CSVs append `performed_unit_id`, `performed_unit_kind`, and JSON
`performed_loop_path`; existing source, pattern and envelope columns are retained.
Zero-length source rows not contributing to a rendered note have blank unit IDs.
Nested occurrence records describe source occurrences, including copies represented
by one loop body. `legacy_projection_selected` means this hierarchy was not emitted.
Existing before/after target MML dumps show the actual selected projection.

Validation: synthetic nested phrases, differing initialization, counts above 255,
tied notes, release differences, noise/mode trajectories and source-cell preservation.
Gra2_005 expanded commands and all six per-tick state timelines match; MGSC 1.11
compiles it with 4806 used bytes (previous shared-envelope output: 5286).
No book-specific commands, source addresses or fixture-specific phrases are used.
Further work includes continuous-drum onset inference, duration-variant gesture
families, non-adjacent macros and compiled-size-aware selection.

Validation completion: all 84 tests passed. Gra2_005 normal/raw expanded commands
and per-tick states match; grider's six OPLL melody command streams match and
MGSC compiles the final output. Legacy report statuses explicitly indicate when
the performed projection was selected. No staging or commit was performed.

## Cost-aware repeat placement (2026-09-29)

The performed-unit compressor now compares its original greedy hierarchy with
an alternative dynamic-programming placement of non-overlapping repeats. The
alternative considers emitted command length, overlapping starts and shorter
repeat counts, while still requiring identical source-unit signatures and exact
command iterations. Initialization differences can stay outside a repeat.
Both strategies recursively search inner repeats; maximum depth/count limits
remain two/255. The shorter textual projection wins, with greedy winning ties.
The performed loop report records `strategy` (`unit_count` or `text_cost`).
This is a text-cost optimization, not an exact model of MGSDRV compiled size.

Gra2_005 selected output: 12688 -> 12575 characters; MGSC used bytes 4806 -> 4794.
A weighted-only experiment used 4754 bytes but had longer text on some channels;
that experiment is not the production selection policy. Expanded command streams
and per-tick states of the selected output match the source-derived baseline.
No note timing, gesture boundaries, envelope selection or voice mapping changed.
Larger future gains likely require non-adjacent reusable phrases or a validated
compiled-byte cost model; do not claim current selection is byte-optimal.

Cost-placement validation: full suite of 84 tests passed; the added cost-selection
invariant test and all six performed-pattern tests subsequently passed. Gra2_005
normal/raw expanded commands and per-tick states match. MGSC 1.11 compiles the
normal output with 4794 used bytes. Output: outputs/gra2_weighted/gra2_005.mml.

## Non-adjacent macro investigation and gra2_003

See field_notes/2026-09-29_macro_compression.md. Added optional local regression
checks for gra2_003 and gra2_005; both pass expanded-command and per-tick state
comparisons. No automatic macro emission or default sync/allocation change.
Macro experiments reduce text but leave real-fixture compiled sizes unchanged.
Gra2_003 requires 26951 track bytes at default sync spacing (plus 886 definitions).
Keeping only start/end sync experimentally reduces tracks to 21603, still above
15000. Prioritize loop-aware sync placement and measured byte cost over assuming
macros are runtime compression. Generated source also exceeds the local mgsc-js
49152-byte source limit before whitespace/comment compaction.

## Loop-preserving synchronization (2026-09-29)

Shared sync candidates now require top-level token boundaries in every active
track, intersected with existing tie-safe leaf boundaries. Entire loops (including
all iterations and nested loops) and macro calls remain intact. No annotation-time
expansion is performed. Applies to PSG, SCC, OPLL melody and OPLL rhythm through
the common final formatter. min_gap remains a minimum, not a forced interval;
zero selects all safe common boundaries, and start/end remain mandatory.
Ended tracks do not constrain later marks. Physical-line wrapping is unchanged.

Gra2_005 MGSC 1.11 total used bytes: 4794 -> 3848, compilation succeeds.
Gra2_003 isolated track sum: 26951 -> 21603, plus 886 definition bytes. It still
exceeds the 15000 track budget; do not claim the complete song now compiles.
Gra2_003 output text is 46960 characters, below the tested wrapper source limit.
Expanded command and per-tick comparisons remain required alongside loop retention.

## PSG/SCC sound reproduction correction

Main target output now treats hardware-envelope m as a raw register period,
using direct y11/y12 writes for zero. Explicit PSG/SCC tuning plus signed detune
preserves observed tone periods within MGSDRV's -127..127 detune range.
Out-of-range cases warn and are marked in target_notes.csv. See
field_notes/2026-09-29_psg_scc_periods.md for independent MGSC/libkss evidence.
Source Segments and legacy debug renderer baselines remain unchanged. Old
pitch-name-only comparisons were insufficient to verify actual output frequency.
# Pitch roundtrip verifier

Reference-note audit now available in scripts/check_reference_pitch.py.
gra2_002: all 310 pitch changes match on all 8 tracks. gra2_008 two iterations:
1391 reference pitch changes match, one extra PSG ch3 observed change (889,
tick1940, CSV line5320) remains unexplained. Formula for both PSG/SCC is
(reference tuning[note] >> (octave-1)) - signed detune. No extra SCC -1.
Four synthetic parser/projection checks pass. No converter tuning change made.

Added scripts/verify_pitch_roundtrip.py, scripts/mml_to_vgm.mjs and
py/roundtrip_pitch.py. Existing reference Segment CSVs remain untouched.
Six synthetic comparator checks pass. gra2_002 completes full MGSC/libkss
roundtrip but zero-offset comparison has differences; onset timing must be
separated from period errors before diagnosing the tuning formula.
See docs/pitch_roundtrip.md for commands, scope and dependency versions.
User suggests deriving a pitch table from original MML and reference CSV.
gra2_002 and gra2_008 original MML already declare a custom #psg_tune table;
validate that mapping first. Do not force a game-specific table on all VGM.
# Automatic target macros (2026-09-30)

py/mml_macros.py is applied after sync formatting in normal target output.
PSG/SCC/OPLL melody participate, ranked by source-character savings. Rhythm
is excluded pending rhythm-aware shared macro parsing. No sync boundary is
crossed; balanced loops and ties are preserved; no recursive definitions.
Allocation stays based on pre-macro text, since macro calls do not save binary
track bytes. GRA2_08 reallocated fixture shrinks 28600 -> 16600 characters;
expanded tokens/timing match. New tests cover melodic chips, loops and ties.
# OPLL rhythm macro completion (2026-09-30)

GF2SMS03 startup fix: rhythm_mml target projection coalesces identical same-time
HH retriggers when the first interval is zero, with a warning. Source CSVs stay
unchanged. Distinct sub-tick collisions remain errors. Reproduction now generates
MML; eight rhythm renderer tests pass including duration/state discrimination.

tests/test_rhythm_pipeline.py now includes optional local grider, using the same
attack/volume/duration checks as the public fixtures; missing input skips only
the local test. No private fixture is added to version control.

Rhythm now participates in automatic macros in its own grammar pool. Existing
Segment exact-repeat grouping/loop projection remains unchanged. mml_sync parses
macro definitions at call time with the calling track's grammar. Added public
pipeline checks for rhythm_only_test01..03 and sample, plus synthetic rhythm
macro/sync equivalence coverage. Sample emits rhythm macros containing existing
loops. Short fixtures need not produce macros when there is no text benefit.
## Zero-length event discussion recorded

See field_notes/2026-09-30_opll_zero_length_events.md before extending the
GF2SMS03 target workaround. Future normalization should separate final tick
state from trigger history. No broad l=0 merge/refactor was implemented in
this documentation update; hardware/emulator audibility remains unverified.
## Local catalog and batch MGS (2026-10-01)

Batch now prefers native mgsc from PATH, supports --mgsc, and uses positional
input/output arguments. JS fallback remains for environments without native
MGSC. Compilation success also requires nonempty output; failure logs are
printed. This Windows session could not launch WSL (E_ACCESSDENIED), so the
user-requested complete native run remains unverified here.

User outputs/mgs compilation failures included ERR_MODULE_NOT_FOUND for mgsc-js,
before MGSC ran. Batch now preflights module loading/initialization before any
conversion and reports setup separately. msxplay's public UI delegates directly
to MGSC.compile, as does our helper. Do not diagnose these old reports as MML
syntax or buffer errors. Tests cover setup failure and continuing genuine errors.

Validation: 56 requested VGMs convert after the fix. Initial regression run had
55 passes and WBIII12 failure before the mid-song one-sample extension; WBIII12
then passed on rerun. Batch MGSC result: 52 successes, four track-buffer failures
(Alest202, Alest204, Alest208, Alest214), intentionally not repaired. Logs and
reports are in outputs/local_mgs_check/. Batch continuation/stale-output test
and nine rhythm renderer tests pass.

Added 56 optional local conversion regressions and scripts/batch_vgm_to_mgs.py
with an MGSC JS helper; see docs/batch_mgs.md. Buffer failures are reported, not
repaired. WBIII08/12 identical startup rhythm collisions are one VGM sample apart:
target coalescing now also permits gaps up to 1/44100 second within one tick,
with equal state and zero preceding interval. Warn and retain all source CSVs;
do not generalize this to arbitrary sub-tick collisions.
## GD3 automatic titles (2026-10-01)

System now uses English only; System and the single release-date field normalize
full-width ASCII. Track/game/author retain per-field language fallback. User
confirmed Alest202 Object too big disappears with a shorter explicit title;
the 240-byte title-line safeguard does not guarantee the whole MGS fits.

py/gd3.py reads bounded UTF-16LE GD3 v1.00 fields. Main CLI uses metadata only
when --title is absent, with --gd3-language ja/en and per-field fallback.
Automatic titles have syntax sanitization and a conservative 240-byte CP932
budget. MGS text field is variable-length; MGSC physical lines are a separate
constraint. Three unit tests pass and Alest201 Japanese output compiles using
MGSC-js 2.0.0. Explicit titles and event interpretation are unchanged.
## Manual allocation override

vgm2mml.py now accepts --alloc with comma-separated channel=bytes entries.
Only specified tracks override final automatic #alloc; no redistribution or
total-budget clipping. Batch forwards the same value to each conversion.
tests/test_mml_alloc.py checks partial/full replacement and invalid input.


## Latest fix (2026-10-01)

Quantized duplicate rhythm hits no longer stop target MML generation: the
last zero-duration same-instrument hit per tick wins. Source Segments remain
unchanged; --dump-passes adds *.opll.rhythm.collisions.csv. See
docs/opll_rhythm.md for the approximation and retained evidence.
Added all 16 reported fixtures to optional local OPLL conversion regressions.
VGM header loop work remains paused; do not resume it as part of this fix.

Validation: all 16 requested conversions and final rhythm attack/volume comparisons
passed; 25 rhythm tests passed. test_conversion_regression.py could not import
fixture_helpers in this checkout. MGSC compilation/playback was not checked.

Restored the test-only SCC clock helper as tests/vgm_test_support.py so it
does not compete with tests/fixtures in shell completion. Updated its import
and excluded the new collision diagnostic CSV from legacy artifact hashes.


## OPLL continuous notes and source retriggers (2026-10-01)

Target rendering now carries zero-duration onset markers to the next timed
interval, slurs continuous intervals and uses q0 when a following pitch/state
interval must keep key-on. Restore q8 for a genuine note end. MGSC 1.11/libkss
roundtrip showed & alone still reattacked on pitch changes; q0 retained key-on.
Do not merge same-pitch key-off/on source events: the old PASS3 retrigger merge
removed real attacks and has been bypassed in Segment construction.

YsSMS01 source/export/fixed key-on counts for channels 0..4:
110/2507/110, 28/19/27, 158/139/158, 152/167/152, 111/110/111.
The remaining ch1 count is a source onset at tick 5951 with zero duration at
EOF, which has no timed target note. Source pitch modulation still rounds to
MGSDRV note names; this change does not promise sample-exact reproduction.
Use scripts/check_opll_key_edges.py reference.vgm actual.vgm --outdir <dir>
for separate traces, Segment dumps, key_edges.csv and count summary. Counts
alone are not timing equivalence; CSV retains explicit times with no alignment.
Generated checks are under outputs/ys_retrigger_check; no private data is tracked.

Validation: 9 OPLL target tests and 25 rhythm tests pass; MGSC 1.11/libkss
compiled/rendered YsSMS01 successfully. Paired 558 timed onsets; raw tick
offsets range 2..7 across playback, not sample-exact alignment. Regenerate
outputs/ys_retrigger_check/fixed/YsSMS01.mml for user listening.

Alest202 evaluated per isolated track due to 20770-byte compiled track total.
ch0/ch1 attack counts match; ch2/ch3 differ by terminal zero-duration edges;
ch4 count equality hides one extra short retrigger and terminal-edge omission.
See field_notes/2026-10-01_alest202_retrigger_check.md. Conversion code unchanged
during this evaluation; volume-15 recovery versus true key edges remains to inspect.

Pre-fix Alest202 export comparison confirms excessive melodic retriggers:
887/2876/1169/1914/3425 versus source 164/163/398/515/515. Attached MML
compiles with 14834 track bytes, whereas fixed isolated tracks total 20770.
No additional conversion change during comparison; see Alest202 field note.


## Current state: coalescing withdrawn (2026-10-01)

Removed projected same-note coalescing after the user reported missing opening
guitar in Alest202. Keep YsSMS01 slur/q0 retrigger fixes and source key-edge
preservation. The user will compare YsSMS01 with its original VGM. Do not
continue compression experiments now. Existing coalesced artifacts are failed
experimental output and must not be recommended for playback or used as goldens.
Opening guitar loss remains unexplained; raw key counts do not prove sound.

Read-only follow-up reviewed duplicate_write_opl3 and vgm-conv's YM2413-to-OPL
converter. Conditional A/B ordering, optional waits and key-dependent RR mapping
are recorded in field_notes/2026-10-01_opll_key_and_envelope.md. Neither reviewed
path proves forced off/on for repeated key-high writes. No conversion behavior
changed; do not infer that this review resolves the weak-sound report.

Onset audit correction: preserve legacy onset, add independent key_on_edge;
target retriggers and continuation gates now use only observed key edges.
OPLL Segments preserve apparently silent rows instead of folding away keys or
register states. Keyed vol=15 intervals emit v0 notes rather than rests.
No coalescing/compression experiment restored. YsSMS01 roundtrips with the
same attack counts; Alest202 checked per isolated track because full capacity
is still exceeded. See outputs/opll_onset_review and the OPLL field note.
Do not claim that these checks resolve the reported lighter/missing sound.

The user accepts the current changes and reports a substantial retrigger
improvement. End audio investigation here. Relevant checks pass after a small
test-only macro-body API correction in test_mml_sync.py; MGSC/libkss roundtrip
checks are complete. Changes remain uncommitted for the user's review/commit.

Evaluation scope agreed with the user: key-on counts only. No timing,
frequency, volume metrics or combined score. check_opll_key_edges.py now emits
keyon_totals.csv and accepts --pairs for existing reference/exported VGM pairs.
missing_keyon/extra_keyon mean summed per-channel count shortages/excesses;
they are not time-matched event identities. Rhythm attacks are excluded.
Four count tests pass. Checked YsSMS01 current export (559/558, shortage 1)
and Alest202 PREVIOUS msxplay export (1755/10271, excess 8516). Do not label
the latter as the current corrected conversion. Sources/exports are untouched;
the tool does not compile or export MGS. See docs/opll_keyon_counts.md.

## 2026-10-01: declared VGM loop metadata
- Added read-only loop boundary inspection and optional .vgm.loop.csv dumps.
- Source samples and legacy wait-clock time remain separate; no KEYON/reset or MML loop emission.
- Seven synthetic tests cover boundaries, payloads, legacy waits and unchanged traces.
- Segment annotations and MML loop notation remain the next stage.
- User regression completed; loop metadata and compressed input fixes are ready for integration.
- Added gzip-signature input detection shared by trace decoding and GD3. VGM <1.50 / zero data-offset headers start at 0x40. Invalid headers/offsets fail explicitly.
- All 42 PS1FM/FFMSX fixtures now produce OPLL register traces; representative MML conversions succeeded.
- Regression conversion_failed entries are deleted duplicate RType fixtures, per user; do not treat them as decoder failures.

## Integrated batch KEYON regression
- Batch MGS conversion now exports the existing compiled MGS using libkss and compares OPLL melodic key-on counts by default; no second MML conversion or compilation.
- CSV/JSON retain four counts plus separate comparison status/error. Missing dependencies, export caps and failures leave counts blank.
- --skip-keyon-counts restores compile-only operation; --libkss-module selects an explicit playback module.
- grider end-to-end export/count check succeeded. No audio equivalence or optimized allocation is claimed.

## OPLL performed-note loop layer
- Added source-linked note/rest grouping and duration-first repeat candidates. True key edges (including zero-tick ones) still delimit units.
- Equal durations alone never authorize replacement: complete rendered trajectories and command iterations must match. Existing Segment loops remain a fallback.
- Segment CSVs retain unit membership; loop reports and paths retain candidate rejection/selection separately.
- Sample/sx01v compile into fewer bytes; grider has shorter source but larger compiled tracks. Alest202 buffer-full and gra2_001 source-size overflow remain unresolved.
- Expanded melodic commands/times were checked against HEAD renderer for all four OPLL inputs; representative MGSC and MGS-export KEYON checks were run. No chip-specific heuristics or new timing/pitch tolerance.

## Reference-loop validation (three songs only)
- User excluded gra2_001; inspect sample, grider and sx01v only.
- Added a bounded reference-loop window audit with source CSV line links, state sequences and interval dumps. Four parser tests pass. Approximate window mismatches are inspection leads, not failed conversion assertions.
- Ordinary repeated instructions can produce identical source states while some integer tick boundaries differ by one tick. Do not discard pitch/volume/voice differences or relax production equality without a separate decision.
- Existing generated MGS files compiled and were exported back into Segment CSVs. Per-song KEYON shortages are 5/38/11; positive keyed-unit shortages are 1/3/1, all source duration one tick. Counts are inventories, not matched missing-event or acoustic-quality scores.
- Isolated first-state pitch/volume differences remain for detailed trajectory inspection. No conversion behavior was changed for this audit.
- Findings and limitations: field_notes/2026-10-01_reference_loop_validation.md. Local detailed outputs: Codex workspace outputs/reference-loop-audit. Do not commit private fixture data or claim full byte/patch/noise/WAV equivalence.

## Sample reference-loop diagnosis
- Regenerated only public sample with --dump-passes, and checked actual final loops after macro expansion against reference phrases. See field_notes/2026-10-01_sample_loop_diagnosis.md and Codex outputs/sample-loop-diagnosis/reference_loop_verdicts.csv.
- Reference line 22 (9/a) is not recovered as a complete two-iteration loop. Its corresponding 28 note/rest units have identical non-timing positive-state sequences, but 5/13 units differ in duration by one tick. Current duration and timed-trajectory equality fail: a concrete missed loop involving timing, not merely a possibility.
- Reference lines 25-27 (b/c/d) also lack complete loops, despite identical source-unit validation keys. Initialization/octave command differences are the separate obstruction; do not attribute these to jitter.
- Line 20 is partially looped (setup first, remaining three iterations); line 21 and lines 28-30 are fully looped. PSG/rhythm repeated cores are looped at shifted boundaries, without reference last-pass exits.
- No tolerance, new vgmticks field or renderer changes were made. The origin of the one-tick differences (source waits versus floating point/60 Hz quantization) is not established. User asked first to diagnose whether reference loops are recovered; do not broaden to a catalog regression.

## Isolated sample musical-length experiment
- Reference-guided local helper uses tempo120/l16/q6/q7/q2 but derives note/pitch/volume/voice order from native Segments. Not a production change or automatic timing estimator.
- MML6453 ->4341 characters; MGSC total used2963 ->2410 bytes, OPLL melodic used2137 ->972. Fully recovered first-pass reference melodic loops5/12 ->12/12. Initialization layout also improves, so savings are not purely timing relaxation.
- Source snapshots unchanged; compressed normalized commands/times exactly equal uncompressed normalized stream. Maximum boundary shift2.625 source ticks; correction CSV retained.
- MGS export604 KEYONs, same as baseline. With declared1ms intermediate-state inspection threshold and raw time, all604 substantive keyed-note state sequences match. Rhythm instrument/volume sequence282hits and custom-patch byte sequences match. Unfiltered differences retained; no WAV equivalence claimed.
- Playable artifact and helper: Codex outputs/sample-note-length-experiment. Findings: field_notes/2026-10-01_sample_note_length_experiment.md. Do not enable this reference-guided method for other fixtures without a separate request and general timing inference design.

## Shared source timing and sample reference audit (2026-10-02)
- User corrected the intended clock policy: all chips share the VGM stream origin;
  all waits must count. Reader now accumulates integer samples, including formerly
  skipped 0x77/0x7A and DAC waits/overrides, and derives time without chip rebasing.
- `--vgmticks --dump-passes` adds absolute samples and source interval ends to
  trace/pass/Segment CSVs; old CSVs retain unavailable samples as None. Command
  timing evidence is also dumped. No musical normalization was enabled.
- New audit: scripts/compare_reference_vgmticks.py; see docs/vgm_timing.md and
  field_notes/2026-10-02_sample_vgmticks.md. Public sample evidence and compiled
  MML are in Codex outputs/sample-vgmticks/with-source-clock; audit is in comparison.
- OPLL 32 comparable later repetitions: at most 139 samples of raw timing difference,
  stable states agree; four rounded-offset windows differ by at most one 60 Hz tick.
  PSG and rhythm each have eight comparable repetitions with equal state sequences
  but different sample timing. PSG alignment is reference-specific, not a KEYON rule.
- Sample MML is identical with/without evidence flag and compiles with MGSC.
  Public conversion regression and bounded timing/chip/target/rhythm tests passed.
  SCC's old synthetic test origin hack was removed in favor of absolute write times.
- Next permitted work is to review source jitter versus musical normalization policy.
  Do not silently enable normalization, run a broad catalog or overwrite fixtures.

## Shared timing adoption after local regression (2026-10-02)
- User completed PSG/SCC, PSG/OPLL and OPLL batch runs. Reviewed CSV/JSON agree:
  669 reported inputs, 399 MGS successes, 269 Track buffer full failures, one
  missing-input failure. The user deliberately deleted the temporary exported
  YsSMS01.vgm; ignore that case for adoption. Present inputs have no observed
  converter exceptions. No generated outputs were changed during review.
- All 399 compiled inputs completed OPLL melodic KEYON comparison. Count
  differences remain (including large PRIMK/FMPAC shortages); they are not a
  timing-change attribution or proof of specific missing events. Rhythm and
  PSG/SCC notes are outside this metric.
- Recorded totals, evidence paths and limits in
  field_notes/2026-10-02_vgmticks_regression.md. User approved production adoption
  and will commit this record, create a PR and merge into main themselves.
  Do not perform those git actions on their behalf.
- After that merge, the next requested task is musical duration normalization.
  Preserve raw sample evidence and distinguish corrected target timing from
  observed source intervals. Normalization remains disabled at this checkpoint.

## Optional musical normalization implemented (2026-10-02)
- User requested source-inferred correction on sample, then bounded benchmarks
  of sample/grider/sx01v. Added py/note_normalization.py and --normalize-lengths
  to converter and batch CLI. Default conversion is unchanged; no Git commit,
  staging, branch switch or PR was performed.
- Fit a common OPLL onset clock, project notes/gates and rhythm, retime PSG/SCC
  commands without scaling frame envelopes. Native traces/Segments stay intact.
  Unsafe/uncertain projection retains all conventional target parts. grider
  abstains because no sufficiently confident shared clock was found.
- Corrected sample: 6333 ->3544 characters, MGSC used2956 ->1678 bytes,
  source/export KEYON609/609. sx01v:17428 ->11248 characters, used9128 ->7183,
  KEYON1615/1615. grider unchanged25243/13075, KEYON2596/2559.
- Ordered pitch/volume/voice state runs agree for sample/sx01v with explicit
  44-sample intermediate inspection threshold; rhythm instrument/volume counts
  and sequences also agree. No WAV equivalence or general PSG/SCC-only clock
  estimator is claimed. Full evidence and limits in the benchmark field note.
- Artifacts: Codex outputs/length-normalization/{sample,grider,sx01v}/normalized.
  Normalization JSON plus dump-only note/loop CSVs distinguish target correction
  from source samples. Exact loop expansion and effective setter-state equality
  are checked before writing target files. Sample CLI native CSV identity and
  default public conversion regression passed.
- Bounded verification finished: 39 tests passed across normalization, rhythm
  rendering/notation, batch and public conversion suites; git diff --check clean.
  Saved native Segment CSVs match byte-for-byte across all three benchmark cases.
- Next: user listening and opt-in regression; do not auto-enable correction,
  copy reference tempos, run a broad catalog or overwrite fixture evidence.

## User-run normalization regression reviewed (2026-10-02)
- Recorded completed PSG+OPLL (26) and OPLL (565) runs in
  field_notes/2026-10-02_normalize_lengths_regression.md. CSV/JSON agree;
  per-input correction reports were reviewed. PSG/SCC-only interrupted run is
  not needed for this comparison and receives no correction with current inference.
- Correction applied to 3/26 and 101/565 inputs. Current compilation: 346 success,
  243 buffer_error, 2 compile_failed; no current conversion exceptions.
- Compare shared input paths: five OPLL buffer errors resolved (Alest208/211,
  FRAY06/11, ILCITY23), but XEVIFS07/08 newly fail Invalid length on r%1 at
  inferred tempo149. OPLL catalog adds22 F1SPRT3D paths and removes2 temp exports;
  do not attribute raw success-total growth to correction. PSG+OPLL statuses unchanged.
- All five buffer-resolved cases are among26 applied songs whose MGS export
  reaches its duration cap. Compilation success is not completed fidelity checking.
  Paired completed OPLL set285: shortage1941->1848, excess32->32;12 inputs
  improve,273 unchanged,none worsen. Incomplete cases are outside that comparison.
- Pending: minimum-length regression and export-duration/termination investigation,
  then per-note semantic correction policy and larger phrase/last-pass-exit loops.
  The95% heuristic is provisional; user questioned it and favors semantic bounds.
- User will commit/push codex/normalize-lengths. This review only writes records;
  no code fixes, staging, commit/push, catalog rerun or fixture changes performed.

## Title-grouped MGS collection utility
- Usage documented in docs/collect_mgs.md on 2026-10-03: preview/copy/overwrite,
  title-folder mapping and collision handling. README intentionally unchanged.
- Added scripts/collect_mgs.py for user-requested MSX player folder layout:
  <title>/<track>.vgm/<track>.mgs -> <outdir>/<title>/<track>.mgs, also .vgz.
  Other layouts use the immediate parent. File names and contents are preserved.
- Supports --dry-run and explicit --overwrite; identical outputs skip. Duplicate
  destinations are checked before copying. Conversion/compilation is not rerun.
- User clarified this is a personal listening utility, not a primary project
  output feature: removed its usage from README. The project output remains MML;
  MGS compilation/playback serves verification. No user output tree was populated
  automatically.

## Bounded authored-loop inventory
- User requested OPLL reference-loop statistics plus phrase lengths, with the
  same method available for a later PSG/SCC comparison. Added
  scripts/audit_mml_loops.py and six focused tests; uses bounded reference parser.
- OPLL subtree currently has only grider/sx01v MML: 55 source loop definitions,
  69 channel-expanded definitions, 49 finite,6 infinite,23 last-pass exits,
  6 enclosing nested loops,max depth2. Grider's song loop encloses rhythm loops.
- Phrase steps range12..7872 with 48=quarter; 2/4/8-whole-note phrases coexist
  with short repeats. Separate ordinary/common/final/expanded lengths retained.
  Field note: field_notes/2026-10-02_opll_reference_loop_statistics.md.
- CSV/JSON outputs in Codex outputs/mml-loop-statistics/opll. No fixture edits,
  conversion reruns, PSG/SCC survey, staging or commit actions. Unknown syntax
  is reported as unsupported; macro calls/loop-internal portamento aren't yet
  supported by the length audit. Next may be PSG/SCC survey with scope controls
  or loop recovery comparison; source statistics alone do not prove recovery.

## User-run PSG/SCC loop inventory reviewed
- Scope corrected on 2026-10-03 following user confirmation: only seventeen
  original msxplay gra2 scores are valid; exclude with_sync_mark split/marked
  variants and all VGM-derived NEMESIS2 conversion outputs. Added audit
  --exclude-dir option. Scoped reports in Codex outputs/mml-loop-statistics/
  psg_scc-original:17 found,3 parsed(002/008/017),14 unsupported;36 definitions,
  30 finite,6 infinite,0 observed exits,5 with children,max depth2. Full coverage
  requires macro/control parser support; prior mixed totals below are historical.
  Field note updated; no conversion, compilation, fixture or Git mutations.
- Recorded results and interpretation in
  field_notes/2026-10-02_psg_scc_loop_statistics.md. User's run found189 files,
  parsed115,unsupported74;4253 definitions,4235 finite,18 infinite,0 exits,
  15 enclosing-child loops,max depth2. No re-audit or parser change was made.
- Major scope bias: msxplay/gra2 has95 parsed files but89 have no loops; six
  loop-bearing files are three versions each of002/008 (108 definitions).
  NEMESIS2 has20 parsed files,16 zero-loop; remaining files supply4145 definitions
  (97.5% of total), with converter-style headers and tiny loops. Do not equate
  that mixture with the authored OPLL two-score reference population.
- All74 unsupported in msxplay:46 macro-call rejections,28 unsupported lexer
  syntax (including h with multiple arguments). Fourteen of17 original gra2
  scores aren't parsed. Zero | counts do not establish that PSG/SCC lacks exits.
- 3800/4253 bodies have<=3 score steps. Raw steps across tempo75/225 aren't
  physical-duration comparisons. Next: improve audit coverage and select one
  original reference per song before drawing chip-group structure conclusions.

## GD3 title display correction (2026-10-03)
- Final merged MML now uses CP932 (Shift-JIS) for native MGSC/MSX Japanese titles;
  unrepresentable characters become ?. Intermediate CSV encoding is unchanged.
- GD3 system prefix is separated from the following text by one space, including
  missing game/date cases. Existing game/date parentheses and explicit title
  override semantics remain unchanged. JS compile/export helpers accept UTF-8
  and CP932 input. README and focused GD3 tests updated.

## Short-first hierarchical loop experiment (2026-10-03)
- Added pure experimental py/hierarchical_loops.py and isolated
  scripts/experiment_hierarchical_loops.py; no production converter integration.
- Compared immediate vs retained candidates on normalized sample/sx01v OPLL
  note units, original-unit widths<=128, depth<=3; exact trajectory/command
  expansion asserted. Five tests pass. Private artifacts in Codex outputs/
  hierarchical-loops; field_notes/2026-10-03_hierarchical_loop_experiment.md
  documents metrics, source reference statistics, and limits.
- sample no improvement; sx01v retained saves36 body chars vs existing;
  immediate worsens244. Not full MML/MGS size metrics. No new audio roundtrip.
- Harness currently observes target-stage notes after envelope decisions, not
  yet pre-envelope structural extraction. No individual reference-window recovery
  certification. Next inspect missed reference intervals and last-pass exits/
  effective state equality; preserve source data and default output behavior.

## OPLL loop strategy comparison (2026-10-03)
- User narrowed discussion to loops and deferred envelope ordering. Use exactly
  sample and sx01v. Prior rejected count-only/gra2_005 report and output tree
  were deleted. No conclusions from that comparison should be reused.
- New source_loop_plan creates an executable structure before target command
  generation; original-unit widths<=128, depth<=3. Both immediate short-first
  and retained-candidate trees drive emitted MML with exact expansion checks.
  Default converter unchanged; explicit optional renderer arguments only.
- scripts/experiment_opll_loop_strategies.py compares current/immediate/retained
  with all PSG/SCC/envelope/rhythm/macro settings unchanged, normalization off.
  All six outputs compiled with MGSC1.11; expanded final timed tokens agree.
- sample text6333/6008/6333 bytes, MGSC used2956/2956/2956. sx01v text
  17428/17518/17187, MGSC used9128/9428/9168. Thus text savings alone do not
  justify production adoption. Private outputs/logs are in Codex outputs/
  opll-loop-strategies; field_notes/2026-10-03_opll_loop_strategies.md records
  methods and bounds. No audio roundtrip or source-reference loop recall claim.
- Envelope-order experimental helpers remain available but are deferred; current
  work and recommended comparisons use the OPLL-only script above. Do not silently
  substitute fixtures. Next may examine missed reference phrases or binary-cost
  loop selection if requested. No staging/commit/push performed.

## Reversible OPLL structure update (2026-10-03)

- User corrected the objective: final MML characters plus successful compilation/no buffer_error. The earlier binary-size adoption criterion above is superseded.
- Added loop_structure.py with exhaustive exact adjacent-repeat candidate catalog, reversible nested tree and alternative intervals. Source width/depth bounds removed; target counts split at 255. Explicit structural experiment only; default converter unchanged.
- sample current/structural: 6333/6333 characters; sx01v: 17428/17187. All four MGSC compilations succeed, no buffer errors, final expanded timed commands identical. No further size improvement beyond prior retained strategy on these fixtures.
- Six structural tests, four source-plan tests and five hierarchical tests pass. Candidate/tree CSVs and full artifacts are in Codex outputs/opll-loop-structure. See field_notes/2026-10-03_reversible_loop_structure.md.
- Macro-aware selective unrolling remains the separate next phase. No staging, commit or push.

- Additional final sx01v syntax inventory: physical loops 73->91, nested loops 4->17, depth 2->3; both outputs already use 32 macros (no bracket loops inside definitions). Recorded per-track counts and structure-aware macro plan in the reversible-loop field note. Next first improve macro search with loops fixed, then compare selective expansion; exact token preservation and MGSC success gate final character ranking.

## Structure-aware macro allocation (2026-10-03)
- Added structured_macros.py and optional --enhance-macros in converter/batch. Searches loop interiors, expands existing generated calls for reselection, compares four bounded allocations with baseline, asserts exact timed-token equality. Loops stay intact; inner-loop expansion remains next phase.
- Structural sample 6333->4913 chars; sx01v 17187->14938. Both compile with MGSC1.11 without buffer errors. Public sample CLI path also compiles. No whole-catalog regression or audio roundtrip.
- Candidate/selection dumps use target-tree paths at each allocation step, not Segment IDs. docs/structured_macros.md and field_notes/2026-10-03_structured_macro_experiment.md document policies/results. No staging/commit/push.

## Five-fixture macro follow-up (2026-10-03)
- es59/es56/Alest202/FRAY02/SORCER02 source characters reduce 21.4/11.7/18.0/20.0/1.5%; all exact baseline timed streams agree, but all still fail compilation (track buffers or mgsc-js 49152-byte source cap). Unchanged alloc, conventional timing, default loop renderer.
- Fixed long enhanced macro definition physical lines: wrap at 120; es59 Undefined Macro disappears, reveals Track buffer full. Five focused tests pass. Artifacts/logs in Codex outputs/structured-macro-followup; field_notes/2026-10-03_structured_macro_followup.md records methods and limitations.
- Restored es59/es56 source MML: 3061/3535 chars, 44/50 physical loops, depth2/3, both compile. Their 9-channel OPLL mode0 source exposes a pre-existing six-melody target limitation: active Segment channels6..8 omitted. Do not claim source fidelity from baseline equality. Not fixed in this compression follow-up.

## Defaults, OPLL mode and title investigation (2026-10-03)
- Structural OPLL loops/enhanced macros now default; --legacy-loops/--legacy-macros restore earlier compression in converter and batch. Normalization remains opt-in, now handles nine melodic tracks and selected structural policy. Retained scripts updated to force their requested loop/macro strategies.
- Mode0 projects nine channels, mode1 six plus rhythm. es59/es56 startup-only enable followed by disable is recognized. High-channel voice IDs/diagnostics/macros/normalization included. Synthetic nine-channel VGM compiles; real es59 now has f/g/h, 50150 chars and still exceeds JS input cap.
- sample default4913/legacy6333 chars both compile with exact timed-token equality. Ancestor overlap selection check optimized; full es59 reconstruction unchanged (~204s search). Large batch tests may require --timeout above300.
- All seven reported bad stored titles are UTF-8; four good newer binaries are CP932. Current GD3/CP932 title-only probes for all11 sources compile and byte-match. No gd3 algorithm change needed; regenerate old outputs. Report and test scope in field_notes/2026-10-03_default_compression_opll_mode_titles.md. User will run full regression. No staging/commit/push.

## PSG/SCC structural loops before envelopes (2026-10-03)
- Default shared bank now uses structural SourceLoopPlans before envelope-ID
  selection; --legacy-loops restores earlier PSG/SCC behavior too. No reference
  envelope lengths/phrase thresholds, invented attacks or source timing changes.
  Macro selection remains independent. Source plans drive actual target output.
- Added/retained source/Segment mappings, complete candidates/tree/projection,
  expanded/stored envelope counts and performed-unit/path annotations. Removed
  unused legacy Segment search when rendering an existing source plan. Updated
  the envelope-order harness to isolate PSG/SCC while keeping OPLL fixed.
- 0012795->2511 chars,0021793->1822; both compile. GRA2_0318206->18213, still
  Track buffer full ch3. contrail61402->58953, still exceeds JS source cap.
  Native tick-state comparisons pass in all paired cases; mixed OPLL timed
  commands unchanged. p52_arbl diagnostic179772 chars with --legacy-macros
  matches Segment tick states; full enhanced-macro paired test remains undone.
- Restored p52/contrail authored scores compile. contrail initially was saved
  GitHub HTML; extracted embedded MML into private outputs without changing the
  user file. Both references exceed the current score-length audit grammar;
  syntax statistics/limitations are recorded, not claimed loop-window recovery.
- Seven structural-bank tests, ten envelope tests, twelve sync tests, public
  conversion regression and four source-plan tests pass. Field note:
  field_notes/2026-10-03_psg_scc_pre_envelope_structure.md. Private outputs in
  Codex outputs/psg-scc-structure. No full local regression or Git staging,
  commit/push. Do not rerun expensive whole-catalog tests without user request.

## Authored gra2 PSG/SCC follow-up (2026-10-03)
- Compared gra2_002/gra2_005 and six available gra2_001 split VGMs exported
  through msxplay.com. Enhanced macros are ON in both; only the PSG/SCC
  envelope-first versus source-loop-first bank differs. Normalization is OFF.
- Final source totals62001->61332 chars (-1.08%); gra2_0058749->8313 (-4.98%,
  including fewer sync comments; code-only7578->7424). Five inputs shrink,
  two unchanged, one grows41 chars. All16 compile via MGSC1.11/mgsc-js;
  native Segment fields and effective per-tick target states agree in all pairs.
- Source trees reach depth3 in some split inputs; final bracket depth remains
  at most2. Counts include macro continuation lines. More source markers do not
  guarantee fewer final characters after stateful projection/macro selection.
- Corrected split inventory after user clarification/regeneration: the earlier
  98 MMLs were v2 fine-grained outputs, whereas six gra2_001 VGMs correspond
  to original loop-boundary splits. Current six MML/VGM pairs have boundaries
  0,886,2166,3126,5046,6966,8526; no missing/extra numbered files. Previous size
  benchmark consumed unchanged VGMs, so its measurements remain valid.
- All ten multi-block songs have35 complete MML/VGM pairs; all MML block
  comments match recomputed shared loop boundaries. Eight have shell wrappers;
  007/011 lack local wrapper/splitter copies but their existing intervals also
  agree with the001 splitter. VGM headers/durations pass coarse checks. Private
  sync-pairs.csv/json inventory is in the same Codex output directory. This is
  a read-only inventory, not a35-block conversion/roundtrip benchmark. Use the
  loop-boundary files rather than v2 splits for authored-loop recovery checks.
- Results/bounds: field_notes/2026-10-03_gra2_msxplay_structure_comparison.md;
  private artifacts: Codex outputs/gra2-source-structure/comparison.csv/json.
  No source/fixture changes, staging/commit/push. Full17-song regression,
  unsplit001 and p52 enhanced-macro pair remain untested. Keep msxplay-derived
  authored references separate from vgmrips/NEMESIS2 captures in comparisons.

## All35 authored-loop block comparisons (2026-10-03)
- User clarified that file correspondence alone was insufficient. Completed35
  earlier/current conversion pairs with enhanced macros held ON, normalization
  OFF, changing only PSG/SCC envelope-first versus source-loop-first projection.
  Six001 pairs reused;29 pairs added. Production conversion code unchanged.
- All70 conversions succeed; native Segment fields and effective tick states
  agree across every pair and with each rendered output. MGSC1.11/mgsc-js
  compiles34/35 in each variant;016 block03 retains track1 buffer full in both.
- Total characters246524->245186 (-0.54%); code-only218404->217724 (-0.31%).
  23 blocks shrink,2 unchanged,10 grow. Best004 block01 -8.35%; worst007 block02
  +6.26%. Final physical loops758->789; selected source trees reach depth4,
  final target brackets remain depth2. Source structure does not guarantee
  minimum final characters or recover all reference parent loops.
- Reference347 channel definitions produce477 invocation windows. Explicit
  first-audible-note mapping uses offsets3/4 and +/-1 tick window tolerance.
  Approximate catalog full/partial225/343, selected179/271; final old32/183,
  new33/202. Do not claim these geometric counts as exact semantic recall.
  One-note/multi-note/nested-parent categories are separately recorded.
- Inspected004 block01 track5: reference nested parent is selected in source
  tree but projected as expanded_different_commands; initialization changes
  inner repeat count3 on first pass versus4 later. This identifies a target
  projection improvement area without changing current sound/state behavior.
- Full report: field_notes/2026-10-03_gra2_loop_block_benchmark.md. Private
  all-blocks-comparison and loop-recovery CSV/JSON are under Codex outputs/
  gra2-source-structure. No35-block audio roundtrip, staging, commit or push.
  Next output direction named by user: mml2vgm MML, then other FM chips; finish
  discussing this benchmark before assuming new implementation scope.

## Six-level loop request (2026-10-03)
- Raised the legacy performed-unit compressor default max_depth from2 to6;
  explicit depth overrides still work. The default structural source builder
  and target projector were already uncapped. The35-block final depth2 was
  an observation, not their configuration. Do not infer a cap from that metric.
- Added six-level detection/projection and legacy-depth regression checks;
  expanded commands are exact. Synthetic structural/performed6 MML both
  compile through MGSC1.11/mgsc-js (63 used bytes). Local source hierarchy and
  projection CSVs/MML/MGS are in Codex outputs/six-level-loops.
- Confirmed default PSG/SCC order: source structure, software-envelope
  selection, target projection, macros. No envelope-order behavior changed.
- This small depth change does not fix differing-initialization parent-loop
  rejection or rerun the35 private blocks. Staging/commit/push remain user work.

## Unrestricted legacy loop depth (2026-10-03)
- User clarified that default depth caps would distort algorithm evaluation.
  Supersedes the preceding2->6 setting: performed_patterns now defaults to
  max_depth=None. Experimental immediate/retained strategies, SourceLoopPlan's
  experimental branches and comparison wrappers also default to no depth cap.
  Explicit limits remain available for deliberately bounded experiments only.
- Seven-level legacy/experimental regressions check exact expanded commands;
  existing structural depth and envelope-order checks remain applicable.
  Source tree recursion terminates on strictly shorter repeated bodies, without
  an arbitrary depth cutoff. No timing/envelope/macro behavior was rewritten.
- All42 focused tests pass (performed/hierarchical/source plans, structural
  loops, pre-envelope order and OPLL target). Inspected seven-level legacy
  hierarchy CSV and generated MML in Codex outputs/unrestricted-loop-depth;
  all382 expanded commands are unchanged. diff --check also passes.
- Earlier35-block results retain their original conditions. No rerun or new
  compiler/playback claim beyond the preceding six-level compilation check.

## gra2_005 depth-removal Segment check (2026-10-03)
- At user request, compared legacy depth2/depth6/unrestricted and current
  default structural output, with enhanced macros and source-sample dumps ON,
  normalization OFF. No conversion code or fixture inputs changed for this check.
- PSG5029/SCC10369 native Segment rows agree in all four variants; all14
  trace/pass CSVs are byte-identical. Every final per-tick effective state agrees
  with its own Segments and with the other outputs. PSG/SCC before/after loop
  projection also preserves every expanded timed command.
- Legacy outputs are byte-identical at8749 characters and applied depth2;
  changed compressor was exercised six times per run. Default8313-character
  MML matches the previous benchmark byte-for-byte and bypasses that compressor.
  All four compile with MGSC1.11/mgsc-js, no buffer errors.
- Recorded in field_notes/2026-10-03_gra2_005_unrestricted_depth_validation.md.
  Local artifacts are Codex outputs/gra2-unrestricted-depth. No audio roundtrip
  claim; this short fixture does not exercise deeper-than-two legacy repeats.

## OPLL continuous-note child-loop recovery (2026-10-03)
- Implemented only in the separate test checkout at
  I:/wsl/repositories/emef2247/test/msx_vgm2mml. The original checkout and its
  active regression were left unchanged; do not copy back or stage automatically.
- Added opll_inner_loops.py: retain outer note/phrase plans and source-linked
  child Segment plans, then project unchanged target controls through both.
  Keep parent-only spelling as an alternative and assert exact expansion.
  Native key edges, notes, timing, patches, PSG/SCC and envelope order unchanged.
- --dump-passes adds child pattern/occurrence paths directly to OPLL Segment
  rows, plus per-channel child marker/candidate CSVs. Source IDs and ranges
  remain available separately from whether the child is emitted.
- FFMSX01 default MML shrinks49922->7944 characters, compiles through MGSC1.11
  JS with ordinary15000 track allocations, and uses5999 total bytes. All8735
  OPLL/4647 PSG native rows,14 trace/pass dumps and expanded timed final commands
  are preserved. Legacy loops/enhanced macros remain7659 characters/5426 bytes;
  the repair recovers capacity, not global minimum size.
- sample4913, grider24721 and gra2_0058313 characters are unchanged; sx01v
  grows15024->15048 (one child loop,4 additional compiled bytes). All eight
  paired conversions compile; Segments, passes and expanded commands match.
- Results and limits: field_notes/2026-10-03_opll_inner_loop_validation.md.
  All55 focused tests pass, including public conversion, sync and macros;
  git diff --check passes.
  Wider catalog regression/listening is next; no native WSL or audio roundtrip
  claim. Final macro-aware global alternative selection remains future work.
# Current handoff

## 2026-10-04: completed PR55 catalog regression audit

- Current result files are in this test checkout under outputs/mgs/hierarchical_loop;
  the original checkout is independently used for OPM work. User corrected the
  regression label from PR56 to PR55.
- Saved field_notes/2026-10-04_hierarchical_loop_regression.md and the detailed
  report/CSV audit at outputs/mgs/hierarchical_loop/comparison_20261004/.
- Current 689 inputs: 417 success, 208 buffer_error, 63 conversion timeouts
  (all retained logs report 300 seconds), one macro-related compiler failure.
- Previous OPLL partial comparison: 5 recovered successes including FFMSX01,
  one lost success; common-success MML characters decreased 4.98% and MGS
  file bytes decreased 5.20%. Previous OPLL recorded only 126 input paths.
- Old baseline has six compile successes now reporting buffer_error. Current
  PRIMK15 has a macro-definition compiler diagnostic. These remain unresolved;
  source text size and compiled per-track capacity must be evaluated separately.
- Old/current matched OPLL KeyOn comparisons (301): missing 1,975 -> 1,089,
  extra 32 unchanged. Previous/current 91 matched comparisons are unchanged.
- Audited retained results/logs only; no converter changes, fixture edits,
  conversions, compiles, audio comparisons, staging or commits were performed.
- Next work requires user direction: investigate lost compile successes/macro
  diagnostic or rerun timeout cases with a longer limit. Do not report timeout
  inputs as capacity recoveries or alter the independent OPM checkout.

Date: 2026-09-28
Status: ready to resume

## Last completed
- Added target-stage PSG/SCC rest cleanup and software-envelope extraction in
  py/mml_envelopes.py. Source Segments are unchanged; target_notes CSV and target
  MML are retained with --dump-passes. Shared envelope bank is limited to 32.
- Removed silent tracks from final body, allocation and sync-point calculation.
- Checked both supplied envelope fixtures in standard/raw modes and gra2_003:
  rendered pitch/volume/mode/wave state matches Segment intervals tick by tick.
- Full suite of 29 tests passed, then all six envelope tests passed after adding
  hardware-envelope/retrigger and definition-limit fallback coverage.
- Corrected SCC to five channels, one enable bit per channel, and shared
  waveform updates for channels 4/5 (MML 7/8).
- SCC PASS1 now describes post-write state until the next event; PASS2 does
  not move waveform-setup time into later notes. Repeat compression preserves
  duration and only groups identical adjacent states; waveform/volume/octave
  changes are applied immediately by the MGS renderer.
- Merged #alloc now distributes 15000 proportionally to emitted track-text
  size (excluding whitespace, track IDs and comments). Silent tracks get no
  allocation; their MML is retained pending a later cleanup step.
- gra2_002 raw SCC tracks 4..8 each total 356 ticks, matching trace intervals.
- Public conversion checks now use trace-state timing/pitch/volume assertions
  for SCC rather than old hashes that encoded the corrected bugs.
- Added --sync-min-gap (default 1000 target-MML steps, 0 for all shared points).
  Select the first shared boundary at least that far from the previous marker;
  start and final end are always retained. No note splitting or retiming.
- Fixed blank-line accumulation when sync annotation extracts track bodies:
  final header now keeps at most one blank separator. Regenerated outputs/check/giselle.mml;
  all nonblank lines (including music and sync comments) match the previous output.
- Added shared step comments to final merged MML via py/mml_sync.py. Common
  boundaries are calculated across all still-playing channels in target MML time.
- Preserved expanded note/command timelines; loops crossing a marker are expanded
  only as needed. Event/PASS/Segment generation remains unchanged.
- Verified all 20 existing/current unittest methods (including 134 conversion
  scenarios), then all 10 sync tests after adding a two-mode mixed-VGM CLI test.
- Verified all 12 mixed public VGMs in standard and raw modes (24 conversions).
- Documented sync semantics and time units in docs/mml_sync.md.
- Refactored PSG/SCC into event CSV -> analysis -> immutable chip-specific Segment -> MML.
- Added py/psg.py, py/scc.py and py/chip_segments.py; renderers consume named fields.
- Retained PASS0-3 and added Segment/waveform CSVs. --dump-passes now keeps input event CSVs.
- Initial 134-case comparison preserved an existing SCC-header bug. Corrected
  the clock offset from 0xCC (ES5503) to 0x9C (K051649), added header-boundary
  checking and clock-flag masking. Regression expectations now come from the
  old non-Segment converter plus only that header fix.
- Verified SCC note output from an unmodified public VGM; header tests added.
- Header correction validation: all 11 unittest methods passed, including 134
  conversion scenarios against the header-corrected pre-refactor reference.
- Inspected PSG zero-length/envelope fields and SCC waveform/Segment CSVs.
- Documented the architecture and preserved legacy heuristics in docs/psg_scc_segments.md.

## Unfinished
- No required implementation remains for automatic shared sync comments.
- Completed rest-only track removal, deferred rest-time controls, and explicit
  volume-hold envelope definitions. Fitting compact linear ramps (= syntax) is
  not implemented; supplied references therefore differ in envelope spelling.
- Supplied envelope reference lengths differ from VGM-derived timing by 3 ticks
  for 001 and 2 ticks for 002; do not claim exact reference-file equality.
- gra2_002 is not yet an exact match to the hand-authored reference: initial
  timing, PSG behavior and envelope representation remain distinct. Allocation
  weights are textual estimates, not measurements from an MML compiler.
- Hardware playback and WSL execution have not been checked.
- Changes are local and uncommitted; existing user-generated/untracked data was left intact.

## Next allowed action
- Review the local diff and run `python -m unittest discover -s tests -v`.
- Treat any changes to timing, waveform reconstruction or note-boundary heuristics as separate work.

## Do not do next
- Do not discard event/PASS evidence or replace chip-specific fields with OPLL defaults.
- Do not mistake 0xCC for SCC or infer valid conversion from old-output equality alone.
- Do not overwrite private fixtures or regenerate regression hashes to hide a mismatch.

## OPLL rhythm inspection update (2026-09-28)

Added native `.opll.segments.csv` output before target voice assignment,
including rhythm channels. Preserved legacy dumps and MML behavior. Added
optional reference parity tests for traces, PASS1-4 and rhythm Segment fields,
and synthetic edge-expansion tests. Private reference data remains untracked.
Next: assess remaining edge cases through the complete pipeline, then agree
on a common rhythm schema before implementing rhythm MML output. Do not
interpret source rhythm flags as independent triggers; use keyon and channel.

Validation: all 37 unittest methods passed (including 134 conversion cases
and all three optional rhythm references). CLI sample Segment CSV contains
282 rhythm rows; merged sample MML is byte-identical to the pre-change output.

## Rhythm grouping update

Added rhythm_patterns.py and group/definition/occurrence CSVs under --dump-passes.
Preserves native Segment data and MML output. Exact adjacent repeats only;
no timing tolerance or common OPNA schema yet. Tests reconstruct timing and
hit states from exported patterns and check every source reference, duplicates,
volume/pitch distinctions, initial silence and the unknown final gap.
Next: review sample patterns before implementing MGSDRV rhythm rendering.

Validation: all 42 unittest methods passed, including the existing 134-case
conversion regression. Sample: 282 input hits, 213 groups, 18 definitions and
71 occurrences; expanded pattern data matches groups and source references.
The sample merged MML remains byte-identical to the previous output.

## Timing field note

Recorded the external oplldrv/libkss timing evidence and sample recalculation
in field_notes/2026-09-28_mgsdrv_libkss_timing.md, linked from project knowledge.
This is documentation only: do not globally replace the existing 60 Hz clock.
Future timing profiles must separate VGM samples, playback frames and MML steps.

## Rhythm MML output update

Implemented rhythm_mml.py, OPLL target projection selection, rhythm-aware sync
and allocation, and five semantic tests. Exact loops and absolute per-drum
levels preserve group onsets/volumes. Legacy melodic variants remain unchanged.
All 47 tests passed. Six fixtures in both modes match grouped rhythm events.
All eight isolated rhythm outputs compile with MGSC 1.11 / mgsc-js 2.0.0;
full sample normal/raw and sx01v raw compile. Other full outputs hit source
length or melodic track buffer limits. No listening test performed.
Next: user playback review; overall melodic size/allocation tuning remains
separate. Do not apply a global 59.94 Hz correction or collapse duplicate hits.

Rhythm tail correction: target end includes the latest OPLL trace tick as
well as Segment ends. Attack-only rhythm Segments omit the final key-off;
using their ends alone truncated the last cymbal in rhythm_only_test02.
The fixture now ends at tick 77 rather than 41, retaining its tick-40 attack.
This does not reconstruct unlogged trailing VGM waits or acoustic decay.
Seven rhythm renderer tests pass, including normal/raw tail checks.

## OPLL custom voice and notation correction

Added opll_target.py and tests/test_opll_target.py. Final merged OPLL output
uses correct YM2413 patch decoding, ROM @0..@14 and user @16+ definitions,
and exact note lengths with ties on splits. Legacy variants remain unchanged
for regression comparisons. Target note CSV records source index and patch.
Custom-voice reference: all 15 definitions and alternating selections match
in normal/raw modes; MGSC 1.11 compiles normal output. No listening check.
Next: user audition; remaining mid-note patch scheduling and source Segment
boundary interpretation are separate from this target-format correction.

## Latest: rhythm notation optimization

Added py/rhythm_notation.py and tests/test_rhythm_notation.py. Final rhythm
output deduplicates absolute volumes safely across loop boundaries and uses
one default length if shorter. Pattern discovery remains Segment-based; no
new loops or macros are inferred from text. Added before/after target dumps
and optimization metrics under --dump-passes. Fixed physical line wrapping
inside long preserved loops after MGSC rejected an overlong line.

Six fixtures in normal/raw modes preserve attacks, volumes and duration.
All 24 isolated before/after rhythm files compile with MGSC 1.11. Sample
normal rhythm text: 1175 -> 633 characters; compiled bytes: 736 -> 449.
Next: extend Segment-based pattern analysis and notation reduction to melody;
macro extraction remains optional. No files staged or committed by the agent.

Full unittest discovery passed all 59 tests after the line-wrapping fix.

## Latest: OPLL octave correction after voice review

Fixed final target notes being one octave too low: MGSDRV octave = MIDI // 12.
Verified block 3 from o4 a versus block 2 from o3 a through MGSC/libkss.
Voice number mapping and custom patch decoding were correct and are unchanged.
Equivalent @16 and @v20 definitions/selectors produce identical user registers.
Generated grider compiles and its opening melody block now matches the source.
Added all-eight-block pitch tests and all-fifteen-ROM-instrument mapping tests.
No files staged or committed. Full audio equivalence remains unproven.

## Relative melody notation and export-tail observation

Final PSG/SCC/OPLL melodic renderers now use >/< for one-octave changes and
)/( for one-volume changes when the previously emitted state is known.
Initial values and larger changes remain absolute. Rest-time source changes
are deferred; relative commands use emitted state, not skipped source state.
Rhythm instrument volumes and Segment/pattern data remain unchanged.

Validation: 63 unittest methods pass. MGSC/libkss checks of absolute versus
relative PSG/OPLL phrases have identical ordered register states. Full grider
has 1934 matching distinct register snapshots after grouping interrupt writes.
PCM and raw VGM bytes are not bit-identical: command processing can change
within-frame write timing. Do not claim sample-exact audio equivalence.

The reference grider MML ends in an infinite repeat without an explicit fade.
Its input VGM has no loop and ends at 121.948390 s, only 19 samples after the
last chip write. A visible WAV fade/release tail may come from export/playback
handling; the screenshot alone cannot establish its origin. No automatic fade
or inferred tail padding was added. Preserve captured data versus target
encoding/export choices as separate concerns.

## Latest: exact melody pattern analysis

Added melody_patterns.py and per-chip pattern/occurrence/marking CSVs under
--dump-passes for PSG, SCC and OPLL. Reuses exact adjacent-repeat search; source
Segments and MML remain unchanged. Added six tests covering state/timing keys,
patch changes, zero-length rows, CSV reconstruction and nonmutation.

Local checks: grider OPLL has 50 repeated occurrences (39 multi-Segment),
PSG/SCC test001 has 202 PSG and 32 SCC repeated occurrences. All compared
state fields and intervals reconstruct from the emitted CSVs. grider final
MML is byte-identical to the pre-analysis output. No private fixture content
was added to tracked files. No staging or commit by the agent.

Next: inspect candidate grouping before implementing state-safe target loops.
Do not apply naive textual loops to relative commands or assume matching
Segment states prove envelope/shared-state equivalence. Macros are optional.

Validation completed: all 69 unittest methods passed.

## Pattern metadata in Segment CSVs

The main --dump-passes pipeline appends segment_index, pattern_id,
occurrence_id, repeat_index, pattern_step, pattern_segments and pattern_repeats
to each chip's existing segments.csv. Original cells and row order are preserved;
in-memory Segments remain unchanged. IDs are local to each chip/channel and
all indices are zero-based. pattern_segments is the unit size; pattern_repeats
is the number of consecutive repetitions in the occurrence. Filter
pattern_repeats > 1 to inspect adjacent repeats alongside pitch/volume/state.
Unmatched singleton candidates still have IDs with pattern_repeats = 1.
OPLL rhythm rows (channels 9..13) have blank melody-pattern columns.
The separate analysis CSVs remain available for definition-level inspection.

Validation: seven melody-pattern tests pass, including original-cell retention,
channel-local indices, zero-length rows, blank rhythm metadata and idempotence.

## Target volume-envelope IDs in Segment CSVs

PSG/SCC rendering appends envelope_id and envelope_kind to segments.csv when
--dump-passes is enabled. IDs are the actual shared MML @e IDs, not separately
allocated analysis IDs. Every positive-length source Segment contributing to
an extracted note receives that note's selection, including merged volume runs.

Kinds: software = extracted @e curve; constant = constant-volume @e0;
inline = tied explicit volume changes using @e0 (including bank-limit fallback);
hardware = PSG hardware envelope, no software ID; rest = no assignment;
zero_length = an event without its own rendered interval, no assignment.
Silent channels retain blank IDs. Pattern columns and all source cells are
preserved. Internal Segments, MML and the existing target_notes CSV are unchanged.
OPLL hardware instrument envelopes are not part of this PSG/SCC software bank.

Eight envelope tests passed, covering merged rows, bank overflow, hardware,
silent channels, zero-length rows, cell preservation and repeatable annotation.
The public PSG/SCC 001 fixture retains identical final MML and existing CSV
cells, including pattern metadata.

## MML loop projection

Final PSG/SCC/OPLL melody renderers now project Segment-derived candidates
through melody_loops.py. No MML string-pattern discovery is performed: candidate
positions and unit lengths come from melody_patterns.analyze. Every iteration
boundary must coincide with a complete rendered note boundary. Candidates that
cut an extracted envelope note are retained as ordinary MML.

Within a candidate, only consecutive units with exactly identical emitted
command sequences are replaced by finite loops, and only when text is shorter.
An initial iteration with different initialization is retained. This preserves
the expanded command stream exactly, including relative octave/volume commands,
envelope selections and tied continuations. Loop counts are split at 255.
No additional state resets, quantization, macros or new note boundaries are
introduced. This conservative first implementation leaves many candidates
uncompressed. Sync annotation can expand loops crossing a synchronization mark.

With --dump-passes, inspect `.melody.before.target.mml`,
`.melody.after.target.mml` and `.melody.loops.csv`. The report references ch,
pattern_id and occurrence_id and gives candidate/looped repetition counts and
an applied/skip status. Existing Segment annotations keep their candidate IDs.
The dump files are per-chip intermediates, before final merge/sync formatting.

Validation includes exact expanded-command equivalence, distinct first entry,
relative changes, envelope/tie boundary rejection, large repeat counts and
unmatched material. In normal mode, grider final MML changes from 32660 to
32438 characters; public PSG/SCC 001 changes from 8330 to 7834 characters.
Both grider versions compile with MGSC 1.11; regenerated VGM has the same
1934 ordered distinct interrupt-grouped register snapshots. This is not a
claim of sample-exact audio or optimal compression. Its padded MGS file size
remains 11264 bytes, so text reduction is not a binary-size guarantee.

Validation update: full discovery ran 77 tests; only the line-by-line sync test
helper failed on multiline loops. It now parses complete prefixes between marks
and checks final duration. All 11 sync tests pass on rerun; five new loop tests
pass. Twelve normal/raw chip projections have identical expanded timelines.

## gra2_005 compression investigation (2026-09-29)

No production conversion changes in this investigation. Baseline compiles;
track 3 is the largest byte consumer. SCC fills the shared 32-envelope bank
before PSG. Complete-note loop experiments preserve expanded commands but
only reduce total used bytes 7859 -> 7404; a few tracks grow in compiled size.
Next design: attack groups -> safe loop boundaries -> envelope extraction ->
global bank allocation -> final loops. Do not force every raw Segment repeat
boundary into an envelope break. See field_notes/2026-09-29_gra2_compression.md.

## User direction: musical structure and long envelopes (2026-09-29)

Use the supplied reference MML and ROM-analysis commentary as an evaluation
oracle for intended musical structure, not merely a source of arbitrary repeated
register patterns. Distinguish percussion gestures, repeated note/rest motifs,
nested phrases, reusable subroutines and outer song loops. Do not paste private
musical content into tracked documentation or hard-code a fixture's phrases.

The reference reuses envelope definitions across different note lengths and
base volumes. Matching entire observed volume-run tuples is too restrictive:
short notes can be observed prefixes of a longer shared envelope. Detect attack
boundaries and preserve envelope restart/continuation semantics before comparing
phrases. A mode-changing percussion gesture must not be absorbed into a volume
curve alone. Reference annotations inform validation; VGM observations remain
primary input. Do not invent an unobserved envelope tail.

The user prefers longer envelopes when the shared bank is limited, for MML size
reduction. Prioritize longer genuinely varying volume trajectories; inspect
saved explicit volume commands and definition/reference overhead as a benefit
check and tie-breaker. A long constant hold alone must not consume a new slot.
Evaluate the shared PSG/SCC candidate bank together, not SCC first. Do not
replace this preference with frequency-only ranking of expanded loop copies.

Next implementation target: recover representative long PSG envelope behavior,
reuse compatible observed prefixes/base-level variants with exact target
semantics, then match note/rest motifs and nested phrases using those envelope
identities. Keep Segment, note/envelope, pattern and occurrence mappings visible.

## SCC driver book review (2026-09-29)

Reviewed the user-provided book photographs; findings and page/photo index are
in [scc_driver_analysis.md](local_only/scc_driver_analysis.md). No converter changes.
Macro playback may truncate or pad with rests according to requested duration.
Gradius2 envelopes have phase-dependent release checks: shared prefixes alone
are insufficient to establish compatible envelopes across note lengths.
This qualifies the prefix-sharing proposal above. Next: validate complete
observed trajectories, release and restart semantics before implementing reuse.
Keep inferred musical structure separate from facts observed in VGM; do not
transcribe or commit the private source photos or musical listings.

## Generic shared envelope selection (2026-09-29)

The main pipeline now collects both PSG/SCC candidates before assigning the
shared 32 slots. Longer varying observed curves rank first, independently of
chip processing order or expanded occurrence frequency. Exact observed prefixes
can reuse a selected definition: every tick, including any release portion,
must agree. No Konami commands, fixture names or inferred envelope tails are
used. Existing Segment envelope IDs identify the actual shared definition.

Gra2_005: 19551 -> 14870 MML characters; MGSC 1.11 used bytes 7859 -> 5286.
All six rendered tracks match Segment pitch/volume/mode/wave state per tick.
Public mixed-envelope fixtures pass in standard and raw modes. This is not
sample-exact audio verification. Envelope extraction boundaries are unchanged.
Further work: gesture-aware percussion grouping and nested note-level phrases;
base-volume normalization and parametric envelope inference remain unimplemented.

## CLI metadata and default artifacts (2026-09-29)

Merged metadata name now defaults to the input stem. --name and --title override
name/title independently; --tile aliases --title. Output filenames remain unchanged.
Normal cleanup now covers all three chip pipelines, including absent chips, whose
empty legacy compress variants previously leaked into the output directory.
Debug and pass-dump modes remain available. No music conversion behavior changed.

## Performed units and nested loops (2026-09-29)

`performed_patterns.py` adds a source-derived performed-unit layer without
changing note boundaries or envelope extraction. PSG/SCC units start from complete
extracted notes/rests. A PSG sounding interval followed by a rest, containing noise,
is conservatively grouped with its trailing rest as a `percussion_candidate`.
Mode, noise period, tone period, volume trajectory and hardware-envelope settings
remain in its constituent signatures. This is an inferred coarse gesture, not a
recovered original drum macro. Uninterrupted or ambiguously separated hits are
not split by a new heuristic. Duration variants are not merged or truncated.

The hierarchy detects exact adjacent repeats of these units, then searches each
repeated phrase for inner repeats. OPLL melody uses its existing complete Segment
notes and patch-aware signatures. Source timing, envelope and patch differences
prevent candidate equality. The greedy search is not an optimal grammar recovery.
There are at most two emitted loop levels and 255 repetitions per loop command.
Only equal emitted command iterations are looped; different initialization stays
outside. Ties and complete envelope notes remain inside one unit. The result
expands to exactly the original commands, including relative state changes.
The smaller textual result of legacy and performed-unit projection is selected
per channel. Text savings do not guarantee smaller compiled bytes per channel.

With `--dump-passes`, `.performed.units.csv` retains constituent Segment indices,
relative signatures and hierarchy paths. `.performed.loops.csv` records channel,
pattern/occurrence/parent IDs, depth, unit range, repeat count and application status.
IDs are local to the channel and this analysis, distinct from raw Segment pattern
IDs. Segment CSVs append `performed_unit_id`, `performed_unit_kind`, and JSON
`performed_loop_path`; existing source, pattern and envelope columns are retained.
Zero-length source rows not contributing to a rendered note have blank unit IDs.
Nested occurrence records describe source occurrences, including copies represented
by one loop body. `legacy_projection_selected` means this hierarchy was not emitted.
Existing before/after target MML dumps show the actual selected projection.

Validation: synthetic nested phrases, differing initialization, counts above 255,
tied notes, release differences, noise/mode trajectories and source-cell preservation.
Gra2_005 expanded commands and all six per-tick state timelines match; MGSC 1.11
compiles it with 4806 used bytes (previous shared-envelope output: 5286).
No book-specific commands, source addresses or fixture-specific phrases are used.
Further work includes continuous-drum onset inference, duration-variant gesture
families, non-adjacent macros and compiled-size-aware selection.

Validation completion: all 84 tests passed. Gra2_005 normal/raw expanded commands
and per-tick states match; grider's six OPLL melody command streams match and
MGSC compiles the final output. Legacy report statuses explicitly indicate when
the performed projection was selected. No staging or commit was performed.

## Cost-aware repeat placement (2026-09-29)

The performed-unit compressor now compares its original greedy hierarchy with
an alternative dynamic-programming placement of non-overlapping repeats. The
alternative considers emitted command length, overlapping starts and shorter
repeat counts, while still requiring identical source-unit signatures and exact
command iterations. Initialization differences can stay outside a repeat.
Both strategies recursively search inner repeats; maximum depth/count limits
remain two/255. The shorter textual projection wins, with greedy winning ties.
The performed loop report records `strategy` (`unit_count` or `text_cost`).
This is a text-cost optimization, not an exact model of MGSDRV compiled size.

Gra2_005 selected output: 12688 -> 12575 characters; MGSC used bytes 4806 -> 4794.
A weighted-only experiment used 4754 bytes but had longer text on some channels;
that experiment is not the production selection policy. Expanded command streams
and per-tick states of the selected output match the source-derived baseline.
No note timing, gesture boundaries, envelope selection or voice mapping changed.
Larger future gains likely require non-adjacent reusable phrases or a validated
compiled-byte cost model; do not claim current selection is byte-optimal.

Cost-placement validation: full suite of 84 tests passed; the added cost-selection
invariant test and all six performed-pattern tests subsequently passed. Gra2_005
normal/raw expanded commands and per-tick states match. MGSC 1.11 compiles the
normal output with 4794 used bytes. Output: outputs/gra2_weighted/gra2_005.mml.

## Non-adjacent macro investigation and gra2_003

See field_notes/2026-09-29_macro_compression.md. Added optional local regression
checks for gra2_003 and gra2_005; both pass expanded-command and per-tick state
comparisons. No automatic macro emission or default sync/allocation change.
Macro experiments reduce text but leave real-fixture compiled sizes unchanged.
Gra2_003 requires 26951 track bytes at default sync spacing (plus 886 definitions).
Keeping only start/end sync experimentally reduces tracks to 21603, still above
15000. Prioritize loop-aware sync placement and measured byte cost over assuming
macros are runtime compression. Generated source also exceeds the local mgsc-js
49152-byte source limit before whitespace/comment compaction.

## Loop-preserving synchronization (2026-09-29)

Shared sync candidates now require top-level token boundaries in every active
track, intersected with existing tie-safe leaf boundaries. Entire loops (including
all iterations and nested loops) and macro calls remain intact. No annotation-time
expansion is performed. Applies to PSG, SCC, OPLL melody and OPLL rhythm through
the common final formatter. min_gap remains a minimum, not a forced interval;
zero selects all safe common boundaries, and start/end remain mandatory.
Ended tracks do not constrain later marks. Physical-line wrapping is unchanged.

Gra2_005 MGSC 1.11 total used bytes: 4794 -> 3848, compilation succeeds.
Gra2_003 isolated track sum: 26951 -> 21603, plus 886 definition bytes. It still
exceeds the 15000 track budget; do not claim the complete song now compiles.
Gra2_003 output text is 46960 characters, below the tested wrapper source limit.
Expanded command and per-tick comparisons remain required alongside loop retention.

## PSG/SCC sound reproduction correction

Main target output now treats hardware-envelope m as a raw register period,
using direct y11/y12 writes for zero. Explicit PSG/SCC tuning plus signed detune
preserves observed tone periods within MGSDRV's -127..127 detune range.
Out-of-range cases warn and are marked in target_notes.csv. See
field_notes/2026-09-29_psg_scc_periods.md for independent MGSC/libkss evidence.
Source Segments and legacy debug renderer baselines remain unchanged. Old
pitch-name-only comparisons were insufficient to verify actual output frequency.
# Pitch roundtrip verifier

Reference-note audit now available in scripts/check_reference_pitch.py.
gra2_002: all 310 pitch changes match on all 8 tracks. gra2_008 two iterations:
1391 reference pitch changes match, one extra PSG ch3 observed change (889,
tick1940, CSV line5320) remains unexplained. Formula for both PSG/SCC is
(reference tuning[note] >> (octave-1)) - signed detune. No extra SCC -1.
Four synthetic parser/projection checks pass. No converter tuning change made.

Added scripts/verify_pitch_roundtrip.py, scripts/mml_to_vgm.mjs and
py/roundtrip_pitch.py. Existing reference Segment CSVs remain untouched.
Six synthetic comparator checks pass. gra2_002 completes full MGSC/libkss
roundtrip but zero-offset comparison has differences; onset timing must be
separated from period errors before diagnosing the tuning formula.
See docs/pitch_roundtrip.md for commands, scope and dependency versions.
User suggests deriving a pitch table from original MML and reference CSV.
gra2_002 and gra2_008 original MML already declare a custom #psg_tune table;
validate that mapping first. Do not force a game-specific table on all VGM.
# Automatic target macros (2026-09-30)

py/mml_macros.py is applied after sync formatting in normal target output.
PSG/SCC/OPLL melody participate, ranked by source-character savings. Rhythm
is excluded pending rhythm-aware shared macro parsing. No sync boundary is
crossed; balanced loops and ties are preserved; no recursive definitions.
Allocation stays based on pre-macro text, since macro calls do not save binary
track bytes. GRA2_08 reallocated fixture shrinks 28600 -> 16600 characters;
expanded tokens/timing match. New tests cover melodic chips, loops and ties.
# OPLL rhythm macro completion (2026-09-30)

GF2SMS03 startup fix: rhythm_mml target projection coalesces identical same-time
HH retriggers when the first interval is zero, with a warning. Source CSVs stay
unchanged. Distinct sub-tick collisions remain errors. Reproduction now generates
MML; eight rhythm renderer tests pass including duration/state discrimination.

tests/test_rhythm_pipeline.py now includes optional local grider, using the same
attack/volume/duration checks as the public fixtures; missing input skips only
the local test. No private fixture is added to version control.

Rhythm now participates in automatic macros in its own grammar pool. Existing
Segment exact-repeat grouping/loop projection remains unchanged. mml_sync parses
macro definitions at call time with the calling track's grammar. Added public
pipeline checks for rhythm_only_test01..03 and sample, plus synthetic rhythm
macro/sync equivalence coverage. Sample emits rhythm macros containing existing
loops. Short fixtures need not produce macros when there is no text benefit.
## Zero-length event discussion recorded

See field_notes/2026-09-30_opll_zero_length_events.md before extending the
GF2SMS03 target workaround. Future normalization should separate final tick
state from trigger history. No broad l=0 merge/refactor was implemented in
this documentation update; hardware/emulator audibility remains unverified.
## Local catalog and batch MGS (2026-10-01)

Batch now prefers native mgsc from PATH, supports --mgsc, and uses positional
input/output arguments. JS fallback remains for environments without native
MGSC. Compilation success also requires nonempty output; failure logs are
printed. This Windows session could not launch WSL (E_ACCESSDENIED), so the
user-requested complete native run remains unverified here.

User outputs/mgs compilation failures included ERR_MODULE_NOT_FOUND for mgsc-js,
before MGSC ran. Batch now preflights module loading/initialization before any
conversion and reports setup separately. msxplay's public UI delegates directly
to MGSC.compile, as does our helper. Do not diagnose these old reports as MML
syntax or buffer errors. Tests cover setup failure and continuing genuine errors.

Validation: 56 requested VGMs convert after the fix. Initial regression run had
55 passes and WBIII12 failure before the mid-song one-sample extension; WBIII12
then passed on rerun. Batch MGSC result: 52 successes, four track-buffer failures
(Alest202, Alest204, Alest208, Alest214), intentionally not repaired. Logs and
reports are in outputs/local_mgs_check/. Batch continuation/stale-output test
and nine rhythm renderer tests pass.

Added 56 optional local conversion regressions and scripts/batch_vgm_to_mgs.py
with an MGSC JS helper; see docs/batch_mgs.md. Buffer failures are reported, not
repaired. WBIII08/12 identical startup rhythm collisions are one VGM sample apart:
target coalescing now also permits gaps up to 1/44100 second within one tick,
with equal state and zero preceding interval. Warn and retain all source CSVs;
do not generalize this to arbitrary sub-tick collisions.
## GD3 automatic titles (2026-10-01)

System now uses English only; System and the single release-date field normalize
full-width ASCII. Track/game/author retain per-field language fallback. User
confirmed Alest202 Object too big disappears with a shorter explicit title;
the 240-byte title-line safeguard does not guarantee the whole MGS fits.

py/gd3.py reads bounded UTF-16LE GD3 v1.00 fields. Main CLI uses metadata only
when --title is absent, with --gd3-language ja/en and per-field fallback.
Automatic titles have syntax sanitization and a conservative 240-byte CP932
budget. MGS text field is variable-length; MGSC physical lines are a separate
constraint. Three unit tests pass and Alest201 Japanese output compiles using
MGSC-js 2.0.0. Explicit titles and event interpretation are unchanged.
## Manual allocation override

vgm2mml.py now accepts --alloc with comma-separated channel=bytes entries.
Only specified tracks override final automatic #alloc; no redistribution or
total-budget clipping. Batch forwards the same value to each conversion.
tests/test_mml_alloc.py checks partial/full replacement and invalid input.


## Latest fix (2026-10-01)

Quantized duplicate rhythm hits no longer stop target MML generation: the
last zero-duration same-instrument hit per tick wins. Source Segments remain
unchanged; --dump-passes adds *.opll.rhythm.collisions.csv. See
docs/opll_rhythm.md for the approximation and retained evidence.
Added all 16 reported fixtures to optional local OPLL conversion regressions.
VGM header loop work remains paused; do not resume it as part of this fix.

Validation: all 16 requested conversions and final rhythm attack/volume comparisons
passed; 25 rhythm tests passed. test_conversion_regression.py could not import
fixture_helpers in this checkout. MGSC compilation/playback was not checked.

Restored the test-only SCC clock helper as tests/vgm_test_support.py so it
does not compete with tests/fixtures in shell completion. Updated its import
and excluded the new collision diagnostic CSV from legacy artifact hashes.


## OPLL continuous notes and source retriggers (2026-10-01)

Target rendering now carries zero-duration onset markers to the next timed
interval, slurs continuous intervals and uses q0 when a following pitch/state
interval must keep key-on. Restore q8 for a genuine note end. MGSC 1.11/libkss
roundtrip showed & alone still reattacked on pitch changes; q0 retained key-on.
Do not merge same-pitch key-off/on source events: the old PASS3 retrigger merge
removed real attacks and has been bypassed in Segment construction.

YsSMS01 source/export/fixed key-on counts for channels 0..4:
110/2507/110, 28/19/27, 158/139/158, 152/167/152, 111/110/111.
The remaining ch1 count is a source onset at tick 5951 with zero duration at
EOF, which has no timed target note. Source pitch modulation still rounds to
MGSDRV note names; this change does not promise sample-exact reproduction.
Use scripts/check_opll_key_edges.py reference.vgm actual.vgm --outdir <dir>
for separate traces, Segment dumps, key_edges.csv and count summary. Counts
alone are not timing equivalence; CSV retains explicit times with no alignment.
Generated checks are under outputs/ys_retrigger_check; no private data is tracked.

Validation: 9 OPLL target tests and 25 rhythm tests pass; MGSC 1.11/libkss
compiled/rendered YsSMS01 successfully. Paired 558 timed onsets; raw tick
offsets range 2..7 across playback, not sample-exact alignment. Regenerate
outputs/ys_retrigger_check/fixed/YsSMS01.mml for user listening.

Alest202 evaluated per isolated track due to 20770-byte compiled track total.
ch0/ch1 attack counts match; ch2/ch3 differ by terminal zero-duration edges;
ch4 count equality hides one extra short retrigger and terminal-edge omission.
See field_notes/2026-10-01_alest202_retrigger_check.md. Conversion code unchanged
during this evaluation; volume-15 recovery versus true key edges remains to inspect.

Pre-fix Alest202 export comparison confirms excessive melodic retriggers:
887/2876/1169/1914/3425 versus source 164/163/398/515/515. Attached MML
compiles with 14834 track bytes, whereas fixed isolated tracks total 20770.
No additional conversion change during comparison; see Alest202 field note.


## Current state: coalescing withdrawn (2026-10-01)

Removed projected same-note coalescing after the user reported missing opening
guitar in Alest202. Keep YsSMS01 slur/q0 retrigger fixes and source key-edge
preservation. The user will compare YsSMS01 with its original VGM. Do not
continue compression experiments now. Existing coalesced artifacts are failed
experimental output and must not be recommended for playback or used as goldens.
Opening guitar loss remains unexplained; raw key counts do not prove sound.

Read-only follow-up reviewed duplicate_write_opl3 and vgm-conv's YM2413-to-OPL
converter. Conditional A/B ordering, optional waits and key-dependent RR mapping
are recorded in field_notes/2026-10-01_opll_key_and_envelope.md. Neither reviewed
path proves forced off/on for repeated key-high writes. No conversion behavior
changed; do not infer that this review resolves the weak-sound report.

Onset audit correction: preserve legacy onset, add independent key_on_edge;
target retriggers and continuation gates now use only observed key edges.
OPLL Segments preserve apparently silent rows instead of folding away keys or
register states. Keyed vol=15 intervals emit v0 notes rather than rests.
No coalescing/compression experiment restored. YsSMS01 roundtrips with the
same attack counts; Alest202 checked per isolated track because full capacity
is still exceeded. See outputs/opll_onset_review and the OPLL field note.
Do not claim that these checks resolve the reported lighter/missing sound.

The user accepts the current changes and reports a substantial retrigger
improvement. End audio investigation here. Relevant checks pass after a small
test-only macro-body API correction in test_mml_sync.py; MGSC/libkss roundtrip
checks are complete. Changes remain uncommitted for the user's review/commit.

Evaluation scope agreed with the user: key-on counts only. No timing,
frequency, volume metrics or combined score. check_opll_key_edges.py now emits
keyon_totals.csv and accepts --pairs for existing reference/exported VGM pairs.
missing_keyon/extra_keyon mean summed per-channel count shortages/excesses;
they are not time-matched event identities. Rhythm attacks are excluded.
Four count tests pass. Checked YsSMS01 current export (559/558, shortage 1)
and Alest202 PREVIOUS msxplay export (1755/10271, excess 8516). Do not label
the latter as the current corrected conversion. Sources/exports are untouched;
the tool does not compile or export MGS. See docs/opll_keyon_counts.md.

## 2026-10-01: declared VGM loop metadata
- Added read-only loop boundary inspection and optional .vgm.loop.csv dumps.
- Source samples and legacy wait-clock time remain separate; no KEYON/reset or MML loop emission.
- Seven synthetic tests cover boundaries, payloads, legacy waits and unchanged traces.
- Segment annotations and MML loop notation remain the next stage.
- User regression completed; loop metadata and compressed input fixes are ready for integration.
- Added gzip-signature input detection shared by trace decoding and GD3. VGM <1.50 / zero data-offset headers start at 0x40. Invalid headers/offsets fail explicitly.
- All 42 PS1FM/FFMSX fixtures now produce OPLL register traces; representative MML conversions succeeded.
- Regression conversion_failed entries are deleted duplicate RType fixtures, per user; do not treat them as decoder failures.

## Integrated batch KEYON regression
- Batch MGS conversion now exports the existing compiled MGS using libkss and compares OPLL melodic key-on counts by default; no second MML conversion or compilation.
- CSV/JSON retain four counts plus separate comparison status/error. Missing dependencies, export caps and failures leave counts blank.
- --skip-keyon-counts restores compile-only operation; --libkss-module selects an explicit playback module.
- grider end-to-end export/count check succeeded. No audio equivalence or optimized allocation is claimed.

## OPLL performed-note loop layer
- Added source-linked note/rest grouping and duration-first repeat candidates. True key edges (including zero-tick ones) still delimit units.
- Equal durations alone never authorize replacement: complete rendered trajectories and command iterations must match. Existing Segment loops remain a fallback.
- Segment CSVs retain unit membership; loop reports and paths retain candidate rejection/selection separately.
- Sample/sx01v compile into fewer bytes; grider has shorter source but larger compiled tracks. Alest202 buffer-full and gra2_001 source-size overflow remain unresolved.
- Expanded melodic commands/times were checked against HEAD renderer for all four OPLL inputs; representative MGSC and MGS-export KEYON checks were run. No chip-specific heuristics or new timing/pitch tolerance.

## Reference-loop validation (three songs only)
- User excluded gra2_001; inspect sample, grider and sx01v only.
- Added a bounded reference-loop window audit with source CSV line links, state sequences and interval dumps. Four parser tests pass. Approximate window mismatches are inspection leads, not failed conversion assertions.
- Ordinary repeated instructions can produce identical source states while some integer tick boundaries differ by one tick. Do not discard pitch/volume/voice differences or relax production equality without a separate decision.
- Existing generated MGS files compiled and were exported back into Segment CSVs. Per-song KEYON shortages are 5/38/11; positive keyed-unit shortages are 1/3/1, all source duration one tick. Counts are inventories, not matched missing-event or acoustic-quality scores.
- Isolated first-state pitch/volume differences remain for detailed trajectory inspection. No conversion behavior was changed for this audit.
- Findings and limitations: field_notes/2026-10-01_reference_loop_validation.md. Local detailed outputs: Codex workspace outputs/reference-loop-audit. Do not commit private fixture data or claim full byte/patch/noise/WAV equivalence.

## Sample reference-loop diagnosis
- Regenerated only public sample with --dump-passes, and checked actual final loops after macro expansion against reference phrases. See field_notes/2026-10-01_sample_loop_diagnosis.md and Codex outputs/sample-loop-diagnosis/reference_loop_verdicts.csv.
- Reference line 22 (9/a) is not recovered as a complete two-iteration loop. Its corresponding 28 note/rest units have identical non-timing positive-state sequences, but 5/13 units differ in duration by one tick. Current duration and timed-trajectory equality fail: a concrete missed loop involving timing, not merely a possibility.
- Reference lines 25-27 (b/c/d) also lack complete loops, despite identical source-unit validation keys. Initialization/octave command differences are the separate obstruction; do not attribute these to jitter.
- Line 20 is partially looped (setup first, remaining three iterations); line 21 and lines 28-30 are fully looped. PSG/rhythm repeated cores are looped at shifted boundaries, without reference last-pass exits.
- No tolerance, new vgmticks field or renderer changes were made. The origin of the one-tick differences (source waits versus floating point/60 Hz quantization) is not established. User asked first to diagnose whether reference loops are recovered; do not broaden to a catalog regression.

## Isolated sample musical-length experiment
- Reference-guided local helper uses tempo120/l16/q6/q7/q2 but derives note/pitch/volume/voice order from native Segments. Not a production change or automatic timing estimator.
- MML6453 ->4341 characters; MGSC total used2963 ->2410 bytes, OPLL melodic used2137 ->972. Fully recovered first-pass reference melodic loops5/12 ->12/12. Initialization layout also improves, so savings are not purely timing relaxation.
- Source snapshots unchanged; compressed normalized commands/times exactly equal uncompressed normalized stream. Maximum boundary shift2.625 source ticks; correction CSV retained.
- MGS export604 KEYONs, same as baseline. With declared1ms intermediate-state inspection threshold and raw time, all604 substantive keyed-note state sequences match. Rhythm instrument/volume sequence282hits and custom-patch byte sequences match. Unfiltered differences retained; no WAV equivalence claimed.
- Playable artifact and helper: Codex outputs/sample-note-length-experiment. Findings: field_notes/2026-10-01_sample_note_length_experiment.md. Do not enable this reference-guided method for other fixtures without a separate request and general timing inference design.

## Shared source timing and sample reference audit (2026-10-02)
- User corrected the intended clock policy: all chips share the VGM stream origin;
  all waits must count. Reader now accumulates integer samples, including formerly
  skipped 0x77/0x7A and DAC waits/overrides, and derives time without chip rebasing.
- `--vgmticks --dump-passes` adds absolute samples and source interval ends to
  trace/pass/Segment CSVs; old CSVs retain unavailable samples as None. Command
  timing evidence is also dumped. No musical normalization was enabled.
- New audit: scripts/compare_reference_vgmticks.py; see docs/vgm_timing.md and
  field_notes/2026-10-02_sample_vgmticks.md. Public sample evidence and compiled
  MML are in Codex outputs/sample-vgmticks/with-source-clock; audit is in comparison.
- OPLL 32 comparable later repetitions: at most 139 samples of raw timing difference,
  stable states agree; four rounded-offset windows differ by at most one 60 Hz tick.
  PSG and rhythm each have eight comparable repetitions with equal state sequences
  but different sample timing. PSG alignment is reference-specific, not a KEYON rule.
- Sample MML is identical with/without evidence flag and compiles with MGSC.
  Public conversion regression and bounded timing/chip/target/rhythm tests passed.
  SCC's old synthetic test origin hack was removed in favor of absolute write times.
- Next permitted work is to review source jitter versus musical normalization policy.
  Do not silently enable normalization, run a broad catalog or overwrite fixtures.

## Shared timing adoption after local regression (2026-10-02)
- User completed PSG/SCC, PSG/OPLL and OPLL batch runs. Reviewed CSV/JSON agree:
  669 reported inputs, 399 MGS successes, 269 Track buffer full failures, one
  missing-input failure. The user deliberately deleted the temporary exported
  YsSMS01.vgm; ignore that case for adoption. Present inputs have no observed
  converter exceptions. No generated outputs were changed during review.
- All 399 compiled inputs completed OPLL melodic KEYON comparison. Count
  differences remain (including large PRIMK/FMPAC shortages); they are not a
  timing-change attribution or proof of specific missing events. Rhythm and
  PSG/SCC notes are outside this metric.
- Recorded totals, evidence paths and limits in
  field_notes/2026-10-02_vgmticks_regression.md. User approved production adoption
  and will commit this record, create a PR and merge into main themselves.
  Do not perform those git actions on their behalf.
- After that merge, the next requested task is musical duration normalization.
  Preserve raw sample evidence and distinguish corrected target timing from
  observed source intervals. Normalization remains disabled at this checkpoint.

## Optional musical normalization implemented (2026-10-02)
- User requested source-inferred correction on sample, then bounded benchmarks
  of sample/grider/sx01v. Added py/note_normalization.py and --normalize-lengths
  to converter and batch CLI. Default conversion is unchanged; no Git commit,
  staging, branch switch or PR was performed.
- Fit a common OPLL onset clock, project notes/gates and rhythm, retime PSG/SCC
  commands without scaling frame envelopes. Native traces/Segments stay intact.
  Unsafe/uncertain projection retains all conventional target parts. grider
  abstains because no sufficiently confident shared clock was found.
- Corrected sample: 6333 ->3544 characters, MGSC used2956 ->1678 bytes,
  source/export KEYON609/609. sx01v:17428 ->11248 characters, used9128 ->7183,
  KEYON1615/1615. grider unchanged25243/13075, KEYON2596/2559.
- Ordered pitch/volume/voice state runs agree for sample/sx01v with explicit
  44-sample intermediate inspection threshold; rhythm instrument/volume counts
  and sequences also agree. No WAV equivalence or general PSG/SCC-only clock
  estimator is claimed. Full evidence and limits in the benchmark field note.
- Artifacts: Codex outputs/length-normalization/{sample,grider,sx01v}/normalized.
  Normalization JSON plus dump-only note/loop CSVs distinguish target correction
  from source samples. Exact loop expansion and effective setter-state equality
  are checked before writing target files. Sample CLI native CSV identity and
  default public conversion regression passed.
- Bounded verification finished: 39 tests passed across normalization, rhythm
  rendering/notation, batch and public conversion suites; git diff --check clean.
  Saved native Segment CSVs match byte-for-byte across all three benchmark cases.
- Next: user listening and opt-in regression; do not auto-enable correction,
  copy reference tempos, run a broad catalog or overwrite fixture evidence.

## User-run normalization regression reviewed (2026-10-02)
- Recorded completed PSG+OPLL (26) and OPLL (565) runs in
  field_notes/2026-10-02_normalize_lengths_regression.md. CSV/JSON agree;
  per-input correction reports were reviewed. PSG/SCC-only interrupted run is
  not needed for this comparison and receives no correction with current inference.
- Correction applied to 3/26 and 101/565 inputs. Current compilation: 346 success,
  243 buffer_error, 2 compile_failed; no current conversion exceptions.
- Compare shared input paths: five OPLL buffer errors resolved (Alest208/211,
  FRAY06/11, ILCITY23), but XEVIFS07/08 newly fail Invalid length on r%1 at
  inferred tempo149. OPLL catalog adds22 F1SPRT3D paths and removes2 temp exports;
  do not attribute raw success-total growth to correction. PSG+OPLL statuses unchanged.
- All five buffer-resolved cases are among26 applied songs whose MGS export
  reaches its duration cap. Compilation success is not completed fidelity checking.
  Paired completed OPLL set285: shortage1941->1848, excess32->32;12 inputs
  improve,273 unchanged,none worsen. Incomplete cases are outside that comparison.
- Pending: minimum-length regression and export-duration/termination investigation,
  then per-note semantic correction policy and larger phrase/last-pass-exit loops.
  The95% heuristic is provisional; user questioned it and favors semantic bounds.
- User will commit/push codex/normalize-lengths. This review only writes records;
  no code fixes, staging, commit/push, catalog rerun or fixture changes performed.

## Title-grouped MGS collection utility
- Usage documented in docs/collect_mgs.md on 2026-10-03: preview/copy/overwrite,
  title-folder mapping and collision handling. README intentionally unchanged.
- Added scripts/collect_mgs.py for user-requested MSX player folder layout:
  <title>/<track>.vgm/<track>.mgs -> <outdir>/<title>/<track>.mgs, also .vgz.
  Other layouts use the immediate parent. File names and contents are preserved.
- Supports --dry-run and explicit --overwrite; identical outputs skip. Duplicate
  destinations are checked before copying. Conversion/compilation is not rerun.
- User clarified this is a personal listening utility, not a primary project
  output feature: removed its usage from README. The project output remains MML;
  MGS compilation/playback serves verification. No user output tree was populated
  automatically.

## Bounded authored-loop inventory
- User requested OPLL reference-loop statistics plus phrase lengths, with the
  same method available for a later PSG/SCC comparison. Added
  scripts/audit_mml_loops.py and six focused tests; uses bounded reference parser.
- OPLL subtree currently has only grider/sx01v MML: 55 source loop definitions,
  69 channel-expanded definitions, 49 finite,6 infinite,23 last-pass exits,
  6 enclosing nested loops,max depth2. Grider's song loop encloses rhythm loops.
- Phrase steps range12..7872 with 48=quarter; 2/4/8-whole-note phrases coexist
  with short repeats. Separate ordinary/common/final/expanded lengths retained.
  Field note: field_notes/2026-10-02_opll_reference_loop_statistics.md.
- CSV/JSON outputs in Codex outputs/mml-loop-statistics/opll. No fixture edits,
  conversion reruns, PSG/SCC survey, staging or commit actions. Unknown syntax
  is reported as unsupported; macro calls/loop-internal portamento aren't yet
  supported by the length audit. Next may be PSG/SCC survey with scope controls
  or loop recovery comparison; source statistics alone do not prove recovery.

## User-run PSG/SCC loop inventory reviewed
- Scope corrected on 2026-10-03 following user confirmation: only seventeen
  original msxplay gra2 scores are valid; exclude with_sync_mark split/marked
  variants and all VGM-derived NEMESIS2 conversion outputs. Added audit
  --exclude-dir option. Scoped reports in Codex outputs/mml-loop-statistics/
  psg_scc-original:17 found,3 parsed(002/008/017),14 unsupported;36 definitions,
  30 finite,6 infinite,0 observed exits,5 with children,max depth2. Full coverage
  requires macro/control parser support; prior mixed totals below are historical.
  Field note updated; no conversion, compilation, fixture or Git mutations.
- Recorded results and interpretation in
  field_notes/2026-10-02_psg_scc_loop_statistics.md. User's run found189 files,
  parsed115,unsupported74;4253 definitions,4235 finite,18 infinite,0 exits,
  15 enclosing-child loops,max depth2. No re-audit or parser change was made.
- Major scope bias: msxplay/gra2 has95 parsed files but89 have no loops; six
  loop-bearing files are three versions each of002/008 (108 definitions).
  NEMESIS2 has20 parsed files,16 zero-loop; remaining files supply4145 definitions
  (97.5% of total), with converter-style headers and tiny loops. Do not equate
  that mixture with the authored OPLL two-score reference population.
- All74 unsupported in msxplay:46 macro-call rejections,28 unsupported lexer
  syntax (including h with multiple arguments). Fourteen of17 original gra2
  scores aren't parsed. Zero | counts do not establish that PSG/SCC lacks exits.
- 3800/4253 bodies have<=3 score steps. Raw steps across tempo75/225 aren't
  physical-duration comparisons. Next: improve audit coverage and select one
  original reference per song before drawing chip-group structure conclusions.

## GD3 title display correction (2026-10-03)
- Final merged MML now uses CP932 (Shift-JIS) for native MGSC/MSX Japanese titles;
  unrepresentable characters become ?. Intermediate CSV encoding is unchanged.
- GD3 system prefix is separated from the following text by one space, including
  missing game/date cases. Existing game/date parentheses and explicit title
  override semantics remain unchanged. JS compile/export helpers accept UTF-8
  and CP932 input. README and focused GD3 tests updated.

## Short-first hierarchical loop experiment (2026-10-03)
- Added pure experimental py/hierarchical_loops.py and isolated
  scripts/experiment_hierarchical_loops.py; no production converter integration.
- Compared immediate vs retained candidates on normalized sample/sx01v OPLL
  note units, original-unit widths<=128, depth<=3; exact trajectory/command
  expansion asserted. Five tests pass. Private artifacts in Codex outputs/
  hierarchical-loops; field_notes/2026-10-03_hierarchical_loop_experiment.md
  documents metrics, source reference statistics, and limits.
- sample no improvement; sx01v retained saves36 body chars vs existing;
  immediate worsens244. Not full MML/MGS size metrics. No new audio roundtrip.
- Harness currently observes target-stage notes after envelope decisions, not
  yet pre-envelope structural extraction. No individual reference-window recovery
  certification. Next inspect missed reference intervals and last-pass exits/
  effective state equality; preserve source data and default output behavior.

## OPLL loop strategy comparison (2026-10-03)
- User narrowed discussion to loops and deferred envelope ordering. Use exactly
  sample and sx01v. Prior rejected count-only/gra2_005 report and output tree
  were deleted. No conclusions from that comparison should be reused.
- New source_loop_plan creates an executable structure before target command
  generation; original-unit widths<=128, depth<=3. Both immediate short-first
  and retained-candidate trees drive emitted MML with exact expansion checks.
  Default converter unchanged; explicit optional renderer arguments only.
- scripts/experiment_opll_loop_strategies.py compares current/immediate/retained
  with all PSG/SCC/envelope/rhythm/macro settings unchanged, normalization off.
  All six outputs compiled with MGSC1.11; expanded final timed tokens agree.
- sample text6333/6008/6333 bytes, MGSC used2956/2956/2956. sx01v text
  17428/17518/17187, MGSC used9128/9428/9168. Thus text savings alone do not
  justify production adoption. Private outputs/logs are in Codex outputs/
  opll-loop-strategies; field_notes/2026-10-03_opll_loop_strategies.md records
  methods and bounds. No audio roundtrip or source-reference loop recall claim.
- Envelope-order experimental helpers remain available but are deferred; current
  work and recommended comparisons use the OPLL-only script above. Do not silently
  substitute fixtures. Next may examine missed reference phrases or binary-cost
  loop selection if requested. No staging/commit/push performed.

## Reversible OPLL structure update (2026-10-03)

- User corrected the objective: final MML characters plus successful compilation/no buffer_error. The earlier binary-size adoption criterion above is superseded.
- Added loop_structure.py with exhaustive exact adjacent-repeat candidate catalog, reversible nested tree and alternative intervals. Source width/depth bounds removed; target counts split at 255. Explicit structural experiment only; default converter unchanged.
- sample current/structural: 6333/6333 characters; sx01v: 17428/17187. All four MGSC compilations succeed, no buffer errors, final expanded timed commands identical. No further size improvement beyond prior retained strategy on these fixtures.
- Six structural tests, four source-plan tests and five hierarchical tests pass. Candidate/tree CSVs and full artifacts are in Codex outputs/opll-loop-structure. See field_notes/2026-10-03_reversible_loop_structure.md.
- Macro-aware selective unrolling remains the separate next phase. No staging, commit or push.

- Additional final sx01v syntax inventory: physical loops 73->91, nested loops 4->17, depth 2->3; both outputs already use 32 macros (no bracket loops inside definitions). Recorded per-track counts and structure-aware macro plan in the reversible-loop field note. Next first improve macro search with loops fixed, then compare selective expansion; exact token preservation and MGSC success gate final character ranking.

## Structure-aware macro allocation (2026-10-03)
- Added structured_macros.py and optional --enhance-macros in converter/batch. Searches loop interiors, expands existing generated calls for reselection, compares four bounded allocations with baseline, asserts exact timed-token equality. Loops stay intact; inner-loop expansion remains next phase.
- Structural sample 6333->4913 chars; sx01v 17187->14938. Both compile with MGSC1.11 without buffer errors. Public sample CLI path also compiles. No whole-catalog regression or audio roundtrip.
- Candidate/selection dumps use target-tree paths at each allocation step, not Segment IDs. docs/structured_macros.md and field_notes/2026-10-03_structured_macro_experiment.md document policies/results. No staging/commit/push.

## Five-fixture macro follow-up (2026-10-03)
- es59/es56/Alest202/FRAY02/SORCER02 source characters reduce 21.4/11.7/18.0/20.0/1.5%; all exact baseline timed streams agree, but all still fail compilation (track buffers or mgsc-js 49152-byte source cap). Unchanged alloc, conventional timing, default loop renderer.
- Fixed long enhanced macro definition physical lines: wrap at 120; es59 Undefined Macro disappears, reveals Track buffer full. Five focused tests pass. Artifacts/logs in Codex outputs/structured-macro-followup; field_notes/2026-10-03_structured_macro_followup.md records methods and limitations.
- Restored es59/es56 source MML: 3061/3535 chars, 44/50 physical loops, depth2/3, both compile. Their 9-channel OPLL mode0 source exposes a pre-existing six-melody target limitation: active Segment channels6..8 omitted. Do not claim source fidelity from baseline equality. Not fixed in this compression follow-up.

## Defaults, OPLL mode and title investigation (2026-10-03)
- Structural OPLL loops/enhanced macros now default; --legacy-loops/--legacy-macros restore earlier compression in converter and batch. Normalization remains opt-in, now handles nine melodic tracks and selected structural policy. Retained scripts updated to force their requested loop/macro strategies.
- Mode0 projects nine channels, mode1 six plus rhythm. es59/es56 startup-only enable followed by disable is recognized. High-channel voice IDs/diagnostics/macros/normalization included. Synthetic nine-channel VGM compiles; real es59 now has f/g/h, 50150 chars and still exceeds JS input cap.
- sample default4913/legacy6333 chars both compile with exact timed-token equality. Ancestor overlap selection check optimized; full es59 reconstruction unchanged (~204s search). Large batch tests may require --timeout above300.
- All seven reported bad stored titles are UTF-8; four good newer binaries are CP932. Current GD3/CP932 title-only probes for all11 sources compile and byte-match. No gd3 algorithm change needed; regenerate old outputs. Report and test scope in field_notes/2026-10-03_default_compression_opll_mode_titles.md. User will run full regression. No staging/commit/push.

## PSG/SCC structural loops before envelopes (2026-10-03)
- Default shared bank now uses structural SourceLoopPlans before envelope-ID
  selection; --legacy-loops restores earlier PSG/SCC behavior too. No reference
  envelope lengths/phrase thresholds, invented attacks or source timing changes.
  Macro selection remains independent. Source plans drive actual target output.
- Added/retained source/Segment mappings, complete candidates/tree/projection,
  expanded/stored envelope counts and performed-unit/path annotations. Removed
  unused legacy Segment search when rendering an existing source plan. Updated
  the envelope-order harness to isolate PSG/SCC while keeping OPLL fixed.
- 0012795->2511 chars,0021793->1822; both compile. GRA2_0318206->18213, still
  Track buffer full ch3. contrail61402->58953, still exceeds JS source cap.
  Native tick-state comparisons pass in all paired cases; mixed OPLL timed
  commands unchanged. p52_arbl diagnostic179772 chars with --legacy-macros
  matches Segment tick states; full enhanced-macro paired test remains undone.
- Restored p52/contrail authored scores compile. contrail initially was saved
  GitHub HTML; extracted embedded MML into private outputs without changing the
  user file. Both references exceed the current score-length audit grammar;
  syntax statistics/limitations are recorded, not claimed loop-window recovery.
- Seven structural-bank tests, ten envelope tests, twelve sync tests, public
  conversion regression and four source-plan tests pass. Field note:
  field_notes/2026-10-03_psg_scc_pre_envelope_structure.md. Private outputs in
  Codex outputs/psg-scc-structure. No full local regression or Git staging,
  commit/push. Do not rerun expensive whole-catalog tests without user request.

## Authored gra2 PSG/SCC follow-up (2026-10-03)
- Compared gra2_002/gra2_005 and six available gra2_001 split VGMs exported
  through msxplay.com. Enhanced macros are ON in both; only the PSG/SCC
  envelope-first versus source-loop-first bank differs. Normalization is OFF.
- Final source totals62001->61332 chars (-1.08%); gra2_0058749->8313 (-4.98%,
  including fewer sync comments; code-only7578->7424). Five inputs shrink,
  two unchanged, one grows41 chars. All16 compile via MGSC1.11/mgsc-js;
  native Segment fields and effective per-tick target states agree in all pairs.
- Source trees reach depth3 in some split inputs; final bracket depth remains
  at most2. Counts include macro continuation lines. More source markers do not
  guarantee fewer final characters after stateful projection/macro selection.
- Corrected split inventory after user clarification/regeneration: the earlier
  98 MMLs were v2 fine-grained outputs, whereas six gra2_001 VGMs correspond
  to original loop-boundary splits. Current six MML/VGM pairs have boundaries
  0,886,2166,3126,5046,6966,8526; no missing/extra numbered files. Previous size
  benchmark consumed unchanged VGMs, so its measurements remain valid.
- All ten multi-block songs have35 complete MML/VGM pairs; all MML block
  comments match recomputed shared loop boundaries. Eight have shell wrappers;
  007/011 lack local wrapper/splitter copies but their existing intervals also
  agree with the001 splitter. VGM headers/durations pass coarse checks. Private
  sync-pairs.csv/json inventory is in the same Codex output directory. This is
  a read-only inventory, not a35-block conversion/roundtrip benchmark. Use the
  loop-boundary files rather than v2 splits for authored-loop recovery checks.
- Results/bounds: field_notes/2026-10-03_gra2_msxplay_structure_comparison.md;
  private artifacts: Codex outputs/gra2-source-structure/comparison.csv/json.
  No source/fixture changes, staging/commit/push. Full17-song regression,
  unsplit001 and p52 enhanced-macro pair remain untested. Keep msxplay-derived
  authored references separate from vgmrips/NEMESIS2 captures in comparisons.

## All35 authored-loop block comparisons (2026-10-03)
- User clarified that file correspondence alone was insufficient. Completed35
  earlier/current conversion pairs with enhanced macros held ON, normalization
  OFF, changing only PSG/SCC envelope-first versus source-loop-first projection.
  Six001 pairs reused;29 pairs added. Production conversion code unchanged.
- All70 conversions succeed; native Segment fields and effective tick states
  agree across every pair and with each rendered output. MGSC1.11/mgsc-js
  compiles34/35 in each variant;016 block03 retains track1 buffer full in both.
- Total characters246524->245186 (-0.54%); code-only218404->217724 (-0.31%).
  23 blocks shrink,2 unchanged,10 grow. Best004 block01 -8.35%; worst007 block02
  +6.26%. Final physical loops758->789; selected source trees reach depth4,
  final target brackets remain depth2. Source structure does not guarantee
  minimum final characters or recover all reference parent loops.
- Reference347 channel definitions produce477 invocation windows. Explicit
  first-audible-note mapping uses offsets3/4 and +/-1 tick window tolerance.
  Approximate catalog full/partial225/343, selected179/271; final old32/183,
  new33/202. Do not claim these geometric counts as exact semantic recall.
  One-note/multi-note/nested-parent categories are separately recorded.
- Inspected004 block01 track5: reference nested parent is selected in source
  tree but projected as expanded_different_commands; initialization changes
  inner repeat count3 on first pass versus4 later. This identifies a target
  projection improvement area without changing current sound/state behavior.
- Full report: field_notes/2026-10-03_gra2_loop_block_benchmark.md. Private
  all-blocks-comparison and loop-recovery CSV/JSON are under Codex outputs/
  gra2-source-structure. No35-block audio roundtrip, staging, commit or push.
  Next output direction named by user: mml2vgm MML, then other FM chips; finish
  discussing this benchmark before assuming new implementation scope.

## Six-level loop request (2026-10-03)
- Raised the legacy performed-unit compressor default max_depth from2 to6;
  explicit depth overrides still work. The default structural source builder
  and target projector were already uncapped. The35-block final depth2 was
  an observation, not their configuration. Do not infer a cap from that metric.
- Added six-level detection/projection and legacy-depth regression checks;
  expanded commands are exact. Synthetic structural/performed6 MML both
  compile through MGSC1.11/mgsc-js (63 used bytes). Local source hierarchy and
  projection CSVs/MML/MGS are in Codex outputs/six-level-loops.
- Confirmed default PSG/SCC order: source structure, software-envelope
  selection, target projection, macros. No envelope-order behavior changed.
- This small depth change does not fix differing-initialization parent-loop
  rejection or rerun the35 private blocks. Staging/commit/push remain user work.

## Unrestricted legacy loop depth (2026-10-03)
- User clarified that default depth caps would distort algorithm evaluation.
  Supersedes the preceding2->6 setting: performed_patterns now defaults to
  max_depth=None. Experimental immediate/retained strategies, SourceLoopPlan's
  experimental branches and comparison wrappers also default to no depth cap.
  Explicit limits remain available for deliberately bounded experiments only.
- Seven-level legacy/experimental regressions check exact expanded commands;
  existing structural depth and envelope-order checks remain applicable.
  Source tree recursion terminates on strictly shorter repeated bodies, without
  an arbitrary depth cutoff. No timing/envelope/macro behavior was rewritten.
- All42 focused tests pass (performed/hierarchical/source plans, structural
  loops, pre-envelope order and OPLL target). Inspected seven-level legacy
  hierarchy CSV and generated MML in Codex outputs/unrestricted-loop-depth;
  all382 expanded commands are unchanged. diff --check also passes.
- Earlier35-block results retain their original conditions. No rerun or new
  compiler/playback claim beyond the preceding six-level compilation check.

## gra2_005 depth-removal Segment check (2026-10-03)
- At user request, compared legacy depth2/depth6/unrestricted and current
  default structural output, with enhanced macros and source-sample dumps ON,
  normalization OFF. No conversion code or fixture inputs changed for this check.
- PSG5029/SCC10369 native Segment rows agree in all four variants; all14
  trace/pass CSVs are byte-identical. Every final per-tick effective state agrees
  with its own Segments and with the other outputs. PSG/SCC before/after loop
  projection also preserves every expanded timed command.
- Legacy outputs are byte-identical at8749 characters and applied depth2;
  changed compressor was exercised six times per run. Default8313-character
  MML matches the previous benchmark byte-for-byte and bypasses that compressor.
  All four compile with MGSC1.11/mgsc-js, no buffer errors.
- Recorded in field_notes/2026-10-03_gra2_005_unrestricted_depth_validation.md.
  Local artifacts are Codex outputs/gra2-unrestricted-depth. No audio roundtrip
  claim; this short fixture does not exercise deeper-than-two legacy repeats.

## OPLL continuous-note child-loop recovery (2026-10-03)
- Implemented only in the separate test checkout at
  I:/wsl/repositories/emef2247/test/msx_vgm2mml. The original checkout and its
  active regression were left unchanged; do not copy back or stage automatically.
- Added opll_inner_loops.py: retain outer note/phrase plans and source-linked
  child Segment plans, then project unchanged target controls through both.
  Keep parent-only spelling as an alternative and assert exact expansion.
  Native key edges, notes, timing, patches, PSG/SCC and envelope order unchanged.
- --dump-passes adds child pattern/occurrence paths directly to OPLL Segment
  rows, plus per-channel child marker/candidate CSVs. Source IDs and ranges
  remain available separately from whether the child is emitted.
- FFMSX01 default MML shrinks49922->7944 characters, compiles through MGSC1.11
  JS with ordinary15000 track allocations, and uses5999 total bytes. All8735
  OPLL/4647 PSG native rows,14 trace/pass dumps and expanded timed final commands
  are preserved. Legacy loops/enhanced macros remain7659 characters/5426 bytes;
  the repair recovers capacity, not global minimum size.
- sample4913, grider24721 and gra2_0058313 characters are unchanged; sx01v
  grows15024->15048 (one child loop,4 additional compiled bytes). All eight
  paired conversions compile; Segments, passes and expanded commands match.
- Results and limits: field_notes/2026-10-03_opll_inner_loop_validation.md.
  All55 focused tests pass, including public conversion, sync and macros;
  git diff --check passes.
  Wider catalog regression/listening is next; no native WSL or audio roundtrip
  claim. Final macro-aware global alternative selection remains future work.

External comparison helper: scripts/batch_vgm_conv.py adds AY-to-OPM outputs
beside the existing listening tree, with separate logs/report. It does not
convert SCC. Existing --generator runs already retain MDX. Comparison uses
external vgm-conv 0.14.1; no external implementation is copied into this project.

2026-10-06 MDX display preview: scripts/render_additive_mdx_notes.py is executable
against existing additive diagnostic CSVs; instructions in docs/psg_scc_opm.md.
It emits separate .notes.mdx/MML/VGM and semantic verification. YUMADV18 passed
state/key-edge comparison; MMDSP display is unverified. Four focused tests pass.
The generator binary is unchanged. Do not replace the default renderer before
player/display validation. PSG unsupported-mode work is deferred for MDX work.


## 2026-10-23 shared FM short-state threshold

User authorized aligning the inherited approximately 1 ms selector across MSX,
x68k and MUCOM, widening the default to 8 ms. note_normalization now calls the
identical fm_state_runs helper shared with those repos: 352 original samples,
retain at least one state per attack, report dropped indices. Existing MSX
normalization remains opt-in; no source evidence or standalone reference-audit
tolerance changed. There is no new MSX --normalization-ms CLI option. Existing
13 note-normalization tests passed. Docs/note_normalization.md updated.
Saved, not staged/committed/pushed; unrelated working-tree files preserved.


## 2026-10-23 final shared threshold direction

User chose the original1ms/44sample default. Shared fm_state_runs default is44
again; docs updated. x68k/MUCOM expose independent --fm-state-ms while their
whole-gate/clock --normalization-ms stays8ms. No new MSXCLI option. No public
pattern sweep or local_only conversion performed in this follow-up.

## 2026-10-27 completed user-run v1.1.0 comparison

User finished run_test.sh. Compared only requested local groups: TWINBEE7,
SALAMD14, FMPAC5, contrail1. All 27 staged input hashes agree. All 26 ordinary
MML and 24 generated MGS files are byte-identical to ../../test2/msx_vgm2mml
(v1.1.0), with matching publication hashes. Both runs: 24 success, SALAMD02/06
buffer errors, contrail unsupported OPLL register range. No ordinary-output
regression found. FM24ms/normalization8ms unchanged. No rerun/listening/public
comparison. See outputs/diagnostics/v110_user_run_comparison_20261027/analysis_ja.md
and external field_notes/2026-10-27_v110_user_run_parity.md.

Current native integration remains uncommitted; comparison alone is not a full
completion claim for seven source chips. Pending approved next direction:
always-output blueprint/reference VGM, volume-free blueprint with source voice
comments, then new indented loop-start line layout in normal MML and blueprint.
Preserve this parity baseline before intentional formatting changes. README,
user run scripts/logs, inputs and normal products remain untouched. No staging,
commit or push. x68k runtime/PDX investigation is separate; driver was supplied
but guest configuration was not changed.

## 2026-10-27 score-only blueprint and independent reference products

Implemented the approved post-v1.1.0 update on codex/musical_HAL. Native source
music is constructed before accepted MGS lowering. Blueprint and reference VGM
survive target lowering/compilation failure with independent outcomes. Default
canonical output is both; MGS export also publishes reference VGM. Failed VGM
plus successful MML is an aggregate partial_failure/nonzero result; batch still
compiles the explicitly successful current MML. Edited/unowned products remain
protected. Normal MML loop layout is whitespace-only and preserves CP932.

Latest user correction supersedes placeholder-voice requests: blueprint contains
no executable @ or v commands, definitions or software envelopes. Timbres/FM
parameters/SCC waves remain comments and sidecars. Score repeats use pitch,
duration, rest, attack/hold atoms, including phrases inside a long held gate.
One global constrained target clock keeps short positive intervals; split pages
share timing. Overlaps get additional lanes/pages. Terminal OPLL rhythm attacks
have explicit target-only tail; non-OPLL percussion is explicitly unmapped in
comments/excluded_percussion. PCM remains outside blueprint.

Verification: 206 focused tests pass, no errors/skips. SALAMD01 fresh default
export produces MML/MGS/VGM/blueprint. Its score lines shrink 20816->11937 chars;
finite-loop openers 44->102. Saved source rerender: 27/27 blueprints,32 pages,
31 compile; only contrail first page exceeds MGSC buffer. All14 SALAMD scores
compile. Ordinary layout:26 token-preserved/idempotent,24 byte-identical MGS,
2 unchanged SALAMD02/06 buffer failures. No listening claim. Original source
and output files protected. Artifacts: outputs/diagnostics/blueprint_v2_20261027/
(analysis_ja.md, integration.json, fixture_rerender, normal_layout, end_to_end).

README/user run scripts/logs untouched. No staging, commit or push. External
note: field_notes/2026-10-27_blueprint_score_and_independent_vgm.md. Next: user
score/listening review. Do not resume HuC KATOKEN until requested; do not claim
all-source blueprint rhythm mapping or automatic envelope reattachment exists.

## 2026-10-27 source score guidance and bounded curves

Implemented score_structure before target lowering; blueprint shares native
pitch spans. Opt-in --score-guided-loops uses whole-note source-guide mappings,
all exact curve/settings variants and exact-command/fallback guards. Applies to
PSG/SCC and ordinary/normalized OPLL; source guides cover other analyzed melodic
chips without new MGS mappings. HW presence is not a repeat barrier; no phase
simulation in score identity or invented resets.

Added default-off --psg-state-ms/--scc-state-ms with explicit maximum/mean volume
register-error budgets; observed compatible-curve reuse only. Source/renderer
profiles checked independently. Applied normalized clocks cause explicit
abstention until post-lowering budgets are proven. Backend fallback retains
accepted projected curves via repartitioning.

322 focused tests pass, including actual MGSC/libkss two phases/full-bank inline
fallback. Dispatch jitter means no raw-sample/acoustic bound claimed. Frozen
3input/4mode comparison: SALAMD02/06 still buffer-fail; small MML gains only.
GRA2split01 allcompile but allMGS1536bytes. Current SALAMD06/GRA2 24ms outputs
match grid MML bytes. Inputs/user publications unchanged. See ignored
outputs/diagnostics/score_guided_curves_20261027/analysis_ja.md and English private
field_notes/2026-10-27_score_guidance_and_bounded_volume_curves.md.

HW probe: MGSDRV can restart envelopes at new notes even with one MML shape
selection; q0 alone does not fix it. Native VGM single-write retention tested.
Existing target HW-articulation repair remains separate, not claimed solved.
README unchanged; no staging/commit/push. User scripts/logs preserved. Next user
score/listening/sweep review; no HuC resumption or default approximation.

## 2026-10-27 checkpoint and HuC6280 resumption authorized

User is auditioning score/curve results and explicitly requests a new branch,
checkpoint commit, then continued HuC6280 implementation. Checkpoint branch:
codex/score-guidance-huc6280. Include task source/tests/docs only; preserve
untracked user logs/run_test.sh/run_sweep.sh. External three October27 MSX notes
are committed separately; no private push. Resume scoped HuC unsupported noise,
dynamic-wave and OPLL spill investigation; do not alter audition defaults.
