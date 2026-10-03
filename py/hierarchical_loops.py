"""Experimental exact note-unit loop trees; source data is never rewritten."""
from dataclasses import dataclass
from functools import lru_cache

@dataclass(frozen=True)
class Node:
    start: int
    end: int
    children: tuple = ()
    repeats: int = 1


def experiment(units, commands, strategy, max_phrase=32, max_depth=3, *, return_tree=False):
    if max_phrase < 1 or max_depth < 1:
        raise ValueError('Phrase width and depth must be positive')
    if len(units) != len(commands):
        raise ValueError('Unit/command length mismatch')
    keys = [(getattr(u, 'validation_key', u.signature()), c)
            for u, c in zip(units, commands)]
    leaves = tuple(Node(i, i+1) for i in range(len(units)))

    def render(node):
        if not node.children:
            return commands[node.start]
        return '[' + ' '.join(render(c) for c in node.children) + ']' + str(node.repeats)

    def expanded(node):
        if not node.children:
            return (node.start,)
        body = tuple(i for c in node.children for i in expanded(c))
        return body * node.repeats

    def depth(node):
        return 0 if not node.children else 1 + max(map(depth,node.children))

    if strategy == 'immediate':
        nodes = list(leaves)
        # Width is measured in original note units, not compressed markers.
        for width in range(1, max_phrase+1):
            i = 0
            while i < len(nodes):
                j = i
                while j < len(nodes) and nodes[j].end-nodes[i].start < width:
                    j += 1
                if j == len(nodes) or nodes[j].end-nodes[i].start != width:
                    i += 1; continue
                stop = j+1
                body = tuple(nodes[i:stop])
                signature = tuple(keys[k] for k in range(nodes[i].start,nodes[j].end))
                count = 1
                while stop < len(nodes) and count < 255:
                    end = stop
                    while end < len(nodes) and nodes[end].end-nodes[stop].start < width:
                        end += 1
                    if end == len(nodes) or nodes[end].end-nodes[stop].start != width:
                        break
                    if tuple(keys[k] for k in range(nodes[stop].start,nodes[end].end)) != signature:
                        break
                    count += 1; stop = end+1
                node = Node(nodes[i].start,nodes[stop-1].end,body,count)
                if count > 1 and depth(node) <= max_depth and len(render(node)) < len(' '.join(render(c) for c in nodes[i:stop])):
                    nodes[i:stop] = [node]
                i += 1
        result = tuple(nodes)
    elif strategy == 'retained':
        @lru_cache(None)
        def solve(lo,hi,remaining):
            costs = {hi:0}; choices = {}
            for start in range(hi-1,lo-1,-1):
                leaf = leaves[start]
                costs[start] = len(render(leaf))+1+costs[start+1]
                choices[start] = (leaf,start+1)
                if not remaining:
                    continue
                for width in range(1,min(max_phrase,(hi-start)//2)+1):
                    signature = keys[start:start+width]
                    count = 2
                    while count <= 255 and start+width*count <= hi:
                        stop = start+width*count
                        if keys[stop-width:stop] != signature:
                            break
                        body = solve(start,start+width,remaining-1)
                        node = Node(start,stop,body,count)
                        cost = len(render(node))+1+costs[stop]
                        if cost < costs[start]:
                            costs[start] = cost; choices[start] = (node,stop)
                        count += 1
            nodes = []; start = lo
            while start < hi:
                node,start = choices[start]; nodes.append(node)
            return tuple(nodes)
        result = solve(0,len(units),max_depth)
    else:
        raise ValueError('Unknown strategy')
    # Identical original units/commands, including controls and ties, must survive.
    indices = tuple(i for node in result for i in expanded(node))
    if tuple(keys[i] for i in indices) != tuple(keys):
        raise AssertionError('Loop expansion changed units or commands')
    rows = []
    def record(nodes,parent=''):
        for node in nodes:
            if node.children:
                identity = len(rows)
                rows.append(dict(id=identity,parent=parent,start=node.start,end=node.end,
                                 width=node.children[-1].end-node.start,repeats=node.repeats,
                                 depth=depth(node)))
                record(node.children,identity)
    record(result)
    if return_tree:
        return result
    return ' '.join(render(n) for n in result), rows
