"""LLM calls para agentes especialistas.

Proveedor principal: DeepSeek (OpenAI-compatible, base_url=https://api.deepseek.com).
Fallback: Anthropic Claude si DEEPSEEK_API_KEY no está configurada.
Token-stripping: payload JSON denso sin historial conversacional.
Integrado con CostGuard: verifica límites antes de llamar.

Auto-carga DEEPSEEK_API_KEY y ANTHROPIC_API_KEY desde frontend/.env.local o .env
si no están ya en el entorno (igual que update_wc_results.py con FOOTBALL_DATA_TOKEN).
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

def _load_env_file() -> None:
    """Carga variables de entorno desde .env / frontend/.env.local si no están en el entorno."""
    _KEYS = ("DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY")
    _ROOT = Path(__file__).resolve().parent.parent.parent.parent  # specialists→agents→src→root
    # Verify: if no .env or frontend/ found, go up one more (handles editable installs)
    if not (_ROOT / "frontend").exists() and (_ROOT.parent / "frontend").exists():
        _ROOT = _ROOT.parent
    for env_path in [_ROOT / ".env", _ROOT / "frontend" / ".env.local"]:
        if not env_path.exists():
            continue
        try:
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if "=" not in line or line.startswith("#"):
                    continue
                k, v = line.split("=", 1)
                k = k.strip(); v = v.strip().strip('"').strip("'")
                if k in _KEYS and not os.environ.get(k):
                    os.environ[k] = v
        except Exception:
            pass

_load_env_file()

logger = logging.getLogger(__name__)

# ── Clientes lazy ──────────────────────────────────────────────────────────────
_deepseek_client: Optional[object] = None
_anthropic_client: Optional[object] = None

_OPENAI_AVAILABLE = False
_ANTHROPIC_AVAILABLE = False

try:
    from openai import OpenAI as _OpenAI  # type: ignore
    _OPENAI_AVAILABLE = True
except ImportError:
    pass

try:
    import anthropic as _anthropic  # type: ignore
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    pass


def _get_deepseek():
    global _deepseek_client
    if _deepseek_client is None:
        key = os.environ.get("DEEPSEEK_API_KEY", "")
        if not key:
            raise RuntimeError("DEEPSEEK_API_KEY no configurada")
        if not _OPENAI_AVAILABLE:
            raise RuntimeError("openai SDK no instalado (pip install openai)")
        _deepseek_client = _OpenAI(api_key=key, base_url="https://api.deepseek.com")
    return _deepseek_client


def _get_anthropic():
    global _anthropic_client
    if _anthropic_client is None:
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY no configurada")
        if not _ANTHROPIC_AVAILABLE:
            raise RuntimeError("anthropic SDK no instalado (pip install anthropic)")
        _anthropic_client = _anthropic.Anthropic(api_key=key)
    return _anthropic_client


# Mapeo de model aliases: los agentes pasan "claude-haiku-4-5" → se redirigen a deepseek
_MODEL_MAP: dict[str, str] = {
    "claude-haiku-4-5-20251001": "deepseek-chat",
    "claude-sonnet-4-6":         "deepseek-chat",
    "claude-fable-5":            "deepseek-chat",
    "claude-opus-4-8":           "deepseek-chat",
}


def call_claude(
    system_prompt: str,
    user_payload: dict,
    model: str = "deepseek-chat",
    max_tokens: int = 512,
    agent_name: str = "",
    match: str = "",
) -> str:
    """Llama al LLM activo (DeepSeek → fallback Claude) y retorna texto.

    Compatible con la firma anterior — los agentes no necesitan cambios.
    """
    from src.cost_guard import BudgetExceeded, get_guard
    guard = get_guard()

    # Normalizar model alias (por si un agente todavía pasa nombre de Claude)
    effective_model = _MODEL_MAP.get(model, model)

    estimated_tokens = (
        len(system_prompt) // 4
        + len(json.dumps(user_payload)) // 4
        + max_tokens
    )
    try:
        guard.check_and_record(effective_model, estimated_tokens,
                               agent_name=agent_name, match=match)
    except BudgetExceeded as e:
        raise RuntimeError(f"CostGuard: {e}") from e

    user_msg = json.dumps(user_payload, ensure_ascii=False)

    # ── Intento 1: DeepSeek ────────────────────────────────────────────────────
    if os.environ.get("DEEPSEEK_API_KEY"):
        try:
            client = _get_deepseek()
            response = client.chat.completions.create(
                model=effective_model,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_msg},
                ],
            )
            text = response.choices[0].message.content or ""
            real_tokens = getattr(response.usage, "total_tokens", estimated_tokens)
            logger.debug("DeepSeek [%s/%s]: %d tokens", agent_name, effective_model, real_tokens)
            return text
        except Exception as exc:
            logger.warning("DeepSeek falló (%s), intentando Claude fallback: %s", effective_model, exc)

    # ── Fallback: Anthropic Claude ─────────────────────────────────────────────
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            claude_model = "claude-haiku-4-5-20251001"
            client = _get_anthropic()
            response = client.messages.create(
                model=claude_model,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_msg}],
            )
            logger.debug("Claude fallback [%s/%s]", agent_name, claude_model)
            return response.content[0].text
        except Exception as exc:
            logger.warning("Claude fallback también falló: %s", exc)

    raise RuntimeError(
        "No hay proveedor LLM disponible. "
        "Configura DEEPSEEK_API_KEY (o ANTHROPIC_API_KEY como fallback)."
    )


def parse_delta_json(text: str) -> dict:
    """Extrae el primer bloque JSON de la respuesta del agente."""
    import re
    m = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    logger.debug("parse_delta_json: no se encontró JSON válido en: %s", text[:200])
    return {}
