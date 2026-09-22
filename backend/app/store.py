"""On-disk gallery: each generated image is `<id>.<ext>` plus a `<id>.json` sidecar with its parameters."""
from __future__ import annotations

import base64
import json
import secrets
import time
from pathlib import Path
from typing import Any


class Store:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, *, b64: str, fmt: str, params: dict[str, Any], job_id: str, index: int, seed: int | None) -> dict[str, Any]:
        ext = {"jpeg": "jpg", "jpg": "jpg", "webp": "webp"}.get(fmt.lower(), "png")
        image_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(3)}"
        image_path = self.root / f"{image_id}.{ext}"
        image_path.write_bytes(base64.b64decode(b64))
        record = {
            "id": image_id,
            "file": image_path.name,
            "url": f"/outputs/{image_path.name}",
            "created": time.time(),
            "job_id": job_id,
            "index": index,
            "seed": seed,
            "params": params,
        }
        (self.root / f"{image_id}.json").write_text(json.dumps(record, indent=2))
        return record

    def get(self, image_id: str) -> dict[str, Any] | None:
        meta = self.root / f"{image_id}.json"
        if not meta.exists():
            return None
        return json.loads(meta.read_text())

    def list(self, limit: int = 60, offset: int = 0) -> dict[str, Any]:
        metas = sorted(self.root.glob("*.json"), key=lambda p: p.name, reverse=True)
        items = []
        for p in metas[offset : offset + limit]:
            try:
                items.append(json.loads(p.read_text()))
            except (OSError, ValueError):
                continue
        return {"items": items, "total": len(metas), "offset": offset, "limit": limit}

    def delete(self, image_id: str) -> bool:
        record = self.get(image_id)
        if record is None:
            return False
        for name in (record["file"], f"{image_id}.json"):
            path = self.root / name
            if path.exists():
                path.unlink()
        return True
