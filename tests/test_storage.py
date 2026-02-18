import pytest

from unittest.mock import patch
from utils.storage import MemoryStorage


class TestInMemStorage:
    """
    Test cases for MemoryStorage class.
    """

    @pytest.fixture
    def mock_app_storage(self):
        """
        Create a mock for NiceGUI app.storage.browser and force in-memory storage.
        """

        with patch("utils.storage.settings.STORAGE_IN_MEMORY", True):
            with patch("utils.storage.app") as mock_app:
                mock_app.storage.browser.get.return_value = "test-session-id"
                yield mock_app

    def test_init(self, mock_app_storage):
        """
        Test storage initialization.
        """

        storage = MemoryStorage()
        assert storage._MemoryStorage__storage == {}

    def test_add_and_get(self, mock_app_storage):
        """
        Test adding and getting values.
        """

        storage = MemoryStorage()
        storage.add("key1", "value1")

        assert storage.get("key1") == "value1"

    def test_get_default(self, mock_app_storage):
        """
        Test getting non-existent key returns default.
        """

        storage = MemoryStorage()

        assert storage.get("nonexistent") is None
        assert storage.get("nonexistent", "default") == "default"

    def test_delete(self, mock_app_storage):
        """
        Test deleting a key.
        """

        storage = MemoryStorage()
        storage.add("key1", "value1")
        storage.delete("key1")

        assert storage.get("key1") is None

    def test_delete_nonexistent_key(self, mock_app_storage):
        """
        Test deleting a non-existent key does not raise.
        """

        storage = MemoryStorage()
        storage.delete("nonexistent")  # Should not raise

    def test_dict_like_get(self, mock_app_storage):
        """
        Test dict-like access with [].
        """

        storage = MemoryStorage()
        storage.add("key1", "value1")

        assert storage["key1"] == "value1"

    def test_dict_like_set(self, mock_app_storage):
        """
        Test dict-like assignment with [].
        """

        storage = MemoryStorage()
        storage["key1"] = "value1"

        assert storage.get("key1") == "value1"

    def test_dict_like_delete(self, mock_app_storage):
        """
        Test dict-like deletion with del.
        """

        storage = MemoryStorage()
        storage["key1"] = "value1"

        del storage["key1"]

        assert storage.get("key1") is None

    def test_contains(self, mock_app_storage):
        """
        Test 'in' operator.
        """

        storage = MemoryStorage()
        storage.add("key1", "value1")

        assert "key1" in storage
        assert "nonexistent" not in storage

    def test_session_isolation(self, mock_app_storage):
        """
        Test that different sessions are isolated.
        """

        storage = MemoryStorage()

        # First session
        mock_app_storage.storage.browser.get.return_value = "session-1"
        storage.add("key", "session1-value")

        # Second session
        mock_app_storage.storage.browser.get.return_value = "session-2"
        storage.add("key", "session2-value")

        # Verify isolation
        mock_app_storage.storage.browser.get.return_value = "session-1"
        assert storage.get("key") == "session1-value"

        mock_app_storage.storage.browser.get.return_value = "session-2"
        assert storage.get("key") == "session2-value"

    def test_no_session_id_raises(self):
        """
        Test that missing session ID raises RuntimeError.
        """

        with patch("utils.storage.app") as mock_app:
            mock_app.storage.browser.get.return_value = None
            storage = MemoryStorage()

            with pytest.raises(RuntimeError, match="No browser session ID found"):
                storage.add("key", "value")

    def test_multiple_keys_same_session(self, mock_app_storage):
        """
        Test storing multiple keys in the same session.
        """

        storage = MemoryStorage()
        storage.add("key1", "value1")
        storage.add("key2", "value2")
        storage.add("key3", "value3")

        assert storage.get("key1") == "value1"
        assert storage.get("key2") == "value2"
        assert storage.get("key3") == "value3"

    def test_overwrite_value(self, mock_app_storage):
        """
        Test overwriting an existing value.
        """

        storage = MemoryStorage()
        storage.add("key1", "original")
        storage.add("key1", "updated")

        assert storage.get("key1") == "updated"

    def test_store_different_types(self, mock_app_storage):
        """
        Test storing different value types.
        """

        storage = MemoryStorage()
        storage.add("string", "value")
        storage.add("int", 42)
        storage.add("list", [1, 2, 3])
        storage.add("dict", {"nested": "value"})
        storage.add("none", None)

        assert storage.get("string") == "value"
        assert storage.get("int") == 42
        assert storage.get("list") == [1, 2, 3]
        assert storage.get("dict") == {"nested": "value"}
        assert storage.get("none") is None

    def test_clear_session(self, mock_app_storage):
        """
        Test clearing a session removes its data.
        """

        storage = MemoryStorage()

        mock_app_storage.storage.browser.get.return_value = "session-1"
        storage.add("key", "value1")

        mock_app_storage.storage.browser.get.return_value = "session-2"
        storage.add("key", "value2")

        storage.clear_session("session-1")

        mock_app_storage.storage.browser.get.return_value = "session-1"
        assert storage.get("key") is None

        mock_app_storage.storage.browser.get.return_value = "session-2"
        assert storage.get("key") == "value2"

    def test_clear_nonexistent_session(self, mock_app_storage):
        """
        Test clearing a non-existent session does not raise.
        """

        storage = MemoryStorage()
        storage.clear_session("nonexistent")  # Should not raise

    def test_purge_stale_sessions(self, mock_app_storage):
        """
        Test that stale sessions are purged after max_age.
        """

        with patch("utils.storage.monotonic") as mock_time:
            mock_time.return_value = 1000.0
            storage = MemoryStorage(max_age=60)

            mock_app_storage.storage.browser.get.return_value = "session-old"
            storage.add("key", "old-value")

            mock_time.return_value = 1050.0
            mock_app_storage.storage.browser.get.return_value = "session-new"
            storage.add("key", "new-value")

            # Advance past max_age for old session but not new
            mock_time.return_value = 1070.0
            storage.purge_stale_sessions()

            mock_app_storage.storage.browser.get.return_value = "session-old"
            assert storage.get("key") is None

            mock_app_storage.storage.browser.get.return_value = "session-new"
            assert storage.get("key") == "new-value"
