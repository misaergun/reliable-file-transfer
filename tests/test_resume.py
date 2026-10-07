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
PARTIAL_SIZE = 10 * 1024


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


def wait_for_partial_file(
    partial_path,
    expected_size,
    timeout=5,
):
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        if partial_path.exists():
            if partial_path.stat().st_size >= expected_size:
                return

        time.sleep(0.05)

    actual_size = (
        partial_path.stat().st_size
        if partial_path.exists()
        else 0
    )

    raise AssertionError(
        f"Partial file did not reach expected size. "
        f"Expected: {expected_size}, "
        f"Actual: {actual_size}"
    )


def test_resumable_upload(tmp_path):
    server_process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "server.server",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    test_file = None
    output_path = None
    partial_path = None
    metadata_path = None

    try:
        wait_for_server()

        test_file = tmp_path / "resume-test.bin"

        data = (
            b"0123456789abcdef"
            * 4096
        )

        test_file.write_bytes(data)

        file_size = test_file.stat().st_size
        file_hash = calculate_sha256(test_file)

        received_dir = Path("received_files")

        output_path = (
            received_dir / test_file.name
        )

        partial_path = (
            received_dir / f"{test_file.name}.part"
        )

        metadata_path = (
            received_dir / f"{test_file.name}.part.json"
        )

        for path in (
            output_path,
            partial_path,
            metadata_path,
        ):
            if path.exists():
                path.unlink()

        # ---------------------------------------------------------
        # First connection:
        # Send only part of the file and intentionally disconnect.
        # ---------------------------------------------------------

        sock = socket.socket(
            socket.AF_INET,
            socket.SOCK_STREAM
        )

        try:
            sock.connect((HOST, PORT))

            send_message(sock, {
                "type": "UPLOAD",
                "filename": test_file.name,
                "size": file_size,
                "sha256": file_hash,
            })

            response = receive_message(sock)

            assert response["type"] == "UPLOAD_READY"
            assert response["offset"] == 0

            with test_file.open("rb") as file:
                partial_data = file.read(
                    PARTIAL_SIZE
                )

            sock.sendall(partial_data)

            # Give the server a chance to receive the data before
            # intentionally closing the connection.
            wait_for_partial_file(
                partial_path,
                PARTIAL_SIZE,
            )

        finally:
            sock.close()

        assert partial_path.exists()
        assert partial_path.stat().st_size == PARTIAL_SIZE
        assert metadata_path.exists()

        # ---------------------------------------------------------
        # Second connection:
        # Server should resume from the partial file offset.
        # ---------------------------------------------------------

        sock = socket.socket(
            socket.AF_INET,
            socket.SOCK_STREAM
        )

        try:
            sock.connect((HOST, PORT))

            send_message(sock, {
                "type": "UPLOAD",
                "filename": test_file.name,
                "size": file_size,
                "sha256": file_hash,
            })

            response = receive_message(sock)

            assert response["type"] == "UPLOAD_READY"
            assert response["offset"] == PARTIAL_SIZE

            with test_file.open("rb") as file:
                file.seek(PARTIAL_SIZE)

                remaining = file_size - PARTIAL_SIZE

                while remaining > 0:
                    chunk = file.read(
                        min(BUFFER_SIZE, remaining)
                    )

                    if not chunk:
                        raise AssertionError(
                            "Unexpected end of source file"
                        )

                    sock.sendall(chunk)
                    remaining -= len(chunk)

            response = receive_message(sock)

            assert response["type"] == "TRANSFER_OK"

        finally:
            sock.close()

        # ---------------------------------------------------------
        # Verify final file.
        # ---------------------------------------------------------

        assert output_path.exists()
        assert output_path.stat().st_size == file_size

        assert (
            calculate_sha256(output_path)
            == file_hash
        )

        assert not partial_path.exists()
        assert not metadata_path.exists()

    finally:
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
            if path is not None and path.exists():
                path.unlink()