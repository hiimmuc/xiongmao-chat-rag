"""Profile, personal API keys and preferences."""

from typing import Literal

from pydantic import Field

from app.schemas.common import Strict, Text

ResponseStyle = Literal["default", "friendly", "candid", "efficient", "professional", "analytical"]
ColorTheme = Literal["default", "github", "claude", "gemini", "monokai"]
Mode = Literal["light", "dark", "system"]
FontFamily = Literal["system", "sans", "serif", "mono"]
FontSize = Literal["small", "medium", "large"]


class ProfileUpdate(Strict):
    display_name: Text = Field(min_length=1, max_length=120)


class KeyBody(Strict):
    api_key: Text = Field(min_length=8, max_length=400)


class KeyTest(Strict):
    api_key: Text | None = Field(default=None, min_length=8, max_length=400)


class Notifications(Strict):
    enabled: bool = True
    document_processing: bool = True
    system: bool = True


class Preferences(Strict):
    """Stored shape of `users.preferences`; defaults fill anything missing."""

    mode: Mode = "system"
    color_theme: ColorTheme = "claude"
    font_family: FontFamily = "system"
    font_size: FontSize = "medium"
    response_style: ResponseStyle = "default"
    notifications: Notifications = Notifications()
    models: list[str] = []  # shortlist shown in the model picker; empty means all


class NotificationsUpdate(Strict):
    enabled: bool | None = None
    document_processing: bool | None = None
    system: bool | None = None


class PreferencesUpdate(Strict):
    """Partial update: only the fields sent are changed."""

    mode: Mode | None = None
    color_theme: ColorTheme | None = None
    font_family: FontFamily | None = None
    font_size: FontSize | None = None
    response_style: ResponseStyle | None = None
    notifications: NotificationsUpdate | None = None
    models: list[str] | None = Field(default=None, max_length=50)
