import json

import scripts.run_knockout_oracle as runner


def _write_cache(path, matches):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"matches": matches}), encoding="utf-8")


def test_load_existing_merges_local_and_published_oracle_cache(tmp_path, monkeypatch):
    processed = tmp_path / "processed" / "knockout_oracle_predictions.json"
    published = tmp_path / "public" / "knockout_oracle_predictions.json"
    _write_cache(processed, [{"home": "France", "away": "Spain", "version": "local"}])
    _write_cache(
        published,
        [
            {"home": "France", "away": "Spain", "version": "published"},
            {"home": "England", "away": "Argentina", "version": "published"},
        ],
    )
    monkeypatch.setattr(runner, "OUT_PATH", processed)
    monkeypatch.setattr(runner, "OUT_FRONTEND", published)

    existing = runner._load_existing()
    by_pair = {frozenset({entry["home"], entry["away"]}): entry for entry in existing}

    assert len(existing) == 2
    assert by_pair[frozenset({"France", "Spain"})]["version"] == "published"
