import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def load_json_records(path: str | Path, source_name: str) -> tuple[list[dict], list[dict]]:
    """Load a JSON array and isolate malformed records instead of failing the whole sync."""
    path = Path(path)
    errors: list[dict] = []
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return [], [{"source": source_name, "error": f"File not found: {path}"}]
    except json.JSONDecodeError as exc:
        return [], [{"source": source_name, "error": f"Invalid JSON at line {exc.lineno}: {exc.msg}"}]

    if not isinstance(payload, list):
        return [], [{"source": source_name, "error": "Expected the top-level JSON value to be an array."}]

    records = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            errors.append({"source": source_name, "record_index": index, "error": "Record is not a JSON object."})
            continue
        records.append(item)
    logger.info("Loaded %s valid records from %s", len(records), source_name)
    return records, errors
