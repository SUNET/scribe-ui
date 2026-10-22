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

"""
The transcript scrolls its own scroller, not the page.

Element.scrollIntoView() moves every scrollable ancestor. With the Timeline
docked along the foot the page has about 170 px of room for it, so centring a
caption slid the whole page up and took the video out of view. The scrolling
is in the browser, so what is checked here is where it is done and how, read
from the component's source; the geometry was tried in Chrome.
"""

import pathlib
import re

SOURCE = (
    pathlib.Path(__file__).parent.parent / "utils" / "transcript_editor.js"
).read_text()


def method(name: str) -> str:
    start = SOURCE.index(f"    {name}(")
    end = SOURCE.index("\n    },\n", start)
    return SOURCE[start:end]


class TestNothingMovesThePageByAccident:
    def test_scroll_into_view_is_only_the_fallback_when_there_is_no_scroller(self):
        code = re.sub(r"(?m)^\s*//.*$", "", SOURCE)
        calls = [m.start() for m in re.finditer(r"\.scrollIntoView\(", code)]
        scroll_within = re.sub(r"(?m)^\s*//.*$", "", method("scrollWithin"))
        inside = code.index(scroll_within)

        assert len(calls) == 1
        assert inside < calls[0] < inside + len(scroll_within)
        assert "if (!scroller)" in scroll_within

    def test_focusing_a_block_and_scrolling_to_one_go_through_scroll_within(self):
        assert "this.scrollWithin(" in method("focusBlock")
        assert "this.scrollWithin(" in method("scrollToBlock")

    def test_centring_and_nearest_are_both_kept(self):
        focus = method("focusBlock")

        assert 'block: "center"' in focus
        assert 'block: "nearest"' in focus
        assert 'block: "center"' in method("scrollToBlock")

    def test_the_scroller_is_the_nearest_ancestor_that_scrolls_not_the_window(self):
        finding = method("scrollerOf")

        assert "parentElement" in finding
        assert "overflowY" in finding
        assert "document.body" in finding
        assert "window" not in finding


class TestTheDockedTimeline:
    def test_the_part_under_the_docked_timeline_is_not_counted_as_visible(self):
        scroll_within = method("scrollWithin")

        assert ".speech-timeline-docked" in scroll_within
        assert "dockTop" in scroll_within

    def test_the_page_gives_way_only_for_what_is_still_hidden(self):
        scroll_within = method("scrollWithin")

        assert "window.scrollBy(" in scroll_within
        assert "const hidden = " in scroll_within
        assert "if (hidden > 0)" in scroll_within

    def test_what_the_page_gave_way_is_given_back_and_no_more(self):
        scroll_within = method("scrollWithin")

        assert "this.pageGiven" in scroll_within
        assert "Math.min(given, window.scrollY, -hidden)" in scroll_within

    def test_the_scroller_is_not_asked_for_more_than_it_has(self):
        scroll_within = method("scrollWithin")

        assert "scroller.scrollHeight - scroller.clientHeight" in scroll_within
