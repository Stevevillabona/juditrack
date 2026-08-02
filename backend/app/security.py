from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pyotp
from jose import JWTError, jwt
from passlib.context import CryptContext

JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-cambiar-en-produccion")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 12

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def crear_access_token(usuario_id: UUID, firma_id: UUID, rol: str) -> str:
    expira = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(usuario_id),
        "firma_id": str(firma_id),
        "rol": rol,
        "exp": expira,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decodificar_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        return None


# --- 2FA (TOTP, compatible con Google Authenticator / Authy) ---

def generar_2fa_secret() -> str:
    return pyotp.random_base32()


def generar_2fa_uri(secret: str, email: str) -> str:
    return pyotp.totp.TOTP(secret).provisioning_uri(name=email, issuer_name="JudiTrack")


def verificar_2fa_codigo(secret: str, codigo: str) -> bool:
    return pyotp.totp.TOTP(secret).verify(codigo, valid_window=1)
