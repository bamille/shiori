"""Persistent storage for words the user has already learned."""

from __future__ import annotations

import json
from pathlib import Path

DEFAULT_PATH = Path.home() / ".shiori" / "known_words.json"


class KnownWords:
    """A persisted set of known word lemmas, stored as JSON."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else DEFAULT_PATH
        self._words: set[str] = set()
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self._words = set(data.get("words", []))
            except (json.JSONDecodeError, OSError):
                self._words = set()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"words": sorted(self._words)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def add(self, word: str) -> None:
        self._words.add(word)

    def remove(self, word: str) -> None:
        self._words.discard(word)

    def __contains__(self, word: object) -> bool:
        return word in self._words

    def __len__(self) -> int:
        return len(self._words)
