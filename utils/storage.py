import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from nicegui import app
from nicegui.storage import request_contextvar
from utils.settings import get_settings

settings = get_settings()

def get_session_id() -> str:
    """
    Get the NiceGUI browser session ID from the request context.
    """
    
    request = request_contextvar.get()
    
    if request and hasattr(request, "session") and "id" in request.session:
        return request.session["id"]
    
    return ""


def derive_key(storage_secret: str, salt: bytes, session_id: str) -> bytes:
    """
    Derive a 256-bit AES key using HKDF.
    """
    
    hkdf = HKDF(
        algorithm=SHA256(),
        length=32,
        salt=salt,
        info=session_id.encode(),
    )
    
    return hkdf.derive(storage_secret.encode())


class EncryptedStorage:
    """
    A transparent encryption wrapper around NiceGUI's app.storage.user.

    All values are encrypted at rest using AES-256-GCM.
    The encryption key is derived via HKDF from:
      - STORAGE_SECRET (server-wide, from settings)
      - A random per-user salt (stored as _salt in the same storage)
      - The NiceGUI browser session UUID
    """

    def __get_aesgcm(self) -> AESGCM:
        """
        Get an AESGCM instance initialized with the derived key.

        Returns:
            AESGCM: An instance of AESGCM initialized with the derived key.
        """

        raw = app.storage.user
        salt_hex = raw.get("salt")

        if not salt_hex:
            salt = os.urandom(16)
            raw["salt"] = salt.hex()
            salt_hex = salt.hex()

        salt = bytes.fromhex(salt_hex)
        session_id = get_session_id()
        key = derive_key(settings.STORAGE_SECRET, salt, session_id)

        return AESGCM(key)

    def __encrypt(self, value):
        """
        Encrypt a value using AES-256-GCM.
        
        Parameters:
            value: The value to encrypt.
        
        Returns:
            str: The encrypted value, encoded in base64.
        """

        if value is None:
            return None

        aesgcm = self.__get_aesgcm()
        nonce = os.urandom(12)
        ciphertext = aesgcm.encrypt(nonce, str(value).encode(), None)
        
        return base64.urlsafe_b64encode(nonce + ciphertext).decode()

    def __decrypt(self, value):
        """
        Decrypt a value using AES-256-GCM.

        Parameters:
            value: The value to decrypt (base64-encoded).
        Returns:
            The decrypted value, or the original value if decryption fails (for plaintext migration).
        """

        if value is None:
            return None
        
        try:
            aesgcm = self.__get_aesgcm()
            raw = base64.urlsafe_b64decode(value.encode())
            nonce = raw[:12]
            ciphertext = raw[12:]
        
            return aesgcm.decrypt(nonce, ciphertext, None).decode()
        
        except Exception:
            # Plaintext migration: return value as-is if decryption fails
            return value

    def __setitem__(self, key: str, value):
        """
        Set a value in the encrypted storage.

        Parameters:
            key (str): The key to set.
            value: The value to set.

        Raises:
            KeyError: If the key is "salt", which is reserved for internal use.
        """

        if key == "salt":
            raise KeyError(f"'{"salt"}' is a reserved key")
        
        app.storage.user[key] = self.__encrypt(value)

    def __getitem__(self, key: str):
        """
        Get a value from the encrypted storage.

        Parameters:
            key (str): The key to get.

        Returns:
            The decrypted value associated with the key.

        Raises:
            KeyError: If the key is "salt", which is reserved for internal use.
        """

        if key == "salt":
            raise KeyError(f"'{"salt"}' is a reserved key")
        
        return self.__decrypt(app.storage.user[key])

    def get(self, key: str, default=None):
        """
        Get a value from the encrypted storage, with a default if the key is not found.

        Parameters:
            key (str): The key to get.
            default: The value to return if the key is not found.

        Returns:
            The decrypted value associated with the key, or the default if the key is not found.
        """

        if key == "salt":
            return default

        value = app.storage.user.get(key)

        if value is None:
            return default

        return self.__decrypt(value)

    def __contains__(self, key: str) -> bool:
        """
        Check if a key exists in the encrypted storage.

        Parameters:
            key (str): The key to check.

        Returns:
            bool: True if the key exists, False otherwise.
        """

        return key in app.storage.user

    def __delitem__(self, key: str):
        """
        Delete a key from the encrypted storage.

        Parameters:
            key (str): The key to delete.

        Raises:
            KeyError: If the key is "salt", which is reserved for internal use.
        """

        del app.storage.user[key]


storage = EncryptedStorage()
