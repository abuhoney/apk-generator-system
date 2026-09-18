"""
handler.py — Todo List function logic.
"""
from __future__ import annotations

import uuid
import datetime
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class Todo:
    id: str
    text: str
    done: bool
    created_at: str
    completed_at: Optional[str]

    def to_dict(self) -> dict:
        return asdict(self)


_store: list[Todo] = []


def add_todo(text: str) -> Todo:
    now = datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    t = Todo(id=str(uuid.uuid4()), text=text, done=False,
             created_at=now, completed_at=None)
    _store.append(t)
    return t


def list_todos(include_done: bool = True) -> list[dict]:
    items = _store if include_done else [t for t in _store if not t.done]
    return [t.to_dict() for t in items]


def toggle_todo(todo_id: str) -> Optional[Todo]:
    for t in _store:
        if t.id == todo_id:
            t.done = not t.done
            t.completed_at = (datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z") if t.done else None
            return t
    return None


def delete_todo(todo_id: str) -> bool:
    global _store
    before = len(_store)
    _store = [t for t in _store if t.id != todo_id]
    return len(_store) < before


def clear_done() -> int:
    global _store
    before = len(_store)
    _store = [t for t in _store if not t.done]
    return before - len(_store)


if __name__ == "__main__":
    add_todo("Test task")
    print(list_todos())
