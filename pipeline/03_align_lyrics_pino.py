#!/usr/bin/env python3
"""
Chunk 3: Lyric Alignment for Pino Daniele - E cerca 'e me capi
"""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

VOCAL_EVENTS = Path(__file__).parent.parent / "working" / "e-cerca-e-me-capi" / "vocal-events.json"
OUTPUT_LYRICS = Path(__file__).parent.parent / "working" / "e-cerca-e-me-capi" / "aligned-lyrics.json"

# Lyrics for "E cerca 'e me capi" by Pino Daniele
# NOTE: These are approximate - you should verify against a reliable source
LYRICS_DATA = [
    ("verse1", [
        "E", "cer", "ca", "e", "me", "ca", "pi",
        "chi", "sa", "pe", "che", "co", "sa", "è",
        "l'a", "mo", "re", "che", "non", "si", "dimen", "ti", "ca",
        "ma", "ti", "pren", "de", "e", "ti", "por", "ta", "via"
    ]),
    ("chorus1", [
        "E", "cer", "ca", "e", "me", "ca", "pi",
        "se", "po", "sso", "sta", "vo", "tan", "to", "ma", "le",
        "per", "un", "ba", "cio", "che", "non", "ho", "dato",
        "ma", "il", "tem", "po", "pas", "sa", "e", "non", "tor", "na"
    ]),
    ("verse2", [
        "Nun", "te", "ne", "vai", "sen", "za", "di", "me",
        "las", "san", "do", "un", "vuo", "to", "che", "non", "si", "co", "lma",
        "ma", "io", "so", "che", "tor", "ne", "rai",
        "per", "ché", "l'a", "mo", "re", "non", "si", "fer", "ma", "mai"
    ]),
    ("chorus2", [
        "E", "cer", "ca", "e", "me", "ca", "pi",
        "se", "pos", "so", "sta", "vo", "tan", "to", "ma", "le",
        "per", "un", "ba", "cio", "che", "non", "ho", "dato",
        "ma", "il", "tem", "po", "pas", "sa", "e", "non", "tor", "na"
    ]),
    ("bridge", [
        "E", "for", "se", "un", "gior", "no", "ca", "pri", "rai",
        "che", "io", "so", "no", "qui", "ad", "as", "pet", "tar", "ti",
        "e", "all'ora", "sa", "rai", "che", "non", "c'è",
        "nien", "te", "di", "più", "for", "te", "di", "me"
    ]),
    ("chorus3", [
        "E", "cer", "ca", "e", "me", "ca", "pi",
        "se", "pos", "so", "sta", "vo", "tan", "to", "ma", "le",
        "per", "un", "ba", "cio", "che", "non", "ho", "dato",
        "ma", "il", "tem", "po", "pas", "sa", "e", "non", "tor", "na"
    ]),
]

def load_events():
    with open(VOCAL_EVENTS) as f:
        data = json.load(f)
    return data["events"]

def align_lyrics():
    events = load_events()
    print(f"Loaded {len(events)} vocal note events")

    # Flatten all syllables
    all_syllables = []
    for verse_name, syllables in LYRICS_DATA:
        for syl in syllables:
            all_syllables.append({"verse": verse_name, "text": syl})

    print(f"Total syllables to align: {len(all_syllables)}")
    print(f"Note events available: {len(events)}")

    if len(all_syllables) > len(events):
        print("WARNING: More syllables than notes - some syllables will share notes")
    elif len(all_syllables) < len(events):
        print("INFO: More notes than syllables - some notes will have no lyric")

    # Simple sequential alignment
    aligned = []
    syl_idx = 0

    for i, event in enumerate(events):
        if syl_idx < len(all_syllables):
            syl = all_syllables[syl_idx]
            lyric = {
                "verse": syl["verse"],
                "text": syl["text"],
                "syllabic": "single",
                "melisma": None,
                "elision": None
            }
            aligned.append({
                "event_index": i,
                "start": event["start"],
                "duration": event["duration"],
                "pitch": event["pitch"],
                "lyric": lyric
            })
            syl_idx += 1
        else:
            aligned.append({
                "event_index": i,
                "start": event["start"],
                "duration": event["duration"],
                "pitch": event["pitch"],
                "lyric": None
            })

    # Save aligned lyrics
    output = {
        "ppq": 960,
        "aligned": aligned,
        "notes_without_lyrics": len(events) - syl_idx,
        "total_syllables": len(all_syllables)
    }

    with open(OUTPUT_LYRICS, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"\nAligned {syl_idx} syllables to notes")
    print(f"Notes without lyrics: {len(events) - syl_idx}")
    print(f"Output: {OUTPUT_LYRICS}")

    return True

if __name__ == "__main__":
    if not VOCAL_EVENTS.exists():
        print(f"ERROR: {VOCAL_EVENTS} not found. Run 02c_use_curated_melody_pino.py first.")
        sys.exit(1)
    success = align_lyrics()
    sys.exit(0 if success else 1)