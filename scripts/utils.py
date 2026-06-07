from pathlib import Path

SHIORI_UNIDIC_DIR = Path(__file__).resolve().parents[1] / "data" / "unidic"
DICT_INFO_URL = "https://raw.githubusercontent.com/polm/unidic-py/master/dicts.json"
SHIORI_UNIDIC_VERSION_FILE = SHIORI_UNIDIC_DIR / ".shiori-unidic-version"