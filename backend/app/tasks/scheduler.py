"""
Orquestación del monitoreo automático, con la base de datos ya conectada.

Dos tareas principales:

1. `despachar_consultas_pendientes`: corre cada 15 min (ver celery_app.py),
   encuentra los procesos activos a los que "les toca" consultarse según el
   intervalo de su plan, dentro de la ventana horaria hábil, y encola una
   tarea `consultar_proceso` por cada uno.

2. `consultar_proceso`: la unidad de trabajo real. Llama al conector
   correspondiente respetando el rate limiter compartido, corre el diff
   engine, persiste actuaciones nuevas (insert-only), registra el
   ConsultaRun de auditoría, y dispara notificaciones. Si falla de forma
   recuperable (captcha, timeout), se reintenta con backoff exponencial;
   si se agotan los reintentos, notifica al usuario que la consulta quedó
   pendiente (nunca deja que el silencio se confunda con "sin novedades").
"""
from __future__ import annotations

import asyncio
import time as time_module
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.config import (
    BACKOFF_BASE_SECONDS,
    DEFAULT_MONITORING_WINDOW,
    MAX_RETRIES_PER_RUN,
    PLANS,
)
from app.connectors.base import MetadatosProceso, ResultadoConsulta
from app.connectors.registry import get_conector, rate_limiter
from app.database import SessionLocal
from app.models import Actuacion, ConsultaRun, EstadoRun, Firma, Proceso, RolUsuario, Usuario
from app.services import notifier
from app.services.diff_engine import calcular_diff, fingerprint_actuacion
from app.tasks.celery_app import celery_app


def _dentro_de_ventana_habil(ahora: datetime) -> bool:
    ventana = DEFAULT_MONITORING_WINDOW
    if ventana.business_days_only and ahora.weekday() >= 5:  # sábado=5, domingo=6
        return False
    return ventana.start <= ahora.time() <= ventana.end


@celery_app.task(name="app.tasks.scheduler.despachar_consultas_pendientes")
def despachar_consultas_pendientes() -> None:
    if not _dentro_de_ventana_habil(datetime.now()):
        return
    asyncio.run(_despachar_async())


async def _despachar_async() -> None:
    async with SessionLocal() as db:
        resultado = await db.execute(
            select(Proceso, Firma.plan)
            .join(Firma, Firma.id == Proceso.firma_id)
            .where(Proceso.activo.is_(True), Proceso.archivado.is_(False))
        )
        for proceso, plan in resultado.all():
            intervalo = timedelta(minutes=PLANS[plan].poll_interval_minutes)

            ultima = await db.execute(
                select(ConsultaRun.ejecutado_en)
                .where(ConsultaRun.proceso_id == proceso.id)
                .order_by(ConsultaRun.ejecutado_en.desc())
                .limit(1)
            )
            ultima_ts = ultima.scalar_one_or_none()

            if ultima_ts is None or datetime.now(timezone.utc) - ultima_ts >= intervalo:
                consultar_proceso.delay(str(proceso.id))


def _metadatos_desde_json(data: dict | None) -> MetadatosProceso | None:
    if not data:
        return None
    fecha_txt = data.get("fecha_radicacion")
    return MetadatosProceso(
        despacho=data.get("despacho"),
        tipo_proceso=data.get("tipo_proceso"),
        clase_proceso=data.get("clase_proceso"),
        partes=data.get("partes") or [],
        fecha_radicacion=datetime.fromisoformat(fecha_txt) if fecha_txt else None,
        extra=data.get("extra") or {},
    )


def _metadatos_a_json(m: MetadatosProceso) -> dict:
    return {
        "despacho": m.despacho,
        "tipo_proceso": m.tipo_proceso,
        "clase_proceso": m.clase_proceso,
        "partes": m.partes,
        "fecha_radicacion": m.fecha_radicacion.isoformat() if m.fecha_radicacion else None,
        "extra": m.extra,
    }


class _ErrorRecuperable(Exception):
    pass


@celery_app.task(
    name="app.tasks.scheduler.consultar_proceso",
    bind=True,
    max_retries=MAX_RETRIES_PER_RUN,
)
def consultar_proceso(self, proceso_id: str) -> None:
    try:
        asyncio.run(_consultar_proceso_async(proceso_id, intento_numero=self.request.retries + 1))
    except _ErrorRecuperable as exc:
        backoff = BACKOFF_BASE_SECONDS * (2**self.request.retries)
        raise self.retry(exc=exc, countdown=backoff)


async def _destinatarios(db, proceso: Proceso) -> list[Usuario]:
    """A quién notificar: el apoderado asignado si existe, si no todos los
    admins de la firma (para no dejar un proceso sin dueño de la alerta)."""
    if proceso.apoderado_id:
        r = await db.execute(select(Usuario).where(Usuario.id == proceso.apoderado_id))
        u = r.scalar_one_or_none()
        if u:
            return [u]
    r = await db.execute(
        select(Usuario).where(Usuario.firma_id == proceso.firma_id, Usuario.rol == RolUsuario.admin)
    )
    return list(r.scalars().all())


async def _consultar_proceso_async(proceso_id: str, intento_numero: int) -> None:
    async with SessionLocal() as db:
        proceso = (
            await db.execute(select(Proceso).where(Proceso.id == proceso_id))
        ).scalar_one_or_none()
        if proceso is None:
            return  # el proceso pudo haber sido borrado entre el encolado y la ejecución

        conector = get_conector(proceso.fuente)
        fingerprints_previos = set(
            (
                await db.execute(
                    select(Actuacion.fingerprint).where(Actuacion.proceso_id == proceso.id)
                )
            ).scalars()
        )
        metadatos_previos = _metadatos_desde_json(proceso.metadatos)

        inicio = time_module.monotonic()
        await rate_limiter.acquire(proceso.fuente)
        try:
            respuesta = await conector.consultar(proceso.radicado)
        finally:
            rate_limiter.release(proceso.fuente)
        duracion_ms = int((time_module.monotonic() - inicio) * 1000)

        if respuesta.resultado in (
            ResultadoConsulta.BLOQUEADO_O_CAPTCHA,
            ResultadoConsulta.ERROR_TEMPORAL,
        ):
            db.add(
                ConsultaRun(
                    proceso_id=proceso.id, fuente=proceso.fuente, estado=EstadoRun.error_temporal,
                    intento_numero=intento_numero, mensaje_error=respuesta.mensaje,
                    duracion_ms=duracion_ms,
                )
            )
            await db.commit()

            if intento_numero >= MAX_RETRIES_PER_RUN:
                await _avisar_fallo(db, proceso, respuesta.mensaje or "Error desconocido")
            raise _ErrorRecuperable(respuesta.mensaje or "Error temporal de la fuente")

        if respuesta.resultado == ResultadoConsulta.FUENTE_CAMBIO_ESTRUCTURA:
            db.add(
                ConsultaRun(
                    proceso_id=proceso.id, fuente=proceso.fuente, estado=EstadoRun.error_permanente,
                    intento_numero=intento_numero, mensaje_error=respuesta.mensaje,
                    duracion_ms=duracion_ms,
                )
            )
            await db.commit()
            await _avisar_fallo(db, proceso, respuesta.mensaje or "El portal cambió su estructura")
            # TODO(observabilidad): además de avisar al usuario, esto debería
            # disparar una alerta interna (Slack/PagerDuty/etc.) al equipo,
            # porque significa que el conector quedó roto para TODOS los
            # procesos de esta fuente, no solo este.
            return

        if respuesta.resultado == ResultadoConsulta.RADICADO_NO_ENCONTRADO:
            db.add(
                ConsultaRun(
                    proceso_id=proceso.id, fuente=proceso.fuente, estado=EstadoRun.error_permanente,
                    intento_numero=intento_numero, mensaje_error=respuesta.mensaje,
                    duracion_ms=duracion_ms,
                )
            )
            await db.commit()
            return

        # --- resultado == OK ---
        diff = calcular_diff(
            fingerprints_previos, respuesta.actuaciones, metadatos_previos, respuesta.metadatos
        )

        for actuacion_cruda in diff.actuaciones_nuevas:
            db.add(
                Actuacion(
                    proceso_id=proceso.id,
                    fingerprint=fingerprint_actuacion(actuacion_cruda),
                    tipo=actuacion_cruda.tipo,
                    fecha_actuacion=actuacion_cruda.fecha_actuacion,
                    anotacion=actuacion_cruda.anotacion,
                    despacho=actuacion_cruda.despacho,
                    ponente=actuacion_cruda.ponente,
                    fecha_audiencia=actuacion_cruda.fecha_audiencia,
                    documento_url=actuacion_cruda.documento_url,
                )
            )

        if respuesta.metadatos:
            proceso.metadatos = _metadatos_a_json(respuesta.metadatos)

        db.add(
            ConsultaRun(
                proceso_id=proceso.id,
                fuente=proceso.fuente,
                estado=EstadoRun.ok if diff.hay_novedades else EstadoRun.sin_cambios,
                intento_numero=intento_numero,
                actuaciones_nuevas=len(diff.actuaciones_nuevas),
                duracion_ms=duracion_ms,
            )
        )
        await db.commit()

        if diff.hay_novedades:
            await _avisar_novedad(db, proceso, diff)


async def _avisar_novedad(db, proceso: Proceso, diff) -> None:
    regla = notifier.ReglaNotificacion(
        avisar_todo=proceso.avisar_todo, tipos_permitidos=set(proceso.tipos_permitidos) or None
    )
    for usuario in await _destinatarios(db, proceso):
        for canal in proceso.notificar_canales:
            try:
                await notifier.notificar_novedad(
                    usuario.email, canal, proceso.alias or "", proceso.radicado, diff, regla
                )
            except NotImplementedError:
                pass  # canal aún no integrado (web_push/sms) — no debe tumbar la corrida


async def _avisar_fallo(db, proceso: Proceso, mensaje_error: str) -> None:
    for usuario in await _destinatarios(db, proceso):
        try:
            await notifier.notificar_fallo_consulta(
                usuario.email, "email", proceso.alias or "", proceso.radicado, proceso.fuente, mensaje_error
            )
        except NotImplementedError:
            pass


@celery_app.task(name="app.tasks.scheduler.enviar_resumenes_diarios")
def enviar_resumenes_diarios() -> None:
    asyncio.run(_enviar_resumenes_diarios_async())


async def _enviar_resumenes_diarios_async() -> None:
    async with SessionLocal() as db:
        desde = datetime.now(timezone.utc) - timedelta(days=1)
        usuarios = (await db.execute(select(Usuario))).scalars().all()

        for usuario in usuarios:
            resultado = await db.execute(
                select(Proceso, ConsultaRun)
                .join(ConsultaRun, ConsultaRun.proceso_id == Proceso.id)
                .where(
                    Proceso.firma_id == usuario.firma_id,
                    ConsultaRun.ejecutado_en >= desde,
                    ConsultaRun.actuaciones_nuevas > 0,
                )
            )
            filas = resultado.all()
            if not filas:
                continue

            lineas = [f"Resumen diario de novedades ({len(filas)} procesos con cambios):", ""]
            for proceso, run in filas:
                lineas.append(
                    f"- {proceso.alias or proceso.radicado}: {run.actuaciones_nuevas} actuación(es) nueva(s)"
                )
            try:
                await notifier.CANALES["email"].enviar(
                    usuario.email, "Tu resumen diario de procesos", "\n".join(lineas)
                )
            except Exception:
                pass  # un resumen fallido no debe frenar el resto de usuarios
