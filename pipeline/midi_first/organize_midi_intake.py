#!/usr/bin/env python3
"""
MIDI intake and organization tool.

Alessio drops newly downloaded MIDI files (whatever filename they arrive
as — expected pattern "Artist - Title.mid") into midi-intake/inbox/. This
script groups them by song, tries to detect which website each came from,
finds files that are exact-content duplicates re-hosted under a different
name, and moves everything into midi-intake/library/<slug>/ with the
source site(s) folded into the filename.

"Duplicate" means the same musical content (same notes/timing, hashed
while ignoring copyright/text metadata) — not just a similar filename.
Two genuinely different transcriptions of the same song are kept side by
side, not merged; they're future material for cross-referencing multiple
MIDI sources of one song (not attempted by this tool).

Dry-run by default: prints a report, changes nothing. Pass --apply to
actually move/rename/delete files.

Run with:  python pipeline/midi_first/organize_midi_intake.py [--apply]
"""
import argparse
import hashlib
import json
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import mido

REPO_ROOT = Path(__file__).parent.parent.parent
INBOX_DIR = REPO_ROOT / "midi-intake" / "inbox"
LIBRARY_DIR = REPO_ROOT / "midi-intake" / "library"
SONGS_DIR = REPO_ROOT / "songs"
OVERRIDES_PATH = REPO_ROOT / "midi-intake" / "source-overrides.json"
TITLE_ARTIST_ORDER_OVERRIDES_PATH = REPO_ROOT / "midi-intake" / "title-artist-overrides.json"
# Sibling repo, best-effort only (title cross-check to avoid slug drift).
WEB_SONGS_DIR = REPO_ROOT.parent / "music-library" / "src" / "data" / "songs"


def safe_print(message: str) -> None:
    """print() that can't crash on a console codepage that doesn't cover a
    character in a filename (e.g. Windows cp1252 vs. accented titles)."""
    encoding = sys.stdout.encoding or "ascii"
    print(message.encode(encoding, errors="replace").decode(encoding), flush=True)


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[’'`]", "", text)
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text


# Real observed data has TWO conventions mixed together across source
# sites: most of Alessio's bulk Neapolitan-song collection is
# "Title - Artist.mid" (e.g. "Voglio A Te - G. Celeste.mid"), while some
# individually-picked files are "Artist - Title.mid" (e.g.
# "Dalla - 4 Marzo 1943.mid", "Queen - Bohemian Rhapsody.mid"). Guessing
# wrong here is exactly the kind of collision Alessio flagged as important
# (see resolve_slug_collisions) — dozens of different songs by the same
# artist would otherwise collapse onto one "song" if the artist segment is
# mistaken for the title.
#
# An abbreviated "Initial. Surname" credit (e.g. "N. D'Angelo", "R. Carosone")
# or the literal "Vari" ("Various artists") marker are strong, unambiguous
# signals for which segment is the artist, observed abundantly in the real
# collection; when neither segment matches, this falls back to
# "Title - Artist" (the collection's dominant convention) — known
# exceptions that don't match either signal (e.g. "Dalla - ...",
# "Queen - ...", "The Beatles - ...") need an entry in
# title-artist-overrides.json (see load_title_artist_order_overrides) rather
# than fighting the default.
_INITIAL_NAME_RE = re.compile(r"^[A-Z]\.\s*(?:[A-Z]\.\s*)?\S")
_VARIOUS_ARTISTS_RE = re.compile(r"^vari\.?$", re.IGNORECASE)


def looks_like_artist_fragment(segment: str) -> bool:
    segment = segment.strip()
    return bool(_INITIAL_NAME_RE.match(segment)) or bool(_VARIOUS_ARTISTS_RE.match(segment))


def parse_artist_title(filename: str, order_override: str | None = None) -> tuple[str, str]:
    """order_override, from title-artist-overrides.json, is 'artist-first'
    or 'title-first' for a specific filename that the automatic signals
    below get wrong."""
    # A download-duplicate marker like "(2)" is always appended to the very
    # end of the *whole* original filename by the browser/OS — which lands
    # on whichever segment happens to be last, artist or title. Stripping
    # it from the full stem before splitting (rather than only from
    # whichever piece scan_inbox calls "title") keeps e.g. "N. D'Angelo"
    # and "N. D'Angelo (2)" from being treated as two different artists.
    stem = strip_download_suffix(Path(filename).stem)
    if " - " not in stem:
        return "", stem.strip()
    first, second = (s.strip() for s in stem.split(" - ", 1))
    if order_override == "artist-first":
        return first, second
    if order_override == "title-first":
        return second, first
    if looks_like_artist_fragment(second):
        return second, first
    if looks_like_artist_fragment(first):
        return first, second
    return second, first  # default: "Title - Artist", the collection's dominant convention


# Browsers/download managers append these when a same-named file already
# exists (e.g. downloading the same MIDI twice), which would otherwise
# split one song into two separate groups by title text alone.
_DOWNLOAD_SUFFIX_RE = re.compile(r"\s*[\(\[](?:copy|copia|\d+)[\)\]]$|\s*-\s*copy$", re.IGNORECASE)


def strip_download_suffix(title: str) -> str:
    previous = None
    while previous != title:
        previous = title
        title = _DOWNLOAD_SUFFIX_RE.sub("", title).strip()
    return title


# The same song commonly shows up as several genuinely different MIDI/.kar
# interpretations — piano-only, full band, live, a different transcriber's
# take. A trailing "(...)"/"[...]" or " - ..." on the title is usually that
# kind of qualifier, not part of the song's actual title, and must NOT
# split them into separate songs/folders — but it's exactly the detail that
# lets Alessio tell interpretations apart, so it stays in the *filename*
# (see scan_inbox) while being stripped only from the *grouping* key/slug.
# Only a TRAILING parenthetical is treated this way, so a title that
# legitimately starts with one (e.g. "(I Can't Get No) Satisfaction") is
# untouched.
_TRAILING_HINT_RE = re.compile(r"\s*[\(\[]([^()\[\]]+)[\)\]]\s*$")
_TRAILING_DASH_HINT_RE = re.compile(r"\s+-\s+(\S.*)$")


def split_title_hint(title: str) -> tuple[str, str | None]:
    match = _TRAILING_HINT_RE.search(title)
    if match:
        core = title[: match.start()].strip()
        if core:
            return core, match.group(1).strip()
    match = _TRAILING_DASH_HINT_RE.search(title)
    if match:
        core = title[: match.start()].strip()
        if core:
            return core, match.group(1).strip()
    return title, None


def load_overrides() -> dict[str, str]:
    if not OVERRIDES_PATH.exists():
        return {}
    data = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def load_title_artist_order_overrides() -> dict[str, str]:
    """filename -> 'artist-first' | 'title-first', for a file the automatic
    signals in parse_artist_title get wrong."""
    if not TITLE_ARTIST_ORDER_OVERRIDES_PATH.exists():
        return {}
    data = json.loads(TITLE_ARTIST_ORDER_OVERRIDES_PATH.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def read_zone_identifier_site(path: Path) -> str | None:
    """Best-effort: the NTFS alternate data stream browsers attach to a
    downloaded file. Lost if the file was moved through a zip, copied from
    a non-NTFS filesystem, or wasn't downloaded directly by a browser."""
    try:
        ads_text = Path(str(path) + ":Zone.Identifier").read_text(
            encoding="utf-8", errors="replace"
        )
    except OSError:
        return None
    match = re.search(r"HostUrl=(\S+)", ads_text)
    if not match:
        return None
    from urllib.parse import urlparse

    netloc = urlparse(match.group(1)).netloc
    return netloc or None


_DOMAIN_RE = re.compile(r"\b(?:www\.)?[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+\b")

# Without this, a plain "two-or-more dot-separated groups" match also fires
# on non-URL abbreviations that are common in Italian copyright text, e.g.
# "S.p.A." or "S.r.l." (company-type suffixes) — a real false positive
# observed on Alessio's actual files. Restricting an un-prefixed match to a
# recognizable TLD avoids that without needing a full public-suffix list.
_COMMON_TLDS = {
    "com", "net", "org", "info", "biz", "co", "io",
    "it", "de", "uk", "fr", "es", "nl", "eu", "us",
}


def _looks_like_domain(candidate: str) -> bool:
    return candidate.rsplit(".", 1)[-1].lower() in _COMMON_TLDS


def read_midi_meta_site(path_or_mid: "Path | mido.MidiFile") -> str | None:
    """Best-effort: a domain-looking string in the MIDI's own
    Copyright/Text meta events, when the source site stamped one in.
    Accepts either a path (opens it) or an already-parsed MidiFile (to
    avoid re-parsing the same file twice — see scan_inbox)."""
    mid = path_or_mid
    if isinstance(mid, Path):
        try:
            mid = mido.MidiFile(str(mid), clip=True)
        except (OSError, ValueError, EOFError, IndexError, KeyError):
            return None
    candidates: list[str] = []
    for track in mid.tracks:
        for msg in track:
            if msg.is_meta and msg.type in ("copyright", "text"):
                candidates.extend(_DOMAIN_RE.findall(msg.text))
    preferred = [c for c in candidates if c.lower().startswith("www.")]
    if preferred:
        return preferred[0]
    plausible = [c for c in candidates if _looks_like_domain(c)]
    return plausible[0] if plausible else None


def detect_source(path: Path, overrides: dict[str, str], mid: "mido.MidiFile | None" = None) -> tuple[str, str]:
    """Returns (site, method) where method is 'override', 'zone-identifier',
    'midi-meta', or 'unknown'. Pass an already-parsed `mid` (see scan_inbox)
    to avoid re-parsing the file a second time just for this check."""
    if path.name in overrides:
        return overrides[path.name], "override"
    site = read_zone_identifier_site(path)
    if site:
        return site, "zone-identifier"
    site = read_midi_meta_site(mid if mid is not None else path)
    if site:
        return site, "midi-meta"
    return "unknown", "unknown"


def note_event_hash(path_or_mid: "Path | mido.MidiFile") -> str | None:
    """Hash of the note_on stream (tick, pitch, velocity) plus the file's
    own ticks_per_beat, ignoring track layout and text/copyright metadata —
    so two re-exports of the same performance hash identically even if a
    different site re-stamped the copyright text or reordered tracks.
    Accepts either a path (opens it) or an already-parsed MidiFile."""
    mid = path_or_mid
    if isinstance(mid, Path):
        try:
            mid = mido.MidiFile(str(mid))
        except (OSError, ValueError, EOFError, IndexError, KeyError):
            return None
    events: list[tuple[int, int, int]] = []
    for track in mid.tracks:
        abs_tick = 0
        for msg in track:
            abs_tick += msg.time
            if msg.type == "note_on" and msg.velocity > 0:
                events.append((abs_tick, msg.note, msg.velocity))
    events.sort()
    payload = json.dumps({"ticks_per_beat": mid.ticks_per_beat, "notes": events}).encode()
    return hashlib.sha256(payload).hexdigest()


def known_titles() -> dict[str, str]:
    """slug -> title, from songs/*.json (already-transcribed songs) and,
    best-effort, from the sibling music-library web repo's song metadata
    (songs not yet transcribed but already known to the site)."""
    titles: dict[str, str] = {}
    for config_path in SONGS_DIR.glob("*.json"):
        config = json.loads(config_path.read_text(encoding="utf-8"))
        if "title" in config:
            titles[config_path.stem] = config["title"]
    if WEB_SONGS_DIR.is_dir():
        for ts_path in WEB_SONGS_DIR.glob("*.ts"):
            if ts_path.stem == "index":
                continue
            match = re.search(r"title:\s*['\"]([^'\"]+)['\"]", ts_path.read_text(encoding="utf-8"))
            if match:
                titles.setdefault(ts_path.stem, match.group(1))
    return titles


@dataclass
class MidiEntry:
    path: Path
    artist: str
    title: str          # full display title, e.g. "Napul'e' (Live 1981)" — kept in the filename
    group_title: str    # hint stripped, e.g. "Napul'e'" — used for the grouping key/slug
    key: str
    slug: str
    site: str
    detect_method: str
    hash: str | None
    keep: bool = True
    merged_sites: list[str] = field(default_factory=list)
    dest_name: str = ""
    library_match: Path | None = None


_DEST_STEM_RE = re.compile(r"^(?P<title>.+)__src-(?P<sites>.+)$")


def parse_dest_stem(stem: str) -> tuple[str, list[str]]:
    match = _DEST_STEM_RE.match(stem)
    if not match:
        return stem, []
    sites = match.group("sites")
    return match.group("title"), [] if sites == "unknown" else sites.split("+")


def scan_library() -> dict[str, dict]:
    """hash -> {"path", "sites"} for files a previous run already organized,
    so a later run recognizes a re-download of something already filed away
    instead of only deduping within the current inbox batch."""
    index: dict[str, dict] = {}
    if not LIBRARY_DIR.is_dir():
        return index
    library_paths = sorted(p for pattern in MIDI_EXTENSIONS for p in LIBRARY_DIR.glob(f"*/{pattern}"))
    for path in library_paths:
        file_hash = note_event_hash(path)
        if file_hash is None:
            continue
        _, sites = parse_dest_stem(path.stem)
        index[file_hash] = {"path": path, "sites": sites}
    return index


def merge_against_library(groups: dict[str, list[MidiEntry]], library_index: dict[str, dict]) -> list[tuple[Path, Path]]:
    """Drops inbox entries whose content is already in the organized
    library (they're redundant re-downloads) and, if one of them carries a
    source site the library copy doesn't have yet, plans a rename of the
    library file to fold it in. Returns the planned (old, new) renames."""
    renames: list[tuple[Path, Path]] = []
    for group in groups.values():
        for entry in group:
            if not entry.keep or entry.hash is None:
                continue
            lib = library_index.get(entry.hash)
            if lib is None:
                continue
            entry.keep = False
            entry.library_match = lib["path"]
            if entry.site != "unknown" and entry.site not in lib["sites"]:
                new_sites = lib["sites"] + [entry.site]
                title, _ = parse_dest_stem(lib["path"].stem)
                new_name = f"{title}__src-{'+'.join(new_sites)}{lib['path'].suffix}"
                new_path = lib["path"].with_name(new_name)
                renames.append((lib["path"], new_path))
                lib["sites"] = new_sites
                lib["path"] = new_path  # chains correctly if another dup in this run adds a third site
    return renames


# .kar ("Soft Karaoke") files are ordinary MIDI files by a different
# extension convention — mido reads them exactly like a .mid file.
MIDI_EXTENSIONS = ("*.mid", "*.midi", "*.kar")


def scan_inbox(overrides: dict[str, str], title_artist_order_overrides: dict[str, str] | None = None) -> list[MidiEntry]:
    entries = []
    paths = sorted(p for pattern in MIDI_EXTENSIONS for p in INBOX_DIR.glob(pattern))
    total = len(paths)
    title_artist_order_overrides = title_artist_order_overrides or {}
    for i, path in enumerate(paths):
        if i % 50 == 0:
            safe_print(f"... scanning {i}/{total}: {path.name!r}")
        artist, title = parse_artist_title(path.name, title_artist_order_overrides.get(path.name))
        group_title, _hint = split_title_hint(title)
        key = slugify(f"{artist} {group_title}" if artist else group_title)
        slug = slugify(group_title)
        try:
            mid = mido.MidiFile(str(path), clip=True)
        except (OSError, ValueError, EOFError, IndexError, KeyError) as e:
            safe_print(f"WARNING: couldn't parse {path.name!r} as MIDI ({e}), skipping")
            continue
        site, method = detect_source(path, overrides, mid)
        entries.append(
            MidiEntry(
                path=path,
                artist=artist,
                title=title,
                group_title=group_title,
                key=key,
                slug=slug,
                site=site,
                detect_method=method,
                hash=note_event_hash(mid),
            )
        )
    return entries


def group_and_dedupe(entries: list[MidiEntry]) -> dict[str, list[MidiEntry]]:
    groups: dict[str, list[MidiEntry]] = {}
    for entry in entries:
        groups.setdefault(entry.key, []).append(entry)

    for group in groups.values():
        by_hash: dict[str, list[MidiEntry]] = {}
        for entry in group:
            if entry.hash is not None:
                by_hash.setdefault(entry.hash, []).append(entry)
        for same_content in by_hash.values():
            if len(same_content) < 2:
                continue
            keeper, *rest = same_content
            sites = [keeper.site] + [e.site for e in rest if e.site != "unknown"]
            keeper.merged_sites = [s for i, s in enumerate(sites) if s not in sites[:i]]
            for dupe in rest:
                dupe.keep = False

    for group in groups.values():
        used_names: set[str] = set()
        for entry in group:
            if not entry.keep:
                continue
            sites = entry.merged_sites or ([entry.site] if entry.site != "unknown" else [])
            site_tag = "+".join(sites) if sites else "unknown"
            suffix = entry.path.suffix.lower()
            base_name = f"{entry.title}__src-{site_tag}"
            name = f"{base_name}{suffix}"
            # Two genuinely different (non-duplicate) interpretations can
            # still land on the same title+source tag (e.g. two unrelated
            # uploads on the same site with no other distinguishing text) —
            # keep every kept file individually addressable rather than
            # silently colliding on rename.
            disambiguator = 2
            while name in used_names:
                name = f"{base_name} ({disambiguator}){suffix}"
                disambiguator += 1
            used_names.add(name)
            entry.dest_name = name

    return groups


def read_library_meta(slug: str) -> dict | None:
    meta_path = LIBRARY_DIR / slug / ".meta.json"
    if not meta_path.exists():
        return None
    return json.loads(meta_path.read_text(encoding="utf-8"))


def write_library_meta(slug: str, artist: str) -> None:
    if not artist:
        return
    meta_path = LIBRARY_DIR / slug / ".meta.json"
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta = read_library_meta(slug) or {"artists": []}
    if artist not in meta["artists"]:
        meta["artists"].append(artist)
        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")


def resolve_slug_collisions(groups: dict[str, list[MidiEntry]]) -> list[str]:
    """A destination folder name (slug) must uniquely identify one song.
    Two different songs that happen to share a title (different artists)
    must NOT be filed into the same folder — unlike two different
    *interpretations* of the *same* song/artist, which are meant to share
    one folder. Detects both an in-batch collision (two groups in this run
    resolving to the same slug) and a cross-run one (this run's slug
    already belongs, per the target folder's .meta.json, to a different
    artist) and disambiguates by folding the artist into the slug. Returns
    human-readable warnings for the report."""
    warnings: list[str] = []

    slug_to_keys: dict[str, set[str]] = {}
    for key, group in groups.items():
        slug_to_keys.setdefault(group[0].slug, set()).add(key)
    for slug, keys in slug_to_keys.items():
        if len(keys) < 2:
            continue
        artists = sorted({groups[k][0].artist or "(unknown artist)" for k in keys})
        warnings.append(f"'{slug}' would be shared by {len(keys)} different songs ({', '.join(artists)}) — disambiguating by artist")
        for key in keys:
            group = groups[key]
            artist = group[0].artist
            new_slug = slugify(f"{group[0].slug}-{artist}") if artist else group[0].slug
            for entry in group:
                entry.slug = new_slug

    for group in groups.values():
        slug = group[0].slug
        artist = group[0].artist
        meta = read_library_meta(slug)
        if meta is None or not artist or artist in meta["artists"]:
            continue
        new_slug = slugify(f"{slug}-{artist}")
        warnings.append(f"'{slug}' already exists in the library for {meta['artists']} — filing {artist!r} as {new_slug!r} instead")
        for entry in group:
            entry.slug = new_slug

    return warnings


def build_report(groups: dict[str, list[MidiEntry]], known: dict[str, str], library_renames: list[tuple[Path, Path]], collision_warnings: list[str]) -> dict:
    known_slugs = set(known.keys())
    songs = []
    for key, group in sorted(groups.items()):
        slug = group[0].slug
        songs.append(
            {
                "key": key,
                "slug": slug,
                "isNewSong": slug not in known_slugs,
                "files": [
                    {
                        "original": e.path.name,
                        "keep": e.keep,
                        "site": e.site,
                        "detectMethod": e.detect_method,
                        "destName": e.dest_name if e.keep else None,
                        "duplicateOfMergedInto": None if e.keep else (
                            str(e.library_match.relative_to(REPO_ROOT)) if e.library_match
                            else next((o.path.name for o in group if o.keep and o.hash == e.hash), None)
                        ),
                    }
                    for e in group
                ],
            }
        )
    return {
        "generatedAt": datetime.now().isoformat(),
        "songs": songs,
        "libraryRenames": [
            {"from": str(old.relative_to(REPO_ROOT)), "to": str(new.relative_to(REPO_ROOT))}
            for old, new in library_renames
        ],
        "collisionWarnings": collision_warnings,
    }


def print_report(report: dict) -> None:
    if report["collisionWarnings"]:
        safe_print("\nCOLLISION WARNINGS (different songs sharing a title):")
        for w in report["collisionWarnings"]:
            safe_print(f"  ! {w}")
    safe_print(f"\n{len(report['songs'])} song group(s) found in {INBOX_DIR}\n")
    for song in report["songs"]:
        new_tag = " [NEW SONG — no songs/*.json or web metadata yet]" if song["isNewSong"] else ""
        safe_print(f"- {song['slug']}{new_tag}")
        for f in song["files"]:
            if f["keep"]:
                safe_print(f"    keep   {f['original']!r} -> {f['destName']!r}  (source: {f['site']}, via {f['detectMethod']})")
            else:
                safe_print(f"    DELETE {f['original']!r}  (exact-content duplicate, merged into {f['duplicateOfMergedInto']!r})")
    if report["libraryRenames"]:
        safe_print("\nAlready-organized files gaining a new source (renamed):")
        for r in report["libraryRenames"]:
            safe_print(f"    {r['from']!r} -> {r['to']!r}")
    safe_print("")


def apply_report(groups: dict[str, list[MidiEntry]], library_renames: list[tuple[Path, Path]]) -> None:
    for old, new in library_renames:
        old.rename(new)
        safe_print(f"renamed {old.relative_to(REPO_ROOT)} -> {new.relative_to(REPO_ROOT)} (new source added)")
    for group in groups.values():
        keepers = [e for e in group if e.keep]
        if keepers:
            slug = group[0].slug
            dest_dir = LIBRARY_DIR / slug
            dest_dir.mkdir(parents=True, exist_ok=True)
            write_library_meta(slug, group[0].artist)
            for entry in keepers:
                dest = dest_dir / entry.dest_name
                entry.path.rename(dest)
                safe_print(f"moved {entry.path.name!r} -> {dest.relative_to(REPO_ROOT)}")
        for entry in group:
            if not entry.keep:
                entry.path.unlink()
                safe_print(f"deleted {entry.path.name!r} (duplicate)")


def organize(apply: bool) -> None:
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    overrides = load_overrides()
    title_artist_order_overrides = load_title_artist_order_overrides()
    entries = scan_inbox(overrides, title_artist_order_overrides)
    if not entries:
        safe_print(f"No .mid/.midi files in {INBOX_DIR}")
        return
    groups = group_and_dedupe(entries)
    collision_warnings = resolve_slug_collisions(groups)
    library_renames = merge_against_library(groups, scan_library())
    report = build_report(groups, known_titles(), library_renames, collision_warnings)
    print_report(report)

    report_path = INBOX_DIR.parent / f"report-{datetime.now():%Y%m%d-%H%M%S}.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    safe_print(f"Wrote {report_path}")

    if apply:
        apply_report(groups, library_renames)
    else:
        safe_print("\nDry run only — nothing moved or deleted. Re-run with --apply to act on this report.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="actually move/rename/delete files (default: dry run)")
    args = parser.parse_args()
    organize(apply=args.apply)
