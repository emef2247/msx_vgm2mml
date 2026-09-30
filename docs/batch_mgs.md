# Batch VGM to MGS

Native `mgsc` on PATH is preferred; Node.js and mgsc-js are not needed in that
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
No libkss dependency is needed. Input/output trees must be separate. The tool
checks that Node can load and initialize MGSC before any conversion. Missing
mgsc-js is an environment/setup error, not an MML compilation error. In WSL,
run the npm installation from this repository in WSL (a globally installed
package is not sufficient for the helper's module resolution).

The tool
recursively finds .vgm files, retains their relative directories, and creates
a per-input directory containing generated MML, MGS on success, and convert.log
and compile.log. Existing MML/MGS for the same input in that output directory
are replaced on reruns. Source files are never modified.

results.csv and results.json list success, conversion_failed, buffer_error,
compile_failed, or process errors. Source-size errors are compile_failed and
their exact message remains in the log. Exit status is 1 if any input failed.
Failures do not stop later files. No allocation adjustment or music truncation
is performed. `--timeout` sets the per-stage timeout in seconds (default 300).
MGS compilation does not prove playback equivalence.

Optional conversion regressions cover WBIII01..14, ThBSMS01..05, YsSMS01..20,
and Alest201..217. Missing local files skip individually; private data is not
included. Run `python -m unittest discover -s tests -p test_local_opll_catalog.py`.
