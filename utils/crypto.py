# Copyright (c) 2025-2026 Sunet.
# Contributor: Kristofer Hallin
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from nicegui import app

import base64
import os


def get_browser_id() -> str:
    """
    Get the browser ID from the NiceGUI app storage.

    Returns:
        str: The browser ID.
    """

    return app.storage.browser["id"]


def _derive_key(key: str, salt: bytes) -> bytes:
    """
    Derive a key from the given key and salt using HKDF.

    The input key is already high-entropy (browser token + server secret),
    so HKDF is appropriate here instead of a slow password-based KDF.

    Args:
        key (str): The input key.
        salt (bytes): The salt to use for key derivation.
    Returns:
        bytes: The derived key.
    """

    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        info=b"scribe-storage-key",
    )

    return hkdf.derive(key.encode())


def encrypt_string(plaintext: str, key: str, salt: bytes, aad: bytes = b"") -> str:
    """
    Encrypt a string using AES-GCM with a derived key.

    Args:
        plaintext (str): The string to encrypt.
        key (str): The input key for key derivation.
        salt (bytes): The salt to use for key derivation.
        aad (bytes, optional): Additional authenticated data. Defaults to b"".
    Returns:
        str: The encrypted string, encoded in base64.
    """

    derived_key = _derive_key(key, salt)
    aesgcm = AESGCM(derived_key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), aad if aad else None)

    return base64.b64encode(nonce + ciphertext).decode()


def decrypt_string(encrypted: str, key: str, salt: bytes, aad: bytes = b"") -> str:
    """
    Decrypt a string that was encrypted with AES-GCM and a derived key.
    Args:
        encrypted (str): The encrypted string, encoded in base64.
        key (str): The input key for key derivation.
        salt (bytes): The salt to use for key derivation.
        aad (bytes, optional): Additional authenticated data. Defaults to b"".

    Returns:
        str: The decrypted plaintext string.
    """

    derived_key = _derive_key(key, salt)
    raw = base64.b64decode(encrypted)
    nonce = raw[:12]
    ciphertext = raw[12:]
    aesgcm = AESGCM(derived_key)
    plaintext = aesgcm.decrypt(nonce, ciphertext, aad if aad else None)

    return plaintext.decode()
