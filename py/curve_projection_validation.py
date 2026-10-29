"""Repartition an accepted curve for a backend without undoing approximation."""
from dataclasses import replace


def repartition(base, accepted):
    if base.chip != accepted.chip or base.source_segments != accepted.source_segments:
        raise ValueError('Curve repartition requires identical native source evidence')
    target=dict(accepted.channels)
    channels=[]
    for channel,notes in base.channels:
        rows=target.get(channel,());cursor=0;projected=[]
        for note in notes:
            start,stop=note.start,note.start+note.length
            while cursor < len(rows) and rows[cursor].start+rows[cursor].length <= start:
                cursor+=1
            pieces=[];coverage=start
            index=cursor
            while index < len(rows) and rows[index].start < stop:
                row=rows[index];left=max(start,row.start);right=min(stop,row.start+row.length)
                if left < right:
                    if left != coverage or row.rest != note.rest:
                        raise ValueError('Curve repartition crosses an accepted gap or rest')
                    at=row.start
                    for volume,length in row.runs:
                        a,b=max(left,at),min(right,at+length)
                        if a < b:
                            if pieces and pieces[-1][0] == volume:
                                pieces[-1]=(volume,pieces[-1][1]+b-a)
                            else:
                                pieces.append((volume,b-a))
                        at+=length
                    coverage=right
                index+=1
            if coverage != stop or not note.rest and sum(n for _,n in pieces)!=note.length:
                raise ValueError('Curve repartition cannot cover a backend note')
            projected.append(replace(note,runs=tuple(pieces)) if not note.rest else note)
        channels.append((channel,tuple(projected)))
    result=replace(base,channels=tuple(channels))
    result.validate(dict(base.source_segments))
    return result
