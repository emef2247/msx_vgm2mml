# OPM catalog roundtrip and listening artifacts (2026-10-04)

## Scope and method

The user requested public and local_only OPM roundtrip checks with generated
MDX MML, MDX and VGM retained for manual listening on real OPM hardware.
This run uses VGM -> native OpmSegment -> MDX register-control MML -> external
mmlx 0.2.0 MDX compilation -> soundlog 0.15.0 VGM replay -> native OpmSegment.
It does not implement a musical note/voice renderer or direct PSG/SCC mapping.

Commands (pass --generator when the helper was built outside its default path):

```bash
python scripts/verify_opm_mdx_roundtrip.py tests/fixtures/public/opm \
  --outdir outputs/opm/mdx_roundtrip/listening_20261004/public \
  --generator /path/to/mdx-fixture-generator
python scripts/verify_opm_mdx_roundtrip.py tests/fixtures/local_only/opm \
  --outdir outputs/opm/mdx_roundtrip/listening_20261004/local_only \
  --generator /path/to/mdx-fixture-generator
```

The public source scan excludes committed mdx_roundtrip replay expectations
and reference subdirectories. Both VGM/VGZ extensions and gzip-wrapped .vgm
files are supported. The source reader/Segment/target behavior is unchanged
by catalog classification; unsupported clock/variant/dual header facts are
checked before expensive state dumps. Input files are never modified.

## Measured outcome

| Catalog | Inputs | Roundtrip success | MDX compilation capacity failure | Unsupported target clock |
|---|---:|---:|---:|---:|
| public | 38 | 38 | 0 | 0 |
| local_only | 168 | 23 | 11 | 134 |
| total | 206 | 61 | 11 | 134 |

The 134 unsupported inputs declare a 3,579,580 Hz YM2151. The initial MDX
control target requires one 4,000,000 Hz YM2151; changing only a clock header
or replaying its KC/KF unchanged at 4 MHz would not preserve source pitch.
No retuning or misleading playable output is generated for these cases.
Native source analysis can handle these clocks; the limitation is this target.

All 11 compilation failures report:
`data inconsistency: MDX track 1 offset exceeds the maximum 0xfffe`.
They are reported as conversion_failed in this pipeline's aggregate report,
with compiler output identifying the external MDX serialization stage.
Their MML and native/target evidence are retained, but no MDX/VGM is claimed.
This is a limitation of the current uncompressed single-conductor control
representation; no controls/tail are discarded to satisfy the file format.
Detailed private case paths stay in ignored generated results/local notes.

| Successful catalog totals | public | local_only |
|---|---:|---:|
| Retained source/replayed controls | 8,572 | 59,358 |
| Channel attacks | 357 | 9,910 |
| Operator KeyOns | 1,377 | 39,640 |
| Operator KeyOffs | 1,208 | 39,540 |
| Known-state mismatches | 0 | 0 |
| Missing/extra attacks, operator KeyOns/Offs (each) | 0 | 0 |
| Max timing difference from source (44100 Hz samples) | 6 | 6 |
| Max timing difference from projected target samples | 0 | 0 |
| Positive source intervals sharing a target tick | 363 | 4,024 |

Counts apply to successful cases, not to unsupported/failed inputs. Exact
retained register/data order and source-known decoded/raw states match at
each control. Same-time writes and Key pulses are not removed. Native
nonchanging writes omitted from Segments remain in raw/state CSVs.

Six VGM samples are about 0.136 ms. Absolute MDX @t255 quantization does not
accumulate gap errors; collapsed target times retain source control order.
These results establish control/state preservation, not measured waveform,
LFO/noise/envelope-phase equality or real-hardware audio equivalence.
VGM song loops cover the first traversal. Non-OPM chips/PDX are outside scope.

## Retained listening material and diagnostics

All artifacts are under outputs/opm/mdx_roundtrip/listening_20261004/:

- public/ and local_only/: native traces/Segments, target controls/timing,
  <stem>.mdx.mml, returned.mdx, returned.vgm, returned Segment CSVs,
  returned.compile.log and per-case comparison.json.
- results.csv/results.json in each catalog: progress saved after each input,
  with absolute paths for files that actually exist.
- conversion.log for every failed/unsupported input; timeout stdout/stderr
  is retained too. The external helper now writes a compiled MDX before
  playback, so it survives a later player failure.
- listen/public/ and listen/local_only/: byte-identical copies of successful
  <stem>.mdx.mml, <stem>.mdx and <stem>.vgm, grouped by original source folders.
  All 183 copied files were verified against the original artifact hashes.
- listening_index.csv: all 206 inputs with status, error and listening paths;
  UTF-8 BOM helps desktop CSV inspection.
- summary.json and listen/README.txt: aggregate counts and listening guidance.

Generated/private music and diagnostic CSVs remain ignored and are not
committed. The listening copies are a convenience for this run; the verifier
retains its full evidence directly and does not require the copy step.

## Automated checks and next boundaries

All 35 OPM unit tests passed, including expected-replay scan exclusions,
gzip clock preflight, unsupported-target classification before analysis,
retained timeout stdout/stderr, negative state/Key/timing comparisons and
existing public Segment/target evidence. The external Rust helper rebuilt
offline with the pinned lockfile.

The next independent work items are clock-aware target conversion and MDX
capacity reduction through a readable/compressed note/voice representation.
Do not weaken state/Key comparisons, change source Segments, invent attacks
at TL changes or silently truncate long tracks to make these cases pass.
