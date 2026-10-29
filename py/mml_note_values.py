"""Exact note-value spelling after score timing; never round musical time here."""
import json
from pathlib import Path
import re

from mml_sync import _parse,_text,_duration,_leaves,analyze_mml


def _meaning(text):
    result={}
    for channel,nodes in analyze_mml(text)[0].items():
        rows=[];tie=False
        for node in _leaves(nodes):
            if node.text=='&':tie=True;continue
            # Timed tokens are recognized from the parser, including plain c4.
            if node.end>node.start:
                pitch=re.match(r'[a-gr][+#-]?',node.text,re.I)
                pitch=pitch[0].lower() if pitch else node.text
                if rows and rows[-1][0]=='note' and rows[-1][1]==pitch and rows[-1][3]==node.start and (tie or pitch=='r'):
                    rows[-1][3]=node.end
                else:rows.append(['note',pitch,node.start,node.end,tie])
                tie=False
            else:rows.append(['control',node.text,node.start])
        result[channel]=rows
    return result


def decompose(text,*,dump_prefix=None):
    from structured_macros import parts_from,emit
    parts,rhythm=parts_from(text);rows=[]
    # Partial q ratios apply to the final fragment, so splitting them would
    # alter gate end. Generated score uses full gates; arbitrary q stays intact.
    partial_gate=bool(re.search(r'\bq[1-7]\b',text,re.I))
    tempo=re.search(r'^#tempo\s+(\d+)',text,re.M)
    minimum=max(1,int(tempo[1] if tempo else 225)//75)
    def notes(pitch,amount):
        output=[];rest=pitch.lower()=='r';first=True
        residue=amount%3
        tail=residue if residue>=minimum else residue+3 if residue else 0
        if amount<minimum or tail>amount:return [pitch+'%'+str(amount)]
        amount-=tail
        values={}
        for denominator in (1,2,4,8,16,32,64):
            for dots in ('','.', '..'):
                value=_duration(str(denominator),dots,48)
                if value<=192 and value%3==0:values[value]=str(denominator)+dots
        for length in sorted(values,reverse=True):
            count,amount=divmod(amount,length)
            if not count:continue
            token=pitch+values[length]
            if rest:
                while count:
                    chunk=min(count,255);output.extend([([token],chunk)] if chunk>1 else [token]);count-=chunk
            else:
                if first:output.append(token);count-=1;first=False
                while count:
                    chunk=min(count,255)
                    output.extend([(['&',token],chunk)] if chunk>1 else ['&',token]);count-=chunk
        if tail:
            if not rest and not first:output.append('&')
            output.append(pitch+'%'+str(tail))
        return output
    def walk(nodes,percussion,path):
        output=[]
        for index,node in enumerate(nodes):
            if isinstance(node,tuple):
                output.append((walk(node[0],percussion,path+(index,)),node[1]));continue
            match=re.fullmatch(r'([a-gr][+#-]?)(%\d+)(\.*)',node,re.I)
            if not match or percussion and match[1].lower()!='r' or partial_gate and match[1].lower()!='r':
                output.append(node);continue
            amount=_duration(match[2],match[3],48)
            rendered=notes(match[1],amount)
            output.extend(rendered)
            rows.append(dict(location=str(path+(index,)),original=node,steps=amount,
                             rendered=' '.join(map(_text,rendered)),residual_steps=amount%3))
        return output
    for index,part in enumerate(parts):
        if isinstance(part,list):part[1]=walk(part[1],rhythm and part[0]=='f',(index,))
    result=emit(parts,[])
    if _meaning(result)!=_meaning(text):raise AssertionError('Note-value decomposition changed gates or controls')
    if dump_prefix:
        prefix=Path(dump_prefix)
        Path(str(prefix)+'.note_values.before.mml').write_text(text,encoding='cp932',errors='replace')
        Path(str(prefix)+'.note_values.after.mml').write_text(result,encoding='cp932',errors='replace')
        Path(str(prefix)+'.note_values.json').write_text(json.dumps(dict(
            policy='exact decomposition to 1/64; terminal/protected residuals retained',
            partial_gate_protected=partial_gate,entries=rows),indent=2)+'\n',encoding='utf-8')
    return result
