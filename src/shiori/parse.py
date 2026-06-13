from __future__ import annotations
from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from fugashi import Tagger

from shiori.paths import SHIORI_UNIDIC_DIR

if TYPE_CHECKING:
    from .ingest import Chapter


QUOTE_PAIRS = {
    "「": "」",
    "『": "』",
    "｢": "｣",
    "【": "】",
    "〈": "〉",
    "《": "》",
    "（": "）",
    "(": ")",
    "[": "]",
}
QUOTE_CLOSERS = {close: open_ for open_, close in QUOTE_PAIRS.items()}
SENTENCE_END_SURFACES = {"。", "！", "？", "!", "?", "．", "｡"}
SENTENCE_BOUNDARY_POS = ("補助記号", "句点")

# must use -r /dev/null so that we don't try to use a system-wide install of unidic
# Note: always use same tagger - see docs for fugashi
@lru_cache(maxsize=1)
def get_tagger() -> Tagger:
    return Tagger(f'-r /dev/null -d "{SHIORI_UNIDIC_DIR}"')

@dataclass(slots=True)
class Word:
    """
    Wrapper for a lexeme, including useful context
    Attributes:
        id: Unique identifier to keep track of word in database.
        lexeme: The lexeme of the actual word.
        original: The lexeme, including inflections. If None, = lexeme.
        context: Surrounding sentence. If blank, assume standalone.
    """
    lexeme: str
    original: str | None
    context: str | None
    is_unk: bool = False
    is_eos: bool = False

    @property
    def id(self):
        return hash(self.lexeme)


class Parser:
    """
    Convert raw text into Word classes
    """
    def __init__(self):
        self._tagger = get_tagger()

    def tokenize(self, input: Chapter | str) -> list[Word]:
        # Avoid importing Chapter at runtime (circular import); duck-type instead.
        if isinstance(input, str):
            text = input
            chapter = None
        else:
            text = input.text
            chapter = input
        tokens = list(self._tagger(text))
        sentences = self._split_sentences(tokens)

        words: list[Word] = []
        for sentence_tokens in sentences:
            sentence_words = self._words_for_sentence(sentence_tokens)
            words.extend(sentence_words)

        if chapter is not None:
            chapter.words = words

        return words

    def tokinize(self, input: Chapter | str) -> list[Word]:
        return self.tokenize(input)

    @staticmethod
    def _feature_value(token: Any, name: str) -> str | None:
        value = getattr(token.feature, name, None)
        return value if value and value != "*" else None

    @classmethod
    def _is_quote_open(cls, token: Any) -> bool:
        return token.surface in QUOTE_PAIRS

    @classmethod
    def _is_quote_close(cls, token: Any) -> bool:
        return token.surface in QUOTE_CLOSERS

    @classmethod
    def _is_sentence_boundary(cls, token: Any) -> bool:
        if token.surface in SENTENCE_END_SURFACES:
            return True

        pos1 = getattr(token.feature, "pos1", None)
        pos2 = getattr(token.feature, "pos2", None)
        return (pos1, pos2) == SENTENCE_BOUNDARY_POS

    @classmethod
    def _split_sentences(cls, tokens: list[Any]) -> list[list[Any]]:
        sentences: list[list[Any]] = []
        current: list[Any] = []
        quote_stack: list[str] = []

        for token in tokens:
            current.append(token)

            if cls._is_quote_open(token):
                quote_stack.append(QUOTE_PAIRS[token.surface])
                continue

            if cls._is_quote_close(token):
                if quote_stack and quote_stack[-1] == token.surface:
                    quote_stack.pop()
                continue

            if cls._is_sentence_boundary(token) and not quote_stack:
                sentences.append(current)
                current = []

        if current:
            sentences.append(current)

        return sentences

    def _words_for_sentence(self, sentence_tokens: list[Any]) -> list[Word]:
        sentence_text = "".join(token.surface for token in sentence_tokens).strip()
        quote_spans = self._quote_spans(sentence_tokens)
        has_quote = bool(quote_spans)

        words: list[Word] = []
        for index, token in enumerate(sentence_tokens):
            context = sentence_text
            if has_quote:
                quote_context = self._context_for_token_in_quotes(sentence_tokens, quote_spans, index)
                if quote_context is not None:
                    context = quote_context

            words.append(
                Word(
                    lexeme=token.surface,
                    original=self._feature_value(token, "lemma"),
                    context=context,
                    is_unk=bool(getattr(token, "is_unk", False)),
                    is_eos=index == len(sentence_tokens) - 1,
                ),
            )

        return words

    @staticmethod
    def _quote_spans(sentence_tokens: list[Any]) -> list[tuple[int, int]]:
        spans: list[tuple[int, int]] = []
        stack: list[tuple[str, int]] = []

        for index, token in enumerate(sentence_tokens):
            if token.surface in QUOTE_PAIRS:
                stack.append((token.surface, index))
                continue

            if token.surface in QUOTE_CLOSERS and stack:
                open_surface, open_index = stack[-1]
                if QUOTE_PAIRS[open_surface] == token.surface:
                    stack.pop()
                    spans.append((open_index, index))

        if stack:
            for _open_surface, open_index in stack:
                spans.append((open_index, len(sentence_tokens)))

        return spans

    @staticmethod
    def _context_for_token_in_quotes(
        sentence_tokens: list[Any],
        quote_spans: list[tuple[int, int]],
        index: int,
    ) -> str | None:
        containing_spans = [span for span in quote_spans if span[0] < index < span[1]]
        if not containing_spans:
            return None

        open_index, close_index = max(containing_spans, key=lambda span: span[0])
        return "".join(token.surface for token in sentence_tokens[open_index + 1 : close_index]).strip()



