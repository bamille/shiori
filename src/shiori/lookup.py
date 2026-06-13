"""Dictionary lookup using Yomitan-format dictionaries."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
from zipfile import ZipFile
import hashlib
import pickle

logger = logging.getLogger(__name__)

class YomitanDictionary:
    """Load and lookup words in a Yomitan-format ZIP dictionary.

    Yomitan dictionaries are ZIP files containing:
    - index.json: metadata
    - term_bank_N.json: term definitions (split across multiple files for size)
    - tag_bank_N.json: tag metadata

    This class lazily loads term banks as needed for efficient memory usage.
    """

    def __init__(self, zip_path: str | Path):
        """Initialize a Yomitan dictionary from a ZIP file.

        Args:
            zip_path: Path to the .zip file.

        Raises:
            FileNotFoundError: If the ZIP file does not exist.
            ValueError: If the ZIP file is missing required index.json.
        """
        self.zip_path = Path(zip_path)
        if not self.zip_path.exists():
            raise FileNotFoundError(f"Dictionary ZIP file not found: {self.zip_path}")

        with ZipFile(self.zip_path, "r") as zf:
            # Load index metadata
            try:
                index_data = zf.read("index.json").decode("utf-8")
                self.metadata = json.loads(index_data)
            except KeyError:
                raise ValueError("ZIP file is missing index.json") from None

        self._term_bank_cache: dict[int, list[list[Any]]] = {}
        self._tag_bank_cache: dict[int, list[list[Any]]] = {}
        self._index_by_term: dict[str, list[int]] = {}  # term -> list of (bank_id, entry_idx)
        
        # Try to load cached index first
        self._cache_path = self._get_cache_path()
        if not self._try_load_cache():
            logger.debug("No valid cache found, will build index on first lookup")

    def _get_cache_path(self) -> Path:
        """Get the cache file path for this dictionary.
        
        Cache is stored in the system temp directory with a hash of the ZIP path
        to allow multiple dictionaries to be cached.
        """
        import tempfile
        zip_hash = hashlib.sha256(str(self.zip_path.resolve()).encode()).hexdigest()[:8]
        cache_dir = Path(tempfile.gettempdir()) / "shiori_cache"
        cache_dir.mkdir(exist_ok=True)
        return cache_dir / f"index_{self.zip_path.stem}_{zip_hash}.pkl"
    
    def _try_load_cache(self) -> bool:
        """Try to load the index from cache.
        
        Returns:
            True if cache was loaded successfully, False otherwise.
        """
        if not self._cache_path.exists():
            return False
        
        try:
            with open(self._cache_path, "rb") as f:
                cached_data = pickle.load(f)
            
            # Verify cache is valid by checking it has expected structure
            if not isinstance(cached_data, dict) or "index" not in cached_data:
                logger.debug("Cache file invalid, will rebuild")
                return False
            
            self._index_by_term = cached_data["index"]
            logger.debug(f"Loaded index from cache ({len(self._index_by_term)} terms)")
            return True
        except Exception as e:
            logger.debug(f"Failed to load cache: {e}, will rebuild")
            return False
    
    def _save_cache(self) -> None:
        """Save the built index to cache."""
        try:
            cached_data = {"index": self._index_by_term}
            with open(self._cache_path, "wb") as f:
                pickle.dump(cached_data, f)
            logger.debug(f"Saved index to cache: {self._cache_path}")
        except Exception as e:
            logger.debug(f"Failed to save cache: {e}")

    def _load_term_bank(self, bank_id: int) -> list[list[Any]]:
        """Load a term_bank JSON file from the ZIP, with caching.

        Args:
            bank_id: The bank number (e.g., 1 for term_bank_1.json).

        Returns:
            Parsed JSON list of term entries.

        Raises:
            ValueError: If the bank file does not exist in the ZIP.
        """
        if bank_id in self._term_bank_cache:
            return self._term_bank_cache[bank_id]

        filename = f"term_bank_{bank_id}.json"
        try:
            with ZipFile(self.zip_path, "r") as zf:
                data = zf.read(filename).decode("utf-8")
            entries = json.loads(data)
            self._term_bank_cache[bank_id] = entries
            return entries
        except KeyError:
            raise ValueError(f"Term bank not found: {filename}") from None

    def _build_index(self) -> None:
        """Build an in-memory index of all terms.

        This scans all term_bank_N.json files and builds a mapping from
        term (headword) to a list of (bank_id, entry_index) tuples for lookup.
        """
        if self._index_by_term:
            return  # Already built

        logger.info("Building term index for %s", self.zip_path.name)

        with ZipFile(self.zip_path, "r") as zf:
            term_banks = [
                f for f in zf.namelist()
                if f.startswith("term_bank_") and f.endswith(".json")
            ]
            self._process_term_banks(zf, term_banks)

        logger.info(
            "Built index with %d unique terms across %d banks",
            len(self._index_by_term),
            len(self._term_bank_cache),
        )
        self._save_cache()

    def _process_term_banks(
        self,
        zf: ZipFile,
        term_banks: list[str],
        progress: Any = None,
        task: Any = None,
    ) -> None:
        """Process all term bank files and build the index."""
        for filename in term_banks:
            try:
                bank_id = int(filename.replace("term_bank_", "").replace(".json", ""))
            except ValueError:
                continue

            data = zf.read(filename).decode("utf-8")
            entries = json.loads(data)

            for entry_idx, entry in enumerate(entries):
                if not entry or len(entry) < 1:
                    continue
                term = entry[0]  # First element is the headword
                if term not in self._index_by_term:
                    self._index_by_term[term] = []
                self._index_by_term[term].append((bank_id, entry_idx))

            if progress and task is not None:
                progress.update(task, advance=1)

    def lookup(self, term: str) -> list[dict[str, Any]]:
        """Lookup a term and return matching dictionary entries.

        Args:
            term: The Japanese word/term to look up.

        Returns:
            List of entry dictionaries, each containing:
            - 'term': The headword
            - 'reading': The kana reading
            - 'definition': Structured definition content
            - 'sequence': JMdict sequence number (if available)
            
            Entries are sorted by sequence number (ascending) so primary
            definitions appear first.
        """
        if not self._index_by_term:
            self._build_index()

        if term not in self._index_by_term:
            return []

        results = []
        for bank_id, entry_idx in self._index_by_term[term]:
            bank_data = self._load_term_bank(bank_id)
            if entry_idx < len(bank_data):
                entry = bank_data[entry_idx]
                results.append(self._parse_entry(entry))

        # Sort by sequence number (lower = more common/primary)
        results.sort(key=lambda x: x.get("sequence") or float("inf"))
        return results

    @staticmethod
    def _parse_entry(entry: list[Any]) -> dict[str, Any]:
        """Parse a single term entry into a usable dictionary.

        The Yomitan format stores entries as:
        [term, reading, definition_tags, sense_tags, popularity, definitions, sequence, ...]

        Args:
            entry: Raw entry list from term_bank JSON.

        Returns:
            Dictionary with parsed entry data.
        """
        if len(entry) < 5:
            return {}

        term = entry[0] if isinstance(entry[0], str) else ""
        reading = entry[1] if isinstance(entry[1], str) else ""
        definitions = entry[5] if len(entry) > 5 else []
        sequence = entry[6] if len(entry) > 6 else None

        return {
            "term": term,
            "reading": reading,
            "definition": definitions,
            "sequence": sequence,
        }

    def get_primary_entry(self, term: str) -> dict[str, Any] | None:
        """Get the primary (most common) entry for a term.
        
        This returns only the first entry after sorting by sequence number,
        suitable when you only need one result.
        
        Args:
            term: The Japanese word/term to look up.
            
        Returns:
            The primary entry dictionary, or None if not found.
        """
        results = self.lookup(term)
        return results[0] if results else None


def load_dictionary(zip_path: str | Path) -> YomitanDictionary:
    """Convenience function to load a Yomitan dictionary.

    Args:
        zip_path: Path to the dictionary ZIP file.

    Returns:
        An initialized YomitanDictionary instance.
    """
    return YomitanDictionary(zip_path)
