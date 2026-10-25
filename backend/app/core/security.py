from base64 import urlsafe_b64encode
from datetime import datetime, timedelta, timezone
import hashlib
import secrets
import jwt
from cryptography.fernet import Fernet, InvalidToken
from pwdlib import PasswordHash
from app.models.user import User
from sqlalchemy import select
from app.core.database import settings


JWT_ALGORITHM = "HS256"
DUMMY_HASH = "$argon2id$v=19$m=65536,t=3,p=4$MjQyZWE1MzBjYjJlZTI0Yw$YTU4NGM5ZTZmYjE2NzZlZjY0ZWY3ZGRkY2U2OWFjNjk"


password_hash = PasswordHash.recommended()


def _wargaming_token_cipher() -> Fernet:
    key_material = hashlib.sha256(
        b"wargaming-access-token:" + settings.secret_key.encode()
    ).digest()
    return Fernet(urlsafe_b64encode(key_material))


def encrypt_wargaming_access_token(access_token: str) -> str:
    return _wargaming_token_cipher().encrypt(access_token.encode()).decode()


def decrypt_wargaming_access_token(encrypted_token: str) -> str:
    try:
        return _wargaming_token_cipher().decrypt(encrypted_token.encode()).decode()
    except (InvalidToken, UnicodeDecodeError) as exc:
        raise ValueError("Unable to decrypt the stored Wargaming access token") from exc


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(plain_password, hashed_password):
    return password_hash.verify(plain_password, hashed_password)


async def authenticate_user(
    session,
    username: str, 
    password: str,
):
    user = await session.scalar(select(User).where(User.name == username))

    if not user:
        # Prevent timing attacks by running password verification even when user doesn't exist
        # This ensures the response time is similar whether or not the email exists
        verify_password(password, DUMMY_HASH)
        return None

    if user.password_hash is None:
        verify_password(password, DUMMY_HASH)
        return None

    if verify_password(password, user.password_hash):
        return user


def create_access_token(subject: str):

    claims = {
        "sub": subject,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    }
        
    encoded_jwt = jwt.encode(
        claims, 
        settings.secret_key, 
        algorithm=JWT_ALGORITHM
    )
    return encoded_jwt


def create_wg_registration_token(
    account_id: int,
    nickname: str,
    encrypted_access_token: str,
    access_token_expires_at: datetime,
) -> str:
    claims = {
        "purpose": "wg_registration",
        "wg_account_id": account_id,
        "wg_nickname": nickname,
        "wg_access_token_encrypted": encrypted_access_token,
        "wg_access_token_expires_at": int(access_token_expires_at.timestamp()),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
    }
    return jwt.encode(claims, settings.secret_key, algorithm=JWT_ALGORITHM)


def create_wg_login_state() -> str:
    claims = {
        "purpose": "wg_login_state",
        "nonce": secrets.token_urlsafe(16),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
    }
    return jwt.encode(claims, settings.secret_key, algorithm=JWT_ALGORITHM)


def create_wg_link_state(user_id: int) -> str:
    claims = {
        "purpose": "wg_link_state",
        "user_id": user_id,
        "nonce": secrets.token_urlsafe(16),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
    }
    return jwt.encode(claims, settings.secret_key, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    return jwt.decode(
        token,
        settings.secret_key,
        algorithms=[JWT_ALGORITHM],
    )