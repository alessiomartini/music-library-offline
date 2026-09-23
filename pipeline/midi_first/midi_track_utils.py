"""
Shared helpers for the MIDI-first pipeline (import_karaoke_midi.py,
extract_midi_lyrics.py, extract_midi_harmony.py).

Everything here reads a source MIDI in its own raw ticks (mid.ticks_per_beat)
— never in seconds, unlike the audio-first path's forced-alignment code,
because a MIDI file's lyric events and note events already share one exact
tick timeline; there is no cross-modal (audio-to-symbolic) alignment problem
to solve here, only parsing. Convert to the pipeline's canonical PPQ=960
grid explicitly at each script's boundary (see constants.PPQ), the same way
musescore_import.py already does for note positions.
"""
import re
from dataclasses import dataclass
from pathlib import Path

import mido

REPO_ROOT = Path(__file__).parent.parent.parent

# GM percussion is always channel 10 (0-indexed 9); never a melody/vocal
# candidate.
DRUM_CHANNEL = 9


def find_midi_source(slug: str, config: dict) -> Path:
    """Resolves the source MIDI for a song: songs/<slug>.json's
    midiSource.file if set, else the single file in
    midi-intake/library/<slug>/ (an explicit config entry is required if
    more than one is present — see midi-intake/README.md for how multiple
    MIDI versions of one song are organized; cross-referencing them is not
    implemented yet)."""
    library_dir = REPO_ROOT / "midi-intake" / "library" / slug
    midi_source = config.get("midiSource") or {}
    filename = midi_source.get("file")
    if filename:
        candidate = library_dir / filename
        if not candidate.exists():
            raise SystemExit(f"ERROR: configured midiSource.file {filename!r} not found in {library_dir}")
        return candidate
    # .kar ("Soft Karaoke") files are ordinary MIDI files by a different
    # extension convention — mido reads them exactly like a .mid file.
    matches = sorted(p for pattern in ("*.mid", "*.midi", "*.kar") for p in library_dir.glob(pattern))
    if not matches:
        raise SystemExit(
            f"ERROR: no MIDI file in {library_dir} — run organize_midi_intake.py first, "
            f"or set songs/{slug}.json's midiSource.file"
        )
    if len(matches) > 1:
        raise SystemExit(
            f"ERROR: {len(matches)} MIDI files in {library_dir} — set songs/{slug}.json's "
            f"midiSource.file to pick one: {[m.name for m in matches]}"
        )
    return matches[0]


def track_name(mid: mido.MidiFile, track_idx: int) -> str:
    for msg in mid.tracks[track_idx]:
        if msg.is_meta and msg.type == "track_name":
            return msg.name
    return ""


def note_onsets_by_channel(mid: mido.MidiFile) -> dict[int, list[int]]:
    """MIDI channel (0-15) -> sorted absolute-tick note_on (velocity>0)
    positions, across ALL tracks combined. Real karaoke MIDI files are
    frequently Format 0 (or otherwise put everything on one track) with
    voice/instruments/drums distinguished only by channel, not by track —
    confirmed against an actual file in Alessio's collection
    ("Zappatore - M. Merola.kar": one track, 9 channels). Channel, not
    track, is therefore the addressable unit for notes throughout this
    module; track stays meaningful only for lyric meta-events (see
    lyric_events_by_track), which the MIDI spec ties to a track, not a
    channel."""
    result: dict[int, list[int]] = {}
    for track in mid.tracks:
        abs_tick = 0
        for msg in track:
            abs_tick += msg.time
            if msg.type == "note_on" and msg.velocity > 0:
                result.setdefault(msg.channel, []).append(abs_tick)
    for onsets in result.values():
        onsets.sort()
    return result


def lyric_events_by_track(mid: mido.MidiFile, event_type: str) -> dict[int, list[tuple[int, str]]]:
    """track index -> [(absolute tick, text), ...] for meta events of the
    given type ('lyrics' or 'text'). Tracks with none are omitted."""
    result: dict[int, list[tuple[int, str]]] = {}
    for i, track in enumerate(mid.tracks):
        abs_tick = 0
        events = []
        for msg in track:
            abs_tick += msg.time
            if msg.is_meta and msg.type == event_type:
                events.append((abs_tick, msg.text))
        if events:
            result[i] = events
    return result


def detect_lyric_event_type(mid: mido.MidiFile, mode: str = "auto") -> str:
    """'lyrics' (MIDI meta 0x05) is the dedicated per-syllable karaoke
    event; 'text' (0x01) is sometimes (ab)used for the same role by tools
    that follow the Soft Karaoke convention loosely. Auto prefers 'lyrics'
    when the file has any, since 'text' is also used for unrelated markers
    (track/instrument labels)."""
    if mode in ("lyrics", "text"):
        return mode
    has_lyrics = any(msg.type == "lyrics" for track in mid.tracks for msg in track)
    return "lyrics" if has_lyrics else "text"


def detect_lyrics_track(mid: mido.MidiFile, event_type: str) -> int | None:
    """The track with the most events of the given type — a real karaoke
    lyric stream is dense (one event per syllable); a stray title/copyright
    marker on an unrelated track is not."""
    by_track = lyric_events_by_track(mid, event_type)
    if not by_track:
        return None
    return max(by_track, key=lambda i: len(by_track[i]))


def detect_vocal_channel(
    mid: mido.MidiFile, lyric_ticks: list[int], tolerance_ticks: int | None = None
) -> tuple[int | None, dict[int, float]]:
    """Identifies the vocal melody channel by how well its note onsets
    coincide with the lyric event ticks — channel, not track, since a real
    karaoke file commonly distinguishes voice/instruments/drums only by
    channel within one track (see note_onsets_by_channel). Deliberately not
    GM program number: karaoke MIDI authors commonly put the vocal guide
    line on an unrelated instrument program (flute, sax, strings...).

    Scored as precision+recall (F1), not recall alone — against a real
    file (see docs/FUTURE-ARCHITECTURE.md's MIDI-first section), a dense
    accompaniment channel (e.g. a bass line moving on nearly every beat)
    out-scored the real vocal channel on recall alone, simply because
    having far more onsets makes *some* of them land near *any* given
    lyric tick by chance, not because it tracks the vocal line. Precision
    (what fraction of the channel's *own* onsets are actually near a
    lyric tick) penalizes that. A channel whose notes sit almost entirely
    below a plausible vocal register is also excluded outright — the same
    real file's bass line would otherwise still contend on F1 alone.

    Returns (best channel or None, {channel: F1 score 0..1}) — the caller
    should log the full score table: on real full-arrangement files the
    top few scores can end up close, and the caller should log the full
    table and expect songs/<slug>.json's midiSource.vocalChannel to often
    need a manual override, not just as a rare edge case."""
    if tolerance_ticks is None:
        tolerance_ticks = max(mid.ticks_per_beat // 4, 1)  # a 16th note
    if not lyric_ticks:
        return None, {}
    lyric_ticks = sorted(lyric_ticks)
    onsets_by_channel = note_onsets_by_channel(mid)
    pitches_by_channel = note_pitches_by_channel(mid)
    scores: dict[int, float] = {}
    for channel, onsets in onsets_by_channel.items():
        if channel == DRUM_CHANNEL or not onsets:
            continue
        channel_pitches = pitches_by_channel.get(channel, [])
        if channel_pitches and sum(channel_pitches) / len(channel_pitches) < VOCAL_PITCH_FLOOR:
            continue
        recall = _coincidence_rate(lyric_ticks, onsets, tolerance_ticks)
        precision = _coincidence_rate(onsets, lyric_ticks, tolerance_ticks)
        scores[channel] = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    if not scores:
        return None, scores
    return max(scores, key=scores.get), scores


# Below this, a channel is essentially never a solo sung melody (this is
# sub-bass-guitar register) — see detect_vocal_channel.
VOCAL_PITCH_FLOOR = 45


def note_pitches_by_channel(mid: mido.MidiFile) -> dict[int, list[int]]:
    """MIDI channel -> every note_on (velocity>0) pitch played on it,
    across all tracks — used to veto an obviously non-vocal-register
    channel (e.g. a bass line) as a vocal-channel candidate."""
    result: dict[int, list[int]] = {}
    for track in mid.tracks:
        for msg in track:
            if msg.type == "note_on" and msg.velocity > 0:
                result.setdefault(msg.channel, []).append(msg.note)
    return result


def _coincidence_rate(probe_ticks: list[int], reference_ticks: list[int], tolerance_ticks: int) -> float:
    """Fraction of probe_ticks landing within tolerance_ticks of some tick
    in reference_ticks (sorted)."""
    if not probe_ticks:
        return 0.0
    reference_ticks = sorted(reference_ticks)
    hits = 0
    for t in probe_ticks:
        pos = _bisect_left(reference_ticks, t)
        candidates = reference_ticks[max(pos - 1, 0):pos + 1]
        if candidates and min(abs(c - t) for c in candidates) <= tolerance_ticks:
            hits += 1
    return hits / len(probe_ticks)


def _bisect_left(sorted_list: list[int], value: int) -> int:
    lo, hi = 0, len(sorted_list)
    while lo < hi:
        mid_i = (lo + hi) // 2
        if sorted_list[mid_i] < value:
            lo = mid_i + 1
        else:
            hi = mid_i
    return lo


def resolve_vocal_channel(mid: mido.MidiFile, midi_source: dict) -> tuple[int | None, dict[int, float]]:
    """The vocal melody channel: songs/<slug>.json's
    midiSource.vocalChannel if set, else auto-detected by lyric/note-onset
    coincidence (see detect_vocal_channel). Shared by import_karaoke_midi.py
    and extract_midi_harmony.py so both agree on which channel is the voice
    without Alessio having to copy a channel number between them — without
    this, extract_midi_harmony.py's default "every non-vocal channel" would
    silently include the vocal line itself whenever vocalChannel isn't
    explicitly configured. Returns (channel or None, coincidence scores —
    empty if a config override was used or nothing was found)."""
    configured = midi_source.get("vocalChannel")
    if configured is not None:
        return configured, {}
    event_type = detect_lyric_event_type(mid, midi_source.get("lyricEventType", "auto"))
    lyrics_track = midi_source.get("lyricsTrack")
    if lyrics_track is None:
        lyrics_track = detect_lyrics_track(mid, event_type)
    if lyrics_track is None:
        return None, {}
    # Real syllable ticks only (parse_karaoke_syllables already drops
    # header/credits-block junk, e.g. "***Song Title***", and bare
    # line-break events) — using raw, unfiltered lyric-event ticks here
    # instead let a header block sitting at tick 0 outscore the real vocal
    # channel whenever some other channel also happens to start at tick 0
    # (e.g. an instrumental intro chord), confirmed against a real file.
    syllables = parse_karaoke_syllables(read_lyric_events(mid, lyrics_track, event_type))
    lyric_ticks = [s["tick"] for s in syllables if s["text"] or s["melisma"]]
    return detect_vocal_channel(mid, lyric_ticks)


def extract_channel_as_midi(mid: mido.MidiFile, channel: int, program: int, out_path: Path) -> None:
    """Writes a standalone single-track MIDI with the chosen channel's note
    events (collected across all of the source's tracks, then reprogrammed
    onto channel 0) plus any tempo/time-signature meta events found
    anywhere in the source file. Channel, not track, because a real
    karaoke file commonly puts every instrument plus the vocal guide line
    on one track, distinguished only by channel (confirmed against an
    actual file — see note_onsets_by_channel). Preserves the source's own
    ticks_per_beat; PPQ reconciliation onto the pipeline's canonical grid
    happens inside musescore_import.import_midi(), same as it already does
    for Basic Pitch's output."""
    events: list[tuple[int, "mido.Message | mido.MetaMessage"]] = []
    for track in mid.tracks:
        abs_tick = 0
        for msg in track:
            abs_tick += msg.time
            if msg.type in ("note_on", "note_off") and msg.channel == channel:
                events.append((abs_tick, msg.copy(channel=0)))
            elif msg.is_meta and msg.type in ("set_tempo", "time_signature"):
                events.append((abs_tick, msg.copy()))
    events.sort(key=lambda e: e[0])

    out = mido.MidiFile(ticks_per_beat=mid.ticks_per_beat)
    out_track = mido.MidiTrack()
    out.tracks.append(out_track)
    out_track.append(mido.Message("program_change", program=program, channel=0, time=0))
    last_tick = 0
    for abs_tick, msg in events:
        msg.time = abs_tick - last_tick
        out_track.append(msg)
        last_tick = abs_tick
    out_track.append(mido.MetaMessage("end_of_track", time=0))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.save(str(out_path))


@dataclass
class RawLyricEvent:
    tick: int
    text: str


def read_lyric_events(mid: mido.MidiFile, track_idx: int, event_type: str) -> list[RawLyricEvent]:
    events = []
    abs_tick = 0
    for msg in mid.tracks[track_idx]:
        abs_tick += msg.time
        if msg.is_meta and msg.type == event_type:
            events.append(RawLyricEvent(tick=abs_tick, text=msg.text))
    return events


# Soft Karaoke text conventions this parser understands — revised
# 2026-09-22 against a real file from Alessio's collection
# ("Zappatore - M. Merola.kar"), which turned out not to follow the
# convention originally assumed here (kept as a compatibility fallback,
# see continues_word below). What that real file actually does:
#   \  or /  at the start of an event -> new paragraph/line (classic
#            convention, kept for files that do use it)
#   a bare "\r"/"\n" event (no other content)  -> also a line break — this
#            file emits these as their own separate lyric events instead
#            of a leading marker character
#   a trailing space on the event text -> this event CLOSES the current
#            word (e.g. "Fe","li","ci","ssi","ma " spells "Felicissima",
#            only the last fragment carries the trailing space)
#   no trailing signal at all -> conservatively treated as closing the
#            word too (tagged "single") rather than assumed to continue:
#            guessing "continues" by default risks silently merging an
#            entire song into one giant "word" for a file that never
#            marks continuation at all; guessing "closes" only costs
#            syllabic (begin/middle/end) grouping fidelity, not content
#   trailing -               -> classic convention: explicitly continues
#            (checked first, so a file that does use hyphens still works)
#   "***line***"-style decoration (a whole event wrapped in asterisks,
#            e.g. a leading title/artist/credits header block before the
#            singing starts) -> skipped entirely, not treated as lyric
#            content
#   "@K"/"@L"/"@T"/"@V" header lines -> skipped entirely. This is the
#            official Soft Karaoke file-header syntax (@KMIDI KARAOKE FILE
#            identifies the format, @L=language, @T=title/author/copyright
#            lines, @V=version) — confirmed against a second real file
#            ("Anna E Marco", Lucio Dalla), which otherwise follows the
#            classic \/-marker + trailing-space convention above cleanly.
# This still has NOT been verified against every source site's variant —
# spot-check working/<slug>/aligned-lyrics.json against the source file for
# a new song before trusting it (see docs/FUTURE-ARCHITECTURE.md's
# MIDI-first section). In particular, no real file surveyed so far has
# shown an explicit "still holding this syllable" melisma marker distinct
# from a plain word-final syllable — held notes with no following lyric
# event simply get no lyrics attached (see extract_midi_lyrics.py), which
# is the existing, already-established conservative fallback.
_DECORATIVE_LINE_RE = re.compile(r"^\*+.*\*+$")
_KAR_HEADER_LINE_RE = re.compile(r"^@[KLTV]")


def parse_karaoke_syllables(raw_events: list[RawLyricEvent]) -> list[dict]:
    """Returns [{tick, verse, text, syllabic, melisma}], text/syllabic set
    for a real syllable, melisma='continue' (text=None) for an explicit
    continuation marker (bare "-", classic convention only)."""
    # Both real files surveyed so far ("Zappatore", "Anna E Marco") signal a
    # word boundary with a trailing space/tab on its last fragment, never
    # with a hyphen — but a fragment with *no* trailing signal at all was
    # being treated as closing too (see the old closes_word below), so
    # "\An","na " ("Anna") parsed as two separate one-syllable "words"
    # instead of one two-syllable word, silently defeating the syllabic
    # begin/middle/end grouping (and, downstream, both the ScoreViewer
    # word-spacing logic and any word-anchored harmony lookup that need it).
    # Fixed 2026-09-22: once a file demonstrates the trailing-space
    # convention anywhere, a fragment with no trailing signal continues the
    # word instead of closing it. A file that never uses trailing spaces at
    # all keeps the old conservative "close by default" fallback, so a
    # hypothetical file with neither convention still can't merge an entire
    # song into one giant word.
    uses_trailing_space_convention = any((raw.text or "").endswith((" ", "\t")) for raw in raw_events)

    parsed: list[dict] = []
    pending_word: list[dict] = []
    line_index = 0

    def flush_word():
        nonlocal pending_word
        if not pending_word:
            return
        if len(pending_word) == 1:
            pending_word[0]["syllabic"] = "single"
        else:
            pending_word[0]["syllabic"] = "begin"
            for s in pending_word[1:-1]:
                s["syllabic"] = "middle"
            pending_word[-1]["syllabic"] = "end"
        parsed.extend(pending_word)
        pending_word = []

    for raw in raw_events:
        text = raw.text or ""
        if _KAR_HEADER_LINE_RE.match(text):
            continue  # "@KMIDI KARAOKE FILE" / "@L.." / "@T.." / "@V.." — file header, not lyrics

        while text[:1] in ("\\", "/"):
            flush_word()
            line_index += 1
            text = text[1:]

        if text in ("", "\r", "\n", "\r\n"):
            if text:  # a genuine line-break event, as opposed to a
                flush_word()  # leading \/-marker that left nothing behind
                line_index += 1
            continue

        if _DECORATIVE_LINE_RE.match(text.strip()):
            continue  # a "***Song Title***"-style header line, not lyrics

        if text.strip() == "-":
            flush_word()
            parsed.append({"tick": raw.tick, "verse": f"line{line_index}", "text": None, "syllabic": None, "melisma": "continue"})
            continue

        continues_word = text.rstrip().endswith("-")
        if text.endswith((" ", "\t")):
            closes_word = True
        elif continues_word:
            closes_word = False
        else:
            closes_word = not uses_trailing_space_convention
        body = text.strip()
        if continues_word:
            body = body[:-1]

        if not body:
            # Whitespace-only (or now-empty after stripping a lone "-")
            # once markers are stripped: close out whatever's pending
            # rather than adding a spurious empty-text syllable.
            flush_word()
            continue

        pending_word.append({"tick": raw.tick, "verse": f"line{line_index}", "text": body, "syllabic": None, "melisma": None})
        if closes_word:
            flush_word()

    flush_word()
    return parsed
