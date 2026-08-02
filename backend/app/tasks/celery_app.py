"""
Cola de trabajos. Celery + Redis como pide el spec.

`beat_schedule` dispara periódicamente el "despachador" (dispatcher), que
decide QUÉ procesos tocan consultarse ahora según el plan del usuario y la
ventana horaria configurada, y encola una tarea de consulta por cada uno.
Las tareas individuales de consulta son las que de verdad llaman a los
conectores y por lo tanto respetan el rate limiter por fuente.
"""
from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.config import REDIS_URL

celery_app = Celery("juditrack", broker=REDIS_URL, backend=REDIS_URL)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="America/Bogota",
    enable_utc=True,
    task_acks_late=True,  # si el worker muere a mitad de tarea, se reintenta
    worker_prefetch_multiplier=1,
)

celery_app.conf.beat_schedule = {
    # Corre cada 15 min; el dispatcher decide internamente qué procesos
    # realmente le tocan a cada uno según su plan (cada 1h, 2h, etc.)
    # y respeta la ventana 8am-4pm / días hábiles.
    "despachar-consultas-pendientes": {
        "task": "app.tasks.scheduler.despachar_consultas_pendientes",
        "schedule": crontab(minute="*/15"),
    },
    "enviar-resumenes-diarios": {
        "task": "app.tasks.scheduler.enviar_resumenes_diarios",
        "schedule": crontab(hour=17, minute=0),  # fin de la ventana hábil
    },
}


# autodiscover_tasks por defecto busca un submódulo "tasks" dentro de cada
# paquete listado (convención django-style); como nuestras tareas viven en
# app.tasks.scheduler, se importa explícitamente para que Celery las registre.
from app.tasks import scheduler  # noqa: E402,F401
