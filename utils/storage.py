import base64
import os
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from nicegui import app
from utils.settings import get_settings

settings = get_settings()

# Keys whose values are encrypted with a per-browser key and stored in
# app.storage.user.  The browser key lives only in app.storage.browser
# (a signed cookie) and is never persisted to disk on the server.
SECRET_KEYS = frozenset({"encryption_password"})


def _derive_key(ikm: bytes, salt: bytes) -> bytes:
    """Derive a 256-bit AES key using HKDF."""
    hkdf = HKDF(
        algorithm=SHA256(),
        length=32,
        salt=salt,
        info=b"browser-storage",
    )
    return hkdf.derive(ikm)


def _get_aesgcm(browser_key: str) -> AESGCM:
    """
    Get an AESGCM instance keyed by the browser key + STORAGE_SECRET.

    The salt is stored in app.storage.user (server-side, not secret).
    """
    salt_hex = app.storage.user.get("salt")

    if not salt_hex:
        salt = os.urandom(16)
        salt_hex = salt.hex()
        app.storage.user["salt"] = salt_hex

    salt = bytes.fromhex(salt_hex)
    # Use browser_key as IKM and STORAGE_SECRET-derived bytes as HKDF salt,
    # so both are required independently for key derivation.
    storage_salt = HKDF(
        algorithm=SHA256(),
        length=32,
        salt=salt,
        info=b"storage-secret",
    ).derive(settings.STORAGE_SECRET.encode())
    key = _derive_key(browser_key.encode(), storage_salt)

    return AESGCM(key)


def _encrypt(value: str, browser_key: str, aad: str) -> str:
    """Encrypt a string value using AES-256-GCM with AAD, returned as base64."""
    aesgcm = _get_aesgcm(browser_key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, value.encode(), aad.encode())

    return base64.urlsafe_b64encode(nonce + ciphertext).decode()


def _decrypt(value: str, browser_key: str, aad: str) -> str:
    """Decrypt a base64-encoded AES-256-GCM ciphertext with AAD verification."""
    aesgcm = _get_aesgcm(browser_key)
    raw = base64.urlsafe_b64decode(value.encode())
    nonce = raw[:12]
    ciphertext = raw[12:]

    return aesgcm.decrypt(nonce, ciphertext, aad.encode()).decode()


# --- URL-safe encryption (for video proxy query params) ---
# Uses only STORAGE_SECRET so the server can decrypt without browser context.


def _derive_url_key(salt: bytes) -> bytes:
    hkdf = HKDF(
        algorithm=SHA256(),
        length=32,
        salt=salt,
        info=b"url-param",
    )
    return hkdf.derive(settings.STORAGE_SECRET.encode())


def encrypt_for_url(value: str) -> str:
    """Encrypt a value for use in URL query params (server-only secret)."""
    salt = os.urandom(16)
    key = _derive_url_key(salt)
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, value.encode(), None)

    return base64.urlsafe_b64encode(salt + nonce + ciphertext).decode()


def decrypt_from_url(value: str) -> str:
    """Decrypt a value from a URL query param."""
    raw = base64.urlsafe_b64decode(value.encode())
    salt = raw[:16]
    nonce = raw[16:28]
    ciphertext = raw[28:]
    key = _derive_url_key(salt)
    aesgcm = AESGCM(key)

    return aesgcm.decrypt(nonce, ciphertext, None).decode()


class Storage:
    """
    Unified storage with two backends:

    - Secret keys (encryption_password): encrypted with a per-browser random
      key and stored in app.storage.user.  The browser key lives only in
      app.storage.browser (a signed cookie that is never written to disk).
    - All other keys: stored in app.storage.user (server-side per-user files).
    """

    def ensure_browser_key(self) -> None:
        """
        Generate a random browser key if one doesn't exist yet.

        Must be called at the top of page handlers, before any await,
        while app.storage.browser is still writable.
        """
        if not app.storage.browser.get("_bk"):
            app.storage.browser["_bk"] = secrets.token_urlsafe(32)

    def _get_browser_key(self) -> str | None:
        return app.storage.browser.get("_bk")

    def __setitem__(self, key: str, value):
        if key in SECRET_KEYS:
            if value is None:
                app.storage.user.pop(f"_secret_{key}", None)
            else:
                browser_key = self._get_browser_key()
                if browser_key:
                    encrypted = _encrypt(str(value), browser_key, key)
                    app.storage.user[f"_secret_{key}"] = encrypted
        else:
            app.storage.user[key] = value

    def __getitem__(self, key: str):
        if key in SECRET_KEYS:
            browser_key = self._get_browser_key()
            if not browser_key:
                raise KeyError(key)

            value = app.storage.user.get(f"_secret_{key}")
            if value is None:
                raise KeyError(key)

            return _decrypt(value, browser_key, key)

        return app.storage.user[key]

    def get(self, key: str, default=None):
        if key in SECRET_KEYS:
            browser_key = self._get_browser_key()
            if not browser_key:
                return default

            value = app.storage.user.get(f"_secret_{key}")
            if value is None:
                return default

            try:
                return _decrypt(value, browser_key, key)
            except Exception:
                return default

        return app.storage.user.get(key, default)

    def __contains__(self, key: str) -> bool:
        if key in SECRET_KEYS:
            return f"_secret_{key}" in app.storage.user

        return key in app.storage.user

    def __delitem__(self, key: str):
        if key in SECRET_KEYS:
            app.storage.user.pop(f"_secret_{key}", None)
        else:
            del app.storage.user[key]


storage = Storage()
