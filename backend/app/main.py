from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_auth import router as auth_router
from app.api.routes_procesos import router as procesos_router
from app.config import CORS_ORIGINS
from app.database import init_models


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_models()  # crea tablas si no existen (dev); usar Alembic en prod
    yield


app = FastAPI(title="JudiTrack API", version="0.1.0", lifespan=lifespan)

# CORS: solo para que EL FRONTEND propio llame a esta API. Esto no tiene
# nada que ver con las fuentes oficiales (que no exponen CORS a nadie);
# esta API es la única que el navegador del usuario toca directamente.
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(procesos_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
