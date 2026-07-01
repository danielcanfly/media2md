from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RequiredActionResult:
    error_code: str
    retryable: bool
    action_required: bool
    required_action: str | None = None
    root_cause: str | None = None
    log_path: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "error_code": self.error_code,
            "retryable": self.retryable,
            "action_required": self.action_required,
            "required_action": self.required_action,
            "root_cause": self.root_cause,
            "log_path": self.log_path,
        }
