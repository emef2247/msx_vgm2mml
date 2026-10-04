"""Native OPM Segments to MDX-dialect MML register controls.

This first target preserves control order/Key masks using y commands on one
conductor track. Source Segments stay unchanged. MDX time is a target projection,
not a new source clock, note interpretation or acoustic simulation.
"""
import csv
from dataclasses import dataclass
import json
from pathlib import Path

# Fixed MXDRV playback tick at @t255: 256 us, or 7056/625 VGM samples.
MDX_SAMPLE_NUMERATOR = 7056
MDX_SAMPLE_DENOMINATOR = 625


@dataclass(frozen=True)
class MdxWrite:
    source_event_id: int
    source_segment_ids: tuple[int, ...]
    source_vgmticks: int
    mdx_tick: int
    projected_vgmticks: int
    register: int
    data: int


@dataclass(frozen=True)
class MdxProjection:
    writes: tuple[MdxWrite, ...]
    source_end_vgmticks: int
    end_mdx_tick: int
    end_projected_vgmticks: int
    clock_hz: int

    def timing_report(self):
        errors = [w.projected_vgmticks - w.source_vgmticks for w in self.writes]
        errors.append(self.end_projected_vgmticks - self.source_end_vgmticks)
        times = sorted({(w.source_vgmticks, w.mdx_tick) for w in self.writes}
                       | {(self.source_end_vgmticks, self.end_mdx_tick)})
        return dict(source_end_vgmticks=self.source_end_vgmticks,
                    projected_end_vgmticks=self.end_projected_vgmticks,
                    end_mdx_tick=self.end_mdx_tick, tempo_byte=255,
                    tick_microseconds=256,
                    max_abs_timing_error_samples=max(map(abs, errors), default=0),
                    collapsed_positive_intervals=sum(a[0] < b[0] and a[1] == b[1]
                                                     for a, b in zip(times, times[1:])),
                    controls=len(self.writes), clock_hz=self.clock_hz)


def mdx_tick(samples):
    """Nearest absolute MDX tick; no per-gap rounding accumulation."""
    if not isinstance(samples, int) or samples < 0:
        raise ValueError('Source sample positions must be nonnegative integers')
    return (samples * MDX_SAMPLE_DENOMINATOR + MDX_SAMPLE_NUMERATOR // 2) // MDX_SAMPLE_NUMERATOR


def projected_samples(tick):
    return tick * MDX_SAMPLE_NUMERATOR // MDX_SAMPLE_DENOMINATOR


def project_segments(segments, *, end_vgmticks):
    """Consume actual OpmSegments, deduplicating shared-write fanout.

    Source nonchanging writes omitted by Segment construction cannot be
    recovered here. Changed states, Key edges and retained test/timer writes
    are represented in source-event order, including zero-duration Segments.
    """
    end_tick = mdx_tick(end_vgmticks)
    facts = set()
    grouped = {}
    for segment in segments:
        facts.add((segment.chip_instance, segment.chip_type, segment.clock_hz))
        if segment.source_event_id is None:
            continue
        identity = (segment.vgmticks, segment.register, segment.data)
        if not 0 <= segment.vgmticks <= end_vgmticks:
            raise ValueError('Segment control is outside source end')
        if (not isinstance(segment.register, int) or not 0 <= segment.register <= 255
                or not isinstance(segment.data, int) or not 0 <= segment.data <= 255):
            raise ValueError('Segment source control must contain byte register/data values')
        previous, ids = grouped.setdefault(segment.source_event_id, (identity, []))
        if previous != identity:
            raise ValueError('Conflicting shared-write Segment evidence')
        ids.append(segment.segment_id)
    if facts != {(0, 'YM2151', 4000000)}:
        raise ValueError('Initial MDX target requires one 4 MHz YM2151 instance')
    writes = []
    last_sample = 0
    for event_id, ((samples, register, data), ids) in sorted(grouped.items()):
        if samples < last_sample:
            raise ValueError('Segment source-event order is not chronological')
        last_sample = samples
        tick = mdx_tick(samples)
        writes.append(MdxWrite(event_id, tuple(sorted(ids)), samples, tick,
                               projected_samples(tick), register, data))
    return MdxProjection(tuple(writes), end_vgmticks, end_tick,
                         projected_samples(end_tick), 4000000)


def render(projection, *, title='OPM Segment replay'):
    title = str(title).replace('"', "'").replace('\r', ' ').replace('\n', ' ')
    lines = [f'#title "{title}"',
             '; OPM Segment target: ordered register controls, one conductor track.',
             '; MDX @t255 = 256 us; r is a time advance, not inferred acoustic silence.',
             '; Source samples and target timing are retained in the controls CSV.',
             'A @t255']
    cursor = 0
    for write in projection.writes:
        gap = write.mdx_tick - cursor
        while gap:
            count = min(gap, 65535)
            lines.append(f'A r%{count}')
            gap -= count
        cursor = write.mdx_tick
        lines.append(f'A y{write.register},{write.data} ; event {write.source_event_id}, sample {write.source_vgmticks}')
    gap = projection.end_mdx_tick - cursor
    while gap:
        count = min(gap, 65535)
        lines.append(f'A r%{count}')
        gap -= count
    return '\n'.join(lines) + '\n'


def dump_projection(projection, path):
    fields = ('source_event_id', 'source_segment_ids', 'source_vgmticks', 'mdx_tick',
              'projected_vgmticks', 'timing_error_samples', 'register', 'data')
    with Path(path).open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        for write in projection.writes:
            row = dict(write.__dict__)
            row['source_segment_ids'] = json.dumps(write.source_segment_ids)
            row['timing_error_samples'] = write.projected_vgmticks - write.source_vgmticks
            writer.writerow(row)
