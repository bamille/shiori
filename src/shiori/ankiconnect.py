from __future__ import annotations

import json
import logging
import re
from argparse import Namespace
from functools import lru_cache
from pathlib import Path
from typing import Any

from py_ankiconnect import PyAnkiconnect

logger = logging.getLogger(__name__)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_NOTE_TYPES_DIR = Path(__file__).resolve().parent / "anki_templates" / "note_types"


def _normalize_host(host: str) -> str:
    if host.startswith("http://") or host.startswith("https://"):
        return host
    return f"http://{host}"

@lru_cache(maxsize=1)
def get_anki_client(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> PyAnkiconnect:
    return PyAnkiconnect(default_host=_normalize_host(host), default_port=port)


def get_note_type_names(client: PyAnkiconnect) -> list[str]:
    result = client("modelNames")
    if not isinstance(result, list):
        raise RuntimeError("Unexpected response from AnkiConnect when listing note types")
    return [str(item) for item in result]


def get_note_type_definition(client: PyAnkiconnect, model_name: str) -> dict[str, Any]:
    """Fetch available model metadata and styling for the selected note type.

    AnkiConnect wrappers can return styling in different forms: older or
    simpler APIs may return a raw CSS string, while some clients or future
    versions may return a richer dict/object.
    """
    result: dict[str, Any] = {
        "name": model_name,
        "fields": client("modelFieldNames", modelName=model_name),
        "templates": client("modelTemplates", modelName=model_name),
    }

    try:
        styling = client("modelStyling", modelName=model_name)
    except Exception as exc:
        styling = None
        logger.warning(
            "Unable to fetch model styling for '%s': %s",
            model_name,
            exc,
        )

    if styling is None:
        logger.warning(
            "No styling returned for note type '%s'; the exported JSON will omit css.",
            model_name,
        )
    elif isinstance(styling, str):
        if styling.strip():
            result["css"] = styling
        else:
            logger.warning(
                "AnkiConnect returned an empty CSS string for '%s'; css will be omitted.",
                model_name,
            )
    elif isinstance(styling, dict):
        if styling:
            result["css"] = styling
        else:
            logger.warning(
                "AnkiConnect returned an empty styling dict for '%s'; css will be omitted.",
                model_name,
            )
    else:
        logger.warning(
            "Received unexpected styling type %s for '%s'; css will be omitted.",
            type(styling).__name__,
            model_name,
        )

    return result


def sanitize_name_for_filename(name: str) -> str:
    sanitized = re.sub(r"[^\w\- ]+", "", name).strip()
    sanitized = re.sub(r"[\s]+", "_", sanitized)
    return sanitized or "anki_note_type"


def choose_note_type(note_types: list[str], choice: str | None = None) -> str:
    if not note_types:
        raise RuntimeError("No note types were returned from AnkiConnect.")

    if choice:
        candidate = choice.strip()
        if candidate.isdigit():
            index = int(candidate) - 1
            if 0 <= index < len(note_types):
                return note_types[index]
            raise ValueError(f"Note type index {candidate} is out of range.")
        if candidate in note_types:
            return candidate
        raise ValueError(f"Note type '{candidate}' was not found in the available models.")

    for index, name in enumerate(note_types, start=1):
        print(f"{index:3d}. {name}")

    selected = input("Select a note type by number or exact name: ").strip()
    if not selected:
        raise ValueError("No selection provided.")

    return choose_note_type(note_types, selected)


def export_note_type(
    note_type: str | None = None,
    output_dir: Path | None = None,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    force: bool = False,
) -> Path:
    client = get_anki_client(host, port)
    note_types = get_note_type_names(client)
    selected = choose_note_type(note_types, note_type)
    note_type_definition = get_note_type_definition(client, selected)

    destination_dir = (output_dir or DEFAULT_NOTE_TYPES_DIR).resolve()
    destination_dir.mkdir(parents=True, exist_ok=True)
    output_path = destination_dir / f"{sanitize_name_for_filename(selected)}.json"

    if output_path.exists() and not force:
        raise FileExistsError(
            f"Output file already exists: {output_path}. Use --force to overwrite."
        )

    output_path.write_text(
        json.dumps(note_type_definition, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path


def cmd_export_note_type(args: Namespace) -> None:
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_NOTE_TYPES_DIR
    try:
        path = export_note_type(
            note_type=args.note_type,
            output_dir=output_dir,
            host=args.host,
            port=args.port,
            force=args.force,
        )
    except Exception as exc:
        raise SystemExit(f"Failed to export note type: {exc}") from exc

    print(f"Wrote Anki note type JSON to: {path}")
