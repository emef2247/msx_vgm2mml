# PSG/SCC structure before software envelopes

## Scope

Extend the adopted OPLL structural plan to PSG/SCC. Use public 001/002 first,
then the requested local GRA2_03 and contrail captures. Do not use source MML
to choose note boundaries, periods, envelope lengths or production thresholds.
Normalization is off. Native VGM/Segment construction is unchanged.

The shared envelope bank builds a reversible structural tree from complete
interpreted notes/rests and their settings/volume runs before selecting any
envelope IDs. It counts stored representatives of that tree, still preferring
long observed curves. All original occurrences are subsequently rendered;
initialization and other unequal commands remain expanded. Short and overlapping
candidates remain in the catalog. Sustained notes are not divided into invented
attacks to create more loop candidates. --legacy-loops restores the earlier
PSG/SCC envelope-first projection, independently of --legacy-macros.

An unused legacy Segment repeat search still ran inside the source-plan renderer.
On p52_arbl this consumed substantial time without supplying any projection.
It is now omitted only when source_plans is supplied. Earlier pass and native
pattern dumps remain available. A test rejects accidental legacy searches in
the structural bank.

## Validation and measurements

The comparison holds OPLL projection and enhanced macros fixed and changes
only the PSG/SCC bank. Full MML character counts include comments. All four
paired cases preserve the same effective PSG/SCC pitch, octave, volume, mode,
noise period and waveform ID at every 60 Hz source tick. They also match their
native Segment timeline under the existing target pitch interpretation. OPLL
expanded timed commands are identical in the mixed contrail comparison.

| Fixture | Envelope-first characters | Loop-first characters | Change | MGSC 1.11 |
| --- | ---: | ---: | ---: | --- |
| psg_scc_001 | 2795 | 2511 | -10.16% | both compile |
| psg_scc_002 | 1793 | 1822 | +1.62% | both compile |
| GRA2_03 | 18206 | 18213 | +0.04% | both Track buffer full, ch3 |
| contrail | 61402 | 58953 | -3.99% | both exceed mgsc-js source cap |

001 code characters excluding blank/comment lines fall from2118 to2022; its
sync comment count also falls from12 to8. Its compiled used bytes stay1825.
002 used bytes change843->895, still fitting allocations. Therefore neither
more source structure nor fewer source characters guarantees lower track usage.
GRA2_03 does not gain meaningful compression; its existing buffer failure remains.
contrail uses21->20 envelope definitions. The source cap here is the49152-byte
mgsc-js input limit, not a successful native-compiler buffer measurement.

p52_arbl structural conversion also completed and its effective PSG/SCC state
matches Segments at every tick. This separate diagnostic used --legacy-macros:
179772 characters, exceeding the JS source cap. Its full enhanced-macro size
comparison is **not completed** and is not included in the paired table. The
earlier envelope-first run was interrupted after prolonged redundant legacy
searching. Existing warnings for241 SCC and588 PSG notes outside the target
detune range remain; this work does not change period approximation.

Local MGSC wrapper/module: MGSC1.11 via mgsc-js2.0.0. No full local catalog run,
native WSL compiler run or audio roundtrip was performed. Tick-state comparisons
do not establish sample-exact source frequencies, phase or release tails.

Tests: seven pre-envelope structural tests, ten envelope tests (including both
public fixtures in ordinary/raw modes), twelve sync tests, public conversion
regression and four source-plan tests passed. Dumps link structural markers to
all contributing Segment indices; envelope IDs and performed-unit/loop-path columns
remain populated. Exact expansion is checked by SourceLoopPlan and the macro
projector separately. Source candidates/trees/projection and expanded/stored
envelope counts are retained with --dump-passes.

## Restored authored references

Both restored source MMLs compile with MGSC1.11. With LF-normalized text,
p52_arbl is9815 decoded
characters,23 macro definitions,14 software envelopes and84 physical bracket
loops with maximum lexical nesting6. contrail is5990 characters,9 macros,
6 software envelopes and62 bracket loops with lexical nesting4. These are
syntax statistics, not counts multiplied by macro calls or recovered musical
windows. The existing score-length auditor cannot fully parse either reference:
p52_arbl has unsupported macro/loop-exit syntax, and contrail includes an
unsupported multi-argument hardware-vibrato command.

The restored contrail.mml initially contained GitHub page HTML rather than plain
MML. The page's embedded rawLines supplied the actual source; an extracted copy
was inspected/compiled outside the repository. The user's original file was
not overwritten. The user subsequently replaced it with plain MML and moved
both references to their respective reference/ directories. The updated files
were checked again; both compile and retain the same syntax statistics.

The references show that authored structure includes named macros, deeper
loops/exits, software envelopes and vibrato/waveform-control recipes. Reversible
literal note repeats alone do not recover those high-level generators from
their expanded register trajectories. Exact recovery of reference loop windows
is not claimed. Future work on those abstractions should remain separate from
the current exact-repeat/envelope-order integration.

Private outputs, compile logs, source candidate/structure CSVs and comparison
JSON: Codex outputs/psg-scc-structure. The local comparison harness, extracted
reference copies and private source contents are not added to the repository.
