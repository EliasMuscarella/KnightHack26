"""Stage cache.

Each stage's output is cached under `data/cache/stages/<stage>/<key>.json` where
key = sha256(canonical JSON of {inputs, stage_version}). Rerunning recomputes only what changed.
Raw SEC artifacts live under `data/cache/sec/` and are never re-downloaded.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


def stable_hash(obj: Any) -> str:
    payload = json.dumps(
        obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class StageCache:
    def __init__(self, root: Path, enabled: bool = True):
        self.root = root
        self.enabled = enabled
        self.hits: list[str] = []
        self.misses: list[str] = []

    def key(self, stage: str, version: str, inputs: Any) -> str:
        return stable_hash({"stage": stage, "version": version, "inputs": inputs})

    def path(self, stage: str, key: str) -> Path:
        return self.root / "stages" / stage / f"{key}.json"

    def get(self, stage: str, key: str) -> Any | None:
        p = self.path(stage, key)
        if self.enabled and p.exists():
            self.hits.append(stage)
            return json.loads(p.read_text(encoding="utf-8"))
        self.misses.append(stage)
        return None

    def put(self, stage: str, key: str, value: Any) -> None:
        p = self.path(stage, key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        tmp.replace(p)
