#!/usr/bin/env python3
"""
Step 6 — MusicXML to normalized JSON.

Reads working/<slug>/aligned-lyrics.json and working/<slug>/harmony-events.json
directly — not working/<slug>/lead-sheet.musicxml — and emits the
schemaVersion 1 envelope the web app's loadScoreJson
(src/lib/scoreLoader.ts) expects, to output/json/<slug>.json — the file
that gets copied into the web repo's src/data/songs/.

Both parts are read from their JSON intermediates rather than re-derived
from the assembled MusicXML. For harmony, music21 writes a ChordSymbol's
<harmony> tag once per measure it spans (splitting it at barlines the same
way it splits a tied note), which duplicates the tag and — for a lead sheet
with this many chord changes — was observed to corrupt the part's own
measure offsets partway through the score on re-parse, silently truncating
the harmony read back from it. The JSON intermediates are the tick-accurate
sources extract_harmony.py/align_lyrics.py already produced; reading them
directly avoids that whole class of round-trip bug. lead-sheet.musicxml is
still written by assemble_musicxml.py and useful for visual inspection, but
is no longer this step's input.

Run with:  python pipeline/musicxml_to_json.py <slug>
"""
import argparse
import json
from pathlib import Path

from constants import PPQ

REPO_ROOT = Path(__file__).parent.parent


def build_voice_events(aligned: list[dict]) -> list[dict]:
    events = []
    previous_end = None
    for entry in aligned:
        start, duration = entry["start"], entry["duration"]
        if previous_end is not None and start > previous_end:
            events.append({"kind": "rest", "start": previous_end, "duration": start - previous_end})

        event = {"kind": "note", "start": start, "duration": duration, "pitch": entry["pitch"]}
        if entry.get("lyrics"):
            # A lyric entry either carries real text (the audio-first path's
            # and most MIDI-first syllables) or, MIDI-first only, a bare
            # melisma continuation marker with no text of its own (see
            # extract_midi_lyrics.py) — ScoreLyric validation (src/lib/score.ts)
            # requires one or the other, never both missing.
            event["lyrics"] = []
            for ly in entry["lyrics"]:
                lyric = {"verse": ly["verse"]}
                if ly.get("melisma"):
                    lyric["melisma"] = ly["melisma"]
                if "text" in ly and ly["text"] is not None:
                    lyric["text"] = ly["text"]
                    lyric["syllabic"] = ly.get("syllabic", "single")
                if ly.get("elision"):
                    lyric["elision"] = ly["elision"]
                event["lyrics"].append(lyric)
        if "tie" in entry:
            event["tie"] = entry["tie"]
        events.append(event)
        previous_end = start + duration
    return events


def load_harmony_events(slug: str) -> list[dict]:
    path = REPO_ROOT / "working" / slug / "harmony-events.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))["harmony"]


def build_measures(time_sig: dict, total_ticks: int) -> list[dict]:
    measure_duration = time_sig["numerator"] * PPQ * 4 // time_sig["denominator"]
    measures = []
    start = 0
    while start < total_ticks:
        measures.append({"start": start, "duration": measure_duration})
        start += measure_duration
    return measures


def convert(slug: str) -> None:
    config = json.loads((REPO_ROOT / "songs" / f"{slug}.json").read_text(encoding="utf-8"))
    working_dir = REPO_ROOT / "working" / slug
    aligned_data = json.loads((working_dir / "aligned-lyrics.json").read_text(encoding="utf-8"))
    aligned = aligned_data["aligned"]
    lyric_sync_method = aligned_data.get("syncMethod", "derived")

    voice_events = build_voice_events(aligned)
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
            "lyricSyncMethod": lyric_sync_method,
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
