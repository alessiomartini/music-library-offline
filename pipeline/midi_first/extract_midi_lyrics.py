#!/usr/bin/env python3
"""
Step 3m (alternate to align_lyrics.py) — lyric extraction from a source
MIDI's own embedded lyric events, for the MIDI-first path.

No audio, no forced alignment: a karaoke-style MIDI file already carries
per-syllable timing, hand-authored against a real recording, on the exact
same tick timeline as its notes. This step only has to parse that text
(see midi_track_utils.parse_karaoke_syllables for the exact rules) and
attach each syllable to whichever working/<slug>/vocal-events.json note
(produced by import_karaoke_midi.py) is sounding at that tick — reusing
the shared note_utils.find_note_index unmodified, since it's already
generic over ticks regardless of where the notes came from.

A note commonly ends up with more than one syllable attached (`lyrics` is
a list, not a single entry): the karaoke text was hand-timed against the
recording, not quantized to the transcribed note grid, so several nearby
syllable ticks legitimately land on (or nearest to) the same note more
often than not. **Tried and reverted 2026-09-22:** forcing a one-syllable-
per-note assignment (a "claimed notes" set, matched with or without a
forward-only search cursor) looked like the right fix for "buchi, mancano
sillabe" reported on the real "Anna e Marco" output, but measured against
that same file it made placement much *worse* (13 unplaced syllables before
-> 179-181 after): most of what looked like erroneous stacking is actually
a real note legitimately carrying multiple syllables, and forcing
uniqueness just pushed the extra syllables past the tolerance instead of
placing them anywhere. The actual cause of the reported gaps turned out to
be downstream, in the web renderer (ScoreViewer.tsx), which only ever drew
`lyrics[0]` and silently dropped the rest — fixed there instead; see that
file's history.

The text-parsing rules follow the common "Soft Karaoke" convention but
have not been verified against every source site's variant — check the
output against the source MIDI by ear/eye for a new song before trusting
it (see docs/FUTURE-ARCHITECTURE.md's MIDI-first section).

Writes working/<slug>/aligned-lyrics.json — same shape as align_lyrics.py's
output, plus "syncMethod": "midi-native".

Run with:  python pipeline/midi_first/extract_midi_lyrics.py <slug>
"""
import argparse
import json
import sys
from pathlib import Path

import mido

import midi_track_utils as mtu

sys.path.insert(0, str(Path(__file__).parent.parent))  # pipeline/ — shared constants.py, note_utils.py, etc.
from constants import PPQ
from note_utils import find_note_index

REPO_ROOT = Path(__file__).parent.parent.parent

# MIDI-authored lyric ticks should land essentially on the real note (this
# is parsing, not acoustic-model-imprecise recognition) — a much tighter
# tolerance than align_lyrics.py's 1.5-second-derived one.
DEFAULT_MAX_GAP_TICKS = PPQ // 8  # a 32nd note


def safe_print(message: str) -> None:
    encoding = sys.stdout.encoding or "ascii"
    print(message.encode(encoding, errors="replace").decode(encoding))


def load_song_config(slug: str) -> dict:
    path = REPO_ROOT / "songs" / f"{slug}.json"
    if not path.exists():
        raise SystemExit(f"ERROR: no song config at {path}")
    return json.loads(path.read_text())


def extract(slug: str) -> None:
    config = load_song_config(slug)
    midi_source = config.get("midiSource") or {}
    midi_path = mtu.find_midi_source(slug, config)
    mid = mido.MidiFile(str(midi_path), clip=True)

    events_path = REPO_ROOT / "working" / slug / "vocal-events.json"
    if not events_path.exists():
        raise SystemExit(f"ERROR: {events_path} not found — run import_karaoke_midi.py first")
    vocal_events = sorted(json.loads(events_path.read_text())["events"], key=lambda e: e["start"])
    if not vocal_events:
        raise SystemExit(f"ERROR: no vocal notes in {events_path}")

    event_type = mtu.detect_lyric_event_type(mid, midi_source.get("lyricEventType", "auto"))
    lyrics_track = midi_source.get("lyricsTrack")
    if lyrics_track is None:
        lyrics_track = mtu.detect_lyrics_track(mid, event_type)
    if lyrics_track is None:
        raise SystemExit(f"ERROR: no {event_type!r} meta-events found in {midi_path}")

    raw_events = mtu.read_lyric_events(mid, lyrics_track, event_type)
    syllables = mtu.parse_karaoke_syllables(raw_events)
    safe_print(f"Parsed {len(syllables)} lyric event(s) ({sum(1 for s in syllables if s['melisma'])} melisma marker(s)) from track {lyrics_track}")

    ticks_per_beat = mid.ticks_per_beat
    max_gap_ticks = midi_source.get("maxLyricNoteGapTicks", DEFAULT_MAX_GAP_TICKS)

    notes_lyrics: list[list[dict]] = [[] for _ in vocal_events]
    unplaced = 0
    for syl in syllables:
        canonical_tick = round(syl["tick"] / ticks_per_beat * PPQ)
        note_index = find_note_index(vocal_events, canonical_tick, max_gap_ticks)
        if note_index is None:
            unplaced += 1
            continue
        entry = {"verse": syl["verse"]}
        if syl["melisma"]:
            entry["melisma"] = syl["melisma"]
        else:
            entry["text"] = syl["text"]
            entry["syllabic"] = syl["syllabic"]
        notes_lyrics[note_index].append(entry)

    aligned = []
    notes_with_lyrics = 0
    for event, lyrics in zip(vocal_events, notes_lyrics):
        entry = {"start": event["start"], "duration": event["duration"], "pitch": event["pitch"]}
        if lyrics:
            entry["lyrics"] = lyrics
            notes_with_lyrics += 1
        aligned.append(entry)

    safe_print(f"Placed {len(syllables) - unplaced}/{len(syllables)} lyric event(s) onto {notes_with_lyrics}/{len(vocal_events)} notes"
               + (f" ({unplaced} more than {max_gap_ticks} ticks from any note, unplaced)" if unplaced else ""))

    output_path = REPO_ROOT / "working" / slug / "aligned-lyrics.json"
    output_path.write_text(json.dumps({
        "ppq": PPQ,
        "aligned": aligned,
        "syncMethod": "midi-native",
        "total_syllables": len(syllables),
        "syllables_dropped": 0,
        "syllables_unplaced": unplaced,
        "notes_without_lyrics": len(vocal_events) - notes_with_lyrics,
    }, indent=2, ensure_ascii=False))
    safe_print(f"Wrote {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slug")
    args = parser.parse_args()
    extract(args.slug)
