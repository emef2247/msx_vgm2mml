"""YM2612 musical gates: the shared FM gate builder with MD part names.

mucomMD2vgm assigns FM channels 1-6 to parts A, B, C, H, I, J — the
same letters MUCOM88 uses for OPNA FM — so the OPNA builder's default
mapping applies unchanged.

Adapted from mucom88_vgm2mml (py/musical_hal/native_imports/
opn2_music.py): this package's opna_music.build_fm_gates already
hardcodes the ABCHIJ letters and takes no parts argument.
"""
from .opna_music import audit_fm_key_edges, build_fm_gates, dump_gates  # noqa: F401


def build_opn2_gates(analysis):
    return build_fm_gates(analysis)
