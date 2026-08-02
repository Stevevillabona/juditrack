from __future__ import annotations

from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import RolUsuario, Usuario
from app.security import decodificar_access_token

bearer_scheme = HTTPBearer()


class UsuarioActual:
    def __init__(self, id: UUID, firma_id: UUID, rol: RolUsuario):
        self.id = id
        self.firma_id = firma_id
        self.rol = rol


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> UsuarioActual:
    payload = decodificar_access_token(credentials.credentials)
    if payload is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token inválido o expirado.")
    return UsuarioActual(
        id=UUID(payload["sub"]),
        firma_id=UUID(payload["firma_id"]),
        rol=RolUsuario(payload["rol"]),
    )


def requiere_rol(*roles_permitidos: RolUsuario):
    async def _check(usuario: UsuarioActual = Depends(get_current_user)) -> UsuarioActual:
        if usuario.rol not in roles_permitidos:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "No tienes permiso para esta acción.")
        return usuario

    return _check


async def get_usuario_orm(
    usuario: UsuarioActual = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> Usuario:
    result = await db.execute(select(Usuario).where(Usuario.id == usuario.id))
    orm_usuario = result.scalar_one_or_none()
    if orm_usuario is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuario no encontrado.")
    return orm_usuario
