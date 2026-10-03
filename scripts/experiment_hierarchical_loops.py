"""Run an isolated converter and compare loop strategies on emitted note units."""
import argparse
import csv
import json
from pathlib import Path
import runpy
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'py'))
import performed_patterns
from hierarchical_loops import experiment
from opll_note_units import NoteUnit


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',type=Path)
    parser.add_argument('--outdir',type=Path,required=True)
    parser.add_argument('--normalize-lengths',action='store_true')
    parser.add_argument('--max-phrase',type=int,default=128)
    parser.add_argument('--max-depth',type=int,default=3)
    args=parser.parse_args()
    args.outdir.mkdir(parents=True,exist_ok=True)
    original=performed_patterns.compress
    reports=[]
    def capture(units,commands,max_depth=2):
        baseline=original(units,commands,max_depth)
        if not units or not isinstance(units[0],NoteUnit):
            return baseline
        channel=len(reports)
        row=dict(channel_index=channel,units=len(units),plain_chars=len(' '.join(commands)),
                 existing_chars=len(baseline[0]))
        for strategy in ('immediate','retained'):
            start=time.perf_counter()
            text,loops=experiment(units,commands,strategy,args.max_phrase,args.max_depth)
            row[strategy+'_chars']=len(text)
            row[strategy+'_loops']=len(loops)
            row[strategy+'_depth']=max((r['depth'] for r in loops),default=0)
            row[strategy+'_seconds']=round(time.perf_counter()-start,3)
            (args.outdir/f'ch{channel}.{strategy}.mml').write_text(text+'\n',encoding='utf-8')
            (args.outdir/f'ch{channel}.{strategy}.loops.json').write_text(json.dumps(loops,indent=2),encoding='utf-8')
        source_matches=command_mismatches=0
        for start in range(len(units)):
            for width in range(1,min(args.max_phrase,(len(units)-start)//2)+1):
                left=tuple(u.validation_key for u in units[start:start+width])
                right=tuple(u.validation_key for u in units[start+width:start+2*width])
                if left == right:
                    source_matches+=1
                    command_mismatches+=commands[start:start+width] != commands[start+width:start+2*width]
        row['adjacent_equal_trajectory_candidates']=source_matches
        row['equal_trajectory_different_commands']=command_mismatches
        row['exact_expansion']=True
        reports.append(row)
        return baseline
    performed_patterns.compress=capture
    sys.argv=['vgm2mml.py',str(args.input),'--outdir',str(args.outdir/'baseline'),'--dump-passes']
    if args.normalize_lengths:
        sys.argv.append('--normalize-lengths')
    try:
        runpy.run_path(str(ROOT/'vgm2mml.py'),run_name='__main__')
    finally:
        performed_patterns.compress=original
    with (args.outdir/'comparison.csv').open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(reports[0]) if reports else ['channel_index'])
        writer.writeheader();writer.writerows(reports)
    print(json.dumps(reports,indent=2))

if __name__=='__main__':
    main()
