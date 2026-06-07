"""Manual UniDic bootstrap for Shiori.

Run this script only when you want to download the large UniDic data set into
the repo-local data/unidic directory.

Usage:
    uv run python scripts/bootstrap_unidic.py

The script does not run during uv sync and does not install UniDic as a normal
project dependency.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Callable
from urllib.error import URLError
from urllib.request import urlopen, urlretrieve

from .utils import SHIORI_UNIDIC_DIR, DICT_INFO_URL, SHIORI_UNIDIC_VERSION_FILE


ProgressCallback = Callable[[int, int], None]


def _fetch_latest_dictionary_info() -> dict[str, str]:
    """Return the latest UniDic metadata entry from the upstream index."""

    try:
        with urlopen(DICT_INFO_URL) as response:
            data = json.load(response)
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError("Unable to fetch UniDic download metadata") from exc

    try:
        return data["latest"]
    except (KeyError, TypeError) as exc:
        raise RuntimeError("UniDic metadata did not contain a latest download entry") from exc


def _read_installed_version() -> str | None:
    """Return the installed UniDic version label, if present."""

    if SHIORI_UNIDIC_VERSION_FILE.exists():
        return SHIORI_UNIDIC_VERSION_FILE.read_text(encoding="utf-8").strip() or None

    return None


def _write_installed_version(version: str) -> None:
    """Persist the installed UniDic version label for future runs."""

    SHIORI_UNIDIC_VERSION_FILE.write_text(f"{version}\n", encoding="utf-8")


def _looks_like_installed_dictionary() -> bool:
    """Check for a completed dictionary tree when no marker file exists."""

    return (SHIORI_UNIDIC_DIR / "sys.dic").exists()


def _download_file(url: str, destination: Path, progress_callback: ProgressCallback | None = None) -> None:
    """Download a file to a local path and emit progress updates if provided."""

    def reporthook(block_count: int, block_size: int, total_size: int) -> None:
        downloaded = block_count * block_size
        if total_size > 0 and downloaded > total_size:
            downloaded = total_size

        if progress_callback is not None:
            progress_callback(downloaded, total_size)

    try:
        urlretrieve(url, destination, reporthook=reporthook)
    except Exception as exc:
        raise RuntimeError(f"Failed to download UniDic archive from {url}") from exc


def _extract_single_directory(archive_path: Path, destination: Path) -> None:
    """Extract the downloaded archive into a temporary staging directory."""

    try:
        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(destination)
    except zipfile.BadZipFile as exc:
        raise RuntimeError("Downloaded UniDic archive was not a valid zip file") from exc


def _move_dictionary_tree(source_root: Path) -> None:
    """Move the extracted UniDic tree into the final repo-local directory."""

    candidates = [path for path in source_root.iterdir() if path.is_dir()]
    if len(candidates) != 1:
        raise RuntimeError("Downloaded UniDic archive did not contain exactly one top-level directory")

    source_dir = candidates[0]
    if SHIORI_UNIDIC_DIR.exists():
        shutil.rmtree(SHIORI_UNIDIC_DIR)

    # if interrupted could lead to partial transfer/cleanup required
    shutil.move(str(source_dir), SHIORI_UNIDIC_DIR)

def main() -> None:
    """Bootstrap UniDic into the repo-local data directory."""

    SHIORI_UNIDIC_DIR.parent.mkdir(parents=True, exist_ok=True)

    dict_info = _fetch_latest_dictionary_info()
    latest_version = f"unidic-{dict_info['version']}"
    installed_version = _read_installed_version()

    if installed_version is None and _looks_like_installed_dictionary():
        _write_installed_version(latest_version)
        print(f"UniDic already present at {SHIORI_UNIDIC_DIR}")
        return

    if installed_version == latest_version:
        print(f"UniDic already present at {SHIORI_UNIDIC_DIR}")
        return

    if installed_version is not None:
        print(f"Updating UniDic from {installed_version} to {latest_version}")
    else:
        print(f"Installing UniDic {latest_version}")

    def progress_callback(downloaded: int, total_size: int) -> None:
        if total_size > 0:
            percent = downloaded * 100 / total_size
            print(f"\rDownloading UniDic: {percent:5.1f}%", end="", flush=True)
        else:
            print(f"\rDownloading UniDic: {downloaded} bytes", end="", flush=True)

    with tempfile.TemporaryDirectory() as temp_dir:
        archive_path = Path(temp_dir) / "unidic.zip"
        extracted_root = Path(temp_dir) / "extracted"
        extracted_root.mkdir()

        _download_file(dict_info["url"], archive_path, progress_callback=progress_callback)
        print()
        _extract_single_directory(archive_path, extracted_root)
        _move_dictionary_tree(extracted_root)
        _write_installed_version(latest_version)

    print(f"UniDic downloaded to {SHIORI_UNIDIC_DIR}")


if __name__ == "__main__":
    main()