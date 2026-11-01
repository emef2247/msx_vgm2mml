"""Enforce the original MGSC macro-definition budget on final MML text.

Measured on the real compiler (mgsc-js oracle): a file whose prefix
through the last macro definition is 5,554 bytes compiles; 5,820 bytes
fails with "Can't defined Macro". When the prefix exceeds the budget,
macros are expanded (the exact inverse of a macro call, so playback
semantics are unchanged), choosing candidates by definition bytes freed
per byte of track growth so the track buffers suffer least.
"""
import re

MGSC_MACRO_DEFINITION_BUDGET = 5500

_DEFINITION_START = re.compile(r'^\*(\d+)\s*=\s*\{?')


def _definition_blocks(lines):
    """(number, start, end) line spans of *N = { ... } definitions."""
    blocks = []
    i = 0
    while i < len(lines):
        match = _DEFINITION_START.match(lines[i])
        if not match:
            i += 1
            continue
        depth = lines[i].count('{') - lines[i].count('}')
        j = i
        while depth > 0 and j + 1 < len(lines):
            j += 1
            depth += lines[j].count('{') - lines[j].count('}')
        blocks.append((int(match.group(1)), i, j))
        i = j + 1
    return blocks


def _body_of(lines, start, end):
    text = '\n'.join(lines[start:end + 1])
    text = text[text.index('=') + 1:].strip()
    if text.startswith('{'):
        text = text[1:]
    if text.endswith('}'):
        text = text[:-1]
    return ' '.join(text.split())


def _expand(lines, number, body):
    call = re.compile(r'\*' + str(number) + r'(?!\d)')
    out = []
    for line in lines:
        code, sep, comment = line.partition(';')
        out.append(call.sub(lambda _m: body, code) + (sep + comment if sep else ''))
    return out


def enforce_macro_budget(text, budget):
    """Expand macros until the definition prefix fits; return (text, expanded)."""
    lines = text.split('\n')
    expanded = []
    while True:
        blocks = _definition_blocks(lines)
        if not blocks:
            break
        prefix = len('\n'.join(lines[:blocks[-1][2] + 1]))
        if prefix <= budget:
            break
        best = None
        for number, start, end in blocks:
            body = _body_of(lines, start, end)
            freed = len('\n'.join(lines[start:end + 1])) + 1
            call = re.compile(r'\*' + str(number) + r'(?!\d)')
            uses = sum(len(call.findall(line.partition(';')[0]))
                       for i, line in enumerate(lines)
                       if not (start <= i <= end))
            growth = uses * max(len(body) - len(f'*{number}'), 0)
            ratio = freed / growth if growth else float('inf')
            if best is None or (ratio, number) > best[0]:
                best = ((ratio, number), number, start, end, body)
        _, number, start, end, body = best
        del lines[start:end + 1]
        lines = _expand(lines, number, body)
        expanded.append(number)
    return '\n'.join(lines), expanded
