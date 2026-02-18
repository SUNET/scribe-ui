from collections import defaultdict
from nicegui import app
from time import monotonic
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

    def __init__(self, max_age: float = 3600):
        """
        Init the class.

        Parameters:
            max_age: Max idle time in seconds before a session is evicted.
        """

        self.__storage: defaultdict[str, dict] = defaultdict(dict)
        self.__last_access: dict[str, float] = {}
        self.__max_age: float = max_age

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

        self.__last_access[session_id] = monotonic()

        return self.__storage[session_id]

    def add(self, key, value):
        """
        Add a key-value pair to the current session's storage.

        Parameters:
            key: The key to add.
            value: The value to associate with the key.
        """

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
        """

        session_store = self.__get_session_store()

        if key in session_store:
            del session_store[key]

    def clear_session(self, session_id: str):
        """
        Remove all stored data for a given session.

        Parameters:
            session_id: The session ID to clear.
        """

        self.__storage.pop(session_id, None)
        self.__last_access.pop(session_id, None)

    def purge_stale_sessions(self):
        """
        Remove sessions that have not been accessed within max_age seconds.
        """

        cutoff = monotonic() - self.__max_age
        stale = [sid for sid, ts in self.__last_access.items() if ts < cutoff]

        for sid in stale:
            self.__storage.pop(sid, None)
            self.__last_access.pop(sid, None)

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
