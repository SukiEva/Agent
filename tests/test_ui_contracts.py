from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_demo_result_card_contract_allows_attachment_summaries() -> None:
    schema_path = ROOT / "packages" / "agent-ui-contracts" / "contracts" / "demo.result_card.v1.schema.json"
    schema = json.loads(schema_path.read_text())

    assert schema["additionalProperties"] is False
    attachments = schema["properties"]["attachments"]
    assert attachments["type"] == "array"
    item = attachments["items"]
    assert item["additionalProperties"] is False
    assert item["required"] == ["file_id", "name"]
    assert set(item["properties"]) == {"file_id", "name", "mime_type", "size_bytes"}


if __name__ == "__main__":
    test_demo_result_card_contract_allows_attachment_summaries()
    print("ui contract tests ok")
