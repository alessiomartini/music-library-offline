"""Shared, source-agnostic helpers for matching a lyric event's tick to a
note in a vocal-events.json-shaped list (used by both
pipeline/audio_first/align_lyrics.py and
pipeline/midi_first/extract_midi_lyrics.py — nothing path-specific belongs
here).
"""


def find_note_index(vocal_events: list[dict], tick: int, max_gap_ticks: int) -> int | None:
    """vocal_events: [{start, duration, ...}, ...], sorted by start. Returns
    the index of the note sounding at `tick`, or the nearest one when none
    is sounding and it starts within max_gap_ticks — otherwise None (very
    likely a real gap in the note list, not something to force an
    attachment onto)."""
    for i, event in enumerate(vocal_events):
        if event["start"] <= tick < event["start"] + event["duration"]:
            return i
    nearest_i = min(range(len(vocal_events)), key=lambda i: abs(vocal_events[i]["start"] - tick))
    nearest = vocal_events[nearest_i]
    if tick >= nearest["start"] + nearest["duration"]:
        gap = tick - (nearest["start"] + nearest["duration"])
    else:
        gap = nearest["start"] - tick
    return nearest_i if gap <= max_gap_ticks else None
