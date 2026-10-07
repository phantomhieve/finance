"""Minimal Gmail API client (OAuth 2.0 web-server flow + read-only message access).

Uses the same Google OAuth client as SSO login (GOOGLE_OAUTH_CLIENT_ID / _SECRET). The Gmail API
must be enabled on that project and ``<VAULT_PUBLIC_URL>/expenses/gmail/callback/`` added as an
authorised redirect URI. Keep the consent screen "In production" — in "Testing" Google expires
refresh tokens after 7 days.
"""
import base64
import logging
import os
import time
from urllib.parse import urlencode

import requests

from .parsing import clean_text, html_to_text

logger = logging.getLogger(__name__)

AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
TOKEN_URL = 'https://oauth2.googleapis.com/token'
REVOKE_URL = 'https://oauth2.googleapis.com/revoke'
API_BASE = 'https://gmail.googleapis.com/gmail/v1/users/me'
SCOPE = 'https://www.googleapis.com/auth/gmail.readonly'
TIMEOUT = 20


class GmailAuthError(Exception):
    """Refresh token revoked/expired — the user must reconnect."""


class GmailError(Exception):
    pass


def _client_credentials():
    client_id = os.environ.get('GOOGLE_OAUTH_CLIENT_ID', '')
    secret = os.environ.get('GOOGLE_OAUTH_CLIENT_SECRET', '')
    if not client_id or not secret:
        raise GmailError('Google OAuth is not configured (GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET).')
    return client_id, secret


def is_configured():
    return bool(os.environ.get('GOOGLE_OAUTH_CLIENT_ID') and os.environ.get('GOOGLE_OAUTH_CLIENT_SECRET'))


def build_auth_url(redirect_uri, state, login_hint=''):
    client_id, _ = _client_credentials()
    params = {
        'client_id': client_id,
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': SCOPE,
        'access_type': 'offline',
        # Account chooser so one person can connect several inboxes; consent so Google
        # re-issues a refresh token on reconnect.
        'prompt': 'select_account consent',
        'include_granted_scopes': 'false',
        'state': state,
    }
    if login_hint:
        params['login_hint'] = login_hint
    return f'{AUTH_URL}?{urlencode(params)}'


def exchange_code(code, redirect_uri):
    client_id, secret = _client_credentials()
    resp = requests.post(TOKEN_URL, data={
        'code': code, 'client_id': client_id, 'client_secret': secret,
        'redirect_uri': redirect_uri, 'grant_type': 'authorization_code',
    }, timeout=TIMEOUT)
    if resp.status_code != 200:
        raise GmailError(f'Token exchange failed ({resp.status_code}).')
    data = resp.json()
    if SCOPE not in (data.get('scope') or ''):
        raise GmailError('Gmail read access was not granted. Tick the Gmail checkbox on the consent screen.')
    if not data.get('refresh_token'):
        raise GmailError('Google did not return a refresh token. Remove Vault from your Google account '
                         'permissions and connect again.')
    return data


def revoke(refresh_token):
    if not refresh_token:
        return
    try:
        requests.post(REVOKE_URL, data={'token': refresh_token}, timeout=TIMEOUT)
    except requests.RequestException:
        logger.warning('Gmail token revoke request failed')


class GmailClient:
    def __init__(self, refresh_token):
        self.refresh_token = refresh_token
        self._access_token = None
        self._expires_at = 0

    def _token(self):
        if self._access_token and time.time() < self._expires_at - 60:
            return self._access_token
        client_id, secret = _client_credentials()
        resp = requests.post(TOKEN_URL, data={
            'client_id': client_id, 'client_secret': secret,
            'refresh_token': self.refresh_token, 'grant_type': 'refresh_token',
        }, timeout=TIMEOUT)
        if resp.status_code in (400, 401):
            raise GmailAuthError('Gmail access was revoked or expired — reconnect this mailbox.')
        if resp.status_code != 200:
            raise GmailError(f'Token refresh failed ({resp.status_code}).')
        data = resp.json()
        self._access_token = data['access_token']
        self._expires_at = time.time() + int(data.get('expires_in', 3600))
        return self._access_token

    def _get(self, path, params=None):
        for attempt in range(3):
            resp = requests.get(f'{API_BASE}{path}', params=params,
                                headers={'Authorization': f'Bearer {self._token()}'}, timeout=TIMEOUT)
            if resp.status_code == 401:
                self._access_token = None
                continue
            if resp.status_code in (429, 500, 503):
                time.sleep(2 ** attempt)
                continue
            if resp.status_code == 403 and 'insufficient' in resp.text.lower():
                raise GmailAuthError('Gmail read permission is missing — reconnect this mailbox.')
            if resp.status_code != 200:
                raise GmailError(f'Gmail API {path} failed ({resp.status_code}).')
            return resp.json()
        raise GmailError(f'Gmail API {path} kept failing.')

    def profile(self):
        return self._get('/profile')

    def list_message_ids(self, query, limit=500):
        ids, token = [], None
        while len(ids) < limit:
            params = {'q': query, 'maxResults': min(100, limit - len(ids))}
            if token:
                params['pageToken'] = token
            data = self._get('/messages', params)
            ids.extend(m['id'] for m in data.get('messages', []))
            token = data.get('nextPageToken')
            if not token:
                break
        return ids

    def get_message(self, message_id):
        return self._get(f'/messages/{message_id}', {'format': 'full'})

    def get_attachment(self, message_id, attachment_id):
        data = self._get(f'/messages/{message_id}/attachments/{attachment_id}')
        return decode_body(data.get('data', ''))


def decode_body(data):
    return base64.urlsafe_b64decode(data + '=' * (-len(data) % 4)) if data else b''


def _walk(part):
    yield part
    for child in part.get('parts', []) or []:
        yield from _walk(child)


def message_parts(message):
    """(headers dict, body text, [pdf attachment descriptors]) from a format=full message."""
    payload = message.get('payload', {})
    headers = {h['name'].lower(): h['value'] for h in payload.get('headers', [])}
    plain, rich, pdfs = [], [], []
    for part in _walk(payload):
        mime = part.get('mimeType', '')
        body = part.get('body', {}) or {}
        filename = part.get('filename') or ''
        if filename.lower().endswith('.pdf') or mime == 'application/pdf':
            pdfs.append({'filename': filename, 'attachment_id': body.get('attachmentId'), 'data': body.get('data')})
        elif mime == 'text/plain' and body.get('data'):
            plain.append(decode_body(body['data']).decode('utf-8', 'replace'))
        elif mime == 'text/html' and body.get('data'):
            rich.append(decode_body(body['data']).decode('utf-8', 'replace'))
    text = clean_text('\n'.join(plain))
    if len(text) < 40 and rich:
        text = html_to_text('\n'.join(rich))
    if not text:
        text = message.get('snippet', '')
    return headers, text, pdfs
