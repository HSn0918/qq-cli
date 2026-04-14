"""Very small protobuf wire parser for NTQQ blobs."""

from __future__ import annotations

from dataclasses import dataclass


class ProtoDecodeError(ValueError):
    """Raised when a protobuf blob cannot be decoded."""


@dataclass
class ProtoField:
    number: int
    wire_type: int
    value: int | bytes


@dataclass
class ProtoMessage:
    path: tuple[int, ...]
    fields: list[ProtoField]


def _read_varint(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while True:
        if offset >= len(data):
            raise ProtoDecodeError("unexpected EOF while reading varint")
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if byte < 0x80:
            return value, offset
        shift += 7
        if shift > 63:
            raise ProtoDecodeError("varint too long")


def parse_fields(data: bytes) -> list[ProtoField]:
    fields: list[ProtoField] = []
    offset = 0
    while offset < len(data):
        key, offset = _read_varint(data, offset)
        number = key >> 3
        wire_type = key & 0x07
        if number <= 0:
            raise ProtoDecodeError("invalid field number")

        if wire_type == 0:
            value, offset = _read_varint(data, offset)
        elif wire_type == 1:
            end = offset + 8
            if end > len(data):
                raise ProtoDecodeError("unexpected EOF while reading fixed64")
            value = int.from_bytes(data[offset:end], "little")
            offset = end
        elif wire_type == 2:
            length, offset = _read_varint(data, offset)
            end = offset + length
            if end > len(data):
                raise ProtoDecodeError("unexpected EOF while reading bytes")
            value = data[offset:end]
            offset = end
        elif wire_type == 5:
            end = offset + 4
            if end > len(data):
                raise ProtoDecodeError("unexpected EOF while reading fixed32")
            value = int.from_bytes(data[offset:end], "little")
            offset = end
        else:
            raise ProtoDecodeError(f"unsupported wire type: {wire_type}")

        fields.append(ProtoField(number=number, wire_type=wire_type, value=value))

    return fields


def is_probably_text(data: bytes) -> bool:
    if not data or b"\x00" in data:
        return False
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    printable = sum(1 for ch in text if ch.isprintable() or ch in "\r\n\t")
    return printable / max(len(text), 1) > 0.9


def try_decode_text(data: bytes) -> str | None:
    if not data:
        return ""
    if not is_probably_text(data):
        return None
    try:
        return data.decode("utf-8").strip()
    except UnicodeDecodeError:
        return None


def walk_messages(data: bytes, max_depth: int = 8) -> list[ProtoMessage]:
    result: list[ProtoMessage] = []

    def _walk(blob: bytes, path: tuple[int, ...], depth: int) -> None:
        if depth > max_depth or not blob:
            return
        try:
            fields = parse_fields(blob)
        except ProtoDecodeError:
            return
        result.append(ProtoMessage(path=path, fields=fields))
        for field in fields:
            if field.wire_type != 2 or not isinstance(field.value, bytes):
                continue
            if try_decode_text(field.value) is not None:
                continue
            _walk(field.value, path + (field.number,), depth + 1)

    _walk(data, tuple(), 0)
    return result


def field_ints(fields: list[ProtoField], number: int) -> list[int]:
    return [int(field.value) for field in fields if field.number == number and isinstance(field.value, int)]


def field_first_int(fields: list[ProtoField], number: int) -> int | None:
    values = field_ints(fields, number)
    return values[0] if values else None


def field_strings(fields: list[ProtoField], number: int) -> list[str]:
    values: list[str] = []
    for field in fields:
        if field.number != number or not isinstance(field.value, bytes):
            continue
        text = try_decode_text(field.value)
        if text is not None and text:
            values.append(text)
    return values


def field_first_string(fields: list[ProtoField], number: int) -> str | None:
    values = field_strings(fields, number)
    return values[0] if values else None


def collect_strings(data: bytes, interesting_fields: set[int] | None = None, max_depth: int = 8) -> list[str]:
    results: list[str] = []
    for message in walk_messages(data, max_depth=max_depth):
        for field in message.fields:
            if field.wire_type != 2 or not isinstance(field.value, bytes):
                continue
            if interesting_fields is not None and field.number not in interesting_fields:
                continue
            text = try_decode_text(field.value)
            if text:
                results.append(text)
    return results
