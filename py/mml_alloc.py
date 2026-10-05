"""Explicit per-track allocation overrides, applied after automatic allocation."""
import re


def parse_alloc(value):
    result = {}
    for item in value.split(','):
        match = re.fullmatch(r'\s*([0-9a-hA-H])\s*=\s*([0-9]+)\s*', item)
        if not match:
            raise ValueError('Expected comma-separated channel=bytes entries (channels 0-9, a-h)')
        ch, size = match[1].lower(), int(match[2])
        if ch in result:
            raise ValueError(f'Duplicate allocation for channel {ch}')
        if not 0 <= size <= 65535:
            raise ValueError('Allocation must be between 0 and 65535 bytes')
        result[ch] = size
    return result


def override_alloc(text, overrides):
    if not overrides:
        return text
    match = re.search(r'^#alloc\s*\{([^}]*)\}', text, re.M)
    values = parse_alloc(match[1]) if match and match[1].strip() else {}
    values.update(overrides)
    line = '#alloc { ' + ', '.join(f'{ch}={values[ch]}' for ch in '0123456789abcdefgh' if ch in values) + ' }'
    if match:
        return text[:match.start()] + line + text[match.end():]
    return text + '\n' + line + '\n'
