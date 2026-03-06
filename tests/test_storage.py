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

import base64
from unittest.mock import MagicMock, patch

import pytest

from utils.crypto import encrypt_string, decrypt_string


TEST_KEY = "my-secret-key"
TEST_SALT = b"test-salt-value!"
TEST_AAD = b"test-aad"
NONCE_LENGTH = 12

BROWSER_KEY = "browser-key-abc123"
STORAGE_SECRET = "storage-secret-xyz"
BROWSER_ID = "browser-uuid-456"


class TestEncryptDecryptRoundTrip:
    def test_string_value(self):
        encrypted = encrypt_string("hello world", TEST_KEY, TEST_SALT)
        assert encrypted != "hello world"
        assert decrypt_string(encrypted, TEST_KEY, TEST_SALT) == "hello world"

    def test_empty_string(self):
        encrypted = encrypt_string("", TEST_KEY, TEST_SALT)
        assert decrypt_string(encrypted, TEST_KEY, TEST_SALT) == ""

    def test_with_aad(self):
        encrypted = encrypt_string("secret", TEST_KEY, TEST_SALT, TEST_AAD)
        assert decrypt_string(encrypted, TEST_KEY, TEST_SALT, TEST_AAD) == "secret"

    def test_wrong_aad_fails(self):
        encrypted = encrypt_string("secret", TEST_KEY, TEST_SALT, TEST_AAD)
        with pytest.raises(Exception):
            decrypt_string(encrypted, TEST_KEY, TEST_SALT, b"wrong-aad")

    def test_wrong_key_fails(self):
        encrypted = encrypt_string("secret", TEST_KEY, TEST_SALT)
        with pytest.raises(Exception):
            decrypt_string(encrypted, "wrong-key", TEST_SALT)

    def test_wrong_salt_fails(self):
        encrypted = encrypt_string("secret", TEST_KEY, TEST_SALT)
        with pytest.raises(Exception):
            decrypt_string(encrypted, TEST_KEY, b"wrong-salt-value")

    def test_ciphertext_is_base64(self):
        encrypted = encrypt_string("test", TEST_KEY, TEST_SALT)
        raw = base64.b64decode(encrypted)
        assert len(raw) > NONCE_LENGTH

    def test_different_nonces_produce_different_ciphertext(self):
        ct1 = encrypt_string("same", TEST_KEY, TEST_SALT)
        ct2 = encrypt_string("same", TEST_KEY, TEST_SALT)
        assert ct1 != ct2  # random nonce each time

    def test_unicode_value(self):
        text = "hej \u00e5\u00e4\u00f6 \U0001f600"
        encrypted = encrypt_string(text, TEST_KEY, TEST_SALT)
        assert decrypt_string(encrypted, TEST_KEY, TEST_SALT) == text


class TestStorageEncryptDecrypt:
    @pytest.fixture
    def mock_deps(self):
        mock_app = MagicMock()
        mock_app.storage.browser = {"_scribe_bk": BROWSER_KEY}

        mock_settings = MagicMock()
        mock_settings.STORAGE_SECRET = STORAGE_SECRET

        with (
            patch("utils.helpers.app", mock_app),
            patch("utils.helpers.get_browser_id", return_value=BROWSER_ID),
            patch("utils.helpers.settings", mock_settings),
        ):
            from utils.helpers import storage_encrypt, storage_decrypt

            yield storage_encrypt, storage_decrypt

    def test_round_trip(self, mock_deps):
        storage_encrypt, storage_decrypt = mock_deps
        encrypted = storage_encrypt("my-password")
        assert encrypted != "my-password"
        assert storage_decrypt(encrypted) == "my-password"

    def test_empty_string_returns_none(self, mock_deps):
        _, storage_decrypt = mock_deps
        assert storage_decrypt("") is None

    def test_none_returns_none(self, mock_deps):
        _, storage_decrypt = mock_deps
        assert storage_decrypt(None) is None

    def test_unicode(self, mock_deps):
        storage_encrypt, storage_decrypt = mock_deps
        text = "l\u00f6senord \U0001f511"
        encrypted = storage_encrypt(text)
        assert storage_decrypt(encrypted) == text

    def test_invalid_ciphertext_returns_none_and_redirects(self):
        mock_app = MagicMock()
        mock_app.storage.browser = {"_scribe_bk": BROWSER_KEY}
        mock_app.storage.user = {"encryption_password": "garbage-data"}

        mock_settings = MagicMock()
        mock_settings.STORAGE_SECRET = STORAGE_SECRET

        mock_ui = MagicMock()

        with (
            patch("utils.helpers.app", mock_app),
            patch("utils.helpers.ui", mock_ui),
            patch("utils.helpers.get_browser_id", return_value=BROWSER_ID),
            patch("utils.helpers.settings", mock_settings),
        ):
            from utils.helpers import storage_decrypt

            result = storage_decrypt("not-valid-base64-ciphertext!")
            assert result is None
            assert mock_app.storage.user["encryption_password"] is None
            mock_ui.navigate.to.assert_called_once_with("/")

    def test_different_browser_key_returns_none_and_redirects(self):
        mock_app = MagicMock()
        mock_app.storage.user = {}
        mock_settings = MagicMock()
        mock_settings.STORAGE_SECRET = STORAGE_SECRET
        mock_ui = MagicMock()

        # Encrypt with one browser key
        mock_app.storage.browser = {"_scribe_bk": "key-1"}
        with (
            patch("utils.helpers.app", mock_app),
            patch("utils.helpers.ui", mock_ui),
            patch("utils.helpers.get_browser_id", return_value=BROWSER_ID),
            patch("utils.helpers.settings", mock_settings),
        ):
            from utils.helpers import storage_encrypt, storage_decrypt

            encrypted = storage_encrypt("secret")

        # Decrypt with different browser key
        mock_app.storage.browser = {"_scribe_bk": "key-2"}
        with (
            patch("utils.helpers.app", mock_app),
            patch("utils.helpers.ui", mock_ui),
            patch("utils.helpers.get_browser_id", return_value=BROWSER_ID),
            patch("utils.helpers.settings", mock_settings),
        ):
            result = storage_decrypt(encrypted)
            assert result is None
            assert mock_app.storage.user["encryption_password"] is None
            mock_ui.navigate.to.assert_called_with("/")
