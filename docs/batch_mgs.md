# Batch VGM to MGS

## Export entry with explicit default thresholds

`export_mgs.py` uses the same batch implementation and diagnostics, with
`--fm-state-ms 24` and `--normalization-ms 8` as its defaults:

```sh
python scripts/export_mgs.py INPUT_DIR --outdir OUTPUT_DIR --force
```

A single VGM/VGZ file is also accepted. Either threshold can be overridden, for
example `--fm-state-ms 4 --normalization-ms 16`. These defaults request optional
normalization; the converter still reports `unchanged` if a safe OPLL-anchored
projection cannot be found. They do not imply PSG/SCC envelope filtering.

The existing `batch_vgm_to_mgs.py` retains its conversion defaults. Both entries
use the same output layout: final MML/MGS directly in each package `tracks/`, and reports/work files
under package `_diagnostics/<stem>/`. The export entry delegates
conversion, compilation, omission rules and report creation to that runner. See
[output layout](output_layout.md) for exact paths, PSG mode directories and reruns. Other options, including `--skip-keyon-counts`, retain
the same meaning; optional key-on verification is enabled unless skipped.

Both entry points preserve `INDIR`-relative parent directories under `OUTDIR`.
For example, `INDIR/vgmrips.net/SALAMD/SONG01.vgm` produces
`OUTDIR/vgmrips.net/SALAMD/tracks/SONG01.mml` and `.mgs`. Omit `--outdir`
to use `INDIR/vgmrips.net/SALAMD/` as the package root instead.

Native `mgsc` on PATH is preferred; mgsc-js is not needed in that
case. The native CLI is invoked as `mgsc INPUT.mml OUTPUT.mgs`. Specify an
executable explicitly with `--mgsc /usr/local/bin/mgsc`.

```sh
python scripts/batch_vgm_to_mgs.py tests/fixtures/local_only/opll --outdir outputs/mgs
```

Conversion requires exit code zero and a nonempty current-run MML.
Compilation requires exit code zero AND a nonempty output MGS, because some native
builds return zero on MML errors. Failure stdout/stderr are printed and logged.
Generated MML remains available for inspection.

When no native compiler is found, the existing JS fallback remains available
for Windows and msxplay compatibility. An explicit `--mgsc-module` selects JS
unless `--mgsc` is also specified. Install Node.js and the optional dependency:

```sh
npm install --no-save --package-lock=false mgsc-js@2.0.0
python scripts/batch_vgm_to_mgs.py tests/fixtures/local_only/opll --outdir outputs/mgs
```

Alternatively pass `--mgsc-module /absolute/path/to/mgsc-js/dist/index.js`.
Compilation alone needs no libkss dependency (`--skip-keyon-counts`). An explicit
output tree must be separate from input. If `--outdir` is omitted, final MML/MGS
go into `tracks/` beside each source VGM. Diagnostics are under each package
`_diagnostics/<stem>/`; the source parent is the package root for a single file. Adjacent reruns exclude generated diagnostic
and PSG-mode directories from input discovery. The tool
checks that Node can load and initialize MGSC before any conversion. Missing
mgsc-js is an environment/setup error, not an MML compilation error. In WSL,
run the npm installation from this repository in WSL (a globally installed
package is not sufficient for the helper's module resolution).

The tool recursively finds .vgm/.vgz files and preserves relative parent
directories. Final products are `<out>/<relative-parent>/tracks/<stem>.mml` and `.mgs`;
there is no extra per-song listening directory. Workspace, logs and sidecars go
to `<out>/<relative-parent>/_diagnostics/<stem>/`. Each package includes staged
originals in `_source_inputs/`, a listening manifest, and package-relative results.
PSG-only modes add `psg_melody/` or `psg_rhythm/` before the relative parent. Source files are
never modified. Reruns replace unchanged products recorded by the publication
manifest; edited or unowned files cause an explicit collision error. Failed reruns
retain earlier owned listening files and report the latest failure separately.

`_diagnostics/results.csv` and `results.json` are updated after every input (under
the mode branch for PSG solo runs), retaining completed
progress if a later input is interrupted. Primary statuses are `success`,
`conversion_failed`, and `compilation_failed`. `stage` and `error_code` distinguish
conversion errors, compiler buffer errors, missing output, process errors and
timeouts. `legacy_status` retains the earlier classification where applicable.
The console prints `input: status: detail`, followed by a final exported count.
Failures do not stop later inputs. No allocation adjustment, automatic retry or
music truncation is performed. `--timeout` sets the per-stage timeout in seconds
(default 1200). A timeout retains partial stdout/stderr. A failed compiler's
incomplete MGS is removed; intermediate MML remains available for inspection.
MGS compilation does not prove playback equivalence.

Each diagnostic input folder contains `report.json` and `report.txt`, recording effective
options, stage commands, output paths, error details and raw log paths.
Normalization and FM state sidecars are embedded under `summaries`; CSV/JSON rows
also expose `normalization_status`, `normalization_reason`, `normalization_ms` and
`fm_state_ms`, so requested settings can be distinguished from actual application. Reruns
replace only known generated MML/MGS, reports, stage logs, normalization and force
sidecars for that input; unrelated files and directories are preserved. A single
`.vgm` or `.vgz` file can be supplied instead of a directory.

## Shared conversion options

`--fm-state-ms` forwards the internal OPLL state threshold (default 1 ms).
`--normalization-ms` forwards the duration normalization threshold (default 8 ms)
and enables normalization; an explicit `--fm-state-ms` also enables it.
`--normalize-lengths` enables it at its default thresholds.
Normalization remains opt-in for the MSX converter. These values control different
passes and are recorded separately. `--dump-passes` retains inspectable conversion
passes. Invalid thresholds and timeouts are rejected before setup or output changes.

`--force` enables only the converter's documented target omission rules. When a
`<stem>.mgs.force.json` is produced, the console and input report show its omission
count and details path. It does not bypass malformed input, compiler buffer limits,
missing dependencies, or timeouts. See the converter's force documentation for the
allowed rules; successful compilation alone is not proof of equivalent playback.

## Integrated OPLL key-on counts

By default each successfully compiled MGS is exported to
`<stem>.roundtrip.vgm` with libkss and compared against its source VGM.
Neither VGM-to-MML conversion nor MGS compilation is repeated for this check.
Install the optional playback dependency in the repository:

```sh
npm install --no-save --package-lock=false libkss-js
python scripts/batch_vgm_to_mgs.py tests/fixtures/local_only/opll --outdir outputs/mgs
```

Alternatively use `--libkss-module /absolute/path/to/libkss-js/dist/index.js`.
Node.js is needed for playback even when using native MGSC.
Use `--skip-keyon-counts` for the previous conversion/compilation-only workflow.

`results.csv` and `results.json` also contain `reference_keyon`, `actual_keyon`,
`missing_keyon`, `extra_keyon`, `keyon_status`, and `keyon_error`.
Compilation `status` remains independent. `keyon_status` is `compared`, `mismatch`,
`selection_only` (PSG solo export; native OPLL equality is not applicable),
`not_compiled`, `unavailable` (dependency failure), `timeout`, `error`, or `disabled`.
Unperformed comparisons have blank counts, never fabricated zeros.
Count differences do not make compilation unsuccessful; exit status is 1 when
conversion/compilation fails, an enabled comparison cannot complete, or ordinary
melodic counts mismatch. Successful solo export uses `selection_only`.

`keyon_setup.log` records playback setup. Each successful export retains the
VGM, `keyon.log`, and a `keyon/` folder with both sides' traces, key edges and
summary JSON. Segment reconstruction is omitted in this batch count-only check;
the standalone comparison command still supports detailed Segment dumps.

Playback uses one pass (`loop: 1`), with a safety duration of the source header's
total samples plus 25% and two seconds. A zero source duration or an export
reaching the duration limit is reported as incomplete instead of supplying
misleading counts. A timeout/error affects that comparison only; later inputs
still run. See [key-on count semantics](opll_keyon_counts.md).

Optional conversion regressions cover WBIII01..14, ThBSMS01..05, YsSMS01..20,
and Alest201..217. Missing local files skip individually; private data is not
included. Run `python -m unittest discover -s tests/script -p test_local_opll_catalog.py`.

`--normalize-lengths` forwards optional musical duration correction to each
conversion. It does not change the default or run conversion twice. Per-input
`convert.log` and `<stem>.normalization.json` report applied/unchanged status;
compiled MGS and KEYON comparison use that same output. See
[normalization behavior and limits](note_normalization.md).

## Compression comparison

The converter now enables structural PSG/SCC/OPLL loops and enhanced macros by default. PSG/SCC structure is built before selecting software envelopes. Pass `--legacy-loops --legacy-macros` to this batch script for the earlier compression. Use separate output directories when comparing. These switches do not reintroduce old channel-layout or encoding defects. Large inputs may need `--timeout 900` because enhanced candidate selection takes longer than the old compressor.

Old UTF-8 MGS titles are not repaired in place. Re-running conversion and compilation generates CP932 titles with the current pipeline.

## Tool licenses

The Python converter is MIT-licensed. MGSC/mgsc-js and libkss-js/libkss have
ISC wrapper/library terms; their embedded MSX compiler/driver materials retain
separate terms. MGSDRV's official distribution instructions require preserving
the original archive contents. These dependencies are obtained separately;
this repository does not vendor their binaries. See
[third-party notices](../THIRD_PARTY_NOTICES.md) for checked versions, exact
notices, source links and redistribution scope.

## Optional inferred OPLL drums

Use `--enhance-drums` to retain PSG/SCC and add an inferred OPLL rhythm part.
This experimental option is off by default. Candidates and target decisions
are saved as `.drums.*` CSV/JSON reports. Existing OPLL melody/rhythm has priority.
See [drum enhancement](drum_enhancement.md) for classification and timing limits.

## Playback validation and setup termination

The generated definition allocation includes the stream's terminating byte.
A successful MGSC compile alone cannot detect the historical missing-terminator
silence. See [definition storage and playback checks](mgs_definition_storage.md).
When OPLL counts differ, batch keeps the compilation result but records
`keyon_status=mismatch`, prints the differences and causes export to exit nonzero.
Matching counts remain narrower evidence than audio or full musical equivalence.
