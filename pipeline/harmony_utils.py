"""Shared, source-agnostic helpers for tiling and cleaning up a list of
timed chord events (used by both pipeline/audio_first/extract_harmony.py
and pipeline/midi_first/extract_midi_harmony.py — nothing path-specific
belongs here).
"""


def retile_durations(events: list[dict], final_duration: int) -> list[dict]:
    """Derive each event's duration from the next event's start (exact
    tiling by construction — see extract_harmony.py's "Harmony tick-tiling"
    note in docs/FUTURE-ARCHITECTURE.md for why this matters); the last
    event gets `final_duration`."""
    for i, event in enumerate(events):
        event["duration"] = events[i + 1]["start"] - event["start"] if i + 1 < len(events) else final_duration
    return [e for e in events if e["duration"] > 0]


def smooth_short_events(events: list[dict], min_duration_ticks: int) -> list[dict]:
    """Merges an event shorter than min_duration_ticks into the preceding
    one (extending its duration to absorb it) instead of keeping it as a
    separate "chord change". Added 2026-09-22 after the MIDI-first path's
    symbolic chord matching (extract_midi_harmony.py), run on a real full-
    band arrangement ("Anna e Marco"), produced a chord change roughly
    every note onset — far more than a listener would perceive — because
    a passing/non-harmonic tone or two instruments attacking a few ticks
    apart each briefly forms its own "chord" under onset-grouping alone.
    Requires `events` to already have real `duration` values (see
    retile_durations). The first event, however short, is always kept —
    there's nothing before it to merge into."""
    if not events:
        return []
    smoothed = [dict(events[0])]
    for event in events[1:]:
        if event["duration"] < min_duration_ticks:
            smoothed[-1]["duration"] += event["duration"]
        else:
            smoothed.append(dict(event))
    return smoothed


def suggest_key(pitches: list[int]) -> tuple[str, str]:
    """Best-effort (tonic name, mode) guess from a list of MIDI pitch
    numbers, via music21's key-analysis (a real pitch-class-distribution
    algorithm — Krumhansl-Schmuckler-style — not "whichever chord root
    appears most often", which conflates the tonic with whatever chord the
    harmony happens to linger on longest). A starting suggestion for
    songs/<slug>.json's hand-authored originalKey/mode fields, not an
    authoritative answer — confirm by ear before trusting it."""
    from music21 import stream, note

    s = stream.Stream()
    for pitch in pitches:
        s.append(note.Note(pitch))
    analyzed = s.analyze("key")
    return analyzed.tonic.name, analyzed.mode


# Italian solfège note names -> pitch class. Sorted longest-first so "SOL"
# (3 letters) is tried before a shorter name could wrongly match a prefix of
# it (nothing else collides here, but this keeps the matching order honest).
_ITALIAN_NOTE_PC = {"SOL": 7, "DO": 0, "RE": 2, "MI": 4, "FA": 5, "LA": 9, "SI": 11}
_ITALIAN_NOTE_NAMES = sorted(_ITALIAN_NOTE_PC, key=len, reverse=True)

# Chord suffix (after the note name + accidental) -> this schema's
# ChordQuality (src/lib/score.ts's isValidChordQuality). Longer suffixes
# first so "m7" isn't consumed as "m" leaving a stray "7". "7+" is this
# style of Italian chart's spelling for a major seventh (the "+" marks the
# 7th degree itself as major, not the 5th — confirmed with Alessio against
# a real chart), not an augmented triad.
_ITALIAN_CHORD_SUFFIXES = [
    ("m7", "minor7"), ("maj7", "major7"), ("7+", "major7"),
    ("6", "major6"), ("m", "minor"), ("7", "dominant7"), ("4", "sus4"), ("", "major"),
]


def _parse_italian_note_name(text: str, pos: int) -> tuple[int, int]:
    """Returns (pitch class, index just past the parsed name+accidental)."""
    for name in _ITALIAN_NOTE_NAMES:
        if text[pos:pos + len(name)].upper() == name:
            pc = _ITALIAN_NOTE_PC[name]
            i = pos + len(name)
            if text[i:i + 1] == "b":
                pc = (pc - 1) % 12
                i += 1
            elif text[i:i + 1] == "#":
                pc = (pc + 1) % 12
                i += 1
            return pc, i
    raise ValueError(f"cannot parse an Italian note name at {text!r}[{pos}:]")


def parse_italian_chord(text: str) -> dict:
    """Parses an Italian lead-sheet chord symbol (e.g. "SIb7+", "DOm7/SIb",
    "FA4") into {"root": pitch class, "quality": ChordQuality, "slashBass":
    pitch class (only if present)} — the same shape extract_midi_harmony.py
    already produces, so callers can treat a verified-chart chord and a
    symbolically-detected one identically."""
    text = text.strip()
    slash_bass = None
    if "/" in text:
        text, bass_text = text.split("/", 1)
        slash_bass, _ = _parse_italian_note_name(bass_text, 0)

    root, i = _parse_italian_note_name(text, 0)
    suffix = text[i:]
    quality = next((q for suf, q in _ITALIAN_CHORD_SUFFIXES if suffix == suf), None)
    if quality is None:
        raise ValueError(f"unrecognized chord suffix {suffix!r} in {text!r}")

    result = {"root": root, "quality": quality}
    if slash_bass is not None:
        result["slashBass"] = slash_bass
    return result


def dedupe_adjacent_within_measure(events: list[dict], measure_length_ticks: int) -> list[dict]:
    """Drop a chord event that repeats the one immediately before it, but
    only when both land in the same measure (e.g. a bar reading A A C D
    becomes A C D). A repeat that crosses a measure boundary — the same
    chord restated at the top of a new bar, e.g. bar N ending on D and bar
    N+1 starting on D again — is left alone: that's the ordinary way a
    chart shows the harmony continuing into a new measure, not a duplicate
    to clean up.
    """
    deduped = []
    for event in events:
        if deduped:
            previous = deduped[-1]
            same_chord = (previous["root"] == event["root"] and previous["quality"] == event["quality"]
                          and previous.get("slashBass") == event.get("slashBass"))
            same_measure = (previous["start"] // measure_length_ticks) == (event["start"] // measure_length_ticks)
            if same_chord and same_measure:
                continue
        deduped.append(event)
    return deduped
