# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

Shiori is a Japanese reading-to-Anki pipeline. It ingests EPUB books, morphologically analyzes Japanese text using MeCab/UniDic via `fugashi`, looks up words in a Yomitan-format dictionary, and produces Anki flashcard decks.

## Commands

```bash
# Run the CLI
uv run shiori <command>

# Run all tests
uv run pytest

# Run a single test file or test
uv run pytest tests/test_parser.py
uv run pytest tests/test_parser.py::ClassName::test_method

# Bootstrap UniDic into data/unidic/ (large download, run once)
uv run python scripts/bootstrap_unidic.py

# Download Jitendex dictionary into data/jitendex-yomitan.zip
uv run python scripts/download_jitendex.py
```

## CLI subcommands

- `shiori info <epub>` — print metadata as JSON
- `shiori list <epub>` — list chapter titles
- `shiori extract <epub> [-o output.txt]` — dump full text
- `shiori dump-note-type [--note-type NAME] [--force]` — export an Anki note type from a running Anki instance (requires AnkiConnect on port 8765)
- `shiori review [epub] [-o cards.apkg] [--known-words path]` — launch the interactive Textual TUI for word review and card creation

## Data dependencies

Both of these must be present before the parser or card builder will work:

| Path | How to get |
|------|------------|
| `data/unidic/` | `uv run python scripts/bootstrap_unidic.py` |
| `data/jitendex-yomitan.zip` | `uv run python scripts/download_jitendex.py` |

Tests that need these files call `pytest.skip()` automatically when they are absent.

The tagger index is disk-cached at `{tempdir}/shiori_cache/` using pickle on first use.

## Architecture

```
ingest.py        EPUB → Book / Chapter (text extraction)
parse.py         Chapter/str → [Word]  (MeCab tokenization + sentence splitting)
lookup.py        str → [dict]          (Yomitan ZIP dictionary lookup)
card_builder.py  Word → genanki.Note   (Anki card assembly)
known_words.py   set[str] persisted to ~/.shiori/known_words.json
tui.py           Textual TUI (BookLoadScreen → ChapterSelectScreen → WordReviewScreen)
ankiconnect.py   AnkiConnect API       (export note types from running Anki)
cli.py           argparse entry points
paths.py         PROJECT_ROOT, SHIORI_UNIDIC_DIR constants
```

### Key design details

**Parser / Tagger**: `get_tagger()` in `parse.py` is `@lru_cache(maxsize=1)`. It is always called with `-r /dev/null -d "<path>"` so that MeCab ignores any system-wide UniDic installation and uses the project-local one. Always reuse the cached tagger; never construct a fresh `Tagger`.

**Sentence splitting**: `Parser._split_sentences()` respects Japanese quote nesting (`「」`, `『』`, `（）`, etc.) — sentence boundaries inside quotes are suppressed. Words inside a quote get the quoted span as their `context` rather than the whole sentence.

**Yomitan dictionary**: `YomitanDictionary` in `lookup.py` lazily builds an in-memory term index (term → list of `(bank_id, entry_idx)` tuples) on first lookup, then caches it to disk. Entries are sorted by Jmdict sequence number so the most common definition comes first.

**Anki note type**: `AnkiCardBuilder` reads a note type JSON exported from Anki (default `src/shiori/anki_templates/note_types/Lapis.json`). Field mapping is done by exact name (`Expression`, `Reading`, `Meaning`, `Sentence`, `Source`). Use `shiori dump-note-type` to export other note types into that same directory.

**Word dataclass**: `Word.original` is the lemma (dictionary form); `Word.lexeme` is the surface form as it appears in the text. `Word.is_eos` marks the last token of its sentence.

**Known words**: `KnownWords` in `known_words.py` stores lemmas (`Word.original`), not surface forms, so all conjugations of a word are covered by a single entry. Stored as a sorted JSON array at `~/.shiori/known_words.json` (overridable via `--known-words`). Saved immediately on each "mark known" action.

**TUI word filtering**: `WordReviewScreen._build_review_entries()` deduplicates by lemma, skips words already in `KnownWords`, and skips any word with no dictionary entry. Lookup tries `Word.original` (lemma) first, then falls back to `Word.lexeme` (surface). Chapter parsing runs in a thread via `asyncio.to_thread` so the UI stays responsive. Cards accumulate in the `AnkiCardBuilder` deck and are written as a single `.apkg` on save.

**TUI review keybindings**: `←`/`→` cycle dictionary definitions, `Enter` adds a card for the current definition, `K` marks word as known, `D` defers (skips without marking), `Q` saves the deck and returns to the chapter list.
