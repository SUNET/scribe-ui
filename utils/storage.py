from nicegui import app
from threading import Lock
from utils.settings import get_settings

# WARNING WARNING WARNING WARNING WARNING WARNING WARNING WARNING WARNING
#
# This should ONLY be used if NiceGUI is running as a single process. It
# should NOT be used together with Uvicorn and multiple workers!
#
# WARNING WARNING WARNING WARNING WARNING WARNING WARNING WARNING WARNING

settings = get_settings()


# Class to replace NiceGUIs app.storage for in-memory storage that is
# session-specific and avoids persistence in any way since we don't want to
# store sensitive data on disk.
class MemoryStorage:
    """
    In-memory storage that uses NiceGUI's browser session ID as the key.
    """

    def __init__(self):
        """
        Init the class.
        """

        self.__storage = {}
        self.__lock = Lock()

    def __get_session_id(self) -> str:
        """
        Get the current browser session ID from NiceGUI.

        Returns:
            str: The session ID.
        """

        user_id = app.storage.browser.get("id", None)

        if not user_id:
            raise RuntimeError("No browser session ID found.")

        return user_id

    def __get_session_store(self) -> dict:
        """
        Get or create the storage dict for the current session.

        Returns:
            dict: The storage dictionary for the current session.
        """

        if not settings.STORAGE_IN_MEMORY:
            return app.storage.user

        session_id = self.__get_session_id()

        if session_id not in self.__storage:
            self.__storage[session_id] = {}

        return self.__storage[session_id]

    def add(self, key, value):
        """
        Add a key-value pair to the current session's storage.

        Parameters:
            key: The key to add.
            value: The value to associate with the key.
        """

        with self.__lock:
            session_store = self.__get_session_store()
            session_store[key] = value

    def get(self, key, default=None):
        """
        Get a value from the current session's storage.

        Parameters:
            key: The key to retrieve.
            default: The default value to return if the key is not found.
        """

        session_store = self.__get_session_store()

        return session_store.get(key, default)

    def delete(self, key):
        """
        Delete a key from the current session's storage.

        Parameters:
            key: The key to delete.
            default: The default value to return if the key is not found.
        """

        with self.__lock:
            session_store = self.__get_session_store()

            if key in session_store:
                del session_store[key]

    def __getitem__(self, key):
        """
        Allow dict-like access: storage[key].

        Parameters:
            key: The key to retrieve.
        """

        return self.get(key)

    def __setitem__(self, key, value):
        """
        Allow dict-like assignment: storage[key] = value.

        Parameters:
            key: The key to set.
            value: The value to associate with the key.
        """

        self.add(key, value)

    def __delitem__(self, key):
        """
        Allow dict-like deletion: del storage[key].

        Parameters:
            key: The key to delete.
        """

        self.delete(key)

    def __contains__(self, key):
        """
        Allow 'in' operator: key in storage.

        Parameters:
            key: The key to check.
        """

        session_store = self.__get_session_store()

        return key in session_store


storage = MemoryStorage()
