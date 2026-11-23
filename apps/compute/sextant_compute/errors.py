"""Request-level errors and input validation helpers.

Every non-2xx response from the compute service has one JSON shape::

    {"error": {"code": "validation_error" | ..., "message": str, "fields": {"<field>": str}}}

``fields`` maps a request field (dotted path for nested models, e.g.
``legs.0.strike``) to a message the UI shows next to that input. Request-level
errors without a field (e.g. a data source being down) leave ``fields`` empty.

Validation messages are written for people: attach them to request-model
fields with ``check(...)`` so pydantic reports them verbatim.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import AfterValidator
from pydantic_core import PydanticCustomError

INPUT_ERROR = "invalid_input"

_GENERIC_MESSAGES = {
    "missing": "This field is required.",
    "float_parsing": "Enter a number.",
    "float_type": "Enter a number.",
    "int_parsing": "Enter a whole number.",
    "int_type": "Enter a whole number.",
    "literal_error": "Choose one of the listed options.",
}


def check(predicate: Callable[[Any], bool], message: str) -> AfterValidator:
    """A field validator that rejects values failing ``predicate`` with ``message``.

    Use with ``Annotated``: ``volatility: Annotated[float, check(lambda v: v > 0, "...")]``.
    """

    def validate(value: Any) -> Any:
        if value is not None and not predicate(value):
            raise PydanticCustomError(INPUT_ERROR, message)
        return value

    return AfterValidator(validate)


def error_body(code: str, message: str, fields: dict[str, str] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "fields": fields or {}}}


def error_response(status: int, code: str, message: str, fields: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(status_code=status, content=error_body(code, message, fields))


def _field_errors(exc: RequestValidationError) -> dict[str, str]:
    fields: dict[str, str] = {}
    for err in exc.errors():
        loc = [str(part) for part in err.get("loc", ())]
        if loc and loc[0] in {"body", "query", "path"}:
            loc = loc[1:]
        field = ".".join(loc) or "_request"
        if err.get("type") == INPUT_ERROR:
            message = err["msg"]
        else:
            message = _GENERIC_MESSAGES.get(err.get("type", ""), err.get("msg", "Invalid value."))
        fields.setdefault(field, message)
    return fields


async def _validation_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    return error_response(422, "validation_error", "Some inputs are invalid. Fix the highlighted fields.", _field_errors(exc))


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, _validation_handler)  # type: ignore[arg-type]
