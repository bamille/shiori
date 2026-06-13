"""Textual TUI for interactive word review and Anki card creation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import genanki
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Center, Horizontal, Vertical
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    LoadingIndicator,
    Static,
)
from textual import work

from .card_builder import AnkiCardBuilder
from .ingest import Book, Chapter
from .known_words import KnownWords
from .parse import Parser, Word


@dataclass
class _ReviewEntry:
    word: Word
    entries: list[dict[str, Any]]
    entry_texts: list[str]


# ---------------------------------------------------------------------------
# Book load screen
# ---------------------------------------------------------------------------

class BookLoadScreen(Screen):
    BINDINGS = [Binding("escape", "app.quit", "Quit")]

    CSS = """
    BookLoadScreen {
        align: center middle;
    }
    #load-form {
        width: 72;
        padding: 2 4;
        border: round $primary;
    }
    #app-title {
        text-align: center;
        text-style: bold;
        padding-bottom: 1;
        color: $primary;
    }
    #app-subtitle {
        text-align: center;
        color: $text-muted;
        padding-bottom: 2;
    }
    #load-btn {
        margin-top: 1;
        width: 100%;
    }
    #load-error {
        color: $error;
        margin-top: 1;
    }
    .hidden {
        display: none;
    }
    """

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Center():
            with Vertical(id="load-form"):
                yield Static("栞  Shiori", id="app-title")
                yield Static("Japanese Reading → Anki", id="app-subtitle")
                yield Input(placeholder="Path to EPUB file…", id="epub-input")
                yield Button("Load Book", variant="primary", id="load-btn")
                yield Static("", id="load-error", classes="hidden")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#epub-input", Input).focus()

    def on_input_submitted(self, _event: Input.Submitted) -> None:
        self._try_load()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "load-btn":
            self._try_load()

    def _try_load(self) -> None:
        path_str = self.query_one("#epub-input", Input).value.strip()
        error = self.query_one("#load-error", Static)
        if not path_str:
            error.update("Please enter a path to an EPUB file.")
            error.remove_class("hidden")
            return
        path = Path(path_str).expanduser()
        if not path.exists():
            error.update(f"File not found: {path}")
            error.remove_class("hidden")
            return
        error.add_class("hidden")
        try:
            book = Book.from_epub(path)
        except Exception as exc:  # noqa: BLE001
            error.update(f"Error loading EPUB: {exc}")
            error.remove_class("hidden")
            return
        self.app.push_screen(ChapterSelectScreen(book))


# ---------------------------------------------------------------------------
# Chapter select screen
# ---------------------------------------------------------------------------

class ChapterSelectScreen(Screen):
    BINDINGS = [Binding("escape", "app.pop_screen", "Back")]

    CSS = """
    #chapter-header {
        padding: 1 2;
        color: $text-muted;
        border-bottom: solid $primary;
    }
    ListView {
        height: 1fr;
    }
    .hidden {
        display: none;
    }
    """

    def __init__(self, book: Book) -> None:
        super().__init__()
        self._book = book
        # Keep a stable mapping from list position → chapter index
        self._chapter_indices = [
            i for i, ch in enumerate(book.chapters) if ch.text.strip()
        ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        title = self._book.title or "Unknown Book"
        with Vertical():
            yield Static(f"[bold]{title}[/bold] — select a chapter", id="chapter-header")
            items = [
                ListItem(Label(f"  {i + 1:3d}.  {self._book.chapters[ci].title or '(untitled)'}"))
                for i, ci in enumerate(self._chapter_indices)
            ]
            yield ListView(*items, id="chapter-list")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#chapter-list", ListView).focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        lv = self.query_one("#chapter-list", ListView)
        list_idx = lv.index
        if list_idx is None:
            return
        chapter_idx = self._chapter_indices[list_idx]
        chapter = self._book.chapters[chapter_idx]
        app = self.app
        assert isinstance(app, ReviewApp)
        app.push_screen(
            WordReviewScreen(
                book=self._book,
                chapter=chapter,
                known_words=app.known_words,
                card_builder=app.card_builder,
                output_path=app.output_path,
            )
        )


# ---------------------------------------------------------------------------
# Word review screen
# ---------------------------------------------------------------------------

class WordReviewScreen(Screen):
    BINDINGS = [
        Binding("left", "prev_def", "← Prev Def"),
        Binding("right", "next_def", "→ Next Def"),
        Binding("enter", "add_card", "Add Card"),
        Binding("k", "mark_known", "Mark Known"),
        Binding("d", "defer_word", "Defer"),
        Binding("q", "finish", "Finish"),
    ]

    CSS = """
    #review-wrapper {
        height: 1fr;
        padding: 1 2;
    }
    #loading {
        align: center middle;
        height: 1fr;
    }
    #review {
        height: 1fr;
    }
    .hidden {
        display: none;
    }
    #word-row {
        height: auto;
        padding-bottom: 1;
    }
    #word-display {
        text-style: bold;
        padding-right: 2;
    }
    #reading-display {
        color: $text-muted;
        padding-top: 1;
    }
    #context-display {
        background: $surface-darken-1;
        border: round $primary-darken-3;
        padding: 1 2;
        margin-bottom: 1;
        height: auto;
    }
    #def-panel {
        border: round $secondary;
        padding: 1 2;
        height: auto;
        margin-bottom: 1;
    }
    #def-counter {
        color: $text-muted;
        padding-bottom: 1;
    }
    #def-text {
        height: auto;
    }
    #status-bar {
        color: $text-muted;
        text-align: right;
        padding-top: 1;
    }
    #done {
        align: center middle;
        height: 1fr;
    }
    #done-message {
        text-align: center;
        padding-bottom: 2;
        text-style: bold;
    }
    #done-buttons {
        height: auto;
        width: 50;
    }
    #save-btn {
        width: 100%;
        margin-bottom: 1;
    }
    #back-btn {
        width: 100%;
    }
    """

    _word_idx: reactive[int] = reactive(0)
    _def_idx: reactive[int] = reactive(0)

    def __init__(
        self,
        book: Book,
        chapter: Chapter,
        known_words: KnownWords,
        card_builder: AnkiCardBuilder,
        output_path: Path,
    ) -> None:
        super().__init__()
        self._book = book
        self._chapter = chapter
        self._known_words = known_words
        self._card_builder = card_builder
        self._output_path = output_path
        self._review_entries: list[_ReviewEntry] = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Vertical(id="review-wrapper"):
            yield LoadingIndicator(id="loading")
            with Vertical(id="review", classes="hidden"):
                with Horizontal(id="word-row"):
                    yield Static("", id="word-display")
                    yield Static("", id="reading-display")
                yield Static("", id="context-display")
                with Vertical(id="def-panel"):
                    yield Static("", id="def-counter")
                    yield Static("", id="def-text")
                yield Static("", id="status-bar")
            with Center(id="done", classes="hidden"):
                with Vertical(id="done-buttons"):
                    yield Static("", id="done-message")
                    yield Button("Save Deck (.apkg)", variant="primary", id="save-btn")
                    yield Button("Back to Chapters", id="back-btn")
        yield Footer()

    def on_mount(self) -> None:
        chapter_title = self._chapter.title or "chapter"
        book_title = self._book.title or "book"
        self.sub_title = f"{book_title} — {chapter_title}"
        self._start_parsing()

    @work
    async def _start_parsing(self) -> None:
        import asyncio
        entries = await asyncio.to_thread(self._parse_in_thread)
        self._on_parsed(entries)

    def _parse_in_thread(self) -> list[_ReviewEntry]:
        parser = Parser()
        words = parser.tokenize(self._chapter)
        return self._build_review_entries(words)

    def _build_review_entries(self, words: list[Word]) -> list[_ReviewEntry]:
        seen: set[str] = set()
        result: list[_ReviewEntry] = []
        for word in words:
            key = word.original or word.lexeme
            if key in self._known_words or key in seen:
                continue
            seen.add(key)
            # Try lemma first, fall back to surface form
            dict_entries = self._card_builder.dictionary.lookup(key)
            if not dict_entries and key != word.lexeme:
                dict_entries = self._card_builder.dictionary.lookup(word.lexeme)
            if not dict_entries:
                continue
            entry_texts = [
                AnkiCardBuilder._extract_definition_text(e.get("definition", ""))
                for e in dict_entries
            ]
            result.append(_ReviewEntry(word=word, entries=dict_entries, entry_texts=entry_texts))
        return result

    def _on_parsed(self, entries: list[_ReviewEntry]) -> None:
        self._review_entries = entries
        self.query_one("#loading").remove()
        if not entries:
            self._show_done(cards_added=0)
            return
        self.query_one("#review").remove_class("hidden")
        self._update_display()

    def _update_display(self) -> None:
        if self._word_idx >= len(self._review_entries):
            self._show_done(cards_added=len(self._card_builder.deck.notes))
            return

        entry = self._review_entries[self._word_idx]
        word = entry.word
        def_idx = min(self._def_idx, len(entry.entries) - 1)

        self.query_one("#word-display", Static).update(f"[bold]{word.lexeme}[/bold]")

        reading = entry.entries[def_idx].get("reading", "") if entry.entries else ""
        if reading and reading != word.lexeme:
            self.query_one("#reading-display", Static).update(f"[dim]({reading})[/dim]")
        else:
            self.query_one("#reading-display", Static).update("")

        ctx = word.context or word.lexeme
        highlighted = ctx.replace(word.lexeme, f"[underline]{word.lexeme}[/underline]", 1)
        self.query_one("#context-display", Static).update(highlighted)

        total = len(entry.entries)
        self.query_one("#def-counter", Static).update(
            f"Definition [{def_idx + 1} / {total}]"
        )
        def_text = entry.entry_texts[def_idx] if entry.entry_texts else "(no definition text)"
        self.query_one("#def-text", Static).update(def_text)

        remaining = len(self._review_entries) - self._word_idx
        self.query_one("#status-bar", Static).update(f"{remaining} unknown word(s) remaining")

    def _show_done(self, cards_added: int) -> None:
        for node_id in ("#review",):
            try:
                self.query_one(node_id).add_class("hidden")
            except Exception:  # noqa: BLE001
                pass
        if not self._review_entries:
            msg = "No unknown words found in this chapter."
        else:
            msg = f"Chapter complete! {cards_added} card(s) created."
        self.query_one("#done-message", Static).update(msg)
        self.query_one("#done").remove_class("hidden")

    def _advance(self) -> None:
        self._def_idx = 0
        self._word_idx += 1
        self._update_display()

    # -- Actions ----------------------------------------------------------------

    def action_prev_def(self) -> None:
        if self._word_idx >= len(self._review_entries):
            return
        entry = self._review_entries[self._word_idx]
        self._def_idx = (self._def_idx - 1) % len(entry.entries)
        self._update_display()

    def action_next_def(self) -> None:
        if self._word_idx >= len(self._review_entries):
            return
        entry = self._review_entries[self._word_idx]
        self._def_idx = (self._def_idx + 1) % len(entry.entries)
        self._update_display()

    def action_add_card(self) -> None:
        if self._word_idx >= len(self._review_entries):
            return
        entry = self._review_entries[self._word_idx]
        word = entry.word
        def_idx = min(self._def_idx, len(entry.entries) - 1)
        dict_entry = entry.entries[def_idx]
        source = f"{self._book.title or ''} / {self._chapter.title or ''}"
        note = self._card_builder.create_card_for_entry(word, dict_entry, source=source)
        self._card_builder.add_card_to_deck(note)
        self._advance()

    def action_mark_known(self) -> None:
        if self._word_idx >= len(self._review_entries):
            return
        word = self._review_entries[self._word_idx].word
        self._known_words.add(word.original or word.lexeme)
        self._known_words.save()
        self._advance()

    def action_defer_word(self) -> None:
        self._advance()

    def action_finish(self) -> None:
        self._save_deck()
        self.app.pop_screen()

    # -- Buttons ----------------------------------------------------------------

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-btn":
            self._save_deck()
            self.query_one("#done-message", Static).update(
                f"Saved to [bold]{self._output_path}[/bold]"
            )
            self.query_one("#save-btn").disabled = True
        elif event.button.id == "back-btn":
            self._save_deck()
            self.app.pop_screen()

    def _save_deck(self) -> None:
        notes = self._card_builder.deck.notes
        if not notes:
            return
        package = genanki.Package(self._card_builder.deck)
        self._output_path.parent.mkdir(parents=True, exist_ok=True)
        package.write_to_file(str(self._output_path))


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

class ReviewApp(App):
    TITLE = "Shiori"

    def __init__(
        self,
        output_path: Path,
        known_words: KnownWords,
        card_builder: AnkiCardBuilder,
        epub_path: Path | None = None,
    ) -> None:
        super().__init__()
        self.output_path = output_path
        self.known_words = known_words
        self.card_builder = card_builder
        self._epub_path = epub_path

    def on_mount(self) -> None:
        if self._epub_path is not None:
            try:
                book = Book.from_epub(self._epub_path)
                self.push_screen(ChapterSelectScreen(book))
                return
            except Exception:  # noqa: BLE001
                pass
        self.push_screen(BookLoadScreen())
