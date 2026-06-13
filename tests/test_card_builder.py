"""Tests for Anki card building functionality."""

from pathlib import Path
import pytest

from shiori.card_builder import AnkiCardBuilder, create_card_from_word
from shiori.parse import Word


JITENDEX_ZIP = Path(__file__).resolve().parents[1] / "data" / "jitendex-yomitan.zip"


@pytest.fixture
def card_builder():
    if not JITENDEX_ZIP.exists():
        pytest.skip(f"Jitendex dictionary not found at {JITENDEX_ZIP}")
    return AnkiCardBuilder(dictionary_path=JITENDEX_ZIP)


def _field(note: object, field_names: list[str], name: str) -> str:
    return note.fields[field_names.index(name)]


class TestAnkiCardBuilder:

    def test_builder_initialization(self, card_builder):
        assert card_builder.dictionary is not None
        assert isinstance(card_builder.field_mapping, dict)
        assert len(card_builder.field_mapping) > 0

    def test_model_creation(self, card_builder):
        model = card_builder.model
        assert model is not None
        field_names = [f["name"] for f in model.fields]
        assert "Expression" in field_names
        assert "MainDefinition" in field_names
        assert "Sentence" in field_names

    def test_deck_creation(self, card_builder):
        deck = card_builder.deck
        assert deck is not None
        assert deck.name == "Shiori Vocabulary"

    def test_lookup_word(self, card_builder):
        word = Word(lexeme="日本", original="にほん", context="日本は素晴らしいです")
        results = card_builder.lookup_word(word)
        assert len(results) > 0
        assert results[0]["term"] == "日本"

    def test_build_card_data(self, card_builder):
        word = Word(lexeme="水", original="みず", context="水は大切です。")
        card_data = card_builder.build_card_data(word, source="Test Book")
        assert card_data is not None
        assert card_data["word.lexeme"] == "水"
        assert card_data["jitendex.reading"] == "みず"
        assert card_data["word.context"] == "水は大切です。"
        assert card_data["metadata.source"] == "Test Book"
        assert len(card_data["jitendex.definition"]) > 0

    def test_build_card_data_not_found(self, card_builder):
        word = Word(lexeme="ぐじゃぐじゃぐじゃ", original=None, context="Not a real word")
        card_data = card_builder.build_card_data(word)
        assert card_data is None

    def test_create_card(self, card_builder):
        word = Word(lexeme="火", original="ひ", context="火は熱いです。")
        note = card_builder.create_card(word, source="Example")
        assert note is not None
        assert len(note.fields) == len(card_builder._field_names)
        field_names = card_builder._field_names
        assert _field(note, field_names, "Expression") == "火"
        assert len(_field(note, field_names, "MainDefinition")) > 0
        assert _field(note, field_names, "Sentence") == "火は熱いです。"
        assert _field(note, field_names, "MiscInfo") == "Example"

    def test_create_card_not_found(self, card_builder):
        word = Word(lexeme="ぐじゃぐじゃぐじゃ", original=None, context="Not a real word")
        note = card_builder.create_card(word)
        assert note is None

    def test_add_card_to_deck(self, card_builder):
        word = Word(lexeme="木", original="き", context="木は自然です。")
        note = card_builder.create_card(word)
        assert note is not None
        initial_count = len(card_builder.deck.notes)
        card_builder.add_card_to_deck(note)
        assert len(card_builder.deck.notes) == initial_count + 1

    def test_extract_definition_text(self):
        text = AnkiCardBuilder._extract_definition_text(None)
        assert text == ""
        text = AnkiCardBuilder._extract_definition_text(["test definition"])
        assert isinstance(text, str)

    def test_convenience_function(self):
        if not JITENDEX_ZIP.exists():
            pytest.skip(f"Jitendex dictionary not found at {JITENDEX_ZIP}")
        word = Word(lexeme="石", original="いし", context="石は硬いです。")
        note = create_card_from_word(word, dictionary_path=JITENDEX_ZIP)
        assert note is not None
        field_names = AnkiCardBuilder(dictionary_path=JITENDEX_ZIP)._field_names
        assert _field(note, field_names, "Expression") == "石"

    def test_multiple_cards_different_words(self, card_builder):
        words = [
            Word(lexeme="水", original="みず", context="水を飲みます。"),
            Word(lexeme="火", original="ひ", context="火をつけます。"),
            Word(lexeme="木", original="き", context="木に登ります。"),
        ]
        field_names = card_builder._field_names
        cards = [card_builder.create_card(w) for w in words]
        assert all(c is not None for c in cards)
        expressions = [_field(c, field_names, "Expression") for c in cards]
        assert expressions == ["水", "火", "木"]

    def test_full_workflow(self, card_builder):
        word = Word(lexeme="太陽", original="たいよう", context="太陽が明るいです。")
        note = card_builder.create_card(word, source="天文学テキスト")
        assert note is not None
        initial_deck_size = len(card_builder.deck.notes)
        card_builder.add_card_to_deck(note)
        assert len(card_builder.deck.notes) == initial_deck_size + 1
        field_names = card_builder._field_names
        assert _field(card_builder.deck.notes[-1], field_names, "Expression") == "太陽"

    def test_field_mapping_drives_note_fields(self, card_builder):
        """Unmapped fields are empty; mapped fields carry the expected values."""
        word = Word(lexeme="空", original="そら", context="空が青い。")
        note = card_builder.create_card(word, source="詩集")
        assert note is not None
        field_names = card_builder._field_names
        # Fields not in field_mapping should be empty
        for anki_field, source_key in card_builder.field_mapping.items():
            idx = field_names.index(anki_field)
            assert note.fields[idx] != "" or source_key == "metadata.source"
        # Spot-check an unmapped field
        unmapped = [n for n in field_names if n not in card_builder.field_mapping]
        for name in unmapped:
            assert _field(note, field_names, name) == ""

    def test_custom_field_mapping(self, tmp_path):
        """A custom mappings file with different field assignments is respected."""
        if not JITENDEX_ZIP.exists():
            pytest.skip(f"Jitendex dictionary not found at {JITENDEX_ZIP}")

        custom_mappings = tmp_path / "mappings.json"
        custom_mappings.write_text(
            '{"field_mapping": {"Expression": "word.context", "Sentence": "word.lexeme"}}',
            encoding="utf-8",
        )
        builder = AnkiCardBuilder(
            dictionary_path=JITENDEX_ZIP,
            mappings_path=custom_mappings,
        )
        word = Word(lexeme="花", original="はな", context="花が咲く。")
        note = builder.create_card(word)
        assert note is not None
        field_names = builder._field_names
        assert _field(note, field_names, "Expression") == "花が咲く。"
        assert _field(note, field_names, "Sentence") == "花"
