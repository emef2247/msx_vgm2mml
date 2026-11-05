"""Export OPN2 (YM2612) VGMs to MSX cartridge target VGMs.

``--target`` selects the cartridge composition: ``makoto``
(default) plays everything on the OPNA Sound Cartridge (FM on
its FM section, DCSG split between the MSX PSG and the OPNA SSG,
DAC on OPNA ADPCM-B); ``sfg01`` projects the FM part to YM2151
(OPM) at the MSX cartridge clock 3.579545 MHz and leaves SSG +
ADPCM-B to the OPNA cartridge. ``--layered`` additionally emits
a target whose FM part sounds on both FM sections at once.
``--dac y8950`` reroutes the DAC lane to an MSX-AUDIO (Y8950)
Delta-T unit instead of the OPNA's ADPCM-B.
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
    result.add_argument('--layered', action='store_true',
                        help='Also emit <stem>.layer.target.vgm: the FM part layered '
                             'onto both FM sections (OPM and OPNA) at once '
                             '(FM only; the plain target is unchanged)')
    result.add_argument('--target', choices=('makoto', 'sfg01'), default='makoto',
                        help='Cartridge composition of the target VGM: makoto = OPNA '
                             'Sound Cartridge alone (default), sfg01 = FM on the OPM '
                             'cartridge with SSG + ADPCM-B on the OPNA cartridge')
    result.add_argument('--dac', choices=('opna', 'y8950'), default='opna',
                        help='DAC lane destination: opna = OPNA ADPCM-B (default), '
                             'y8950 = MSX-AUDIO (Y8950) Delta-T unit '
                             '(with --layered the DAC lane always goes to the OPNA)')
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
            summary = convert(source, folder, force=args.force,
                              layered=args.layered, target=args.target,
                              dac=args.dac)
            summary['status'] = 'success'
            print(f"{source.name}: success")
        except Exception as error:
            summary = dict(source=str(source), status='conversion_failed',
                           detail=str(error), error_type=type(error).__name__)
            print(f"{source.name}: FAILED {type(error).__name__}: {error}", file=sys.stderr)
        results.append(summary)
    (root / 'report.json').write_text(json.dumps(results, indent=2) + '\n', encoding='utf-8')
    return 1 if any(r['status'] != 'success' for r in results) else 0


if __name__ == '__main__':
    raise SystemExit(main())
