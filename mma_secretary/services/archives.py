from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from mma_secretary.services.engine import TournamentService

_META_KEY = "current_archive_id"


def _safe(name: str) -> str:
    text = re.sub(r"[^\w\-а-яА-ЯёЁ]+", "_", (name or "").strip(), flags=re.IGNORECASE)
    text = text.strip("_")[:40]
    return text or "turnir"


class Archives:
    def __init__(self, folder: Path, svc: TournamentService):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.svc = svc

    def _ensure_meta(self) -> None:
        self.svc.conn.execute(
            "CREATE TABLE IF NOT EXISTS app_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )

    def current_id(self) -> str | None:
        self._ensure_meta()
        row = self.svc.conn.execute(
            "SELECT value FROM app_meta WHERE key=?", (_META_KEY,)
        ).fetchone()
        return row[0] if row else None

    def set_current_id(self, sid: str | None) -> None:
        self._ensure_meta()
        if sid:
            self.svc.conn.execute(
                "INSERT INTO app_meta (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (_META_KEY, sid),
            )
        else:
            self.svc.conn.execute("DELETE FROM app_meta WHERE key=?", (_META_KEY,))
        self.svc.conn.commit()

    def list(self) -> list[dict]:
        current = self.current_id()
        items = []
        for path in self.folder.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            meta = data.get("_meta") or {}
            t = data.get("tournament") or {}
            sid = path.stem
            items.append(
                {
                    "id": sid,
                    "name": meta.get("title") or t.get("name") or path.stem,
                    "saved_at": meta.get("saved_at") or "",
                    "participants": len(data.get("participants") or []),
                    "active": bool(current) and sid == current,
                }
            )
        items.sort(key=lambda x: x["saved_at"] or x["id"], reverse=True)
        return items

    def save(self, title: str) -> dict:
        title = (title or "").strip() or (self.svc.get_tournament().get("name") or "Турнир")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        sid = f"{stamp}_{_safe(title)}"
        bundle = self.svc.export_bundle()
        bundle["_meta"] = {
            "title": title,
            "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        path = self.folder / f"{sid}.json"
        path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        self.set_current_id(sid)
        return {"id": sid, "name": title}

    def load(self, sid: str) -> None:
        path = self.folder / f"{sid}.json"
        if not path.is_file():
            raise FileNotFoundError("Такой сохранённый турнир не найден")
        data = json.loads(path.read_text(encoding="utf-8"))
        self.svc.import_bundle(data)
        self.set_current_id(sid)

    def delete(self, sid: str) -> None:
        path = self.folder / f"{sid}.json"
        if path.is_file():
            path.unlink()
        if self.current_id() == sid:
            self.set_current_id(None)
