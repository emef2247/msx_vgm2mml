"""Exact target repeats first; reserve macros for complete sounding phrases."""
from functools import lru_cache
from copy import deepcopy
import re

from mml_sync import _NOTE, _RHYTHM_NOTE, _text


def freeze(nodes):
    return tuple((freeze(n[0]), n[1]) if isinstance(n, tuple) else n for n in nodes)


def changes_default_length(nodes):
    return any(changes_default_length(n[0]) if isinstance(n,tuple)
               else bool(re.fullmatch(r'l(?:%\d+|\d+)\.*',n,re.I)) for n in nodes)


@lru_cache(maxsize=8192)
def shape(nodes, rhythm=False, incoming_tie=False):
    """Capped attack/event counts and continuation context; never infer a new gate."""
    attacks = timed = sounding = 0
    first_tied = None
    pending, last_rest = incoming_tie, False
    for node in nodes:
        if isinstance(node, tuple):
            for _ in range(min(node[1], 2)):
                a, t, s, first, pending, rest = shape(node[0], rhythm, pending)
                attacks, timed, sounding = min(2, attacks+a), min(2, timed+t), min(2, sounding+s)
                if first_tied is None:first_tied = first
                if t:last_rest = rest
        elif node == '&' and not rhythm:
            pending = True
        elif (_RHYTHM_NOTE if rhythm else _NOTE).fullmatch(node):
            rest = node.lower().startswith('r')
            timed = min(2, timed+1)
            if not rest:
                if first_tied is None:first_tied = pending
                sounding = min(2, sounding+1)
                attacks = min(2, attacks+int(not pending))
            pending, last_rest = False, rest
    return attacks, timed, sounding, first_tied, pending, last_rest


def contexts(nodes, rhythm=False):
    pending = False; result = [False]
    for node in nodes:
        pending = shape(freeze([node]), rhythm, pending)[4]
        result.append(pending)
    # Is the first event to the right tied to material on its left?
    following = [False]*(len(nodes)+1)
    suffix = None
    for index in range(len(nodes)-1, -1, -1):
        row = shape(freeze([nodes[index]]), rhythm)
        if row[1]:suffix = row[3] if not row[5] or row[2] else False
        elif nodes[index] == '&':suffix = True
        following[index] = bool(suffix)
    return result, following


def summaries(nodes, rhythm=False):
    return [(shape(freeze([node]),rhythm,False),shape(freeze([node]),rhythm,True)) for node in nodes]


def extend(left, right):
    a,t,s,first,pending,rest=left
    b,u,v,next_first,next_pending,next_rest=right
    return min(2,a+b),min(2,t+u),min(2,s+v),first if first is not None else next_first,next_pending,next_rest if u else rest


def classify(row, following_tie=False, *, root=True, at_end=False):
    attacks,timed,sounding,first_tied,pending,rest=row
    if not sounding or first_tied or pending:return 0
    if not rest and (following_tie or at_end and not root):return 0
    if attacks>=2:return 2
    return int(attacks==1 and timed>=2)


def quality(nodes, start, stop, rhythm=False, *, root=True, context=None):
    """0=inline, 1=complete gate, 2=multiple source-spelled attacks."""
    before, after = context if context is not None else contexts(nodes, rhythm)
    return classify(shape(freeze(nodes[start:stop]),rhythm,before[start]),after[stop],root=root,at_end=stop==len(nodes))


def prepare(text, audit=None):
    """Fold adjacent complete command groups before nonadjacent macro search."""
    from structured_macros import parts_from, emit
    parts, rhythm = parts_from(text)
    def visit(nodes, percussion, path):
        groups, pending = [], []
        for index, node in enumerate(nodes):
            if isinstance(node, tuple):
                node = (visit(node[0], percussion, path+(index,)), node[1])
            pending.append(node)
            if isinstance(node, tuple) or (_RHYTHM_NOTE if percussion else _NOTE).fullmatch(node):
                groups.append(pending); pending = []
        if pending:groups.append(pending)
        keys = [freeze(group) for group in groups]
        result = []; index = 0
        while index < len(groups):
            best = None
            for width in range(1, min(24, (len(groups)-index)//2)+1):
                key = keys[index:index+width]; count = 1
                while keys[index+count*width:index+(count+1)*width] == key:
                    count += 1
                if count < 2:continue
                body = [n for group in groups[index:index+width] for n in group]
                # MGSC encodes default note lengths when compiling a loop body.
                # Literal repetition of a changing l-state is not sufficient proof.
                if changes_default_length(body):continue
                stats = shape(freeze(body), percussion)
                if not stats[1] or stats[4]:continue
                chunks = []; remaining = count
                while remaining:
                    repeats = min(255, remaining)
                    chunks.extend([(deepcopy(body), repeats)] if repeats > 1 else deepcopy(body))
                    remaining -= repeats
                original = ' '.join(_text(n) for group in groups[index:index+width*count] for n in group)
                saving = len(original)-len(' '.join(map(_text, chunks)))
                if saving > 0 and (best is None or saving > best[0]):
                    best = saving, width, count, chunks, body
            if best:
                saving, width, count, chunks, body = best
                result.extend(chunks)
                if audit is not None:
                    audit.append(dict(location=str(path),atom_start=index,atom_width=width,
                        repeats=count,estimated_saving=saving,body=' '.join(map(_text,body))))
                index += width*count
            else:
                result.extend(groups[index]); index += 1
        return result
    for index, part in enumerate(parts):
        if isinstance(part, list):
            part[1] = visit(part[1], rhythm and part[0] == 'f', (index,))
    return emit(parts, [])
