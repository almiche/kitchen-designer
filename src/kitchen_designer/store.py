from __future__ import annotations

import json
import os
import secrets
from datetime import datetime
from pathlib import Path

from .catalog import _CATALOG_PATH


def project_root() -> Path:
    override = os.environ.get("KITCHEN_DESIGNER_HOME")
    if override:
        return Path(override)
    return _CATALOG_PATH.parents[1]


def designs_dir() -> Path:
    path = project_root() / "designs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def new_id(prefix: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{prefix}-{stamp}-{secrets.token_hex(2)}"


def design_dir(design_id: str) -> Path:
    path = designs_dir() / design_id
    if not path.is_dir():
        raise ValueError(f"unknown design {design_id}")
    return path


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())
