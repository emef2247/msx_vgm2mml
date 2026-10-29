"""Whitespace-only presentation of MGSDRV track repeats.

Retain the channel designator on every physical score line. Repeat depth is
carried across sync comments. Leaf repeats close inline; parent repeats close
at their opening indentation. Every closure ends its physical score line.
Definitions, allocation blocks and comments keep their original order.
"""
import re


def format_mml_loops(text, width=110, indent=2):
    output=[];stacks={};pending=[];channel=None;level=0;brace_depth=0

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
            stack=stacks.setdefault(current,[])
            depth=len(stack)
            for word in re.findall(r'\[|\]\s*\d*|[^\s\[\]]+',body):
                if word=='[':
                    if stack:stack[-1]=True
                    flush();level=depth;pending.append(word);depth+=1
                    stack.append(False)
                    continue
                if word.startswith(']'):
                    word=re.sub(r'\s+','',word)
                    parent=stack.pop() if stack else False
                    depth=len(stack)
                    if parent:
                        flush();level=depth
                    elif not pending:
                        level=depth
                    pending.append(word)
                    flush()
                    continue
                if not pending:level=depth
                if pending and len(current)+1+level*indent+sum(len(x)+1 for x in pending)+len(word)>width:
                    flush();level=depth
                pending.append(word)
            if separator:
                flush();output.append(';'+comment)
        brace_depth+=code.count('{')-code.count('}')
    flush()
    return '\n'.join(output)+'\n'
