from __future__ import annotations
import argparse
import json
from pathlib import Path

from .ankiconnect import cmd_export_note_type
from .ingest import Book
from .paths import PROJECT_ROOT


def cmd_review(args: argparse.Namespace) -> int:
    from .card_builder import AnkiCardBuilder
    from .known_words import KnownWords
    from .tui import ReviewApp

    known_words_path = Path(args.known_words).expanduser() if args.known_words else None
    known_words = KnownWords(known_words_path)

    try:
        card_builder = AnkiCardBuilder()
    except FileNotFoundError as exc:
        print(f"Error: {exc}")
        print("Run 'uv run python scripts/download_jitendex.py' to download the dictionary.")
        return 1

    epub_path = Path(args.epub).expanduser() if args.epub else None
    output_path = Path(args.output).expanduser()

    app = ReviewApp(
        output_path=output_path,
        known_words=known_words,
        card_builder=card_builder,
        epub_path=epub_path,
    )
    app.run()
    return 0

def _load_book(path: str) -> Book:
    p = Path(path)
    return Book.from_epub(p)

def cmd_info(args: argparse.Namespace) -> None:
    book = _load_book(args.epub)
    print(json.dumps(book.to_metadata(), ensure_ascii=False, indent=2))

def cmd_list(args: argparse.Namespace) -> None:
    book = _load_book(args.epub)
    for i, title in enumerate(book.chapter_titles, 1):
        print(f"{i:3d}  {title}")

def cmd_extract(args: argparse.Namespace) -> None:
    book = _load_book(args.epub)
    text = book.extract_text()
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text)

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="shiori")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("info", help="Print metadata as JSON")
    p.add_argument("epub", help="Path to EPUB file")
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("list", help="List chapter titles")
    p.add_argument("epub", help="Path to EPUB file")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("extract", help="Extract full text")
    p.add_argument("epub", help="Path to EPUB file")
    p.add_argument("-o", "--output", help="Write text to file (stdout if omitted)")
    p.set_defaults(func=cmd_extract)

    p = sub.add_parser(
        "dump-note-type",
        help="Export a note type from a running Anki instance to note_types JSON",
    )
    p.add_argument("--host", default="127.0.0.1", help="AnkiConnect host")
    p.add_argument("--port", type=int, default=8765, help="AnkiConnect port")
    p.add_argument("--note-type", help="Note type name or numeric index from list")
    p.add_argument(
        "--output-dir",
        default=str(PROJECT_ROOT / "src" / "shiori" / "anki_templates" / "note_types"),
        help="Directory to write note type JSON into",
    )
    p.add_argument("--force", action="store_true", help="Overwrite existing file if it exists")
    p.set_defaults(func=cmd_export_note_type)

    p = sub.add_parser("review", help="Interactive word review and Anki card creation")
    p.add_argument("epub", nargs="?", help="Path to EPUB file (optional, can be entered in the app)")
    p.add_argument("-o", "--output", default="shiori_cards.apkg", help="Output .apkg file (default: shiori_cards.apkg)")
    p.add_argument("--known-words", help="Path to known words JSON (default: ~/.shiori/known_words.json)")
    p.set_defaults(func=cmd_review)

    args = parser.parse_args(argv)
    return args.func(args) or 0