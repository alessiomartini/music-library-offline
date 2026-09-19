#!/usr/bin/env python3
"""
Chunk 3: Lyric Alignment
Manual tool to align known lyrics to transcribed vocal notes.
For "Your Song" we know the lyrics, so we map them to the note events.
"""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

VOCAL_EVENTS = Path(__file__).parent.parent / "working" / "your-song" / "vocal-events.json"
OUTPUT_LYRICS = Path(__file__).parent.parent / "working" / "your-song" / "aligned-lyrics.json"

# Known lyrics for "Your Song" - verse by verse
# Format: list of (verse_name, list of syllables)
# Each syllable will be assigned to a note event in sequence
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

    # Simple sequential alignment: each syllable gets one note
    # For melismas (one syllable over multiple notes), we'd need manual marking
    aligned = []
    syl_idx = 0

    for i, event in enumerate(events):
        if syl_idx < len(all_syllables):
            syl = all_syllables[syl_idx]
            # Determine syllabic type
            # Simple heuristic: if it's the only syllable for this word part
            # For now, mark all as 'single' - user can edit later
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

    # Show first 20 aligned
    print("\nFirst 20 aligned:")
    for a in aligned[:20]:
        l = a["lyric"]
        if l:
            print(f"  [{a['start']:5d}] pitch={a['pitch']:3d} dur={a['duration']:4d} -> {l['verse']}: '{l['text']}' ({l['syllabic']})")
        else:
            print(f"  [{a['start']:5d}] pitch={a['pitch']:3d} dur={a['duration']:4d} -> (no lyric)")

    return True

if __name__ == "__main__":
    success = align_lyrics()
    sys.exit(0 if success else 1)