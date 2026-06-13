#!/usr/bin/env python3
"""Download the Jitendex Yomitan dictionary."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from urllib.request import urlopen

logger = logging.getLogger(__name__)

JITENDEX_URL = "https://github.com/stephenmk/stephenmk.github.io/releases/latest/download/jitendex-yomitan.zip"
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "data" / "jitendex-yomitan.zip"


def download_jitendex(output_path: Path | None = None, chunk_size: int = 8192) -> Path:
    """Download the latest Jitendex Yomitan dictionary.

    Args:
        output_path: Where to save the ZIP file. Defaults to data/jitendex-yomitan.zip.
        chunk_size: Download chunk size in bytes.

    Returns:
        Path to the downloaded file.

    Raises:
        urllib.error.URLError: If the download fails.
    """
    output_path = output_path or DEFAULT_OUTPUT
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Downloading Jitendex from %s", JITENDEX_URL)
    logger.info("Saving to %s", output_path)

    try:
        with urlopen(JITENDEX_URL, timeout=60) as response:
            total_size = response.headers.get("Content-Length")
            if total_size:
                total_size = int(total_size)
                logger.info("File size: %.2f MB", total_size / (1024 * 1024))

            downloaded = 0
            with open(output_path, "wb") as f:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size:
                        percent = (downloaded / total_size) * 100
                        logger.info("Progress: %.1f%%", percent)

    except Exception as exc:
        logger.error("Failed to download: %s", exc)
        if output_path.exists():
            output_path.unlink()
        raise

    logger.info("Download complete: %s", output_path)
    return output_path


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for downloading Jitendex."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="shiori-download-dict",
        description="Download the Jitendex Yomitan dictionary.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    try:
        path = download_jitendex(args.output)
        print(f"Successfully downloaded to: {path}")
        return 0
    except Exception:
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
