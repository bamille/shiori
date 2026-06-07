"""Remove the repo-local UniDic data directory."""

from __future__ import annotations

import shutil
from pathlib import Path

from .utils import SHIORI_UNIDIC_DIR


def main() -> None:
    """Delete the installed UniDic tree if it exists."""

    if SHIORI_UNIDIC_DIR.exists():
        shutil.rmtree(SHIORI_UNIDIC_DIR)
        print(f"Removed {SHIORI_UNIDIC_DIR}")
    else:
        print(f"Nothing to remove at {SHIORI_UNIDIC_DIR}")


if __name__ == "__main__":
    main()