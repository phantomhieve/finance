"""Symmetric encryption for secrets stored in the DB (Gmail refresh tokens, statement PDF passwords).

Key resolution: EXPENSES_ENCRYPTION_KEY (a Fernet key) if set, else derived from SECRET_KEY.
Rotating either invalidates stored values — users then reconnect Gmail / re-enter passwords.
"""
import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _fernet():
    key = os.environ.get('EXPENSES_ENCRYPTION_KEY', '').strip()
    if not key:
        digest = hashlib.sha256(b'vault-expenses:' + settings.SECRET_KEY.encode()).digest()
        key = base64.urlsafe_b64encode(digest).decode()
    return Fernet(key.encode())


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
