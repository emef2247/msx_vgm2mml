# Batch VGM to MGS

Native `mgsc` on PATH is preferred; mgsc-js is not needed in that
case. The native CLI is invoked as `mgsc INPUT.mml OUTPUT.mgs`. Specify an
executable explicitly with `--mgsc /usr/local/bin/mgsc`.

```sh
python scripts/batch_vgm_to_mgs.py tests/fixtures/local_only/opll --outdir outputs/mgs
```

Success requires exit code zero AND a nonempty output MGS, because some native
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
Compilation alone needs no libkss dependency (`--skip-keyon-counts`). Input/output trees must be separate. The tool
checks that Node can load and initialize MGSC before any conversion. Missing
mgsc-js is an environment/setup error, not an MML compilation error. In WSL,
run the npm installation from this repository in WSL (a globally installed
package is not sufficient for the helper's module resolution).

The tool
recursively finds .vgm/.vgz files, retains their relative directories, and creates
a per-input directory containing generated MML, MGS on success, and convert.log
and compile.log. Existing MML/MGS for the same input in that output directory
are replaced on reruns. Source files are never modified.

results.csv and results.json list success, conversion_failed, buffer_error,
compile_failed, or process errors. Source-size errors are compile_failed and
their exact message remains in the log. Exit status is 1 if any input failed.
Failures do not stop later files. No allocation adjustment or music truncation
is performed. `--timeout` sets the per-stage timeout in seconds (default 300).
Timeouts are reported separately as `convert_timeout` or `compile_timeout`,
not as conversion exceptions or ordinary process errors. The stage log retains
partial stdout/stderr and the configured number of seconds. Later inputs still
run. A timed-out compiler's incomplete MGS is removed; intermediate MML remains
available for inspection. Increase the timeout for a slow but valid conversion
rather than reducing musical accuracy or limiting the source-loop structure.
MGS compilation does not prove playback equivalence.

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
Compilation `status` remains independent. `keyon_status` is `compared`,
`not_compiled`, `unavailable` (dependency failure), `timeout`, `error`, or `disabled`.
Unperformed comparisons have blank counts, never fabricated zeros.
Count differences do not make compilation unsuccessful; exit status is 1 when
conversion/compilation or an enabled comparison cannot complete.

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
included. Run `python -m unittest discover -s tests -p test_local_opll_catalog.py`.

`--normalize-lengths` forwards optional musical duration correction to each
conversion. It does not change the default or run conversion twice. Per-input
`convert.log` and `<stem>.normalization.json` report applied/unchanged status;
compiled MGS and KEYON comparison use that same output. See
[normalization behavior and limits](note_normalization.md).

## Compression comparison

The converter now enables structural PSG/SCC/OPLL loops and enhanced macros by default. PSG/SCC structure is built before selecting software envelopes. Pass `--legacy-loops --legacy-macros` to this batch script for the earlier compression. Use separate output directories when comparing. These switches do not reintroduce old channel-layout or encoding defects. Large inputs may need `--timeout 900` because enhanced candidate selection takes longer than the old compressor.

Old UTF-8 MGS titles are not repaired in place. Re-running conversion and compilation generates CP932 titles with the current pipeline.
