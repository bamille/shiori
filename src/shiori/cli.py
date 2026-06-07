from __future__ import annotations
import argparse
import json
from pathlib import Path

from .ingest import Book

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

    args = parser.parse_args(argv)
    args.func(args)
    return 0