import base64
from unittest.mock import MagicMock, patch

import pytest

NONCE_LENGTH = 12
TEST_SECRET = "test-secret-key"


def _make_mock_app(browser=None, user=None):
    mock_app = MagicMock()
    mock_app.storage.browser = browser if browser is not None else {}
    mock_app.storage.user = user if user is not None else {}
    return mock_app


@pytest.fixture
def mock_app():
    return _make_mock_app()


@pytest.fixture
def storage_instance(mock_app):
    """Storage with browser + user writable."""
    with (
        patch("utils.storage.app", mock_app),
        patch("utils.storage.get_settings") as mock_settings,
    ):
        mock_settings.return_value.STORAGE_SECRET = TEST_SECRET
        from utils.storage import Storage

        yield Storage(), mock_app


@pytest.fixture
def storage_with_browser_key(mock_app):
    """Storage with a browser key already set."""
    with (
        patch("utils.storage.app", mock_app),
        patch("utils.storage.get_settings") as mock_settings,
    ):
        mock_settings.return_value.STORAGE_SECRET = TEST_SECRET
        from utils.storage import Storage

        store = Storage()
        store.ensure_browser_key()
        yield store, mock_app


class TestNonSecretKeys:
    """Non-secret keys go to app.storage.user."""

    def test_set_and_get(self, storage_instance):
        store, mock = storage_instance
        store["token"] = "my-jwt"
        assert mock.storage.user["token"] == "my-jwt"
        assert store["token"] == "my-jwt"

    def test_get_default(self, storage_instance):
        store, _ = storage_instance
        assert store.get("missing") is None
        assert store.get("missing", "fallback") == "fallback"

    def test_contains(self, storage_instance):
        store, _ = storage_instance
        store["token"] = "x"
        assert "token" in store
        assert "missing" not in store

    def test_delete(self, storage_instance):
        store, mock = storage_instance
        store["token"] = "x"
        del store["token"]
        assert "token" not in mock.storage.user

    def test_none_value(self, storage_instance):
        store, mock = storage_instance
        store["token"] = None
        assert mock.storage.user["token"] is None

    def test_not_stored_in_browser(self, storage_instance):
        store, mock = storage_instance
        store["token"] = "my-jwt"
        assert "token" not in mock.storage.browser


class TestEnsureBrowserKey:
    """ensure_browser_key() creates a random key in app.storage.browser."""

    def test_creates_key(self, storage_instance):
        store, mock = storage_instance
        store.ensure_browser_key()
        assert "_bk" in mock.storage.browser
        assert len(mock.storage.browser["_bk"]) > 20

    def test_idempotent(self, storage_instance):
        store, mock = storage_instance
        store.ensure_browser_key()
        first_key = mock.storage.browser["_bk"]
        store.ensure_browser_key()
        assert mock.storage.browser["_bk"] == first_key


class TestSecretKeys:
    """Secret keys are encrypted with browser key and stored in app.storage.user."""

    def test_set_writes_encrypted_to_user_storage(self, storage_with_browser_key):
        store, mock = storage_with_browser_key
        store["encryption_password"] = "my-secret"
        raw = mock.storage.user["_secret_encryption_password"]
        assert raw != "my-secret"
        # Should be valid base64
        decoded = base64.urlsafe_b64decode(raw.encode())
        assert len(decoded) > NONCE_LENGTH

    def test_get_decrypts(self, storage_with_browser_key):
        store, _ = storage_with_browser_key
        store["encryption_password"] = "my-secret"
        assert store.get("encryption_password") == "my-secret"

    def test_getitem_decrypts(self, storage_with_browser_key):
        store, _ = storage_with_browser_key
        store["encryption_password"] = "my-secret"
        assert store["encryption_password"] == "my-secret"

    def test_set_none_clears(self, storage_with_browser_key):
        store, mock = storage_with_browser_key
        store["encryption_password"] = "my-secret"
        store["encryption_password"] = None
        assert "_secret_encryption_password" not in mock.storage.user
        assert store.get("encryption_password") is None

    def test_delete(self, storage_with_browser_key):
        store, mock = storage_with_browser_key
        store["encryption_password"] = "my-secret"
        del store["encryption_password"]
        assert "_secret_encryption_password" not in mock.storage.user

    def test_contains(self, storage_with_browser_key):
        store, _ = storage_with_browser_key
        store["encryption_password"] = "my-secret"
        assert "encryption_password" in store

    def test_not_contains_when_missing(self, storage_with_browser_key):
        store, _ = storage_with_browser_key
        assert "encryption_password" not in store

    def test_not_stored_in_browser(self, storage_with_browser_key):
        store, mock = storage_with_browser_key
        store["encryption_password"] = "my-secret"
        assert "encryption_password" not in mock.storage.browser

    def test_get_returns_default_without_browser_key(self, storage_instance):
        store, mock = storage_instance
        # No browser key set
        assert store.get("encryption_password") is None
        assert store.get("encryption_password", "fallback") == "fallback"

    def test_getitem_raises_without_browser_key(self, storage_instance):
        store, _ = storage_instance
        with pytest.raises(KeyError):
            _ = store["encryption_password"]

    def test_set_ignored_without_browser_key(self, storage_instance):
        store, mock = storage_instance
        # No browser key — set should be a no-op
        store["encryption_password"] = "my-secret"
        assert "_secret_encryption_password" not in mock.storage.user

    def test_different_browser_keys_produce_different_ciphertext(self, mock_app):
        with (
            patch("utils.storage.app", mock_app),
            patch("utils.storage.get_settings") as mock_settings,
        ):
            mock_settings.return_value.STORAGE_SECRET = TEST_SECRET
            from utils.storage import Storage

            store = Storage()
            store.ensure_browser_key()
            store["encryption_password"] = "same-password"
            ct1 = mock_app.storage.user["_secret_encryption_password"]

            # Change browser key
            mock_app.storage.browser["_bk"] = "different-browser-key"
            store["encryption_password"] = "same-password"
            ct2 = mock_app.storage.user["_secret_encryption_password"]

            assert ct1 != ct2


class TestSalt:
    """Salt is stored in app.storage.user."""

    def test_salt_created_in_user_storage(self, storage_with_browser_key):
        store, mock = storage_with_browser_key
        store["encryption_password"] = "x"
        assert "salt" in mock.storage.user
        assert len(bytes.fromhex(mock.storage.user["salt"])) == 16

    def test_salt_reused(self, storage_with_browser_key):
        store, mock = storage_with_browser_key
        store["encryption_password"] = "x"
        salt1 = mock.storage.user["salt"]
        store["encryption_password"] = "y"
        assert mock.storage.user["salt"] == salt1

    def test_salt_not_in_browser(self, storage_with_browser_key):
        store, mock = storage_with_browser_key
        store["encryption_password"] = "x"
        assert "salt" not in mock.storage.browser


class TestUrlEncryption:
    """encrypt_for_url / decrypt_from_url for video proxy."""

    def test_roundtrip(self):
        with patch("utils.storage.get_settings") as mock_settings:
            mock_settings.return_value.STORAGE_SECRET = TEST_SECRET
            from utils.storage import decrypt_from_url, encrypt_for_url

            encrypted = encrypt_for_url("my-password")
            assert encrypted != "my-password"
            assert decrypt_from_url(encrypted) == "my-password"

    def test_empty_string(self):
        with patch("utils.storage.get_settings") as mock_settings:
            mock_settings.return_value.STORAGE_SECRET = TEST_SECRET
            from utils.storage import decrypt_from_url, encrypt_for_url

            encrypted = encrypt_for_url("")
            assert decrypt_from_url(encrypted) == ""

    def test_different_encryptions_differ(self):
        with patch("utils.storage.get_settings") as mock_settings:
            mock_settings.return_value.STORAGE_SECRET = TEST_SECRET
            from utils.storage import encrypt_for_url

            ct1 = encrypt_for_url("password")
            ct2 = encrypt_for_url("password")
            # Different nonces produce different ciphertext
            assert ct1 != ct2
