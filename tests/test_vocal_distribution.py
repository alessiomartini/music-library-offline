import numpy as np

from vocal_distribution import distribution, note_seconds


def hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def test_seconds_are_weighted_by_time_not_by_note_count():
    hop = 0.01
    # A3 for 2 s, C4 for 1 s, silence, A3 again for 1 s, then a 0.03 s blip on C6 (dropped).
    f0 = np.array([hz(57)] * 200 + [hz(60)] * 100 + [np.nan] * 50 + [hz(57)] * 100 + [hz(84)] * 3)
    prob = np.where(np.isfinite(f0), 0.9, 0.0)
    seconds = note_seconds(f0, prob, hop)
    assert seconds == {57: 3.0, 60: 1.0}
    d = distribution(seconds)
    assert d["histogram"] == {"57": 0.75, "60": 0.25}
    assert (d["low"], d["high"], d["seconds"]) == (57, 60, 4.0)
    assert (d["coreLow"], d["coreHigh"]) == (57, 60)


def test_unvoiced_frames_and_rare_notes_do_not_set_the_range():
    hop = 0.01
    f0 = np.array([hz(48)] * 10 + [hz(62)] * 3000)
    prob = np.array([0.9] * 10 + [0.9] * 2990 + [0.1] * 10)
    d = distribution(note_seconds(f0, prob, hop))
    # C3 is 0.1 s out of 30 s: in the histogram, but below the 1% share that sets the range.
    assert d["low"] == 62 and "48" in d["histogram"]


def test_vibrato_around_a_note_counts_as_that_note():
    hop = 0.01
    t = np.arange(300) * hop
    # A3 with a +-40 cent, 6 Hz vibrato: raw rounding alone would still stay on A3, add 4-frame wobble to 60.
    cents = 40 * np.sin(2 * np.pi * 6 * t)
    f0 = hz(57) * 2 ** (cents / 1200)
    f0[100:103] = hz(58)  # a 30 ms glitch inside the held note
    d = distribution(note_seconds(f0, np.full(300, 0.9), hop))
    assert d["histogram"] == {"57": 1.0}
