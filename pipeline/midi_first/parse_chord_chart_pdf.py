#!/usr/bin/env python3
"""
Chunk 3 (feeds apply_verified_source.py) — mechanically extract a verified
text+chord chart from an Accordi&Spartiti-style PDF into
corrections/<slug>/verified-source.json, instead of a person reading the
PDF and typing out which word each chord sits above.

Why this exists: the first "verified-source.json" for Anna e Marco (this
session, 2026-09-22) was transcribed by hand, estimating from the rendered
PDF which word a chord symbol was positioned above. Re-checked against a
mechanical extraction: several chords were attached to the wrong word (e.g.
the PDF's "SIb ... DOm7" line over "Anna come sono tante, Anna permalosa"
has DOm7's left edge exactly aligned with "permalosa", not the second
"Anna" as the hand transcription guessed) — eyeballing column position from
a proportional-width PDF render is unreliable. This PDF is vector text, not
a scanned image, so every character carries its own real x/y position
(pdfplumber's page.extract_words()); a chord's word attachment can be
computed from that directly instead of estimated.

Algorithm:
1. Extract words per page with their (x0, x1, top) via pdfplumber.
2. Group words into lines by `top` (a tolerance, not exact equality —
   words on one visual line can differ by a fraction of a point).
3. Classify each line: "chord" if every word on it parses as a valid
   Italian chord symbol (harmony_utils.parse_italian_chord doesn't raise)
   and it has few words (a chord line is short); "lyric" otherwise.
4. Only lines from the first chord line onward, and before a line whose
   text is exactly "CREDITS" (this site's chart footer marker), are song
   content — skips the title/artist header and the credits/legal
   boilerplate without hardcoding today's specific song's title text.
5. Walk lines in order, accumulating the most recent chord line's chords.
   Each lyric line becomes one verified-source.json entry, with the
   pending chords attached by nearest horizontal overlap (chord [x0,x1] vs
   word [x0,x1]) and then cleared — a lyric line with no chord line
   directly above it (harmony carries over from before) gets no chords,
   same as a person reading the chart would read it. A chord line with no
   lyric line to attach to (a purely instrumental interlude, e.g.
   "DOm7/SIb SIb7+ DOm7/SIb" alone between verses) has no word to anchor
   its chords to and is intentionally not represented — verified-
   source.json is word-anchored by design (see apply_verified_source.py).

Run with:  python pipeline/midi_first/parse_chord_chart_pdf.py <pdf_path> <slug>
Writes corrections/<slug>/verified-source.json and prints a line-by-line
report (chord -> word it was attached to) for a quick visual check against
the source PDF before trusting it.
"""
import argparse
import json
import sys
from pathlib import Path

import pdfplumber

sys.path.insert(0, str(Path(__file__).parent.parent))  # pipeline/ — shared harmony_utils.py
from harmony_utils import parse_italian_chord

REPO_ROOT = Path(__file__).parent.parent.parent

# Two words are "the same line" if their top y-coordinates are within this
# many PDF points of each other — comfortably less than the ~15pt gap
# between a chord line and its lyric line, generous enough for normal
# same-line font-rendering jitter.
LINE_Y_TOLERANCE = 3.0

# A chord line in this chart style is always a handful of short symbols,
# never a full sentence — bounds how many "chord-shaped" words in a row we
# trust as a chord line rather than a coincidence.
MAX_CHORD_LINE_WORDS = 8

CREDITS_MARKER = "CREDITS"


def safe_print(message: str) -> None:
    encoding = sys.stdout.encoding or "ascii"
    print(message.encode(encoding, errors="replace").decode(encoding))


def group_words_into_lines(words: list[dict]) -> list[list[dict]]:
    lines: list[list[dict]] = []
    for word in words:
        if lines and abs(lines[-1][0]["top"] - word["top"]) <= LINE_Y_TOLERANCE:
            lines[-1].append(word)
        else:
            lines.append([word])
    for line in lines:
        line.sort(key=lambda w: w["x0"])
    return lines


def is_chord_line(line: list[dict]) -> bool:
    if not line or len(line) > MAX_CHORD_LINE_WORDS:
        return False
    for word in line:
        try:
            parse_italian_chord(word["text"])
        except ValueError:
            return False
    return True


def attach_chord_to_nearest_word(chord_word: dict, lyric_line: list[dict], excluded: set[int]) -> int:
    """Returns the index (within lyric_line) of the word whose horizontal
    extent overlaps the chord's the most — falling back to smallest edge
    distance when there's no overlap at all (a chord printed slightly past
    the end of a short word, for instance, common when a chord line has
    more entries spread wider than a short lyric line has words). `excluded`
    (word indices another chord on the same line already claimed) is
    skipped when possible, so two chords on a wide line don't collapse onto
    the same nearest-by-fallback word merely because nothing else is
    closer — only reused if every word is already excluded."""
    candidates = [i for i in range(len(lyric_line)) if i not in excluded] or list(range(len(lyric_line)))

    def overlap(word: dict) -> float:
        return max(0.0, min(chord_word["x1"], word["x1"]) - max(chord_word["x0"], word["x0"]))

    best_i, best_overlap = candidates[0], -1.0
    for i in candidates:
        o = overlap(lyric_line[i])
        if o > best_overlap:
            best_overlap, best_i = o, i
    if best_overlap > 0:
        return best_i
    return min(
        candidates,
        key=lambda i: min(abs(lyric_line[i]["x0"] - chord_word["x0"]), abs(lyric_line[i]["x1"] - chord_word["x1"])),
    )


def extract_lines(pdf_path: Path) -> list[dict]:
    """Returns [{"words": [str, ...], "chords": {word_index: chord_text}}, ...]
    for every lyric line found across the whole PDF, in reading order."""
    result: list[dict] = []
    started = False
    pending_chords: list[dict] = []  # chord words from the most recent chord line, not yet attached

    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
            for line in group_words_into_lines(words):
                line_text = " ".join(w["text"] for w in line)
                if line_text.strip() == CREDITS_MARKER:
                    return result  # everything from here on is credits/legal boilerplate

                if is_chord_line(line):
                    started = True
                    pending_chords = line
                    continue

                if not started:
                    continue  # title/artist header, before the first chord line

                chords: dict[str, str] = {}
                used_indices: set[int] = set()
                for chord_word in pending_chords:
                    word_index = attach_chord_to_nearest_word(chord_word, line, used_indices)
                    used_indices.add(word_index)
                    key = str(word_index)
                    if key in chords:
                        # More chords on this line than words to anchor them
                        # to (e.g. a fast harmony run over a short final
                        # phrase) — verified-source.json only holds one
                        # chord per word, so the earlier one is dropped here.
                        # Flagged, not silent: this line needs a by-ear check.
                        safe_print(f"  WARNING: line {len(result)} has more chords than words — "
                                   f"{chords[key]!r} on word {word_index} ({line[word_index]['text']!r}) "
                                   f"was replaced by {chord_word['text']!r}")
                    chords[key] = chord_word["text"]
                pending_chords = []
                result.append({"words": [w["text"] for w in line], "chords": chords})

    return result


def convert(pdf_path: Path, slug: str, source_label: str) -> None:
    lines = extract_lines(pdf_path)
    if not lines:
        raise SystemExit(f"ERROR: no chord+lyric lines found in {pdf_path} — check it matches the expected chart layout")

    output = {"source": source_label, "chordNotation": "italian", "lines": lines}
    output_dir = REPO_ROOT / "corrections" / slug
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "verified-source.json"
    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")

    total_chords = sum(len(line["chords"]) for line in lines)
    safe_print(f"Extracted {len(lines)} lyric line(s), {total_chords} chord(s) -> {output_path}")
    safe_print("")
    for line in lines:
        words = line["words"]
        annotated = list(words)
        for word_index, chord in sorted(line["chords"].items(), key=lambda kv: -int(kv[0])):
            annotated.insert(int(word_index), f"[{chord}]")
        safe_print(" ".join(annotated))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf_path", type=Path)
    parser.add_argument("slug")
    args = parser.parse_args()
    convert(args.pdf_path, args.slug, source_label=f"{args.pdf_path.name} (mechanically extracted)")
