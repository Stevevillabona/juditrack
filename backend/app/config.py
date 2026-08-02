"""
Configuración central. Todo lo que varía entre entornos (dev/staging/prod)
o entre planes de suscripción vive aquí, nunca hardcodeado en los conectores.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import time


@dataclass
class MonitoringWindow:
    """Ventana horaria en la que el scheduler puede lanzar consultas."""
    start: time = time(8, 0)
    end: time = time(16, 0)
    timezone: str = "America/Bogota"
    business_days_only: bool = True  # lunes a viernes


@dataclass
class PlanConfig:
    """Frecuencia de monitoreo y canales disponibles por plan."""
    name: str
    poll_interval_minutes: int
    channels: list[str] = field(default_factory=lambda: ["email"])
    max_procesos: int | None = None


PLANS: dict[str, PlanConfig] = {
    "free": PlanConfig(name="free", poll_interval_minutes=24 * 60, channels=["email"], max_procesos=5),
    "standard": PlanConfig(name="standard", poll_interval_minutes=120, channels=["email", "web_push"]),
    "premium": PlanConfig(
        name="premium",
        poll_interval_minutes=60,
        channels=["email", "web_push", "sms", "whatsapp"],
    ),
}

DEFAULT_MONITORING_WINDOW = MonitoringWindow()

# --- Infraestructura ---
DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+asyncpg://juditrack:juditrack@localhost:5432/juditrack"
)
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# --- Rate limiting hacia fuentes oficiales ---
# Nunca superar esto por fuente, sin importar cuántos procesos/usuarios existan.
# Es un límite global compartido, no por usuario.
SOURCE_RATE_LIMITS = {
    "rama_judicial": {"max_concurrent": 2, "min_seconds_between_requests": 3},
    "tyba": {"max_concurrent": 2, "min_seconds_between_requests": 3},
    "samai": {"max_concurrent": 1, "min_seconds_between_requests": 5},
    "spoa": {"max_concurrent": 1, "min_seconds_between_requests": 5},
    "superfinanciera": {"max_concurrent": 2, "min_seconds_between_requests": 3},
    "sic": {"max_concurrent": 2, "min_seconds_between_requests": 3},
}

# --- Reintentos / backoff ---
MAX_RETRIES_PER_RUN = 4
BACKOFF_BASE_SECONDS = 30  # backoff exponencial: 30s, 60s, 120s, 240s

# --- Notificaciones ---
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")

# --- CORS ---
# Dominio(s) desde donde se sirve el frontend en producción. Coma-separado.
# En Render, esto se llena automáticamente apuntando a la URL del sitio estático.
CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]
