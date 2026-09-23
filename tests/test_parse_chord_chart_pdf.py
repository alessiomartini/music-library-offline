import parse_chord_chart_pdf as pcc


def _word(text, x0, x1, top):
    return {"text": text, "x0": x0, "x1": x1, "top": top}


def test_group_words_into_lines_splits_on_top_gap():
    words = [_word("Anna", 0, 10, 100.0), _word("come", 12, 20, 100.2), _word("SIb", 0, 5, 84.5)]
    lines = pcc.group_words_into_lines(words)
    assert [[w["text"] for w in line] for line in lines] == [["Anna", "come"], ["SIb"]]


def test_group_words_into_lines_sorts_within_line_by_x():
    words = [_word("come", 12, 20, 100.0), _word("Anna", 0, 10, 100.1)]
    lines = pcc.group_words_into_lines(words)
    assert [w["text"] for w in lines[0]] == ["Anna", "come"]


def test_is_chord_line_true_for_valid_chords():
    line = [_word("SIb", 0, 5, 0), _word("DOm7", 10, 15, 0)]
    assert pcc.is_chord_line(line) is True


def test_is_chord_line_false_for_lyrics():
    line = [_word("Anna", 0, 5, 0), _word("come", 10, 15, 0)]
    assert pcc.is_chord_line(line) is False


def test_is_chord_line_false_when_too_many_words():
    line = [_word("SIb", i * 5, i * 5 + 3, 0) for i in range(pcc.MAX_CHORD_LINE_WORDS + 1)]
    assert pcc.is_chord_line(line) is False


def test_attach_chord_to_nearest_word_prefers_overlap():
    chord = _word("SIb", 10, 20, 0)
    line = [_word("An", 0, 8, 0), _word("na", 10, 18, 0), _word("co", 25, 30, 0)]
    assert pcc.attach_chord_to_nearest_word(chord, line, excluded=set()) == 1


def test_attach_chord_to_nearest_word_falls_back_to_nearest_edge():
    # Chord positioned past the end of a short line, with no overlap.
    chord = _word("DOm", 200, 210, 0)
    line = [_word("ed", 0, 5, 0), _word("il", 10, 15, 0), _word("biliardo", 20, 60, 0)]
    assert pcc.attach_chord_to_nearest_word(chord, line, excluded=set()) == 2


def test_attach_chord_to_nearest_word_avoids_already_claimed_index():
    # Both LAb/DO and DOm fall back to the same nearest word ("biliardo")
    # under plain distance — excluding an already-claimed index must push
    # the second chord onto a different (still reasonable) word instead of
    # silently colliding with the first.
    line = [_word("ed", 0, 5, 0), _word("il", 10, 15, 0), _word("cielo", 20, 40, 0), _word("un", 45, 55, 0), _word("biliardo", 60, 100, 0)]
    lab_do = _word("LAb/DO", 174, 202, 0)
    dom = _word("DOm", 207, 221, 0)
    first = pcc.attach_chord_to_nearest_word(lab_do, line, excluded=set())
    second = pcc.attach_chord_to_nearest_word(dom, line, excluded={first})
    assert first != second


def test_extract_lines_skips_header_and_stops_at_credits(tmp_path, monkeypatch):
    class FakePage:
        def __init__(self, word_rows):
            self._word_rows = word_rows

        def extract_words(self, **kwargs):
            words = []
            for top, texts in enumerate(self._word_rows):
                x = 0
                for text in texts:
                    words.append(_word(text, x, x + len(text) + 2, float(top * 20)))
                    x += len(text) + 5
            return words

    class FakePdf:
        def __init__(self, pages):
            self.pages = pages

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    pages = [FakePage([
        ["TITLE"],
        ["Artist", "Name"],
        ["SIb"],
        ["Anna", "come", "sono"],
        ["CREDITS"],
        ["AUTORE:", "Someone"],
    ])]
    monkeypatch.setattr(pcc.pdfplumber, "open", lambda path: FakePdf(pages))

    lines = pcc.extract_lines(tmp_path / "fake.pdf")
    assert len(lines) == 1
    assert lines[0]["words"] == ["Anna", "come", "sono"]
    assert lines[0]["chords"] == {"0": "SIb"}
