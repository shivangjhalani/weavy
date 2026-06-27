import json
from typing import Any, Literal

from pydantic import BaseModel, field_validator

ThemeStatus = Literal["deep", "active", "emerging", "dormant"]

# Salience rank lives on the theme itself (lower = more salient). A freshly created
# theme sorts last until the next theme-run reconciliation assigns its real rank.
THEME_PRIORITY_UNSET = 1_000_000


def _parse_json_list(v: Any) -> list:
    if isinstance(v, str):
        return json.loads(v)
    return list(v) if v else []


class Theme(BaseModel):
    name: str
    state: str
    status: list[ThemeStatus]  # 1-2 items
    anchors: list[str]  # node ids
    priority: int = THEME_PRIORITY_UNSET  # salience rank — lower is more salient

    @field_validator("status", "anchors", mode="before")
    @classmethod
    def parse_json_list(cls, v: Any) -> list:
        return _parse_json_list(v)

    @field_validator("status")
    @classmethod
    def status_length(cls, v: list[ThemeStatus]) -> list[ThemeStatus]:
        if not 1 <= len(v) <= 2:
            raise ValueError("status must have 1 or 2 items")
        return v

    def render_block(self) -> str:
        status_str = ", ".join(self.status)
        anchors_str = ", ".join(self.anchors) if self.anchors else "none"
        return f"{self.name} [{status_str}]\n{self.state}\n\u2192 {anchors_str}"
