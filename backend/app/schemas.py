from __future__ import annotations

import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, field_validator

RADICADO_REGEX = re.compile(r"^\d{23}$")


class ProcesoCrear(BaseModel):
    radicado: str
    fuente: str = "rama_judicial"
    alias: str | None = None
    cliente: str | None = None
    jurisdiccion: str | None = None
    apoderado_id: UUID | None = None
    tags: list[str] = []

    @field_validator("radicado")
    @classmethod
    def validar_radicado(cls, v: str) -> str:
        v = v.strip().replace(" ", "").replace("-", "")
        if not RADICADO_REGEX.match(v):
            raise ValueError(
                "El radicado debe tener exactamente 23 dígitos numéricos "
                "(departamento+ciudad+entidad+especialidad+despacho+año+consecutivo+instancia)."
            )
        return v


class ProcesoRespuesta(BaseModel):
    id: UUID
    radicado: str
    fuente: str
    alias: str | None
    cliente: str | None
    jurisdiccion: str | None
    activo: bool
    archivado: bool
    tiene_novedades: bool = False

    class Config:
        from_attributes = True


class ActuacionRespuesta(BaseModel):
    id: UUID
    tipo: str
    fecha_actuacion: datetime
    anotacion: str
    despacho: str | None
    documento_url: str | None

    class Config:
        from_attributes = True


class ConsultaRunRespuesta(BaseModel):
    id: UUID
    fuente: str
    estado: str
    intento_numero: int
    actuaciones_nuevas: int
    mensaje_error: str | None
    duracion_ms: int | None
    ejecutado_en: datetime

    class Config:
        from_attributes = True
