#!/usr/bin/env python3
"""
Step 3m/4m override — replace a MIDI-first song's lyrics and harmony with a
human-verified text+chord chart (e.g. an Accordi&Spartiti PDF, transcribed
by hand into corrections/<slug>/verified-source.json), while keeping the
source MIDI's own note timing.

Why: symbolic chord-template matching on raw MIDI notes
(extract_midi_harmony.py) and MIDI-authored lyric-tick placement
(extract_midi_lyrics.py) are each a first automatic pass with real error —
a verified chart, when Alessio has found and checked one, is a better
source for *what* the words and chords are. But the chart has no tick
timing of its own (a PDF has lines, not timestamps), and the MIDI has no
reliable chord recognition — so this step takes the chart's words and
chords and the MIDI's note timing and lines them up, word by word.

corrections/<slug>/verified-source.json shape:
{
  "lines": [
    {"words": ["Anna", "come", ...], "chords": {"0": "SIb", "4": "DOm7"}},
    ...
  ]
}
`chords` maps a word's index within its line (as a string key, since JSON
object keys are strings) to an Italian chord symbol written above it in the
chart — see harmony_utils.parse_italian_chord.

Algorithm:
1. Reconstruct the MIDI-derived word sequence from working/<slug>/
   aligned-lyrics.json — same begin/middle/end/single grouping
   extract_midi_lyrics.py already produced — each word carrying the list of
   note indices it was assigned to (its notes' start ticks are what we
   actually want out of this).
2. Align the verified chart's word sequence against it with
   difflib.SequenceMatcher on normalized (lowercased, punctuation-stripped)
   text — this tolerates the two sequences disagreeing here and there
   (a mistranscribed MIDI word, a line the chart merges differently)
   without needing an exact match everywhere, and keeps both sequences in
   their original order (neither list is sorted or reordered first).
3. For each matched pair, write the chart's word (correct spelling) onto
   the first note of the MIDI word's note span, and clear the rest of that
   span's lyrics (ScoreViewer.tsx then renders them as held/"_", since
   they're mid-word notes with no MIDI-native melisma marker to say
   otherwise). A chord attached to that word becomes a harmony event at
   that first note's start tick.
4. Unmatched chart words (no confident MIDI counterpart) are left unplaced
   and reported, never guessed at. Unmatched MIDI words keep no lyric text
   (the chart, not the MIDI's own guess, is the source of truth once this
   step runs) — also reported, so a bad alignment is visible, not silent.

Writes working/<slug>/aligned-lyrics.json and working/<slug>/harmony-
events.json, overwriting extract_midi_lyrics.py's / extract_midi_harmony.py's
output for this song. Re-run those two scripts first (in that order) before
this one if the source MIDI or vocal transcription changed.

Run with:  python pipeline/midi_first/apply_verified_source.py <slug>
"""
import argparse
import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))  # pipeline/ — shared constants.py, harmony_utils.py
from constants import PPQ
from harmony_utils import dedupe_adjacent_within_measure, parse_italian_chord, retile_durations

REPO_ROOT = Path(__file__).parent.parent.parent


def safe_print(message: str) -> None:
    encoding = sys.stdout.encoding or "ascii"
    print(message.encode(encoding, errors="replace").decode(encoding))


def normalize_word(word: str) -> str:
    """Lowercase, accent-insensitive-ish, punctuation-stripped comparison
    key — chart and MIDI text disagree on capitalization, trailing commas,
    and elision apostrophes far more often than on the letters themselves."""
    word = word.lower().replace("'", "").replace("’", "")
    return re.sub(r"[^a-zàèéìòù]", "", word)


class MidiWord:
    def __init__(self, text: str, note_indices: list[int]):
        self.text = text
        self.note_indices = note_indices


def reconstruct_midi_words(aligned: list[dict]) -> list[MidiWord]:
    """Groups aligned-lyrics.json's per-note syllable entries back into
    words using their syllabic tags — the inverse of the flush_word grouping
    in midi_track_utils.parse_karaoke_syllables. A note stacked with several
    syllables (see extract_midi_lyrics.py's docstring) contributes each of
    its entries as if they were separate notes at that same note index."""
    words: list[MidiWord] = []
    current_text = ""
    current_notes: list[int] = []

    def flush():
        nonlocal current_text, current_notes
        if current_text:
            words.append(MidiWord(current_text, current_notes))
        current_text = ""
        current_notes = []

    for note_index, note in enumerate(aligned):
        for entry in note.get("lyrics") or []:
            text = entry.get("text")
            if text is None:  # a melisma continuation marker, not a syllable
                continue
            syllabic = entry.get("syllabic", "single")
            current_text += text
            current_notes.append(note_index)
            if syllabic in ("end", "single"):
                flush()
    flush()
    return words


# How far ahead of the current position to look for each verified line's
# words. A song's verses repeat the same handful of words ("Anna", "Marco",
# "che", "non", ...) many times — matching one flat SequenceMatcher run over
# the whole song let a word steal a match (and its chord) from a same-
# spelled word several verses away. Matching one line at a time, in a
# window just ahead of where the previous line left off, keeps each match
# local to where that line actually falls in the song.
ALIGN_WINDOW_WORDS = 25


def align_verified_lines(
    midi_words: list[MidiWord], verified_lines: list[list[str]],
) -> list[tuple[int, int, int]]:
    """Returns [(midi_word_index, line_index, word_index_in_line), ...] for
    matched words, in order. Advances a cursor through midi_words one
    verified line at a time so each line's words are only matched against a
    nearby window, not the whole song."""
    midi_norm = [normalize_word(w.text) for w in midi_words]
    pairs: list[tuple[int, int, int]] = []
    cursor = 0
    for line_index, words in enumerate(verified_lines):
        window = midi_norm[cursor:cursor + ALIGN_WINDOW_WORDS]
        line_norm = [normalize_word(w) for w in words]
        matcher = SequenceMatcher(None, window, line_norm, autojunk=False)
        line_pairs = []
        for block in matcher.get_matching_blocks():
            for k in range(block.size):
                line_pairs.append((cursor + block.a + k, line_index, block.b + k))
        pairs.extend(line_pairs)
        # Advance past this line's last match so the next line's window
        # starts after it — even with no match, advance by the line's own
        # length as a best-effort estimate rather than leaving the window
        # stuck in place.
        cursor = (line_pairs[-1][0] + 1) if line_pairs else min(cursor + len(words), len(midi_words))
    return pairs


def apply(slug: str) -> None:
    working_dir = REPO_ROOT / "working" / slug
    aligned_path = working_dir / "aligned-lyrics.json"
    aligned_data = json.loads(aligned_path.read_text())
    aligned = aligned_data["aligned"]

    source_path = REPO_ROOT / "corrections" / slug / "verified-source.json"
    if not source_path.exists():
        raise SystemExit(f"ERROR: no verified source at {source_path}")
    source = json.loads(source_path.read_text())

    verified_lines: list[list[str]] = [line["words"] for line in source["lines"]]
    total_verified_words = sum(len(words) for words in verified_lines)

    midi_words = reconstruct_midi_words(aligned)
    pairs = align_verified_lines(midi_words, verified_lines)
    matched_midi = {mi for mi, _, _ in pairs}

    # Start every note with no lyrics; matched words below repopulate them.
    for note in aligned:
        note.pop("lyrics", None)

    harmony_events: list[dict] = []
    config = json.loads((REPO_ROOT / "songs" / f"{slug}.json").read_text())

    for midi_index, line_index, word_index in pairs:
        midi_word = midi_words[midi_index]
        verified_text = source["lines"][line_index]["words"][word_index]
        # A word's note_indices can repeat the same note (its syllables were
        # originally stacked on one physical note, see
        # reconstruct_midi_words) and, separately, two different matched
        # words can each resolve to that same note — append rather than
        # overwrite, so ScoreViewer's joinNoteLyrics (frontend) shows both,
        # and dedupe so a word doesn't clear its own just-written entry off
        # its own first note when its later "notes" are really the same one.
        unique_notes = list(dict.fromkeys(midi_word.note_indices))
        first_note_index = unique_notes[0]
        entry = {"verse": f"line{line_index}", "text": verified_text, "syllabic": "single"}
        aligned[first_note_index].setdefault("lyrics", []).append(entry)
        for note_index in unique_notes[1:]:
            aligned[note_index].pop("lyrics", None)

        chord_text = source["lines"][line_index]["chords"].get(str(word_index))
        if chord_text:
            event = parse_italian_chord(chord_text)
            event["start"] = aligned[first_note_index]["start"]
            harmony_events.append(event)

    unmatched_midi = len(midi_words) - len(matched_midi)
    unmatched_verified = total_verified_words - len(pairs)
    safe_print(f"Matched {len(pairs)} word(s); {unmatched_midi}/{len(midi_words)} MIDI word(s) and "
               f"{unmatched_verified}/{total_verified_words} verified word(s) left unmatched")
    if unmatched_verified:
        matched_owners = {(li, wi) for _, li, wi in pairs}
        unmatched_texts = [
            words[wi] for li, words in enumerate(verified_lines) for wi in range(len(words))
            if (li, wi) not in matched_owners
        ]
        safe_print(f"  Unplaced verified words (no confident MIDI match): {unmatched_texts}")

    aligned_data["aligned"] = aligned
    aligned_data["correctedFrom"] = "verified-source"
    aligned_path.write_text(json.dumps(aligned_data, indent=2, ensure_ascii=False))
    safe_print(f"Wrote {aligned_path}")

    harmony_events.sort(key=lambda e: e["start"])
    harmony_events = retile_durations(harmony_events, final_duration=PPQ)
    ts = config["timeSignature"]
    measure_length_ticks = ts["numerator"] * PPQ * 4 // ts["denominator"]
    harmony_events = dedupe_adjacent_within_measure(harmony_events, measure_length_ticks)
    harmony_events = retile_durations(harmony_events, final_duration=PPQ)

    harmony_path = working_dir / "harmony-events.json"
    harmony_path.write_text(json.dumps({"ppq": PPQ, "tempo_bpm": config["tempoBpm"], "harmony": harmony_events}, indent=2))
    safe_print(f"{len(harmony_events)} harmony event(s) -> {harmony_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slug")
    args = parser.parse_args()
    apply(args.slug)
