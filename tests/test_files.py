from __future__ import annotations

import asyncio
from tempfile import TemporaryDirectory
from pathlib import Path

from agent_core.files import LocalFileStore


def test_local_file_store_roundtrip() -> None:
    asyncio.run(_test_local_file_store_roundtrip())


async def _test_local_file_store_roundtrip() -> None:
    with TemporaryDirectory() as directory:
        store = LocalFileStore(Path(directory))
        ref = await store.put_bytes("example.txt", b"hello", "text/plain")
        assert ref.file_id.startswith("file_")
        assert ref.name == "example.txt"
        assert ref.mime_type == "text/plain"
        assert ref.size_bytes == 5
        assert await store.read_bytes(ref.file_id) == b"hello"
        loaded = await store.get_ref(ref.file_id)
        assert loaded == ref
        try:
            await store.read_bytes("../bad")
        except ValueError:
            pass
        else:
            raise AssertionError("path traversal file_id should fail")


if __name__ == "__main__":
    test_local_file_store_roundtrip()
    print("file tests ok")
