from typing import Any, Dict, Optional


class SRTCaption:
    def __init__(
        self,
        index: int,
        start_time: str,
        end_time: str,
        text: str,
        speaker: Optional[str] = "",
    ):
        """
        Initialize a caption with index, start time, end time, and text.
        """

        self.index = index
        self.start_time = start_time
        self.end_time = end_time
        self.text = text
        self.is_selected = False
        self.is_highlighted = False  # For search highlighting
        self.is_valid = True  # For validation
        self.speaker = speaker if speaker else "UNKNOWN"

    def copy(self) -> "SRTCaption":
        """
        Create a deep copy of the caption.
        """

        new_caption = SRTCaption(
            self.index,
            self.start_time,
            self.end_time,
            self.text,
            self.speaker,
        )
        new_caption.is_selected = self.is_selected
        new_caption.is_highlighted = self.is_highlighted
        new_caption.is_valid = self.is_valid
        return new_caption

    def to_dict(self) -> Dict[str, Any]:
        return {
            "speaker": self.speaker,
            "text": self.text,
            "start": self.get_start_seconds(),
            "end": self.get_end_seconds(),
            "duration": self.get_end_seconds() - self.get_start_seconds(),
        }

    def to_srt_format(self) -> str:
        return f"{self.index}\n{self.start_time} --> {self.end_time}\n{self.text}\n"

    def get_start_seconds(self) -> float:
        """
        Convert timestamp to seconds for calculations.
        """

        time_parts = self.start_time.replace(",", ".").split(":")
        hours = float(time_parts[0])
        minutes = float(time_parts[1])
        seconds = float(time_parts[2])

        return hours * 3600 + minutes * 60 + seconds

    def get_end_seconds(self) -> float:
        """
        Convert timestamp to seconds for calculations.
        """

        time_parts = str(self.end_time).replace(",", ".").split(":")

        hours = float(time_parts[0])
        minutes = float(time_parts[1])
        seconds = float(time_parts[2])

        return hours * 3600 + minutes * 60 + seconds

    def matches_search(self, search_term: str, case_sensitive: bool = False) -> bool:
        """
        Check if caption matches search term.
        """
        if not search_term:
            return False

        text = self.text if case_sensitive else self.text.lower()
        term = search_term if case_sensitive else search_term.lower()

        return term in text
