from pathlib import Path

from shiori import Book


SAMPLE = Path("src/shiori/test/test1.epub")


def test_sample_exists():
    assert SAMPLE.exists(), f"Sample EPUB not found at {SAMPLE}"


def test_from_epub_basic():
    book = Book.from_epub(SAMPLE)
    assert book.title and "海辺のカフカ" in book.title
    assert any("村上春樹" in a for a in book.authors)
    assert book.language == "ja"
    assert book.modified is not None
    assert book.chapters and len(book.chapters) > 0
    assert book.metadata.get("chapter_count") == len(book.chapters)
    text = book.extract_text()
    assert isinstance(text, str) and len(text) > 100
    assert "カフカ" in text


def test_to_metadata_structure():
    book = Book.from_epub(SAMPLE)
    md = book.to_metadata()
    assert md["title"] == book.title
    assert md["authors"] == book.authors
    assert "chapters" in md and isinstance(md["chapters"], list)
    if md["chapters"]:
        first = md["chapters"][0]
        assert set(["id", "title", "href", "text"]).issubset(first.keys())
