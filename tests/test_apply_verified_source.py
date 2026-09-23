import apply_verified_source as avs
import harmony_utils as hu


def test_parse_italian_chord_major_triad():
    assert hu.parse_italian_chord("SIb") == {"root": 10, "quality": "major"}


def test_parse_italian_chord_minor7():
    assert hu.parse_italian_chord("DOm7") == {"root": 0, "quality": "minor7"}


def test_parse_italian_chord_major6():
    assert hu.parse_italian_chord("MIb6") == {"root": 3, "quality": "major6"}


def test_parse_italian_chord_sus4():
    assert hu.parse_italian_chord("FA4") == {"root": 5, "quality": "sus4"}


def test_parse_italian_chord_seven_plus_is_major7_not_augmented():
    # Confirmed with Alessio: in this chart's convention "7+" means the 7th
    # degree is major, not that the 5th is augmented.
    assert hu.parse_italian_chord("SIb7+") == {"root": 10, "quality": "major7"}


def test_parse_italian_chord_slash_bass():
    assert hu.parse_italian_chord("DOm7/SIb") == {"root": 0, "quality": "minor7", "slashBass": 10}


def test_parse_italian_chord_minor_triad():
    assert hu.parse_italian_chord("SOLm") == {"root": 7, "quality": "minor"}


def test_parse_italian_chord_flat_slash_bass():
    assert hu.parse_italian_chord("LAb/DO") == {"root": 8, "quality": "major", "slashBass": 0}


def test_normalize_word_strips_punctuation_and_case():
    assert avs.normalize_word("Anna,") == "anna"
    assert avs.normalize_word("c'è") == "cè"
    assert avs.normalize_word("città") == "città"


def test_reconstruct_midi_words_groups_by_syllabic():
    aligned = [
        {"start": 0, "duration": 100, "pitch": 60, "lyrics": [{"verse": "line0", "text": "An", "syllabic": "begin"}]},
        {"start": 100, "duration": 100, "pitch": 62, "lyrics": [{"verse": "line0", "text": "na", "syllabic": "end"}]},
        {"start": 200, "duration": 100, "pitch": 64, "lyrics": [{"verse": "line0", "text": "co", "syllabic": "begin"},
                                                                 {"verse": "line0", "text": "me", "syllabic": "end"}]},
        {"start": 300, "duration": 100, "pitch": 65},
    ]
    words = avs.reconstruct_midi_words(aligned)
    assert [w.text for w in words] == ["Anna", "come"]
    assert words[0].note_indices == [0, 1]
    assert words[1].note_indices == [2, 2]


def test_align_verified_lines_matches_in_order_tolerating_noise():
    midi_words = [avs.MidiWord(t, [i]) for i, t in enumerate(["An", "co", "sono", "tante", "extra"])]
    pairs = avs.align_verified_lines(midi_words, [["Anna", "come", "sono", "tante,"]])
    # "An"/"Anna" and "co"/"come" don't normalize-match exactly (partial
    # words), but "sono" and "tante"/"tante," do, and stay in order.
    assert (2, 0, 2) in pairs
    assert (3, 0, 3) in pairs
    assert all(mi < 4 for mi, _, _ in pairs)  # never matches the trailing "extra" MIDI word


def test_align_verified_lines_does_not_cross_verse_repeats():
    # "Anna" appears far apart in two different verses; the second verse's
    # line must match the SECOND "Anna" in the MIDI sequence, not steal the
    # first one back from across the song.
    midi_words = [avs.MidiWord(t, [i]) for i, t in enumerate(["Anna", "canta", "x", "x", "x", "Anna", "balla"])]
    pairs = avs.align_verified_lines(midi_words, [["Anna", "canta"], ["Anna", "balla"]])
    by_line = {(li, wi): mi for mi, li, wi in pairs}
    assert by_line[(0, 0)] == 0
    assert by_line[(1, 0)] == 5


def test_apply_keeps_both_words_when_two_words_share_one_note(tmp_path, monkeypatch):
    # Regression test for a real bug found on "Anna e Marco": when a note's
    # original stacked syllables reconstruct into two separate words (e.g.
    # "Anna"+"come" both entirely on note 0), the second matched word must
    # not overwrite the first — both should end up on that note's lyrics.
    import json

    slug = "test-song"
    song_dir = tmp_path
    monkeypatch.setattr(avs, "REPO_ROOT", song_dir)
    (song_dir / "songs").mkdir()
    (song_dir / "songs" / f"{slug}.json").write_text(json.dumps({
        "slug": slug, "timeSignature": {"numerator": 4, "denominator": 4}, "tempoBpm": 120,
    }))
    (song_dir / "working" / slug).mkdir(parents=True)
    (song_dir / "corrections" / slug).mkdir(parents=True)

    aligned = {
        "ppq": 960,
        "aligned": [
            {"start": 0, "duration": 1440, "pitch": 74, "lyrics": [
                {"verse": "line1", "text": "An", "syllabic": "begin"},
                {"verse": "line1", "text": "na", "syllabic": "end"},
                {"verse": "line1", "text": "co", "syllabic": "begin"},
                {"verse": "line1", "text": "me", "syllabic": "end"},
            ]},
            {"start": 1440, "duration": 480, "pitch": 72, "lyrics": [{"verse": "line1", "text": "so", "syllabic": "begin"}]},
        ],
    }
    (song_dir / "working" / slug / "aligned-lyrics.json").write_text(json.dumps(aligned))
    (song_dir / "corrections" / slug / "verified-source.json").write_text(json.dumps({
        "lines": [{"words": ["Anna", "come", "sono"], "chords": {"0": "SIb"}}],
    }))

    avs.apply(slug)

    result = json.loads((song_dir / "working" / slug / "aligned-lyrics.json").read_text())["aligned"]
    assert [e["text"] for e in result[0]["lyrics"]] == ["Anna", "come"]
    harmony = json.loads((song_dir / "working" / slug / "harmony-events.json").read_text())["harmony"]
    assert harmony[0]["start"] == 0 and harmony[0]["root"] == 10 and harmony[0]["quality"] == "major"
