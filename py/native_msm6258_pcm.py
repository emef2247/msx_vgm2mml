"""Known-reset MSM4 source decoding; native supply evidence remains intact."""
from fractions import Fraction
import math
from native_music import NativePCM

# Established x68k opna_adpcm._msm_next 10-bit transition.
_STEPS = tuple((16 * 11 ** i) // (10 ** i) for i in range(49))
_INDEX = (-1, -1, -1, -1, 2, 4, 6, 8)

# Target-policy properties of a playback, not source-evidence failures.
# Following the x68k source/target split, a playback whose only blockers are
# these still becomes a decoded asset: the reasons are recorded here and on
# the asset, and the target stage reports them as explicit losses (continuous
# stream delivery, start-pan retention, unfed gate tail) instead of the
# builder refusing the playback outright.
_POLICY_REASONS = frozenset((
    'irregular_byte_supply', 'rate_change_during_playback',
    'delivery_cadence_unresolved', 'not_independently_playable',
    'midplay_pan_change', 'source_gate_exceeds_finite_decoded_samples'))


def decode_msm4(encoded):
    """Known-reset, low-nibble-first 10-bit MSM4 scaled to signed16."""
    signal, index, result = -2, 0, []
    for byte in encoded:
        for nibble in (byte & 15, byte >> 4):
            step = _STEPS[index]
            delta = step // 8
            if nibble & 4: delta += step
            if nibble & 2: delta += step // 2
            if nibble & 1: delta += step // 4
            signal = max(-512, min(511, signal + (-delta if nibble & 8 else delta)))
            index = max(0, min(48, index + _INDEX[nibble & 7]))
            result.append(signal * 64)
    return tuple(result)


def add_msm6258_pcm(builder):
    analysis = builder.bundle['analyses'].get('msm6258')
    if analysis is None:
        builder.decisions.append(('msm6258_pcm_source_issue', 'analysis_unavailable'))
        return
    events = builder.bundle['events']
    def source_id(identity):
        if identity is not None and 0 <= identity < len(events):
            return events[identity].source_event_id
        return identity
    for issue in analysis.issues:
        builder.decisions.append(('msm6258_pcm_source_issue', issue.code,
                                  source_id(issue.source_event_id), issue.vgmticks))
    for observation in analysis.observations:
        builder.decisions.append(('msm6258_pcm_source_observation', observation.code,
                                  source_id(observation.source_event_id), observation.vgmticks))
    samples = {sample.sample_id: sample for sample in analysis.samples}
    transfers = tuple(analysis.transfers); supplies = tuple(analysis.stream_supplies)
    for p in analysis.playbacks:
        device = builder.device('msm6258', p.chip_instance)
        sample = samples.get(p.sample_id); reasons = list(p.issues)
        # Assets are never built from an uncertain source reconstruction:
        # hard reasons below keep the playback unresolved. Policy reasons
        # (see _POLICY_REASONS) describe delivery, not reconstruction.
        if analysis.issues: reasons.append('source_analysis_issues')
        if p.chip_instance: reasons.append('unsupported_chip_instance')
        if analysis.options & 8: reasons.append('unsupported_12bit_output')
        if not p.decoder_reset_known: reasons.append('decoder_reset_unknown')
        if not p.delivery_cadence_compatible: reasons.append('delivery_cadence_unresolved')
        if not p.independently_playable: reasons.append('not_independently_playable')
        if sample is None or not sample.encoded_bytes: reasons.append('missing_sample_bytes')
        elif sample.codec != 'msm6258-adpcm4-low-first': reasons.append('unsupported_source_codec')
        if p.rate_num <= 0 or p.rate_den <= 0: reasons.append('source_rate_unknown')
        if p.pan not in (0, 1, 2, 3): reasons.append('source_pan_unknown')
        pan_curve = tuple((c.vgmticks, c.pan, source_id(c.source_event_id))
            for c in analysis.controls if c.register == 2 and c.source_event_id in p.control_event_ids)
        if any(pan != p.pan for _, pan, _ in pan_curve): reasons.append('midplay_pan_change')
        if p.end_vgmticks <= p.start_vgmticks: reasons.append('empty_playback_interval')
        rate = Fraction(p.rate_num, p.rate_den) if p.rate_den > 0 else Fraction(0)
        end = p.end_vgmticks; exhaustion = None; gate_exceeded = False
        if sample is not None and rate > 0:
            exhaustion = Fraction(p.start_vgmticks) + len(sample.encoded_bytes)*2*44100/rate
            if end > exhaustion:
                if end-exhaustion <= 1:
                    end = math.floor(exhaustion)
                else:
                    # The decoded content is finite and shorter than the
                    # gate. Clip the asset to the decoded coverage and carry
                    # the excess as a target-policy reason (unfed tail); no
                    # held tail is invented.
                    reasons.append('source_gate_exceeds_finite_decoded_samples')
                    end = math.floor(exhaustion); gate_exceeded = True
        count = math.ceil(Fraction(end-p.start_vgmticks, 44100) * rate)
        if end <= p.start_vgmticks: reasons.append('finite_playback_below_source_tick')
        unique_reasons = tuple(dict.fromkeys(reasons))
        policy_reasons = tuple(r for r in unique_reasons if r in _POLICY_REASONS)
        if any(r not in _POLICY_REASONS for r in unique_reasons):
            builder.decisions.append(('msm6258_pcm_unresolved_playback', device.device_id,
                                      p.playback_id, unique_reasons))
            continue
        if policy_reasons:
            builder.decisions.append(('msm6258_pcm_stream_policy', device.device_id,
                                      p.playback_id, policy_reasons))
        if end != p.end_vgmticks and not gate_exceeded:
            builder.decisions.append(('msm6258_pcm_source_observation',
                'finite_exhaustion_endpoint_rounding', p.playback_id,
                p.end_vgmticks, end, exhaustion.numerator, exhaustion.denominator))
        decoded = decode_msm4(sample.encoded_bytes)
        identities = [p.first_source_event_id, *p.control_event_ids, p.last_source_event_id]
        identities.extend(t.source_event_id for t in transfers[p.transfer_start:p.transfer_end]
                          if t.chip_instance == p.chip_instance)
        identities.extend(s.source_event_id for s in supplies[p.stream_transfer_start:p.stream_transfer_end]
                          if s.chip_instance == p.chip_instance)
        builder.pcm_assets.append(NativePCM(
            f'{device.device_id}:playback:{p.playback_id}', device.device_id,
            p.start_vgmticks, end, float(rate), decoded[:count],
            tuple(dict.fromkeys(source_id(i) for i in identities)),
            (('source_encoding', sample.codec), ('source_sample_id', p.sample_id),
             ('source_sample_sha256', sample.sha256), ('source_playback_id', p.playback_id),
             ('source_rate_num', p.rate_num), ('source_rate_den', p.rate_den),
             ('source_gate_end_vgmticks', p.end_vgmticks),
             ('decoded_exhaustion_num', exhaustion.numerator),
             ('decoded_exhaustion_den', exhaustion.denominator),
             ('source_clock_hz', p.clock_hz), ('source_divider', p.divider), ('pan', p.pan),
             ('pan_interpretation', 'low2_disable_bits_0_both_1_left_2_right_3_mute'),
             ('source_pan_curve', pan_curve), ('source_options', analysis.options),
             ('decoder_reset_known', p.decoder_reset_known), ('reset_observed', p.reset_observed),
             ('reset_origin', p.reset_origin), ('codec_basis', 'x68k_msm4_10bit_signal_minus2_index0_scale64'),
             ('reconstruction', 'nominal_continuous_delivery_not_fifo_emulation'),
             ('duration_basis', 'ceil_gate_rate_clipped_finite_content_no_held_tail'),
             ('decoded_sample_count', len(decoded)), ('clipped_samples', len(decoded)-count),
             ('consumed_nibbles', p.consumed_nibbles), ('termination', p.termination),
             ('policy_reasons', policy_reasons))))
