"""Compare envelope-first and source-loop-first conversion in separate trees."""
import argparse
import json
from pathlib import Path
import runpy
import sys
from functools import partial
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'py'))
import mml_envelopes
import opll_target
from pre_envelope_loops import LoopFirstEnvelopeBank, EnvelopeFirstStructuredBank
from mml_sync import analyze_mml, _leaves


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',type=Path)
    parser.add_argument('--outdir',type=Path,required=True)
    args=parser.parse_args()
    original=mml_envelopes.EnvelopeBank
    original_opll=opll_target.render
    results=[]
    expanded_tracks=[]
    try:
        for label,bank in [('current',original),('envelope-first',EnvelopeFirstStructuredBank),
                           ('loop-first',LoopFirstEnvelopeBank)]:
            mml_envelopes.EnvelopeBank=bank
            opll_target.render = (original_opll if label == 'current' else
                                  partial(original_opll, source_loops=True if label == 'loop-first' else 'after'))
            out=args.outdir/label
            sys.argv=['vgm2mml.py',str(args.input),'--outdir',str(out),'--dump-passes']
            runpy.run_path(str(ROOT/'vgm2mml.py'),run_name='__main__')
            raw=(out/(args.input.stem+'.mml')).read_bytes()
            text=raw.decode('cp932')
            expanded_tracks.append({ch: tuple((n.text, n.start, n.end) for n in _leaves(nodes))
                                    for ch, nodes in analyze_mml(text)[0].items()})
            results.append(dict(order=label,mml_bytes=len(raw),
                                envelope_definitions=sum(line.startswith('@e') for line in text.splitlines()),
                                source_plan_reports=len(list(out.glob('*.source_loops.csv'))),
                                normalization=False,
                                opll_software_envelope_selection='not applicable'))
    finally:
        mml_envelopes.EnvelopeBank=original
        opll_target.render=original_opll
    comparison=dict(runs=results, expanded_timed_tokens_equal=all(t == expanded_tracks[0] for t in expanded_tracks),
                    controlled_orders_mml_equal=(args.outdir/'envelope-first'/f'{args.input.stem}.mml').read_bytes() ==
                                                (args.outdir/'loop-first'/f'{args.input.stem}.mml').read_bytes(),
                    scope='Full final MML expanded through macros/loops; comparison between orders, not against input VGM')
    (args.outdir/'comparison.json').write_text(json.dumps(comparison,indent=2),encoding='utf-8')
    print(json.dumps(comparison,indent=2))

if __name__=='__main__':main()
