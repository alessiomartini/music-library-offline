import extract_midi_harmony as emh
import harmony_utils


def test_smooth_short_events_merges_brief_passing_chord():
    events = [
        {"start": 0, "root": 0, "quality": "major", "duration": 960},
        {"start": 960, "root": 2, "quality": "minor", "duration": 100},  # brief passing chord
        {"start": 1060, "root": 7, "quality": "major", "duration": 960},
    ]
    smoothed = harmony_utils.smooth_short_events(events, min_duration_ticks=480)
    assert [(e["root"], e["quality"]) for e in smoothed] == [(0, "major"), (7, "major")]
    assert smoothed[0]["duration"] == 960 + 100  # absorbed the passing chord's duration


def test_smooth_short_events_keeps_first_event_even_if_short():
    events = [{"start": 0, "root": 0, "quality": "major", "duration": 10}]
    assert harmony_utils.smooth_short_events(events, min_duration_ticks=480) == events


def test_smooth_short_events_empty_list():
    assert harmony_utils.smooth_short_events([], min_duration_ticks=480) == []


def test_suggest_key_c_major_melody():
    # A flat, equally-weighted scale is genuinely ambiguous between a key
    # and its relative minor (music21 correctly returns A minor for a bare
    # C major scale) — this instead weights the tonic the way a real
    # melody would (starts/ends there, returns to it repeatedly).
    pitches = [60, 60, 60, 64, 64, 67, 67, 72, 60, 60, 64, 67, 60]
    tonic, mode = harmony_utils.suggest_key(pitches)
    assert tonic == "C"
    assert mode == "major"


def test_classify_chord_exact_major():
    assert emh.classify_chord({0, 4, 7}) == (0, "major")


def test_classify_chord_exact_minor():
    assert emh.classify_chord({0, 3, 7}) == (0, "minor")


def test_classify_chord_dominant7_exact():
    assert emh.classify_chord({0, 4, 7, 10}) == (0, "dominant7")


def test_classify_chord_major7_exact():
    assert emh.classify_chord({0, 4, 7, 11}) == (0, "major7")


def test_classify_chord_transposed_root():
    # D major (D F# A) = pitch classes 2, 6, 9
    assert emh.classify_chord({2, 6, 9}) == (2, "major")


def test_classify_chord_extension_reduces_to_richest_template():
    # a 9th chord (root, 3rd, 5th, b7, 9th) reduces to dominant7
    assert emh.classify_chord({0, 4, 7, 10, 2}) == (0, "dominant7")


def test_classify_chord_power_chord_defaults_major():
    assert emh.classify_chord({0, 7}) == (0, "major")


def test_classify_chord_dyad_with_minor_third_defaults_minor():
    assert emh.classify_chord({0, 3}) == (0, "minor")


def test_classify_chord_single_note_defaults_major():
    assert emh.classify_chord({5}) == (5, "major")


def test_classify_chord_empty_returns_none():
    assert emh.classify_chord(set()) is None


def test_group_onsets_merges_near_simultaneous_notes():
    events = [(0, 60), (2, 64), (5, 67), (960, 60)]
    groups = emh.group_onsets(events, tolerance_ticks=10)
    assert groups == [(0, [60, 64, 67]), (960, [60])]


def test_group_onsets_splits_onsets_beyond_tolerance():
    events = [(0, 60), (20, 64)]
    groups = emh.group_onsets(events, tolerance_ticks=10)
    assert groups == [(0, [60]), (20, [64])]


def test_build_harmony_events_basic_progression():
    # C major at tick 0, G major at tick 960
    note_events = [(0, 48), (0, 52), (0, 55), (960, 43), (960, 47), (960, 50)]
    events = emh.build_harmony_events(note_events)
    assert [(e["start"], e["root"], e["quality"]) for e in events] == [(0, 0, "major"), (960, 7, "major")]
    assert "slashBass" not in events[0]


def test_build_harmony_events_detects_slash_bass():
    # C major triad (root C, pitch class 0) with E (pitch class 4) as the
    # lowest sounding note -> C/E
    note_events = [(0, 52), (0, 55), (0, 60)]  # E3, G3, C4
    events = emh.build_harmony_events(note_events)
    assert events[0]["root"] == 0
    assert events[0]["quality"] == "major"
    assert events[0]["slashBass"] == 4


def test_resolve_harmony_channels_excludes_drums_and_vocal_by_default(tmp_path):
    from midi_fixtures import make_karaoke_midi

    mid = make_karaoke_midi(tmp_path / "k.mid")
    channels = emh.resolve_harmony_channels(mid, {}, vocal_channel=1)  # Flute's channel
    assert channels == [2]  # Piano's channel only — not the vocal channel, not drums


def test_resolve_harmony_channels_honors_explicit_config(tmp_path):
    from midi_fixtures import make_karaoke_midi

    mid = make_karaoke_midi(tmp_path / "k.mid")
    assert emh.resolve_harmony_channels(mid, {"harmonyChannel": 3}, vocal_channel=1) == [3]
    assert emh.resolve_harmony_channels(mid, {"instrumentalChannels": [3, 4]}, vocal_channel=1) == [3, 4]


def test_resolve_harmony_channels_works_on_format0_style_single_track(tmp_path):
    from midi_fixtures import make_format0_style_karaoke_midi

    mid = make_format0_style_karaoke_midi(tmp_path / "f0.mid")
    channels = emh.resolve_harmony_channels(mid, {}, vocal_channel=2)
    assert channels == [1]  # the accompaniment channel, not vocal (2) or drums (9)
