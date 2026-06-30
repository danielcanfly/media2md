from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CliSection:
    name: str
    status: str
    category: str
    message: str | None = None
    data: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "category": self.category,
            "message": self.message,
            "data": dict(self.data),
        }


@dataclass(frozen=True)
class CliOutputModel:
    event: str
    schema: str
    status: str
    category: str
    summary: str | None = None
    sections: tuple[CliSection, ...] = ()
    data: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "sections", tuple(self.sections))
        object.__setattr__(self, "data", dict(self.data))

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "event": self.event,
            "schema": self.schema,
            "status": self.status,
            "category": self.category,
            "summary": self.summary,
            "sections": [section.as_dict() for section in self.sections],
        }
        reserved = {"event", "schema", "status", "category", "summary", "sections"}
        payload.update({key: value for key, value in self.data.items() if key not in reserved})
        return payload
