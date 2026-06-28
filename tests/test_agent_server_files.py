from __future__ import annotations

import os
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient


def test_file_upload_endpoint() -> None:
    with TemporaryDirectory() as directory:
        os.environ["AGENT_FILE_STORE_ROOT"] = directory
        from agent_server.main import create_app

        client = TestClient(create_app())
        response = client.post(
            "/api/files",
            files={"file": ("example.txt", b"hello", "text/plain")},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["file_id"].startswith("file_")
        assert payload["name"] == "example.txt"
        assert payload["mime_type"] == "text/plain"
        assert payload["size_bytes"] == 5


if __name__ == "__main__":
    test_file_upload_endpoint()
    print("agent server file endpoint tests ok")
