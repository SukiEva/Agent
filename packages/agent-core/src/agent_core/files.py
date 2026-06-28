from __future__ import annotations

import json
from pathlib import Path

from agent_core.ids import new_id
from agent_core.schemas.files import FileRef


class LocalFileStore:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    async def put_bytes(self, name: str, content: bytes, mime_type: str | None = None) -> FileRef:
        file_id = new_id("file")
        file_dir = self._root / file_id
        file_dir.mkdir(parents=False, exist_ok=False)
        content_path = file_dir / "content"
        metadata_path = file_dir / "metadata.json"
        content_path.write_bytes(content)
        ref = FileRef(file_id=file_id, name=name, mime_type=mime_type, size_bytes=len(content))
        metadata_path.write_text(ref.model_dump_json(), encoding="utf-8")
        return ref

    async def read_bytes(self, file_id: str) -> bytes:
        return self._content_path(file_id).read_bytes()

    async def get_ref(self, file_id: str) -> FileRef | None:
        metadata_path = self._metadata_path(file_id)
        if not metadata_path.exists():
            return None
        return FileRef(**json.loads(metadata_path.read_text(encoding="utf-8")))

    def _content_path(self, file_id: str) -> Path:
        return self._safe_file_dir(file_id) / "content"

    def _metadata_path(self, file_id: str) -> Path:
        return self._safe_file_dir(file_id) / "metadata.json"

    def _safe_file_dir(self, file_id: str) -> Path:
        if "/" in file_id or "\\" in file_id or file_id in {"", ".", ".."}:
            raise ValueError("invalid file_id")
        path = self._root / file_id
        if not path.is_dir():
            raise FileNotFoundError(file_id)
        return path


def build_file_store(settings: dict[str, object], cwd: Path | None = None) -> LocalFileStore:
    file_settings = settings.get("files", {})
    if not isinstance(file_settings, dict):
        file_settings = {}
    root_value = str(file_settings.get("local_root", ".data/files"))
    root = Path(root_value)
    if not root.is_absolute():
        root = (cwd or Path.cwd()) / root
    return LocalFileStore(root)
