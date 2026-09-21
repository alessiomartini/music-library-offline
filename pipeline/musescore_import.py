"""
MuseScore 4 CLI integration.

Converts a MIDI file into quantized note events by shelling out to
`MuseScore4.exe --score-elements <midi>`, which imports the MIDI with
MuseScore's own adaptive quantization (full polyphony, tuplet detection, tie
handling) and prints the resulting score as JSON directly — no MusicXML/
music21 round-trip needed. This replaced this pipeline's own fixed-grid
snap-to-eighth-note quantization, which produced far worse notation than
opening the same raw MIDI directly in MuseScore.

Each event's duration is derived from the gap to the next event in the same
(staff, voice) — not from the nominal duration name MuseScore reports:
inside a tuplet, "beat" already reflects the note's real (compressed)
position, but `duration: {"name": "Eighth"}` alone does not reflect the
tuplet scaling. Retiling from the next event's start sidesteps needing to
interpret MuseScore's Tuplet markers at all (the same trick
extract_harmony.py uses for chord durations).

Requires MuseScore 4 installed. The executable is located via the
MUSESCORE4_PATH environment variable, the default Windows install path, or
mscore/mscore4portable on PATH, in that order.
"""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from constants import PPQ

DEFAULT_WINDOWS_PATH = r"C:\Program Files\MuseScore 4\bin\MuseScore4.exe"

DURATION_NAME_TO_QUARTERS = {
    "Whole": 4.0, "Half": 2.0, "Quarter": 1.0, "Eighth": 0.5,
    "16th": 0.25, "32nd": 0.125, "64th": 0.0625, "128th": 0.03125,
}

PITCH_CLASS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

SAFE_GRID_TICKS = PPQ // 16  # a 64th note

_NOTE_NAME_RE = re.compile(r"^([A-G])([b#]*)(-?\d+)$")


def find_musescore() -> str:
    env_path = os.environ.get("MUSESCORE4_PATH")
    if env_path:
        return env_path
    if Path(DEFAULT_WINDOWS_PATH).exists():
        return DEFAULT_WINDOWS_PATH
    for name in ("mscore4portable", "mscore", "musescore4", "MuseScore4"):
        found = shutil.which(name)
        if found:
            return found
    raise SystemExit(
        "ERROR: MuseScore 4 executable not found. Set the MUSESCORE4_PATH "
        "environment variable to its full path, or install it at the "
        f"default location ({DEFAULT_WINDOWS_PATH})."
    )


def note_name_to_midi(name: str) -> int:
    m = _NOTE_NAME_RE.match(name)
    if not m:
        raise ValueError(f"unrecognized MuseScore pitch name: {name!r}")
    step, accidental, octave = m.groups()
    pitch_class = PITCH_CLASS[step] + accidental.count("#") - accidental.count("b")
    return pitch_class + (int(octave) + 1) * 12


def duration_to_quarters(duration: dict) -> float:
    base = DURATION_NAME_TO_QUARTERS.get(duration.get("name", "Quarter"), 1.0)
    dots = duration.get("dots", 0)
    return base * (2 - 2 ** -dots) if dots else base


def _merge_ties(notes: list[dict]) -> list[dict]:
    """notes: [{start, duration, pitch, tied}], already sorted by start.
    Merge a note flagged tied with the next same-pitch note that starts
    exactly where it ends, extending duration and dropping the second."""
    by_pitch: dict[int, list[dict]] = {}
    for n in notes:
        by_pitch.setdefault(n["pitch"], []).append(n)

    merged = []
    for pitch, group in by_pitch.items():
        group.sort(key=lambda n: n["start"])
        i = 0
        while i < len(group):
            current = dict(group[i])
            j = i + 1
            while current.pop("tied", False) and j < len(group) and group[j]["start"] == current["start"] + current["duration"]:
                current["duration"] += group[j]["duration"]
                current["tied"] = group[j].get("tied", False)
                j += 1
            current.pop("tied", None)
            merged.append(current)
            i = j
    merged.sort(key=lambda n: (n["start"], n["pitch"]))
    return merged


def import_midi(midi_path: Path, measure_length_quarters: float) -> list[dict]:
    """Returns [{start, duration, pitch}] in ticks, one event per pitch
    (a chord becomes one event per note it contains), derived from
    MuseScore's own MIDI import and quantization."""
    exe = find_musescore()
    result = subprocess.run(
        [exe, "--score-elements", str(midi_path)],
        capture_output=True, text=True, check=True,
    )
    parts = json.loads(result.stdout)
    elements = parts[0]["elements"] if parts else []

    groups = []
    for el in elements:
        if el["type"] not in ("Note", "Chord", "Rest"):
            continue
        beat = el["measureIdx"] * measure_length_quarters + el["beat"]
        voice_key = (el["staffIdx"], el["voiceIdx"])
        fallback_quarters = duration_to_quarters(el.get("duration", {}))
        if el["type"] == "Note":
            pitches = [(note_name_to_midi(el["name"]), el.get("tied") == "true")]
        elif el["type"] == "Chord":
            pitches = [(note_name_to_midi(n["name"]), n.get("tied") == "true") for n in el["notes"]]
        else:
            pitches = None
        groups.append({"voice": voice_key, "beat": beat, "pitches": pitches, "fallback_quarters": fallback_quarters})

    by_voice: dict[tuple, list[dict]] = {}
    for g in groups:
        by_voice.setdefault(g["voice"], []).append(g)

    raw_notes = []
    for voice_groups in by_voice.values():
        voice_groups.sort(key=lambda g: g["beat"])
        for i, g in enumerate(voice_groups):
            if g["pitches"] is None:
                continue
            # Cap at the nominal (name+dots) duration: MuseScore sometimes
            # places a note in a voice that stays otherwise empty for a long
            # stretch, so "gap to the next event in this voice" alone can be
            # wildly too long. Still prefer that gap when it's *shorter* than
            # nominal, since that's what correctly reflects a tuplet's real
            # (compressed) duration — "beat" already accounts for tuplet
            # scaling, but duration.name alone does not.
            next_beat = voice_groups[i + 1]["beat"] if i + 1 < len(voice_groups) else None
            gap_quarters = (next_beat - g["beat"]) if next_beat is not None else None
            duration_quarters = min(gap_quarters, g["fallback_quarters"]) if gap_quarters else g["fallback_quarters"]
            # Snap to a 64th-note grid: an arbitrary tick value doesn't
            # necessarily land on a cleanly notatable quarterLength (ticks /
            # PPQ), and music21's automatic duration-typing can respond to
            # one that doesn't by inferring a degenerate tuplet music21
            # itself then can't write to MusicXML ("Cannot convert '2048th'
            # duration"). A 64th note is finer than anything these songs
            # actually need, so this only ever corrects otherwise-unusable
            # values, not real musical content.
            start = round(g["beat"] * PPQ / SAFE_GRID_TICKS) * SAFE_GRID_TICKS
            end = round((g["beat"] + duration_quarters) * PPQ / SAFE_GRID_TICKS) * SAFE_GRID_TICKS
            duration = max(end - start, SAFE_GRID_TICKS)
            for pitch, tied in g["pitches"]:
                raw_notes.append({"start": start, "duration": duration, "pitch": pitch, "tied": tied})

    raw_notes.sort(key=lambda n: (n["start"], n["pitch"]))
    return _merge_ties(raw_notes)


def enforce_monophonic(events: list[dict]) -> list[dict]:
    """Collapse time-overlapping notes to a single active line: MuseScore
    sometimes places a handful of scattered notes in a second voice even for
    audio that's musically monophonic (a solo vocal line) — residual
    harmonics or separation bleed that Basic Pitch picks up as a second
    simultaneous pitch, not a real second voice. Keeps whichever note is
    already sounding and drops anything that starts before it ends,
    independent of which MuseScore voice/staff it came from."""
    events = sorted(events, key=lambda e: e["start"])
    kept = []
    active_end = -1
    for event in events:
        if event["start"] < active_end:
            continue
        kept.append(event)
        active_end = event["start"] + event["duration"]
    return kept
