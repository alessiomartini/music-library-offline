"""Shared constants for the offline pipeline scripts (used by both
pipeline/audio_first/ and pipeline/midi_first/ — nothing path-specific
belongs here).

PPQ (ticks per quarter note) must be identical across every script that
produces or consumes tick values, and must match the web app's
SCORE_PPQ (src/lib/score.ts). It used to be copied by hand into each
script; two of those copies drifted into a different (wrong) convention,
which is what caused the your-song tick-unit bug. Import it from here
instead of redefining it.
"""

PPQ = 960

# General MIDI "Voice Oohs". MuseScore's MIDI import auto-splits a
# piano-family program (GM 0-7) across a grand staff, which scatters a
# monophonic vocal line's harmonic/separation-bleed artifacts (Basic Pitch
# occasionally detects a spurious simultaneous second pitch, and a
# karaoke-MIDI vocal line can genuinely overlap itself briefly too) into a
# spurious second staff instead of leaving them as ordinary overlaps to
# resolve. A non-piano program keeps the import on a single staff. Shared
# by audio_first/transcribe_vocals.py (Basic Pitch's output) and
# midi_first/import_karaoke_midi.py (a source MIDI's vocal channel).
VOICE_PROGRAM = 53

# Vocal distribution from a recording (audio_first/vocal_distribution.py).
VOCAL_FMIN, VOCAL_FMAX = "C2", "C6"   # pYIN search range for the sung f0
VOCAL_HOP_S = 0.01                    # f0 frame hop, seconds
VOCAL_VOICED_PROB = 0.1               # on top of pYIN's own voiced decision; 0.5 dropped most real singing
VOCAL_MEDIAN_FRAMES = 7               # pitch smoothing (70 ms) so vibrato doesn't flip the rounded note
VOCAL_MIN_RUN_S = 0.05                # shorter single-note runs are stem bleed or octave errors
VOCAL_MIN_SHARE = 0.01                # a note needs this share of the singing time to set the range
VOCAL_CORE_PERCENTILES = (0.1, 0.9)   # "core" range: where 80% of the singing time sits
VOCAL_DURATION_TOLERANCE_S = 5        # YouTube vs any Deezer version of the song, to accept a search result

# Demucs window overlap: 0.1 instead of the default 0.25 is ~17% faster on CPU and gave the
# same vocal histogram (overlap 0.993 on E cerca 'e me capi, 2026-10-16).
DEMUCS_OVERLAP = 0.1
VOCAL_CONSENSUS_MAX_DIFF_S = 25       # ...or 3+ results agree on a duration this close to a Deezer version
