from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user, get_usuario_orm, UsuarioActual
from app.models import Firma, RolUsuario, Usuario
from app.schemas_auth import (
    Activar2FARespuesta,
    Confirmar2FA,
    Login,
    RegistroFirma,
    TokenRespuesta,
)
from app.security import (
    crear_access_token,
    generar_2fa_secret,
    generar_2fa_uri,
    hash_password,
    verificar_2fa_codigo,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/registro", response_model=TokenRespuesta, status_code=201)
async def registro(payload: RegistroFirma, db: AsyncSession = Depends(get_db)):
    existente = await db.execute(select(Usuario).where(Usuario.email == payload.email))
    if existente.scalar_one_or_none() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe una cuenta con ese correo.")

    if len(payload.password) < 8:
        raise HTTPException(422, "La contraseña debe tener al menos 8 caracteres.")

    firma = Firma(nombre=payload.nombre_firma, plan="free")
    db.add(firma)
    await db.flush()  # para obtener firma.id antes del commit

    usuario = Usuario(
        firma_id=firma.id,
        email=payload.email,
        password_hash=hash_password(payload.password),
        nombre=payload.nombre_usuario,
        rol=RolUsuario.admin,  # quien registra la firma es admin por defecto
    )
    db.add(usuario)
    await db.commit()

    token = crear_access_token(usuario.id, firma.id, usuario.rol.value)
    return TokenRespuesta(access_token=token, requiere_2fa_setup=True)


@router.post("/login", response_model=TokenRespuesta)
async def login(payload: Login, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Usuario).where(Usuario.email == payload.email))
    usuario = result.scalar_one_or_none()

    if usuario is None or not verify_password(payload.password, usuario.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Credenciales inválidas.")

    if usuario.two_factor_enabled:
        if not payload.codigo_2fa:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "Esta cuenta tiene verificación en dos pasos activa: incluye 'codigo_2fa'.",
            )
        if not verificar_2fa_codigo(usuario.two_factor_secret, payload.codigo_2fa):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Código de verificación incorrecto.")

    token = crear_access_token(usuario.id, usuario.firma_id, usuario.rol.value)
    return TokenRespuesta(access_token=token, requiere_2fa_setup=not usuario.two_factor_enabled)


@router.post("/2fa/iniciar", response_model=Activar2FARespuesta)
async def iniciar_2fa(usuario: Usuario = Depends(get_usuario_orm), db: AsyncSession = Depends(get_db)):
    """Genera un secreto TOTP nuevo (pendiente de confirmar con un código
    antes de activarse de verdad, para no bloquear al usuario si escanea mal)."""
    secret = generar_2fa_secret()
    usuario.two_factor_secret = secret
    await db.commit()
    return Activar2FARespuesta(secret=secret, otpauth_uri=generar_2fa_uri(secret, usuario.email))


@router.post("/2fa/confirmar", status_code=204)
async def confirmar_2fa(
    payload: Confirmar2FA, usuario: Usuario = Depends(get_usuario_orm), db: AsyncSession = Depends(get_db)
):
    if not usuario.two_factor_secret:
        raise HTTPException(400, "Primero llama a /api/auth/2fa/iniciar.")
    if not verificar_2fa_codigo(usuario.two_factor_secret, payload.codigo):
        raise HTTPException(400, "Código incorrecto. Intenta de nuevo.")
    usuario.two_factor_enabled = True
    await db.commit()
