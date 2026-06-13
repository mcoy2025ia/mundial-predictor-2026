"""Tests para pipeline_logger — observabilidad JSONL."""
import json
import time
from contextlib import contextmanager
from pathlib import Path

import pytest

import sys
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import src.pipeline_logger as pl


@contextmanager
def _tmp_logger(tmp_path: Path):
    """Parchea LOG_PATH a un directorio temporal."""
    original = pl.LOG_PATH
    pl.LOG_PATH = tmp_path / "runs.jsonl"
    try:
        yield pl.LOG_PATH
    finally:
        pl.LOG_PATH = original


# ---------------------------------------------------------------------------
# append_run
# ---------------------------------------------------------------------------

def test_append_run_creates_file(tmp_path):
    with _tmp_logger(tmp_path):
        pl.append_run("full_pipeline", duration_s=5.0)
    log = tmp_path / "runs.jsonl"
    assert log.exists()
    entries = [json.loads(l) for l in log.read_text().strip().splitlines()]
    assert len(entries) == 1
    assert entries[0]["run_type"] == "full_pipeline"
    assert entries[0]["status"] == "ok"
    assert entries[0]["duration_s"] == 5.0


def test_append_run_error_status(tmp_path):
    with _tmp_logger(tmp_path):
        pl.append_run("live_update", duration_s=1.0, status="error", error="ValueError: test")
    log = tmp_path / "runs.jsonl"
    entry = json.loads(log.read_text().strip())
    assert entry["status"] == "error"
    assert "ValueError" in entry["error"]


def test_append_run_metrics_stored(tmp_path):
    with _tmp_logger(tmp_path):
        pl.append_run("full_pipeline", duration_s=3.0, metrics={"rps": 0.1958, "n_train": 41635})
    entry = json.loads((tmp_path / "runs.jsonl").read_text().strip())
    assert entry["metrics"]["rps"] == 0.1958
    assert entry["metrics"]["n_train"] == 41635


def test_append_run_artifacts_relative(tmp_path):
    with _tmp_logger(tmp_path):
        pl.append_run("export", duration_s=2.0, artifacts=[
            ROOT / "data" / "processed" / "features.parquet"
        ])
    entry = json.loads((tmp_path / "runs.jsonl").read_text().strip())
    assert any("features.parquet" in a for a in entry["artifacts"])
    # Debe ser relativo, no absoluto
    assert not any(a.startswith("C:") or a.startswith("/") for a in entry["artifacts"])


def test_multiple_appends(tmp_path):
    with _tmp_logger(tmp_path):
        pl.append_run("full_pipeline", duration_s=10.0)
        pl.append_run("live_update", duration_s=2.0)
        pl.append_run("export", duration_s=1.5)
    lines = (tmp_path / "runs.jsonl").read_text().strip().splitlines()
    assert len(lines) == 3


# ---------------------------------------------------------------------------
# run_context
# ---------------------------------------------------------------------------

def test_run_context_ok(tmp_path):
    with _tmp_logger(tmp_path):
        with pl.run_context("full_pipeline") as ctx:
            ctx["metrics"] = {"rps": 0.1958}
    entry = json.loads((tmp_path / "runs.jsonl").read_text().strip())
    assert entry["status"] == "ok"
    assert entry["metrics"]["rps"] == 0.1958
    assert entry["duration_s"] >= 0


def test_run_context_captures_exception(tmp_path):
    with _tmp_logger(tmp_path):
        with pytest.raises(RuntimeError):
            with pl.run_context("full_pipeline"):
                raise RuntimeError("pipeline failure")
    entry = json.loads((tmp_path / "runs.jsonl").read_text().strip())
    assert entry["status"] == "error"
    assert "pipeline failure" in entry["error"]


def test_run_context_duration_measured(tmp_path):
    with _tmp_logger(tmp_path):
        with pl.run_context("live_update"):
            time.sleep(0.05)
    entry = json.loads((tmp_path / "runs.jsonl").read_text().strip())
    assert entry["duration_s"] >= 0.04


# ---------------------------------------------------------------------------
# read_runs
# ---------------------------------------------------------------------------

def test_read_runs_empty(tmp_path):
    with _tmp_logger(tmp_path):
        runs = pl.read_runs()
    assert runs == []


def test_read_runs_returns_last_n(tmp_path):
    with _tmp_logger(tmp_path):
        for i in range(5):
            pl.append_run("full_pipeline", duration_s=float(i))
        runs = pl.read_runs(last_n=3)
    assert len(runs) == 3
    # Último run tiene duration_s=4.0
    assert runs[-1]["duration_s"] == 4.0
