import os
from pathlib import Path
from typing import Any, Dict

import yaml


def load_config(path: str | None = None) -> Dict[str, Any]:
    if path is None:
        path = os.environ.get("JARVIS_KB_CONFIG", "config.yaml")
    with open(path) as f:
        raw = yaml.safe_load(f)
    cfg = raw.get("jarvis_kb", raw)

    def expand(obj: Any) -> Any:
        if isinstance(obj, str) and obj.startswith("~/"):
            return os.path.expanduser(obj)
        if isinstance(obj, dict):
            return {k: expand(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [expand(i) for i in obj]
        return obj

    return expand(cfg)
