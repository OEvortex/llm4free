"""Server-Sent Events (SSE) parser over an iterator of text lines.

Follows the WHATWG EventSource framing rules: ``data``/``event``/``id``/``retry``
fields, multi-line ``data`` joined with ``\\n``, blank-line dispatch, and ``:``
comment lines ignored.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator


@dataclass
class ServerSentEvent:
    event: str = "message"
    data: str = ""
    id: str | None = None
    retry: int | None = None
    raw: list[str] = field(default_factory=list)

    def json(self) -> object:
        import json

        return json.loads(self.data)


def iter_sse_events(lines: Iterator[str]) -> Iterator[ServerSentEvent]:
    data_lines: list[str] = []
    event_type = ""
    event_id: str | None = None
    retry: int | None = None

    def dispatch() -> ServerSentEvent | None:
        nonlocal data_lines, event_type, event_id, retry
        if not data_lines:
            # A blank line with only an event/id set: nothing to emit.
            event_type = ""
            retry = None
            return None
        data = "\n".join(data_lines)
        # A single trailing newline is stripped per spec.
        if data.endswith("\n"):
            data = data[:-1]
        ev = ServerSentEvent(
            event=event_type or "message",
            data=data,
            id=event_id,
            retry=retry,
            raw=list(data_lines),
        )
        data_lines = []
        event_type = ""
        retry = None
        return ev

    for line in lines:
        if line == "":
            ev = dispatch()
            if ev is not None:
                yield ev
            continue
        if line.startswith(":"):
            continue  # comment / keep-alive

        if ":" in line:
            field_name, _, value = line.partition(":")
            if value.startswith(" "):
                value = value[1:]
        else:
            field_name, value = line, ""

        if field_name == "data":
            data_lines.append(value)
        elif field_name == "event":
            event_type = value
        elif field_name == "id":
            event_id = value
        elif field_name == "retry":
            if value.isdigit():
                retry = int(value)


__all__ = ["ServerSentEvent", "iter_sse_events"]
