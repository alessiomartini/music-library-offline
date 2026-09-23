import mido
import pytest

import organize_midi_intake as omi


def make_midi(path, notes, copyright_text=None, ticks_per_beat=480):
    """notes: list of (tick, pitch, velocity, duration)."""
    mid = mido.MidiFile(ticks_per_beat=ticks_per_beat)
    track = mido.MidiTrack()
    mid.tracks.append(track)
    if copyright_text:
        track.append(mido.MetaMessage("copyright", text=copyright_text, time=0))
    last_tick = 0
    for tick, note, velocity, duration in notes:
        track.append(mido.Message("note_on", note=note, velocity=velocity, time=tick - last_tick))
        track.append(mido.Message("note_off", note=note, velocity=0, time=duration))
        last_tick = tick + duration
    mid.save(str(path))


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Napul'e'", "napule"),
        ("L'anno Che Verrà", "lanno-che-verra"),
        ("Don't Let Me Down", "dont-let-me-down"),
        ("We Are The Champions", "we-are-the-champions"),
        ("4 Marzo 1943", "4-marzo-1943"),
    ],
)
def test_slugify_matches_expected_pilot_song_slugs(title, expected):
    assert omi.slugify(title) == expected


def test_parse_artist_title_no_dash_is_title_only():
    assert omi.parse_artist_title("SomeTitle.mid") == ("", "SomeTitle")


def test_parse_artist_title_initial_surname_signal_wins_regardless_of_side():
    # The abbreviated-credit signal identifies the artist segment even
    # though it's on opposite sides in these two real-world-shaped names.
    assert omi.parse_artist_title("Voglio A Te - G. Celeste.mid") == ("G. Celeste", "Voglio A Te")
    assert omi.parse_artist_title("R. Carosone - Tu Vuo Fa L'americano.mid") == ("R. Carosone", "Tu Vuo Fa L'americano")


def test_parse_artist_title_vari_signal():
    assert omi.parse_artist_title("Zappatore - Vari.mid") == ("Vari", "Zappatore")


def test_parse_artist_title_defaults_to_title_first_when_ambiguous():
    # Neither segment matches a strong signal: falls back to the
    # collection's dominant "Title - Artist" convention.
    assert omi.parse_artist_title("Song - Some Band.mid") == ("Some Band", "Song")


def test_parse_artist_title_strips_download_suffix_before_splitting():
    # Regression: a "(2)" download-duplicate marker is appended to the
    # whole original filename, so it can land on the artist segment (real
    # observed data: "21 & 30 - N. D'angelo (2).mid") — it must not be
    # left dangling there, or the same artist gets treated as two different
    # ones across a duplicate pair.
    assert omi.parse_artist_title("21 & 30 - N. D'angelo (2).mid") == ("N. D'angelo", "21 & 30")
    assert omi.parse_artist_title("Song - G. Celeste (2).mid") == ("G. Celeste", "Song")


def test_parse_artist_title_order_override():
    assert omi.parse_artist_title("Dalla - Caruso.mid", order_override="artist-first") == ("Dalla", "Caruso")
    assert omi.parse_artist_title("Caruso - Dalla.mid", order_override="title-first") == ("Dalla", "Caruso")


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Song", "Song"),
        ("Song (copy)", "Song"),
        ("Song (1)", "Song"),
        ("Song (2) (1)", "Song"),
        ("Song - Copy", "Song"),
        ("Song [copia]", "Song"),
    ],
)
def test_strip_download_suffix(raw, expected):
    assert omi.strip_download_suffix(raw) == expected


@pytest.mark.parametrize(
    "raw,expected_core,expected_hint",
    [
        ("Napul'e'", "Napul'e'", None),
        ("Napul'e' (Live 1981)", "Napul'e'", "Live 1981"),
        ("Song [Piano Version]", "Song", "Piano Version"),
        ("Song - Acoustic", "Song", "Acoustic"),
        ("(I Can't Get No) Satisfaction", "(I Can't Get No) Satisfaction", None),  # leading, not trailing
    ],
)
def test_split_title_hint(raw, expected_core, expected_hint):
    core, hint = omi.split_title_hint(raw)
    assert core == expected_core
    assert hint == expected_hint


def test_read_midi_meta_site_finds_domain_in_copyright_text(tmp_path):
    path = tmp_path / "song.mid"
    make_midi(path, [(0, 60, 90, 120)], copyright_text="Sequenced for www.example-karaoke.com")
    assert omi.read_midi_meta_site(path) == "www.example-karaoke.com"


def test_read_midi_meta_site_returns_none_without_domain(tmp_path):
    path = tmp_path / "song.mid"
    make_midi(path, [(0, 60, 90, 120)], copyright_text="No URL in here")
    assert omi.read_midi_meta_site(path) is None


def test_read_midi_meta_site_keeps_full_hyphenated_domain(tmp_path):
    path = tmp_path / "song.mid"
    make_midi(path, [(0, 60, 90, 120)], copyright_text="downloaded from www.midi-smoketest.example")
    assert omi.read_midi_meta_site(path) == "www.midi-smoketest.example"


def test_note_event_hash_ignores_copyright_text_but_not_notes(tmp_path):
    notes = [(0, 60, 90, 480), (480, 62, 90, 480)]
    a = tmp_path / "a.mid"
    b = tmp_path / "b.mid"
    c = tmp_path / "c.mid"
    make_midi(a, notes, copyright_text="site one")
    make_midi(b, notes, copyright_text="a completely different copyright string")
    make_midi(c, [(0, 64, 90, 480)], copyright_text="site one")

    assert omi.note_event_hash(a) == omi.note_event_hash(b)
    assert omi.note_event_hash(a) != omi.note_event_hash(c)


def _setup_repo(tmp_path, monkeypatch):
    inbox = tmp_path / "inbox"
    library = tmp_path / "library"
    songs_dir = tmp_path / "songs"
    inbox.mkdir()
    songs_dir.mkdir()
    monkeypatch.setattr(omi, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(omi, "INBOX_DIR", inbox)
    monkeypatch.setattr(omi, "LIBRARY_DIR", library)
    monkeypatch.setattr(omi, "SONGS_DIR", songs_dir)
    monkeypatch.setattr(omi, "OVERRIDES_PATH", tmp_path / "source-overrides.json")
    monkeypatch.setattr(omi, "WEB_SONGS_DIR", tmp_path / "nonexistent-web-songs")
    return inbox, library, songs_dir


def test_groups_by_song_flags_duplicates_and_new_songs(tmp_path, monkeypatch):
    inbox, library, songs_dir = _setup_repo(tmp_path, monkeypatch)

    notes = [(0, 60, 90, 480), (480, 62, 90, 480)]
    make_midi(inbox / "Song - Vari.mid", notes, copyright_text="www.siteone.com")
    make_midi(inbox / "Song - Vari (copy).mid", notes, copyright_text="www.sitetwo.com")
    make_midi(inbox / "Different Song - Vari.mid", [(0, 64, 100, 240)])

    overrides = omi.load_overrides()
    entries = omi.scan_inbox(overrides)
    assert len(entries) == 3

    groups = omi.group_and_dedupe(entries)
    song_group = groups[omi.slugify("Vari Song")]
    assert len(song_group) == 2
    kept = [e for e in song_group if e.keep]
    dropped = [e for e in song_group if not e.keep]
    assert len(kept) == 1
    assert len(dropped) == 1
    # Both sites should be folded into the surviving entry's merged_sites.
    assert set(kept[0].merged_sites) == {"www.siteone.com", "www.sitetwo.com"}

    collision_warnings = omi.resolve_slug_collisions(groups)
    library_renames = omi.merge_against_library(groups, omi.scan_library())
    report = omi.build_report(groups, omi.known_titles(), library_renames, collision_warnings)
    assert all(s["isNewSong"] for s in report["songs"])  # nothing in songs_dir yet

    omi.apply_report(groups, library_renames)
    assert not (inbox / "Song - Vari.mid").exists() or not (inbox / "Song - Vari (copy).mid").exists()
    remaining_mids = list(library.glob("*/*.mid"))
    assert len(remaining_mids) == 2  # one survivor for "song", one for "different-song"


def test_known_titles_reads_existing_song_configs(tmp_path, monkeypatch):
    inbox, library, songs_dir = _setup_repo(tmp_path, monkeypatch)
    (songs_dir / "your-song.json").write_text('{"title": "Your Song"}', encoding="utf-8")

    make_midi(inbox / "Your Song - Elton John.mid", [(0, 60, 90, 480)])
    entries = omi.scan_inbox(omi.load_overrides())
    groups = omi.group_and_dedupe(entries)
    report = omi.build_report(groups, omi.known_titles(), [], [])

    song = next(s for s in report["songs"] if s["slug"] == "your-song")
    assert song["isNewSong"] is False


def test_reorganize_drops_redownload_of_already_organized_song(tmp_path, monkeypatch):
    """A second run, after a song is already in library/, should recognize a
    re-download of the same content as redundant rather than filing a
    duplicate copy alongside the organized one."""
    inbox, library, songs_dir = _setup_repo(tmp_path, monkeypatch)
    notes = [(0, 60, 90, 480), (480, 62, 90, 480)]

    make_midi(inbox / "Song - Vari.mid", notes, copyright_text="www.siteone.com")
    omi.organize(apply=True)
    assert list(library.glob("song/*.mid")) and not list(inbox.iterdir())

    # Same content re-downloaded later from a second site, under a new name.
    make_midi(inbox / "Song Reupload - Vari.mid", notes, copyright_text="www.sitetwo.com")
    omi.organize(apply=True)

    assert not list(inbox.iterdir())  # the redundant copy was deleted, not filed
    library_files = list(library.glob("song/*.mid"))
    assert len(library_files) == 1  # still exactly one file for this song
    assert "www.siteone.com" in library_files[0].name
    assert "www.sitetwo.com" in library_files[0].name  # new source folded into its name


def test_different_songs_same_title_land_in_different_folders(tmp_path, monkeypatch):
    """Two unrelated songs that happen to share a title (different artists)
    must never be merged into the same library folder."""
    inbox, library, songs_dir = _setup_repo(tmp_path, monkeypatch)
    make_midi(inbox / "Song - A. One.mid", [(0, 60, 90, 480)])
    make_midi(inbox / "Song - A. Two.mid", [(0, 64, 90, 480)])

    omi.organize(apply=True)

    folders = {p.name for p in library.iterdir() if p.is_dir()}
    assert folders == {"song-a-one", "song-a-two"}
    assert list((library / "song-a-one").glob("*.mid"))
    assert list((library / "song-a-two").glob("*.mid"))


def test_later_run_with_different_artist_same_title_is_disambiguated(tmp_path, monkeypatch):
    """The collision check must also catch a collision against a song
    already organized by an earlier run, not just within one batch."""
    inbox, library, songs_dir = _setup_repo(tmp_path, monkeypatch)
    make_midi(inbox / "Song - A. One.mid", [(0, 60, 90, 480)])
    omi.organize(apply=True)
    assert (library / "song").is_dir()

    make_midi(inbox / "Song - A. Two.mid", [(0, 64, 90, 480)])
    omi.organize(apply=True)

    assert (library / "song").is_dir()  # untouched
    assert (library / "song-a-two").is_dir()  # the colliding new song, disambiguated
    assert list((library / "song").glob("*.mid"))
    assert list((library / "song-a-two").glob("*.mid"))


def test_different_interpretations_of_same_song_keep_distinguishable_names(tmp_path, monkeypatch):
    inbox, library, songs_dir = _setup_repo(tmp_path, monkeypatch)
    make_midi(inbox / "Napul'e' (Piano Version) - Vari.mid", [(0, 60, 90, 480)],
              copyright_text="www.siteone.com")
    make_midi(inbox / "Napul'e' (Live 1981) - Vari.mid", [(0, 64, 90, 480)],
              copyright_text="www.siteone.com")

    omi.organize(apply=True)

    song_dir = library / "napule"
    assert song_dir.is_dir()
    names = {p.name for p in song_dir.glob("*.mid")}
    assert len(names) == 2  # both kept, distinct filenames, no collision/overwrite
    assert any("Piano Version" in n for n in names)
    assert any("Live 1981" in n for n in names)


def test_dry_run_leaves_inbox_untouched(tmp_path, monkeypatch):
    inbox, library, songs_dir = _setup_repo(tmp_path, monkeypatch)
    make_midi(inbox / "Artist - Song.mid", [(0, 60, 90, 480)])

    omi.organize(apply=False)

    assert (inbox / "Artist - Song.mid").exists()
    assert not list(library.glob("*/*.mid"))
