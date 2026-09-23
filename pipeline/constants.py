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
