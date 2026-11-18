"""Load/save the day-by-day JSON logs (tennis_diagnostico.json, web_diario.json) without losing history.

- save_json writes to a temporary file and swaps it in (os.replace), so a crash mid-write never truncates the log.
- load_json, when the file exists but cannot be parsed, moves it aside to <name>.corrupt-<UTC timestamp> and
  warns, instead of letting the next save overwrite the whole history with just today.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


def load_json(path: Path, default, strict: bool = False):
    """strict=True raises on a corrupt file instead of moving it aside (for records that must never restart empty)."""
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))   # -sig: some files were saved with a BOM
    except Exception as exc:  # noqa: BLE001
        if strict:
            raise RuntimeError(f"{path} is corrupt, refusing to overwrite it: {exc}") from exc
        aside = path.with_name(f"{path.name}.corrupt-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}")
        os.replace(path, aside)
        logger.warning("%s unreadable (%s): moved to %s, starting a new one", path.name, str(exc)[:80], aside.name)
        return default


def save_json(path: Path, data, **dumps_kwargs) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, **dumps_kwargs), encoding="utf-8")
    os.replace(tmp, path)
