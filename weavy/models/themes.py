import json
from typing import Any, Literal

from pydantic import BaseModel, field_validator

ThemeStatus = Literal["deep", "active", "emerging", "dormant"]


class Theme(BaseModel):
    name: str
    state: str
    status: list[ThemeStatus]  # 1-2 items
    anchors: list[str]  # node ids

    @field_validator("status", mode="before")
    @classmethod
    def parse_status(cls, v: Any) -> list:
        if isinstance(v, str):
            return json.loads(v)
        return list(v) if v else []

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
