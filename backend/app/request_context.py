"""Request context propagation for structured logging.

The PDF requires every JSON log line to carry a request_id propagated from
the X-Request-ID header (generated when absent). Middleware sets the value
on a ContextVar so log formatting can read it from anywhere in the call
stack -- including provider code -- without threading the id explicitly.
"""

from contextvars import ContextVar

request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    return request_id_ctx.get()


def set_request_id(value: str | None) -> None:
    request_id_ctx.set(value)
