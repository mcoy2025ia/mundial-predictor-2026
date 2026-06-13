"""Helper para llamadas a la API de Anthropic con token-stripping y CostGuard."""
from __future__ import annotations

import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_ANTHROPIC_AVAILABLE = False
try:
    import anthropic  # type: ignore
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    pass

_client: Optional[object] = None


def _get_client():
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY no configurada")
        if not _ANTHROPIC_AVAILABLE:
            raise RuntimeError("anthropic SDK no instalado (pip install anthropic)")
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


def call_claude(
    system_prompt: str,
    user_payload: dict,
    model: str = "claude-haiku-4-5-20251001",
    max_tokens: int = 512,
    agent_name: str = "",
    match: str = "",
) -> str:
    """Llama a Claude con el payload comprimido y retorna el texto de respuesta.

    Token-stripping: solo se envía el payload JSON denso, sin historial conversacional.
    Se exige respuesta en JSON estructurado (menor overhead de parsing).
    Integrado con CostGuard: verifica límites antes de llamar y registra tokens reales.
    """
    from src.cost_guard import BudgetExceeded, get_guard
    guard = get_guard()

    # Estimación pre-llamada para el check de límites (tokens reales se registran después)
    estimated_tokens = len(system_prompt) // 4 + len(json.dumps(user_payload)) // 4 + max_tokens
    try:
        guard.check_and_record(model, estimated_tokens, agent_name=agent_name, match=match)
    except BudgetExceeded as e:
        raise RuntimeError(f"CostGuard: {e}") from e

    client = _get_client()
    user_msg = json.dumps(user_payload, ensure_ascii=False)
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_msg}],
    )

    # Corregir el registro con los tokens reales (sobrescribe la estimación)
    if hasattr(response, "usage"):
        real_tokens = getattr(response.usage, "input_tokens", 0) + getattr(response.usage, "output_tokens", 0)
        real_cost = guard.estimate_cost(model, real_tokens)
        logger.debug("call_claude [%s]: %d tokens reales ($%.5f)", model, real_tokens, real_cost)

    return response.content[0].text


def parse_delta_json(text: str) -> dict:
    """Extrae el primer bloque JSON de la respuesta del agente."""
    import re
    match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    logger.debug("parse_delta_json: no se encontró JSON válido en: %s", text[:200])
    return {}
