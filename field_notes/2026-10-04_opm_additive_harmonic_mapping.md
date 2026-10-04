# OPM additive harmonic mapping candidate (2026-10-04)

## User-provided source

The user supplied a screenshot of this post:
https://x.com/arith_rose/status/2093677528305242126
The web tool could not retrieve the post; the observation below is based on the
provided screenshot, not a independently fetched thread or its replies.

The author describes using YM2151 algorithm7, with four sine carriers at the
fundamental and3rd/5th/7th harmonics. A DFT tool measures harmonic balance and
maps it to operator output levels. This supplies a concrete additive approach
to approximating rectangular-wave timbres. It is distinct from inferring a
manual arranger's arbitrary FM algorithm and operator settings.

## What follows, and what does not

For an isolated, approximately periodic WAV tone, DFT/STFT measurements can
estimate the fundamental and amplitudes of chosen harmonics. With algorithm7
and selected frequency ratios fixed in advance, those measured amplitudes can
inform carrier TL choices. This is a constrained approximation, not a unique
reconstruction of an arbitrary FM patch. Polyphonic WAV, noisy attacks,
modulation, phase relationships and envelopes make general inversion harder.

An ideal symmetric square has odd harmonics with amplitude proportional to1/n.
Using four carriers at1/3/5/7 approximates that series; it does not reproduce all
harmonics or every pulse width. Relative levels from20*log10(1/n) are roughly
0,-9.54,-13.98,-16.90 dB before target TL quantization and overall scaling.
These numbers come from the ideal mathematical model, not from the post's
particular20 tones. For a pure additive prototype, disable feedback, detune,
LFO and noise; any later modulation must be handled separately.

SCC gives32 signed waveform samples directly. That is a more direct source
than rendering and measuring a mixed WAV. A possible independent Target stage:

1. Retain source waveform and period in native Segments.
2. Analyze one cycle with DFT; record DC and harmonic amplitude/phase separately.
3. Select up to four representable harmonic ratios and level approximations.
   Record selected/omitted components and target quantization in a target CSV.
4. Project source volume changes separately; do not confuse its musical envelope
   with the spectrum of the stored waveform.
5. Convert pitch for target clock and operator ratios, then generate MDX MML/VGM.
6. Compare spectra/envelopes and listen. Register/Key equivalence alone cannot
   assess likeness across different chip architectures.

This would be a generic SCC/PSG -> OPM timbre experiment. It is not implemented
here, and no native Segment values were replaced by estimated target values.
The private MSXGRA2S investigation provides comparison examples rather than
training truth or mandatory patch choices.
