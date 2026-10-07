"""
Chats ko storage/chats.json me save karta hai (server restart ke baad bhi bani rehti hain).
Baad me isi interface ke saath database lagayenge, baaki code nahi badlega.
"""
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from threading import Lock

from app.core.config import get_settings
from app.core.database import available, connection
from psycopg.types.json import Json


def now() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class Message:
    role: str
    content: str
    id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=now)
    attachments: list[dict] | None = None
    model: dict | None = None
    duration_ms: int | None = None
    steps: list[dict] | None = None
    sources: list[dict] | None = None
    files: list[dict] | None = None
    error: str | None = None


@dataclass
class Chat:
    title: str
    id: str = field(default_factory=new_id)
    updated_at: datetime = field(default_factory=now)
    messages: list[Message] = field(default_factory=list)


def _to_json(chat: Chat) -> dict:
    data = asdict(chat)
    data["updated_at"] = chat.updated_at.isoformat()
    for m in data["messages"]:
        m["created_at"] = m["created_at"].isoformat()
    return data


def _from_json(data: dict) -> Chat:
    messages = [
        Message(**{**m, "created_at": datetime.fromisoformat(m["created_at"])})
        for m in data.get("messages", [])
    ]
    return Chat(
        id=data["id"],
        title=data["title"],
        updated_at=datetime.fromisoformat(data["updated_at"]),
        messages=messages,
    )


class ChatStore:
    def __init__(self) -> None:
        self._path = get_settings().storage_dir / "chats.json"
        self._lock = Lock()
        self._chats: dict[str, Chat] = self._load()

    # ---------- disk ----------

    def _load(self) -> dict[str, Chat]:
        if not self._path.exists():
            return {}
        try:
            items = json.loads(self._path.read_text(encoding="utf-8"))
            return {c["id"]: _from_json(c) for c in items}
        except (OSError, ValueError, KeyError, TypeError):
            return {}  # file kharab ho to khali se shuru

    def _save(self) -> None:
        # Ye hamesha lock ke andar call hota hai
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps([_to_json(c) for c in self._chats.values()], ensure_ascii=False),
            encoding="utf-8",
        )
        tmp.replace(self._path)

    # ---------- chats ----------

    def create(self, title: str) -> Chat:
        chat = Chat(title=title)
        if available():
            with connection() as conn:
                conn.execute("INSERT INTO chats (id, title, updated_at) VALUES (%s, %s, %s)", (chat.id, chat.title, chat.updated_at))
            return chat
        with self._lock:
            self._chats[chat.id] = chat
            self._save()
        return chat

    def get(self, chat_id: str) -> Chat | None:
        if available():
            with connection() as conn:
                chat_row = conn.execute("SELECT id, title, updated_at FROM chats WHERE id = %s", (chat_id,)).fetchone()
                if not chat_row:
                    return None
                rows = conn.execute(
                    "SELECT id, role, content, created_at, attachments, model, duration_ms, steps, sources, files, error "
                    "FROM messages WHERE chat_id = %s ORDER BY created_at", (chat_id,)
                ).fetchall()
            return Chat(
                id=chat_row[0], title=chat_row[1], updated_at=chat_row[2],
                messages=[Message(id=r[0], role=r[1], content=r[2], created_at=r[3], attachments=r[4],
                                  model=r[5], duration_ms=r[6], steps=r[7], sources=r[8], files=r[9], error=r[10])
                          for r in rows],
            )
        return self._chats.get(chat_id)

    def list_all(self, query: str = "") -> list[Chat]:
        if available():
            with connection() as conn:
                rows = conn.execute(
                    "SELECT id, title, updated_at FROM chats WHERE title ILIKE %s ORDER BY updated_at DESC",
                    (f"%{query.strip()}%",),
                ).fetchall()
            return [Chat(id=r[0], title=r[1], updated_at=r[2]) for r in rows]
        q = query.lower().strip()
        chats = [c for c in self._chats.values() if q in c.title.lower()]
        return sorted(chats, key=lambda c: c.updated_at, reverse=True)

    def add_message(self, chat_id: str, message: Message) -> None:
        if available():
            with connection() as conn:
                conn.execute(
                    "INSERT INTO messages (id, chat_id, role, content, created_at, attachments, model, duration_ms, steps, sources, files, error) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (message.id, chat_id, message.role, message.content, message.created_at, Json(message.attachments),
                     Json(message.model), message.duration_ms, Json(message.steps), Json(message.sources), Json(message.files), message.error),
                )
                conn.execute("UPDATE chats SET updated_at = %s WHERE id = %s", (now(), chat_id))
            return
        with self._lock:
            chat = self._chats[chat_id]
            chat.messages.append(message)
            chat.updated_at = now()
            self._save()

    def rename(self, chat_id: str, title: str) -> bool:
        if available():
            with connection() as conn:
                result = conn.execute("UPDATE chats SET title = %s, updated_at = %s WHERE id = %s", (title, now(), chat_id))
            return result.rowcount > 0
        with self._lock:
            chat = self._chats.get(chat_id)
            if not chat:
                return False
            chat.title = title
            self._save()
        return True

    def delete(self, chat_id: str) -> bool:
        if available():
            with connection() as conn:
                result = conn.execute("DELETE FROM chats WHERE id = %s", (chat_id,))
            return result.rowcount > 0
        with self._lock:
            if self._chats.pop(chat_id, None) is None:
                return False
            self._save()
        return True

    def update_message_files(self, chat_id: str, message_id: str, files: list[dict]) -> None:
        if available():
            with connection() as conn:
                conn.execute("UPDATE messages SET files = %s WHERE chat_id = %s AND id = %s", (Json(files), chat_id, message_id))
            return
        with self._lock:
            chat = self._chats.get(chat_id)
            if not chat:
                return
            for message in chat.messages:
                if message.id == message_id:
                    message.files = files
                    self._save()
                    return


chat_store = ChatStore()