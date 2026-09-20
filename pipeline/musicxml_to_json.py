#!/usr/bin/env python3
"""
Step 6 — MusicXML to normalized JSON.

Reads working/<slug>/lead-sheet.musicxml back for the voice part, and
working/<slug>/harmony-events.json directly for harmony, and emits the
schemaVersion 1 envelope the web app's loadScoreJson
(src/lib/scoreLoader.ts) expects, to output/json/<slug>.json — the file
that gets copied into the web repo's src/data/songs/.

Harmony is read from the JSON intermediate rather than re-derived from the
assembled MusicXML: music21 writes a ChordSymbol's <harmony> tag once per
measure it spans (splitting it at barlines the same way it splits a tied
note), which duplicates the tag and — for a lead sheet with this many chord
changes — was observed to corrupt the part's own measure offsets partway
through the score on re-parse, silently truncating the harmony read back
from it. harmony-events.json is the tick-accurate, already-tiled source
extract_harmony.py produced it from in the first place; reading it directly
avoids that whole round-trip.

Run with:  python pipeline/musicxml_to_json.py <slug>
"""
import argparse
import json
from pathlib import Path

from music21 import converter, note

REPO_ROOT = Path(__file__).parent.parent
PPQ = 960


def extract_voice_part(voice_part) -> list[dict]:
    events = []
    for element in voice_part.flatten().notes:
        start_ticks = int(round(element.offset * PPQ))
        dur_ticks = int(round(element.duration.quarterLength * PPQ))

        if isinstance(element, note.Note):
            lyrics = [
                {
                    "verse": f"verse{ly.number}" if ly.number else "verse1",
                    "text": ly.text,
                    "syllabic": ly.syllabic if ly.syllabic else "single",
                }
                for ly in element.lyrics
            ]
            event = {"kind": "note", "start": start_ticks, "duration": dur_ticks, "pitch": element.pitch.midi}
            if lyrics:
                event["lyrics"] = lyrics
            events.append(event)
        elif isinstance(element, note.Rest):
            events.append({"kind": "rest", "start": start_ticks, "duration": dur_ticks})

    events.sort(key=lambda e: e["start"])
    return events


def load_harmony_events(slug: str) -> list[dict]:
    path = REPO_ROOT / "working" / slug / "harmony-events.json"
    if not path.exists():
        return []
    return json.loads(path.read_text())["harmony"]


def build_measures(time_sig: dict, total_ticks: int) -> list[dict]:
    measure_duration = time_sig["numerator"] * PPQ * 4 // time_sig["denominator"]
    measures = []
    start = 0
    while start < total_ticks:
        measures.append({"start": start, "duration": measure_duration})
        start += measure_duration
    return measures


def convert(slug: str) -> None:
    config = json.loads((REPO_ROOT / "songs" / f"{slug}.json").read_text())
    musicxml_path = REPO_ROOT / "working" / slug / "lead-sheet.musicxml"
    print("Loading MusicXML...")
    score = converter.parse(str(musicxml_path))

    voice_part = next((p for p in score.parts if p.id == 'voice' or p.partName == 'Voice'), None)
    if voice_part is None:
        raise SystemExit("ERROR: Voice part not found in MusicXML")

    voice_events = extract_voice_part(voice_part)
    harmony_events = load_harmony_events(slug)
    print(f"Voice events: {len(voice_events)}")
    print(f"Harmony events: {len(harmony_events)}")

    ts = config["timeSignature"]
    all_events = voice_events + harmony_events
    max_end = max((e["start"] + e["duration"] for e in all_events), default=PPQ * ts["numerator"])
    measures = build_measures(ts, max_end)
    print(f"Measures: {len(measures)}")

    score_json = {
        "schemaVersion": 1,
        "score": {
            "ppq": PPQ,
            "originalKey": config["originalKey"],
            "timeSignature": ts,
            "measures": measures,
            "tempo": {"bpm": config["tempoBpm"]},
            "parts": [{"id": "voice", "name": "Voice", "role": "voice", "events": voice_events}],
            "harmony": harmony_events,
        },
    }

    output_path = REPO_ROOT / "output" / "json" / f"{slug}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(score_json, indent=2))
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slug")
    args = parser.parse_args()
    convert(args.slug)
