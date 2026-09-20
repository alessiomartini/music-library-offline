#!/usr/bin/env python3
"""
Step 5 — MusicXML assembly.

Combines a song's vocal events (with aligned lyrics) and harmony events
into a two-part (Voice + Harmony) MusicXML document via music21, using
metadata (title, composer, key, tempo, time signature) from
songs/<slug>.json.

Writes working/<slug>/lead-sheet.musicxml.

Run with:  python pipeline/assemble_musicxml.py <slug>
"""
import argparse
import json
from pathlib import Path

from music21 import clef, harmony as m21harmony, instrument, key as m21key, metadata, meter, note, pitch as m21pitch, stream, tempo

REPO_ROOT = Path(__file__).parent.parent
PPQ = 960
NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
QUALITY_TO_SYMBOL = {
    'major': '', 'minor': 'm', 'dominant7': '7', 'major7': 'maj7',
    'minor7': 'm7', 'halfDiminished7': 'm7b5', 'augmented': 'aug',
    'sus4': 'sus4', 'dominant7sus4': '7sus4', 'major6': '6',
}


def ticks_to_ql(ticks: int) -> float:
    return ticks / PPQ


def assemble(slug: str) -> None:
    config = json.loads((REPO_ROOT / "songs" / f"{slug}.json").read_text())
    working_dir = REPO_ROOT / "working" / slug

    vocal_events = json.loads((working_dir / "vocal-events.json").read_text())["events"]
    aligned = json.loads((working_dir / "aligned-lyrics.json").read_text())["aligned"]
    harmony_events = json.loads((working_dir / "harmony-events.json").read_text())["harmony"]

    print(f"Vocal events: {len(vocal_events)}")
    print(f"Aligned lyrics: {len([a for a in aligned if a['lyric']])}")
    print(f"Harmony events: {len(harmony_events)}")

    lyrics_by_start = {a["start"]: a["lyric"] for a in aligned if a["lyric"]}

    score = stream.Score()
    score.metadata = metadata.Metadata()
    score.metadata.title = config["title"]
    score.metadata.composer = config["composer"]
    if config.get("lyricist"):
        score.metadata.lyricist = config["lyricist"]

    ts = config["timeSignature"]
    score.insert(0, tempo.MetronomeMark(number=config["tempoBpm"]))
    score.insert(0, meter.TimeSignature(f"{ts['numerator']}/{ts['denominator']}"))
    score.insert(0, m21key.Key(config["originalKey"].replace('b', '-'), config.get("mode", "major")))

    voice_part = stream.Part()
    voice_part.id = "voice"
    voice_part.partName = "Voice"
    voice_part.instrument = instrument.Vocalist()
    voice_part.insert(0, clef.TrebleClef())

    for event in vocal_events:
        p = m21pitch.Pitch()
        p.midi = event["pitch"]
        n = note.Note(p)
        n.duration.quarterLength = ticks_to_ql(event["duration"])
        n.offset = ticks_to_ql(event["start"])

        lyric = lyrics_by_start.get(event["start"])
        if lyric:
            n.lyrics.append(note.Lyric(text=lyric["text"], number=1, syllabic=lyric.get("syllabic", "single")))

        voice_part.insert(n.offset, n)
    voice_part.makeMeasures(inPlace=True)

    harmony_part = stream.Part()
    harmony_part.id = "harmony"
    harmony_part.partName = "Harmony"
    harmony_part.instrument = instrument.Piano()

    for h in harmony_events:
        symbol = f"{NOTE_NAMES[h['root']]}{QUALITY_TO_SYMBOL.get(h['quality'], '')}"
        if h.get("slashBass") is not None:
            symbol += f"/{NOTE_NAMES[h['slashBass']]}"

        cs = m21harmony.ChordSymbol(symbol)
        dur_ql = ticks_to_ql(h["duration"])
        cs.duration.quarterLength = dur_ql if dur_ql > 0 else 1.0
        cs.offset = ticks_to_ql(h["start"])
        harmony_part.insert(cs.offset, cs)
    harmony_part.makeMeasures(inPlace=True)

    score.insert(0, voice_part)
    score.insert(0, harmony_part)

    output_path = working_dir / "lead-sheet.musicxml"
    score.write("musicxml", fp=str(output_path))
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slug")
    args = parser.parse_args()
    assemble(args.slug)
