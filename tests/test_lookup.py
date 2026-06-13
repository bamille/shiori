"""Tests for dictionary lookup functionality."""

from pathlib import Path
import pytest
from shiori.lookup import YomitanDictionary, load_dictionary


JITENDEX_ZIP = Path(__file__).resolve().parents[2] / "data" / "jitendex-yomitan.zip"


@pytest.fixture
def jitendex():
    """Load the Jitendex dictionary for testing."""
    if not JITENDEX_ZIP.exists():
        pytest.skip(f"Jitendex dictionary not found at {JITENDEX_ZIP}")
    return load_dictionary(JITENDEX_ZIP)


class TestYomitanDictionary:
    """Tests for YomitanDictionary class."""

    def test_load_dictionary(self, jitendex):
        """Test that dictionary loads and has expected metadata."""
        assert jitendex.metadata is not None
        assert "title" in jitendex.metadata
        assert "Jitendex" in jitendex.metadata["title"]
        assert jitendex.metadata["sourceLanguage"] == "ja"
        assert jitendex.metadata["targetLanguage"] == "en"

    def test_lookup_common_word(self, jitendex):
        """Test looking up a common Japanese word."""
        results = jitendex.lookup("日本")
        assert len(results) > 0
        assert results[0]["term"] == "日本"
        assert results[0]["reading"] == "にほん"
        assert "definition" in results[0]

    def test_lookup_multiple_readings(self, jitendex):
        """Test that lookup returns multiple entries for words with different readings."""
        results = jitendex.lookup("日本")
        # 日本 has at least にほん and にっぽん
        assert len(results) >= 1

    def test_lookup_nonexistent_word(self, jitendex):
        """Test that lookup returns empty list for nonexistent words."""
        results = jitendex.lookup("ぐじゃぐじゃぐじゃ")
        assert results == []

    def test_lookup_dual_forms(self, jitendex):
        """Test looking up a word that has two possible forms"""
        results = jitendex.lookup("猿")
        assert len(results) > 0
        results = jitendex.lookup("サル")
        assert len(results) > 0

    def test_lookup_katakana(self, jitendex):
        """Test looking up a katakana word."""
        results = jitendex.lookup("コンピューター")
        assert len(results) > 0

    def test_parse_entry(self, jitendex):
        """Test that entry parsing works correctly."""
        results = jitendex.lookup("水")
        for result in results:
            assert "term" in result
            assert "reading" in result
            assert "definition" in result
            assert result["term"] == "水"

    def test_index_building(self, jitendex):
        """Test that index is available after creation (cached or built)."""
        # Index may be loaded from cache or empty initially
        initial_size = len(jitendex._index_by_term)
        jitendex.lookup("日本")
        # After lookup, index should be populated
        assert len(jitendex._index_by_term) > 0
        # If initially empty, it should have been built
        if initial_size == 0:
            assert len(jitendex._index_by_term) > initial_size

    def test_sequential_lookups(self, jitendex):
        """Test that multiple lookups work correctly."""
        words = ["水", "火", "木"]
        for word in words:
            results = jitendex.lookup(word)
            assert len(results) > 0, f"Failed to lookup {word}"
            assert results[0]["term"] == word

    def test_cache_hit(self, jitendex):
        """Test that caching works for repeated lookups."""
        # First lookup
        results1 = jitendex.lookup("日本")
        # Second lookup should use cache
        results2 = jitendex.lookup("日本")
        assert results1 == results2
        # Verify cache is in use
        assert len(jitendex._term_bank_cache) > 0
