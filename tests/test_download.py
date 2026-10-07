import hashlib
import socket
import threading

import pytest

from client.client import download_file
from common.protocol import receive_message, send_message


HOST = "127.0.0.1"


@pytest.fixture
def fake_download_server():
    def start(file_data, advertised_hash):
        server_socket = socket.socket(
            socket.AF_INET,
            socket.SOCK_STREAM,
        )

        server_socket.bind((HOST, 0))
        server_socket.listen(1)

        port = server_socket.getsockname()[1]

        def run_server():
            client_socket, _ = server_socket.accept()

            try:
                send_message(
                    client_socket,
                    {
                        "type": "DOWNLOAD_READY",
                        "filename": "test.bin",
                        "size": len(file_data),
                        "sha256": advertised_hash,
                    },
                )

                client_socket.sendall(file_data)

                receive_message(client_socket)

            finally:
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
        "client.client.HOST",
        HOST,
    )

    monkeypatch.setattr(
        "client.client.PORT",
        port,
    )

    monkeypatch.setattr(
        "client.client.DOWNLOAD_DIR",
        download_dir,
    )


def test_download_detects_checksum_mismatch(
    tmp_path,
    monkeypatch,
    fake_download_server,
):
    file_data = b"hello network transfer"

    correct_hash = hashlib.sha256(
        file_data
    ).hexdigest()

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

    download_file("test.bin")

    downloaded_file = tmp_path / "test.bin"

    assert downloaded_file.exists()

    actual_hash = hashlib.sha256(
        downloaded_file.read_bytes()
    ).hexdigest()

    assert actual_hash == correct_hash
    assert actual_hash != wrong_hash

    thread.join(timeout=2)

    assert not thread.is_alive()


def test_download_verifies_correct_checksum(
    tmp_path,
    monkeypatch,
    fake_download_server,
):
    file_data = b"hello reliable file transfer"

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

    download_file("test.bin")

    downloaded_file = tmp_path / "test.bin"

    assert downloaded_file.exists()
    assert downloaded_file.read_bytes() == file_data

    actual_hash = hashlib.sha256(
        downloaded_file.read_bytes()
    ).hexdigest()

    assert actual_hash == correct_hash

    thread.join(timeout=2)

    assert not thread.is_alive()