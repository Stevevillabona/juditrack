"""
Motor de monitoreo para la arquitectura gratuita (GitHub Actions + Supabase).

Reemplaza al par Celery+Postgres-propio de la arquitectura de Render: en vez
de un worker siempre despierto, este script corre una vez por invocación
(disparada por cron de GitHub Actions o manualmente desde la pestaña
"Actions" del repo), procesa todos los procesos activos, y termina.

Reutiliza sin cambios la lógica de negocio ya construida en
backend/app/connectors y backend/app/services (son puro Python, sin
SQLAlchemy ni FastAPI de por medio), y habla con Supabase por su API REST
(PostgREST) usando la service role key, que se salta RLS a propósito para
poder monitorear los procesos de todos los usuarios.

Variables de entorno esperadas (se configuran como Secrets de GitHub, ver
DESPLIEGUE_GRATIS.md):
  SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD  (opcionales)
  PROCESO_ID  (opcional: si se define, solo procesa ese proceso puntual;
               lo usa el botón "Run workflow" con input manual)
"""
from __future__ import annotations

import asyncio
import os
import smtplib
import sys
import time
from email.mime.text import MIMEText
from pathlib import Path

import requests

# Reutiliza la lógica ya construida en backend/app, sin necesitar FastAPI,
# SQLAlchemy ni Celery instalados (esos módulos son Python puro).
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.connectors.base import MetadatosProceso, ResultadoConsulta  # noqa: E402
from app.connectors.registry import get_conector, rate_limiter  # noqa: E402
from app.services.diff_engine import calcular_diff, fingerprint_actuacion  # noqa: E402

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SERVICE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
PROCESO_ID_FORZADO = os.environ.get("PROCESO_ID", "").strip() or None

SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT") or "587")
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")

HEADERS = {
    "apikey": SERVICE_KEY,
    "Authorization": f"Bearer {SERVICE_KEY}",
    "Content-Type": "application/json",
}


# ---------------------------------------------------------------- utilidades REST

def rest_get(tabla: str, params: dict) -> list[dict]:
    r = requests.get(f"{SUPABASE_URL}/rest/v1/{tabla}", headers=HEADERS, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def rest_patch(tabla: str, filtro: dict, body: dict) -> None:
    r = requests.patch(f"{SUPABASE_URL}/rest/v1/{tabla}", headers=HEADERS, params=filtro, json=body, timeout=30)
    r.raise_for_status()


def rest_post(tabla: str, body: dict | list, on_conflict: str | None = None, ignorar_duplicados: bool = False) -> None:
    headers = dict(HEADERS)
    params = {}
    if on_conflict:
        params["on_conflict"] = on_conflict
        headers["Prefer"] = "resolution=ignore-duplicates,return=minimal" if ignorar_duplicados else "return=minimal"
    else:
        headers["Prefer"] = "return=minimal"
    r = requests.post(f"{SUPABASE_URL}/rest/v1/{tabla}", headers=headers, params=params, json=body, timeout=30)
    r.raise_for_status()


# ---------------------------------------------------------------- notificaciones

def enviar_email(destinatario: str, asunto: str, cuerpo: str) -> None:
    if not (SMTP_HOST and SMTP_USER and SMTP_PASSWORD):
        print(f"  (SMTP no configurado, se omite el correo a {destinatario})")
        return
    msg = MIMEText(cuerpo, "plain", "utf-8")
    msg["Subject"] = asunto
    msg["From"] = SMTP_USER
    msg["To"] = destinatario
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_USER, [destinatario], msg.as_string())


def destinatarios(proceso: dict) -> list[str]:
    if proceso.get("apoderado_id"):
        perfiles = rest_get("perfiles", {"id": f"eq.{proceso['apoderado_id']}", "select": "email"})
        if perfiles:
            return [p["email"] for p in perfiles]
    admins = rest_get(
        "perfiles", {"firma_id": f"eq.{proceso['firma_id']}", "rol": "eq.admin", "select": "email"}
    )
    return [p["email"] for p in admins]


def notificar_novedad(proceso: dict, diff) -> None:
    alias = proceso.get("alias") or proceso["radicado"]
    lineas = [f"Se detectaron novedades en el proceso {alias} ({proceso['radicado']}):", ""]
    for a in diff.actuaciones_nuevas:
        lineas.append(f"- [{a.tipo}] {a.fecha_actuacion.date()}: {a.anotacion[:200]}")
    for c in diff.cambios:
        if c.actuacion is None:
            lineas.append(f"- {c.detalle}")
    cuerpo = "\n".join(lineas)
    for correo in destinatarios(proceso):
        enviar_email(correo, f"Novedad en el proceso {alias}", cuerpo)


def notificar_fallo(proceso: dict, mensaje_error: str) -> None:
    alias = proceso.get("alias") or proceso["radicado"]
    cuerpo = (
        f"La consulta automática para el proceso {alias} ({proceso['radicado']}) falló "
        f"y quedó pendiente de reintento.\n\nDetalle: {mensaje_error}\n\n"
        "Esto NO significa que no haya novedades: significa que todavía no pudimos verificarlo."
    )
    for correo in destinatarios(proceso):
        enviar_email(correo, f"No se pudo consultar el proceso {alias}", cuerpo)


# ---------------------------------------------------------------- metadatos (de)serialización

def metadatos_desde_json(data: dict | None) -> MetadatosProceso | None:
    if not data:
        return None
    fecha_txt = data.get("fecha_radicacion")
    from datetime import datetime as dt

    return MetadatosProceso(
        despacho=data.get("despacho"),
        tipo_proceso=data.get("tipo_proceso"),
        clase_proceso=data.get("clase_proceso"),
        partes=data.get("partes") or [],
        fecha_radicacion=dt.fromisoformat(fecha_txt) if fecha_txt else None,
        extra=data.get("extra") or {},
    )


def metadatos_a_json(m: MetadatosProceso) -> dict:
    return {
        "despacho": m.despacho,
        "tipo_proceso": m.tipo_proceso,
        "clase_proceso": m.clase_proceso,
        "partes": m.partes,
        "fecha_radicacion": m.fecha_radicacion.isoformat() if m.fecha_radicacion else None,
        "extra": m.extra,
    }


# ---------------------------------------------------------------- procesamiento de un proceso

async def procesar_proceso(proceso: dict) -> None:
    radicado, fuente = proceso["radicado"], proceso["fuente"]
    alias = proceso.get("alias") or radicado
    print(f"→ {alias} ({radicado}) vía {fuente}")

    conector = get_conector(fuente)
    fingerprints_previos = {
        a["fingerprint"]
        for a in rest_get("actuaciones", {"proceso_id": f"eq.{proceso['id']}", "select": "fingerprint"})
    }
    metadatos_previos = metadatos_desde_json(proceso.get("metadatos"))

    inicio = time.monotonic()
    await rate_limiter.acquire(fuente)
    try:
        respuesta = await conector.consultar(radicado)
    finally:
        rate_limiter.release(fuente)
    duracion_ms = int((time.monotonic() - inicio) * 1000)

    if respuesta.resultado in (ResultadoConsulta.BLOQUEADO_O_CAPTCHA, ResultadoConsulta.ERROR_TEMPORAL):
        rest_post("consulta_runs", {
            "proceso_id": proceso["id"], "fuente": fuente, "estado": "error_temporal",
            "mensaje_error": respuesta.mensaje, "duracion_ms": duracion_ms,
        })
        print(f"  falló (temporal): {respuesta.mensaje}")
        notificar_fallo(proceso, respuesta.mensaje or "Error desconocido")
        return

    if respuesta.resultado == ResultadoConsulta.FUENTE_CAMBIO_ESTRUCTURA:
        rest_post("consulta_runs", {
            "proceso_id": proceso["id"], "fuente": fuente, "estado": "error_permanente",
            "mensaje_error": respuesta.mensaje, "duracion_ms": duracion_ms,
        })
        print(f"  ⚠️  posible cambio de estructura en la fuente: {respuesta.mensaje}")
        notificar_fallo(proceso, respuesta.mensaje or "El portal cambió su estructura")
        return

    if respuesta.resultado == ResultadoConsulta.RADICADO_NO_ENCONTRADO:
        rest_post("consulta_runs", {
            "proceso_id": proceso["id"], "fuente": fuente, "estado": "error_permanente",
            "mensaje_error": respuesta.mensaje, "duracion_ms": duracion_ms,
        })
        print(f"  radicado no encontrado: {respuesta.mensaje}")
        return

    # --- OK ---
    diff = calcular_diff(fingerprints_previos, respuesta.actuaciones, metadatos_previos, respuesta.metadatos)

    if diff.actuaciones_nuevas:
        filas = [
            {
                "proceso_id": proceso["id"],
                "fingerprint": fingerprint_actuacion(a),
                "tipo": a.tipo,
                "fecha_actuacion": a.fecha_actuacion.isoformat(),
                "anotacion": a.anotacion,
                "despacho": a.despacho,
                "ponente": a.ponente,
                "fecha_audiencia": a.fecha_audiencia.isoformat() if a.fecha_audiencia else None,
                "documento_url": a.documento_url,
            }
            for a in diff.actuaciones_nuevas
        ]
        rest_post("actuaciones", filas, on_conflict="proceso_id,fingerprint", ignorar_duplicados=True)

    if respuesta.metadatos:
        rest_patch("procesos", {"id": f"eq.{proceso['id']}"}, {"metadatos": metadatos_a_json(respuesta.metadatos)})

    rest_post("consulta_runs", {
        "proceso_id": proceso["id"], "fuente": fuente,
        "estado": "ok" if diff.hay_novedades else "sin_cambios",
        "actuaciones_nuevas": len(diff.actuaciones_nuevas), "duracion_ms": duracion_ms,
    })

    if diff.hay_novedades:
        print(f"  ✔ {len(diff.actuaciones_nuevas)} actuación(es) nueva(s)")
        notificar_novedad(proceso, diff)
    else:
        print("  sin cambios")


async def main() -> None:
    filtro = {"activo": "eq.true", "archivado": "eq.false", "select": "*"}
    if PROCESO_ID_FORZADO:
        filtro["id"] = f"eq.{PROCESO_ID_FORZADO}"

    procesos = rest_get("procesos", filtro)
    print(f"{len(procesos)} proceso(s) a revisar.")

    for proceso in procesos:
        try:
            await procesar_proceso(proceso)
        except Exception as exc:  # un proceso roto no debe tumbar el resto de la corrida
            print(f"  ERROR inesperado procesando {proceso.get('radicado')}: {exc}")


if __name__ == "__main__":
    asyncio.run(main())
