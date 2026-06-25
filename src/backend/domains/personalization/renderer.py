from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from backend.domains.personalization.variables import SUPPORTED_VARIABLES, build_variable_values


_PLACEHOLDER_RE = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")
_SUPPORTED_SET = set(SUPPORTED_VARIABLES)


@dataclass(slots=True)
class PersonalizationRenderResult:
    rendered_text: str
    used_variables: list[str]
    missing_variables: list[str]
    unknown_variables: list[str]


def render_personalized_text(
    template_text: str | None,
    *,
    contact: Any = None,
    sender_profile: Any = None,
    variable_values: dict[str, Any] | None = None,
) -> PersonalizationRenderResult:
    text = template_text or ""
    values = build_variable_values(contact, sender_profile)
    if variable_values:
        values.update(variable_values)

    used_variables: list[str] = []
    missing_variables: list[str] = []
    unknown_variables: list[str] = []

    def replace(match: re.Match[str]) -> str:
        variable = match.group(1).strip()

        if variable not in _SUPPORTED_SET:
            _append_unique(unknown_variables, variable)
            return match.group(0)

        _append_unique(used_variables, variable)
        value = values.get(variable)
        if _is_missing(value):
            _append_unique(missing_variables, variable)
            return ""
        return str(value)

    rendered = _PLACEHOLDER_RE.sub(replace, text)
    return PersonalizationRenderResult(
        rendered_text=rendered,
        used_variables=used_variables,
        missing_variables=missing_variables,
        unknown_variables=unknown_variables,
    )


def _append_unique(items: list[str], value: str) -> None:
    if value not in items:
        items.append(value)


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    return False
