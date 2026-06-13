"""Observabilidad JSONL para pipeline runs y live updates.

Cada ejecución de run_pipeline.py o predict_live.py appenda una línea a
logs/pipeline_runs.jsonl. Esto permite auditar cuándo corrió el pipeline,
qué métricas produjo y qué artefactos se generaron.

Formato de cada línea:
{
  "ts":         "2026-06-13T14:30:00+00:00",   # UTC ISO-8601
  "run_type":   "full_pipeline" | "live_update" | "export",
  "duration_s": 42.3,
  "status":     "ok" | "error",
  "error":      null | "mensaje",
  "metrics":    {...},      # vacío si live_update
  "artifacts":  [...],      # paths relativos generados
  "meta":       {...}       # contexto libre (n_train, n_live_results, etc.)
}
"""
from __future__ import annotations

import json
import logging
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator, Optional

ROOT = Path(__file__).parent.parent
LOG_PATH = ROOT / "logs" / "pipeline_runs.jsonl"

logger = logging.getLogger(__name__)


def _rel(path: Path | str) -> str:
    """Convierte a ruta relativa al ROOT para portabilidad."""
    try:
        return str(Path(path).relative_to(ROOT))
    except ValueError:
        return str(path)


def append_run(
    run_type: str,
    duration_s: float,
    status: str = "ok",
    error: Optional[str] = None,
    metrics: Optional[dict] = None,
    artifacts: Optional[list] = None,
    meta: Optional[dict] = None,
) -> None:
    """Appenda una línea JSONL al ledger de runs."""
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "run_type": run_type,
        "duration_s": round(duration_s, 2),
        "status": status,
        "error": error,
        "metrics": metrics or {},
        "artifacts": [_rel(a) for a in (artifacts or [])],
        "meta": meta or {},
    }
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    logger.debug("pipeline_logger: run registrado (%s, %.1fs, %s)", run_type, duration_s, status)


@contextmanager
def run_context(
    run_type: str,
    artifacts: Optional[list] = None,
    meta: Optional[dict] = None,
) -> Generator[dict, None, None]:
    """Context manager que mide tiempo y captura excepciones.

    Uso:
        with run_context("full_pipeline", artifacts=[...], meta={...}) as ctx:
            # ... hacer trabajo ...
            ctx["metrics"] = {"rps": 0.1958}   # añadir métricas en el bloque
    """
    ctx: dict[str, Any] = {"metrics": {}, "artifacts": artifacts or [], "meta": meta or {}}
    t0 = time.monotonic()
    try:
        yield ctx
        duration = time.monotonic() - t0
        append_run(
            run_type=run_type,
            duration_s=duration,
            status="ok",
            metrics=ctx.get("metrics", {}),
            artifacts=ctx.get("artifacts", []),
            meta=ctx.get("meta", {}),
        )
    except Exception as exc:
        duration = time.monotonic() - t0
        append_run(
            run_type=run_type,
            duration_s=duration,
            status="error",
            error=str(exc),
            metrics=ctx.get("metrics", {}),
            artifacts=ctx.get("artifacts", []),
            meta=ctx.get("meta", {}),
        )
        raise


def read_runs(last_n: int = 20) -> list[dict]:
    """Lee los últimos N runs del ledger."""
    if not LOG_PATH.exists():
        return []
    lines = LOG_PATH.read_text(encoding="utf-8").strip().splitlines()
    entries = []
    for line in lines:
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries[-last_n:]


def summary() -> None:
    """Imprime resumen de los últimos 10 runs en stdout."""
    runs = read_runs(10)
    if not runs:
        print("Sin runs registrados en", LOG_PATH)
        return
    print(f"\n{'Timestamp':<28} {'Tipo':<18} {'Dur(s)':>7} {'Estado':<8} {'Métricas'}")
    print("-" * 90)
    for r in runs:
        ts = r.get("ts", "")[:19].replace("T", " ")
        rtype = r.get("run_type", "")[:18]
        dur = r.get("duration_s", 0)
        status = r.get("status", "")
        metrics_str = ", ".join(f"{k}={v}" for k, v in list(r.get("metrics", {}).items())[:3])
        print(f"{ts:<28} {rtype:<18} {dur:>7.1f} {status:<8} {metrics_str}")
