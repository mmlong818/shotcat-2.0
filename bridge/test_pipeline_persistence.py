from __future__ import annotations

import json
import sys
from pathlib import Path


BRIDGE_DIR = Path(__file__).resolve().parent
if str(BRIDGE_DIR) not in sys.path:
    sys.path.insert(0, str(BRIDGE_DIR))

import pipeline_server


def test_load_jobs_preserves_confirmation_and_marks_interrupted_processes(tmp_path: Path, monkeypatch) -> None:
    jobs_file = tmp_path / "pipeline-jobs.json"
    jobs_file.write_text(json.dumps({
        "running": {"status": "running", "pid": "p1", "step": "visual-dict"},
        "confirm": {"status": "awaiting_confirmation", "pid": "p1", "step": "shot-breakdown"},
        "done": {"status": "done", "pid": "p1", "step": "unit-gen"},
    }), encoding="utf-8")
    monkeypatch.setattr(pipeline_server, "JOBS_FILE", jobs_file)

    loaded = pipeline_server._load_jobs()

    assert loaded["running"]["status"] == "error"
    assert "中断" in loaded["running"]["error"]
    assert loaded["confirm"]["status"] == "awaiting_confirmation"
    assert loaded["done"]["status"] == "done"


def test_persist_jobs_replaces_file_atomically(tmp_path: Path, monkeypatch) -> None:
    jobs_file = tmp_path / "pipeline-jobs.json"
    monkeypatch.setattr(pipeline_server, "JOBS_FILE", jobs_file)
    monkeypatch.setattr(pipeline_server, "JOBS", {"job-1": {"status": "queued", "pid": "p1"}})

    pipeline_server._persist_jobs_locked()

    assert json.loads(jobs_file.read_text(encoding="utf-8"))["job-1"]["status"] == "queued"
    assert not jobs_file.with_suffix(".tmp").exists()
