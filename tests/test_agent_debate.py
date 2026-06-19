from src.agent_debate import AgentDebateSystem


def test_parse_predictions_new_format_limits_to_top_two():
    consensus = """
An?lisis final.
RESULTADO_JSON: {"predictions": [
  {"home_goals": 2, "away_goals": 1, "probability": 0.31},
  {"home_goals": 1, "away_goals": 1, "probability": 0.24},
  {"home_goals": 3, "away_goals": 2, "probability": 0.10}
]}
"""

    predictions = AgentDebateSystem.parse_predictions(consensus)

    assert len(predictions) == 2
    assert predictions[0] == {
        "home_goals": 2,
        "away_goals": 1,
        "probability": 0.31,
        "predicted_winner": "home",
    }
    assert predictions[1]["predicted_winner"] == "draw"


def test_parse_predictions_legacy_single_prediction():
    consensus = 'RESULTADO_JSON: {"home_goals": 0, "away_goals": 1, "probability": 0.22}'

    predictions = AgentDebateSystem.parse_predictions(consensus)

    assert len(predictions) == 1
    assert predictions[0]["predicted_winner"] == "away"
    assert AgentDebateSystem.parse_top_prediction(consensus) == predictions[0]


def test_parse_predictions_rejects_non_list_predictions():
    consensus = 'RESULTADO_JSON: {"predictions": {"home_goals": 1, "away_goals": 0}}'

    assert AgentDebateSystem.parse_predictions(consensus) == []
