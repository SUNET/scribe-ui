"""
Every page has a title in the tab and one h1 on the page (WCAG 2.4.2, 1.3.1,
2.4.6). Most pages show a title and give it the heading role; the editor, the
viewer and the recorder show none, and have a hidden h1 with the same words
as the document title, so a person who does not see the page can still tell
where they are.
"""

import pathlib
import re

import pytest

from utils import common

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAGE_DECORATOR = re.compile(r"^\s*@ui\.page\(", re.MULTILINE)


def source(relative: str) -> str:
    return (ROOT / relative).read_text()


def page_files():
    files = sorted((ROOT / "pages").rglob("*.py"))

    return [
        path.relative_to(ROOT).as_posix()
        for path in files
        if PAGE_DECORATOR.search(path.read_text())
    ]


class TestEditorTitle:
    def test_subtitles_and_transcripts_are_named_apart(self):
        from pages.srt import editor_title

        assert editor_title("srt") == "Subtitle editor"
        assert editor_title("txt") == "Transcript editor"

    def test_anything_else_is_a_transcript(self):
        from pages.srt import editor_title

        assert editor_title("") == "Transcript editor"

    def test_the_page_uses_it_for_both_the_tab_and_the_heading(self):
        text = source("pages/srt.py")

        assert "title = editor_title(data_format)" in text
        assert "page_init(use_drawer=True, title=title)" in text
        assert "hidden_page_heading(title)" in text

    def test_the_heading_comes_after_the_job_id_is_checked(self):
        text = source("pages/srt.py")

        assert text.index("UUID(uuid)") < text.index("hidden_page_heading(title)")
        assert text.index("hidden_page_heading(title)") < text.index(
            "editor = SRTEditor("
        )


class TestTheHiddenHeading:
    def test_it_is_an_h1_that_only_a_screen_reader_meets(self, monkeypatch):
        made = []

        class Label:
            def __init__(self, text):
                made.append(self)
                self.text = text
                self.class_names = ""
                self.properties = ""

            def classes(self, names):
                self.class_names = names
                return self

            def props(self, props):
                self.properties = props
                return self

        monkeypatch.setattr(common.ui, "label", Label)

        common.hidden_page_heading("Viewer")

        assert len(made) == 1
        assert made[0].text == "Viewer"
        assert made[0].class_names == "sr-only"
        assert "role=heading" in made[0].properties
        assert "aria-level=1" in made[0].properties

    def test_sr_only_takes_no_room(self):
        from utils.styles import default_styles

        rule = default_styles[default_styles.index(".sr-only {") :]
        rule = rule[: rule.index("}")]

        assert "position: absolute;" in rule
        assert "width: 1px;" in rule
        assert "height: 1px;" in rule


class TestTheViewer:
    def test_it_is_called_viewer_whatever_the_file(self):
        text = source("pages/view.py")

        assert 'title="Viewer"' in text
        assert 'hidden_page_heading("Viewer")' in text
        assert "View transcription" not in text

    def test_the_file_name_it_shows_is_a_heading_under_the_page_heading(self):
        text = source("pages/view.py")
        at = text.index('ui.label(filename).classes("view-title")')

        assert "aria-level=2" in text[at : at + 120]
        assert text.index("hidden_page_heading") < at


class TestTheRecorder:
    def test_it_has_a_heading_that_matches_its_title(self):
        text = source("pages/record.py")

        assert 'title="Recorder"' in text
        assert 'hidden_page_heading("Recorder")' in text


class TestTheSignInPage:
    def test_the_welcome_text_is_its_heading(self):
        text = source("main.py")
        at = text.index("ui.label(settings.LANDING_TEXT)")

        assert "aria-level=1" in text[at : at + 200]


@pytest.mark.parametrize("relative", page_files())
def test_every_page_has_a_title_and_an_h1(relative):
    text = source(relative)

    # status.py is for a visitor who may not be signed in, so it sets its own
    # title instead of going through page_init.
    assert "page_init(" in text or "ui.page_title(" in text, relative
    assert "title=" in text or "ui.page_title(" in text, relative
    assert "aria-level=1" in text or "hidden_page_heading(" in text, relative


def test_the_pages_are_found():
    # Guard for the test above: a glob that finds nothing would pass it.
    found = page_files()

    assert "pages/home.py" in found
    assert "pages/srt.py" in found
    assert "pages/admin/users.py" in found
    assert len(found) >= 14
