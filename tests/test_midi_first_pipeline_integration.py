"""End-to-end test of the MIDI-first path (import_karaoke_midi ->
extract_midi_lyrics -> extract_midi_harmony -> musicxml_to_json) against a
synthetic karaoke MIDI, run through the real MuseScore 4 CLI (this
environment has it installed — see musescore_import.find_musescore). This
is the same integration MuseScore already gets from the audio-first path's
own scripts; nothing here is MIDI-first-specific about invoking it."""
import json
import shutil
from pathlib import Path

import pytest

import extract_midi_harmony
import extract_midi_lyrics
import import_karaoke_midi
import midi_track_utils
import musescore_import
import musicxml_to_json
from midi_fixtures import make_karaoke_midi


def _musescore_available() -> bool:
    return bool(shutil.which("mscore") or Path(musescore_import.DEFAULT_WINDOWS_PATH).exists())


pytestmark = pytest.mark.skipif(not _musescore_available(), reason="MuseScore 4 not found")


def _setup(tmp_path, monkeypatch, slug="testsong"):
    for module in (import_karaoke_midi, extract_midi_lyrics, extract_midi_harmony, midi_track_utils):
        monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    songs_dir = tmp_path / "songs"
    songs_dir.mkdir()
    library_dir = tmp_path / "midi-intake" / "library" / slug
    library_dir.mkdir(parents=True)
    make_karaoke_midi(library_dir / "source.mid")
    config = {
        "slug": slug,
        "title": "Test Song",
        "originalKey": "C",
        "mode": "major",
        "tempoBpm": 120,
        "timeSignature": {"numerator": 4, "denominator": 4},
        "midiSource": {"file": "source.mid"},
    }
    (songs_dir / f"{slug}.json").write_text(json.dumps(config), encoding="utf-8")
    return config


def test_import_karaoke_midi_produces_vocal_events(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    import_karaoke_midi.import_vocal_track("testsong")

    events_path = tmp_path / "working" / "testsong" / "vocal-events.json"
    data = json.loads(events_path.read_text())
    assert data["ppq"] == 960
    pitches = [e["pitch"] for e in data["events"]]
    assert pitches == [60, 62, 64, 65, 67]


def test_extract_midi_lyrics_attaches_syllables_and_melisma(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    import_karaoke_midi.import_vocal_track("testsong")
    extract_midi_lyrics.extract("testsong")

    aligned = json.loads((tmp_path / "working" / "testsong" / "aligned-lyrics.json").read_text())
    assert aligned["syncMethod"] == "midi-native"
    assert aligned["syllables_dropped"] == 0
    notes_with_lyrics = [n for n in aligned["aligned"] if "lyrics" in n]
    assert len(notes_with_lyrics) == 5  # Hel-lo world(-held) test
    texts = [ly.get("text") for n in notes_with_lyrics for ly in n["lyrics"]]
    assert texts == ["Hel", "lo", "world", None, "test"]
    melismas = [ly.get("melisma") for n in notes_with_lyrics for ly in n["lyrics"]]
    assert melismas == [None, None, None, "continue", None]


def test_extract_midi_harmony_produces_chord_events(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    extract_midi_harmony.extract("testsong")

    harmony = json.loads((tmp_path / "working" / "testsong" / "harmony-events.json").read_text())
    assert harmony["ppq"] == 960
    qualities = [(e["root"], e["quality"]) for e in harmony["harmony"]]
    assert qualities == [(0, "major"), (7, "major")]  # C major, G major


def test_full_midi_first_pipeline_produces_valid_score_json(tmp_path, monkeypatch):
    """The real bug this guards against: musicxml_to_json.py crashing on a
    melisma-only lyric entry (no "text" key) — see its build_voice_events fix."""
    _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(musicxml_to_json, "REPO_ROOT", tmp_path)

    import_karaoke_midi.import_vocal_track("testsong")
    extract_midi_lyrics.extract("testsong")
    extract_midi_harmony.extract("testsong")
    musicxml_to_json.convert("testsong")

    output = json.loads((tmp_path / "output" / "json" / "testsong.json").read_text())
    assert output["schemaVersion"] == 1
    score = output["score"]
    assert score["ppq"] == 960
    voice_events = score["parts"][0]["events"]
    note_events = [e for e in voice_events if e["kind"] == "note"]
    assert len(note_events) == 5
    # every lyric entry has either text or a melisma marker, per score.ts's
    # validateLyrics rule
    for event in note_events:
        for lyric in event.get("lyrics", []):
            assert "text" in lyric or "melisma" in lyric
    assert score["harmony"]
