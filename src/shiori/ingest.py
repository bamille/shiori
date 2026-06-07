from __future__ import annotations

from dataclasses import dataclass, field
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
import re
from typing import Any

from ebooklib import ITEM_DOCUMENT, epub


@dataclass(slots=True)
class Chapter:
	"""A lightweight container for a single chapter's extracted data.

	Attributes:
		id: The EPUB internal id for the chapter item when available.
		title: The human-readable title (from <title> or <h1>-<h3> where found).
		href: The item filename/href within the EPUB package.
		text: The chapter body text normalized to plain text.
	"""
	id: str | None
	title: str | None
	href: str | None
	text: str


class _HTMLTextExtractor(HTMLParser):
	"""HTML-to-text extractor used to pull visible text from XHTML.

	This minimal parser preserves paragraph and heading breaks by inserting
	newline markers for a small set of structural tags, and accumulates
	raw data chunks which are joined and HTML-unescaped when requested.
	"""
	def __init__(self) -> None:
		super().__init__()
		self._parts: list[str] = []

	def handle_data(self, data: str) -> None:
		"""Append text node content to the accumulator."""
		if data:
			self._parts.append(data)

	def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
		"""Insert a newline for certain block-level or break tags."""
		if tag in {"br", "p", "div", "li", "section", "article", "header", "footer", "h1", "h2", "h3", "h4", "h5", "h6"}:
			self._parts.append("\n")

	def handle_endtag(self, tag: str) -> None:
		"""Also insert newlines when these tags close to separate blocks."""
		if tag in {"p", "div", "li", "section", "article", "header", "footer", "h1", "h2", "h3", "h4", "h5", "h6"}:
			self._parts.append("\n")

	def text(self) -> str:
		"""Return the accumulated text with HTML entities unescaped."""
		return unescape("".join(self._parts))


@dataclass(slots=True)
class Book:
	"""Representation of an EPUB book with extracted text and metadata.

	Use :meth:`from_epub` to load a book from a filesystem path. The
	`Book` holds basic Dublin Core metadata (title, authors, language,
	publication/modified dates) as well as a list of extracted `Chapter`
	objects and a `metadata` dict with additional fields.

	Attributes:
		source_path: Original file path used to load the EPUB.
		title: Primary title (if present in metadata or content).
		authors: Sequence of creators found in the EPUB metadata.
		published: DC date value if present.
		modified: OPF modified timestamp when available.
		language: Primary language code (e.g. 'en', 'ja').
		chapters: Ordered list of extracted `Chapter` instances.
		metadata: Additional metadata values mapped by key.
	"""
	source_path: Path
	title: str | None
	authors: list[str] = field(default_factory=list)
	published: str | None = None
	modified: str | None = None
	language: str | None = None
	chapters: list[Chapter] = field(default_factory=list)
	metadata: dict[str, Any] = field(default_factory=dict)

	@classmethod
	def from_epub(cls, source: str | Path) -> Book:
		"""Load an EPUB file from `source` and return a `Book`.

		`source` may be a string path or a `Path` object. This is a
		convenience wrapper around :meth:`from_epub_book` which accepts an
		`ebooklib.epub.EpubBook` instance.
		"""
		source_path = Path(source)
		epub_book = epub.read_epub(str(source_path))
		return cls.from_epub_book(source_path, epub_book)

	@classmethod
	def from_epub_book(cls, source_path: Path, epub_book: epub.EpubBook) -> Book:
		"""Create a `Book` from an already-parsed `ebooklib` book object.

		This method centralizes metadata normalization and chapter
		extraction. It is useful when the caller already holds an
		`ebooklib.epub.EpubBook` instance (for example, when doing custom
		preprocessing before extraction).
		"""
		title = cls._first_metadata_value(epub_book, "DC", "title")
		authors = cls._metadata_values(epub_book, "DC", "creator")
		language = cls._first_metadata_value(epub_book, "DC", "language")
		published = cls._first_metadata_value(epub_book, "DC", "date")
		modified = cls._first_metadata_value(epub_book, "OPF", "meta", key="property", value="dcterms:modified")
		chapters = cls._extract_chapters(epub_book)

		metadata = {
			"title": title,
			"authors": authors,
			"language": language,
			"published": published,
			"modified": modified,
			"publisher": cls._metadata_values(epub_book, "DC", "publisher"),
			"description": cls._metadata_values(epub_book, "DC", "description"),
			"subjects": cls._metadata_values(epub_book, "DC", "subject"),
			"identifiers": cls._metadata_values(epub_book, "DC", "identifier"),
			"chapter_count": len(chapters),
		}

		return cls(
			source_path=source_path,
			title=title,
			authors=authors,
			published=published,
			modified=modified,
			language=language,
			chapters=chapters,
			metadata=metadata,
		)

	@property
	def chapter_titles(self) -> list[str]:
		"""Return a list of non-empty chapter titles in order."""
		return [chapter.title for chapter in self.chapters if chapter.title]

	def extract_text(self) -> str:
		"""Return the full book text as a single string.

		Chapters are joined with a blank line. Each chapter's text is
		stripped of leading/trailing whitespace before joining.
		"""
		return "\n\n".join(chapter.text.strip() for chapter in self.chapters if chapter.text.strip())

	def to_metadata(self) -> dict[str, Any]:
		"""Return a JSON-serializable metadata representation of the book.

		Includes top-level metadata fields and a list of chapter dicts.
		"""
		return {
			"source_path": str(self.source_path),
			"title": self.title,
			"authors": self.authors,
			"published": self.published,
			"modified": self.modified,
			"language": self.language,
			"chapters": [
				{
					"id": chapter.id,
					"title": chapter.title,
					"href": chapter.href,
					"text": chapter.text,
				}
				for chapter in self.chapters
			],
			"metadata": self.metadata,
		}

	@staticmethod
	def _metadata_values(epub_book: epub.EpubBook, namespace: str, name: str) -> list[str]:
		"""Return all metadata values for a given namespace and name.

		This wraps `ebooklib`'s `get_metadata` and coerces results to
		strings. Useful for fields that may be repeated (creators,
		subjects, identifiers, etc.).
		"""
		values: list[str] = []
		for value, _attrs in epub_book.get_metadata(namespace, name):
			if value:
				values.append(str(value))
		return values

	@staticmethod
	def _first_metadata_value(
		epub_book: epub.EpubBook,
		namespace: str,
		name: str,
		*,
		key: str | None = None,
		value: str | None = None,
	) -> str | None:
		"""Return the first metadata value matching optional attribute filters.

		When `key` and `value` are provided, the metadata attribute dict
		is consulted (this is used to find OPF meta elements such as the
		`dcterms:modified` timestamp).
		"""
		for candidate, attrs in epub_book.get_metadata(namespace, name):
			if key is not None and attrs.get(key) != value:
				continue
			if candidate:
				return str(candidate)
		return None

	@classmethod
	def _extract_chapters(cls, epub_book: epub.EpubBook) -> list[Chapter]:
		"""Extract chapter-like document items from the EPUB spine.

		The algorithm walks the spine in order and selects items that are
		documents (XHTML). As a fallback it will return any document items
		found in the package when the spine-based walk produces nothing.
		"""
		chapters: list[Chapter] = []
		seen_ids: set[str] = set()

		for spine_entry in epub_book.spine:
			item_id = spine_entry[0] if isinstance(spine_entry, tuple) else spine_entry
			if not item_id or item_id in {"nav", "ncx"}:
				continue

			item = epub_book.get_item_with_id(item_id)
			if item is None or item_id in seen_ids:
				continue

			if getattr(item, "media_type", None) != "application/xhtml+xml" and item.get_type() != ITEM_DOCUMENT:
				continue

			seen_ids.add(item_id)
			chapters.append(cls._chapter_from_item(item))

		if not chapters:
			for item in epub_book.get_items_of_type(ITEM_DOCUMENT):
				item_id = getattr(item, "id", None)
				if item_id and item_id in seen_ids:
					continue
				chapters.append(cls._chapter_from_item(item))

		return chapters

	@staticmethod
	def _chapter_from_item(item: Any) -> Chapter:
		"""Build a Chapter instance from an EPUB item.

		The method extracts raw XHTML, derives a reasonable title (title
		element, header tags, or filename) and converts the body to plain
		text.
		"""
		html_text = Book._item_html(item)
		title = Book._extract_title(html_text) or getattr(item, "title", None) or getattr(item, "file_name", None)
		text = Book._html_to_text(html_text)
		return Chapter(
			id=getattr(item, "id", None),
			title=title,
			href=getattr(item, "file_name", None),
			text=text,
		)

	@staticmethod
	def _item_html(item: Any) -> str:
		"""Return the item's content decoded to a text string.

		This handles byte content and falls back to str() otherwise.
		"""
		content = item.get_content()
		if isinstance(content, bytes):
			return content.decode("utf-8", errors="ignore")
		return str(content)

	@staticmethod
	def _extract_title(html_text: str) -> str | None:
		"""Try to find a title string inside common title or heading tags.

		Searches `<title>`, then `<h1>`, `<h2>`, `<h3>` and strips any inner
		tags. Returns None if no candidate is found.
		"""
		for pattern in (r"<title[^>]*>(.*?)</title>", r"<h1[^>]*>(.*?)</h1>", r"<h2[^>]*>(.*?)</h2>", r"<h3[^>]*>(.*?)</h3>"):
			match = re.search(pattern, html_text, flags=re.IGNORECASE | re.DOTALL)
			if match:
				title = re.sub(r"<[^>]+>", "", match.group(1)).strip()
				if title:
					return unescape(title)
		return None

	@staticmethod
	def _html_to_text(html_text: str) -> str:
		"""Coerce XHTML into normalized plain text using the extractor.

		The returned text is stripped line-by-line and blank lines are
		removed to produce a compact representation suitable for search
		or storage.
		"""
		parser = _HTMLTextExtractor()
		parser.feed(html_text)
		lines = [line.strip() for line in parser.text().splitlines()]
		return "\n".join(line for line in lines if line)


