from pydantic import BaseModel


class FileRef(BaseModel):
    file_id: str
    name: str
    mime_type: str | None = None
    size_bytes: int | None = None
