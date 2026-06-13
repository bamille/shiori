"""Build Anki cards from parsed words and dictionary lookups."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import genanki

from .lookup import YomitanDictionary, load_dictionary
from .parse import Word

logger = logging.getLogger(__name__)

DEFAULT_DICT_PATH = Path(__file__).resolve().parents[2] / "data" / "jitendex-yomitan.zip"
DEFAULT_NOTE_TYPE_PATH = Path(__file__).resolve().parent / "anki_templates" / "note_types" / "Lapis.json"
DEFAULT_MAPPINGS_PATH = Path(__file__).resolve().parent / "anki_templates" / "mappings.json"

MODEL_ID = 8675309
DECK_ID = 2675312


class AnkiCardBuilder:
    """Build Anki cards from Word objects and dictionary lookups.

    Field population is driven by the mappings JSON: each entry maps an Anki
    field name (exact, as exported from Anki) to a Shiori source key such as
    "word.lexeme" or "jitendex.definition". Fields absent from the mapping are
    left empty in the generated note.

    Supported source keys:
        word.lexeme        — surface form from Word.lexeme
        word.original      — lemma from Word.original (falls back to lexeme)
        word.context       — surrounding sentence from Word.context
        jitendex.term      — headword from the dictionary entry
        jitendex.reading   — kana reading from the dictionary entry
        jitendex.definition — extracted definition text
        metadata.source    — the source argument passed to build_card_data / create_card
    """

    def __init__(
        self,
        dictionary_path: str | Path | None = None,
        note_type_path: str | Path | None = None,
        mappings_path: str | Path | None = None,
    ):
        dict_path = Path(dictionary_path or DEFAULT_DICT_PATH)
        if not dict_path.exists():
            raise FileNotFoundError(f"Dictionary not found: {dict_path}")
        self.dictionary = load_dictionary(dict_path)

        self.note_type_path = Path(note_type_path or DEFAULT_NOTE_TYPE_PATH)
        if not self.note_type_path.exists():
            raise FileNotFoundError(f"Note type file not found: {self.note_type_path}")
        with open(self.note_type_path) as f:
            self.note_type_def = json.load(f)

        mappings_file = Path(mappings_path or DEFAULT_MAPPINGS_PATH)
        if not mappings_file.exists():
            raise FileNotFoundError(f"Mappings file not found: {mappings_file}")
        with open(mappings_file) as f:
            self._mappings_def = json.load(f)

        self._field_names: list[str] = self.note_type_def.get("fields", [])
        self.field_mapping: dict[str, str] = self._mappings_def.get("field_mapping", {})

        self._model: genanki.Model | None = None
        self._deck: genanki.Deck | None = None

    @property
    def model(self) -> genanki.Model:
        if self._model is None:
            fields = [{"name": name} for name in self._field_names]
            self._model = genanki.Model(
                MODEL_ID,
                self.note_type_def.get("name", "Unknown Shiori Model"),
                fields=fields,
                templates=self.note_type_def.get("templates", []),
                css=self.note_type_def.get("css", ""),
            )
        return self._model

    @property
    def deck(self) -> genanki.Deck:
        if self._deck is None:
            self._deck = genanki.Deck(DECK_ID, "Shiori Vocabulary")
        return self._deck

    def lookup_word(self, word: Word) -> list[dict[str, Any]]:
        return self.dictionary.lookup(word.lexeme)

    def build_card_data(self, word: Word, source: str = "") -> dict[str, str] | None:
        """Return a source-keyed data dict for a word, or None if not in dictionary.

        Keys are Shiori source keys (e.g. "word.lexeme", "jitendex.reading").
        Pass this dict to create_card, or inspect it directly for the raw values
        before field mapping is applied.
        """
        results = self.lookup_word(word)
        if not results:
            logger.warning("Word '%s' not found in dictionary", word.lexeme)
            return None
        entry = results[0]
        return self.build_card_data_for_entry(word, entry, source)

    def build_card_data_for_entry(
        self, word: Word, entry: dict[str, Any], source: str = ""
    ) -> dict[str, str]:
        """Return a source-keyed data dict built from a specific dictionary entry.

        Used by the TUI when the user selects a specific definition from multiple
        lookup results rather than defaulting to the first one.
        """
        return {
            "word.lexeme": word.lexeme,
            "word.original": word.original or word.lexeme,
            "word.context": word.context or "",
            "jitendex.term": entry.get("term", word.lexeme),
            "jitendex.reading": entry.get("reading", ""),
            "jitendex.definition": self._extract_definition_text(entry.get("definition", "")),
            "metadata.source": source,
        }

    def create_card(self, word: Word, source: str = "") -> genanki.Note | None:
        """Create a single Anki note from a Word object.

        Iterates over the note type's field list and fills each field whose name
        appears in field_mapping; all other fields are left empty.
        """
        card_data = self.build_card_data(word, source)
        if card_data is None:
            return None
        field_values = [
            card_data.get(self.field_mapping.get(name, ""), "")
            for name in self._field_names
        ]
        return genanki.Note(model=self.model, fields=field_values)

    def create_card_for_entry(
        self, word: Word, entry: dict[str, Any], source: str = ""
    ) -> genanki.Note:
        """Create an Anki note from a specific dictionary entry chosen by the user."""
        card_data = self.build_card_data_for_entry(word, entry, source)
        field_values = [
            card_data.get(self.field_mapping.get(name, ""), "")
            for name in self._field_names
        ]
        return genanki.Note(model=self.model, fields=field_values)

    def add_card_to_deck(self, note: genanki.Note) -> None:
        self.deck.add_note(note)

    @staticmethod
    def _extract_definition_text(definition: Any) -> str:
        if not definition:
            return ""
        if isinstance(definition, list) and len(definition) > 0:
            first_def = definition[0]
            if isinstance(first_def, dict):
                glosses = AnkiCardBuilder._extract_glosses(first_def)
                if glosses:
                    return "; ".join(glosses)
        return str(definition)[:500]

    @staticmethod
    def _extract_glosses(definition_dict: dict[str, Any]) -> list[str]:
        glosses = []
        if definition_dict.get("type") != "structured-content":
            return glosses

        def traverse(obj: Any) -> None:
            if isinstance(obj, dict):
                data_content = obj.get("data", {}).get("content")
                if data_content == "glossary":
                    content = obj.get("content")
                    if isinstance(content, dict):
                        if content.get("tag") == "li" and "content" in content:
                            glosses.append(str(content["content"]))
                    elif isinstance(content, list):
                        for item in content:
                            if isinstance(item, dict) and item.get("tag") == "li":
                                if "content" in item:
                                    glosses.append(str(item["content"]))
                            elif isinstance(item, str):
                                glosses.append(item)
                    else:
                        glosses.append(str(content))
                for key in ["content", "children"]:
                    if key in obj:
                        traverse(obj[key])
            elif isinstance(obj, list):
                for item in obj:
                    traverse(item)

        traverse(definition_dict.get("content", {}))
        return glosses


def create_card_from_word(
    word: Word,
    dictionary_path: str | Path | None = None,
    source: str = "",
) -> genanki.Note | None:
    """Convenience function to create a single card from a Word."""
    builder = AnkiCardBuilder(dictionary_path=dictionary_path)
    return builder.create_card(word, source)
