from .cli import main as cli_main
from .ingest import Book, Chapter


def main(argv: list[str] | None = None) -> int:
    return cli_main(argv)
