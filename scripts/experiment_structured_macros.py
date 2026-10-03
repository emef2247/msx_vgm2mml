"""Reallocate macros in generated MML with its loop structure preserved."""
import argparse,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'py'))
from structured_macros import enhance_macros,expanded


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('input',type=Path)
    p.add_argument('--outdir',type=Path,required=True)
    p.add_argument('--mgsc-module',type=Path)
    a=p.parse_args(); a.outdir.mkdir(parents=True,exist_ok=True)
    text=a.input.read_text(encoding='cp932')
    output=a.outdir/a.input.name
    result=enhance_macros(text,dump_prefix=output.with_suffix(''))
    output.write_text(result,encoding='cp932',newline='\n')
    report=dict(input=str(a.input),output=str(output),before_characters=len(text),
                after_characters=len(result),saved_characters=len(text)-len(result),
                expanded_timed_commands_equal=expanded(text)==expanded(result))
    if a.mgsc_module:
        proc=subprocess.run(['node',str(ROOT/'scripts/compile_mgs.mjs'),str(output),
                             str(output.with_suffix('.mgs')),str(a.mgsc_module.resolve())],
                            capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=60)
        log=proc.stdout+proc.stderr
        (a.outdir/'compile.log').write_text(log,encoding='utf-8')
        report.update(compile_success=proc.returncode==0,buffer_error='buffer full' in log.lower())
    (a.outdir/'comparison.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))
    if report.get('compile_success') is False: raise SystemExit(1)

if __name__=='__main__': main()
