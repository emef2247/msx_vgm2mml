"""Final MGSC notation: additive ties and an explicit shared default length.

Run after macro selection/layout. Whitespace does not carry articulation in
MGSC. Caret adds length to the preceding note; ampersand remains a slur when
pitch or octave changes. No timing approximation is performed here.
"""
from collections import Counter
import re

from mml_sync import _TOKEN,_NOTE,_duration


def compact(text):
    rhythm=bool(re.search(r'^#opll_mode\s+1\b',text,re.M))
    additive_ties=not bool(re.search(r'\bq[1-7]\b',text,re.I))
    # Keep explicit lengths in externally supplied changing-l scopes.
    protected=bool(re.search(r'(?<![a-z@])l(?:%\d+|\d+)',
        '\n'.join(line.split(';',1)[0] for line in text.splitlines() if not line.startswith('#')),re.I))
    counts=Counter()
    for line in text.splitlines():
        match=re.match(r'^([1-9a-h])\s+(.*)',line,re.I)
        if not match or rhythm and match[1].lower()=='f':continue
        for token in _TOKEN.findall(match[2].split(';',1)[0]):
            note=_NOTE.fullmatch(token)
            if note and note[1]:counts[note[1]+note[2]]+=1
            elif note:protected=True
    for body in re.findall(r'^\*\d+\s*=\s*\{([^}]*)\}',text,re.M):
        if any((note:=_NOTE.fullmatch(token)) and not note[1] for token in _TOKEN.findall(body)):
            protected=True
    default=None if protected or not counts else max(counts,key=lambda key:counts[key]*len(key))
    # A default setter on every track must pay for itself.
    tracks=len(set(re.findall(r'^([1-9a-h])\s+',text,re.M|re.I)))
    if default and counts[default]*len(default)<=tracks*(len(default)+2):default=None
    initialized=set();octaves={};out=[];macro_depth=0;defaults={}
    for line in text.splitlines():
        code,semicolon,comment=line.partition(';')
        match=re.match(r'^([1-9a-h])\s+(.*)',code,re.I)
        macro=bool(re.match(r'^\*\d+\s*=\s*\{',code))
        if macro or macro_depth:
            # Macro bodies keep explicit lengths: caller l-state is independent.
            out.append(line);macro_depth+=code.count('{')-code.count('}')
            continue
        if not match or rhythm and match[1].lower()=='f':out.append(line);continue
        channel=match[1].lower();body=match[2];tokens=_TOKEN.findall(body)
        if ''.join(tokens)!=body:out.append(line);continue
        result=[];pitch=None;octave=octaves.get(channel,4);tie=False;total=0;adjacent=False
        if default and channel not in initialized:
            result.append('l'+default+' ');initialized.add(channel)
            spec=re.fullmatch(r'(%\d+|\d+)(\.*)',default)
            defaults[channel]=_duration(spec[1],spec[2],48)
        for token in tokens:
            if token=='&':tie=True;continue
            note=_NOTE.fullmatch(token)
            if note:
                name=re.match(r'[a-gr][+#-]?',token,re.I)[0].lower()
                length=(note[1] or '')+note[2]
                count=_duration(note[1],note[2],defaults.get(channel,48))
                same=(additive_ties and adjacent and pitch==(octave,name) and name!='r' and total+count<=256)
                rendered=('^'+length if tie and same else ('& ' if tie else '')+token)
                if default and length==default:
                    if not (tie and same):rendered=('& ' if tie else '')+name
                if tie and same and not length:rendered='^%'+str(count)
                if rendered.startswith('^'):
                    while result and result[-1].isspace():result.pop()
                result.append(rendered);total=total+count if tie and same else count
                tie=False;pitch=(octave,name);adjacent=True
            else:
                if re.fullmatch(r'o\d+',token,re.I):octave=int(token[1:])
                elif token in ('<','>'):octave+=1 if token=='>' else -1
                if token.startswith('*') or token in ('[',) or token.startswith(']'):
                    # A repeated/macro body may alter octave or preceding pitch.
                    pitch=None
                if not token.isspace():adjacent=False
                if token.lower().startswith('l'):
                    setter=re.fullmatch(r'l(%\d+|\d+)(\.*)',token,re.I)
                    if setter:defaults[channel]=_duration(setter[1],setter[2],48)
                result.append(token)
        octaves[channel]=octave
        if tie:result.append('&')
        out.append(match[1]+' '+''.join(result).strip()+((';'+comment) if semicolon else ''))
    result='\n'.join(out)+'\n'
    return result if len(result)<len(text) else text
