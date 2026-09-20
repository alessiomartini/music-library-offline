#!/usr/bin/env python3
"""
Step 3 — lyric alignment.

Assigns each syllable from songs/<slug>.json's "lyrics" to the next vocal
note event, in order, within each verse — not across the whole song in one
pass. Two heuristics reduce (but do not eliminate) the mismatch between note
count and syllable count that a real melody with tied notes and melismas
always has:

1. A tied note (see transcribe_vocals.py's tie extraction) is one sustained
   musical note split across a barline into two written events. Only the
   first (tie type "start") consumes a syllable; the continuation/stop
   note(s) get no lyric, the same way a single untied note would.

2. Syllables are assigned per verse, not in one pass across the whole
   song. The alignment resets at each verse boundary instead of letting a
   melisma's extra notes permanently shift every syllable after it for the
   rest of the song. Verse boundaries are guessed by matching each verse's
   expected cumulative position (by syllable count, as a fraction of the
   song's total syllables) against the nearest actual rest in the melody —
   printed below for a quick check against the recording.

Neither heuristic detects a real melisma (one syllable held across several
*different* pitches, no tie) within a verse: that still falls back to
"leftover notes get no lyric" at the end of the verse's syllable list, same
as the old whole-song behavior but now contained to one verse instead of
cascading through the rest of the song. Getting melismas fully right needs
either audio/text forced alignment or hand-marked note-spans in the song
config — see docs/FUTURE-ARCHITECTURE.md's melisma model.

Writes working/<slug>/aligned-lyrics.json.

Run with:  python pipeline/align_lyrics.py <slug>
"""
import argparse
import json
from pathlib import Path

from constants import PPQ

REPO_ROOT = Path(__file__).parent.parent


def find_verse_boundaries(events: list[dict], verse_syllable_counts: list[int]) -> list[int]:
    """Return, for each verse after the first, the event index it should start at.

    Matches the verse's expected position (cumulative syllables so far /
    total syllables) against the nearest actual rest between two assignable
    (non-tie-continuation) events, so a boundary never falls in the middle
    of a legato run.
    """
    assignable_indices = [i for i, e in enumerate(events) if e.get("tie", {}).get("type") not in ("continue", "stop")]
    total_syllables = sum(verse_syllable_counts)
    total_assignable = len(assignable_indices)

    # Candidate boundaries: a rest between consecutive assignable events,
    # recorded as (how many assignable slots precede it, its event index).
    candidates = []
    for pos, idx in enumerate(assignable_indices[:-1]):
        next_idx = assignable_indices[pos + 1]
        prev_end = events[idx]["start"] + events[idx]["duration"]
        if events[next_idx]["start"] > prev_end:
            candidates.append((pos + 1, next_idx))

    boundaries = []
    cumulative = 0
    for count in verse_syllable_counts[:-1]:
        cumulative += count
        target_fraction = cumulative / total_syllables
        best = min(candidates, key=lambda c: abs(c[0] / total_assignable - target_fraction))
        boundaries.append(best[1])
    return boundaries


def align(slug: str) -> None:
    config = json.loads((REPO_ROOT / "songs" / f"{slug}.json").read_text())
    events_path = REPO_ROOT / "working" / slug / "vocal-events.json"
    if not events_path.exists():
        raise SystemExit(f"ERROR: {events_path} not found — run transcribe_vocals.py first")
    events = sorted(json.loads(events_path.read_text())["events"], key=lambda e: e["start"])

    verses = config["lyrics"]
    verse_syllable_counts = [len(v["syllables"]) for v in verses]
    print(f"Vocal note events: {len(events)}")
    print(f"Verses: {[v['verse'] for v in verses]}, syllable counts: {verse_syllable_counts}")

    boundaries = find_verse_boundaries(events, verse_syllable_counts) if len(verses) > 1 else []
    segment_bounds = [0, *boundaries, len(events)]
    tempo_bpm = config["tempoBpm"]
    for i, idx in enumerate(boundaries):
        seconds = events[idx]["start"] / PPQ * 60.0 / tempo_bpm
        print(f"  guessed boundary before verse {verses[i + 1]['verse']!r}: event {idx}, ~{seconds:.1f}s — check against the recording")

    aligned = []
    total_notes_without_lyrics = 0
    for verse, start_idx, end_idx in zip(verses, segment_bounds, segment_bounds[1:]):
        segment = events[start_idx:end_idx]
        syllables = verse["syllables"]
        syl_i = 0
        placed = 0
        for event in segment:
            lyric = None
            is_tie_continuation = event.get("tie", {}).get("type") in ("continue", "stop")
            if not is_tie_continuation and syl_i < len(syllables):
                syl = syllables[syl_i]
                lyric = {"verse": verse["verse"], "text": syl["text"], "syllabic": syl.get("syllabic", "single")}
                syl_i += 1
                placed += 1
            entry = {"start": event["start"], "duration": event["duration"], "pitch": event["pitch"], "lyric": lyric}
            if "tie" in event:
                entry["tie"] = event["tie"]
            aligned.append(entry)
        if syl_i < len(syllables):
            print(f"WARNING: verse {verse['verse']!r} has {len(syllables) - syl_i} syllables left over — more syllables than assignable notes in this segment")
        without_lyric = sum(1 for e in segment if not e.get("tie", {}).get("type") in ("continue", "stop")) - placed
        total_notes_without_lyrics += without_lyric + sum(1 for e in segment if e.get("tie", {}).get("type") in ("continue", "stop"))
        print(f"  {verse['verse']!r}: {len(segment)} notes, {placed}/{len(syllables)} syllables placed")

    output_path = REPO_ROOT / "working" / slug / "aligned-lyrics.json"
    output_path.write_text(json.dumps({
        "ppq": PPQ,
        "aligned": aligned,
        "notes_without_lyrics": total_notes_without_lyrics,
        "total_syllables": sum(verse_syllable_counts),
    }, indent=2))
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slug")
    args = parser.parse_args()
    align(args.slug)
