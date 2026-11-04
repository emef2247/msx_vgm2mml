"""Export OPN2 (YM2612) VGMs to dual-cartridge target VGMs.

The FM part is projected to YM2151 (OPM) at the MSX cartridge clock
3.579545 MHz and the two DCSG chips to the MSX PSG (AY) and the OPNA
Sound Cartridge's SSG section, all in one ``<stem>.target.vgm`` for
playback on the two cartridges (e.g. via MAmidiMEmo's VGM player and
a VSIF dongle). The DAC lane (S4: OPNA ADPCM-B) is inventoried in
each song's summary JSON as deferred, not dropped.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'py'))
from opn2_target_vgm import convert


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument('input', type=Path, help='VGM/VGZ file or recursive input directory')
    result.add_argument('--outdir', type=Path, help='Output root (default: beside the source)')
    result.add_argument('--force', action='store_true',
                        help='Project through gated source features (CSM, CH3 special, '
                             'unknown register effects) with the losses recorded')
    return result


def _inputs(path):
    if path.is_file():
        return [path]
    return sorted(p for p in path.rglob('*') if p.suffix.lower() in ('.vgm', '.vgz'))


def main():
    args = parser().parse_args()
    root = args.outdir or (args.input.parent if args.input.is_file() else args.input)
    root.mkdir(parents=True, exist_ok=True)
    results = []
    for source in _inputs(args.input):
        folder = root / source.stem
        try:
            summary = convert(source, folder, force=args.force)
            summary['status'] = 'success'
            print(f"{source.name}: {summary['target_writes']} target writes "
                  f"(OPM {summary['opm_writes']} + DCSG {summary['dcsg_writes']}), "
                  f"losses={summary['losses']}, deferred={list(summary['deferred'])}")
        except Exception as error:
            summary = dict(source=str(source), status='conversion_failed',
                           detail=str(error), error_type=type(error).__name__)
            print(f"{source.name}: FAILED {type(error).__name__}: {error}", file=sys.stderr)
        results.append(summary)
    (root / 'report.json').write_text(json.dumps(results, indent=2) + '\n', encoding='utf-8')
    return 1 if any(r['status'] != 'success' for r in results) else 0


if __name__ == '__main__':
    raise SystemExit(main())
