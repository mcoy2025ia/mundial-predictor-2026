import json

import scripts.run_upset_agent as runner


def _write_cache(path, winner):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"upsets": [{"home": "France", "away": "Spain", "predicted_winner": winner}]}),
        encoding="utf-8",
    )


def test_load_existing_uses_published_cache_in_clean_checkout(tmp_path, monkeypatch):
    processed = tmp_path / "processed" / "upset_predictions.json"
    published = tmp_path / "public" / "upset_predictions.json"
    _write_cache(published, "Spain")
    monkeypatch.setattr(runner, "OUT_PATH", processed)
    monkeypatch.setattr(runner, "OUT_FRONTEND", published)

    assert runner._load_existing()[0]["predicted_winner"] == "Spain"


def test_load_existing_merges_caches_and_published_wins(tmp_path, monkeypatch):
    processed = tmp_path / "processed" / "upset_predictions.json"
    published = tmp_path / "public" / "upset_predictions.json"
    _write_cache(processed, "France")
    _write_cache(published, "Spain")
    monkeypatch.setattr(runner, "OUT_PATH", processed)
    monkeypatch.setattr(runner, "OUT_FRONTEND", published)

    existing = runner._load_existing()

    assert len(existing) == 1
    assert existing[0]["predicted_winner"] == "Spain"
