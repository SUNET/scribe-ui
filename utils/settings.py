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

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Settings for the application.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        validate_assignment=True,
        enable_decoding=False,
    )

    API_URL: str = ""
    OIDC_APP_LOGIN_ROUTE: str = ""
    OIDC_APP_LOGOUT_ROUTE: str = ""
    OIDC_APP_REFRESH_ROUTE: str = ""
    STORAGE_SECRET: str = "change_this_secret_to_another_very_secret_secret"

    LOGO_LANDING: str = "sunet_logo.png"
    LOGO_LANDING_WIDTH: str = "250"
    LOGO_TOPBAR_LIGHT: str = "sunet_small.png"
    LOGO_TOPBAR_DARK: str = "sunet_small_dark.png"
    FAVICON: str = "favicon.ico"
    TAB_TITLE: str = "Sunet Scribe"
    TOPBAR_TEXT: str = "Sunet Scribe"
    LANDING_TEXT: str = "Welcome to Sunet Scribe"
    MANUAL_URL: str = "https://sunet.box.com/s/la16r5iu3gkm5n149mzmth9yiaulx3ub"

    # Subtitle line length guideline. Lines longer than this are flagged in
    # the editor and reported by "Validate"; nothing is truncated.
    CHARACTER_LIMIT: int = 42
    CHARACTER_LIMIT_EXCEEDED_COLOR: str = "text-red"

    # Subtitle row count guideline, alongside CHARACTER_LIMIT. A caption with
    # more lines than this is flagged the same way; nothing is truncated or
    # auto-wrapped.
    MAX_SUBTITLE_LINES: int = 2

    # Review sensitivity: how far up the confidence range to flag words for
    # review. A word is flagged when its score falls below the threshold for
    # the selected sensitivity, so raising sensitivity flags strictly more.
    #
    #   Low     only the words the model was least sure of
    #   Medium  adds the middle of the range
    #   High    everything the model was not clearly confident about
    #
    # Worth retuning if you change transcription models -- what counts as a
    # low score differs between them.
    REVIEW_SENSITIVITY_LOW: float = 0.25
    REVIEW_SENSITIVITY_MEDIUM: float = 0.50
    REVIEW_SENSITIVITY_HIGH: float = 0.75

    WHISPER_MODELS: list[str] = [
        "Fast transcription (normal accuracy)",
        "Slower transcription (higher accuracy)",
    ]
    WHISPER_LANGUAGES: list[str] = [
        "Swedish",
        "English",
        "Norwegian",
        "Finnish",
        "Danish",
        "French",
        "Spanish",
        "Portuguese",
        "German",
        "Italian",
        "Dutch",
        "Russian",
        "Ukrainian",
        "Icelandic",
        "Northern Sámi (Experimental)",
    ]


@lru_cache
def get_settings() -> Settings:
    """
    Get the settings for the application.
    """

    return Settings()
