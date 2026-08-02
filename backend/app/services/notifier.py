"""
Servicio de notificaciones. Cada canal implementa `enviar`; el servicio
decide QUÉ enviar según las reglas configuradas por el usuario/proceso,
y siempre dispara una notificación cuando una fuente falló (para que el
usuario nunca confunda "silencio" con "sin novedades").
"""
from __future__ import annotations

import abc
import smtplib
from dataclasses import dataclass
from email.mime.text import MIMEText

from app import config
from app.services.diff_engine import ResultadoDiff


@dataclass
class ReglaNotificacion:
    """Reglas configurables por proceso o globales por usuario."""
    avisar_todo: bool = True
    tipos_permitidos: set[str] | None = None  # p.ej. {"sentencia", "auto"} si avisar_todo=False
    resumen_diario: bool = False
    resumen_semanal: bool = False


class CanalNotificacion(abc.ABC):
    nombre: str

    @abc.abstractmethod
    async def enviar(self, destinatario: str, asunto: str, cuerpo: str) -> None:
        raise NotImplementedError


class CanalEmail(CanalNotificacion):
    nombre = "email"

    async def enviar(self, destinatario: str, asunto: str, cuerpo: str) -> None:
        msg = MIMEText(cuerpo, "plain", "utf-8")
        msg["Subject"] = asunto
        msg["From"] = config.SMTP_USER
        msg["To"] = destinatario

        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as server:
            server.starttls()
            server.login(config.SMTP_USER, config.SMTP_PASSWORD)
            server.sendmail(config.SMTP_USER, [destinatario], msg.as_string())


class CanalWebPush(CanalNotificacion):
    nombre = "web_push"

    async def enviar(self, destinatario: str, asunto: str, cuerpo: str) -> None:
        # `destinatario` aquí es la suscripción Web Push (endpoint + claves)
        # serializada. Se integraría con la librería `pywebpush` usando
        # config.VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY.
        raise NotImplementedError("Integrar pywebpush con las claves VAPID del proyecto.")


class CanalSMSWhatsApp(CanalNotificacion):
    nombre = "sms_whatsapp"

    async def enviar(self, destinatario: str, asunto: str, cuerpo: str) -> None:
        # Integrar con un proveedor (Twilio, etc.) para planes premium.
        raise NotImplementedError("Integrar proveedor de SMS/WhatsApp para planes premium.")


CANALES: dict[str, CanalNotificacion] = {
    "email": CanalEmail(),
    "web_push": CanalWebPush(),
    "sms_whatsapp": CanalSMSWhatsApp(),
}


def _filtrar_por_regla(diff: ResultadoDiff, regla: ReglaNotificacion) -> bool:
    if regla.avisar_todo:
        return diff.hay_novedades
    if not regla.tipos_permitidos:
        return False
    return any(a.tipo in regla.tipos_permitidos for a in diff.actuaciones_nuevas)


def construir_mensaje_novedad(alias: str, radicado: str, diff: ResultadoDiff) -> tuple[str, str]:
    asunto = f"Novedad en el proceso {alias or radicado}"
    lineas = [f"Se detectaron novedades en el proceso {alias or radicado} ({radicado}):", ""]
    for a in diff.actuaciones_nuevas:
        lineas.append(f"- [{a.tipo}] {a.fecha_actuacion.date()}: {a.anotacion[:200]}")
    for c in diff.cambios:
        if c.actuacion is None:
            lineas.append(f"- {c.detalle}")
    return asunto, "\n".join(lineas)


def construir_mensaje_fallo(alias: str, radicado: str, fuente: str, mensaje_error: str) -> tuple[str, str]:
    asunto = f"No se pudo consultar el proceso {alias or radicado}"
    cuerpo = (
        f"La consulta automática a {fuente} para el proceso {alias or radicado} ({radicado}) "
        f"falló y quedó pendiente de reintento.\n\nDetalle: {mensaje_error}\n\n"
        "Esto NO significa que no haya novedades: significa que todavía no pudimos verificarlo."
    )
    return asunto, cuerpo


async def notificar_novedad(
    destinatario: str, canal: str, alias: str, radicado: str, diff: ResultadoDiff, regla: ReglaNotificacion
) -> None:
    if not _filtrar_por_regla(diff, regla):
        return
    asunto, cuerpo = construir_mensaje_novedad(alias, radicado, diff)
    await CANALES[canal].enviar(destinatario, asunto, cuerpo)


async def notificar_fallo_consulta(
    destinatario: str, canal: str, alias: str, radicado: str, fuente: str, mensaje_error: str
) -> None:
    asunto, cuerpo = construir_mensaje_fallo(alias, radicado, fuente, mensaje_error)
    await CANALES[canal].enviar(destinatario, asunto, cuerpo)
