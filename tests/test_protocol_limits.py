import json
import socket
import struct

import pytest

from common.protocol import (
    MAX_MESSAGE_SIZE,
    receive_message,
    send_message,
)


def test_send_message_rejects_oversized_message():
    left, right = socket.socketpair()

    try:
        oversized_message = {
            "data": "x" * (MAX_MESSAGE_SIZE + 1)
        }

        with pytest.raises(ValueError, match="exceeds maximum size"):
            send_message(left, oversized_message)

    finally:
        left.close()
        right.close()


def test_receive_message_rejects_oversized_message():
    left, right = socket.socketpair()

    try:
        header = struct.pack(
            "!I",
            MAX_MESSAGE_SIZE + 1,
        )

        left.sendall(header)

        with pytest.raises(ValueError, match="exceeds maximum size"):
            receive_message(right)

    finally:
        left.close()
        right.close()


def test_receive_message_rejects_empty_message():
    left, right = socket.socketpair()

    try:
        left.sendall(
            struct.pack("!I", 0)
        )

        with pytest.raises(ValueError, match="cannot be empty"):
            receive_message(right)

    finally:
        left.close()
        right.close()


def test_receive_message_rejects_invalid_json():
    left, right = socket.socketpair()

    try:
        invalid_json = b"{invalid json"

        left.sendall(
            struct.pack(
                "!I",
                len(invalid_json),
            )
        )

        left.sendall(invalid_json)

        with pytest.raises(ValueError, match="Invalid JSON message"):
            receive_message(right)

    finally:
        left.close()
        right.close()


def test_receive_message_rejects_invalid_utf8():
    left, right = socket.socketpair()

    try:
        invalid_utf8 = b"\xff\xfe\xfd"

        left.sendall(
            struct.pack(
                "!I",
                len(invalid_utf8),
            )
        )

        left.sendall(invalid_utf8)

        with pytest.raises(ValueError, match="Invalid JSON message"):
            receive_message(right)

    finally:
        left.close()
        right.close()


def test_receive_message_accepts_valid_json():
    left, right = socket.socketpair()

    try:
        message = {
            "type": "UPLOAD",
            "filename": "test.txt",
        }

        data = json.dumps(message).encode("utf-8")

        left.sendall(
            struct.pack(
                "!I",
                len(data),
            )
        )

        left.sendall(data)

        received = receive_message(right)

        assert received == message

    finally:
        left.close()
        right.close()