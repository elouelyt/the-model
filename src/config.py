"""Loads non-sensitive project configuration from config.yaml."""

from pathlib import Path
from typing import Any

import yaml

_CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


def load_config() -> dict[str, Any]:
    """Load and return the project configuration from config.yaml.

    Returns:
        Parsed configuration as a nested dictionary.

    Raises:
        FileNotFoundError: If config.yaml does not exist.
    """
    if not _CONFIG_PATH.exists():
        raise FileNotFoundError(f"config.yaml not found at {_CONFIG_PATH}")
    with open(_CONFIG_PATH) as f:
        return yaml.safe_load(f)
