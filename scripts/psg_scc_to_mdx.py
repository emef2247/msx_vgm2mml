"""Tonal PSG/SCC -> OPM MDX with selectable PSG voice models, with inspectable evidence."""
import argparse
import csv
import shutil
import subprocess
import tempfile
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'py'), str(ROOT)]
from vgm_io import read_vgm_bytes, read_vgm_header
from vgm_timing import command_times
from vgm_reader import parse_vgm
from psg import build_segments as build_psg
from scc import build_segments as build_scc
from psg_scc_opm import project, verify_writes


def source_facts(raw):
    header = read_vgm_header(raw)
    clocks = [header['ay_clock_raw'], header['scc_clock_raw']]
    ay_type, ay_flags = header['ay_type'], header['ay_flags']
    if any(c & 0xc0000000 for c in clocks):
        raise ValueError('Dual chips and SCC variants are not implemented in this target')
    if clocks[0] and (ay_type != 0 or ay_flags not in (0, 1, 2, 3)):
        raise ValueError('Volume/pitch profile supports AY8910 legacy/single output flags only')
    end = 0
    silent_opll_writes = 0
    absent_scc_writes = 0
    for event in command_times(raw):
        cmd = event.command
        end = event.vgmticks + event.wait_samples
        if cmd in (0x61, 0x62, 0x63, 0x64, 0x66) or 0x70 <= cmd <= 0x7f:
            continue
        if cmd == 0xa0:
            if not clocks[0] or raw[event.address + 1] > 15:
                raise ValueError('Unsupported AY instance/register or missing clock')
        elif cmd == 0x51:
            reg, data = raw[event.address + 1:event.address + 3]
            if (0x20 <= reg <= 0x28 and data & 0x10) or (reg == 0x0e and data & 0x20 and data & 0x1f):
                raise ValueError('Active OPLL is not supported by the PSG/SCC OPM target')
            silent_opll_writes += 1
        elif cmd == 0xd2:
            port = raw[event.address + 1]
            if not clocks[1]:
                if port == 2 and raw[event.address + 3] & 15:
                    raise ValueError('SCC volume written without a clock')
                absent_scc_writes += 1
            if port not in (0, 1, 2, 3):
                raise ValueError('SCC test/variant/instance writes require further target support')
        else:
            raise ValueError(f'Unsupported source command in this prototype: {cmd:#x}')
    return dict(psg_clock=clocks[0], scc_clock=clocks[1], end_vgmticks=end,
                ay_type=ay_type, ay_flags=ay_flags, silent_opll_writes=silent_opll_writes, absent_scc_writes=absent_scc_writes)


def _convert(source, out, *, psg_gain=None, scc_gain=.125, title=None, psg_model='fm', pitch_policy=None):
    source, out = Path(source), Path(out)
    facts = source_facts(read_vgm_bytes(source))
    out.mkdir(parents=True, exist_ok=True)
    paths = parse_vgm(str(source), str(out), include_vgmticks=True, dump_loop=True)
    psg = build_psg(paths[2], str(out), stem=source.stem, dump_passes=True)
    scc = build_scc(paths[3], str(out), stem=source.stem, dump_passes=True)
    plan = project(psg, scc, psg_clock=facts['psg_clock'], scc_clock=facts['scc_clock'],
                   end_vgmticks=facts['end_vgmticks'], psg_gain=psg_gain, scc_gain=scc_gain,
                   psg_model=psg_model, pitch_policy=pitch_policy)
    plan.settings.update(ay_type=facts['ay_type'], ay_flags=facts['ay_flags'],
                         silent_opll_writes=facts['silent_opll_writes'], absent_scc_writes=facts['absent_scc_writes'])
    plan.dump(out, source.stem)
    mml = out / (source.stem + '.mdx.mml')
    mml.write_text(plan.render(title or source.stem + ' - PSG/SCC OPM (' + psg_model + ')'), encoding='utf-8')
    return mml, plan



def convert(source, out, *, psg_gain=None, scc_gain=.125, title=None, psg_model='fm', pitch_policy=None, dump_passes=True):
    """Keep native evidence on request; default standalone audit keeps all passes."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    if dump_passes:
        return _convert(source, out, psg_gain=psg_gain, scc_gain=scc_gain, title=title,
                        psg_model=psg_model, pitch_policy=pitch_policy)
    with tempfile.TemporaryDirectory(prefix='psg-scc-opm-') as temp:
        mml, plan = _convert(source, temp, psg_gain=psg_gain, scc_gain=scc_gain, title=title,
                        psg_model=psg_model, pitch_policy=pitch_policy)
        result = out / mml.name
        shutil.copyfile(mml, result)
    return result, plan


def compile_and_verify(generator, mml, plan, out, stem):
    # Imports also work when invoked by the repository's top-level entry point.
    from scripts.verify_opm_mdx_roundtrip import generate
    from opm_roundtrip import controls
    base = out / '_compiler_initialization'
    base.mkdir(exist_ok=True)
    initial = base / 'initialization.mml'
    initial.write_text('#title "Compiler initialization"\nA @t255 r%1\n', encoding='utf-8')
    init = controls(generate(generator.resolve(), initial, base, 'initialization'))
    if any(sample != 0 or reg == 8 for sample, reg, data in init):
        raise ValueError('Unexpected compiler initialization; comparison refused')
    actual = generate(generator.resolve(), mml, out, stem, max_ticks=max(2, plan.end_tick + 1))
    report = verify_writes(plan, controls(actual), init, actual.source_end_vgmticks)
    (out / (stem + '.verification.json')).write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    if not report['passed']:
        raise RuntimeError('Generated target controls did not survive the MDX roundtrip')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path, help='PSG/SCC VGM or directory to scan recursively')
    parser.add_argument('--outdir', type=Path, required=True)
    parser.add_argument('--psg-gain', type=float, default=None, help='PSG gain: default fm=1, additive=0.125')
    parser.add_argument('--psg-model', choices=['fm', 'additive'], default='fm',
                        help='PSG tone model (default: fm); SCC remains additive')
    parser.add_argument('--opm-pitch-policy', choices=['clamp', 'error'], default=None,
                        help='Range policy: default fm=clamp, additive=error')
    parser.add_argument('--scc-gain', type=float, default=.125)
    parser.add_argument('--generator', type=Path, help='External MDX compiler/player; retain MDX/VGM and verify')
    parser.add_argument('--comparison-dir', type=Path, help='Optional existing OPM VGM tree, matched by relative path')
    args = parser.parse_args()
    if not args.input.exists():
        parser.error('Input does not exist')
    if args.generator and not args.generator.is_file():
        parser.error('Generator does not exist')
    files = sorted(p for p in args.input.rglob('*') if p.suffix.lower() in ('.vgm', '.vgz')) if args.input.is_dir() else [args.input]
    if not files:
        parser.error('No VGM inputs found')
    args.outdir.mkdir(parents=True, exist_ok=True)
    results = []
    for source in files:
        relative = source.relative_to(args.input) if args.input.is_dir() else Path(source.name)
        out = args.outdir / relative.with_suffix('') if args.input.is_dir() else args.outdir
        row = dict(input=str(source), status='', detail='', mml='', mdx='', vgm='', comparison_vgm='')
        try:
            mml, plan = convert(source, out, psg_gain=args.psg_gain, scc_gain=args.scc_gain,
                                psg_model=args.psg_model, pitch_policy=args.opm_pitch_policy)
            row.update(status='mml_only', mml=str(mml))
            if args.generator:
                report = compile_and_verify(args.generator, mml, plan, out, source.stem)
                row.update(status='verified', mdx=str(out / (source.stem + '.mdx')),
                           vgm=str(out / (source.stem + '.vgm')),
                           detail=f"{report['expected_controls']} exact target controls; not acoustic equivalence")
            if args.comparison_dir:
                reference = args.comparison_dir / relative
                if reference.is_file():
                    target = out / (source.stem + '.vgm-conv.vgm')
                    shutil.copyfile(reference, target)
                    row['comparison_vgm'] = str(target)
        except ValueError as error:
            row.update(status='unsupported', detail=str(error))
        except subprocess.TimeoutExpired as error:
            row.update(status='timeout', detail=str(error))
        except (RuntimeError, OSError) as error:
            row.update(status='failed', detail=str(error))
        results.append(row)
        print(f"{relative}: {row['status']} {row['detail']}")
    (args.outdir / 'results.json').write_text(json.dumps(results, indent=2) + '\n', encoding='utf-8')
    with (args.outdir / 'results.csv').open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)
    if any(r['status'] not in ('verified', 'mml_only') for r in results):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
