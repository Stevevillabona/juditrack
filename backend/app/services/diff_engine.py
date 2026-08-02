"""
Motor de detección de cambios.

Compara la lista de ActuacionCruda que devolvió un conector contra las
Actuacion ya guardadas en base de datos para ese proceso, a nivel de
actuación individual (no "algo cambió" a nivel de proceso completo).

Reglas:
- Una actuación es "nueva" si su fingerprint no existe ya en BD.
- Nunca se modifica ni se borra una Actuacion existente (historial inmutable).
- Cambios de despacho/ponente en el proceso (no en una actuación puntual) se
  detectan comparando los metadatos actuales contra los del último estado
  conocido y se reportan como un tipo especial de "novedad".
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from app.connectors.base import ActuacionCruda, MetadatosProceso


def fingerprint_actuacion(a: ActuacionCruda) -> str:
    raw = f"{a.tipo}|{a.fecha_actuacion.isoformat()}|{a.anotacion}".strip().lower()
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass
class CambioDetectado:
    tipo: str  # 'nueva_actuacion', 'cambio_despacho', 'cambio_ponente', 'nueva_audiencia'
    detalle: str
    actuacion: ActuacionCruda | None = None


@dataclass
class ResultadoDiff:
    actuaciones_nuevas: list[ActuacionCruda]
    cambios: list[CambioDetectado]

    @property
    def hay_novedades(self) -> bool:
        return bool(self.actuaciones_nuevas or self.cambios)


def calcular_diff(
    actuaciones_previas_fingerprints: set[str],
    actuaciones_nuevas_crudas: list[ActuacionCruda],
    metadatos_previos: MetadatosProceso | None,
    metadatos_actuales: MetadatosProceso | None,
) -> ResultadoDiff:
    nuevas: list[ActuacionCruda] = []
    cambios: list[CambioDetectado] = []

    for a in actuaciones_nuevas_crudas:
        fp = fingerprint_actuacion(a)
        if fp not in actuaciones_previas_fingerprints:
            nuevas.append(a)
            if a.fecha_audiencia is not None:
                cambios.append(
                    CambioDetectado(
                        tipo="nueva_audiencia",
                        detalle=f"Nueva fecha de audiencia: {a.fecha_audiencia.isoformat()}",
                        actuacion=a,
                    )
                )

    if metadatos_previos and metadatos_actuales:
        if (
            metadatos_previos.despacho
            and metadatos_actuales.despacho
            and metadatos_previos.despacho != metadatos_actuales.despacho
        ):
            cambios.append(
                CambioDetectado(
                    tipo="cambio_despacho",
                    detalle=f"El proceso pasó de '{metadatos_previos.despacho}' a '{metadatos_actuales.despacho}'.",
                )
            )

    return ResultadoDiff(actuaciones_nuevas=nuevas, cambios=cambios)
