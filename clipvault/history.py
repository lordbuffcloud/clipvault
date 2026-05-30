"""Persistent clipboard history model."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from uuid import uuid4


@dataclass
class ClipboardItem:
    """One saved text clipboard item."""

    id: str
    text: str
    created_at: str
    updated_at: str
    pinned: bool = False

    @classmethod
    def create(cls, text: str) -> "ClipboardItem":
        now = utc_now()
        return cls(id=uuid4().hex, text=text, created_at=now, updated_at=now)

    @classmethod
    def from_dict(cls, data: dict) -> "ClipboardItem":
        return cls(
            id=str(data["id"]),
            text=str(data["text"]),
            created_at=str(data.get("created_at") or utc_now()),
            updated_at=str(data.get("updated_at") or data.get("created_at") or utc_now()),
            pinned=bool(data.get("pinned", False)),
        )

    def to_dict(self) -> dict:
        return asdict(self)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def default_history_path() -> Path:
    data_home = os.environ.get("XDG_DATA_HOME")
    base = Path(data_home).expanduser() if data_home else Path.home() / ".local" / "share"
    return base / "clipvault" / "history.json"


class ClipboardHistory:
    """Manage clipboard history items and JSON persistence."""

    def __init__(self, path: str | Path | None = None, max_items: int = 100):
        if max_items < 1:
            raise ValueError("max_items must be at least 1")
        self.path = Path(path).expanduser() if path else default_history_path()
        self.max_items = max_items
        self.items: list[ClipboardItem] = []

    @classmethod
    def load(cls, path: str | Path | None = None, max_items: int = 100) -> "ClipboardHistory":
        history = cls(path=path, max_items=max_items)
        if not history.path.exists():
            return history

        try:
            data = json.loads(history.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return history

        raw_items = data.get("items", []) if isinstance(data, dict) else []
        if not isinstance(raw_items, list):
            return history

        loaded: list[ClipboardItem] = []
        seen_texts: set[str] = set()
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            try:
                item = ClipboardItem.from_dict(raw)
            except (KeyError, TypeError, ValueError):
                continue
            if not item.text.strip() or item.text in seen_texts:
                continue
            loaded.append(item)
            seen_texts.add(item.text)

        history.items = loaded
        history._prune()
        return history

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "max_items": self.max_items,
            "items": [item.to_dict() for item in self.items],
        }
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(self.path)

    def add(self, text: str) -> ClipboardItem | None:
        normalized = text.strip()
        if not normalized:
            return None

        for index, item in enumerate(self.items):
            if item.text == text:
                item.updated_at = utc_now()
                self.items.pop(index)
                self.items.insert(0, item)
                return item

        item = ClipboardItem.create(text)
        self.items.insert(0, item)
        self._prune()
        return item

    def search(self, query: str) -> list[ClipboardItem]:
        normalized = query.strip().casefold()
        if not normalized:
            return list(self.items)
        return [item for item in self.items if normalized in item.text.casefold()]

    def delete(self, item_id: str) -> bool:
        for index, item in enumerate(self.items):
            if item.id == item_id:
                self.items.pop(index)
                return True
        return False

    def pin(self, item_id: str, pinned: bool) -> bool:
        for item in self.items:
            if item.id == item_id:
                item.pinned = pinned
                item.updated_at = utc_now()
                self._prune()
                return True
        return False

    def clear(self, include_pinned: bool = False) -> None:
        if include_pinned:
            self.items = []
        else:
            self.items = [item for item in self.items if item.pinned]

    def _prune(self) -> None:
        while len(self.items) > self.max_items:
            remove_index = self._oldest_unpinned_index()
            if remove_index is None:
                remove_index = len(self.items) - 1
            self.items.pop(remove_index)

    def _oldest_unpinned_index(self) -> int | None:
        for index in range(len(self.items) - 1, -1, -1):
            if not self.items[index].pinned:
                return index
        return None
