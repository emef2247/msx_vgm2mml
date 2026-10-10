"""Independent reference/generated MDX audit using external mdxtools mdxdump.

This checks metadata and command categories, not original score recovery.
The converter never reads a reference MDX/MML to choose its output.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import subprocess


def inspect_mdx(tool, source, output):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        run = subprocess.run([str(tool), str(source)], capture_output=True, timeout=60)
    except subprocess.TimeoutExpired as error:
        output.write_bytes(error.stdout or b'')
        output.with_suffix('.stderr.txt').write_bytes((error.stderr or b'')+b'\nmdxdump exceeded 60 seconds\n')
        raise RuntimeError('External mdxdump exceeded 60 seconds; partial dump/stderr retained') from error
    output.write_bytes(run.stdout)
    output.with_suffix('.stderr.txt').write_bytes(run.stderr)
    if run.returncode:
        raise RuntimeError(f'mdxdump failed ({run.returncode}): {run.stderr.decode("utf-8",errors="replace")}')
    # mdxdump prints the original Shift-JIS title bytes unchanged.
    text=run.stdout.decode('cp932',errors='replace')
    counts=Counter()
    # MDX titles may span lines. This tool's C string output can also run past
    # the title terminator into the PDX name; keep only the title before 0x1a.
    heading=re.search(r'\Atitle (.*?)\r?\npdxfile ([^\r\n]*)',text,re.S)
    if not heading:
        raise ValueError('Unrecognized external MDX metadata heading')
    title=heading[1].split('\x1a',1)[0].rstrip('\r\n')
    pdx=heading[2]
    tempos=[]
    text=text[heading.end():]
    for line in text.splitlines():
        if line.startswith('SetTempo '):
            match=re.fullmatch(r'SetTempo (\d+) BPM \((\d+)\)',line)
            if not match: raise ValueError('Unrecognized external tempo line')
            tempos.append(int(match[2]));counts['SetTempo']+=1
        elif line:
            counts[line.split()[0]]+=1
    return dict(title=title,pdx=pdx,tempo_bytes=tempos,command_counts=dict(counts))


def audit(tool, reference, generated, mml, outdir):
    outdir=Path(outdir)
    a=inspect_mdx(tool,reference,outdir/'reference.mdxdump.txt')
    b=inspect_mdx(tool,generated,outdir/'generated.mdxdump.txt')
    text=Path(mml).read_text(encoding='utf-8')
    title=re.search(r'^#title\s+"(.*)"\s*$',text,re.M|re.I)
    normalize=lambda s:' '.join(s.split()).replace('"',"'")
    result=dict(reference=a,generated=b,
                generated_mml_title=title[1] if title else None,
                title_matches_reference=bool(title and normalize(a['title'])==normalize(title[1])),
                compiled_title_matches_mml=bool(title and normalize(b['title'])==normalize(title[1])),
                tempo_bytes_match_reference=a['tempo_bytes']==b['tempo_bytes'],
                generated_tempo_visible_in_mml=all(f'@t{tempo}' in text for tempo in b['tempo_bytes']),
                reference_command_categories_missing_from_mdx=sorted(set(a['command_counts'])-set(b['command_counts'])),
                scope='metadata and encoded command categories; equivalent lower-level controls may represent a missing category')
    (outdir/'metadata.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reference',type=Path)
    parser.add_argument('generated',type=Path)
    parser.add_argument('mml',type=Path)
    parser.add_argument('--mdxdump',type=Path,required=True)
    parser.add_argument('--outdir',type=Path,required=True)
    args=parser.parse_args()
    result=audit(args.mdxdump,args.reference,args.generated,args.mml,args.outdir)
    print(json.dumps(result,indent=2,ensure_ascii=False))


if __name__=='__main__': main()
