import socket

import pytest

from common.protocol import (
    receive_exact,
    receive_message,
    send_message,
)


def test_send_and_receive_message():
    server_socket, client_socket = socket.socketpair()

    try:
        message = {
            "type": "UPLOAD",
            "filename": "test.txt",
            "size": 123,
        }

        send_message(client_socket, message)

        received = receive_message(server_socket)

        assert received == message

    finally:
        server_socket.close()
        client_socket.close()


def test_multiple_messages():
    server_socket, client_socket = socket.socketpair()

    try:
        first_message = {
            "type": "UPLOAD",
            "filename": "first.txt",
        }

        second_message = {
            "type": "DOWNLOAD",
            "filename": "second.txt",
        }

        send_message(client_socket, first_message)
        send_message(client_socket, second_message)

        assert receive_message(server_socket) == first_message
        assert receive_message(server_socket) == second_message

    finally:
        server_socket.close()
        client_socket.close()


def test_receive_exact_returns_requested_size():
    server_socket, client_socket = socket.socketpair()

    try:
        data = b"hello world"

        client_socket.sendall(data)

        received = receive_exact(
            server_socket,
            len(data)
        )

        assert received == data

    finally:
        server_socket.close()
        client_socket.close()


def test_receive_exact_raises_when_connection_closes():
    server_socket, client_socket = socket.socketpair()

    try:
        client_socket.close()

        with pytest.raises(ConnectionError):
            receive_exact(
                server_socket,
                10
            )

    finally:
        server_socket.close()