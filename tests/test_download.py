import hashlib
import socket
import threading

import pytest

from client import client
from common.protocol import (
    receive_message,
    send_message,
)


@pytest.fixture
def fake_download_server():
    def start(file_data, advertised_hash):
        server_socket = socket.socket(
            socket.AF_INET,
            socket.SOCK_STREAM,
        )

        server_socket.setsockopt(
            socket.SOL_SOCKET,
            socket.SO_REUSEADDR,
            1,
        )

        server_socket.bind(
            ("127.0.0.1", 0)
        )

        server_socket.listen(1)

        port = server_socket.getsockname()[1]

        def run_server():
            client_socket = None

            try:
                client_socket, _ = server_socket.accept()

                request = receive_message(
                    client_socket
                )

                assert request["type"] == "DOWNLOAD"

                send_message(
                    client_socket,
                    {
                        "type": "DOWNLOAD_READY",
                        "filename": request["filename"],
                        "size": len(file_data),
                        "sha256": advertised_hash,
                    },
                )

                client_socket.sendall(file_data)

                try:
                    receive_message(
                        client_socket
                    )
                except (
                    ConnectionError,
                    socket.timeout,
                ):
                    pass

            finally:
                if client_socket is not None:
                    client_socket.close()

                server_socket.close()

        thread = threading.Thread(
            target=run_server,
            daemon=True,
        )

        thread.start()

        return port, thread

    return start


def configure_client(
    monkeypatch,
    port,
    download_dir,
):
    monkeypatch.setattr(
        client,
        "HOST",
        "127.0.0.1",
    )

    monkeypatch.setattr(
        client,
        "PORT",
        port,
    )

    monkeypatch.setattr(
        client,
        "DOWNLOAD_DIR",
        download_dir,
    )


def test_download_detects_checksum_mismatch(
    tmp_path,
    monkeypatch,
    fake_download_server,
):
    file_data = b"hello network transfer"

    wrong_hash = "0" * 64

    port, thread = fake_download_server(
        file_data,
        wrong_hash,
    )

    configure_client(
        monkeypatch,
        port,
        tmp_path,
    )

    client.download_file("test.bin")

    downloaded_file = tmp_path / "test.bin"
    partial_file = tmp_path / "test.bin.part"

    assert not downloaded_file.exists()

    assert partial_file.exists()

    assert partial_file.read_bytes() == file_data

    thread.join(timeout=2)


def test_download_verifies_correct_checksum(
    tmp_path,
    monkeypatch,
    fake_download_server,
):
    file_data = b"hello network transfer"

    correct_hash = hashlib.sha256(
        file_data
    ).hexdigest()

    port, thread = fake_download_server(
        file_data,
        correct_hash,
    )

    configure_client(
        monkeypatch,
        port,
        tmp_path,
    )

    client.download_file("test.bin")

    downloaded_file = tmp_path / "test.bin"
    partial_file = tmp_path / "test.bin.part"

    assert downloaded_file.exists()

    assert downloaded_file.read_bytes() == file_data

    assert not partial_file.exists()

    thread.join(timeout=2)