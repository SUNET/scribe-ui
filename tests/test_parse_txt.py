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

import json

import pytest

from utils.srt import SRTEditor


def segment(speaker: str, text: str, start: float, end: float) -> dict:
    return {
        "speaker": speaker,
        "text": text,
        "start": start,
        "end": end,
        "duration": end - start,
    }


@pytest.fixture
def editor():
    editor = SRTEditor("job-uuid", "txt", "file.txt")

    for name in ("refresh_display", "update_words_per_minute",
                 "save_state_for_undo", "mark_as_changed"):
        setattr(editor, name, lambda *args, **kwargs: None)

    return editor


class TestWorkerOutput:
    """
    Raw diarisation output arrives in short lower case fragments and still
    wants tidying on the way in.
    """

    def test_same_speaker_segments_are_merged(self, editor):
        editor.parse_txt(json.dumps({"segments": [
            segment("SPEAKER_00", "det här är en mening", 0.0, 2.0),
            segment("SPEAKER_00", "och det här är en till", 2.0, 4.0),
        ]}))

        assert len(editor.captions) == 1
        assert editor.captions[0].text == "Det här är en mening och det här är en till"
        assert editor.captions[0].start_time == "00:00:00,000"
        assert editor.captions[0].end_time == "00:00:04,000"

    def test_speaker_change_starts_a_new_block(self, editor):
        editor.parse_txt(json.dumps({"segments": [
            segment("SPEAKER_00", "hej", 0.0, 1.0),
            segment("SPEAKER_01", "hej själv", 1.0, 2.0),
        ]}))

        assert [caption.text for caption in editor.captions] == ["Hej", "Hej själv"]
        assert editor.speakers == {"SPEAKER_00", "SPEAKER_01"}

    def test_long_block_is_broken_at_a_sentence_end(self, editor):
        editor.parse_txt(json.dumps({"segments": [
            segment("SPEAKER_00", " ".join(["ord"] * 50) + ".", 0.0, 30.0),
            segment("SPEAKER_00", "en ny mening", 30.0, 32.0),
        ]}))

        assert len(editor.captions) == 2
        assert editor.captions[1].text == "En ny mening"

    def test_text_after_a_period_is_capitalised(self, editor):
        editor.parse_txt(json.dumps({"segments": [
            segment("SPEAKER_00", "första meningen. andra meningen.", 0.0, 4.0),
        ]}))

        assert editor.captions[0].text == "Första meningen. Andra meningen."


class TestSavedTranscript:
    """
    A transcript saved from the editor carries the blocks the reader arranged,
    and reloading it must give them back unchanged.
    """

    def test_split_same_speaker_blocks_survive_a_reload(self, editor):
        editor.parse_txt(json.dumps({
            "segments": [
                segment("SPEAKER_00", "Första halvan", 0.0, 2.0),
                segment("SPEAKER_00", "andra halvan", 2.0, 4.0),
            ],
            "preserve_segments": True,
        }))

        assert [caption.text for caption in editor.captions] == [
            "Första halvan",
            "andra halvan",
        ]

    def test_round_trip_keeps_the_block_structure(self, editor):
        editor.parse_txt(json.dumps({"segments": [
            segment("SPEAKER_00", "en mening som delas här och fortsätter sedan", 0.0, 4.0),
        ]}))

        editor.split_caption(
            editor.captions[0], len("en mening som delas här")
        )

        before = [(caption.speaker, caption.text) for caption in editor.captions]
        assert len(before) == 2

        reloaded = SRTEditor("job-uuid", "txt", "file.txt")
        reloaded.parse_txt(json.dumps(editor.export_json()))

        assert [(caption.speaker, caption.text) for caption in reloaded.captions] == before

    def test_deliberate_lower_case_is_left_alone(self, editor):
        editor.parse_txt(json.dumps({
            "segments": [
                segment("SPEAKER_00", "iPhone är namnet. iPad också.", 0.0, 4.0),
            ],
            "preserve_segments": True,
        }))

        assert editor.captions[0].text == "iPhone är namnet. iPad också."


class TestEmptyInput:
    def test_no_segments_key(self, editor):
        editor.parse_txt(json.dumps({}))

        assert editor.captions == []

    def test_empty_segment_list(self, editor):
        editor.parse_txt(json.dumps({"segments": []}))

        assert editor.captions == []

    def test_blank_segments_are_skipped(self, editor):
        editor.parse_txt(json.dumps({
            "segments": [
                segment("SPEAKER_00", "  ", 0.0, 1.0),
                segment("SPEAKER_00", "Med text", 1.0, 2.0),
            ],
            "preserve_segments": True,
        }))

        assert [caption.text for caption in editor.captions] == ["Med text"]
