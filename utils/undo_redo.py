from typing import List, Optional
from utils.caption import SRTCaption


class UndoRedoManager:
    """
    Manages undo/redo history for the SRT editor.
    """

    def __init__(self, max_history: int = 50):
        self.undo_stack: List[List[SRTCaption]] = []
        self.redo_stack: List[List[SRTCaption]] = []
        self.max_history = max_history

    def save_state(self, captions: List[SRTCaption]) -> None:
        """
        Save the current state to the undo stack.
        """

        # Deep copy the captions list
        state = [caption.copy() for caption in captions]
        self.undo_stack.append(state)

        # Clear redo stack when new action is performed
        self.redo_stack.clear()

        # Limit history size
        if len(self.undo_stack) > self.max_history:
            self.undo_stack.pop(0)

    def undo(self, current_captions: List[SRTCaption]) -> Optional[List[SRTCaption]]:
        """
        Undo the last action and return the previous state.
        """
        if not self.undo_stack:
            return None

        # Save current state to redo stack
        current_state = [caption.copy() for caption in current_captions]
        self.redo_stack.append(current_state)

        # Pop and return the previous state
        return self.undo_stack.pop()

    def redo(self, current_captions: List[SRTCaption]) -> Optional[List[SRTCaption]]:
        """
        Redo the last undone action and return the next state.
        """

        if not self.redo_stack:
            return None

        # Save current state to undo stack
        current_state = [caption.copy() for caption in current_captions]
        self.undo_stack.append(current_state)

        # Pop and return the next state
        return self.redo_stack.pop()

    def can_undo(self) -> bool:
        """
        Check if undo is available.
        """

        return len(self.undo_stack) > 0

    def can_redo(self) -> bool:
        """
        Check if redo is available.
        """

        return len(self.redo_stack) > 0

    def clear(self) -> None:
        """
        Clear all history.
        """

        self.undo_stack.clear()
        self.redo_stack.clear()
