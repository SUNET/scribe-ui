# Copyright (c) 2025-2026 Sunet.
# Contributor: Kristofer Hallin
#
# This file is part of Sunet Scribe.
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

from dataclasses import dataclass
from typing import List, Optional, Set
from utils.caption import SRTCaption


@dataclass
class EditorState:
    """
    One point in the editor's history.

    Both halves travel together. The captions carry which speaker each block
    belongs to; the speaker list carries which names exist at all -- including
    ones no block uses yet ("Add new", or every block reassigned away), which
    is why it cannot simply be recomputed from the captions on the way back.
    Restoring one without the other left a block naming a speaker the list had
    never heard of, and the rename menu then refused to act on it.

    speakers is None for a state saved without one, which leaves whatever the
    editor already has alone rather than clearing it.
    """

    captions: List[SRTCaption]
    speakers: Optional[Set[str]] = None


class UndoRedoManager:
    """
    Manages undo/redo history for the SRT editor.
    """

    def __init__(self, max_history: int = 50):
        self.undo_stack: List[EditorState] = []
        self.redo_stack: List[EditorState] = []
        self.max_history = max_history

    @staticmethod
    def _snapshot(
        captions: List[SRTCaption], speakers: Optional[Set[str]]
    ) -> EditorState:
        """
        A copy of both halves, so later edits to the live editor cannot reach
        back into a state already on a stack.
        """

        return EditorState(
            [caption.copy() for caption in captions],
            None if speakers is None else set(speakers),
        )

    def save_state(
        self, captions: List[SRTCaption], speakers: Optional[Set[str]] = None
    ) -> None:
        """
        Save the current state to the undo stack.
        """

        state = self._snapshot(captions, speakers)
        self.undo_stack.append(state)

        # Clear redo stack when new action is performed
        self.redo_stack.clear()

        # Limit history size
        if len(self.undo_stack) > self.max_history:
            self.undo_stack.pop(0)

    def undo(
        self,
        current_captions: List[SRTCaption],
        current_speakers: Optional[Set[str]] = None,
    ) -> Optional[EditorState]:
        """
        Undo the last action and return the previous state.
        """
        if not self.undo_stack:
            return None

        # Save current state to redo stack
        self.redo_stack.append(self._snapshot(current_captions, current_speakers))

        # Pop and return the previous state
        return self.undo_stack.pop()

    def redo(
        self,
        current_captions: List[SRTCaption],
        current_speakers: Optional[Set[str]] = None,
    ) -> Optional[EditorState]:
        """
        Redo the last undone action and return the next state.
        """

        if not self.redo_stack:
            return None

        # Save current state to undo stack
        self.undo_stack.append(self._snapshot(current_captions, current_speakers))

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
