"""
Interfaz común de conectores.

Cada fuente oficial (Rama Judicial, SAMAI, SPOA, Superfinanciera, SIC,
publicaciones por despacho) implementa esta interfaz. El motor de monitoreo
(tasks/scheduler.py) solo conoce este contrato, nunca los detalles de cada
portal. Así se puede reparar o agregar una fuente sin tocar las demás.

IMPORTANTE: toda la lógica de estos conectores corre en el backend (aquí),
nunca en el navegador del cliente. El frontend solo llama a la API propia.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class ResultadoConsulta(str, Enum):
    OK = "ok"
    RADICADO_NO_ENCONTRADO = "radicado_no_encontrado"
    BLOQUEADO_O_CAPTCHA = "bloqueado_o_captcha"
    ERROR_TEMPORAL = "error_temporal"  # timeout, 5xx, HTML cambió de forma recuperable
    FUENTE_CAMBIO_ESTRUCTURA = "fuente_cambio_estructura"  # selector roto -> alerta interna


@dataclass
class ActuacionCruda:
    """Una actuación tal como la devuelve la fuente, sin persistir todavía.
    El diff engine decide si ya existía o es nueva."""
    tipo: str
    fecha_actuacion: datetime
    anotacion: str
    despacho: str | None = None
    ponente: str | None = None
    fecha_audiencia: datetime | None = None
    documento_url: str | None = None


@dataclass
class MetadatosProceso:
    despacho: str | None = None
    tipo_proceso: str | None = None
    clase_proceso: str | None = None
    partes: list[str] = field(default_factory=list)
    fecha_radicacion: datetime | None = None
    extra: dict = field(default_factory=dict)


@dataclass
class RespuestaConsulta:
    resultado: ResultadoConsulta
    metadatos: MetadatosProceso | None = None
    actuaciones: list[ActuacionCruda] = field(default_factory=list)
    mensaje: str | None = None


class ConectorFuente(abc.ABC):
    """Todo conector nuevo hereda de esta clase e implementa `consultar`.

    Ejemplo de cómo se vería el conector #2 (SAMAI) sin tocar el resto
    del sistema:

        class ConectorSamai(ConectorFuente):
            nombre_fuente = "samai"
            async def consultar(self, radicado): ...

    y se registra en connectors/registry.py.
    """

    nombre_fuente: str

    @abc.abstractmethod
    async def consultar(self, radicado: str) -> RespuestaConsulta:
        """Consulta el estado actual de un radicado en la fuente.
        No debe lanzar excepciones para errores esperables (bloqueo, captcha,
        radicado no encontrado): esos casos se comunican vía ResultadoConsulta.
        Solo debe lanzar para errores realmente inesperados."""
        raise NotImplementedError

    @abc.abstractmethod
    def valida_radicado(self, radicado: str) -> bool:
        """Validación de formato específica de la fuente (algunas fuentes
        aceptan solo el radicado de 23 dígitos, otras tienen su propio formato)."""
        raise NotImplementedError
