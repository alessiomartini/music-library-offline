import numpy as np

from vocal_distribution import distribution, sung_notes


def hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def test_time_and_count_histograms_differ():
    hop = 0.01
    # A3 for 2 s, C4 for 1 s, silence, A3 again for 1 s, then a 0.03 s blip on C6 (dropped).
    f0 = np.array([hz(57)] * 200 + [hz(60)] * 100 + [np.nan] * 50 + [hz(57)] * 100 + [hz(84)] * 3)
    prob = np.where(np.isfinite(f0), 0.9, 0.0)
    notes = sung_notes(f0, prob, hop)
    assert notes == [(57, 2.0), (60, 1.0), (57, 1.0)]
    d = distribution(notes)
    assert d["histogram"] == {"57": 0.75, "60": 0.25}           # by time: 3 s of A3, 1 s of C4
    assert d["countHistogram"] == {"57": 0.6667, "60": 0.3333}  # by count: A3 twice, C4 once
    assert (d["low"], d["high"], d["seconds"], d["notes"]) == (57, 60, 4.0, 3)
    assert (d["coreLow"], d["coreHigh"]) == (57, 60)


def test_rare_notes_are_in_the_histogram_but_do_not_set_the_range():
    hop = 0.01
    f0 = np.array([hz(60)] * 10 + [hz(62)] * 3000)
    prob = np.array([0.9] * 10 + [0.9] * 2990 + [0.05] * 10)
    d = distribution(sung_notes(f0, prob, hop))
    # C4 is 0.1 s out of 30 s: in the histogram, but below the 1% share that sets the range.
    assert d["low"] == 62 and "60" in d["histogram"]


def test_a_dropped_glitch_inside_a_held_note_leaves_one_note():
    hop = 0.01
    t = np.arange(300) * hop
    f0 = hz(57) * 2 ** (40 * np.sin(2 * np.pi * 6 * t) / 1200)  # A3 with a +-40 cent vibrato
    f0[200:212] = hz(64)  # a 120 ms pitch error: too long to smooth, shorter than the shortest note
    notes = sung_notes(f0, np.full(300, 0.9), hop, min_run_s=0.15)
    assert [n for n, _ in notes] == [57]


def test_a_video_matches_any_deezer_version_of_the_song():
    from vocal_distribution import pick_videos
    results = [("live", 301.0, None, 9), ("single", 238.0, None, 5), ("nodur", None, None, 1)]
    # Deezer lists the album version (256 s) first and the single (237 s) later.
    assert pick_videos(results, [256, 237], "X")[0] == ("single", 237)
    assert pick_videos(results, [400], "X") == []


def test_three_uploads_agreeing_on_a_duration_close_to_deezer_win():
    from vocal_distribution import pick_videos
    results = [("a", 234.0, None, 0), ("b", 238.0, None, 0), ("c", 240.0, None, 0), ("d", 301.0, None, 0)]
    assert pick_videos(results, [256], "X") == [("b", 238)]   # 7 Years: Deezer only has the 256 s version
    assert pick_videos(results, [330], "X") == []              # agreeing, but too far from any Deezer version
    assert pick_videos([("a", 234.0, None, 0), ("d", 301.0, None, 0)], [256], "X") == []  # two are not enough


def test_official_channels_and_views_come_first():
    from vocal_distribution import official, pick_videos
    assert official("Robin Williams - Topic", "Robin Williams")
    assert official("AlexBrittiVEVO", "Alex Britti") and official("Alex Britti", "Alex Britti, Neri Per Caso")
    assert not official("lyricscentral815", "Robin Williams")
    results = [("fan", 163.0, "GEORGEN2890", 2_462_958), ("topic", 172.0, "Robin Williams - Topic", 8_203_170),
               ("lyrics", 239.0, "lyricscentral815", 737_014)]
    # Deezer has no matching version: only the official upload is trusted.
    assert pick_videos(results, [], "Robin Williams") == [("topic", 172)]
    # Several uploads match Deezer: the official one first, then by views.
    both = [("fan", 171.0, "fans", 9_000_000), ("topic", 172.0, "Robin Williams - Topic", 10), ("other", 170.0, "x", 100)]
    assert [v for v, _ in pick_videos(both, [171], "Robin Williams")] == ["topic", "fan", "other"]


def test_a_cluster_an_octave_away_is_dropped_but_notes_joining_the_range_stay():
    from vocal_distribution import drop_strays
    # Melody on A3..E4 (a gap of one semitone between scale notes is normal), a brief
    # G4 next to it, and an octave-error cluster around A4 three empty semitones away.
    notes = [(57, 30.0), (59, 30.0), (60, 30.0), (62, 30.0), (64, 30.0), (66, 0.5), (70, 0.5), (71, 0.5)]
    kept = [n for n, _ in drop_strays(notes)]
    assert kept == [57, 59, 60, 62, 64, 66]
