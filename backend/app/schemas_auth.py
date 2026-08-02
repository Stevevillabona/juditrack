from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, EmailStr


class RegistroFirma(BaseModel):
    nombre_firma: str
    nombre_usuario: str
    email: EmailStr
    password: str


class Login(BaseModel):
    email: EmailStr
    password: str
    codigo_2fa: str | None = None


class TokenRespuesta(BaseModel):
    access_token: str
    token_type: str = "bearer"
    requiere_2fa_setup: bool = False


class Activar2FARespuesta(BaseModel):
    secret: str
    otpauth_uri: str


class Confirmar2FA(BaseModel):
    codigo: str
