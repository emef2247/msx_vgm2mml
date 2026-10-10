# 2026-10-07: musical native OPM MDX MML rebuild

## Scope and source provenance

The user requested a musical MDX renderer based on the MGSDRV pipeline, rather
than treating a successful register/tied-note roundtrip as the output goal.
Native OPM state/Segments and the integrated CSV were already accepted and were
not redesigned. Musical interpretation, reversible source structure, target
compaction and external validation remain separate stages. No reference score
is read to choose notes, voices, tempo, title or phrases during conversion.

All 32 reference MML/MDX pairs match the original X68K collection byte-for-byte.
The original collection is `H:/_env/X68K/emu/x68000/images/MDX`. Arumana MMLs
are in its MML subdirectory; their MDX siblings are in the parent collection.
These are imported references, not vgm2mml-generated expectations.

Twelve missing input VGMs were generated directly from reference MDX using an
external soundlog driver and original PDX search paths. They are stored beside
their `reference/` directory under `tests/fixtures/local_only/opm`. Original
MML/MDX files are unchanged. Generated/private data remain outside git.

Missing inputs created: KMSM004, KMSM009, F_A01, FILC, POWERE, POWEROPEN,
FF4BAT1, FF4GORU, FF4LYDIA, FF4SIREN, RAY2C and ARMST5.
Five used named PDX files from the original collection: KMSM009, F_A01,
FF4BAT1, FF4SIREN and RAY2C. PCM exists in some source VGMs but is outside this
native OPM projection; the verifier now reports that scope explicitly.

## Implementation

- Key-to-KeyOff musical note units own all internal pitch/volume/control changes.
  Held controls no longer reject an entire note merely because its state changes.
- Inferred score clocks must preserve every observed boundary within the
  existing six-sample projection resolution and must not collapse positive
  intervals. All safe alternatives are reported; notation tie-breaks cannot
  waive a bad boundary. Source samples and event order remain in the passes.
- Uniform carrier attenuation becomes target volume only when all four TL
  values and source raw TL bytes can be reproduced. Reserved raw bits must not
  disappear through decoded-level inference; other edits remain explicit controls.
- Shared MGSDRV SourceLoopPlan/LoopStructure drives outer phrases and internal
  held/released trajectories before target setter/duration compaction.
- Unique-source separators and periodic-prefix closed forms preserve the full
  candidate catalog and selected tree. Tests compare these against the shared
  solver on 147 deterministic cases; there is no phrase-width/depth cap.
- The shared solver uses its already interned integer symbols for distinct-body
  checks instead of repeatedly hashing complete trajectories. Equality and
  choice order are unchanged. No elapsed-time improvement is asserted here.
- Same-tick post-Key tone/pitch edits cannot precede deferred MDX voice loading
  safely. They keep explicit ordered controls with a named reason; source
  Segments are not altered to make a note representation pass.
- Dump passes retain native evidence, musical units/full trajectories, voice
  definitions, source catalogs, fold decisions, flat/uncompacted MML and every
  compaction decision. Integrated CSV annotation streams rows instead of
  loading the complete native view again.
- structured is the new default; legacy and registers remain explicit options.
  No README, native reader, MGSDRV renderer or PSG/SCC-to-OPM model was changed.

## Validation

- 83 OPM/MDX automated checks and 8 shared-loop checks pass.
- All 38 public OPM inputs pass external MML -> MDX -> VGM -> Segment checks.
- All 32 imported reference inputs produce MML; 30 compile and pass
  external projected Key/state/time comparison. Two reach MDX offset capacity.
- Successful local cases contain 32,957 source channel attacks.
  Missing/extra channel attacks and operator Keys are zero; ordered projected
  edges and all source-known states match in every successful case.
- Loop expansion is separately checked against unlooped target tokens. These
  are behavioral checks, not acoustic equivalence or proof of original score
  recovery. Source timing projection differences remain separately reported.
- On 19 cases with existing old generated MML, character count is
  614,603 -> 139,483 (77.3% smaller). This is not a compiled-size score.
  Old artifacts were reused; a fresh legacy run was not substituted silently.

| Input stem | Old MML chars | New MML chars | New MDX bytes | Result |
|---|---:|---:|---:|---|
| ARMBS1 | 11054 | 4249 | 1866 | success |
| ARMBS2 | 54877 | 16262 | 7679 | success |
| ARMBSEN | 5049 | 2026 | 924 | success |
| ARMEND | 15269 | 3459 | 1488 | success |
| ARMOPN | 9839 | 3019 | 1473 | success |
| ARMOVER | 13662 | 6934 | 3270 | success |
| ARMST1 | 59743 | 20815 | 9343 | success |
| ARMST2 | 77227 | 27529 | 12605 | success |
| ARMST5 | — | 17901 | 8411 | success |
| ARMSTCR | 4484 | 2031 | 912 | success |
| ARM_7DCC | 3528 | 849 | 383 | success |
| FF4BAT1 | — | 103904 | 53796 | success |
| FF4GORU | — | 26979 | 13699 | success |
| FF4LYDIA | — | 31588 | 17123 | success |
| FF4SIREN | — | 27377 | 14567 | success |
| FF4WM1 | — | 151492 | — | compile_or_replay_failed |
| FILC | — | 93180 | 45630 | success |
| F_A01 | — | 4220 | 2107 | success |
| HYDS_01 | 10769 | 1352 | 619 | success |
| HYDS_02 | 5873 | 1177 | 585 | success |
| HYDS_03 | 5931 | 984 | 444 | success |
| HYDS_04 | 1144 | 485 | 207 | success |
| HYDS_05 | 13463 | 2126 | 831 | success |
| HYDS_06 | 6383 | 1499 | 812 | success |
| HYDS_07 | 6414 | 956 | 449 | success |
| KMSM004 | — | 83305 | 37948 | success |
| KMSM009 | — | 268659 | — | compile_or_replay_failed |
| POWERE | — | 103191 | 54607 | success |
| POWEROPEN | — | 15123 | 7558 | success |
| RAY2C | — | 132498 | 55474 | success |
| ST1 | 59740 | 20812 | 9340 | success |
| WARNOP | 250154 | 22919 | 10393 | success |

POWERE and FF4BAT1 exceeded the offset limit in the initial musical renderer.
Internal trajectory loops reduced them sufficiently to compile (54,607 and
53,796 bytes respectively), with unchanged projected Keys and known states.
FF4WM1 still fails at track 5 and KMSM009 at track 4 offset, maximum 0xfffe.
Their MML/trace/timing/compile diagnostics are retained; no events are removed
to force compilation. Further software LFO recovery/MDX representation work
is needed. Macros have not been added.

KMSM009 has 11,925 musical note units and long released control trajectories
(one released unit contains 9,796 retained controls). Its unrestricted source
search was expensive. Completed comparisons were reused after strictly
equivalent plan optimizations; no timing comparison between these runs is made.
The additional loop pass used cached immutable raw traces from the preceding
full conversion run, retaining source evidence paths in its timing report.

## Independent metadata evidence

External vampirefrog/mdxtools mdxdump was run on original reference MDX and
generated MDX for each successful case. Both outputs/stderr and parsed metadata
are retained. Multi-line titles and the title/PDX delimiter are handled without
treating header continuation text as music commands. No external implementation
was copied into the Python engine.

- 30/30 generated MDX title/tempo metadata agree with their generated MML.
- 23/30 original/generated encoded tempo-byte lists agree.
- 0 reference titles agree: these source VGMs have no GD3 track title; the
  renderer uses the filename. Original MDX titles are not copied from an oracle.
  Use --title explicitly when the desired title is known.
- Remaining tempo-list differences are explicit. A safe single-clock score
  can preserve the performance without reproducing original tempo changes or
  note-length choices. Automatic tempo-change recovery is not implemented.
- Original software-LFO/relative-volume command categories need not occur as
  identical opcodes in generated MDX. Their observed control trajectories are
  represented and checked, but the original command syntax is not recovered.
- Encoded command counts are not expanded musical note counts. PCM/PDX names
  are reported but their sound is outside this output target.

## Evidence locations and next scope

Windows scratch results: `C:\Users\ef110\Documents\Codex\2026-09-25\co\tmp\mdx-rebuild\outputs\reference-benchmark-musical`.
The source raw/state/integrated Segment evidence for cached inputs is under
`outputs/reference-benchmark/` in that scratch workspace, not replaced by
separate per-channel source files. Results include absolute evidence paths.
Successful per-stem folders contain generated MML, returned.mdx and returned.vgm
for listening. Public results are in the sibling `outputs/public-musical/`.
Provenance evidence is `outputs/reference-provenance.json`; generated input
logs/hashes are in `outputs/missing-vgm/`. None are intended for commit.

The installed native path is ready for user execution; see docs/opm_mdx.md.
Remaining work: the two offset failures; explicit tempo/LFO recovery; user
listening/MMDSP checks; later integration into the separate PSG/SCC target.
Do not insert artificial retriggers for graphical meters or rewrite native
CSV/state/timing to resemble a reference score. Reference selection is not an
oracle dependency. README should still not advertise OPM at this stage.
