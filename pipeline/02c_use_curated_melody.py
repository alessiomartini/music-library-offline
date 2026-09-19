#!/usr/bin/env python3
"""
Use curated.musicxml as the authoritative melody (it was manually verified).
Extract events and align lyrics to it.
"""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

from music21 import converter

CURATED_MUSICXML = Path(__file__).parent.parent / "working" / "your-song" / "curated.musicxml"
OUTPUT_EVENTS = Path(__file__).parent.parent / "working" / "your-song" / "vocal-events.json"
OUTPUT_ALIGNED = Path(__file__).parent.parent / "working" / "your-song" / "aligned-lyrics.json"

PPQ = 960

# Lyrics data (same as before)
LYRICS_DATA = [
    ("verse1", [
        "It's", "a", "lit", "tle", "bit", "fun", "ny",
        "this", "fee", "ling", "in", "side",
        "I'm", "not", "one", "of", "those", "who", "can",
        "eas", "i", "ly", "hide",
        "I", "don't", "have", "much", "mo", "ney",
        "but", "boy", "if", "I", "did",
        "I'd", "buy", "a", "big", "house", "where",
        "we", "both", "could", "live"
    ]),
    ("verse2", [
        "If", "I", "was", "a", "sculp", "tor",
        "but", "then", "a", "gain", "no",
        "or", "a", "man", "who", "makes", "po", "tions",
        "in", "a", "tra", "vel", "ling", "show",
        "I", "know", "it's", "not", "much",
        "but", "it's", "the", "best", "I", "can", "do",
        "My", "gift", "is", "my", "song",
        "and", "this", "one's", "for", "you"
    ]),
    ("chorus1", [
        "And", "you", "can", "tell", "ev", "ry", "bo", "dy",
        "this", "is", "your", "song",
        "It", "may", "be", "qui", "te", "sim", "ple",
        "but", "now", "that", "it's", "done",
        "I", "hope", "you", "don't", "mind",
        "I", "hope", "you", "don't", "mind",
        "that", "I", "put", "down", "in", "words",
        "how", "won", "der", "ful", "life", "is",
        "while", "you're", "in", "the", "world"
    ]),
    ("verse3", [
        "I", "sat", "on", "the", "roof",
        "and", "kicked", "off", "the", "moss",
        "well", "a", "few", "of", "the", "verses",
        "well", "they've", "got", "me", "quite", "cross",
        "but", "the", "sun", "been", "qui", "te", "kind",
        "while", "I", "wrote", "this", "song",
        "it's", "for", "peo", "ple", "like", "you",
        "that", "keep", "it", "turn", "ing", "on"
    ]),
    ("chorus2", [
        "So", "ex", "cuse", "me", "for", "get", "ting",
        "but", "these", "things", "I", "do",
        "you", "see", "I've", "for", "got", "ten",
        "if", "they're", "green", "or", "they're", "blue",
        "an", "y", "way", "the", "thing", "is",
        "what", "I", "re", "al", "ly", "mean",
        "yours", "are", "the", "sweet", "est", "eyes",
        "I've", "ev", "er", "seen"
    ]),
    ("chorus3", [
        "And", "you", "can", "tell", "ev", "ry", "bo", "dy",
        "this", "is", "your", "song",
        "It", "may", "be", "qui", "te", "sim", "ple",
        "but", "now", "that", "it's", "done",
        "I", "hope", "you", "don't", "mind",
        "I", "hope", "you", "don't", "mind",
        "that", "I", "put", "down", "in", "words",
        "how", "won", "der", "ful", "life", "is",
        "while", "you're", "in", "the", "world"
    ]),
    ("outro", [
        "I", "hope", "you", "don't", "mind",
        "I", "hope", "you", "don't", "mind",
        "that", "I", "put", "down", "in", "words",
        "how", "won", "der", "ful", "life", "is",
        "while", "you're", "in", "the", "world"
    ])
]

def extract_from_curated():
    print("Loading curated.musicxml...")
    score = converter.parse(str(CURATED_MUSICXML))

    voice_part = score.parts[0]  # Only one part: Voice
    notes = list(voice_part.flatten().notes)

    print(f"Total notes/rests in curated: {len(notes)}")

    # Extract note events (skip rests)
    events = []
    for n in notes:
        if n.isNote:
            # offset is in quarter notes, convert to ticks
            start_ticks = int(round(n.offset * PPQ / 4.0))
            dur_ticks = int(round(n.duration.quarterLength * PPQ / 4.0))
            pitch = n.pitch.midi

            events.append({
                "start": start_ticks,
                "duration": dur_ticks,
                "pitch": pitch,
                "velocity": 0.8,  # default
                "kind": "note"
            })

    # Sort by start
    events.sort(key=lambda e: e["start"])

    print(f"Extracted {len(events)} note events")
    print(f"Pitch range: {min(e['pitch'] for e in events)} - {max(e['pitch'] for e in events)}")

    # Detect tempo from the score (curated has no explicit tempo, use ~72 BPM from original)
    # The audit mentioned tempo changes from 63-52 BPM, but for v1 we use constant
    tempo_bpm = 72

    # Save events
    output_data = {
        "ppq": PPQ,
        "tempo_bpm": tempo_bpm,
        "events": events
    }

    with open(OUTPUT_EVENTS, 'w') as f:
        json.dump(output_data, f, indent=2)

    print(f"Events saved to: {OUTPUT_EVENTS}")

    # Print first 20
    for e in events[:20]:
        print(f"  start={e['start']:5d}, dur={e['duration']:4d}, pitch={e['pitch']:3d}")

    return events, tempo_bpm

def align_lyrics(events):
    print("\nAligning lyrics...")

    # Flatten syllables
    all_syllables = []
    for verse_name, syllables in LYRICS_DATA:
        for syl in syllables:
            all_syllables.append({"verse": verse_name, "text": syl})

    print(f"Total syllables: {len(all_syllables)}")
    print(f"Total note events: {len(events)}")

    # Align sequentially
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

    output = {
        "ppq": PPQ,
        "aligned": aligned,
        "notes_without_lyrics": len(events) - syl_idx,
        "total_syllables": len(all_syllables)
    }

    with open(OUTPUT_ALIGNED, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"Aligned {syl_idx} syllables to notes")
    print(f"Notes without lyrics: {len(events) - syl_idx}")
    print(f"Output: {OUTPUT_ALIGNED}")

    return aligned

if __name__ == "__main__":
    events, tempo = extract_from_curated()
    align_lyrics(events)
    print("\nDone!")