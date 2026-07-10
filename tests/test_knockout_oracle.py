"""Tests de parsing y validación del Oráculo de Eliminatorias.

No tocan la API de DeepSeek: ejercitan solo la coacción de coherencia
90'↔prórroga↔penales↔clasificado, que es el contrato crítico (nunca dejar la
llave sin un equipo que avanza).
"""
from src.knockout_oracle import KnockoutOracle, ORACLE_ROUNDS

HOME, AWAY = "Spain", "Belgium"


def _verdict(json_body: str) -> dict:
    return KnockoutOracle.parse_verdict(f"Análisis.\nRESULTADO_JSON: {json_body}", HOME, AWAY)


def test_winner_in_90_forces_no_extra_time():
    v = _verdict(
        '{"agente": "Tactical Scout", "marcador_90_minutos": {"equipo_local": 2, "equipo_visitante": 0},'
        ' "habra_tiempo_extra": true, "marcador_120_minutos": {"equipo_local": 3, "equipo_visitante": 1},'
        ' "habra_penaltis": true, "resultado_penaltis": {"equipo_local": 5, "equipo_visitante": 4},'
        ' "equipo_clasificado": "Belgium", "fase_de_definicion": "penaltis", "conviccion": "alta",'
        ' "explicacion": "..."}'
    )
    # Ganó el local en 90' → se anula toda la parafernalia de prórroga/penales.
    assert v["valido"] is True
    assert v["habra_tiempo_extra"] is False
    assert v["marcador_120_minutos"] is None
    assert v["habra_penaltis"] is False
    assert v["resultado_penaltis"] is None
    assert v["fase_de_definicion"] == "90_minutos"
    assert v["equipo_clasificado"] == HOME
    assert v["predicted_winner"] == "home"


def test_draw_in_90_requires_extra_time():
    v = _verdict(
        '{"marcador_90_minutos": {"equipo_local": 1, "equipo_visitante": 1},'
        ' "habra_tiempo_extra": false, "marcador_120_minutos": {"equipo_local": 2, "equipo_visitante": 1},'
        ' "equipo_clasificado": "Spain", "fase_de_definicion": "90_minutos", "conviccion": "media",'
        ' "explicacion": "..."}'
    )
    # Empate en 90' → prórroga obligatoria; gana el local en la prórroga.
    assert v["habra_tiempo_extra"] is True
    assert v["fase_de_definicion"] == "tiempo_extra"
    assert v["marcador_120_minutos"] == {"equipo_local": 2, "equipo_visitante": 1}
    assert v["habra_penaltis"] is False
    assert v["equipo_clasificado"] == HOME


def test_draw_after_120_goes_to_penalties():
    v = _verdict(
        '{"marcador_90_minutos": {"equipo_local": 1, "equipo_visitante": 1},'
        ' "habra_tiempo_extra": true, "marcador_120_minutos": {"equipo_local": 2, "equipo_visitante": 2},'
        ' "habra_penaltis": true, "resultado_penaltis": {"equipo_local": 3, "equipo_visitante": 5},'
        ' "equipo_clasificado": "Belgium", "fase_de_definicion": "penaltis", "conviccion": "baja",'
        ' "explicacion": "..."}'
    )
    assert v["habra_penaltis"] is True
    assert v["fase_de_definicion"] == "penaltis"
    assert v["resultado_penaltis"] == {"equipo_local": 3, "equipo_visitante": 5}
    assert v["equipo_clasificado"] == AWAY
    assert v["predicted_winner"] == "away"


def test_draw_120_but_no_penalty_score_uses_named_winner():
    v = _verdict(
        '{"marcador_90_minutos": {"equipo_local": 0, "equipo_visitante": 0},'
        ' "habra_tiempo_extra": true, "marcador_120_minutos": {"equipo_local": 1, "equipo_visitante": 1},'
        ' "habra_penaltis": true, "resultado_penaltis": null,'
        ' "equipo_clasificado": "Spain", "fase_de_definicion": "penaltis", "conviccion": "media",'
        ' "explicacion": "..."}'
    )
    # Sin marcador de penales pero con clasificado nombrado → se sintetiza una tanda coherente.
    assert v["valido"] is True
    assert v["habra_penaltis"] is True
    assert v["equipo_clasificado"] == HOME
    assert v["resultado_penaltis"]["equipo_local"] > v["resultado_penaltis"]["equipo_visitante"]


def test_penalties_without_winner_or_named_team_is_invalid():
    v = _verdict(
        '{"marcador_90_minutos": {"equipo_local": 0, "equipo_visitante": 0},'
        ' "habra_tiempo_extra": true, "marcador_120_minutos": {"equipo_local": 1, "equipo_visitante": 1},'
        ' "habra_penaltis": true, "resultado_penaltis": null, "equipo_clasificado": "Nadie",'
        ' "fase_de_definicion": "penaltis", "conviccion": "media", "explicacion": "..."}'
    )
    assert v["valido"] is False
    assert v["equipo_clasificado"] is None


def test_missing_json_block_is_invalid():
    v = KnockoutOracle.parse_verdict("Solo texto, sin bloque de resultado.", HOME, AWAY, fallback_agent="Consenso")
    assert v["valido"] is False
    assert v["agente"] == "Consenso"


def test_malformed_json_is_invalid():
    v = _verdict('{"marcador_90_minutos": {"equipo_local": 2 "equipo_visitante": 1}}')
    assert v["valido"] is False


def test_invalid_conviction_defaults_to_media():
    v = _verdict(
        '{"marcador_90_minutos": {"equipo_local": 3, "equipo_visitante": 1},'
        ' "equipo_clasificado": "Spain", "conviccion": "altísima", "explicacion": "..."}'
    )
    assert v["conviccion"] == "media"


def test_oracle_rounds_are_late_stage_only():
    assert ORACLE_ROUNDS == {"Quarter-final", "Semi-final", "Final", "Match for third place"}
    assert "Round of 16" not in ORACLE_ROUNDS
    assert "Round of 32" not in ORACLE_ROUNDS
