"""
handler.py — Notes function logic.

Notes are stored as a list of dicts: {id, title, body, created_at, updated_at}.
The backend provides CRUD endpoints; the front-end uses localStorage for
offline-first behavior and syncs when the backend is reachable.
"""
from __future__ import annotations

import uuid
import datetime
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class Note:
    id: str
    title: str
    body: str
    created_at: str
    updated_at: str

    def to_dict(self) -> dict:
        return asdict(self)


_store: dict[str, Note] = {}


def create_note(title: str, body: str = "") -> Note:
    now = datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    note = Note(
        id=str(uuid.uuid4()),
        title=title or "Untitled",
        body=body,
        created_at=now,
        updated_at=now,
    )
    _store[note.id] = note
    return note


def get_note(note_id: str) -> Optional[Note]:
    return _store.get(note_id)


def list_notes() -> list[dict]:
    return [n.to_dict() for n in sorted(_store.values(),
                                         key=lambda n: n.updated_at, reverse=True)]


def update_note(note_id: str, title: Optional[str] = None,
                body: Optional[str] = None) -> Optional[Note]:
    note = _store.get(note_id)
    if note is None:
        return None
    if title is not None:
        note.title = title
    if body is not None:
        note.body = body
    note.updated_at = datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    return note


def delete_note(note_id: str) -> bool:
    return _store.pop(note_id, None) is not None


def search_notes(query: str) -> list[dict]:
    q = query.lower()
    return [n.to_dict() for n in _store.values()
            if q in n.title.lower() or q in n.body.lower()]


if __name__ == "__main__":
    n = create_note("Hello", "World")
    print(n.to_dict())
    print(list_notes())
