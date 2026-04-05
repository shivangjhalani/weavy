from typing import Literal

from pydantic import BaseModel, field_validator

ThemeStatus = Literal["deep", "active", "emerging", "dormant"]


class Theme(BaseModel):
    name: str
    state: str
    status: list[ThemeStatus]  # 1-2 items
    anchors: list[str]  # node ids

    @field_validator("status")
    @classmethod
    def status_length(cls, v: list[ThemeStatus]) -> list[ThemeStatus]:
        if not 1 <= len(v) <= 2:
            raise ValueError("status must have 1 or 2 items")
        return v
