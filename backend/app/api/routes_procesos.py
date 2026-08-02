"""
Endpoints REST para gestión de procesos, ya conectados a la base de datos.

La consulta a la fuente oficial NUNCA ocurre de forma síncrona dentro de una
petición HTTP: crear un proceso solo lo registra y encola una primera
consulta en segundo plano (Celery). El usuario ve el resultado cuando esté
listo, vía polling del dashboard o notificación.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.registry import get_conector
from app.database import get_db
from app.deps import UsuarioActual, get_current_user
from app.models import AccessLog, Actuacion, ConsultaRun, Proceso, ProcesoVisto
from app.schemas import ActuacionRespuesta, ConsultaRunRespuesta, ProcesoCrear, ProcesoRespuesta

router = APIRouter(prefix="/api/procesos", tags=["procesos"])


async def _tiene_novedades(db: AsyncSession, proceso: Proceso, usuario_id: UUID) -> bool:
    """Novedad = existe alguna Actuacion detectada después de la última vez
    que ESTE usuario vio el proceso (o, si nunca lo ha visto, cualquier
    actuación existente cuenta como novedad)."""
    visto = await db.execute(
        select(ProcesoVisto).where(
            ProcesoVisto.proceso_id == proceso.id, ProcesoVisto.usuario_id == usuario_id
        )
    )
    marca = visto.scalar_one_or_none()
    ultima_actuacion = max(
        (a.detectada_en for a in proceso.actuaciones), default=None
    )
    if ultima_actuacion is None:
        return False
    if marca is None:
        return True
    return ultima_actuacion > marca.visto_hasta


@router.post("", response_model=ProcesoRespuesta, status_code=201)
async def crear_proceso(
    payload: ProcesoCrear,
    usuario: UsuarioActual = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conector = get_conector(payload.fuente)
    if not conector.valida_radicado(payload.radicado):
        raise HTTPException(422, f"Radicado inválido para la fuente '{payload.fuente}'.")

    existente = await db.execute(
        select(Proceso).where(
            Proceso.firma_id == usuario.firma_id,
            Proceso.radicado == payload.radicado,
            Proceso.fuente == payload.fuente,
        )
    )
    if existente.scalar_one_or_none() is not None:
        raise HTTPException(409, "Ya existe ese radicado registrado en esta fuente para tu firma.")

    proceso = Proceso(
        firma_id=usuario.firma_id,
        radicado=payload.radicado,
        fuente=payload.fuente,
        alias=payload.alias,
        cliente=payload.cliente,
        jurisdiccion=payload.jurisdiccion,
        apoderado_id=payload.apoderado_id,
        tags=payload.tags,
    )
    db.add(proceso)
    await db.commit()
    await db.refresh(proceso)

    # Primera consulta en segundo plano, sin bloquear la respuesta HTTP.
    from app.tasks.scheduler import consultar_proceso

    consultar_proceso.delay(str(proceso.id))

    return ProcesoRespuesta(
        id=proceso.id,
        radicado=proceso.radicado,
        fuente=proceso.fuente,
        alias=proceso.alias,
        cliente=proceso.cliente,
        jurisdiccion=proceso.jurisdiccion,
        activo=proceso.activo,
        archivado=proceso.archivado,
        tiene_novedades=False,
    )


@router.post("/importar-csv", status_code=202)
async def importar_csv(
    archivo: UploadFile,
    usuario: UsuarioActual = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Importación en lote. Formato esperado (encabezados):
    radicado,fuente,alias,cliente,jurisdiccion

    Filas inválidas se reportan sin abortar la carga completa."""
    contenido = (await archivo.read()).decode("utf-8-sig")
    lector = csv.DictReader(io.StringIO(contenido))

    creados, errores = 0, []
    from app.tasks.scheduler import consultar_proceso

    for i, fila in enumerate(lector, start=2):  # fila 1 = encabezado
        radicado = (fila.get("radicado") or "").strip()
        fuente = (fila.get("fuente") or "rama_judicial").strip()
        try:
            conector = get_conector(fuente)
        except ValueError as e:
            errores.append({"fila": i, "error": str(e)})
            continue
        if not conector.valida_radicado(radicado):
            errores.append({"fila": i, "error": f"Radicado inválido: '{radicado}'"})
            continue

        proceso = Proceso(
            firma_id=usuario.firma_id,
            radicado=radicado,
            fuente=fuente,
            alias=(fila.get("alias") or "").strip() or None,
            cliente=(fila.get("cliente") or "").strip() or None,
            jurisdiccion=(fila.get("jurisdiccion") or "").strip() or None,
        )
        db.add(proceso)
        await db.flush()
        consultar_proceso.delay(str(proceso.id))
        creados += 1

    await db.commit()
    return {"creados": creados, "errores": errores}


@router.get("", response_model=list[ProcesoRespuesta])
async def listar_procesos(
    con_novedades: bool | None = None,
    cliente: str | None = None,
    jurisdiccion: str | None = None,
    archivado: bool = False,
    usuario: UsuarioActual = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(Proceso).where(Proceso.firma_id == usuario.firma_id, Proceso.archivado == archivado)
    if cliente:
        query = query.where(Proceso.cliente == cliente)
    if jurisdiccion:
        query = query.where(Proceso.jurisdiccion == jurisdiccion)

    resultado = await db.execute(query)
    procesos = resultado.scalars().all()

    respuestas = []
    for p in procesos:
        novedad = await _tiene_novedades(db, p, usuario.id)
        if con_novedades is not None and novedad != con_novedades:
            continue
        respuestas.append(
            ProcesoRespuesta(
                id=p.id, radicado=p.radicado, fuente=p.fuente, alias=p.alias,
                cliente=p.cliente, jurisdiccion=p.jurisdiccion, activo=p.activo,
                archivado=p.archivado, tiene_novedades=novedad,
            )
        )
    return respuestas


async def _get_proceso_o_404(db: AsyncSession, proceso_id: UUID, firma_id: UUID) -> Proceso:
    resultado = await db.execute(
        select(Proceso).where(Proceso.id == proceso_id, Proceso.firma_id == firma_id)
    )
    proceso = resultado.scalar_one_or_none()
    if proceso is None:
        raise HTTPException(404, "Proceso no encontrado.")
    return proceso


@router.get("/{proceso_id}", response_model=ProcesoRespuesta)
async def obtener_proceso(
    proceso_id: UUID,
    usuario: UsuarioActual = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    proceso = await _get_proceso_o_404(db, proceso_id, usuario.firma_id)

    # Trazabilidad: quién vio qué proceso y cuándo.
    db.add(AccessLog(usuario_id=usuario.id, proceso_id=proceso.id, accion="ver"))

    novedad = await _tiene_novedades(db, proceso, usuario.id)

    # Al ver el detalle, se actualiza (o crea) la marca de "visto hasta ahora".
    marca = await db.execute(
        select(ProcesoVisto).where(
            ProcesoVisto.proceso_id == proceso.id, ProcesoVisto.usuario_id == usuario.id
        )
    )
    marca_obj = marca.scalar_one_or_none()
    ahora = datetime.now(timezone.utc)
    if marca_obj is None:
        db.add(ProcesoVisto(proceso_id=proceso.id, usuario_id=usuario.id, visto_hasta=ahora))
    else:
        marca_obj.visto_hasta = ahora

    await db.commit()

    return ProcesoRespuesta(
        id=proceso.id, radicado=proceso.radicado, fuente=proceso.fuente, alias=proceso.alias,
        cliente=proceso.cliente, jurisdiccion=proceso.jurisdiccion, activo=proceso.activo,
        archivado=proceso.archivado, tiene_novedades=novedad,
    )


@router.get("/{proceso_id}/actuaciones", response_model=list[ActuacionRespuesta])
async def listar_actuaciones(
    proceso_id: UUID,
    usuario: UsuarioActual = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_proceso_o_404(db, proceso_id, usuario.firma_id)
    resultado = await db.execute(
        select(Actuacion).where(Actuacion.proceso_id == proceso_id).order_by(Actuacion.fecha_actuacion)
    )
    return resultado.scalars().all()


@router.get("/{proceso_id}/auditoria", response_model=list[ConsultaRunRespuesta])
async def auditoria_proceso(
    proceso_id: UUID,
    usuario: UsuarioActual = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Registro de auditoría de cada corrida contra la fuente: qué se
    consultó, cuándo, con qué resultado y con qué error si falló. Sin cajas
    negras: si una consulta quedó pendiente por bloqueo o cambio de
    estructura de la fuente, el usuario lo ve aquí explícitamente."""
    await _get_proceso_o_404(db, proceso_id, usuario.firma_id)
    resultado = await db.execute(
        select(ConsultaRun)
        .where(ConsultaRun.proceso_id == proceso_id)
        .order_by(ConsultaRun.ejecutado_en.desc())
        .limit(100)
    )
    return resultado.scalars().all()


@router.post("/{proceso_id}/archivar", status_code=204)
async def archivar_proceso(
    proceso_id: UUID,
    usuario: UsuarioActual = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    proceso = await _get_proceso_o_404(db, proceso_id, usuario.firma_id)
    proceso.archivado = True
    proceso.activo = False
    await db.commit()


@router.post("/{proceso_id}/pausar", status_code=204)
async def pausar_proceso(
    proceso_id: UUID,
    usuario: UsuarioActual = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    proceso = await _get_proceso_o_404(db, proceso_id, usuario.firma_id)
    proceso.activo = False
    await db.commit()


@router.post("/{proceso_id}/reanudar", status_code=204)
async def reanudar_proceso(
    proceso_id: UUID,
    usuario: UsuarioActual = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    proceso = await _get_proceso_o_404(db, proceso_id, usuario.firma_id)
    proceso.activo = True
    await db.commit()


@router.post("/{proceso_id}/consultar-ahora", status_code=202)
async def forzar_consulta(
    proceso_id: UUID,
    usuario: UsuarioActual = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Permite forzar una consulta inmediata fuera del ciclo programado,
    respetando igualmente el rate limiter compartido de la fuente."""
    await _get_proceso_o_404(db, proceso_id, usuario.firma_id)
    from app.tasks.scheduler import consultar_proceso

    consultar_proceso.delay(str(proceso_id))
    return {"status": "encolado"}
