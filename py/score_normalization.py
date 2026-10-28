"""Lossy score timing per original device; source-native evidence stays exact."""
from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass, replace
from fractions import Fraction
import csv
import json
from pathlib import Path
from copy import copy
from dataclasses import is_dataclass


def score_tempo(value):
    try:tempo=Fraction(str(value))
    except (ValueError,ZeroDivisionError) as error:raise ValueError('--score-tempo must be an integer from 1 to 255') from error
    if tempo.denominator!=1 or not 1<=tempo<=255:
        raise ValueError('--score-tempo must be an integer from 1 to 255')
    return int(tempo)


def add_arguments(parser):
    parser.add_argument('--score-normalize',action='store_true',
        help='Quantize musical timing per original chip instance; compensate at score-gate quiet windows (opt-in)')
    parser.add_argument('--score-tempo',type=score_tempo,default=225,
        help='Reference tempo for score-normalize; 1/64=60/tempo/16 seconds (default: 225)')


def option_values(args):
    return dict(score_normalize=getattr(args,'score_normalize',False),score_tempo=getattr(args,'score_tempo',225))


@dataclass(frozen=True)
class DeviceClock:
    device_id: str
    quantum: Fraction
    anchors: tuple = ((0,0),)
    reason: str = ''
    end_sample: int | None = None

    def position(self,sample):
        if self.reason:return sample
        if self.end_sample is not None and sample>=self.end_sample:return self.end_sample
        index=bisect_right(self.anchors,(sample,float('inf')))-1
        source,target=self.anchors[max(0,index)]
        count=(Fraction(sample)-source)//self.quantum
        result=round(Fraction(target)+count*self.quantum)
        return min(result,self.end_sample) if self.end_sample is not None else result


@dataclass
class Normalization:
    performance: object
    clocks: dict
    anchors: list
    intervals: list
    mappings: list
    report: dict

    def dump(self,root,stem):
        root=Path(root);root.mkdir(parents=True,exist_ok=True)
        (root/f'{stem}.score_normalization.json').write_text(json.dumps(self.report,indent=2)+'\n',encoding='utf-8')
        for name,rows in (('anchors',self.anchors),('intervals',self.intervals),('controls',self.mappings)):
            fields=list(rows[0]) if rows else ['device_id']
            with (root/f'{stem}.score_normalization.{name}.csv').open('w',newline='',encoding='utf-8') as stream:
                writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(rows)


def _quiet(performance,device):
    """Score gate inactivity only, never a claim about acoustic release tails."""
    spans=[(u.start_sample,u.end_sample) for u in performance.units if u.device_id==device and u.end_sample>u.start_sample]
    for event in performance.percussion:
        if event.device_id!=device:continue
        if event.stop_sample is None:return (), 'unknown_percussion_stop'
        spans.append((event.start_sample,event.stop_sample))
    merged=[]
    for start,stop in sorted(spans):
        if merged and start<=merged[-1][1]:merged[-1]=(merged[-1][0],max(stop,merged[-1][1]))
        else:merged.append((start,stop))
    quiet=[];cursor=0
    for start,stop in merged:
        if start>cursor:quiet.append((cursor,start))
        cursor=max(cursor,stop)
    if cursor<performance.end_sample:quiet.append((cursor,performance.end_sample))
    return tuple(quiet),''


def normalize(performance,*,tempo=225,source_loop=False):
    tempo=score_tempo(tempo);quantum=Fraction(44100*60,tempo*16)
    clocks={};anchors=[];intervals=[];mappings=[];device_reports=[]
    devices={d.device_id:d for d in performance.devices}
    packet_chips={p.chip for p in performance.pcm_packets}
    global_opaque=bool(packet_chips&{'pcm','unknown'})
    for identity,device in devices.items():
        units=[u for u in performance.units if u.device_id==identity]
        controls=[c for c in performance.controls if c.device_id==identity]
        quiet,uncertain=_quiet(performance,identity)
        reason=''
        if source_loop:reason='source_song_loop_requires_shared_boundary_validation'
        elif global_opaque or device.chip in packet_chips or any(u.role=='pcm' for u in units):reason='opaque_pcm_or_stream_dependencies'
        elif any((c.kind=='opm_timer_control' and dict(c.parameters).get('timer_flags',0)&128) or
                 (c.kind=='opna_mode' and dict(c.parameters).get('csm',0)) for c in controls):
            reason='unmodeled_csm_timer_generated_gates'
        elif uncertain:reason=uncertain
        elif controls and not units and not any(e.device_id==identity for e in performance.percussion):reason='no_complete_gate_coverage'
        elif device.chip in ('psg','scc') and any(d.chip==device.chip and d.instance for d in devices.values()):
            reason='dual_instance_gate_coverage_not_proven'
        chosen=[(0,0)]
        clock=DeviceClock(identity,quantum,tuple(chosen),reason,performance.end_sample)
        if not reason:
            for start,stop in quiet:
                if stop==0 or stop==performance.end_sample:continue
                before=clock.position(stop)
                desired=round(round(Fraction(stop)/quantum)*quantum)
                # A backwards jump would reorder muted/shared writes in the
                # quiet window. Preserve monotonicity; the residual stays bounded.
                target=max(before,desired)
                rest_start=clock.position(start)
                eligible=Fraction(stop-start)>=quantum and target>=rest_start
                anchors.append(dict(device_id=identity,source_start=start,source_end=stop,
                    evidence='score_gate_quiet',acoustic_silence_proven=False,
                    projected_rest_start=rest_start,projected_anchor=target,
                    desired_absolute_anchor=desired,
                    previous_projection=before,compensation_samples=target-before,
                    applied=eligible,reason='' if eligible else 'quiet_window_too_short'))
                if eligible:
                    chosen.append((stop,target))
                    clock=DeviceClock(identity,quantum,tuple(chosen),end_sample=performance.end_sample)
        clocks[identity]=clock
        shifts=[];collapsed=0;short_kept=0;lengthened=0
        for unit in units:
            start,stop=clock.position(unit.start_sample),clock.position(unit.end_sample)
            shifts.extend((start-unit.start_sample,stop-unit.end_sample))
            collapsed+=int(stop==start and unit.end_sample>unit.start_sample)
            short_kept+=int(0<unit.end_sample-unit.start_sample<quantum and stop>start)
            lengthened+=int(stop-start>unit.end_sample-unit.start_sample)
            intervals.append(dict(device_id=identity,unit_id=unit.unit_id,source_channel=unit.channel,
                source_start=unit.start_sample,source_end=unit.end_sample,
                projected_start=start,projected_end=stop,
                start_shift=start-unit.start_sample,end_shift=stop-unit.end_sample,
                collapsed=stop==start and unit.end_sample>unit.start_sample,reason=reason))
        device_reports.append(dict(device_id=identity,chip=device.chip,instance=device.instance,
            status='abstained' if reason else 'applied',reason=reason,anchors=len(chosen)-1,
            collapsed_units=collapsed,sub_quantum_units_retained=short_kept,lengthened_units=lengthened,
            maximum_boundary_shift_samples=max(map(abs,shifts),default=0)))
    controls=[];seen=defaultdict(set)
    for control in performance.controls:
        at=clocks[control.device_id].position(control.sample)
        seen[control.device_id,at].add(control.sample)
        controls.append(replace(control,sample=at))
        mappings.append(dict(device_id=control.device_id,control_id=control.control_id,
            source_event_id=control.source_event_id,source_sample=control.sample,projected_sample=at,
            shift_samples=at-control.sample,order=control.order))
    def curve(points,clock):
        return tuple((clock.position(at),value) for at,value in points)
    units=tuple(replace(u,start_sample=clocks[u.device_id].position(u.start_sample),
        end_sample=clocks[u.device_id].position(u.end_sample),
        pitch_curve=curve(u.pitch_curve,clocks[u.device_id]),volume_curve=curve(u.volume_curve,clocks[u.device_id]),
        voice_curve=curve(u.voice_curve,clocks[u.device_id])) for u in performance.units)
    percussion=tuple(replace(e,start_sample=clocks[e.device_id].position(e.start_sample),
        stop_sample=clocks[e.device_id].position(e.stop_sample) if e.stop_sample is not None else None,
        pitch_curve=curve(e.pitch_curve,clocks[e.device_id]),volume_curve=curve(e.volume_curve,clocks[e.device_id]))
        for e in performance.percussion)
    end=performance.end_sample
    report=dict(enabled=True,reference_tempo=tempo,quantum_samples=str(quantum),
        quantum_ms=float(quantum*1000/44100),minimum_note='1/64 boundary grid; straddling short gates can survive or lengthen',
        quantization_priority='shared device timestamps before independent duration truncation; floors and lengthening coexist',
        synchronization_scope='original_device_id; independent chip instances',
        evidence='score_gate_quiet; not acoustic silence',
        timing_policy='floor within device epochs; nearest absolute quiet-end anchors',
        anchor_monotonicity='never move backwards across muted/shared controls',
        interval_mapping='planned endpoints; gates are rebuilt from projected controls; terminal holds follow output EOF',
        eof_policy='original container EOF pinned; terminal residual may remain',
        source_sha256=performance.source_sha256,source_end_sample=performance.end_sample,
        end_sample=end,devices=device_reports,source_segments_unchanged=True,
        collapsed_control_groups=sum(len(samples)>1 for samples in seen.values()),
        collapsed_control_order_preserved=True,percussion_unknown_stop_is_quiet=False)
    report.update(status='applied' if any(d['status']=='applied' for d in device_reports) else 'abstained',
        sync_points=[dict(device_id=a['device_id'],source_sample=a['source_end'],projected_sample=a['projected_anchor'])
                     for a in anchors if a['applied']],
        maximum_control_shift_samples=max((abs(m['shift_samples']) for m in mappings),default=0))
    report['mgs_backend_timing']=dict(source_view='original interpreted sample spans',
        interpretation_timebase='integer vgmticks at 44100 Hz',notation_tempo=tempo,
        notation_steps_per_whole=192,minimum_note_steps=3,
        frame_clock_used_for_score=False,software_envelope_driver_hz=60,
        exact_timing_equality_with_reference_vgm=False,
        reference_vgm_policy='ordered boundary warp; separate from per-note duration truncation',
        note='Only software-envelope holds use driver frames; musical durations derive directly from sample spans')
    projected=replace(performance,units=units,controls=tuple(controls),percussion=percussion,
        end_sample=end,patterns=(),metadata=performance.metadata+(('score_normalization',report),))
    return Normalization(projected,clocks,anchors,intervals,mappings,report)


def comment_header(text,report):
    """Expose timing anchors without splitting existing phrase loops/macros."""
    if not report or not report.get('sync_points'):return text
    quantum=Fraction(report['quantum_samples'])
    rows=['; Score sync: original device channels only; score steps use reference tempo '+str(report['reference_tempo'])+'.']
    for point in report['sync_points']:
        rows.append('; score-sync '+point['device_id']+' source_sample='+str(point['source_sample'])+
            ' projected_sample='+str(point['projected_sample'])+
            ' score_step='+str(round(Fraction(point['projected_sample'])*3/quantum)))
    lines=text.splitlines()
    at=next((i+1 for i,line in enumerate(lines) if line.startswith('#tempo ')),0)
    lines[at:at]=rows
    return '\n'.join(lines)+'\n'


def sample_segments(segments,path):
    """Compatibility view for interpreters: every time field is source samples.

    These copies never replace the original Segment dump. Target note values
    are chosen later, after sounding-unit and internal-curve interpretation.
    """
    result={};rows=[]
    for channel,members in segments.items():
        result[channel]=[]
        for index,segment in enumerate(members):
            if segment.vgmticks is None or segment.vgmticks_end is None:
                raise ValueError('Score target clock requires source-sample boundaries')
            start=segment.vgmticks;stop=segment.vgmticks_end
            if is_dataclass(segment):
                projected=replace(segment,ticks=start,l=stop-start)
            else:
                projected=copy(segment);projected.ticks=projected.tick_start=start
                projected.tick_end=stop;projected.l=stop-start
            result[channel].append(projected)
            rows.append(dict(channel=channel,index=index,source_start=segment.vgmticks,source_end=segment.vgmticks_end,
                previous_tick=segment.ticks,previous_length=segment.l,interpretation_sample=start,
                interpretation_duration_samples=stop-start,timebase='vgmticks_44100'))
    with Path(path).open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]) if rows else ['channel'])
        writer.writeheader();writer.writerows(rows)
    return result


def sample_csv(path):
    """Compatibility OPLL event/patch columns, explicitly on the sample clock."""
    path=Path(path)
    if not path.is_file():return
    text=path.read_text(encoding='utf-8');data=list(csv.reader(text.splitlines()))
    if not data or 'vgmticks' not in data[0]:return
    sample=data[0].index('vgmticks');tick=data[0].index('ticks')
    for row in data[1:]:
        if len(row)>sample and row[sample]:row[tick]=row[sample]
    path.with_name(path.stem+'.before.sample_clock.csv').write_text(text,encoding='utf-8')
    with path.open('w',newline='',encoding='utf-8') as stream:csv.writer(stream,lineterminator='\n').writerows(data)


class SampleTimingMapper:
    """No fitted/frame clock between native interpretation and score lowering."""
    plan = None
    applied = False
    report = dict(status='disabled',applied=False,reason='score mode uses integer source samples')

    @staticmethod
    def sample(value,source_sample=None):
        return int(value if source_sample is None else source_sample)

    source_sample = staticmethod(int)

    def boundaries(self,values,source_samples=None):
        return tuple(map(int,values if source_samples is None else source_samples))


@dataclass(frozen=True)
class ScoreTiming:
    tempo: int = 225
    quantize: bool = True
    end_sample: int | None = None
    anchors: tuple = ((0,0),)

    @property
    def quantum(self):
        return Fraction(44100*60,self.tempo*16)

    def count(self,samples):
        return Fraction(samples)//self.quantum

    def position(self,sample):
        if not self.quantize:return round(Fraction(sample*self.tempo*48,44100*60))
        index=bisect_right(self.anchors,(sample,float('inf')))-1
        source,steps=self.anchors[max(0,index)]
        return steps+int(self.count(sample-source))*3

    def span(self,start,stop,*,rest=False):
        if rest or not self.quantize:return self.position(start),self.position(stop)
        begin=self.position(start)
        return begin,begin+int(self.count(stop-start))*3


def timing_for_chip(report,chip):
    devices=report.get('devices',())
    source=[device for device in devices if device['chip']==chip]
    if not source:
        # The supported HuC target allocation retains one original device.
        source=[device for device in devices if device['chip']=='huc6280']
    enabled=bool(source) and all(device['status']=='applied' for device in source)
    identities={device['device_id'] for device in source}
    return timing_for_devices(report,identities,enabled)


def timing_for_devices(report,identities,enabled=True):
    quantum=Fraction(report['quantum_samples'])
    anchors=((0,0),)+tuple((point['source_sample'],round(Fraction(point['projected_sample'])*3/quantum))
        for point in report.get('sync_points',()) if point['device_id'] in identities)
    return ScoreTiming(report['reference_tempo'],quantize=enabled,
                       end_sample=report['source_end_sample'],anchors=tuple(sorted(set(anchors))))
