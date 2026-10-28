"""Shared MGSDRV frontend settings; native source data is never normalized."""
from dataclasses import dataclass
from fractions import Fraction

DEFAULT_FM_STATE_MS = 1.0
DEFAULT_NORMALIZATION_MS = 8.0


CURVE_OPTION_NAMES = ('psg_state_ms', 'scc_state_ms', 'curve_volume_error', 'curve_mean_error')


def add_curve_arguments(parser):
    """Keep the experimental score/curve switches identical across frontends."""
    parser.add_argument('--score-guided-loops', action='store_true',
                        help='Guide target repeats with pitch/duration/rest/attack structure (opt-in)')
    for chip in ('psg', 'scc'):
        parser.add_argument('--'+chip+'-state-ms', type=float, default=None,
                            help=f'Maximum contiguous changed {chip.upper()} volume interval in ms (default: off)')
    parser.add_argument('--curve-volume-error', type=float, default=None,
                        help='Required maximum native volume-register deviation, 0..15; not acoustic amplitude')
    parser.add_argument('--curve-mean-error', type=float, default=None,
                        help='Required duration-weighted mean volume-register deviation, 0..15')


def curve_option_values(args):
    return dict(score_guided_loops=getattr(args, 'score_guided_loops', False),
                **{name: getattr(args, name, None) for name in CURVE_OPTION_NAMES})


def nonnegative(value, option):
    try:
        number = Fraction(str(value))
    except (ValueError, ZeroDivisionError) as error:
        raise ValueError(f'{option} must be finite and nonnegative') from error
    if number < 0:
        raise ValueError(f'{option} must be finite and nonnegative')
    return number


def sample_threshold(milliseconds, option):
    try:
        value = Fraction(str(milliseconds)) * Fraction(441, 10)
    except (ValueError, ZeroDivisionError) as error:
        raise ValueError(f'{option} must be finite and positive') from error
    if value < 1:
        raise ValueError(f'{option} must span at least one source sample')
    return value.numerator // value.denominator


@dataclass(frozen=True)
class MgsOptions:
    normalize_lengths: bool = False
    normalization_ms: float | None = None
    fm_state_ms: float | None = None
    force: bool = False
    dump_passes: bool = False
    enhance_drums: bool = False
    psg_part: str = 'all'
    software_volume_curves: bool = False
    score_guided_loops: bool = False
    psg_state_ms: float | None = None
    scc_state_ms: float | None = None
    curve_volume_error: float | None = None
    curve_mean_error: float | None = None
    score_normalize: bool = False
    score_tempo: int = 225

    def __post_init__(self):
        from score_normalization import score_tempo
        score_tempo(self.score_tempo)
        if self.score_normalize and self.normalize_lengths:
            raise ValueError('--score-normalize and --normalize-lengths select different timing algorithms')
        if self.psg_part not in ('all', 'melody', 'rhythm'):
            raise ValueError("psg_part must be all, melody, or rhythm")
        sample_threshold(self.effective_normalization_ms, '--normalization-ms')
        sample_threshold(self.effective_fm_state_ms, '--fm-state-ms')
        for name in CURVE_OPTION_NAMES:
            value = getattr(self, name)
            if value is not None:
                number = nonnegative(value, '--'+name.replace('_', '-'))
                if name.startswith('curve_') and number > 15:
                    raise ValueError('--'+name.replace('_', '-')+' must be within native volume-register levels 0..15')
        active = any(getattr(self, name) is not None and float(getattr(self, name)) > 0
                     for name in ('psg_state_ms', 'scc_state_ms'))
        if active:
            if self.curve_volume_error is None or self.curve_mean_error is None:
                raise ValueError('Curve approximation requires explicit --curve-volume-error and --curve-mean-error')

    @property
    def enabled(self):
        if self.score_normalize:return False
        return self.normalize_lengths or self.normalization_ms is not None or self.fm_state_ms is not None

    @property
    def effective_fm_state_ms(self):
        return DEFAULT_FM_STATE_MS if self.fm_state_ms is None else self.fm_state_ms

    @property
    def effective_normalization_ms(self):
        return DEFAULT_NORMALIZATION_MS if self.normalization_ms is None else self.normalization_ms

    @property
    def curve_approx_options(self):
        return {chip: dict(state_ms=float(getattr(self, chip+'_state_ms')),
                           max_volume_error=float(self.curve_volume_error), max_mean_error=float(self.curve_mean_error))
                for chip in ('psg', 'scc') if getattr(self, chip+'_state_ms') is not None
                and float(getattr(self, chip+'_state_ms')) > 0}

    def cli_args(self):
        result = ['--normalize-lengths'] if self.normalize_lengths else []
        for name in ('normalization_ms', 'fm_state_ms'):
            if getattr(self, name) is not None:
                result += ['--' + name.replace('_', '-'), str(getattr(self, name))]
        if self.force:
            result.append('--force')
        if self.dump_passes:
            result.append('--dump-passes')
        if self.enhance_drums:
            result.append('--enhance-rhythm')
        if self.psg_part != 'all':
            result.append('--psg-' + self.psg_part + '-only')
        result.append('--software-volume-curves' if self.software_volume_curves
                      else '--no-software-volume-curves')
        result.extend(self.curve_cli_args())
        if self.score_normalize:result+=['--score-normalize','--score-tempo',str(self.score_tempo)]
        return result

    def curve_cli_args(self):
        result = ['--score-guided-loops'] if self.score_guided_loops else []
        for name in CURVE_OPTION_NAMES:
            if getattr(self, name) is not None:
                result += ['--'+name.replace('_', '-'), str(getattr(self, name))]
        return result

    def as_dict(self):
        return dict(normalize_lengths_requested=bool(self.normalize_lengths),
                    score_normalize=self.score_normalize,score_tempo=self.score_tempo,
                    normalization_enabled=bool(self.enabled),
                    normalization_ms_requested=None if self.normalization_ms is None else float(self.normalization_ms),
                    fm_state_ms_requested=None if self.fm_state_ms is None else float(self.fm_state_ms),
                    normalization_ms=float(self.effective_normalization_ms),
                    fm_state_ms=float(self.effective_fm_state_ms),
                    normalization_samples=sample_threshold(self.effective_normalization_ms, '--normalization-ms'),
                    fm_state_samples=sample_threshold(self.effective_fm_state_ms, '--fm-state-ms'),
                    normalization_scope='shared OPLL-anchored target clock; no whole-gate omission',
                    fm_state_scope='OPLL melody within accepted normalization only; PSG/SCC approximation is independent',
                    force=bool(self.force), dump_passes=bool(self.dump_passes),
                    enhance_drums=bool(self.enhance_drums),
                    enhance_rhythm=bool(self.enhance_drums), psg_part=self.psg_part,
                    software_volume_curves=bool(self.software_volume_curves),
                    score_guided_loops=bool(self.score_guided_loops),
                    psg_state_ms=None if self.psg_state_ms is None else float(self.psg_state_ms),
                    scc_state_ms=None if self.scc_state_ms is None else float(self.scc_state_ms),
                    curve_volume_error=None if self.curve_volume_error is None else float(self.curve_volume_error),
                    curve_mean_error=None if self.curve_mean_error is None else float(self.curve_mean_error),
                    curve_approximation=self.curve_approx_options,
                    curve_error_units='native volume-register levels 0..15; not acoustic amplitude',
                    curve_approximation_scope='fixed-tone/fixed-wave volume only; native source and score boundaries retained')
