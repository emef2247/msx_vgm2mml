"""Shared MGSDRV frontend settings; native source data is never normalized."""
from dataclasses import dataclass
from fractions import Fraction

DEFAULT_FM_STATE_MS = 1.0
DEFAULT_NORMALIZATION_MS = 8.0


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

    def __post_init__(self):
        if self.psg_part not in ('all', 'melody', 'rhythm'):
            raise ValueError("psg_part must be all, melody, or rhythm")
        sample_threshold(self.effective_normalization_ms, '--normalization-ms')
        sample_threshold(self.effective_fm_state_ms, '--fm-state-ms')

    @property
    def enabled(self):
        return self.normalize_lengths or self.normalization_ms is not None or self.fm_state_ms is not None

    @property
    def effective_fm_state_ms(self):
        return DEFAULT_FM_STATE_MS if self.fm_state_ms is None else self.fm_state_ms

    @property
    def effective_normalization_ms(self):
        return DEFAULT_NORMALIZATION_MS if self.normalization_ms is None else self.normalization_ms

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
        return result

    def as_dict(self):
        return dict(normalize_lengths_requested=bool(self.normalize_lengths),
                    normalization_enabled=bool(self.enabled),
                    normalization_ms_requested=None if self.normalization_ms is None else float(self.normalization_ms),
                    fm_state_ms_requested=None if self.fm_state_ms is None else float(self.fm_state_ms),
                    normalization_ms=float(self.effective_normalization_ms),
                    fm_state_ms=float(self.effective_fm_state_ms),
                    normalization_samples=sample_threshold(self.effective_normalization_ms, '--normalization-ms'),
                    fm_state_samples=sample_threshold(self.effective_fm_state_ms, '--fm-state-ms'),
                    normalization_scope='shared OPLL-anchored target clock; no whole-gate omission',
                    fm_state_scope='OPLL melody within accepted normalization only; PSG/SCC curves unchanged',
                    force=bool(self.force), dump_passes=bool(self.dump_passes),
                    enhance_drums=bool(self.enhance_drums),
                    enhance_rhythm=bool(self.enhance_drums), psg_part=self.psg_part,
                    software_volume_curves=bool(self.software_volume_curves))
