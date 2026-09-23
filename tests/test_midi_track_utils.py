import mido
import pytest

import midi_track_utils as mtu
from midi_fixtures import make_karaoke_midi


def test_detect_lyric_event_type_prefers_lyrics(tmp_path):
    mid = make_karaoke_midi(tmp_path / "k.mid")
    assert mtu.detect_lyric_event_type(mid) == "lyrics"


def test_detect_lyric_event_type_falls_back_to_text_when_no_lyrics_events(tmp_path):
    from midi_fixtures import build_lyric_track, build_meta_track, build_note_track

    mid = mido.MidiFile(ticks_per_beat=480)
    mid.tracks.append(build_meta_track())
    mid.tracks.append(build_note_track("Flute", 73, 1, [(0, 60, 480)]))
    mid.tracks.append(build_lyric_track("Words", [(0, "hi")], event_type="text"))
    assert mtu.detect_lyric_event_type(mid) == "text"


def test_detect_lyric_event_type_explicit_mode_overrides_detection(tmp_path):
    mid = make_karaoke_midi(tmp_path / "k.mid")
    assert mtu.detect_lyric_event_type(mid, "text") == "text"


def test_detect_lyrics_track_finds_dense_track(tmp_path):
    mid = make_karaoke_midi(tmp_path / "k.mid")
    idx = mtu.detect_lyrics_track(mid, "lyrics")
    assert mtu.track_name(mid, idx) == "Words"


def test_detect_lyrics_track_returns_none_when_absent(tmp_path):
    mid = make_karaoke_midi(tmp_path / "k.mid")
    assert mtu.detect_lyrics_track(mid, "text") is None


def test_detect_vocal_channel_ignores_gm_program_uses_coincidence(tmp_path):
    mid = make_karaoke_midi(tmp_path / "k.mid")
    lyrics_track = mtu.detect_lyrics_track(mid, "lyrics")
    lyric_ticks = [e.tick for e in mtu.read_lyric_events(mid, lyrics_track, "lyrics")]
    vocal_channel, scores = mtu.detect_vocal_channel(mid, lyric_ticks)
    assert vocal_channel == 1  # the "Flute"-disguised vocal track's channel, not a "voice" program
    assert scores[vocal_channel] == 1.0
    assert scores[vocal_channel] > scores.get(2, 0.0)  # channel 2 is the Piano/harmony track


def test_detect_vocal_channel_returns_none_without_lyric_ticks(tmp_path):
    mid = make_karaoke_midi(tmp_path / "k.mid")
    assert mtu.detect_vocal_channel(mid, []) == (None, {})


def test_resolve_vocal_channel_works_on_a_single_format0_style_track(tmp_path):
    """Regression, end-to-end: a real karaoke file from Alessio's
    collection turned out to be a single track with voice/instruments/
    drums distinguished only by MIDI channel (Format 0-shaped), not by
    separate tracks — the original track-indexed design couldn't handle
    this at all. It also has a leading header/credits block
    ("***Song***"/"***Artist***") at tick 0, which — before
    resolve_vocal_channel was fixed to score coincidence against parsed
    syllable ticks instead of raw lyric-event ticks — could outscore the
    real vocal channel whenever some other channel also starts at tick 0
    (here, the accompaniment chord)."""
    from midi_fixtures import make_format0_style_karaoke_midi

    mid = make_format0_style_karaoke_midi(tmp_path / "f0.mid")
    assert len(mid.tracks) == 1
    vocal_channel, scores = mtu.resolve_vocal_channel(mid, {})
    assert vocal_channel == 2  # the vocal-carrying channel in that fixture
    assert 9 not in scores  # the drum channel is never a vocal candidate


def test_extract_channel_as_midi_preserves_notes_tempo_and_time_signature(tmp_path):
    mid = make_karaoke_midi(tmp_path / "k.mid")
    out_path = tmp_path / "sub.mid"
    mtu.extract_channel_as_midi(mid, channel=1, program=53, out_path=out_path)  # Flute's channel

    sub = mido.MidiFile(str(out_path))
    assert sub.ticks_per_beat == mid.ticks_per_beat
    note_ons = [msg.note for msg in sub.tracks[0] if msg.type == "note_on" and msg.velocity > 0]
    assert note_ons == [60, 62, 64, 65, 67]
    assert [msg.program for msg in sub.tracks[0] if msg.type == "program_change"] == [53]
    assert any(msg.type == "set_tempo" for msg in sub.tracks[0])
    assert any(msg.type == "time_signature" for msg in sub.tracks[0])
    assert all(msg.channel == 0 for msg in sub.tracks[0] if msg.type in ("note_on", "note_off"))


def test_extract_channel_as_midi_excludes_other_channels_notes(tmp_path):
    mid = make_karaoke_midi(tmp_path / "k.mid")
    out_path = tmp_path / "sub.mid"
    mtu.extract_channel_as_midi(mid, channel=2, program=0, out_path=out_path)  # Piano's channel
    sub = mido.MidiFile(str(out_path))
    note_ons = sorted(msg.note for msg in sub.tracks[0] if msg.type == "note_on" and msg.velocity > 0)
    assert note_ons == sorted([48, 52, 55, 43, 47, 50])  # only the Piano channel's chords


def test_extract_channel_as_midi_works_across_a_single_multi_channel_track(tmp_path):
    from midi_fixtures import make_format0_style_karaoke_midi

    mid = make_format0_style_karaoke_midi(tmp_path / "f0.mid")
    out_path = tmp_path / "sub.mid"
    mtu.extract_channel_as_midi(mid, channel=2, program=53, out_path=out_path)
    sub = mido.MidiFile(str(out_path))
    note_ons = [msg.note for msg in sub.tracks[0] if msg.type == "note_on" and msg.velocity > 0]
    assert note_ons  # pulled the vocal channel's notes out of the single shared track
    assert all(msg.channel == 0 for msg in sub.tracks[0] if msg.type in ("note_on", "note_off"))


# --- parse_karaoke_syllables -------------------------------------------------

RawLyricEvent = mtu.RawLyricEvent


def test_parse_multisyllable_word():
    events = [RawLyricEvent(0, "Hel-"), RawLyricEvent(480, "lo")]
    result = mtu.parse_karaoke_syllables(events)
    assert [r["text"] for r in result] == ["Hel", "lo"]
    assert [r["syllabic"] for r in result] == ["begin", "end"]
    assert all(r["verse"] == "line0" for r in result)
    assert all(r["melisma"] is None for r in result)


def test_parse_single_word_with_leading_space():
    events = [RawLyricEvent(0, " world")]
    result = mtu.parse_karaoke_syllables(events)
    assert result == [{"tick": 0, "verse": "line0", "text": "world", "syllabic": "single", "melisma": None}]


def test_parse_melisma_continuation_marker():
    events = [RawLyricEvent(0, " world"), RawLyricEvent(480, "-")]
    result = mtu.parse_karaoke_syllables(events)
    assert result[0]["text"] == "world"
    assert result[1] == {"tick": 480, "verse": "line0", "text": None, "syllabic": None, "melisma": "continue"}


def test_parse_bare_dash_is_the_only_melisma_marker():
    # A bare "-" is the (classic-convention) melisma marker; plain
    # whitespace alone is not treated as one (real observed data doesn't
    # use it that way) — it's just skipped rather than producing a
    # spurious empty-text syllable.
    events = [RawLyricEvent(0, " hi"), RawLyricEvent(480, "-"), RawLyricEvent(960, " ")]
    result = mtu.parse_karaoke_syllables(events)
    # "hi" (closed immediately, no trailing signal), then the "-" melisma
    # marker; the trailing bare-space event contributes nothing (skipped).
    assert [r["text"] for r in result] == ["hi", None]
    assert [r.get("melisma") for r in result] == [None, "continue"]


def test_parse_trailing_space_closes_word_real_convention():
    # Confirmed against a real file ("Zappatore - M. Merola.kar"):
    # multi-syllable words are closed by a *trailing* space on the last
    # fragment, with no hyphen at all — not the leading-space /
    # trailing-hyphen convention.
    events = [RawLyricEvent(0, "Fe"), RawLyricEvent(1, "li"), RawLyricEvent(2, "ci"), RawLyricEvent(3, "ssi"), RawLyricEvent(4, "ma ")]
    result = mtu.parse_karaoke_syllables(events)
    assert [r["text"] for r in result] == ["Fe", "li", "ci", "ssi", "ma"]
    # This file demonstrates the trailing-space convention (the last event
    # ends in a space), so the four fragments before it — none carrying any
    # closing signal of their own — continue the word instead of each
    # closing on its own; only "ma " (trailing space) actually ends it.
    assert [r["syllabic"] for r in result] == ["begin", "middle", "middle", "middle", "end"]


def test_parse_fragment_with_no_signal_closes_when_file_never_uses_trailing_space():
    # A file that never demonstrates the trailing-space convention anywhere
    # keeps the old conservative behavior: a fragment with no closing signal
    # of its own closes immediately, rather than risking merging the whole
    # song into one "word" by guessing it continues.
    events = [RawLyricEvent(0, "Fe"), RawLyricEvent(1, "li")]
    result = mtu.parse_karaoke_syllables(events)
    assert [r["text"] for r in result] == ["Fe", "li"]
    assert [r["syllabic"] for r in result] == ["single", "single"]


def test_parse_bare_carriage_return_is_a_line_break_not_lyric_content():
    events = [RawLyricEvent(0, "Hi "), RawLyricEvent(100, "\r"), RawLyricEvent(200, "there ")]
    result = mtu.parse_karaoke_syllables(events)
    assert [r["text"] for r in result] == ["Hi", "there"]
    assert [r["verse"] for r in result] == ["line0", "line1"]


def test_parse_decorative_header_line_is_skipped():
    events = [RawLyricEvent(0, "***Test Song***"), RawLyricEvent(100, "\r"), RawLyricEvent(200, "Real ")]
    result = mtu.parse_karaoke_syllables(events)
    assert [r["text"] for r in result] == ["Real"]


def test_parse_soft_karaoke_header_lines_are_skipped():
    # The official Soft Karaoke file-header syntax — confirmed against a
    # real file ("Anna E Marco", Lucio Dalla).
    events = [
        RawLyricEvent(0, "@KMIDI KARAOKE FILE"),
        RawLyricEvent(0, "@LENGL"),
        RawLyricEvent(0, "@TCopyright Generalmusic S.p.a."),
        RawLyricEvent(100, "\\An"),
        RawLyricEvent(200, "na "),
    ]
    result = mtu.parse_karaoke_syllables(events)
    assert [r["text"] for r in result] == ["An", "na"]


def test_parse_trailing_space_word_closing_with_leading_paragraph_marker():
    # Confirmed against "Anna E Marco": leading \/-markers combine with the
    # trailing-space word-closing convention in the same file.
    events = [RawLyricEvent(0, "\\An"), RawLyricEvent(1, "na "), RawLyricEvent(2, "co"), RawLyricEvent(3, "me ")]
    result = mtu.parse_karaoke_syllables(events)
    assert [r["text"] for r in result] == ["An", "na", "co", "me"]
    assert [r["verse"] for r in result] == ["line1"] * 4  # the leading \ bumps the counter before "An"


def test_parse_line_and_paragraph_markers_bump_verse():
    events = [RawLyricEvent(0, "Hi"), RawLyricEvent(480, "/there"), RawLyricEvent(960, "\\New paragraph")]
    result = mtu.parse_karaoke_syllables(events)
    assert [r["verse"] for r in result] == ["line0", "line1", "line2"]
    assert [r["text"] for r in result] == ["Hi", "there", "New paragraph"]


def test_parse_bare_line_marker_with_no_text_is_skipped():
    events = [RawLyricEvent(0, "Hi"), RawLyricEvent(480, "/"), RawLyricEvent(960, "there")]
    result = mtu.parse_karaoke_syllables(events)
    assert [r["text"] for r in result] == ["Hi", "there"]
    assert result[1]["verse"] == "line1"  # the bare marker still bumped the line counter


def test_parse_three_syllable_word():
    events = [RawLyricEvent(0, "ev-"), RawLyricEvent(1, "ry-"), RawLyricEvent(2, "bo-"), RawLyricEvent(3, "dy")]
    result = mtu.parse_karaoke_syllables(events)
    assert [r["syllabic"] for r in result] == ["begin", "middle", "middle", "end"]


def test_find_midi_source_uses_config_file_when_set(tmp_path, monkeypatch):
    library = tmp_path / "midi-intake" / "library" / "song"
    library.mkdir(parents=True)
    (library / "a.mid").write_bytes(b"")
    (library / "b.mid").write_bytes(b"")
    monkeypatch.setattr(mtu, "REPO_ROOT", tmp_path)
    resolved = mtu.find_midi_source("song", {"midiSource": {"file": "b.mid"}})
    assert resolved == library / "b.mid"


def test_find_midi_source_errors_on_ambiguity_without_config(tmp_path, monkeypatch):
    library = tmp_path / "midi-intake" / "library" / "song"
    library.mkdir(parents=True)
    (library / "a.mid").write_bytes(b"")
    (library / "b.mid").write_bytes(b"")
    monkeypatch.setattr(mtu, "REPO_ROOT", tmp_path)
    with pytest.raises(SystemExit):
        mtu.find_midi_source("song", {})


def test_find_midi_source_auto_picks_single_file(tmp_path, monkeypatch):
    library = tmp_path / "midi-intake" / "library" / "song"
    library.mkdir(parents=True)
    (library / "only.mid").write_bytes(b"")
    monkeypatch.setattr(mtu, "REPO_ROOT", tmp_path)
    assert mtu.find_midi_source("song", {}) == library / "only.mid"
