"""Choose MGSDRV's static OPLL layout from source rhythm-mode writes."""
import csv


def mode_from_trace(path):
    enabled = False
    rhythm_used = False
    with open(path, newline='') as stream:
        for row in csv.DictReader(stream):
            if row.get('#type') == 'rhythm':
                enabled = bool(int(row.get('is_ryt') or 0))
                if enabled and any(int(row.get(k) or 0) for k in ('bd','sd','tom','tc','hh')):
                    rhythm_used = True
    # MGSDRV initialization can briefly enable rhythm before selecting nine
    # melody channels. That write alone must not suppress the final three voices.
    return int(rhythm_used or enabled)
