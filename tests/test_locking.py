import hashlib
import socket
import subprocess
import sys
import time
from pathlib import Path

from common.protocol import send_message, receive_message


HOST = "127.0.0.1"
PORT = 5050

BUFFER_SIZE = 64 * 1024


def calculate_sha256(file_path):
    sha256 = hashlib.sha256()

    with file_path.open("rb") as file:
        while True:
            chunk = file.read(BUFFER_SIZE)

            if not chunk:
                break

            sha256.update(chunk)

    return sha256.hexdigest()


def wait_for_server():
    for _ in range(50):
        sock = socket.socket(
            socket.AF_INET,
            socket.SOCK_STREAM
        )

        try:
            sock.connect((HOST, PORT))
            sock.close()
            return

        except ConnectionRefusedError:
            sock.close()
            time.sleep(0.1)

    raise RuntimeError("Server did not start")


def test_same_filename_is_locked(tmp_path):
    server_process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "server.server",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    first_socket = None
    second_socket = None

    output_path = Path(
        "received_files",
        "locking-test.bin"
    )

    partial_path = Path(
        "received_files",
        "locking-test.bin.part"
    )

    metadata_path = Path(
        "received_files",
        "locking-test.bin.part.json"
    )

    try:
        wait_for_server()

        test_file = tmp_path / "locking-test.bin"

        data = b"locking-test-data" * 4096
        test_file.write_bytes(data)

        file_size = test_file.stat().st_size
        file_hash = calculate_sha256(test_file)

        for path in (
            output_path,
            partial_path,
            metadata_path,
        ):
            if path.exists():
                path.unlink()

        # ---------------------------------------------------------
        # First client acquires the upload lock.
        # ---------------------------------------------------------

        first_socket = socket.socket(
            socket.AF_INET,
            socket.SOCK_STREAM
        )

        first_socket.connect((HOST, PORT))

        send_message(first_socket, {
            "type": "UPLOAD",
            "filename": test_file.name,
            "size": file_size,
            "sha256": file_hash,
        })

        first_response = receive_message(
            first_socket
        )

        assert first_response["type"] == "UPLOAD_READY"
        assert first_response["offset"] == 0

        # Send one chunk so the first client is actively
        # participating in the upload.
        with test_file.open("rb") as file:
            chunk = file.read(BUFFER_SIZE)

        first_socket.sendall(chunk)

        # ---------------------------------------------------------
        # Second client attempts the same filename.
        # ---------------------------------------------------------

        second_socket = socket.socket(
            socket.AF_INET,
            socket.SOCK_STREAM
        )

        second_socket.connect((HOST, PORT))

        send_message(second_socket, {
            "type": "UPLOAD",
            "filename": test_file.name,
            "size": file_size,
            "sha256": file_hash,
        })

        second_response = receive_message(
            second_socket
        )

        assert second_response["type"] == "UPLOAD_FAILED"

        assert (
            second_response["message"]
            == "Another client is currently "
               "uploading this file"
        )

    finally:
        if first_socket is not None:
            first_socket.close()

        if second_socket is not None:
            second_socket.close()

        if server_process.poll() is None:
            server_process.terminate()

            try:
                server_process.wait(timeout=5)

            except subprocess.TimeoutExpired:
                server_process.kill()
                server_process.wait()

        for path in (
            output_path,
            partial_path,
            metadata_path,
        ):
            if path.exists():
                path.unlink()