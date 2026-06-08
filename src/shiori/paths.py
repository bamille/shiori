from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SHIORI_UNIDIC_DIR = Path(os.environ.get("SHIORI_UNIDIC_DIR", PROJECT_ROOT / "data" / "unidic"))