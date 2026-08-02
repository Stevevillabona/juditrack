"""
Modelo de datos. Puntos de diseño clave:

- `Actuacion` es INSERT-only: nunca se actualiza ni se borra una fila existente,
  solo se agregan nuevas. Así el historial es inmutable y auditable.
- `Proceso.estado_hash` guarda un hash del último set de actuaciones conocidas,
  para que el diff engine no tenga que releer todo el historial en cada corrida.
- `Proceso.visto_hasta` (por usuario, ver `ProcesoVisto`) separa "novedad desde
  la última consulta automática" de "novedad desde que el usuario lo vio",
  que el spec pide como dos cosas distintas.
- `ConsultaRun` es el registro de auditoría de cada intento de consulta,
  exitoso o fallido, visible al usuario (no es una caja negra).
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, Enum, ForeignKey, Index, String, Text, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class RolUsuario(str, enum.Enum):
    admin = "admin"
    abogado = "abogado"
    asistente = "asistente"


class Firma(Base):
    """Cuenta de equipo (tenant). Un usuario individual también vive dentro
    de una Firma de un solo miembro, para no duplicar el modelo de permisos."""
    __tablename__ = "firmas"

    id: Mapped[uuid.UUID] = uuid_pk()
    nombre: Mapped[str] = mapped_column(String(200))
    plan: Mapped[str] = mapped_column(String(50), default="free")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    usuarios: Mapped[list["Usuario"]] = relationship(back_populates="firma")
    procesos: Mapped[list["Proceso"]] = relationship(back_populates="firma")


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[uuid.UUID] = uuid_pk()
    firma_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("firmas.id"))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    nombre: Mapped[str] = mapped_column(String(200))
    rol: Mapped[RolUsuario] = mapped_column(Enum(RolUsuario), default=RolUsuario.abogado)
    two_factor_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    two_factor_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    firma: Mapped[Firma] = relationship(back_populates="usuarios")


class Proceso(Base):
    __tablename__ = "procesos"
    __table_args__ = (
        UniqueConstraint("firma_id", "radicado", "fuente", name="uq_proceso_por_firma"),
        Index("ix_procesos_radicado", "radicado"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    firma_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("firmas.id"))
    radicado: Mapped[str] = mapped_column(String(23))  # 23 dígitos, validado en schemas.py
    fuente: Mapped[str] = mapped_column(String(50))  # 'rama_judicial', 'samai', 'spoa', ...

    alias: Mapped[str | None] = mapped_column(String(200), nullable=True)
    cliente: Mapped[str | None] = mapped_column(String(200), nullable=True)
    jurisdiccion: Mapped[str | None] = mapped_column(String(100), nullable=True)
    apoderado_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSONB, default=list)

    # Metadatos que trae la fuente (despacho, tipo de proceso, partes, etc.)
    metadatos: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Reglas de notificación específicas de este proceso (si no se configuran,
    # se hereda el default: avisar de todo, por email).
    notificar_canales: Mapped[list[str]] = mapped_column(JSONB, default=lambda: ["email"])
    avisar_todo: Mapped[bool] = mapped_column(Boolean, default=True)
    tipos_permitidos: Mapped[list[str]] = mapped_column(JSONB, default=list)

    estado_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    archivado: Mapped[bool] = mapped_column(Boolean, default=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)  # pausado = False

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    firma: Mapped[Firma] = relationship(back_populates="procesos")
    actuaciones: Mapped[list["Actuacion"]] = relationship(
        back_populates="proceso", order_by="Actuacion.fecha_actuacion", lazy="selectin"
    )


class Actuacion(Base):
    """INSERT-only. Cada fila es una actuación tal como la reportó la fuente
    en el momento en que se detectó por primera vez."""
    __tablename__ = "actuaciones"
    __table_args__ = (
        UniqueConstraint("proceso_id", "fingerprint", name="uq_actuacion_fingerprint"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    proceso_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("procesos.id"))

    # Hash del contenido normalizado de la actuación (fecha+tipo+anotación+despacho...)
    # Sirve para detectar duplicados exactos al re-consultar la fuente.
    fingerprint: Mapped[str] = mapped_column(String(64))

    tipo: Mapped[str] = mapped_column(String(100))  # 'auto', 'sentencia', 'notificación', etc.
    fecha_actuacion: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    anotacion: Mapped[str] = mapped_column(Text)
    despacho: Mapped[str | None] = mapped_column(String(300), nullable=True)
    ponente: Mapped[str | None] = mapped_column(String(200), nullable=True)
    fecha_audiencia: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    documento_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    detectada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    proceso: Mapped[Proceso] = relationship(back_populates="actuaciones")


class ProcesoVisto(Base):
    """Marca de lectura por usuario: separa 'novedad desde última consulta
    automática' de 'novedad desde que ESTE usuario lo vio'."""
    __tablename__ = "procesos_vistos"
    __table_args__ = (UniqueConstraint("proceso_id", "usuario_id", name="uq_visto"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    proceso_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("procesos.id"))
    usuario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuarios.id"))
    visto_hasta: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EstadoRun(str, enum.Enum):
    ok = "ok"
    sin_cambios = "sin_cambios"
    error_temporal = "error_temporal"  # captcha, bloqueo, timeout -> se reintentará
    error_permanente = "error_permanente"  # radicado no existe, formato inválido


class ConsultaRun(Base):
    """Registro de auditoría de CADA intento de consulta a una fuente.
    Esto es lo que el usuario ve en 'qué se consultó, cuándo, con qué resultado'."""
    __tablename__ = "consulta_runs"

    id: Mapped[uuid.UUID] = uuid_pk()
    proceso_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("procesos.id"))
    fuente: Mapped[str] = mapped_column(String(50))
    estado: Mapped[EstadoRun] = mapped_column(Enum(EstadoRun))
    intento_numero: Mapped[int] = mapped_column(default=1)
    actuaciones_nuevas: Mapped[int] = mapped_column(default=0)
    mensaje_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    duracion_ms: Mapped[int | None] = mapped_column(nullable=True)
    ejecutado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class Notificacion(Base):
    __tablename__ = "notificaciones"

    id: Mapped[uuid.UUID] = uuid_pk()
    usuario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuarios.id"))
    proceso_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("procesos.id"), nullable=True)
    canal: Mapped[str] = mapped_column(String(20))  # email, web_push, sms, whatsapp
    asunto: Mapped[str] = mapped_column(String(300))
    cuerpo: Mapped[str] = mapped_column(Text)
    enviada: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class AccessLog(Base):
    """Trazabilidad: quién vio qué proceso y cuándo."""
    __tablename__ = "access_log"

    id: Mapped[uuid.UUID] = uuid_pk()
    usuario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuarios.id"))
    proceso_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("procesos.id"))
    accion: Mapped[str] = mapped_column(String(50))  # 'ver', 'exportar', 'editar'
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
