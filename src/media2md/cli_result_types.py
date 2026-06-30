from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .cli_output_service import make_output_model, make_section


@dataclass(frozen=True)
class CliResultEnvelope:
    event: str
    schema: str
    section: str
    status: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return make_output_model(
            event=self.event,
            schema=self.schema,
            summary=self.message,
            sections=(
                make_section(
                    self.section,
                    status=self.status,
                    message=self.message,
                    data=self.data,
                ),
            ),
            data=self.data,
        ).as_dict()


def cli_result(
    *,
    event: str,
    section: str,
    status: str,
    message: str,
    data: dict[str, Any],
    schema: str | None = None,
) -> dict[str, Any]:
    return CliResultEnvelope(
        event=event,
        schema=schema or f"media2md.cli.{event}/v1",
        section=section,
        status=status,
        message=message,
        data=data,
    ).as_dict()

