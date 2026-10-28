"""Exact experimental macro search at every level of a finite loop tree."""
from collections import defaultdict
from bisect import bisect_right
import csv
import json
from pathlib import Path
import re
import textwrap
from mml_macros import compress_macros
from mml_sync import _parse, _text, analyze_mml, _leaves
from mml_relative_state import normalize, relative_body, compact_callers, signature
from mml_macro_phrases import prepare as prepare_phrases, contexts, summaries, extend, classify


def expanded(text):
    return signature(text)


def parts_from(text):
    definitions=dict(re.findall(r'^\*(\d+)\s*=\s*\{([^}]*)\}\s*$',text,re.M))
    def expand(body,stack=()):
        def call(m):
            if m[1] in stack or m[1] not in definitions:
                raise ValueError('Undefined or recursive macro')
            return expand(definitions[m[1]],stack+(m[1],))
        return re.sub(r'\*(\d+)\b',call,body)
    plain=re.sub(r'^\*\d+\s*=\s*\{[^}]*\}\s*\n?','',text,flags=re.M)
    rhythm=bool(re.search(r'^#opll_mode\s+1\b',text,re.M))
    parts=[]
    for line in plain.splitlines():
        m=re.fullmatch(r'([1-9a-h])\s+(.*)',line,re.I)
        if not m:
            parts.append(line)
            continue
        ch,body=m[1].lower(),expand(m[2])
        if parts and isinstance(parts[-1],list) and parts[-1][0]==ch:
            parts[-1][1]+=' '+body
        else:
            parts.append([ch,body])
    for p in parts:
        if isinstance(p,list):
            p[1]=_parse(p[1],rhythm=rhythm and p[0]=='f')
    return parts,rhythm


def locations(parts,rhythm):
    def walk(nodes,path,grammar):
        yield nodes,path,grammar
        for i,n in enumerate(nodes):
            if isinstance(n,tuple):
                yield from walk(n[0],path+(i,),grammar)
    for i,p in enumerate(parts):
        if isinstance(p,list):
            yield from walk(p[1],(i,),rhythm and p[0]=='f')


def emit(parts,definitions):
    lines=[]; inserted=False
    for p in parts:
        if isinstance(p,str):
            lines.append(p); continue
        if not inserted:
            # MGSC misreads sufficiently long physical definition lines.
            # Whitespace inside braces can span lines without changing tokens.
            for definition in definitions:
                lines.extend(textwrap.wrap(definition, width=120,
                    break_long_words=False, break_on_hyphens=False))
            inserted=True
        ch,nodes=p; line=ch+' '
        for word in ' '.join(map(_text,nodes)).split():
            if len(line)+len(word)+1>120:
                lines.append(line.rstrip()); line=ch+' '
            line+=word+' '
        lines.append(line.rstrip())
    return '\n'.join(lines)+'\n'


def select(text,limit,width,first_rank):
    parts,rhythm=parts_from(text)
    definitions=[]; audit=[]
    for number in range(limit):
        candidates=defaultdict(list)
        locs=list(locations(parts,rhythm))
        for loc,(nodes,path,grammar) in enumerate(locs):
            context=contexts(nodes,grammar)
            node_shapes=summaries(nodes,grammar)
            words=list(map(_text,nodes))
            lengths=list(map(len,words))
            has_macro=['*' in word for word in words]
            has_absolute=[not relative_body([word]) for word in words]
            for start in range(len(words)):
                if words[start]=='&' or has_macro[start]: continue
                body_length=0
                stats=(0,0,0,None,context[0][start],False)
                for size in range(1,min(width,len(words)-start)+1):
                    stop=start+size
                    body_length+=lengths[stop-1]+(size>1)
                    if body_length>512 or has_macro[stop-1] or has_absolute[stop-1]: break
                    stats=extend(stats,node_shapes[stop-1][int(stats[4])])
                    if stats[3] is True:break
                    if words[stop-1]=='&' or (stop<len(words) and words[stop]=='&'): continue
                    seq=tuple(words[start:stop])
                    category=classify(stats,context[1][stop],root=len(path)==1,at_end=stop==len(nodes))
                    if not category:continue
                    candidates[(grammar,category,seq)].append((loc,start))
        ranked=[]; ref=f'*{number}'
        for (grammar,category,seq),positions in candidates.items():
            body=' '.join(seq)
            # Even accepting overlapping occurrences cannot save enough here.
            # This exact upper bound avoids costly ancestry checks, not candidates.
            if len(positions)<2 or len(positions)*(len(body)-len(ref))-len(f'{ref} = {{ {body} }}\n')<=0:
                continue
            selected=[]; ends={}; occupied=defaultdict(list)
            for loc,start in sorted(positions,key=lambda p:(len(locs[p[0]][1]),p)):
                path=locs[loc][1]
                if start<ends.get(loc,0): continue
                # Parent replacements subsume child occurrences; never select both.
                covered = False
                for depth in range(1, len(path)):
                    starts = occupied.get(path[:depth], ())
                    at = path[depth]
                    index = bisect_right(starts, at) - 1
                    if index >= 0 and at < starts[index] + len(seq):
                        covered = True
                        break
                if covered: continue
                selected.append((loc,start)); ends[loc]=start+len(seq)
                occupied[path].append(start)
            saving=len(selected)*(len(body)-len(ref))-len(f'{ref} = {{ {body} }}\n')
            if len(selected)>1 and saving>0:
                ranked.append((category,saving,seq,selected,grammar))
        if not ranked: break
        ranked.sort(key=lambda r:(-r[0],-r[1],r[2]))
        ranked=[row for row in ranked if row[0]==ranked[0][0]]
        category,saving,seq,selected,grammar=ranked[min(first_rank if number==0 else 0,len(ranked)-1)]
        definitions.append(f'{ref} = {{ '+' '.join(seq)+' }')
        audit.append(dict(macro_id=number,body=' '.join(seq),occurrences=len(selected),
                          estimated_saving=saving,rhythm=grammar,phrase_kind='multiple_attacks' if category==2 else 'complete_gate',
                          locations=json.dumps([(locs[l][1],s,len(seq)) for l,s in selected])))
        for loc,start in sorted(selected,reverse=True):
            locs[loc][0][start:start+len(seq)]=[ref]
    return emit(parts,definitions),audit


def enhance_macros(text,limit=32,dump_prefix=None):
    """Bounded allocation portfolio, preserving loops and synchronization blocks.

    Rank macro count, then complete character count. This is a bounded portfolio;
    compilation is checked separately by the experiment runner.
    """
    original=text
    expected=expanded(text)
    state_rows=[]
    text=normalize(text,state_rows)
    before_phrases=text
    loop_rows=[]
    text=prepare_phrases(text,loop_rows)
    choices=[(compress_macros(text),[],'baseline')]
    for width,rank in ((24,0),(64,0),(64,1),(64,2)):
        result,rows=select(text,limit,width,rank)
        result=compact_callers(result)
        if expanded(result)!=expected:
            raise AssertionError('Macro selection changed expanded timed commands')
        choices.append((result,rows,f'width{width}-first{rank}'))
    # Shared relative gestures take precedence over extra small text-only macros.
    macro_count=lambda value:len(re.findall(r'^\*\d+\s*=',value,re.M))
    result,rows,strategy=min(choices,key=lambda item:(macro_count(item[0]),len(item[0])))
    if dump_prefix:
        prefix=Path(dump_prefix); prefix.parent.mkdir(parents=True,exist_ok=True)
        Path(str(prefix)+'.macro_state.before.mml').write_text(original,encoding='cp932',errors='replace')
        Path(str(prefix)+'.macro_state.relative.mml').write_text(text,encoding='cp932',errors='replace')
        Path(str(prefix)+'.macro_state.json').write_text(json.dumps(state_rows,indent=2)+'\n',encoding='utf-8')
        Path(str(prefix)+'.macro_phrases.before.mml').write_text(before_phrases,encoding='cp932',errors='replace')
        Path(str(prefix)+'.macro_phrases.after.mml').write_text(text,encoding='cp932',errors='replace')
        Path(str(prefix)+'.macro_phrases.loops.json').write_text(json.dumps(loop_rows,indent=2)+'\n',encoding='utf-8')
        with Path(str(prefix)+'.macros.csv').open('w',encoding='utf-8',newline='') as f:
            w=csv.DictWriter(f,fieldnames=('macro_id','body','occurrences','estimated_saving','rhythm','phrase_kind','locations'))
            w.writeheader(); w.writerows(rows)
        Path(str(prefix)+'.macro_selection.json').write_text(json.dumps(dict(
            selected=strategy,original_characters=len(original),selected_characters=len(result),
            priority='macro_count_then_characters',
            phrase_policy='adjacent_loops_first; complete_gates_or_multiple_attacks; no_single_event_or_control_only_macros',
            alternatives=[dict(strategy=s,characters=len(t),macro_count=macro_count(t)) for t,_,s in choices]),indent=2)+'\n',encoding='utf-8')
    return result
