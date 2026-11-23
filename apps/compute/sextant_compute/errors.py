"""Request-level errors and input validation helpers.

Every non-2xx response from the compute service has one JSON shape::

    {"error": {"code": "validation_error" | ..., "message": str, "fields": {"<field>": str}}}

``fields`` maps a request field (dotted path for nested models, e.g.
``legs.0.strike``) to a message the UI shows next to that input. Request-level
errors without a field (e.g. a data source being down) leave ``fields`` empty.

Codes in use:

- 422 ``validation_error``: the request model rejected the input.
- 422 ``no_such_data``: the data source has no such data (unknown ticker, empty
  range). Raised by adapters as ``NoSuchData``; endpoints that can tell which
  input was wrong re-raise it as ``ApiError(..., fields=...)`` so it shows inline.
- 503 ``source_unavailable``: an adapter raised ``SourceUnavailable``. The UI shows
  "data source temporarily unavailable, please retry".
- 403 ``key_required``: a source that runs on the visitor's own key (Tiingo) was
  asked for without a working key (``KeyRequired``). The message points to Settings.

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

from sextant_compute.data.errors import KeyRequired, NoSuchData, SourceUnavailable

INPUT_ERROR = "invalid_input"

_GENERIC_MESSAGES = {
    "missing": "This field is required.",
    "float_parsing": "Enter a number.",
    "float_type": "Enter a number.",
    "int_parsing": "Enter a whole number.",
    "int_type": "Enter a whole number.",
    "literal_error": "Choose one of the listed options.",
    "date_parsing": "Enter a date as YYYY-MM-DD.",
    "date_from_datetime_parsing": "Enter a date as YYYY-MM-DD.",
    "date_type": "Enter a date as YYYY-MM-DD.",
    "string_type": "Enter text.",
    "list_type": "Enter a list.",
}

SOURCE_UNAVAILABLE_MESSAGE = "The data source is temporarily unavailable. Please retry in a moment."


class ApiError(Exception):
    """Raise from an endpoint to answer with the standard error body."""

    def __init__(self, status: int, code: str, message: str, fields: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.fields = status, code, message, fields or {}


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


async def _api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
    return error_response(exc.status, exc.code, exc.message, exc.fields)


async def _no_such_data_handler(_request: Request, exc: NoSuchData) -> JSONResponse:
    return error_response(422, "no_such_data", exc.message)


async def _key_required_handler(_request: Request, exc: KeyRequired) -> JSONResponse:
    return error_response(403, "key_required", exc.message)


async def _source_unavailable_handler(_request: Request, exc: SourceUnavailable) -> JSONResponse:
    return error_response(503, "source_unavailable", SOURCE_UNAVAILABLE_MESSAGE)


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, _validation_handler)  # type: ignore[arg-type]
    app.add_exception_handler(ApiError, _api_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(NoSuchData, _no_such_data_handler)  # type: ignore[arg-type]
    app.add_exception_handler(SourceUnavailable, _source_unavailable_handler)  # type: ignore[arg-type]
    app.add_exception_handler(KeyRequired, _key_required_handler)  # type: ignore[arg-type]
