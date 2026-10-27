"""Whitespace-only presentation of MGSDRV track repeats.

Retain the channel designator on every physical score line. Repeat depth is
carried across sync comments; closing brackets do not force a line break.
Definitions, allocation blocks and comments keep their original order.
"""
import re


def format_mml_loops(text, width=110, indent=2):
    output=[];depths={};pending=[];channel=None;level=0;brace_depth=0

    def flush():
        if pending:
            output.append(channel+' '+' '*(level*indent)+' '.join(pending))
            pending.clear()

    for line in text.splitlines():
        code,separator,comment=line.partition(';')
        match=re.fullmatch(r'([1-9a-hA-H])\s+(.*)',code) if brace_depth==0 else None
        if match is None:
            flush();channel=None
            output.append(line)
        else:
            current,body=match[1],match[2]
            if current!=channel:
                flush();channel=current
            depth=depths.get(current,0)
            for word in re.findall(r'\[|\]\s*\d*|[^\s\[\]]+',body):
                if word=='[':
                    flush();level=depth;pending.append(word);depth+=1
                    continue
                if not pending:level=depth
                word=re.sub(r'\s+','',word) if word.startswith(']') else word
                if pending and len(current)+1+level*indent+sum(len(x)+1 for x in pending)+len(word)>width:
                    flush();level=depth
                pending.append(word)
                if word.startswith(']'):depth=max(0,depth-1)
            depths[current]=depth
            if separator:
                flush();output.append(';'+comment)
        brace_depth+=code.count('{')-code.count('}')
    flush()
    return '\n'.join(output)+'\n'
