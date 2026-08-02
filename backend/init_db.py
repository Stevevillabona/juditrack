"""Crea las tablas si no existen. Se corre antes de levantar el worker o el
beat de Celery, para que el orden de arranque de los contenedores en
docker-compose no importe (la API también lo hace en su lifespan, esto es
solo para cubrir el caso de que un worker arranque primero)."""
import asyncio

from app.database import init_models

if __name__ == "__main__":
    asyncio.run(init_models())
