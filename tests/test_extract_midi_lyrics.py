import json

import extract_midi_lyrics as eml


def _write_song(song_dir, slug, max_gap_ticks=None):
    (song_dir / "songs").mkdir(exist_ok=True)
    midi_source = {"file": "song.mid"}
    if max_gap_ticks is not None:
        midi_source["maxLyricNoteGapTicks"] = max_gap_ticks
    (song_dir / "songs" / f"{slug}.json").write_text(json.dumps({"slug": slug, "midiSource": midi_source}))
    (song_dir / "working" / slug).mkdir(parents=True)


def test_extract_keeps_all_syllables_landing_on_the_same_note(tmp_path, monkeypatch):
    # A note held while several syllable ticks land within its window (or
    # nearest to it, with no closer note) legitimately gets more than one
    # lyrics entry — see the module docstring for why forcing one syllable
    # per note was tried and reverted. Nothing here should be dropped.
    import constants
    import midi_track_utils as mtu

    slug = "test-song"
    song_dir = tmp_path
    monkeypatch.setattr(eml, "REPO_ROOT", song_dir)
    _write_song(song_dir, slug)

    vocal_events = {"events": [{"start": 0, "duration": 200, "pitch": 60}, {"start": 500, "duration": 50, "pitch": 62}]}
    (song_dir / "working" / slug / "vocal-events.json").write_text(json.dumps(vocal_events))

    from midi_fixtures import make_karaoke_midi

    midi_path = song_dir / "song.mid"
    make_karaoke_midi(midi_path, ticks_per_beat=constants.PPQ)  # 1:1 tick scaling for this test
    monkeypatch.setattr(mtu, "find_midi_source", lambda s, c: midi_path)
    monkeypatch.setattr(mtu, "detect_lyric_event_type", lambda mid, pref: "text")
    monkeypatch.setattr(mtu, "detect_lyrics_track", lambda mid, event_type: 0)
    monkeypatch.setattr(mtu, "read_lyric_events", lambda mid, track, event_type: [])
    monkeypatch.setattr(mtu, "parse_karaoke_syllables", lambda raw: [
        {"tick": 10, "verse": "line0", "melisma": None, "text": "An", "syllabic": "begin"},
        {"tick": 50, "verse": "line0", "melisma": None, "text": "na", "syllabic": "middle"},
        {"tick": 90, "verse": "line0", "melisma": None, "text": "co", "syllabic": "middle"},
        {"tick": 130, "verse": "line0", "melisma": None, "text": "me", "syllabic": "end"},
    ])

    eml.extract(slug)

    aligned = json.loads((song_dir / "working" / slug / "aligned-lyrics.json").read_text())["aligned"]
    assert [e["text"] for e in aligned[0]["lyrics"]] == ["An", "na", "co", "me"]
    assert "lyrics" not in aligned[1]


def test_extract_never_drops_a_syllable_beyond_tolerance(tmp_path, monkeypatch):
    # A syllable tick far from every note (beyond maxLyricNoteGapTicks) must
    # still land on the nearest note instead of being silently dropped —
    # Alessio's explicit requirement after finding missing words in a
    # published song.
    import constants
    import midi_track_utils as mtu

    slug = "test-song"
    song_dir = tmp_path
    monkeypatch.setattr(eml, "REPO_ROOT", song_dir)
    _write_song(song_dir, slug, max_gap_ticks=10)

    vocal_events = {"events": [{"start": 0, "duration": 20, "pitch": 60}, {"start": 1000, "duration": 20, "pitch": 62}]}
    (song_dir / "working" / slug / "vocal-events.json").write_text(json.dumps(vocal_events))

    from midi_fixtures import make_karaoke_midi

    midi_path = song_dir / "song.mid"
    make_karaoke_midi(midi_path, ticks_per_beat=constants.PPQ)
    monkeypatch.setattr(mtu, "find_midi_source", lambda s, c: midi_path)
    monkeypatch.setattr(mtu, "detect_lyric_event_type", lambda mid, pref: "text")
    monkeypatch.setattr(mtu, "detect_lyrics_track", lambda mid, event_type: 0)
    monkeypatch.setattr(mtu, "read_lyric_events", lambda mid, track, event_type: [])
    # tick 400 is 380 ticks from note 0 and 600 ticks from note 1 — far
    # beyond max_gap_ticks=10 from either, so nothing matches confidently.
    monkeypatch.setattr(mtu, "parse_karaoke_syllables", lambda raw: [
        {"tick": 400, "verse": "line0", "melisma": None, "text": "lost", "syllabic": "single"},
    ])

    eml.extract(slug)

    result = json.loads((song_dir / "working" / slug / "aligned-lyrics.json").read_text())
    aligned = result["aligned"]
    all_text = [e["text"] for n in aligned for e in n.get("lyrics", [])]
    assert all_text == ["lost"]  # never dropped
    assert aligned[0]["lyrics"][0]["text"] == "lost"  # forced onto the nearest note (note 0, 380 < 600 away)
    assert result["syllables_approximate"] == 1
