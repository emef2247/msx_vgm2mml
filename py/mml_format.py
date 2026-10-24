"""Whitespace-only layout for final MGSDRV MML, after macro selection."""
import re


_TRACK = re.compile(r'^(\s*[1-9a-hA-H]\s+)(.*)$')
_MACRO = re.compile(r'^\s*\*\d+\s*=\s*\{')


def _scan(text):
    """Yield characters outside strings/comments, retaining their offsets."""
    quote = None
    comment = False
    escaped = False
    for index, char in enumerate(text):
        if comment:
            if char in '\r\n':
                comment = False
            continue
        if quote:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in '\"\'':
            quote = char
        elif char == ';':
            yield index, char
            comment = True
        else:
            yield index, char


def _layout(body, prefix, line_width):
    # Split only structural brackets. Repeat counts belong to the close bracket.
    chunks = []
    start = 0
    consumed = 0
    for index, char in _scan(body):
        if index < consumed or char not in '[]':
            continue
        chunks.append(body[start:index])
        end = index + 1
        if char == ']':
            count = re.match(r'[ \t]*(\d+)', body[end:])
            if count:
                end += count.end()
                chunks.append(']' + count[1])
            else:
                chunks.append(char)
        else:
            chunks.append(char)
        start = consumed = end
    chunks.append(body[start:])
    result = []
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        # Only existing, unquoted whitespace is a safe generic wrap boundary.
        boundaries = [i for i, char in _scan(chunk) if char in ' \t']
        while len(prefix) + len(chunk) > line_width:
            limit = line_width - len(prefix)
            choices = [i for i in boundaries if 0 < i <= limit]
            if not choices:
                break
            cut = choices[-1]
            result.append(prefix + chunk[:cut].rstrip())
            chunk = chunk[cut:].lstrip()
            boundaries = [i for i, char in _scan(chunk) if char in ' \t']
        result.append(prefix + chunk)
    return result


def format_mml(text, line_width=120):
    """Put repeat delimiters on separate lines, preserving target commands.

    Track continuations repeat their channel prefix; macro bodies do not.
    Non-macro brace blocks and all header/comment lines are retained verbatim.
    Macros containing comments are retained verbatim rather than relocating
    comments across executable text. Long indivisible tokens remain intact.
    """
    if line_width < 4:
        raise ValueError('MML line width must be at least 4')
    lines = text.splitlines(keepends=True)
    result = []
    depth = 0
    index = 0
    while index < len(lines):
        line = lines[index]
        ending = '\r\n' if line.endswith('\r\n') else '\n' if line.endswith('\n') else ''
        code = line[:-len(ending)] if ending else line
        if depth == 0 and _MACRO.match(code):
            block = line
            balance = sum(1 if char == '{' else -1 if char == '}' else 0
                          for _, char in _scan(block))
            while balance > 0 and index + 1 < len(lines):
                index += 1
                block += lines[index]
                balance = sum(1 if char == '{' else -1 if char == '}' else 0
                              for _, char in _scan(block))
            structural = list(_scan(block))
            opening = next(i for i, char in structural if char == '{')
            closing = next((i for i, char in structural if char == '}'), None)
            # Preserve ambiguous/comment-bearing definitions in full.
            comment = any(char == ';' for _, char in structural)
            if balance or closing is None or comment:
                result.append(block)
            else:
                tail = block[closing + 1:]
                newline = '\r\n' if '\r\n' in block else '\n'
                body = block[opening + 1:closing]
                formatted = _layout(body, '', line_width)
                result.append(block[:opening + 1] + newline + newline.join(formatted)
                              + newline + '}' + tail)
        elif depth == 0 and (match := _TRACK.match(code)):
            prefix, body = match.groups()
            # Keep the exact comment suffix, including leading whitespace.
            semicolon = next((i for i, char in _scan(body) if char == ';'), None)
            if semicolon is None:
                music, suffix = body, ''
            else:
                music = body[:semicolon].rstrip()
                suffix = body[len(music):]
            formatted = _layout(music, prefix, line_width)
            if formatted:
                formatted[-1] += suffix
                result.append((ending or '\n').join(formatted) + ending)
            else:
                result.append(line)
        else:
            result.append(line)
            depth += sum(1 if char == '{' else -1 if char == '}' else 0
                         for _, char in _scan(code))
        index += 1
    return ''.join(result)
