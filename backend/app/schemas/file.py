from datetime import datetime

from app.schemas.base import CamelModel


class GeneratedFileOut(CamelModel):
    id: str
    name: str
    type: str
    size: int
    chat_id: str | None = None
    created_at: datetime
