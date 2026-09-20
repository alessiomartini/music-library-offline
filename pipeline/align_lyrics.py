#!/usr/bin/env python3
"""
Step 3 — lyric alignment.

Sequentially assigns each syllable from songs/<slug>.json's "lyrics" to the
next vocal note event, in order. This is a simple heuristic (one syllable
per melody note, in order) — it does not detect melismas, elisions, or
multiple lyric lines; those need the syllabic/verse fields in the song
config to be set by hand (see the "syllabic" values on each syllable).

Writes working/<slug>/aligned-lyrics.json.

Run with:  python pipeline/align_lyrics.py <slug>
"""
import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
PPQ = 960


def align(slug: str) -> None:
    config = json.loads((REPO_ROOT / "songs" / f"{slug}.json").read_text())
    events_path = REPO_ROOT / "working" / slug / "vocal-events.json"
    if not events_path.exists():
        raise SystemExit(f"ERROR: {events_path} not found — run transcribe_vocals.py first")
    events = json.loads(events_path.read_text())["events"]

    syllables = [
        {"verse": verse["verse"], **syl}
        for verse in config["lyrics"]
        for syl in verse["syllables"]
    ]

    print(f"Vocal note events: {len(events)}")
    print(f"Syllables in song config: {len(syllables)}")
    if len(syllables) > len(events):
        print("WARNING: more syllables than notes — some syllables will not be placed")
    elif len(syllables) < len(events):
        print("INFO: more notes than syllables — some notes will have no lyric")

    aligned = []
    for i, event in enumerate(events):
        lyric = None
        if i < len(syllables):
            syl = syllables[i]
            lyric = {"verse": syl["verse"], "text": syl["text"], "syllabic": syl.get("syllabic", "single")}
        aligned.append({
            "event_index": i,
            "start": event["start"],
            "duration": event["duration"],
            "pitch": event["pitch"],
            "lyric": lyric,
        })

    placed = min(len(events), len(syllables))
    output_path = REPO_ROOT / "working" / slug / "aligned-lyrics.json"
    output_path.write_text(json.dumps({
        "ppq": PPQ,
        "aligned": aligned,
        "notes_without_lyrics": len(events) - placed,
        "total_syllables": len(syllables),
    }, indent=2))
    print(f"Aligned {placed} syllables -> {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slug")
    args = parser.parse_args()
    align(args.slug)
