"""Synthetic karaoke-style MIDI builders shared by the MIDI-first pipeline
tests. Not a real-world sample — see midi_track_utils.py's docstring on
parse_karaoke_syllables for the caveat that real source files should still
be checked once available."""
import mido


def build_meta_track(tempo_bpm=120, numerator=4, denominator=4):
    track = mido.MidiTrack()
    track.append(mido.MetaMessage("track_name", name="Karaoke", time=0))
    track.append(mido.MetaMessage("time_signature", numerator=numerator, denominator=denominator, time=0))
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(tempo_bpm), time=0))
    return track


def build_note_track(name, program, channel, notes):
    """notes: [(start_tick, pitch, duration_ticks)], non-overlapping, sorted by start."""
    track = mido.MidiTrack()
    track.append(mido.MetaMessage("track_name", name=name, time=0))
    track.append(mido.Message("program_change", program=program, channel=channel, time=0))
    last = 0
    for start, pitch, duration in notes:
        track.append(mido.Message("note_on", note=pitch, velocity=90, channel=channel, time=start - last))
        track.append(mido.Message("note_off", note=pitch, velocity=0, channel=channel, time=duration))
        last = start + duration
    return track


def build_chord_track(name, program, channel, chords):
    """chords: [(start_tick, [pitches], duration_ticks)]."""
    track = mido.MidiTrack()
    track.append(mido.MetaMessage("track_name", name=name, time=0))
    track.append(mido.Message("program_change", program=program, channel=channel, time=0))
    last = 0
    for start, pitches, duration in chords:
        gap = start - last
        for i, p in enumerate(pitches):
            track.append(mido.Message("note_on", note=p, velocity=80, channel=channel, time=gap if i == 0 else 0))
        for i, p in enumerate(pitches):
            track.append(mido.Message("note_off", note=p, velocity=0, channel=channel, time=duration if i == 0 else 0))
        last = start + duration
    return track


def build_lyric_track(name, events, event_type="lyrics"):
    """events: [(tick, text)]."""
    track = mido.MidiTrack()
    track.append(mido.MetaMessage("track_name", name=name, time=0))
    last = 0
    for tick, text in events:
        track.append(mido.MetaMessage(event_type, text=text, time=tick - last))
        last = tick
    return track


def build_drum_track(notes):
    """notes: [(start_tick, pitch, duration_ticks)] on GM channel 10 (index 9)."""
    track = mido.MidiTrack()
    track.append(mido.MetaMessage("track_name", name="Drums", time=0))
    last = 0
    for start, pitch, duration in notes:
        track.append(mido.Message("note_on", note=pitch, velocity=100, channel=9, time=start - last))
        track.append(mido.Message("note_off", note=pitch, velocity=0, channel=9, time=duration))
        last = start + duration
    return track


def make_format0_style_karaoke_midi(path, ticks_per_beat=120):
    """A single-track, multi-channel karaoke file, modeled directly on a
    real file from Alessio's collection ("Zappatore - M. Merola.kar"):
    voice, instruments, and drums are distinguished only by MIDI channel,
    not by separate tracks, and the lyric text uses a leading
    "***title***"/"\r"-delimited header block followed by real syllables
    closed by a *trailing* space rather than the classic leading-space /
    trailing-hyphen convention."""
    mid = mido.MidiFile(ticks_per_beat=ticks_per_beat)
    track = mido.MidiTrack()
    mid.tracks.append(track)
    track.append(mido.MetaMessage("track_name", name="Zappatore", time=0))
    track.append(mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0))
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(100), time=0))

    events = []  # (abs_tick, message)
    # Header block: not real lyrics.
    events.append((0, mido.MetaMessage("lyrics", text="***Test Song***", time=0)))
    events.append((0, mido.MetaMessage("lyrics", text="\r", time=0)))
    events.append((0, mido.MetaMessage("lyrics", text="***M. Merola***", time=0)))
    events.append((0, mido.MetaMessage("lyrics", text="\r", time=0)))
    # Real syllables: "Hel" + "lo " closes "Hello"; "world " closes itself.
    events.append((240, mido.MetaMessage("lyrics", text="Hel", time=0)))
    events.append((360, mido.MetaMessage("lyrics", text="lo ", time=0)))
    events.append((600, mido.MetaMessage("lyrics", text="world ", time=0)))

    # Channel 1: an accompaniment chord at tick 0.
    for pitch in (48, 52, 55):
        events.append((0, mido.Message("note_on", note=pitch, velocity=80, channel=1, time=0)))
    for pitch in (48, 52, 55):
        events.append((240, mido.Message("note_off", note=pitch, velocity=0, channel=1, time=0)))
    # Channel 2: the vocal line, timed to coincide with the lyric ticks.
    events.append((240, mido.Message("note_on", note=60, velocity=90, channel=2, time=0)))
    events.append((360, mido.Message("note_off", note=60, velocity=0, channel=2, time=0)))
    events.append((360, mido.Message("note_on", note=62, velocity=90, channel=2, time=0)))
    events.append((600, mido.Message("note_off", note=62, velocity=0, channel=2, time=0)))
    events.append((600, mido.Message("note_on", note=64, velocity=90, channel=2, time=0)))
    events.append((840, mido.Message("note_off", note=64, velocity=0, channel=2, time=0)))
    # Channel 9: drums, must never be picked as vocal or default harmony.
    events.append((0, mido.Message("note_on", note=36, velocity=100, channel=9, time=0)))
    events.append((120, mido.Message("note_off", note=36, velocity=0, channel=9, time=0)))

    events.sort(key=lambda e: e[0])
    last = 0
    for abs_tick, msg in events:
        msg.time = abs_tick - last
        track.append(msg)
        last = abs_tick
    mid.save(str(path))
    return mido.MidiFile(str(path))


def make_karaoke_midi(path, ticks_per_beat=480):
    """A small 5-note song: "Hello" (2 syllables) - "world" (held across two
    notes via an explicit melisma continuation marker) - "test" (1
    syllable). The vocal line is disguised on a "Flute" GM program (73),
    not a voice-like one, deliberately — see midi_track_utils.detect_vocal_track.
    A 2-chord "Piano" accompaniment track and a drum track (to be ignored)
    round it out."""
    mid = mido.MidiFile(ticks_per_beat=ticks_per_beat)
    mid.tracks.append(build_meta_track())
    mid.tracks.append(build_note_track("Flute", 73, 1, [
        (0, 60, 480), (480, 62, 480), (960, 64, 480), (1440, 65, 480), (1920, 67, 480),
    ]))
    mid.tracks.append(build_lyric_track("Words", [
        (0, "Hel-"), (480, "lo"), (960, " world"), (1440, "-"), (1920, " test"),
    ]))
    mid.tracks.append(build_chord_track("Piano", 0, 2, [
        (0, [48, 52, 55], 960), (960, [43, 47, 50], 960),
    ]))
    mid.tracks.append(build_drum_track([(0, 36, 480), (480, 36, 480)]))
    mid.save(str(path))
    return mido.MidiFile(str(path))
