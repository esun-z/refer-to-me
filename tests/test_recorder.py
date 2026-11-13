"""JSONL dataset recorder."""

import json

from refer_to_me.core.recorder import Recorder


def record(i: int) -> dict:
    return {
        "schema_version": 1,
        "record_id": f"r{i}",
        "message_text": "下周月例会改到周四",
        "questions": {"t1": {"type": "noul", "instructions": "与月例会有关？"}},
        "answers": {"t1": {"noul": 0.9, "confidence": 0.9}},
        "human_label": None,
    }


def test_append_single_line_chinese(tmp_path):
    rec = Recorder(tmp_path / "data" / "laya_dataset.jsonl")
    assert rec.append(record(1)) is True
    lines = rec.path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert "月例会" in lines[0]  # ensure_ascii=False
    parsed = json.loads(lines[0])
    assert parsed["human_label"] is None
    assert parsed["answers"]["t1"]["noul"] == 0.9


def test_append_multiple(tmp_path):
    rec = Recorder(tmp_path / "d.jsonl")
    for i in range(3):
        assert rec.append(record(i))
    lines = rec.path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    assert [json.loads(line)["record_id"] for line in lines] == ["r0", "r1", "r2"]


def test_write_failure_returns_false(tmp_path):
    # path whose parent is a file -> mkdir/open fails
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    rec = Recorder(blocker / "sub" / "d.jsonl")
    assert rec.append(record(1)) is False
