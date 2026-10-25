"""``multipart/form-data`` encoder for ``files=`` / ``data=`` bodies.

Produces a fully-buffered body. Uploads in LLM4Free are small (STT audio,
images), so streaming the encode is not required.
"""

from __future__ import annotations

import mimetypes
import os
import uuid
from typing import Any, IO

# A "file" value may be: bytes, str, an open file object, or a tuple of
# (filename, data), (filename, data, content_type), or (name, filename, data, ct)
FileValue = Any

_CRLF = b"\r\n"


def _guess_type(filename: str | None) -> str:
    if filename:
        guess, _ = mimetypes.guess_type(filename)
        if guess:
            return guess
    return "application/octet-stream"


def _read_part_data(data: Any) -> tuple[bytes, str | None, str | None]:
    """Normalise a file value into (payload, filename, content_type)."""
    filename: str | None = None
    content_type: str | None = None

    if isinstance(data, tuple):
        if len(data) == 2:
            filename, payload = data  # type: ignore[misc]
        elif len(data) == 3:
            filename, payload, content_type = data  # type: ignore[misc]
        elif len(data) == 4:
            _name, filename, payload, content_type = data  # type: ignore[misc]
        else:
            raise ValueError(f"Unsupported files= tuple arity: {len(data)}")
    else:
        payload = data

    if isinstance(payload, str):
        body = payload.encode("utf-8")
        filename = filename or os.path.basename(payload) if False else filename
    elif isinstance(payload, (bytes, bytearray)):
        body = bytes(payload)
    elif hasattr(payload, "read"):
        stream: IO[Any] = payload
        body = stream.read()
        if isinstance(body, str):
            body = body.encode("utf-8")
        if filename is None:
            filename = getattr(stream, "name", None)
            if isinstance(filename, str):
                filename = os.path.basename(filename)
    else:
        raise TypeError(f"Unsupported file payload type: {type(payload)!r}")

    return body, filename, content_type


def encode_multipart(
    data: dict[str, Any] | list[tuple[str, Any]] | None = None,
    files: dict[str, FileValue] | list[tuple[str, FileValue]] | None = None,
) -> tuple[bytes, str]:
    """Encode ``data`` + ``files`` into a multipart/form-data body.

    Returns ``(body_bytes, content_type_header_value)``.
    """
    boundary = uuid.uuid4().hex
    parts: list[bytes] = []

    def add_field(name: str, value: Any, *, filename: str | None = None, ct: str | None = None) -> None:
        disp = f'Content-Disposition: form-data; name="{name}"'
        if filename is not None:
            disp += f'; filename="{filename}"'
        header = [_CRLF, disp.encode("utf-8")]
        if ct:
            header += [_CRLF, f"Content-Type: {ct}".encode("utf-8")]
        header.append(_CRLF)
        header.append(_CRLF)
        if isinstance(value, str):
            body = value.encode("utf-8")
        elif isinstance(value, (bytes, bytearray)):
            body = bytes(value)
        else:
            body = str(value).encode("utf-8")
        header.append(body)
        header.append(_CRLF)
        parts.append(b"--" + boundary.encode("ascii") + b"".join(header))

    # regular fields
    if data:
        items = data.items() if isinstance(data, dict) else data
        for name, value in items:  # type: ignore[assignment]
            if isinstance(value, (list, tuple)):
                for v in value:
                    add_field(name, v)
            else:
                add_field(name, value)

    # file fields
    if files:
        items = files.items() if isinstance(files, dict) else files
        for name, spec in items:  # type: ignore[misc]
            body, filename, ct = _read_part_data(spec)
            add_field(name, body, filename=filename or name, ct=ct or _guess_type(filename))

    terminator = b"--" + boundary.encode("ascii") + b"--" + _CRLF
    body = b"".join(parts) + terminator
    return body, f"multipart/form-data; boundary={boundary}"


__all__ = ["encode_multipart"]
