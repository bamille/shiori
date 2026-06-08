from pathlib import Path

from shiori import Book
from shiori.parse import Parser


SAMPLE = Path("src/shiori/test_sources/test1.epub")


def test_tokenize_stores_words_and_scopes_quote_contexts():
	book = Book.from_epub(SAMPLE)
	chapter = next(
		chapter
		for chapter in book.chapters
		if "それで、お金のことはなんとかなったんだね？" in chapter.text
	)

	parser = Parser()
	words = parser.tokenize(chapter)

	assert chapter.words is words

	quoted_word = next(
		word
		for word in words
		if word.lexeme == "それ" and word.context == "それで、お金のことはなんとかなったんだね？"
	)
	outside_word = next(
		word
		for word in words
		if word.lexeme == "言う"
		# Note that カラスと呼ばれる少年 is a title, not part of context.
		# TODO: Fix title detection to make robust (look for newlines + no EOS marker?)
		and word.context == 'カラスと呼ばれる少年「それで、お金のことはなんとかなったんだね？」とカラスと呼ばれる少年は言う。'
	)

	assert quoted_word.context == "それで、お金のことはなんとかなったんだね？"
	assert outside_word.context == 'カラスと呼ばれる少年「それで、お金のことはなんとかなったんだね？」とカラスと呼ばれる少年は言う。'
	assert words[-1].is_eos