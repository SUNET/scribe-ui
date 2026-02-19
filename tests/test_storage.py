import os
import base64
from unittest.mock import MagicMock, patch

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


SALT_KEY = "_salt"
NONCE_LENGTH = 12
TEST_SECRET = "test-secret-key"
TEST_SESSION_ID = "abc123-session-uuid"


def _derive_key(storage_secret, salt, session_id):
    hkdf = HKDF(algorithm=SHA256(), length=32, salt=salt, info=session_id.encode())
    return hkdf.derive(storage_secret.encode())


@pytest.fixture
def mock_storage():
    """Mock NiceGUI app.storage.user as a plain dict."""
    backing = {}
    mock_app = MagicMock()
    mock_app.storage.user = backing
    return backing, mock_app


@pytest.fixture
def mock_request():
    """Mock NiceGUI request_contextvar with a session ID."""
    request = MagicMock()
    request.session = {"id": TEST_SESSION_ID}
    return request


@pytest.fixture
def encrypted_storage(mock_storage, mock_request):
    """Create an EncryptedStorage with mocked dependencies."""
    backing, mock_app = mock_storage

    with (
        patch("utils.storage.app", mock_app),
        patch("utils.storage.request_contextvar") as mock_ctx,
        patch("utils.storage.get_settings") as mock_settings,
    ):
        mock_ctx.get.return_value = mock_request
        mock_settings.return_value.STORAGE_SECRET = TEST_SECRET

        from utils.storage import EncryptedStorage

        store = EncryptedStorage()
        yield store, backing


class TestEncryptDecryptRoundTrip:
    def test_string_value(self, encrypted_storage):
        store, backing = encrypted_storage
        store["token"] = "my-secret-token"
        assert backing.get("token") != "my-secret-token"  # encrypted
        assert store["token"] == "my-secret-token"

    def test_none_value(self, encrypted_storage):
        store, backing = encrypted_storage
        store["key"] = None
        assert backing["key"] is None
        assert store.get("key") is None

    def test_empty_string(self, encrypted_storage):
        store, backing = encrypted_storage
        store["key"] = ""
        assert store["key"] == ""

    def test_multiple_keys(self, encrypted_storage):
        store, _ = encrypted_storage
        store["a"] = "value_a"
        store["b"] = "value_b"
        assert store["a"] == "value_a"
        assert store["b"] == "value_b"

    def test_overwrite_value(self, encrypted_storage):
        store, _ = encrypted_storage
        store["key"] = "first"
        store["key"] = "second"
        assert store["key"] == "second"


class TestGetMethod:
    def test_get_existing(self, encrypted_storage):
        store, _ = encrypted_storage
        store["key"] = "value"
        assert store.get("key") == "value"

    def test_get_missing_returns_default(self, encrypted_storage):
        store, _ = encrypted_storage
        assert store.get("missing") is None
        assert store.get("missing", "fallback") == "fallback"

    def test_get_with_custom_default(self, encrypted_storage):
        store, _ = encrypted_storage
        assert store.get("x", "default_val") == "default_val"


class TestPlaintextMigration:
    def test_reads_plaintext_when_decryption_fails(self, encrypted_storage):
        store, backing = encrypted_storage
        # Simulate pre-existing plaintext data
        backing["old_token"] = "plaintext-jwt-token"
        assert store.get("old_token") == "plaintext-jwt-token"

    def test_reads_plaintext_getitem(self, encrypted_storage):
        store, backing = encrypted_storage
        backing["legacy"] = "legacy-value"
        assert store["legacy"] == "legacy-value"


class TestSaltKey:
    def test_salt_is_generated(self, encrypted_storage):
        store, backing = encrypted_storage
        store["key"] = "value"
        assert SALT_KEY in backing
        assert len(bytes.fromhex(backing[SALT_KEY])) == 16

    def test_salt_reserved_setitem(self, encrypted_storage):
        store, _ = encrypted_storage
        with pytest.raises(KeyError, match="reserved"):
            store[SALT_KEY] = "value"

    def test_salt_reserved_getitem(self, encrypted_storage):
        store, _ = encrypted_storage
        with pytest.raises(KeyError, match="reserved"):
            _ = store[SALT_KEY]

    def test_salt_get_returns_default(self, encrypted_storage):
        store, _ = encrypted_storage
        assert store.get(SALT_KEY) is None
        assert store.get(SALT_KEY, "x") == "x"

    def test_same_salt_reused(self, encrypted_storage):
        store, backing = encrypted_storage
        store["a"] = "1"
        salt1 = backing[SALT_KEY]
        store["b"] = "2"
        salt2 = backing[SALT_KEY]
        assert salt1 == salt2


class TestContainsAndDelete:
    def test_contains(self, encrypted_storage):
        store, _ = encrypted_storage
        store["key"] = "value"
        assert "key" in store
        assert "missing" not in store

    def test_delete(self, encrypted_storage):
        store, backing = encrypted_storage
        store["key"] = "value"
        del store["key"]
        assert "key" not in backing


class TestKeyDerivation:
    def test_different_secrets_produce_different_ciphertext(self, mock_storage, mock_request):
        backing, mock_app = mock_storage

        from utils.storage import EncryptedStorage

        ciphertexts = []
        for secret in ["secret-1", "secret-2"]:
            backing.clear()
            with (
                patch("utils.storage.app", mock_app),
                patch("utils.storage.request_contextvar") as mock_ctx,
                patch("utils.storage.get_settings") as mock_settings,
            ):
                mock_ctx.get.return_value = mock_request
                mock_settings.return_value.STORAGE_SECRET = secret
                store = EncryptedStorage()
                store["key"] = "same-value"
                ciphertexts.append(backing["key"])

        # Different secrets should produce different ciphertext
        # (they also have different salts, so this is guaranteed)
        assert ciphertexts[0] != ciphertexts[1]

    def test_ciphertext_is_base64(self, encrypted_storage):
        store, backing = encrypted_storage
        store["key"] = "test"
        # Should be valid base64
        raw = base64.urlsafe_b64decode(backing["key"].encode())
        assert len(raw) > NONCE_LENGTH  # nonce + ciphertext
