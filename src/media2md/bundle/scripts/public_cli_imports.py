from __future__ import annotations

import importlib
from typing import Any


def optional_attr(module_name: str, attr_name: str) -> Any | None:
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError:
        return None
    return getattr(module, attr_name, None)


def optional_attrs(module_name: str, *attr_names: str) -> tuple[Any | None, ...]:
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError:
        return tuple(None for _ in attr_names)
    return tuple(getattr(module, attr_name, None) for attr_name in attr_names)
