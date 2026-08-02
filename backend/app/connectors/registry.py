"""
Registro de conectores disponibles + rate limiter compartido.

El rate limiter vive aquí (no dentro de cada conector) porque el límite es
por fuente a nivel de TODO el sistema, no por proceso ni por usuario:
si 500 usuarios monitorean la Rama Judicial, seguimos respetando un único
techo de peticiones concurrentes hacia ese portal.
"""
from __future__ import annotations

import asyncio
import time

from app.config import SOURCE_RATE_LIMITS
from app.connectors.base import ConectorFuente
from app.connectors.rama_judicial import ConectorRamaJudicial
from app.connectors.tyba import ConectorTyba

# --- Registro de conectores activos ---
# Para agregar SAMAI, SPOA, Superfinanciera, SIC o despachos: se construye la
# clase en su propio archivo (misma forma que rama_judicial.py) y se agrega
# una línea aquí. Nada más del sistema necesita cambiar.
CONECTORES: dict[str, ConectorFuente] = {
    "rama_judicial": ConectorRamaJudicial(),
    "tyba": ConectorTyba(),
    # "samai": ConectorSamai(),
    # "spoa": ConectorSpoa(),
    # "superfinanciera": ConectorSuperfinanciera(),
    # "sic": ConectorSic(),
}


class RateLimiter:
    """Semáforo + espaciado mínimo entre peticiones, por fuente."""

    def __init__(self) -> None:
        self._semaphores: dict[str, asyncio.Semaphore] = {}
        self._last_request_ts: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        for fuente, cfg in SOURCE_RATE_LIMITS.items():
            self._semaphores[fuente] = asyncio.Semaphore(cfg["max_concurrent"])
            self._locks[fuente] = asyncio.Lock()
            self._last_request_ts[fuente] = 0.0

    async def acquire(self, fuente: str) -> None:
        cfg = SOURCE_RATE_LIMITS[fuente]
        await self._semaphores[fuente].acquire()
        async with self._locks[fuente]:
            elapsed = time.monotonic() - self._last_request_ts[fuente]
            wait = cfg["min_seconds_between_requests"] - elapsed
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request_ts[fuente] = time.monotonic()

    def release(self, fuente: str) -> None:
        self._semaphores[fuente].release()


rate_limiter = RateLimiter()


def get_conector(fuente: str) -> ConectorFuente:
    if fuente not in CONECTORES:
        raise ValueError(f"No hay conector registrado para la fuente '{fuente}'")
    return CONECTORES[fuente]
