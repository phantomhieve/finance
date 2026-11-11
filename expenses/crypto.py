"""Symmetric encryption for secrets stored in the DB (Gmail refresh tokens, statement PDF passwords).

Key resolution: EXPENSES_ENCRYPTION_KEY (a Fernet key) if set, else derived from SECRET_KEY.
Rotating either invalidates stored values — users then reconnect Gmail / re-enter passwords.
"""
import base64
import functools
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


@functools.lru_cache(maxsize=8)
def _fernet_for_key(env_key: str, secret_key: str, debug: bool) -> Fernet:
    key = env_key
    if not key:
        if not debug and (
            not secret_key
            or len(secret_key) < 32
            or secret_key.startswith('django-insecure-')
        ):
            raise RuntimeError(
                "EXPENSES_ENCRYPTION_KEY or a strong (>=32-char) DJANGO_SECRET_KEY "
                "must be configured when DEBUG=False."
            )
        digest = hashlib.sha256(b'vault-expenses:' + secret_key.encode()).digest()
        key = base64.urlsafe_b64encode(digest).decode()
    return Fernet(key.encode())


def _fernet() -> Fernet:
    return _fernet_for_key(
        os.environ.get('EXPENSES_ENCRYPTION_KEY', '').strip(),
        getattr(settings, 'SECRET_KEY', '') or '',
        bool(getattr(settings, 'DEBUG', False)),
    )


def encrypt(plaintext):
    if not plaintext:
        return ''
    return _fernet().encrypt(plaintext.encode()).decode()


def encrypt_bytes(data):
    return _fernet().encrypt(data) if data else b''


def decrypt_bytes(token):
    """Bytes back, or b'' if empty / encrypted with another key."""
    if not token:
        return b''
    try:
        return _fernet().decrypt(bytes(token))
    except InvalidToken:
        return b''


def decrypt(token):
    """Return the plaintext, or '' if the value is empty or was encrypted with another key."""
    if not token:
        return ''
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        return ''
