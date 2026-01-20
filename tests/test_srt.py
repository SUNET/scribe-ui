import pytest
from utils.srt import SRTCaption, UndoRedoManager


class TestSRTCaption:
    """Test cases for SRTCaption class."""

    def test_init(self):
        """Test caption initialization."""
        caption = SRTCaption(
            index=1,
            start_time="00:00:10,000",
            end_time="00:00:15,500",
            text="Hello world",
            speaker="John"
        )
        
        assert caption.index == 1
        assert caption.start_time == "00:00:10,000"
        assert caption.end_time == "00:00:15,500"
        assert caption.text == "Hello world"
        assert caption.speaker == "John"
        assert caption.is_selected is False
        assert caption.is_highlighted is False
        assert caption.is_valid is True

    def test_init_default_speaker(self):
        """Test caption initialization with default speaker."""
        caption = SRTCaption(
            index=1,
            start_time="00:00:10,000",
            end_time="00:00:15,500",
            text="Hello world"
        )
        
        assert caption.speaker == "UNKNOWN"

    def test_init_empty_speaker(self):
        """Test caption initialization with empty speaker string."""
        caption = SRTCaption(
            index=1,
            start_time="00:00:10,000",
            end_time="00:00:15,500",
            text="Hello world",
            speaker=""
        )
        
        assert caption.speaker == "UNKNOWN"

    def test_copy(self):
        """Test caption copy method."""
        original = SRTCaption(
            index=1,
            start_time="00:00:10,000",
            end_time="00:00:15,500",
            text="Hello world",
            speaker="John"
        )
        original.is_selected = True
        original.is_highlighted = True
        original.is_valid = False
        
        copied = original.copy()
        
        assert copied.index == original.index
        assert copied.start_time == original.start_time
        assert copied.end_time == original.end_time
        assert copied.text == original.text
        assert copied.speaker == original.speaker
        assert copied.is_selected == original.is_selected
        assert copied.is_highlighted == original.is_highlighted
        assert copied.is_valid == original.is_valid
        
        # Ensure it's a deep copy
        assert copied is not original

    def test_to_dict(self):
        """Test caption to_dict method."""
        caption = SRTCaption(
            index=1,
            start_time="00:00:10,000",
            end_time="00:00:15,500",
            text="Hello world",
            speaker="John"
        )
        
        result = caption.to_dict()
        
        assert result["speaker"] == "John"
        assert result["text"] == "Hello world"
        assert result["start"] == 10.0
        assert result["end"] == 15.5
        assert result["duration"] == 5.5

    def test_to_srt_format(self):
        """Test caption to_srt_format method."""
        caption = SRTCaption(
            index=1,
            start_time="00:00:10,000",
            end_time="00:00:15,500",
            text="Hello world",
            speaker="John"
        )
        
        result = caption.to_srt_format()
        expected = "1\n00:00:10,000 --> 00:00:15,500\nHello world\n"
        
        assert result == expected

    def test_get_start_seconds(self):
        """Test conversion of start time to seconds."""
        caption = SRTCaption(
            index=1,
            start_time="00:00:10,500",
            end_time="00:00:15,000",
            text="Hello world"
        )
        
        assert caption.get_start_seconds() == 10.5

    def test_get_start_seconds_with_hours(self):
        """Test conversion of start time with hours to seconds."""
        caption = SRTCaption(
            index=1,
            start_time="01:30:45,250",
            end_time="01:30:50,000",
            text="Hello world"
        )
        
        # 1 hour = 3600 seconds, 30 minutes = 1800 seconds, 45.25 seconds
        expected = 3600 + 1800 + 45.25
        assert caption.get_start_seconds() == expected

    def test_get_end_seconds(self):
        """Test conversion of end time to seconds."""
        caption = SRTCaption(
            index=1,
            start_time="00:00:10,000",
            end_time="00:00:15,750",
            text="Hello world"
        )
        
        assert caption.get_end_seconds() == 15.75

    def test_get_end_seconds_with_hours(self):
        """Test conversion of end time with hours to seconds."""
        caption = SRTCaption(
            index=1,
            start_time="00:00:10,000",
            end_time="02:15:30,500",
            text="Hello world"
        )
        
        # 2 hours = 7200 seconds, 15 minutes = 900 seconds, 30.5 seconds
        expected = 7200 + 900 + 30.5
        assert caption.get_end_seconds() == expected

    def test_matches_search_case_insensitive(self):
        """Test case-insensitive search matching."""
        caption = SRTCaption(
            index=1,
            start_time="00:00:10,000",
            end_time="00:00:15,000",
            text="Hello World"
        )
        
        assert caption.matches_search("hello", case_sensitive=False) is True
        assert caption.matches_search("WORLD", case_sensitive=False) is True
        assert caption.matches_search("world", case_sensitive=False) is True
        assert caption.matches_search("goodbye", case_sensitive=False) is False

    def test_matches_search_case_sensitive(self):
        """Test case-sensitive search matching."""
        caption = SRTCaption(
            index=1,
            start_time="00:00:10,000",
            end_time="00:00:15,000",
            text="Hello World"
        )
        
        assert caption.matches_search("Hello", case_sensitive=True) is True
        assert caption.matches_search("World", case_sensitive=True) is True
        assert caption.matches_search("hello", case_sensitive=True) is False
        assert caption.matches_search("WORLD", case_sensitive=True) is False

    def test_matches_search_empty_term(self):
        """Test search matching with empty search term."""
        caption = SRTCaption(
            index=1,
            start_time="00:00:10,000",
            end_time="00:00:15,000",
            text="Hello World"
        )
        
        assert caption.matches_search("", case_sensitive=False) is False
        assert caption.matches_search("", case_sensitive=True) is False

    def test_matches_search_partial_match(self):
        """Test partial string matching in search."""
        caption = SRTCaption(
            index=1,
            start_time="00:00:10,000",
            end_time="00:00:15,000",
            text="The quick brown fox"
        )
        
        assert caption.matches_search("quick", case_sensitive=False) is True
        assert caption.matches_search("brown fox", case_sensitive=False) is True
        assert caption.matches_search("slow", case_sensitive=False) is False


class TestUndoRedoManager:
    """Test cases for UndoRedoManager class."""

    def test_init(self):
        """Test manager initialization."""
        manager = UndoRedoManager()
        
        assert manager.max_history == 50
        assert len(manager.undo_stack) == 0
        assert len(manager.redo_stack) == 0

    def test_init_custom_max_history(self):
        """Test manager initialization with custom max history."""
        manager = UndoRedoManager(max_history=10)
        
        assert manager.max_history == 10

    def test_save_state(self):
        """Test saving state to undo stack."""
        manager = UndoRedoManager()
        captions = [
            SRTCaption(1, "00:00:10,000", "00:00:15,000", "First caption"),
            SRTCaption(2, "00:00:15,000", "00:00:20,000", "Second caption")
        ]
        
        manager.save_state(captions)
        
        assert len(manager.undo_stack) == 1
        assert len(manager.redo_stack) == 0
        assert len(manager.undo_stack[0]) == 2

    def test_save_state_clears_redo(self):
        """Test that saving state clears redo stack."""
        manager = UndoRedoManager()
        captions = [
            SRTCaption(1, "00:00:10,000", "00:00:15,000", "First caption")
        ]
        
        manager.save_state(captions)
        manager.redo_stack.append(captions)  # Manually add to redo
        
        assert len(manager.redo_stack) == 1
        
        manager.save_state(captions)
        
        assert len(manager.redo_stack) == 0

    def test_save_state_deep_copy(self):
        """Test that save_state creates deep copy of captions."""
        manager = UndoRedoManager()
        captions = [
            SRTCaption(1, "00:00:10,000", "00:00:15,000", "First caption")
        ]
        
        manager.save_state(captions)
        
        # Modify original
        captions[0].text = "Modified"
        
        # Saved state should be unchanged
        assert manager.undo_stack[0][0].text == "First caption"

    def test_save_state_max_history_limit(self):
        """Test that history is limited to max_history."""
        manager = UndoRedoManager(max_history=3)
        captions = [
            SRTCaption(1, "00:00:10,000", "00:00:15,000", "Caption")
        ]
        
        # Save 4 states
        for i in range(4):
            captions[0].text = f"Caption {i}"
            manager.save_state(captions)
        
        assert len(manager.undo_stack) == 3
        # First state should be removed
        assert manager.undo_stack[0][0].text == "Caption 1"

    def test_undo(self):
        """Test undo functionality."""
        manager = UndoRedoManager()
        
        # Create initial state
        captions_v1 = [
            SRTCaption(1, "00:00:10,000", "00:00:15,000", "Version 1")
        ]
        manager.save_state(captions_v1)
        
        # Create modified state
        captions_v2 = [
            SRTCaption(1, "00:00:10,000", "00:00:15,000", "Version 2")
        ]
        
        result = manager.undo(captions_v2)
        
        assert result is not None
        assert result[0].text == "Version 1"
        assert len(manager.undo_stack) == 0
        assert len(manager.redo_stack) == 1

    def test_undo_empty_stack(self):
        """Test undo with empty stack."""
        manager = UndoRedoManager()
        captions = [
            SRTCaption(1, "00:00:10,000", "00:00:15,000", "Caption")
        ]
        
        result = manager.undo(captions)
        
        assert result is None

    def test_redo(self):
        """Test redo functionality."""
        manager = UndoRedoManager()
        
        # Create initial state and save
        captions_v1 = [
            SRTCaption(1, "00:00:10,000", "00:00:15,000", "Version 1")
        ]
        manager.save_state(captions_v1)
        
        # Create modified state
        captions_v2 = [
            SRTCaption(1, "00:00:10,000", "00:00:15,000", "Version 2")
        ]
        
        # Undo to move v2 to redo stack
        manager.undo(captions_v2)
        
        # Redo
        result = manager.redo(captions_v1)
        
        assert result is not None
        assert result[0].text == "Version 2"
        assert len(manager.redo_stack) == 0
        assert len(manager.undo_stack) == 1

    def test_redo_empty_stack(self):
        """Test redo with empty stack."""
        manager = UndoRedoManager()
        captions = [
            SRTCaption(1, "00:00:10,000", "00:00:15,000", "Caption")
        ]
        
        result = manager.redo(captions)
        
        assert result is None

    def test_can_undo(self):
        """Test can_undo method."""
        manager = UndoRedoManager()
        
        assert manager.can_undo() is False
        
        captions = [
            SRTCaption(1, "00:00:10,000", "00:00:15,000", "Caption")
        ]
        manager.save_state(captions)
        
        assert manager.can_undo() is True

    def test_can_redo(self):
        """Test can_redo method."""
        manager = UndoRedoManager()
        
        assert manager.can_redo() is False
        
        captions = [
            SRTCaption(1, "00:00:10,000", "00:00:15,000", "Caption")
        ]
        manager.redo_stack.append(captions)
        
        assert manager.can_redo() is True

    def test_clear(self):
        """Test clear method."""
        manager = UndoRedoManager()
        captions = [
            SRTCaption(1, "00:00:10,000", "00:00:15,000", "Caption")
        ]
        
        manager.save_state(captions)
        manager.redo_stack.append(captions)
        
        assert len(manager.undo_stack) > 0
        assert len(manager.redo_stack) > 0
        
        manager.clear()
        
        assert len(manager.undo_stack) == 0
        assert len(manager.redo_stack) == 0

    def test_undo_redo_sequence(self):
        """Test a complete undo/redo sequence."""
        manager = UndoRedoManager()
        
        # Save state 1
        captions_v1 = [
            SRTCaption(1, "00:00:10,000", "00:00:15,000", "Version 1")
        ]
        manager.save_state(captions_v1)
        
        # Save state 2
        captions_v2 = [
            SRTCaption(1, "00:00:10,000", "00:00:15,000", "Version 2")
        ]
        manager.save_state(captions_v2)
        
        # Current state 3
        captions_v3 = [
            SRTCaption(1, "00:00:10,000", "00:00:15,000", "Version 3")
        ]
        
        # Undo twice
        result = manager.undo(captions_v3)
        assert result[0].text == "Version 2"
        
        result = manager.undo(result)
        assert result[0].text == "Version 1"
        
        # Redo once
        result = manager.redo(result)
        assert result[0].text == "Version 2"
        
        # Redo again
        result = manager.redo(result)
        assert result[0].text == "Version 3"
